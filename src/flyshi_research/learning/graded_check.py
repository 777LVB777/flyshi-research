"""Verdict logic for the graded-rate encoding test (docs/design/graded-encoding.md).

Pure numpy; no Brian2, no simulation. The criteria below were written BEFORE any
run and are fixed constants here; they must not be edited after seeing data. To
change them, write a new dated pre-statement instead.

REVISION NOTES (both made on 2026-09-21, BEFORE the test was run and before any
result existed):
  1. This three-outcome rule replaced an earlier two-outcome rule (ACCEPTED / NOT
     ACCEPTED). Reason: saturation at high rates is plausible neuron behaviour and
     indicates a usable range rather than a failed encoding.
  2. USABLE RANGE additionally requires the chosen sub-range's OWN endpoint
     distance to clear 3 x d_AA (closing a loophole: the 30-vs-150 Hz gate alone
     could let through a sub-range whose change is inside the noise).

The question: the encoder turns a feature value into a KC firing rate. Does the
MBON readout change monotonically with that rate, and by more than the noise?

  ACCEPTED      the CIRCUIT score (per-type mean, 80% table) is STRICTLY monotonic
                across all five rates AND the Euclidean distance between the MBON
                vectors at 30 and 150 Hz is >= 3 x d_AA (d_AA = 5.10 Hz).
  USABLE RANGE  the endpoint distance passes but the score is not monotonic across
                all five rates (in practice: monotonicity breaks at the top or
                bottom), AND the longest strictly monotonic CONTIGUOUS sub-range of
                at least three rates has its own endpoint distance (MBON vectors at
                that sub-range's first and last rates) >= 3 x d_AA. The encoder's
                rate bounds must then equal that sub-range before any learning
                experiment.
  FAIL          the endpoint distance is below 3 x d_AA, OR no strictly monotonic
                contiguous sub-range spans at least three rates, OR the chosen
                sub-range's own endpoint distance is below 3 x d_AA. Value encoding
                by rate fails; the encoder must change before any learning experiment.

After the test, the encoder's min_rate_hz and max_rate_hz must EQUAL the validated
range (all five rates, 30-150 Hz, for ACCEPTED; the sub-range for USABLE RANGE);
see ``encoder_params_for`` / ``require_encoder_matches``.

"Strictly monotonic" = successive differences all > 0 or all < 0 (either
direction; an exact tie is a violation). Tie-break when several sub-ranges share
the longest length (the rule did not say; fixed here before any run): larger
absolute score change from first to last rate, then the lower starting rate.
The 30-vs-150 Hz endpoint gate applies FIRST, whatever sub-range is selected. The
sub-range gate is then applied to the ONE chosen sub-range (the longest, after the
tie-break); there is no fall-back to a shorter or tied alternative that would pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from dataclasses import replace

from .params import EncoderParams
from .readout import SignTable, circuit_score, load_sign_table

# ---- pre-stated design of the test (fixed) ---------------------------------- #
PRESTATED_RATES_HZ: Tuple[float, ...] = (30.0, 60.0, 90.0, 120.0, 150.0)
PRESTATED_DURATION_MS = 1000.0
PRESTATED_TRIALS = 5
PRESTATED_KC_SET_SIZE = 100
PRESTATED_KC_SET_SEED = 20260316  # selects set A (the first of two disjoint sets)
PRESTATED_SEED = 20260316  # simulation seed, the same for all five rates
PRESTATED_SIGN_TABLE = "circuit_80"
PRESTATED_AGGREGATION = "type_mean"

# ---- pre-stated acceptance criterion (fixed) -------------------------------- #
D_AA_NOISE_FLOOR_HZ = 5.10  # same-cue noise floor, docs/design/mbon-separability.md
NOISE_MARGIN = 3.0
DISTANCE_THRESHOLD_HZ = NOISE_MARGIN * D_AA_NOISE_FLOOR_HZ  # 15.30 Hz
MIN_SUBRANGE_RATES = 3  # a usable sub-range must span at least this many rates


class Verdict(str, Enum):
    ACCEPTED = "ACCEPTED"
    USABLE_RANGE = "USABLE RANGE"
    FAIL = "FAIL"


def strictly_monotonic(values: Sequence[float]) -> Tuple[bool, str]:
    """(is_strictly_monotonic, "increasing" | "decreasing" | "none")."""
    v = np.asarray(values, dtype=np.float64)
    if v.ndim != 1 or v.size < 2:
        raise ValueError("need a 1-D sequence of at least 2 values")
    d = np.diff(v)
    if np.all(d > 0):
        return True, "increasing"
    if np.all(d < 0):
        return True, "decreasing"
    return False, "none"


def euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError(f"vector shapes differ: {x.shape} vs {y.shape}")
    return float(np.linalg.norm(x - y))


@dataclass(frozen=True)
class MonotonicRun:
    """A maximal strictly monotonic contiguous run: value indices start..end (inclusive)."""

    start: int
    end: int
    direction: str  # "increasing" | "decreasing"

    @property
    def n_rates(self) -> int:
        return self.end - self.start + 1


def monotonic_runs(values: Sequence[float]) -> List[MonotonicRun]:
    """All maximal strictly monotonic contiguous runs (each spanning >= 2 values).

    Adjacent runs of opposite direction share their turning-point value; an exact
    tie (zero difference) belongs to no run.
    """
    v = np.asarray(values, dtype=np.float64)
    if v.ndim != 1 or v.size < 2:
        raise ValueError("need a 1-D sequence of at least 2 values")
    sign = np.sign(np.diff(v))
    runs: List[MonotonicRun] = []
    i = 0
    while i < len(sign):
        if sign[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < len(sign) and sign[j + 1] == sign[i]:
            j += 1
        runs.append(MonotonicRun(i, j + 1, "increasing" if sign[i] > 0 else "decreasing"))
        i = j + 1
    return runs


def select_usable_subrange(
    values: Sequence[float], min_rates: int = MIN_SUBRANGE_RATES
) -> Tuple[Optional[MonotonicRun], Tuple[MonotonicRun, ...]]:
    """(chosen longest strictly monotonic contiguous sub-range, all sub-ranges tied
    for longest). ``(None, ())`` if no run spans at least ``min_rates`` values.

    Tie-break among equally long runs: larger |last - first| score change, then
    the lower starting index. Pre-stated because the rule left it open.
    """
    v = np.asarray(values, dtype=np.float64)
    candidates = [r for r in monotonic_runs(v) if r.n_rates >= min_rates]
    if not candidates:
        return None, ()
    longest = max(r.n_rates for r in candidates)
    tied = tuple(r for r in candidates if r.n_rates == longest)
    best = min(tied, key=lambda r: (-abs(v[r.end] - v[r.start]), r.start))
    return best, tied


@dataclass(frozen=True)
class GradedResult:
    verdict: Verdict
    rates_hz: Tuple[float, ...]
    scores: Tuple[float, ...]  # CIRCUIT score at each rate
    monotonic: bool  # strictly monotonic across ALL five rates
    direction: str  # of the full-range score sequence ("none" if not monotonic)
    distance_lo_hi_hz: float  # Euclidean, lowest vs highest rate (the gate)
    distance_threshold_hz: float
    distance_ok: bool
    # Validated range the encoder's rate bounds may use: (lo, hi) in Hz. The full
    # tested range for ACCEPTED, the selected sub-range for USABLE RANGE, None for FAIL.
    validated_range_hz: Optional[Tuple[float, float]]
    validated_direction: Optional[str]
    tied_longest_subranges_hz: Tuple[Tuple[float, float], ...]  # all sub-ranges tied for longest
    fail_reasons: Tuple[str, ...]  # non-empty only for FAIL
    # The chosen (longest, after tie-break) strictly monotonic sub-range and its OWN
    # endpoint distance. This is a GATE for USABLE RANGE; it is populated whenever a
    # sub-range exists, including when it is what caused a FAIL.
    chosen_subrange_hz: Optional[Tuple[float, float]]
    chosen_subrange_distance_hz: Optional[float]
    chosen_subrange_distance_ok: Optional[bool]
    # ---- diagnostics: reported, NOT part of the criterion --------------------
    n_nonzero_mbons: Tuple[int, ...]
    distances_from_lowest_hz: Tuple[float, ...]  # d(30 Hz, r) for each rate r
    vector_distance_nondecreasing: bool  # do the vectors move steadily away from 30 Hz?
    n_mbons_active: int  # MBONs nonzero at any rate
    n_mbons_weakly_monotonic: int  # of those, how many never reverse direction
    score_noise_note: str = (
        "single seed, no tolerance: a marginal score reversal may be noise (d_AA is "
        "measured at 150 Hz only); the criterion was pre-stated without a tolerance"
    )

    @property
    def accepted(self) -> bool:
        return self.verdict == Verdict.ACCEPTED

    def summary_lines(self) -> List[str]:
        lines = ["rate_hz  circuit_score  n_nonzero_mbons  dist_from_30Hz"]
        for r, s, n, d in zip(self.rates_hz, self.scores, self.n_nonzero_mbons,
                              self.distances_from_lowest_hz):
            lines.append(f"{r:7g}  {s:13.3f}  {n:15d}  {d:14.2f}")
        lines += [
            f"endpoint gate: |MBON({self.rates_hz[0]:g} Hz) - MBON({self.rates_hz[-1]:g} Hz)| = "
            f"{self.distance_lo_hi_hz:.2f} Hz vs threshold {self.distance_threshold_hz:.2f} Hz "
            f"({NOISE_MARGIN:g} x d_AA {D_AA_NOISE_FLOOR_HZ}): {'pass' if self.distance_ok else 'FAIL'}",
            f"CIRCUIT score strictly monotonic across all five rates: {self.monotonic}"
            + (f" ({self.direction})" if self.monotonic else ""),
        ]
        if self.chosen_subrange_hz is not None and not self.monotonic:
            a, b = self.chosen_subrange_hz
            lines.append(
                f"sub-range gate: chosen sub-range {a:g}-{b:g} Hz: |MBON({a:g} Hz) - MBON({b:g} Hz)| = "
                f"{self.chosen_subrange_distance_hz:.2f} Hz vs threshold {self.distance_threshold_hz:.2f} Hz: "
                f"{'pass' if self.chosen_subrange_distance_ok else 'FAIL'}"
            )
        lines.append(f"VERDICT: {self.verdict.value}")
        if self.verdict == Verdict.ACCEPTED:
            lines.append(f"validated range: {self.validated_range_hz[0]:g}-{self.validated_range_hz[1]:g} Hz "
                         "(the full tested range). The encoder's rate bounds must EQUAL it; rates outside "
                         "it are untested.")
        elif self.verdict == Verdict.USABLE_RANGE:
            lo, hi = self.validated_range_hz
            lines.append(
                f"longest strictly monotonic contiguous sub-range: {lo:g}-{hi:g} Hz "
                f"({self.validated_direction}). The encoder's rate bounds must EQUAL "
                f"{lo:g}-{hi:g} Hz (i.e. be RESTRICTED to it) before any learning experiment."
            )
            if len(self.tied_longest_subranges_hz) > 1:
                tied = ", ".join(f"{a:g}-{b:g}" for a, b in self.tied_longest_subranges_hz)
                lines.append(f"note: sub-ranges tied for longest: {tied} Hz; chosen by the pre-stated "
                             "tie-break (larger score change, then lower start).")
        else:
            lines.append("FAIL reason(s): " + "; ".join(self.fail_reasons))
            lines.append("Value encoding by rate fails; the encoder must change before any learning experiment.")
        lines += [
            f"diagnostic: vector distance from {self.rates_hz[0]:g} Hz non-decreasing: "
            f"{self.vector_distance_nondecreasing}",
            f"diagnostic: {self.n_mbons_weakly_monotonic}/{self.n_mbons_active} active MBONs "
            "never reverse direction across the five rates",
        ]
        return lines


def evaluate(
    vectors_by_rate: Mapping[float, Sequence[float]],
    labels: Sequence[str],
    table: Optional[SignTable] = None,
    aggregation: str = PRESTATED_AGGREGATION,
) -> GradedResult:
    """Apply the pre-stated three-outcome rule.

    ``vectors_by_rate``: exactly the five pre-stated rates -> a firing-rate vector
    (Hz) over ALL MBON instances, silent ones as 0, in the same order as
    ``labels`` (the cell-type label of each instance).
    """
    if set(vectors_by_rate) != set(PRESTATED_RATES_HZ):
        raise ValueError(
            f"need exactly the pre-stated rates {PRESTATED_RATES_HZ}, got {sorted(vectors_by_rate)}"
        )
    table = table if table is not None else load_sign_table(PRESTATED_SIGN_TABLE)
    rates = PRESTATED_RATES_HZ
    vecs: Dict[float, np.ndarray] = {r: np.asarray(vectors_by_rate[r], dtype=np.float64) for r in rates}
    scores = tuple(circuit_score(vecs[r], labels, table, aggregation).score for r in rates)
    monotonic, direction = strictly_monotonic(scores)
    lo, hi = rates[0], rates[-1]
    dist = euclidean(vecs[lo], vecs[hi])
    dist_ok = dist >= DISTANCE_THRESHOLD_HZ
    from_lowest = tuple(euclidean(vecs[lo], vecs[r]) for r in rates)

    best, tied = select_usable_subrange(scores)
    chosen = sub_dist = sub_ok = None
    if best is not None:
        chosen = (rates[best.start], rates[best.end])
        sub_dist = euclidean(vecs[chosen[0]], vecs[chosen[1]])
        sub_ok = bool(sub_dist >= DISTANCE_THRESHOLD_HZ)
    fail_reasons: List[str] = []
    if not dist_ok:
        fail_reasons.append(
            f"endpoint distance {dist:.2f} Hz is below the {DISTANCE_THRESHOLD_HZ:.2f} Hz threshold"
        )
    if best is None:
        fail_reasons.append(
            f"no strictly monotonic contiguous sub-range spans at least {MIN_SUBRANGE_RATES} rates"
        )
    elif best.n_rates < len(rates) and not sub_ok:
        # (A full-range sub-range has the same endpoints as the endpoint gate above.)
        fail_reasons.append(
            f"chosen sub-range {chosen[0]:g}-{chosen[1]:g} Hz: its own endpoint distance "
            f"{sub_dist:.2f} Hz is below the {DISTANCE_THRESHOLD_HZ:.2f} Hz threshold"
        )

    if fail_reasons:
        verdict = Verdict.FAIL
    elif monotonic:
        verdict = Verdict.ACCEPTED
    else:
        verdict = Verdict.USABLE_RANGE

    if verdict == Verdict.ACCEPTED:
        validated, v_dir = (lo, hi), direction
    elif verdict == Verdict.USABLE_RANGE:
        validated, v_dir = (rates[best.start], rates[best.end]), best.direction
    else:
        validated, v_dir = None, None

    stack = np.vstack([vecs[r] for r in rates])  # (5, n_mbon)
    active = np.any(stack > 0, axis=0)
    diffs = np.diff(stack[:, active], axis=0)  # (4, n_active)
    weakly = np.all(diffs >= 0, axis=0) | np.all(diffs <= 0, axis=0)
    return GradedResult(
        verdict=verdict,
        rates_hz=rates,
        scores=scores,
        monotonic=monotonic,
        direction=direction,
        distance_lo_hi_hz=dist,
        distance_threshold_hz=DISTANCE_THRESHOLD_HZ,
        distance_ok=dist_ok,
        validated_range_hz=validated,
        validated_direction=v_dir,
        tied_longest_subranges_hz=tuple((rates[r.start], rates[r.end]) for r in tied),
        fail_reasons=tuple(fail_reasons),
        chosen_subrange_hz=chosen,
        chosen_subrange_distance_hz=sub_dist,
        chosen_subrange_distance_ok=sub_ok,
        n_nonzero_mbons=tuple(int(np.sum(vecs[r] > 0)) for r in rates),
        distances_from_lowest_hz=from_lowest,
        vector_distance_nondecreasing=bool(np.all(np.diff(from_lowest) >= 0)),
        n_mbons_active=int(active.sum()),
        n_mbons_weakly_monotonic=int(weakly.sum()),
    )


# ---- what the verdict means for the encoder --------------------------------- #
def validated_encoder_bounds(result: GradedResult) -> Tuple[float, float]:
    """The (min_rate_hz, max_rate_hz) the encoder must use after this test: the whole
    tested range for ACCEPTED, the chosen sub-range for USABLE RANGE. Raises on FAIL
    (there is no validated range; the encoder must change)."""
    if result.validated_range_hz is None:
        raise ValueError(
            "graded-encoding verdict is FAIL: no validated rate range exists, so the "
            "encoder must change before any learning experiment"
        )
    return result.validated_range_hz


def encoder_params_for(result: GradedResult, base: Optional[EncoderParams] = None) -> EncoderParams:
    """``base`` (default: EncoderParams()) with min/max rate set to the validated range."""
    lo, hi = validated_encoder_bounds(result)
    return replace(base if base is not None else EncoderParams(), min_rate_hz=lo, max_rate_hz=hi)


def require_encoder_matches(params: EncoderParams, result: GradedResult) -> None:
    """Raise unless the encoder's rate bounds EQUAL the validated range exactly."""
    lo, hi = validated_encoder_bounds(result)
    if (params.min_rate_hz, params.max_rate_hz) != (lo, hi):
        raise ValueError(
            f"encoder rate bounds {params.min_rate_hz:g}-{params.max_rate_hz:g} Hz do not equal the "
            f"validated range {lo:g}-{hi:g} Hz (verdict {result.verdict.value}); use "
            "encoder_params_for(result)"
        )
