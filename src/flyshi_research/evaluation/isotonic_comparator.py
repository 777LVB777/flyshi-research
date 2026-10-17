"""Phase 2 market comparator: the raw price, isotonically calibrated on TRAINING
markets only, with shrinkage and a raw-versus-calibrated guard.

FINAL method (docs/design/phase2-design.md, 10.2, confirmed 2026-10-12):

1. **Fit.** Isotonic regression (pool-adjacent-violators) of the outcome on the raw
   price at ``t_d``, on the probability scale, training markets only. Tied prices
   are pooled.
2. **Shrinkage.** Each isotonic block is shrunk toward the block's own mean price
   with pseudo-count ``m = 20``: ``(sum y + m * mean_price) / (n + m)``.
3. **Prediction.** Linear interpolation between block centres (each block's mean
   price); prices beyond the training range take the nearest end value.
4. **Guard, fixed before any test market is scored.** 5-fold cross-validation on
   the training markets, folds by a seeded hash of the market ID, comparing the
   Brier score of the raw price with that of the calibrated price. The comparator
   is whichever is lower (a tie keeps the raw price). Both are reported.

Re-pooling (decided 2026-10-16): shrinking each block toward its OWN mean price can
leave two adjacent shrunk values out of order when a small block follows a large one.
Pool-adjacent-violators is therefore applied again to the shrunk values, weighted by
n + pseudo_count, so the map is monotone non-decreasing. A pooled run of blocks takes
one value and keeps its blocks' centres, so interpolation stays monotone. The values
before re-pooling are kept (``shrunk_values``) and ``repooled`` says whether it acted.

Pure numpy. Nothing here sees a test market: ``fit_comparator`` receives training
markets only, and the frozen result is a plain dict with a SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

PSEUDO_COUNT = 20.0
CV_FOLDS = 5
#: folds are sha256(FOLD_SEED|market id) mod CV_FOLDS (pre-stated 2026-10-16)
FOLD_SEED = "flyshi-phase2-comparator-folds-20261016"
RAW = "raw_price"
CALIBRATED = "isotonic_calibrated_price"


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Shrunk isotonic blocks: ``centres`` (block mean prices, strictly increasing),
    ``values`` (shrunk outcome rates) and ``counts`` (markets per block)."""

    centres: Tuple[float, ...]
    values: Tuple[float, ...]
    counts: Tuple[int, ...]
    pseudo_count: float
    shrunk_values: Tuple[float, ...] = ()  # before the second pooling

    @property
    def repooled(self) -> bool:
        return tuple(self.shrunk_values) != tuple(self.values)

    def predict(self, prices: Sequence[float]) -> np.ndarray:
        """Linear between block centres; the nearest end value beyond them."""
        return np.interp(np.asarray(prices, dtype=float), self.centres, self.values)

    @property
    def monotone(self) -> bool:
        return bool(np.all(np.diff(self.values) >= 0.0))


def pav_blocks(prices: Sequence[float], outcomes: Sequence[int]) -> List[Tuple[int, float, float]]:
    """Pool-adjacent-violators on the outcome, ordered by price, tied prices pooled
    first. Returns ``(n, sum_outcome, sum_price)`` per block in price order; block
    outcome means are non-decreasing."""
    p = np.asarray(prices, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.size == 0 or p.size != y.size:
        raise ValueError("need one outcome per price, at least one market")
    if not np.all(np.isfinite(p)) or np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("prices must be finite probabilities in [0, 1]")
    if not np.all(np.isin(y, (0.0, 1.0))):
        raise ValueError("outcomes must be 0 or 1")
    order = np.argsort(p, kind="mergesort")
    p, y = p[order], y[order]
    unique, start = np.unique(p, return_index=True)
    ends = list(start[1:]) + [p.size]
    blocks: List[List[float]] = []  # [n, sum_y, sum_p]
    for a, b in zip(start, ends):
        blocks.append([float(b - a), float(y[a:b].sum()), float(p[a:b].sum())])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] > blocks[-1][1] / blocks[-1][0]:
            n, sy, sp = blocks.pop()
            blocks[-1][0] += n
            blocks[-1][1] += sy
            blocks[-1][2] += sp
    return [(int(n), sy, sp) for n, sy, sp in blocks]


