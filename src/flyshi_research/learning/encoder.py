"""Market features -> Kenyon-cell (KC) stimulation.

Pure numpy; no Brian2, no simulation. The output is a plain description of
"which KC root IDs get driven at what rate" that a simulation runner can consume.

Design (docs/design/mb-learning-interface.md, 4a):
  * each feature owns a fixed, seeded, DISJOINT pool of KC IDs;
  * a feature value becomes a firing rate by a bounded linear map, with
    out-of-range values clipped and the clipping REPORTED (never silent);
  * Option B (4b) needs two stimuli per decision: "YES at price p" and
    "NO at price 1 - p".

Note for whoever wires this to the runner: ``repro/mushroom_body/fast_runner.run_cue``
currently takes ONE scalar rate for the whole stimulated set. A ``Stimulus`` has a
per-KC rate array, so the runner will need a per-neuron-rate variant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple

import numpy as np

from .params import EncoderParams, FeatureSpec

YES = "YES"
NO = "NO"


@dataclass(frozen=True)
class ClipEvent:
    """A feature value that fell outside its declared range and was clipped."""

    feature: str
    raw: float
    clipped_to: float
    direction: str  # "low" or "high"


@dataclass(frozen=True, eq=False)
class Stimulus:
    """KC stimulation for one framing of one market.

    ``kc_ids[i]`` is driven at ``rates_hz[i]``. Every KC of an encoded feature's
    pool appears (a pool at 0 Hz appears with rate 0). Features that were
    optional and absent are listed in ``omitted`` and contribute no KCs.
    """

    side: str
    kc_ids: np.ndarray  # int64
    rates_hz: np.ndarray  # float64, parallel to kc_ids
    feature_rates_hz: Dict[str, float]
    feature_values: Dict[str, float]  # value actually encoded (after clip + any mirror)
    clip_events: Tuple[ClipEvent, ...]
    omitted: Tuple[str, ...]

    @property
    def was_clipped(self) -> bool:
        return len(self.clip_events) > 0

    def driven(self) -> Tuple[np.ndarray, np.ndarray]:
        """(kc_ids, rates_hz) restricted to KCs with rate > 0."""
        keep = self.rates_hz > 0
        return self.kc_ids[keep], self.rates_hz[keep]


@dataclass(frozen=True, eq=False)
class OptionBStimuli:
    """The two stimuli for one Option B decision."""

    yes: Stimulus  # "YES at price p"
    no: Stimulus  # "NO at price 1 - p"

    @property
    def was_clipped(self) -> bool:
        return self.yes.was_clipped or self.no.was_clipped


def assign_pools(
    kc_ids: Iterable[int], feature_names: Iterable[str], pool_size: int, seed: int
) -> Dict[str, np.ndarray]:
    """Draw one disjoint pool of ``pool_size`` KC IDs per feature.

    Deterministic in ``(set of kc_ids, feature order, pool_size, seed)``: the
    input is sorted first, so the caller's ordering does not matter. NOTE the
    pool a feature gets depends on its position in ``feature_names``; adding or
    reordering features reshuffles the assignment. (Draws come from numpy's
    PCG64 ``default_rng``; the stream is stable in practice but numpy does not
    formally guarantee it across major versions - freeze the pools you use.)
    """
    arr = np.asarray(list(kc_ids) if not isinstance(kc_ids, np.ndarray) else kc_ids)
    if arr.size == 0:
        raise ValueError("kc_ids is empty")
    if not np.issubdtype(arr.dtype, np.integer):
        # FlyWire root IDs are ~7e17; float64 would silently corrupt them.
        raise TypeError(f"kc_ids must be integers, got dtype {arr.dtype}")
    ids = np.sort(arr.astype(np.int64))
    if np.any(ids[1:] == ids[:-1]):
        raise ValueError("kc_ids contains duplicates")
    names = list(feature_names)
    need = pool_size * len(names)
    if need > ids.size:
        raise ValueError(
            f"need {need} distinct KCs ({len(names)} features x {pool_size}) but only "
            f"{ids.size} were supplied"
        )
    rng = np.random.default_rng(seed)
    shuffled = ids[rng.permutation(ids.size)]
    return {
        name: np.sort(shuffled[i * pool_size : (i + 1) * pool_size])
        for i, name in enumerate(names)
    }


def value_to_rate(
    value: float, spec: FeatureSpec, min_rate_hz: float, max_rate_hz: float
) -> Tuple[float, Optional[ClipEvent], float]:
    """Bounded linear map from a feature value to a KC firing rate.

        rate = min_rate + (clip(v, vmin, vmax) - vmin) / (vmax - vmin) * (max_rate - min_rate)

    Returns ``(rate_hz, clip_event_or_None, clipped_value)``. Non-finite values
    raise: they signal an upstream bug and must not become a plausible rate.
    """
    v = float(value)
    if not np.isfinite(v):
        raise ValueError(f"feature {spec.name!r}: non-finite value {value!r}")
    event = None
    if v < spec.min_value:
        event = ClipEvent(spec.name, v, spec.min_value, "low")
        v = spec.min_value
    elif v > spec.max_value:
        event = ClipEvent(spec.name, v, spec.max_value, "high")
        v = spec.max_value
    frac = (v - spec.min_value) / (spec.max_value - spec.min_value)
    return min_rate_hz + frac * (max_rate_hz - min_rate_hz), event, v


class KCEncoder:
    """Fixed-pool, fixed-mapping encoder from market features to KC stimulation."""

    def __init__(
        self,
        kc_ids: Iterable[int],
        seed: Optional[int] = None,
        params: Optional[EncoderParams] = None,
    ) -> None:
        """``kc_ids``: the KC IDs to draw from (pass LEFT-hemisphere KCs; this
        class does not know or filter hemisphere and hardcodes no IDs)."""
        self.params = params or EncoderParams()
        self.seed = self.params.pool_seed if seed is None else seed
        self.specs: Dict[str, FeatureSpec] = {f.name: f for f in self.params.features}
        # Pools for ALL features, including optional ones, so an absent optional
        # feature never shifts anyone else's pool.
        self.pools: Dict[str, np.ndarray] = assign_pools(
            kc_ids, list(self.specs), self.params.pool_size, self.seed
        )

    def encode(self, features: Mapping[str, float], side: str = YES) -> Stimulus:
        """Encode one market's features for one framing (``"YES"`` or ``"NO"``).

        Under ``"NO"``, features with ``mirror_for_no`` are reflected about their
        range midpoint AFTER clipping (price p -> 1 - p). Unknown feature names
        and missing required features raise ValueError.
        """
        if side not in (YES, NO):
            raise ValueError(f"side must be 'YES' or 'NO', got {side!r}")
        unknown = set(features) - set(self.specs)
        if unknown:
            raise ValueError(f"unknown features: {sorted(unknown)}")
        missing = [n for n, s in self.specs.items() if s.required and n not in features]
        if missing:
            raise ValueError(f"missing required features: {missing}")

        ids, rates = [], []
        f_rates: Dict[str, float] = {}
        f_values: Dict[str, float] = {}
        clips = []
        omitted = []
        for name, spec in self.specs.items():  # spec order = deterministic output order
            if name not in features:
                omitted.append(name)
                continue
            rate, event, clipped_value = value_to_rate(
                features[name], spec, self.params.min_rate_hz, self.params.max_rate_hz
            )
            if event is not None:
                clips.append(event)
            used = clipped_value
            if side == NO and spec.mirror_for_no:
                used = spec.min_value + spec.max_value - clipped_value
                rate, _, _ = value_to_rate(
                    used, spec, self.params.min_rate_hz, self.params.max_rate_hz
                )
            pool = self.pools[name]
            ids.append(pool)
            rates.append(np.full(pool.size, rate, dtype=np.float64))
            f_rates[name] = rate
            f_values[name] = used
        return Stimulus(
            side=side,
            kc_ids=np.concatenate(ids) if ids else np.empty(0, dtype=np.int64),
            rates_hz=np.concatenate(rates) if rates else np.empty(0, dtype=np.float64),
            feature_rates_hz=f_rates,
            feature_values=f_values,
            clip_events=tuple(clips),
            omitted=tuple(omitted),
        )

    def option_b_stimuli(self, features: Mapping[str, float]) -> OptionBStimuli:
        """The two Option B stimuli: "YES at price p" and "NO at price 1 - p"."""
        return OptionBStimuli(yes=self.encode(features, YES), no=self.encode(features, NO))


def option_b_stimuli(encoder: KCEncoder, features: Mapping[str, float]) -> OptionBStimuli:
    """Module-level form of :meth:`KCEncoder.option_b_stimuli`."""
    return encoder.option_b_stimuli(features)
