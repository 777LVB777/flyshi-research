"""Pure-NumPy mixed-valence mushroom-body model from Bennett et al. (2021).

Paper: https://doi.org/10.1038/s41467-021-22592-4
Reference implementation:
https://github.com/BrainsOnBoard/paper_RPEs_in_drosophila_mb

The core implements the paper's linear/rectified units (Eqs. 9, 10 and 14),
binary softmax choice (Eq. 11), and mixed-valence plasticity (Eq. 22, the
authors' Eq. 8 rule).  ``BennettMarketAgent`` adapts the model to Flyshi's
existing market feature encoder; the biological model itself knows nothing
about markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from flyshi_research.evaluation.calibration import fit_and_apply_calibration
from flyshi_research.learning.encoder import KCEncoder, Stimulus
from flyshi_research.simulator import Action, Decision, Market, MarketObservation, observe_market


# Exact settings used by the authors' Fig. 3d-g analysis (mb_vs_mv_analysis.m,
# flag 6) and model code (mb_mv_a.m).  They are not claimed as universal fly
# parameters.
PAPER_TOTAL_KC_RATE = 10.0
PAPER_INITIAL_WEIGHT_MAX = 0.1
PAPER_GAMMA = 1.0
PAPER_BETA = 5.0  # source uses temperature T=0.2 and beta=1/T
PAPER_BASE_LEARNING_RATE = 2.5e-2
PAPER_MV_LEARNING_RATE = 0.5 * PAPER_BASE_LEARNING_RATE


@dataclass(frozen=True)
class BennettMVParams:
    """Source-verified parameters for the Fig. 3 mixed-valence model."""

    gamma: float = PAPER_GAMMA
    beta: float = PAPER_BETA
    learning_rate: float = PAPER_MV_LEARNING_RATE
    initial_weight_max: float = PAPER_INITIAL_WEIGHT_MAX
    total_kc_rate: float = PAPER_TOTAL_KC_RATE

    def __post_init__(self) -> None:
        values = np.asarray(
            [self.gamma, self.beta, self.learning_rate, self.initial_weight_max,
             self.total_kc_rate],
            dtype=float,
        )
        if not np.all(np.isfinite(values)):
            raise ValueError("all mixed-valence parameters must be finite")
        if self.gamma < 0.0 or self.beta < 0.0 or self.initial_weight_max < 0.0:
            raise ValueError("gamma, beta and initial_weight_max must be non-negative")
        if self.learning_rate <= 0.0 or self.total_kc_rate <= 0.0:
            raise ValueError("learning_rate and total_kc_rate must be positive")


@dataclass(frozen=True, eq=False)
class MBResponse:
    """Approach/avoidance MBON rates and their reinforcement prediction."""

    approach_rate: float
    avoidance_rate: float
    reinforcement_prediction: float


@dataclass(frozen=True, eq=False)
class LearningStep:
    """Auditable values from one Eq. 14/Eq. 22 update."""

    reinforcement: float
    approach_dan_rate: float
    avoidance_dan_rate: float
    dan_difference: float
    weight_delta: np.ndarray


def _cue_vector(values: object, n_kcs: int, total_kc_rate: float) -> np.ndarray:
    cue = np.asarray(values, dtype=np.float64)
    if cue.ndim != 1 or cue.size != n_kcs:
        raise ValueError(f"cue must be one-dimensional with {n_kcs} entries")
    if not np.all(np.isfinite(cue)) or np.any(cue < 0.0):
        raise ValueError("cue firing rates must be finite and non-negative")
    if not np.isclose(float(np.sum(cue)), total_kc_rate, rtol=0.0, atol=1e-10):
        raise ValueError(f"cue firing rates must sum to {total_kc_rate:g} Hz")
    return cue.copy()


class BennettMixedValenceMB:
    """Two-MBON/two-DAN mixed-valence model with sequential reward input.

    ``decide`` takes YES and NO cue vectors and returns Flyshi's ordinary
    :class:`Decision`.  When learning is enabled, exactly one subsequent call
    to ``reward`` updates the chosen cue's KC->MBON weights.  ``freeze`` disables
    queuing and plasticity for a held-out test split.
    """

    def __init__(
        self,
        n_kcs: int,
        *,
        seed: int,
        params: BennettMVParams | None = None,
    ) -> None:
        if not isinstance(n_kcs, int) or isinstance(n_kcs, bool) or n_kcs < 1:
            raise ValueError("n_kcs must be a positive integer")
        self.n_kcs = n_kcs
        self.params = params or BennettMVParams()
        self._rng = np.random.default_rng(seed)
        self._approach_weights = self._rng.uniform(
            0.0, self.params.initial_weight_max, self.n_kcs
        )
        self._avoidance_weights = self._rng.uniform(
            0.0, self.params.initial_weight_max, self.n_kcs
        )
        self._learning_enabled = True
        self._pending: tuple[np.ndarray, MBResponse] | None = None

    @property
    def learning_enabled(self) -> bool:
        return self._learning_enabled

    @property
    def approach_weights(self) -> np.ndarray:
        return self._approach_weights.copy()

    @property
    def avoidance_weights(self) -> np.ndarray:
        return self._avoidance_weights.copy()

    def set_weights(self, approach: object, avoidance: object) -> None:
        """Set non-negative KC->MBON weights, primarily for state restoration."""
        plus = np.asarray(approach, dtype=np.float64)
        minus = np.asarray(avoidance, dtype=np.float64)
        if plus.shape != (self.n_kcs,) or minus.shape != (self.n_kcs,):
            raise ValueError("weight vectors must match n_kcs")
        if not np.all(np.isfinite(plus)) or not np.all(np.isfinite(minus)):
            raise ValueError("weights must be finite")
        if np.any(plus < 0.0) or np.any(minus < 0.0):
            raise ValueError("weights must be non-negative")
        if self._pending is not None:
            raise RuntimeError("cannot replace weights while a decision awaits reward")
        self._approach_weights = plus.copy()
        self._avoidance_weights = minus.copy()

    def freeze(self) -> None:
        """Disable plasticity for held-out decisions; no pending reward may exist."""
        if self._pending is not None:
            raise RuntimeError("resolve the pending decision before freezing")
        self._learning_enabled = False

    def response(self, cue: object) -> MBResponse:
        """Compute Eq. 10 MBON rates and their signed prediction."""
        k = _cue_vector(cue, self.n_kcs, self.params.total_kc_rate)
        approach = float(max(0.0, self._approach_weights @ k))
        avoidance = float(max(0.0, self._avoidance_weights @ k))
        return MBResponse(approach, avoidance, approach - avoidance)

    def decide(
        self,
        yes_cue: object,
        no_cue: object,
        *,
        forced_action: Action | None = None,
    ) -> Decision:
        """Choose between two cues with Eq. 11 and optionally queue learning.

        ``forced_action`` exists to reproduce experiments in which the authors'
        code fixes cue 1 (``choose1=true``); ordinary market use leaves it unset.
        """
        if self._pending is not None:
            raise RuntimeError("the previous decision still awaits reward")
        yes = _cue_vector(yes_cue, self.n_kcs, self.params.total_kc_rate)
        no = _cue_vector(no_cue, self.n_kcs, self.params.total_kc_rate)
        yes_response = self.response(yes)
        no_response = self.response(no)
        predictions = np.asarray(
            [yes_response.reinforcement_prediction, no_response.reinforcement_prediction]
        )
        logits = self.params.beta * predictions
        exponentials = np.exp(logits - np.max(logits))
        probabilities = exponentials / np.sum(exponentials)
        yes_probability = float(probabilities[0])
        if forced_action is not None and forced_action not in (Action.YES, Action.NO):
            raise ValueError("forced_action must be YES or NO")
        if forced_action is None:
            action = Action.YES if self._rng.random() < yes_probability else Action.NO
        else:
            action = forced_action
        if self._learning_enabled:
            self._pending = (yes, yes_response) if action is Action.YES else (no, no_response)
        return Decision(yes_probability, action)

    def reward(self, reinforcement: float) -> LearningStep:
        """Apply signed reinforcement through paper Eqs. 14 and 22."""
        if not self._learning_enabled:
            raise RuntimeError("model is frozen; held-out decisions cannot learn")
        if self._pending is None:
            raise RuntimeError("reward requires a preceding decision")
        r = float(reinforcement)
        if not np.isfinite(r):
            raise ValueError("reinforcement must be finite")
        cue, response = self._pending
        baseline = self.params.gamma * float(np.sum(cue))
        # Eq. 14 with signed r = r_plus - r_minus and feedback weight w_M=1.
        approach_dan = float(
            max(0.0, baseline + r - response.reinforcement_prediction)
        )
        avoidance_dan = float(
            max(0.0, baseline - r + response.reinforcement_prediction)
        )
        difference = approach_dan - avoidance_dan
        delta = self.params.learning_rate * cue * difference
        # Eq. 22 / authors' Eq. 8 implementation, with excitatory weight floor.
        self._approach_weights = np.maximum(0.0, self._approach_weights + delta)
        self._avoidance_weights = np.maximum(0.0, self._avoidance_weights - delta)
        self._pending = None
        return LearningStep(r, approach_dan, avoidance_dan, difference, delta.copy())


def normalized_stimulus_vector(
    stimulus: Stimulus,
    kc_ids: Sequence[int],
    *,
    total_kc_rate: float = PAPER_TOTAL_KC_RATE,
) -> np.ndarray:
    """Map Flyshi encoder rates onto KCs and normalise to the paper's 10 Hz.

    This normalization is a Flyshi adaptation, not an equation from the paper.
    It preserves relative feature rates while satisfying the paper's fixed
    summed KC activity and equalising total drive between YES/NO framings.
    """
    ids = np.asarray(kc_ids)
    if ids.ndim != 1 or ids.size == 0 or not np.issubdtype(ids.dtype, np.integer):
        raise TypeError("kc_ids must be a non-empty one-dimensional integer sequence")
    if np.unique(ids).size != ids.size:
        raise ValueError("kc_ids contains duplicates")
    index = {int(kc_id): position for position, kc_id in enumerate(ids)}
    cue = np.zeros(ids.size, dtype=np.float64)
    for kc_id, rate in zip(stimulus.kc_ids, stimulus.rates_hz):
        try:
            position = index[int(kc_id)]
        except KeyError as exc:
            raise ValueError(f"stimulus contains unknown KC ID {int(kc_id)}") from exc
        cue[position] = float(rate)
    total = float(np.sum(cue))
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("stimulus must have positive finite total drive")
    return cue * (float(total_kc_rate) / total)


class BennettMarketAgent:
    """MarketObservation adapter using Flyshi's existing Option-B KC encoder."""

    def __init__(
        self,
        kc_ids: Sequence[int],
        *,
        seed: int,
        params: BennettMVParams | None = None,
        encoder: KCEncoder | None = None,
    ) -> None:
        raw_ids = np.asarray(kc_ids)
        if raw_ids.ndim != 1 or raw_ids.size == 0 or not np.issubdtype(raw_ids.dtype, np.integer):
            raise TypeError("kc_ids must be a non-empty one-dimensional integer sequence")
        if np.unique(raw_ids).size != raw_ids.size:
            raise ValueError("kc_ids contains duplicates")
        self.kc_ids = tuple(map(int, raw_ids))
        self.model = BennettMixedValenceMB(len(self.kc_ids), seed=seed, params=params)
        self.encoder = encoder or KCEncoder(self.kc_ids)
        if set(self.encoder.pools) and any(
            not set(map(int, pool)).issubset(self.kc_ids) for pool in self.encoder.pools.values()
        ):
            raise ValueError("encoder pools must be subsets of kc_ids")

    @staticmethod
    def _features(observation: MarketObservation) -> dict[str, float]:
        return {
            "price": observation.quote,
            "recent_change": observation.recent_change,
            "time_to_resolution": observation.time_to_resolution,
            "liquidity": observation.liquidity,
            "signal": observation.signal,
        }

    def decide(self, observation: MarketObservation) -> Decision:
        if not isinstance(observation, MarketObservation):
            raise TypeError("observation must be a MarketObservation")
        pair = self.encoder.option_b_stimuli(self._features(observation))
        total = self.model.params.total_kc_rate
        yes = normalized_stimulus_vector(pair.yes, self.kc_ids, total_kc_rate=total)
        no = normalized_stimulus_vector(pair.no, self.kc_ids, total_kc_rate=total)
        return self.model.decide(yes, no)

    def reward(self, reinforcement: float) -> LearningStep:
        return self.model.reward(reinforcement)

    def freeze(self) -> None:
        self.model.freeze()