def fit_isotonic(prices: Sequence[float], outcomes: Sequence[int],
                 pseudo_count: float = PSEUDO_COUNT) -> IsotonicCalibrator:
    blocks = pav_blocks(prices, outcomes)
    centres = tuple(sp / n for n, _, sp in blocks)
    shrunk = [(sy + pseudo_count * (sp / n)) / (n + pseudo_count) for n, sy, sp in blocks]
    weights = [n + pseudo_count for n, _, _ in blocks]
    pools = []  # [weighted sum, weight, blocks pooled]
    for v, w in zip(shrunk, weights):
        pools.append([v * w, w, 1])
        while len(pools) > 1 and pools[-2][0] / pools[-2][1] > pools[-1][0] / pools[-1][1]:
            a = pools.pop()
            pools[-1][0] += a[0]
            pools[-1][1] += a[1]
            pools[-1][2] += a[2]
    values = tuple(float(t / w) for t, w, k in pools for _ in range(k))
    return IsotonicCalibrator(centres, values, tuple(n for n, _, _ in blocks), float(pseudo_count),
                              tuple(shrunk))


def fold_of(market_id: str, folds: int = CV_FOLDS, seed: str = FOLD_SEED) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{market_id}".encode()).digest()[:8], "big") % folds


@dataclass(frozen=True)
class FrozenComparator:
    """The comparator chosen on training markets, frozen before any test scoring."""

    choice: str
    calibrator: IsotonicCalibrator
    cv_brier_raw: float
    cv_brier_calibrated: float
    fold_sizes: Tuple[int, ...]
    n_train: int
    training_ids_sha256: str
    pseudo_count: float = PSEUDO_COUNT
    folds: int = CV_FOLDS
    fold_seed: str = FOLD_SEED

    def predict(self, prices: Sequence[float]) -> np.ndarray:
        p = np.asarray(prices, dtype=float)
        return self.calibrator.predict(p) if self.choice == CALIBRATED else p.copy()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["calibrator"]["monotone"] = self.calibrator.monotone
        d["calibrator"]["repooled"] = self.calibrator.repooled
        return d

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, d: Mapping) -> "FrozenComparator":
        c = dict(d["calibrator"])
        c.pop("monotone", None)
        c.pop("repooled", None)
        cal = IsotonicCalibrator(tuple(c["centres"]), tuple(c["values"]), tuple(c["counts"]),
                                 float(c["pseudo_count"]), tuple(c.get("shrunk_values", ())))
        rest = {k: v for k, v in d.items() if k != "calibrator"}
        rest["fold_sizes"] = tuple(rest["fold_sizes"])
        return cls(calibrator=cal, **rest)


def ids_sha256(market_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(sorted(str(i) for i in market_ids)).encode()).hexdigest()


def fit_comparator(train_ids: Sequence[str], train_prices: Sequence[float], train_outcomes: Sequence[int],
                   pseudo_count: float = PSEUDO_COUNT, folds: int = CV_FOLDS,
                   fold_seed: str = FOLD_SEED) -> FrozenComparator:
    """Fit on TRAINING markets only and apply the guard. There is no test argument."""
    ids = [str(i) for i in train_ids]
    p = np.asarray(train_prices, dtype=float)
    y = np.asarray(train_outcomes, dtype=float)
    if not (len(ids) == p.size == y.size) or len(set(ids)) != len(ids):
        raise ValueError("one distinct market ID per training price and outcome")
    fold = np.array([fold_of(i, folds, fold_seed) for i in ids])
    sizes = tuple(int((fold == f).sum()) for f in range(folds))
    held_out = np.empty(p.size)
    for f in range(folds):
        test = fold == f
        if not test.any():
            continue
        if test.all():
            raise ValueError("cross-validation needs markets outside every fold")
        held_out[test] = fit_isotonic(p[~test], y[~test], pseudo_count).predict(p[test])
    brier_raw = float(np.mean((p - y) ** 2))
    brier_cal = float(np.mean((held_out - y) ** 2))
    choice = CALIBRATED if brier_cal < brier_raw else RAW  # a tie keeps the raw price
    return FrozenComparator(choice, fit_isotonic(p, y, pseudo_count), brier_raw, brier_cal, sizes,
                            int(p.size), ids_sha256(ids), float(pseudo_count), folds, fold_seed)


def describe(comparator: FrozenComparator) -> Dict[str, object]:
    """Counts and Brier scores only (no block values)."""
    return {"choice": comparator.choice, "cv_brier_raw": comparator.cv_brier_raw,
            "cv_brier_calibrated": comparator.cv_brier_calibrated, "n_train": comparator.n_train,
            "fold_sizes": list(comparator.fold_sizes), "blocks": len(comparator.calibrator.counts),
            "monotone": comparator.calibrator.monotone, "repooled_after_shrinkage": comparator.calibrator.repooled}
