"""MBON rates -> decision (Option B).

Pure numpy; no Brian2, no simulation.

Score
-----
Weight +1 = approach-like MBON type, -1 = avoidance-like, 0 = neither. A higher
score means more approach-like activity. Two aggregations (``params.AGGREGATIONS``):

``type_mean`` (DEFAULT, decided): average the rates of the instances of each cell
type FIRST, then ``score = sum over types of (sign weight) x (type mean rate)``.
Each type gets exactly one vote, whatever its instance count. Reason: the raw
sum would let a type with many instances dominate for an anatomical reason -
MBON10 has 9 instances in the v783 model (6 responded in the KC-direct data) and
is an atypical MBON whose dendrites lie largely outside the lobes.

``instance_sum`` (named variant, NOT the default): ``score = sum over instances of
(sign weight) x (rate)``. A type with several instances counts several times.

The type mean is only as good as the instance list it is given: pass EVERY
instance of each type (silent ones at 0 Hz), not just the ones that fired.
Averaging responders only inflates each type's mean by a different, arbitrary
factor. This module does not select instances; the caller does. DECIDED
2026-09-22 (docs/design/open-decisions.md, 2): the primary readout passes all 96
MBON instances from both hemispheres; left-hemisphere-only exists only as a
preregistered POST-HOC RESCORING (flyshi_research.learning.mbon_sides), never as
an arm or condition. It rescores runs as they actually happened under a left-only
readout: exact in the first learning test, whose teaching signal comes from the
condition and not the readout, but not in the closed-loop synthetic market
(score -> action -> teaching), where it cannot show what a left-only system would
have done.

Sign tables come from data files (``data/``), never from code:
  * ``circuit_<X>``: derived from direct PAM/PPL1->MBON synapse totals with the
    dominant-family rule: PAM supplies >= X% -> avoidance-like (-1); PPL1
    supplies >= X% -> approach-like (+1); otherwise (mixed, or no annotated
    dopamine input) 0. ``circuit_80`` is the preregistered primary;
    ``circuit_70`` / ``circuit_90`` are preregistered sensitivity checks.
    ``circuit_80_no_gamma3`` (MBON08 and MBON09 zeroed; listed in the data
    file) is a further preregistered sensitivity check.
  * ``strict`` / ``group``: explicit label lists (preregistered robustness checks).

Option B decision
-----------------
Two runs per market ("YES at p", "NO at 1-p"); each is scored; pick the framing
with the higher score, but ABSTAIN unless the margin exceeds ``margin_threshold``
(which must be set from training data only; its units depend on the aggregation).
Abstaining is a valid zero-stake action, and it triggers NO learning update
(see plasticity.py). ``DecisionTally`` tracks the abstention rate.

All sign assignments are UNVERIFIED at compartment level (see the design docs);
CIRCUIT signs are a circuit-logic modelling assumption, not behavioural results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from .params import AGG_TYPE_MEAN, AGGREGATIONS

DEFAULT_AGGREGATION = AGG_TYPE_MEAN

DATA_DIR = Path(__file__).resolve().parent / "data"
DOPAMINE_INPUT_FILE = "mbon_dopamine_input.json"
SIGN_TABLES_FILE = "mbon_sign_tables.json"

_TIE_TOL = 1e-9  # float noise is not a margin; margins this small are ties


class Choice(str, Enum):
    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class SignTable:
    """label -> {-1, 0, +1}. Labels not listed have weight 0 (see ``is_listed``)."""

    name: str
    weights: Mapping[str, int]
    description: str = ""

    def __post_init__(self) -> None:
        bad = {k: v for k, v in self.weights.items() if v not in (-1, 0, 1)}
        if bad:
            raise ValueError(f"sign weights must be -1, 0 or +1; got {bad}")

    def weight(self, label: str) -> int:
        return int(self.weights.get(label, 0))

    def is_listed(self, label: str) -> bool:
        return label in self.weights

    @classmethod
    def from_json(cls, path: Union[str, Path], table: Optional[str] = None) -> "SignTable":
        """Load a custom table. Accepts either ``{"weights": {...}}`` or, with
        ``table="strict"``-style selection, the multi-table layout of
        ``data/mbon_sign_tables.json``."""
        path = Path(path)
        with open(path) as fh:
            raw = json.load(fh)
        if table is not None:
            raw = raw["tables"][table]
        return cls(
            name=table or path.stem,
            weights={str(k): int(v) for k, v in raw["weights"].items()},
            description=raw.get("description", ""),
        )


def load_dopamine_counts(path: Optional[Union[str, Path]] = None) -> Dict[str, Tuple[int, int]]:
    """label -> (PAM synapses, PPL1 synapses) from the data file."""
    with open(Path(path) if path else DATA_DIR / DOPAMINE_INPUT_FILE) as fh:
        raw = json.load(fh)["counts"]
    return {label: (int(c["pam"]), int(c["ppl1"])) for label, c in raw.items()}


def dominant_family(pam: int, ppl1: int, threshold_pct: float) -> Optional[str]:
    """``"PAM"``, ``"PPL1"`` or ``None`` under the dominant-family rule.

    Family F is dominant when it supplies at least ``threshold_pct`` percent of
    (pam + ppl1). No annotated dopamine input (total 0) -> None. Integer
    cross-multiplication avoids float rounding at exact boundaries.
    """
    if not 50.0 < threshold_pct <= 100.0:
        raise ValueError("threshold_pct must be in (50, 100]")
    total = pam + ppl1
    if total == 0:
        return None
    if pam * 100 >= threshold_pct * total:
        return "PAM"
    if ppl1 * 100 >= threshold_pct * total:
        return "PPL1"
    return None


def circuit_sign_table(
    counts: Mapping[str, Tuple[int, int]], threshold_pct: float, name: Optional[str] = None
) -> SignTable:
    """CIRCUIT table: PAM-dominant -> -1 (avoidance-like), PPL1-dominant -> +1."""
    sign = {"PAM": -1, "PPL1": 1, None: 0}
    weights = {
        label: sign[dominant_family(pam, ppl1, threshold_pct)]
        for label, (pam, ppl1) in counts.items()
    }
    return SignTable(
        name=name or f"circuit_{threshold_pct:g}",
        weights=weights,
        description=(
            f"CIRCUIT: dominant-family rule at {threshold_pct:g}% over direct PAM/PPL1 "
            "synapse totals (circuit-logic assumption; compartment map UNVERIFIED)"
        ),
    )


_CIRCUIT_NAME = re.compile(r"^circuit_(\d+(?:\.\d+)?)(?:_([a-z][a-z0-9_]*))?$")


def load_sign_table(name: str, data_dir: Optional[Union[str, Path]] = None) -> SignTable:
    """Load a preregistered sign table by name.

    ``"circuit_80"`` (primary), ``"circuit_70"``, ``"circuit_90"`` (any
    ``circuit_<pct>``), ``"strict"``, ``"group"``, and CIRCUIT variants
    ``"circuit_<pct>_<variant>"`` whose zeroed labels are listed under
    ``circuit_variants`` in the sign-tables data file (e.g.
    ``"circuit_80_no_gamma3"``: MBON08 and MBON09 set to zero weight).
    """
    base = Path(data_dir) if data_dir else DATA_DIR
    m = _CIRCUIT_NAME.match(name)
    if m:
        counts = load_dopamine_counts(base / DOPAMINE_INPUT_FILE)
        table = circuit_sign_table(counts, float(m.group(1)), name=name)
        if m.group(2) is None:
            return table
        with open(base / SIGN_TABLES_FILE) as fh:
            variant = json.load(fh).get("circuit_variants", {}).get(m.group(2))
        if variant is None:
            raise ValueError(f"unknown sign table {name!r}: no CIRCUIT variant {m.group(2)!r}")
        zero = {str(k) for k in variant["zero"]}
        return SignTable(
            name=name,
            weights={k: (0 if k in zero else v) for k, v in table.weights.items()},
            description=f"{table.description}; variant {m.group(2)}: {variant.get('description', '')}",
        )
    try:
        return SignTable.from_json(base / SIGN_TABLES_FILE, table=name)
    except KeyError:
        raise ValueError(
            f"unknown sign table {name!r}; expected 'circuit_<pct>', "
            "'circuit_<pct>_<variant>', 'strict' or 'group'"
        ) from None


@dataclass(frozen=True)
class ScoreResult:
    """Score plus bookkeeping. The ``n_*`` counts are in VOTING UNITS: cell types
    under ``type_mean``, individual instances under ``instance_sum``."""

    score: float
    aggregation: str
    n_approach: int  # units with weight +1
    n_avoidance: int  # units with weight -1
    n_zero: int  # units listed in the table with weight 0
    n_unlisted: int  # units whose label is not in the table (weight 0)
    unlisted_labels: Tuple[str, ...]
    n_instances: int  # MBON instances that were supplied
    type_rates: Mapping[str, float]  # per-type mean rate (type_mean only; {} otherwise)

    @property
    def n_weighted(self) -> int:
        return self.n_approach + self.n_avoidance


def _as_rates(rates: Sequence[float], n: int) -> np.ndarray:
    r = np.asarray(rates, dtype=np.float64)
    if r.ndim != 1 or r.size != n:
        raise ValueError(f"rates must be 1-D with one entry per label ({n}), got shape {r.shape}")
    if not np.all(np.isfinite(r)):
        raise ValueError("rates contain non-finite values")
    if np.any(r < 0):
        raise ValueError("rates must be >= 0")
    return r


def circuit_score(
    rates: Sequence[float],
    labels: Sequence[str],
    table: SignTable,
    aggregation: str = DEFAULT_AGGREGATION,
) -> ScoreResult:
    """Sign-weighted CIRCUIT score. ``labels[i]`` is the cell-type label of the MBON
    instance whose rate is ``rates[i]``. Default aggregation is the per-type mean
    (see module docstring); pass ``aggregation="instance_sum"`` for the variant."""
    if aggregation not in AGGREGATIONS:
        raise ValueError(f"aggregation must be one of {AGGREGATIONS}, got {aggregation!r}")
    labels = list(labels)
    r = _as_rates(rates, len(labels))

    if aggregation == AGG_TYPE_MEAN:
        by_type: Dict[str, List[float]] = {}
        for label, rate in zip(labels, r.tolist()):
            by_type.setdefault(label, []).append(rate)
        type_rates = {t: float(np.mean(v)) for t, v in by_type.items()}
        units = sorted(type_rates)  # fixed summation order: independent of input order
        unit_rates = [type_rates[t] for t in units]
    else:
        type_rates = {}
        units = labels
        unit_rates = r.tolist()

    w = np.array([table.weight(u) for u in units], dtype=np.float64)
    unlisted = [u for u in units if not table.is_listed(u)]
    return ScoreResult(
        score=float(np.dot(w, np.array(unit_rates, dtype=np.float64))) if units else 0.0,
        aggregation=aggregation,
        n_approach=int(np.sum(w > 0)),
        n_avoidance=int(np.sum(w < 0)),
        n_zero=int(sum(1 for u in units if table.is_listed(u) and table.weight(u) == 0)),
        n_unlisted=len(unlisted),
        unlisted_labels=tuple(sorted(set(unlisted))),
        n_instances=len(labels),
        type_rates=type_rates,
    )


@dataclass(frozen=True)
class ReadoutDecision:
    choice: Choice
    score_yes: float
    score_no: float
    margin: float  # |score_yes - score_no|
    margin_threshold: float
    table_name: str
    n_weighted: int  # voting units (types, or instances) carrying nonzero weight
    aggregation: str = DEFAULT_AGGREGATION


def decide(
    rates_yes: Sequence[float],
    rates_no: Sequence[float],
    labels: Sequence[str],
    table: SignTable,
    margin_threshold: float = 0.0,
    aggregation: str = DEFAULT_AGGREGATION,
) -> ReadoutDecision:
    """Option B: score both framings, take the higher, ABSTAIN unless the margin
    exceeds ``margin_threshold``.

    Raises ValueError if NO voting unit in ``labels`` carries nonzero weight in
    ``table`` - that is a labelling/config mismatch (e.g. wrong label format),
    and silently abstaining forever would hide it.
    """
    if not margin_threshold >= 0.0:
        raise ValueError("margin_threshold must be >= 0")
    yes = circuit_score(rates_yes, labels, table, aggregation)
    no = circuit_score(rates_no, labels, table, aggregation)
    if yes.n_weighted == 0:
        raise ValueError(
            f"no MBON label has nonzero weight in sign table {table.name!r} "
            f"(unlisted labels: {list(yes.unlisted_labels)[:5]}...). Check label format."
        )
    diff = yes.score - no.score
    margin = abs(diff)
    if margin <= margin_threshold + _TIE_TOL:
        choice = Choice.ABSTAIN
    else:
        choice = Choice.YES if diff > 0 else Choice.NO
    return ReadoutDecision(
        choice=choice,
        score_yes=yes.score,
        score_no=no.score,
        margin=margin,
        margin_threshold=float(margin_threshold),
        table_name=table.name,
        n_weighted=yes.n_weighted,
        aggregation=aggregation,
    )


class DecisionTally:
    """Running count of readout choices; tracks the ABSTENTION RATE.

    ``record`` accepts a ``Choice``, its string value, or a ``ReadoutDecision``.
    Abstention rate = abstained / all decisions recorded (NaN before any).
    Report it next to the forecast metrics: a system that abstains on most
    markets can look accurate on the few it acts on.
    """

    def __init__(self) -> None:
        self.n_yes = 0
        self.n_no = 0
        self.n_abstain = 0

    def record(self, decision: Union[Choice, str, "ReadoutDecision"]) -> Choice:
        choice = decision.choice if isinstance(decision, ReadoutDecision) else Choice(decision)
        if choice == Choice.YES:
            self.n_yes += 1
        elif choice == Choice.NO:
            self.n_no += 1
        else:
            self.n_abstain += 1
        return choice

    @property
    def n_decisions(self) -> int:
        return self.n_yes + self.n_no + self.n_abstain

    @property
    def n_acted(self) -> int:
        return self.n_yes + self.n_no

    @property
    def abstention_rate(self) -> float:
        return self.n_abstain / self.n_decisions if self.n_decisions else float("nan")

    def summary(self) -> Dict[str, float]:
        return {
            "n_decisions": self.n_decisions,
            "n_yes": self.n_yes,
            "n_no": self.n_no,
            "n_abstain": self.n_abstain,
            "abstention_rate": self.abstention_rate,
        }
