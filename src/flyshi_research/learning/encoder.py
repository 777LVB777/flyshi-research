"""Market features -> Kenyon-cell (KC) stimulation.

Pure numpy; no Brian2, no simulation. The output is a plain description of
"which KC root IDs get driven at what rate" that a simulation runner can consume.

Design (docs/design/mb-learning-interface.md, 4a):
  * each feature owns a fixed, seeded, DISJOINT pool of KC IDs;
  * a feature value becomes a firing rate by a bounded linear map, with
    out-of-range values clipped and the clipping REPORTED (never silent);
  * Option B (4b) needs two stimuli per decision: "YES at price p" and
    "NO at price 1 - p". By default a reserved KC pool exactly equalises their
    aggregate rate x pool-size drive; ``unbalanced`` retains the old behaviour
    as a named ablation.

Runner hand-off: ``Stimulus.rates_by_kc_id()`` gives the ``{root_id: Hz}`` mapping
that ``repro/mushroom_body/fast_runner.run_cue_rates`` consumes (the scalar-rate
``run_cue`` cannot express per-feature rates).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple

import numpy as np

from .params import (
    OPTION_B_BALANCED,
    OPTION_B_UNBALANCED,
    OPTION_B_VARIANTS,
    EncoderParams,
    FeatureSpec,
)

YES = "YES"
NO = "NO"
BALANCE_FEATURE = "__total_drive_balance__"


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

    def rates_by_kc_id(self, driven_only: bool = False) -> Dict[int, float]:
        """``{kc_root_id: rate_hz}`` - the plain mapping the per-neuron-rate runner
        (``fast_runner.run_cue_rates``) takes. Root IDs come out as Python ints, so
        no precision is lost. ``driven_only`` drops KCs at 0 Hz."""
        ids, rates = self.driven() if driven_only else (self.kc_ids, self.rates_hz)
        return {int(i): float(r) for i, r in zip(ids.tolist(), rates.tolist())}


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
        arr = np.asarray(list(kc_ids) if not isinstance(kc_ids, np.ndarray) else kc_ids)
        if arr.size == 0:
            raise ValueError("kc_ids is empty")
        if not np.issubdtype(arr.dtype, np.integer):
            raise TypeError(f"kc_ids must be integers, got dtype {arr.dtype}")
        ids = np.sort(arr.astype(np.int64))
        if np.any(ids[1:] == ids[:-1]):
            raise ValueError("kc_ids contains duplicates")
        feature_need = self.params.pool_size * len(self.specs)
        need = feature_need + self.params.balance_pool_size
        if need > ids.size:
            raise ValueError(
                f"need {need} distinct KCs ({feature_need} feature-pool KCs + "
                f"{self.params.balance_pool_size} balancing KCs) but only "
                f"{ids.size} were supplied"
            )
        shuffled = ids[np.random.default_rng(self.seed).permutation(ids.size)]
        names = list(self.specs)
        self.pools = {
            name: np.sort(
                shuffled[i * self.params.pool_size : (i + 1) * self.params.pool_size]
            )
            for i, name in enumerate(names)
        }
        self.balance_pool = np.sort(shuffled[feature_need:need])

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

    def option_b_stimuli(
        self, features: Mapping[str, float], variant: Optional[str] = None
    ) -> OptionBStimuli:
        """Build the paired Option B stimuli.

        ``total_drive_balanced`` (the default) leaves every feature-pool rate
        unchanged and appends the same reserved pool of ``B`` KCs to both
        framings. Let ``D_Y = sum_i rate_Y[i]`` and likewise ``D_N`` over the
        feature pools, ``r_min`` be the encoder minimum, and
        ``Delta = |D_Y-D_N|``. The higher-drive framing gives every balancing KC
        ``r_min``; the lower-drive framing gives each one

            r_min + Delta / B.

        Thus both totals are exactly ``max(D_Y,D_N) + B*r_min`` in real
        arithmetic. The capacity check in :class:`EncoderParams` guarantees the
        balancing rate remains within the encoder bounds for every in-range
        feature value. Because the existing encoder uses disjoint uniform pools,
        summing per-KC rates is exactly ``sum(rate_f * pool_size_f)``: this is the
        requested total spike-drive, while the identity/rate pattern remains the
        only difference between YES and NO. Floating-point totals can differ by
        machine rounding only.

        ``unbalanced`` returns the historical feature pools without the reserved
        pool and is retained solely as a named comparison/ablation.
        """
        chosen = self.params.option_b_variant if variant is None else variant
        if chosen not in OPTION_B_VARIANTS:
            raise ValueError(f"variant must be one of {OPTION_B_VARIANTS}, got {chosen!r}")
        yes = self.encode(features, YES)
        no = self.encode(features, NO)
        if chosen == OPTION_B_UNBALANCED:
            return OptionBStimuli(yes=yes, no=no)

        d_yes = float(np.sum(yes.rates_hz, dtype=np.float64))
        d_no = float(np.sum(no.rates_hz, dtype=np.float64))
        difference = abs(d_yes - d_no)
        low_balance_rate = self.params.min_rate_hz + difference / self.balance_pool.size
        if low_balance_rate > self.params.max_rate_hz + 1e-12:
            raise ValueError(
                "balancing pool lacks capacity for this Option B pair: "
                f"required rate {low_balance_rate:g} Hz exceeds "
                f"{self.params.max_rate_hz:g} Hz"
            )

        if d_yes >= d_no:
            yes_rate, no_rate = self.params.min_rate_hz, low_balance_rate
        else:
            yes_rate, no_rate = low_balance_rate, self.params.min_rate_hz
        return OptionBStimuli(
            yes=self._append_balance_pool(yes, yes_rate),
            no=self._append_balance_pool(no, no_rate),
        )

    def _append_balance_pool(self, stimulus: Stimulus, rate_hz: float) -> Stimulus:
        """Return ``stimulus`` with the encoder's reserved balancing pool."""
        feature_rates = dict(stimulus.feature_rates_hz)
        feature_rates[BALANCE_FEATURE] = float(rate_hz)
        feature_values = dict(stimulus.feature_values)
        feature_values[BALANCE_FEATURE] = float(rate_hz)
        return Stimulus(
            side=stimulus.side,
            kc_ids=np.concatenate((stimulus.kc_ids, self.balance_pool)),
            rates_hz=np.concatenate(
                (stimulus.rates_hz, np.full(self.balance_pool.size, rate_hz, dtype=np.float64))
            ),
            feature_rates_hz=feature_rates,
            feature_values=feature_values,
            clip_events=stimulus.clip_events,
            omitted=stimulus.omitted,
        )


def option_b_stimuli(
    encoder: KCEncoder,
    features: Mapping[str, float],
    variant: Optional[str] = None,
) -> OptionBStimuli:
    """Module-level form of :meth:`KCEncoder.option_b_stimuli`."""
    return encoder.option_b_stimuli(features, variant=variant)
