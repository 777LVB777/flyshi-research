"""MBON rates -> decision (Option B).

Pure numpy; no Brian2, no simulation.

Score
-----
``score = sum over MBON instances of (sign weight) x (firing rate, Hz)`` with
weight +1 for approach-like MBONs, -1 for avoidance-like MBONs, 0 otherwise. It
is a plain SUM over instances (not a per-type mean), so a type with several
responding instances (e.g. MBON10 x6) counts several times. A higher score
means more approach-like activity.

Sign tables come from data files (``data/``), never from code:
  * ``circuit_<X>``: derived from direct PAM/PPL1->MBON synapse totals with the
    dominant-family rule: PAM supplies >= X% -> avoidance-like (-1); PPL1
    supplies >= X% -> approach-like (+1); otherwise (mixed, or no annotated
    dopamine input) 0. ``circuit_80`` is the preregistered primary;
    ``circuit_70`` / ``circuit_90`` are preregistered sensitivity checks.
  * ``strict`` / ``group``: explicit label lists (preregistered robustness checks).

Option B decision
-----------------
Two runs per market ("YES at p", "NO at 1-p"); each is scored; pick the framing
with the higher score, but ABSTAIN unless the margin exceeds ``margin_threshold``
(which must be set from training data only). Abstaining is a valid zero-stake
action.

All sign assignments are UNVERIFIED at compartment level (see the design docs);
CIRCUIT signs are a circuit-logic modelling assumption, not behavioural results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

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


_CIRCUIT_NAME = re.compile(r"^circuit_(\d+(?:\.\d+)?)$")


def load_sign_table(name: str, data_dir: Optional[Union[str, Path]] = None) -> SignTable:
    """Load a preregistered sign table by name.

    ``"circuit_80"`` (primary), ``"circuit_70"``, ``"circuit_90"`` (any
    ``circuit_<pct>``), ``"strict"``, ``"group"``.
    """
    base = Path(data_dir) if data_dir else DATA_DIR
    m = _CIRCUIT_NAME.match(name)
    if m:
        counts = load_dopamine_counts(base / DOPAMINE_INPUT_FILE)
        return circuit_sign_table(counts, float(m.group(1)), name=name)
    try:
        return SignTable.from_json(base / SIGN_TABLES_FILE, table=name)
    except KeyError:
        raise ValueError(
            f"unknown sign table {name!r}; expected 'circuit_<pct>', 'strict' or 'group'"
        ) from None


@dataclass(frozen=True)
class ScoreResult:
    score: float
    n_approach: int  # instances with weight +1
    n_avoidance: int  # instances with weight -1
    n_zero: int  # instances listed in the table with weight 0
    n_unlisted: int  # instances whose label is not in the table (weight 0)
    unlisted_labels: Tuple[str, ...]

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


def circuit_score(rates: Sequence[float], labels: Sequence[str], table: SignTable) -> ScoreResult:
    """Sign-weighted sum of MBON rates. ``labels[i]`` is the cell-type label of
    the MBON instance whose rate is ``rates[i]``."""
    labels = list(labels)
    r = _as_rates(rates, len(labels))
    w = np.array([table.weight(l) for l in labels], dtype=np.float64)
    unlisted = sorted({l for l in labels if not table.is_listed(l)})
    n_unlisted = sum(1 for l in labels if not table.is_listed(l))
    return ScoreResult(
        score=float(np.dot(w, r)),
        n_approach=int(np.sum(w > 0)),
        n_avoidance=int(np.sum(w < 0)),
        n_zero=int(sum(1 for l in labels if table.is_listed(l) and table.weight(l) == 0)),
        n_unlisted=n_unlisted,
        unlisted_labels=tuple(unlisted),
    )


@dataclass(frozen=True)
class ReadoutDecision:
    choice: Choice
    score_yes: float
    score_no: float
    margin: float  # |score_yes - score_no|
    margin_threshold: float
    table_name: str
    n_weighted: int  # MBON instances carrying nonzero weight in the table


def decide(
    rates_yes: Sequence[float],
    rates_no: Sequence[float],
    labels: Sequence[str],
    table: SignTable,
    margin_threshold: float = 0.0,
) -> ReadoutDecision:
    """Option B: score both framings, take the higher, ABSTAIN unless the margin
    exceeds ``margin_threshold``.

    Raises ValueError if NO label in ``labels`` carries nonzero weight in
    ``table`` - that is a labelling/config mismatch (e.g. wrong label format),
    and silently abstaining forever would hide it.
    """
    if not margin_threshold >= 0.0:
        raise ValueError("margin_threshold must be >= 0")
    yes = circuit_score(rates_yes, labels, table)
    no = circuit_score(rates_no, labels, table)
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
    )
