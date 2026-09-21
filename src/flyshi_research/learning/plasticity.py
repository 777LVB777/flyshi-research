"""Compartment-matched KC->MBON plasticity and the pending-decision queue.

Pure numpy; no Brian2, no simulation. Operates on a plain (n_kc x n_mbon) weight
matrix (design doc 4d).

Rule (multiplicative depression toward a floor, plus drift toward baseline)::

    e_k   = KC eligibility in [0, 1] from the pattern saved at decision time
            (0 at or below kc_active_threshold_hz, else min(rate / kc_rate_ref_hz, 1))
    g_j   = clip( sum_t strength_t * mask_t[j], 0, 1 )   # dopamine gate per MBON
    f_kj  = learning_rate * e_k * g_j                    # in [0, 1]: each factor is
    F     = floor_fraction * W0                          # floor (W0 = connectome weights)
    W    <- W - f * (W - F)                              # weaken; never crosses F
    W    <- W0 + (1 - drift_rate)^n * (W - W0)           # drift, n drift steps

* Only MBONs inside the compartment of the firing dopamine type get g_j > 0, so
  every other column is left EXACTLY unchanged (no "everything smells bad").
* Only recently-active KCs get e_k > 0, so inactive KC rows are left EXACTLY
  unchanged by depression.
* "Weaken" = reduce weight MAGNITUDE toward the floor, so the rule is also
  well-defined for negative (inhibitory) baseline weights.
* Drift touches every weight (that is its job) and is a no-op on weights already
  at baseline.

The compartment map is inferred from v783 dopamine->MBON wiring and is
UNVERIFIED (design docs); ambiguous/zero-sign MBONs belong to no compartment.
Cues that SHARE KCs will interfere on the shared KC rows; disjoint pools do not.

Abstentions (decided): a decision whose readout was ABSTAIN causes NO learning
update - no depression and no drift; its market resolving later leaves the
weights bit-identical. Only acted (YES/NO) decisions enter the queue. Consequence
to keep in mind: drift advances only on resolutions of acted decisions (call
``advance`` for time passing), and an abstained market's outcome teaches nothing.
The abstention rate is tracked in ``PlasticKCMBON.tally``.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from .params import PlasticityParams
from .readout import Choice, DecisionTally, dominant_family


# --------------------------------------------------------------------------- #
# compartment map
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, eq=False)
class CompartmentMap:
    """Which MBONs each dopamine type may modify.

    ``masks[type]`` is a length-``n_mbon`` array in [0, 1]. Type names are
    arbitrary strings (``"PAM"``/``"PPL1"`` at family level, or finer such as
    ``"PAM06"``) - whatever keys the caller later passes as dopamine strengths.
    A dopamine type absent from the map is an error, and an MBON in no mask is
    never plastic.
    """

    n_mbon: int
    masks: Dict[str, np.ndarray]

    def __post_init__(self) -> None:
        clean = {}
        for k, m in self.masks.items():
            a = np.asarray(m, dtype=np.float64)
            if a.shape != (self.n_mbon,):
                raise ValueError(f"mask {k!r} has shape {a.shape}, expected ({self.n_mbon},)")
            if not (np.all(np.isfinite(a)) and np.all((a >= 0) & (a <= 1))):
                raise ValueError(f"mask {k!r} must be finite and within [0, 1]")
            clean[k] = a
        object.__setattr__(self, "masks", clean)

    @classmethod
    def from_dopamine_counts(
        cls,
        mbon_labels: Sequence[str],
        counts: Mapping[str, Tuple[int, int]],
        threshold_pct: float,
    ) -> "CompartmentMap":
        """Family-level map from direct dopamine->MBON synapse totals.

        MBON j is in the PAM compartment if PAM supplies >= ``threshold_pct`` of
        its annotated dopamine input (same dominant-family rule as CIRCUIT),
        likewise PPL1. Labels missing from ``counts``, with no annotated input,
        or with mixed input are in NO compartment (plasticity disabled). Use the
        same threshold as the CIRCUIT readout variant under test. UNVERIFIED.
        """
        pam = np.zeros(len(mbon_labels))
        ppl1 = np.zeros(len(mbon_labels))
        for j, label in enumerate(mbon_labels):
            if label not in counts:
                continue
            fam = dominant_family(*counts[label], threshold_pct)
            if fam == "PAM":
                pam[j] = 1.0
            elif fam == "PPL1":
                ppl1[j] = 1.0
        return cls(n_mbon=len(mbon_labels), masks={"PAM": pam, "PPL1": ppl1})


# --------------------------------------------------------------------------- #
# pure update functions
# --------------------------------------------------------------------------- #
def kc_eligibility(kc_rates: Sequence[float], params: PlasticityParams) -> np.ndarray:
    """Eligibility in [0, 1] of each KC given its rate (Hz) at decision time."""
    r = np.asarray(kc_rates, dtype=np.float64)
    if r.ndim != 1:
        raise ValueError("kc pattern must be 1-D")
    if not np.all(np.isfinite(r)) or np.any(r < 0):
        raise ValueError("kc pattern must be finite and >= 0")
    e = np.clip(r / params.kc_rate_ref_hz, 0.0, 1.0)
    e[r <= params.kc_active_threshold_hz] = 0.0
    return e


def _check_weights(w: np.ndarray, name: str) -> np.ndarray:
    a = np.asarray(w, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError(f"{name} must be 2-D (n_kc x n_mbon), got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains non-finite values")
    return a


def depress(
    weights: np.ndarray,
    baseline: np.ndarray,
    kc_pattern: Sequence[float],
    dopamine: Mapping[str, float],
    compartments: CompartmentMap,
    params: PlasticityParams,
) -> np.ndarray:
    """Return NEW weights after one dopamine event (input arrays are not modified).

    ``dopamine`` maps dopamine type -> strength in [0, 1]. Unknown types raise.
    Entries with zero effective step (inactive KC, out-of-compartment MBON, or
    zero dopamine) are returned bit-identical.
    """
    W = _check_weights(weights, "weights")
    W0 = _check_weights(baseline, "baseline")
    if W.shape != W0.shape:
        raise ValueError("weights and baseline must have the same shape")
    n_kc, n_mbon = W.shape
    if n_mbon != compartments.n_mbon:
        raise ValueError(f"compartment map covers {compartments.n_mbon} MBONs, weights have {n_mbon}")
    e = kc_eligibility(kc_pattern, params)
    if e.size != n_kc:
        raise ValueError(f"kc pattern has {e.size} KCs, weights have {n_kc}")

    gate = np.zeros(n_mbon)
    for dtype, strength in dopamine.items():
        if dtype not in compartments.masks:
            raise ValueError(
                f"dopamine type {dtype!r} not in compartment map {sorted(compartments.masks)}"
            )
        s = float(strength)
        if not (np.isfinite(s) and 0.0 <= s <= 1.0):
            raise ValueError(f"dopamine strength for {dtype!r} must be in [0, 1], got {strength!r}")
        gate += s * compartments.masks[dtype]
    gate = np.clip(gate, 0.0, 1.0)

    f = params.learning_rate * np.outer(e, gate)  # each factor is in [0, 1], so f is too
    floor = params.floor_fraction * W0
    moved = W - f * (W - floor)
    # Enforce the floor on the weakening side (magnitude never below the floor).
    # Only entries with f > 0 are returned modified: an untouched weight is never
    # rewritten, even if it happens to start below the floor.
    moved = np.where(W0 >= 0, np.maximum(moved, floor), np.minimum(moved, floor))
    return np.where(f > 0, moved, W)


def drift(
    weights: np.ndarray, baseline: np.ndarray, params: PlasticityParams, n_steps: int = 1
) -> np.ndarray:
    """Return NEW weights after ``n_steps`` drift steps toward ``baseline``
    (closed form of repeatedly closing ``drift_rate`` of the remaining gap)."""
    if n_steps < 0:
        raise ValueError("n_steps must be >= 0")
    W = _check_weights(weights, "weights")
    W0 = _check_weights(baseline, "baseline")
    if W.shape != W0.shape:
        raise ValueError("weights and baseline must have the same shape")
    keep = (1.0 - params.drift_rate) ** n_steps
    if keep == 1.0:  # no drift: return weights bit-identical, not W0 + (W - W0)
        return W.copy()
    return W0 + keep * (W - W0)


# --------------------------------------------------------------------------- #
# decision queue
# --------------------------------------------------------------------------- #
class DuplicateMarketError(ValueError):
    pass


class UnknownMarketError(KeyError):
    pass


@dataclass(frozen=True, eq=False)
class PendingDecision:
    market_id: str
    kc_pattern: np.ndarray  # private copy, read-only
    meta: Dict[str, Any] = field(default_factory=dict)


class DecisionQueue:
    """Pending decisions awaiting a market outcome, keyed by market id.

    Insertion order is kept for inspection only; resolution may happen in any
    order and always uses the pattern stored for THAT market.
    """

    def __init__(self, n_kc: int) -> None:
        self.n_kc = n_kc
        self._pending: "OrderedDict[str, PendingDecision]" = OrderedDict()

    def record(self, market_id: str, kc_pattern: Sequence[float], **meta: Any) -> None:
        if market_id in self._pending:
            raise DuplicateMarketError(f"market {market_id!r} already has a pending decision")
        p = np.array(kc_pattern, dtype=np.float64)  # copy: caller may mutate theirs
        if p.shape != (self.n_kc,):
            raise ValueError(f"kc pattern has shape {p.shape}, expected ({self.n_kc},)")
        if not np.all(np.isfinite(p)) or np.any(p < 0):
            raise ValueError("kc pattern must be finite and >= 0")
        p.flags.writeable = False
        self._pending[market_id] = PendingDecision(market_id, p, dict(meta))

    def peek(self, market_id: str) -> PendingDecision:
        try:
            return self._pending[market_id]
        except KeyError:
            raise UnknownMarketError(f"no pending decision for market {market_id!r}") from None

    def pop(self, market_id: str) -> PendingDecision:
        try:
            return self._pending.pop(market_id)
        except KeyError:
            raise UnknownMarketError(f"no pending decision for market {market_id!r}") from None

    def discard(self, market_id: str) -> None:
        """Drop a pending decision without teaching (e.g. voided market). No-op if absent."""
        self._pending.pop(market_id, None)

    def pending_ids(self) -> List[str]:
        return list(self._pending)

    def __contains__(self, market_id: object) -> bool:
        return market_id in self._pending

    def __len__(self) -> int:
        return len(self._pending)


# --------------------------------------------------------------------------- #
# stateful wrapper
# --------------------------------------------------------------------------- #
class PlasticKCMBON:
    """Current KC->MBON weights + connectome baseline + pending-decision queue."""

    def __init__(
        self,
        baseline_weights: np.ndarray,
        compartments: CompartmentMap,
        params: Optional[PlasticityParams] = None,
    ) -> None:
        self.params = params or PlasticityParams()
        self.compartments = compartments
        self._baseline = _check_weights(baseline_weights, "baseline_weights").copy()
        self._baseline.flags.writeable = False
        self._weights = self._baseline.copy()
        self.n_kc, self.n_mbon = self._baseline.shape
        if self.n_mbon != compartments.n_mbon:
            raise ValueError("compartment map size does not match weight matrix")
        self.queue = DecisionQueue(self.n_kc)
        self.tally = DecisionTally()  # YES/NO/ABSTAIN counts -> abstention rate
        self._abstained: set = set()  # markets we abstained on, awaiting resolution
        self.n_updates_applied = 0  # resolutions that changed learning state
        self.n_abstained_resolved = 0  # resolutions skipped because we abstained

    @property
    def weights(self) -> np.ndarray:
        """Current weights as a read-only view."""
        v = self._weights.view()
        v.flags.writeable = False
        return v

    @property
    def baseline(self) -> np.ndarray:
        return self._baseline

    def record_decision(
        self,
        market_id: str,
        kc_pattern: Optional[Sequence[float]],
        choice: Union[Choice, str],
        **meta: Any,
    ) -> bool:
        """Register a decision at decision time. ``choice`` is the readout outcome
        (``Choice`` or "YES"/"NO"/"ABSTAIN") and is REQUIRED so an abstention cannot
        be mistaken for an action.

        YES/NO: save the KC activity pattern of the framing acted on; returns True.
        ABSTAIN: nothing is queued and ``kc_pattern`` is ignored (may be None);
        the market is remembered so its later ``resolve`` is a recognised no-op;
        returns False. Every call is counted in ``self.tally``.
        A market id may be registered only once (until resolved/discarded/reset).
        """
        choice = Choice(choice)
        if market_id in self.queue or market_id in self._abstained:
            raise DuplicateMarketError(f"market {market_id!r} already has a pending decision")
        if choice == Choice.ABSTAIN:
            self._abstained.add(market_id)
            self.tally.record(choice)
            return False
        if kc_pattern is None:
            raise ValueError("kc_pattern is required for YES/NO decisions")
        self.queue.record(market_id, kc_pattern, choice=choice.value, **meta)
        self.tally.record(choice)  # only after the queue accepted it
        return True

    def resolve(self, market_id: str, dopamine: Mapping[str, float]) -> np.ndarray:
        """Apply the update for ``market_id`` using ITS saved pattern.

        Order: depression (dopamine gate), then ``drift_steps_per_resolution``
        drift steps. ``dopamine={}`` (nothing to teach) applies drift only.
        A market whose decision was ABSTAIN is dequeued with NO update at all
        (weights bit-identical). Unknown market -> UnknownMarketError. Validation
        happens before mutation, so a failed call leaves the market pending.
        """
        if market_id in self._abstained:
            self._abstained.discard(market_id)
            self.n_abstained_resolved += 1
            return self.weights
        pending = self.queue.peek(market_id)  # raises UnknownMarketError; no mutation yet
        new = depress(
            self._weights, self._baseline, pending.kc_pattern, dopamine,
            self.compartments, self.params,
        )
        new = drift(new, self._baseline, self.params, self.params.drift_steps_per_resolution)
        self._weights = new
        self.queue.pop(market_id)
        self.n_updates_applied += 1
        return self.weights

    def discard(self, market_id: str) -> None:
        """Forget a pending or abstained market without teaching (e.g. voided)."""
        self._abstained.discard(market_id)
        self.queue.discard(market_id)

    def advance(self, n_steps: int = 1) -> np.ndarray:
        """Extra drift with no dopamine (time passing without resolutions)."""
        self._weights = drift(self._weights, self._baseline, self.params, n_steps)
        return self.weights

    def reset(self) -> None:
        """Restore connectome weights; clear the queue, abstained set and counters."""
        self._weights = self._baseline.copy()
        self.queue = DecisionQueue(self.n_kc)
        self.tally = DecisionTally()
        self._abstained = set()
        self.n_updates_applied = 0
        self.n_abstained_resolved = 0