def run_market_sequence(
    markets: Sequence[Market],
    agent: BennettMarketAgent,
    *,
    train_count: int,
    reinforcement: Callable[[Market, Decision], float],
) -> dict:
    """Run an identical chronological train/test split and shared calibration.

    Only training markets are supplied to ``reinforcement`` and plasticity.
    Test outcomes are merely copied into returned evaluation records after the
    decision; the agent receives only :class:`MarketObservation` objects.
    """
    rows = tuple(markets)
    if len(rows) < 4 or not 2 <= train_count <= len(rows) - 2:
        raise ValueError("need at least two training and two test markets")
    records: list[dict] = []
    for index, market in enumerate(rows):
        if index == train_count:
            agent.freeze()
        decision = agent.decide(observe_market(market))
        if index < train_count:
            value = float(reinforcement(market, decision))
            if not np.isfinite(value):
                raise ValueError("reinforcement callback returned a non-finite value")
            agent.reward(value)
        records.append(
            {
                "sequence": market.sequence,
                "outcome": market.outcome,
                "quote": market.quote,
                "raw_probability": decision.forecast_probability,
                "action": decision.action.value,
            }
        )
    train = records[:train_count]
    test = records[train_count:]
    calibrated = fit_and_apply_calibration(
        [row["raw_probability"] for row in train],
        [row["outcome"] for row in train],
        [row["raw_probability"] for row in test],
    )
    for record, probability in zip(test, calibrated.calibrated_test):
        record["calibrated_probability"] = float(probability)
    return {"train": train, "test": test, "calibrator": calibrated.scaler}
