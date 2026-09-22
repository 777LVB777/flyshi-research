"""Pure-numpy orchestration for the synthetic-market signal sweep.

The real spiking simulator is injected through the same small protocol used by
``first_learning``.  Tests use fakes; importing this module never imports Brian2
or loads connectome data.  Pre-stated design: ``docs/design/synthetic-market-experiment.md``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Protocol, Sequence, Tuple

import numpy as np

from flyshi_research.evaluation.baselines import (
    BASELINE_NAMES,
    MARKET_PRICE,
    decisions_from_forecasts,
    fit_baselines,
)
from flyshi_research.evaluation.calibration import fit_and_apply_calibration
from flyshi_research.evaluation.metrics import (
    abstention_rate,
    bootstrap_confidence_interval,
    brier_score,
    expected_calibration_error,
    log_loss,
    maximum_drawdown,
    per_market_pnl,
    reliability_diagram,
    turnover,
)
from flyshi_research.simulator import Action, Market, MarketObservation, generate_signal_markets, observe_market

from .bias_mitigation import (
    INNATE_SCORE_SUBTRACTION,
    MITIGATIONS,
    TOTAL_DRIVE_BALANCING,
    score_difference,
    select_balance_pool,
    total_drive_balance,
)
from .encoder import KCEncoder, OptionBStimuli
from .first_learning import Readout
from .params import EncoderParams, PlasticityParams, RewardParams
from .plasticity import CompartmentMap, PlasticKCMBON
from .readout import load_dopamine_counts
from .reward import brier_improvement_reward, dopamine_signal, profit_reward

PROFIT = "profit"
ACCURACY = "accuracy"
LEARNING_OFF = "learning_off"
CONDITIONS = (PROFIT, ACCURACY, LEARNING_OFF)
SIGNAL_STRENGTHS = (0.0, 0.1, 0.2, 0.4, 0.8)
MARKET_SEEDS = (20261001, 20261002, 20261003, 20261004, 20261005)


class Simulator(Protocol):
    kc_ids: Sequence[int]
    mbon_ids: Sequence[int]
    mbon_labels: Sequence[str]

    def baseline_weights(self) -> np.ndarray: ...
    def set_weights(self, weights: np.ndarray) -> None: ...
    def present(
        self, rates_by_kc_id: Mapping[int, float], seed: int, duration_ms: float, n_trials: int
    ) -> Tuple[np.ndarray, np.ndarray]: ...


@dataclass(frozen=True)
class SyntheticConfig:
    """Pre-stated sweep settings. Mitigation is deliberately mandatory."""

    mitigation: str
    signal_strengths: Tuple[float, ...] = SIGNAL_STRENGTHS
    market_seeds: Tuple[int, ...] = MARKET_SEEDS
    markets_per_seed: int = 100
    train_fraction: float = 0.70
    price_deviation: float = 0.20
    duration_ms: float = 1000.0
    trials: int = 5
    simulation_seed_base: int = 20270000
    exploration_seed: int = 20261090
    score_scale: float = 20.0
    decision_margin: float = 0.0
    balance_pool_size: int = 300
    balance_pool_seed: int = 20260403
    bootstrap_resamples: int = 2000
    bootstrap_seed: int = 20261099
    confidence_level: float = 0.95
    fee_per_trade: float = 0.01
    spread: float = 0.02
    encoder: EncoderParams = field(default_factory=EncoderParams)
    plasticity: PlasticityParams = field(default_factory=PlasticityParams)
    reward: RewardParams = field(default_factory=RewardParams)
    prestated: bool = True

    def __post_init__(self) -> None:
        if self.mitigation not in MITIGATIONS:
            raise ValueError(f"mitigation must be one of {MITIGATIONS}")
        if self.markets_per_seed < 10:
            raise ValueError("markets_per_seed must be >= 10")
        if not 0.0 < self.train_fraction < 1.0:
            raise ValueError("train_fraction must be in (0, 1)")
        if self.train_count < 2 or self.test_count < 2:
            raise ValueError("chronological split needs at least two train and two test markets")
        if len(set(self.market_seeds)) != len(self.market_seeds):
            raise ValueError("market seeds must be distinct")
        if any(s < 0.0 or s > 1.0 for s in self.signal_strengths):
            raise ValueError("signal strengths must be in [0, 1]")
        if self.duration_ms <= 0 or self.trials < 1 or self.score_scale <= 0:
            raise ValueError("duration, trials and score_scale must be positive")

    @property
    def train_count(self) -> int:
        return int(self.markets_per_seed * self.train_fraction)

    @property
    def test_count(self) -> int:
        return self.markets_per_seed - self.train_count

    def to_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:10]


@dataclass(frozen=True)
class Job:
    id: str
    kind: str  # innate | condition
    strength: float
    market_seed: int
    condition: Optional[str]
    deps: Tuple[str, ...]
    n_runs: int


def _strength_key(value: float) -> str:
    return format(value, ".6g").replace(".", "p")


def innate_job_id(strength: float, seed: int) -> str:
    return f"innate:{_strength_key(strength)}:{seed}"


def condition_job_id(condition: str, strength: float, seed: int) -> str:
    return f"condition:{condition}:{_strength_key(strength)}:{seed}"


def plan_jobs(cfg: SyntheticConfig) -> list[Job]:
    jobs: list[Job] = []
    if cfg.mitigation == INNATE_SCORE_SUBTRACTION:
        jobs += [
            Job(innate_job_id(s, seed), "innate", s, seed, None, (), 2 * cfg.markets_per_seed)
            for s in cfg.signal_strengths
            for seed in cfg.market_seeds
        ]
    for strength in cfg.signal_strengths:
        for seed in cfg.market_seeds:
            dependency = (
                (innate_job_id(strength, seed),)
                if cfg.mitigation == INNATE_SCORE_SUBTRACTION
                else ()
            )
            jobs += [
                Job(
                    condition_job_id(condition, strength, seed),
                    "condition",
                    strength,
                    seed,
                    condition,
                    dependency,
                    2 * cfg.markets_per_seed,
                )
                for condition in CONDITIONS
            ]
    return jobs


def estimated_run_count(cfg: SyntheticConfig) -> int:
    return sum(job.n_runs for job in plan_jobs(cfg))


def critical_path_runs(cfg: SyntheticConfig) -> int:
    return 4 * cfg.markets_per_seed if cfg.mitigation == INNATE_SCORE_SUBTRACTION else 2 * cfg.markets_per_seed


def market_features(market: Market) -> Dict[str, float]:
    return {
        "price": market.quote,
        "recent_change": market.recent_change,
        "time_to_resolution": market.time_to_resolution,
        "liquidity": market.liquidity,
        "signal": market.signal,
    }


def feature_matrix(markets: Sequence[Market]) -> np.ndarray:
    names = ("price", "recent_change", "time_to_resolution", "liquidity", "signal")
    return np.asarray([[market_features(m)[name] for name in names] for m in markets], dtype=float)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return float(1.0 / (1.0 + np.exp(-value)))
    exponent = np.exp(value)
    return float(exponent / (1.0 + exponent))


def simulation_seed(cfg: SyntheticConfig, strength: float, market_seed: int, index: int) -> int:
    return (
        cfg.simulation_seed_base
        + cfg.signal_strengths.index(strength) * 100_000
        + cfg.market_seeds.index(market_seed) * 1_000
        + index
    )


def _stimuli(
    encoder: KCEncoder,
    market: Market,
    cfg: SyntheticConfig,
    balance_pool: Optional[np.ndarray],
) -> OptionBStimuli:
    pair = encoder.option_b_stimuli(market_features(market))
    if cfg.mitigation == TOTAL_DRIVE_BALANCING:
        if balance_pool is None:
            raise AssertionError("total-drive balancing needs its filler pool")
        pair = total_drive_balance(
            pair,
            balance_pool,
            min_rate_hz=cfg.encoder.min_rate_hz,
            max_rate_hz=cfg.encoder.max_rate_hz,
        )
    return pair


def _score_pair(
    sim: Simulator,
    readout: Readout,
    pair: OptionBStimuli,
    seed: int,
    cfg: SyntheticConfig,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    kc_yes, mbon_yes = sim.present(pair.yes.rates_by_kc_id(), seed, cfg.duration_ms, cfg.trials)
    kc_no, mbon_no = sim.present(pair.no.rates_by_kc_id(), seed, cfg.duration_ms, cfg.trials)
    return kc_yes, kc_no, readout.score(mbon_yes), readout.score(mbon_no)


def _exploration_action(cfg: SyntheticConfig, market_seed: int, index: int) -> Action:
    rng = np.random.default_rng([cfg.exploration_seed, market_seed, index])
    return Action.YES if rng.random() < 0.5 else Action.NO


def _action(difference: float, cfg: SyntheticConfig, *, train: bool, market_seed: int, index: int) -> Action:
    if difference > cfg.decision_margin:
        return Action.YES
    if difference < -cfg.decision_margin:
        return Action.NO
    # Training-only exploration turns an otherwise unlearnable initial tie into
    # a real acted-on decision. It is seeded and therefore reproducible.
    return _exploration_action(cfg, market_seed, index) if train else Action.ABSTAIN


def _teaching(
    condition: str, market: Market, action: Action, forecast: float, cfg: SyntheticConfig
) -> Dict[str, float]:
    if condition == LEARNING_OFF or action is Action.ABSTAIN:
        return {}
    if condition == PROFIT:
        gross = market.outcome - market.quote if action is Action.YES else market.quote - market.outcome
        profit = gross - cfg.fee_per_trade - 0.5 * cfg.spread
        value = profit_reward(profit, cfg.reward)
    elif condition == ACCURACY:
        value = brier_improvement_reward(forecast, market.outcome, market.quote, cfg.reward)
    else:
        raise ValueError(f"unknown condition {condition!r}")
    return dopamine_signal(value, cfg.reward).strengths()


def setup_encoder(sim: Simulator, cfg: SyntheticConfig) -> Tuple[KCEncoder, Optional[np.ndarray]]:
    encoder = KCEncoder(sim.kc_ids, params=cfg.encoder)
    balance_pool = None
    if cfg.mitigation == TOTAL_DRIVE_BALANCING:
        occupied = np.concatenate(list(encoder.pools.values()))
        balance_pool = select_balance_pool(
            sim.kc_ids, occupied, pool_size=cfg.balance_pool_size, seed=cfg.balance_pool_seed
        )
    return encoder, balance_pool


def compute_innate_scores(
    sim: Simulator, cfg: SyntheticConfig, strength: float, market_seed: int
) -> list[Tuple[float, float]]:
    """Exact per-stimulus scores at baseline weights (two runs per market)."""
    markets = generate_signal_markets(
        cfg.markets_per_seed, market_seed, strength, cfg.price_deviation
    )
    encoder, balance_pool = setup_encoder(sim, cfg)
    readout = Readout(sim.mbon_labels, _first_learning_config())
    sim.set_weights(sim.baseline_weights())
    out = []
    for index, market in enumerate(markets):
        pair = _stimuli(encoder, market, cfg, balance_pool)
        _, _, yes, no = _score_pair(
            sim, readout, pair, simulation_seed(cfg, strength, market_seed, index), cfg
        )
        out.append((yes, no))
    return out


def _first_learning_config():
    # Avoid importing a real backend; Readout only needs these two fields.
    from .first_learning import ExperimentConfig

    return ExperimentConfig()


def run_dataset(
    sim: Simulator,
    cfg: SyntheticConfig,
    strength: float,
    market_seed: int,
    condition: str,
    *,
    innate_scores: Optional[Sequence[Tuple[float, float]]] = None,
) -> dict:
    """Run one strength/seed/condition chain on an injected simulator."""
    if strength not in cfg.signal_strengths or market_seed not in cfg.market_seeds:
        raise ValueError("strength and market_seed must belong to the configured sweep")
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {CONDITIONS}")
    if cfg.mitigation == INNATE_SCORE_SUBTRACTION:
        if innate_scores is None or len(innate_scores) != cfg.markets_per_seed:
            raise ValueError("innate-score subtraction needs one exact score pair per market")

    markets = generate_signal_markets(
        cfg.markets_per_seed, market_seed, strength, cfg.price_deviation
    )
    encoder, balance_pool = setup_encoder(sim, cfg)
    readout = Readout(sim.mbon_labels, _first_learning_config())
    baseline = np.asarray(sim.baseline_weights(), dtype=float)
    cmap = CompartmentMap.from_dopamine_counts(
        list(sim.mbon_labels), load_dopamine_counts(), 80.0
    )
    plastic = PlasticKCMBON(baseline, cmap, cfg.plasticity)
    records = []

    for index, market in enumerate(markets):
        train = index < cfg.train_count
        sim.set_weights(plastic.weights if condition != LEARNING_OFF else baseline)
        pair = _stimuli(encoder, market, cfg, balance_pool)
        kc_yes, kc_no, yes_score, no_score = _score_pair(
            sim, readout, pair, simulation_seed(cfg, strength, market_seed, index), cfg
        )
        innate_yes, innate_no = (innate_scores[index] if innate_scores is not None else (None, None))
        difference = score_difference(
            yes_score,
            no_score,
            mitigation=cfg.mitigation,
            innate_yes_score=innate_yes,
            innate_no_score=innate_no,
        )
        raw_probability = _sigmoid(difference / cfg.score_scale)
        action = _action(difference, cfg, train=train, market_seed=market_seed, index=index)
        if train and condition != LEARNING_OFF and action is not Action.ABSTAIN:
            chosen_kc = kc_yes if action is Action.YES else kc_no
            plastic.record_decision(f"m{index}", chosen_kc, action.value)
            plastic.resolve(
                f"m{index}", _teaching(condition, market, action, raw_probability, cfg)
            )
        records.append(
            {
                "sequence": index,
                "outcome": market.outcome,
                "quote": market.quote,
                "raw_probability": raw_probability,
                "action": action.value,
                "score_difference": difference,
            }
        )

    train_records, test_records = records[: cfg.train_count], records[cfg.train_count :]
    calibrated = fit_and_apply_calibration(
        [r["raw_probability"] for r in train_records],
        [r["outcome"] for r in train_records],
        [r["raw_probability"] for r in test_records],
    )
    for record, probability in zip(test_records, calibrated.calibrated_test):
        record["calibrated_probability"] = float(probability)
    return {
        "condition": condition,
        "strength": strength,
        "market_seed": market_seed,
        "train": train_records,
        "test": test_records,
        "calibrator": asdict(calibrated.scaler),
    }


def _metric_summary(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    actions: Sequence[Action],
    quotes: np.ndarray,
    cfg: SyntheticConfig,
) -> dict:
    pnl = per_market_pnl(
        quotes,
        outcomes,
        actions,
        fee_per_trade=cfg.fee_per_trade,
        spread=cfg.spread,
    )
    reliability = reliability_diagram(probabilities, outcomes)
    def finite_or_none(values: np.ndarray) -> list[Optional[float]]:
        return [float(value) if np.isfinite(value) else None for value in values]

    return {
        "brier_score": brier_score(probabilities, outcomes),
        "log_loss": log_loss(probabilities, outcomes),
        "expected_calibration_error": expected_calibration_error(probabilities, outcomes),
        "reliability_diagram": {
            "bin_edges": reliability.bin_edges.tolist(),
            "counts": reliability.counts.tolist(),
            "mean_probabilities": finite_or_none(reliability.mean_probabilities),
            "observed_frequencies": finite_or_none(reliability.observed_frequencies),
        },
        "pnl_after_costs": float(np.sum(pnl)),
        "maximum_drawdown": maximum_drawdown(pnl),
        "turnover": turnover(actions),
        "abstention_rate": abstention_rate(actions),
    }


def evaluate_signal_requirement(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: SyntheticConfig) -> dict:
    """Evaluate complete job outputs and apply the pre-stated paired-bootstrap gate."""
    strengths_out: Dict[str, dict] = {}
    qualifying = []
    for strength in cfg.signal_strengths:
        circuit: Dict[str, dict] = {}
        condition_vectors: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, list[Action]]] = {}
        for condition in CONDITIONS:
            rows = [
                row
                for seed in cfg.market_seeds
                for row in outputs[(strength, seed, condition)]["test"]
            ]
            probabilities = np.asarray([r["calibrated_probability"] for r in rows])
            raw_probabilities = np.asarray([r["raw_probability"] for r in rows])
            outcomes = np.asarray([r["outcome"] for r in rows])
            quotes = np.asarray([r["quote"] for r in rows])
            actions = [Action(r["action"]) for r in rows]
            circuit[condition] = {
                "calibrated": _metric_summary(probabilities, outcomes, actions, quotes, cfg),
                "uncalibrated": _metric_summary(raw_probabilities, outcomes, actions, quotes, cfg),
            }
            condition_vectors[condition] = (probabilities, outcomes, quotes, actions)

        baseline_rows: Dict[str, Dict[str, list]] = {
            name: {"calibrated": [], "uncalibrated": []} for name in BASELINE_NAMES
        }
        baseline_outcomes, baseline_quotes = [], []
        for seed in cfg.market_seeds:
            markets = generate_signal_markets(cfg.markets_per_seed, seed, strength, cfg.price_deviation)
            train, test = markets[: cfg.train_count], markets[cfg.train_count :]
            train_obs = tuple(observe_market(m) for m in train)
            test_obs = tuple(observe_market(m) for m in test)
            suite = fit_baselines(
                train_obs,
                [m.outcome for m in train],
                feature_matrix(train),
                ("price", "recent_change", "time_to_resolution", "liquidity", "signal"),
                seed=seed,
            )
            predicted = suite.predict(test_obs, feature_matrix(test))
            for name in BASELINE_NAMES:
                baseline_rows[name]["calibrated"].extend(predicted[name].calibrated.tolist())
                baseline_rows[name]["uncalibrated"].extend(predicted[name].uncalibrated.tolist())
            baseline_outcomes.extend(m.outcome for m in test)
            baseline_quotes.extend(m.quote for m in test)
        y = np.asarray(baseline_outcomes)
        q = np.asarray(baseline_quotes)
        baseline_summary = {}
        for name, versions in baseline_rows.items():
            probabilities = np.asarray(versions["calibrated"])
            raw_probabilities = np.asarray(versions["uncalibrated"])
            observations = tuple(MarketObservation(float(x)) for x in q)
            actions = [decision.action for decision in decisions_from_forecasts(probabilities, observations)]
            baseline_summary[name] = {
                "calibrated": _metric_summary(probabilities, y, actions, q, cfg),
                "uncalibrated": _metric_summary(raw_probabilities, y, actions, q, cfg),
            }

        profit_p, profit_y, _, _ = condition_vectors[PROFIT]
        off_p, off_y, _, _ = condition_vectors[LEARNING_OFF]
        if not np.array_equal(profit_y, y) or not np.array_equal(off_y, y):
            raise ValueError("circuit and baseline test markets are not aligned")
        market_p = np.asarray(baseline_rows[MARKET_PRICE]["calibrated"])
        vs_market = (market_p - y) ** 2 - (profit_p - y) ** 2
        vs_off = (off_p - y) ** 2 - (profit_p - y) ** 2
        market_ci = bootstrap_confidence_interval(
            vs_market,
            np.mean,
            confidence_level=cfg.confidence_level,
            n_resamples=cfg.bootstrap_resamples,
            seed=cfg.bootstrap_seed + cfg.signal_strengths.index(strength),
        )
        off_ci = bootstrap_confidence_interval(
            vs_off,
            np.mean,
            confidence_level=cfg.confidence_level,
            n_resamples=cfg.bootstrap_resamples,
            seed=cfg.bootstrap_seed + 100 + cfg.signal_strengths.index(strength),
        )
        passes = market_ci.lower > 0.0 and off_ci.lower > 0.0
        if passes:
            qualifying.append(strength)
        strengths_out[str(strength)] = {
            "circuit": circuit,
            "baselines": baseline_summary,
            "profit_improvement_vs_market": asdict(market_ci),
            "profit_improvement_vs_learning_off": asdict(off_ci),
            "passes": passes,
        }
    requirement = min(qualifying) if qualifying else None
    higher_failures = (
        [
            strength
            for strength in cfg.signal_strengths
            if strength > requirement and not strengths_out[str(strength)]["passes"]
        ]
        if requirement is not None
        else []
    )
    return {
        "prestated_test": cfg.prestated,
        "mitigation": cfg.mitigation,
        "success": bool(qualifying),
        "signal_requirement": requirement,
        "higher_strength_failures": higher_failures,
        "strengths": strengths_out,
    }


def results_dir_for(base: Path, cfg: SyntheticConfig) -> Path:
    return Path(base) / f"synthetic_market_{cfg.config_hash()}"
