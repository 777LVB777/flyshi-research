"""Pure-numpy orchestration for the synthetic-market signal sweep.

The real spiking simulator is injected through the same small protocol used by
``first_learning``.  Tests use fakes; importing this module never imports Brian2
or loads connectome data.  Pre-stated design: ``docs/design/synthetic-market-experiment.md``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
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
    NO_MITIGATION,
    TOTAL_DRIVE_BALANCING,
    score_difference,
)
from .encoder import BALANCE_FEATURE, KCEncoder, OptionBStimuli
from .first_learning import Readout
from .mbon_sides import LEFT, side_mask
from .params import (
    OPTION_B_BALANCED,
    OPTION_B_UNBALANCED,
    EncoderParams,
    PlasticityParams,
    RewardParams,
)
from .plasticity import CompartmentMap, PlasticKCMBON
from .readout import load_dopamine_counts
from .reward import brier_improvement_reward, dopamine_signal, profit_reward

PROFIT = "profit"
ACCURACY = "accuracy"
LEARNING_OFF = "learning_off"
# Preregistered drift sensitivity check (decided 2026-09-22, docs/design/
# open-decisions.md item 4): the headline profit arm with drift switched off
# (drift_rate = 0). It is its own TRAINING condition because drift acts inside the
# learning loop and cannot be recomputed from a run that had drift on. It is
# reported next to the profit arm and never enters the pre-stated gate, which is
# defined on PROFIT against the market price and LEARNING_OFF.
PROFIT_DRIFT_OFF = "profit_drift_off"
CONDITIONS = (PROFIT, ACCURACY, LEARNING_OFF, PROFIT_DRIFT_OFF)
#: conditions whose teaching signal is the profit reward
PROFIT_LIKE = (PROFIT, PROFIT_DRIFT_OFF)
SIGNAL_STRENGTHS = (0.0, 0.1, 0.2, 0.4, 0.8)
MARKET_SEEDS = (20261001, 20261002, 20261003, 20261004, 20261005)


class Simulator(Protocol):
    kc_ids: Sequence[int]
    mbon_ids: Sequence[int]
    mbon_labels: Sequence[str]

    def baseline_weights(self) -> np.ndarray: ...
    def set_weights(self, weights: np.ndarray) -> None: ...
    def present_trials(
        self, rates_by_kc_id: Mapping[int, float], seed: int, duration_ms: float, n_trials: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """``(kc_mean, mbon_mean, kc_per_trial, apl_per_trial)``: trial-mean KC and MBON
        rates (``kc_ids`` / ``mbon_ids`` order), plus per-trial rates of every KC
        ``[n_trials, n_kc]`` and of every APL neuron ``[n_trials, n_apl]``. Required
        since 2026-10-09 for per-decision ignition tracking."""
        ...


@dataclass(frozen=True)
class SyntheticConfig:
    """Pre-stated sweep settings.

    ``mitigation`` defaults to ``NO_MITIGATION`` (decided 2026-10-09): the
    validated encoder exactly as ACCEPTED - left-only pools, mirrored NO framing,
    no balancing - read by the raw CIRCUIT-80 per-type-mean score.
    """

    mitigation: str = NO_MITIGATION
    signal_strengths: Tuple[float, ...] = SIGNAL_STRENGTHS
    market_seeds: Tuple[int, ...] = MARKET_SEEDS
    markets_per_seed: int = 100
    train_fraction: float = 0.70
    price_deviation: float = 0.20
    duration_ms: float = 1000.0
    trials: int = 5
    simulation_seed_base: int = 20270000
    exploration_seed: int = 20261090
    # DECIDED 2026-10-09 (was a placeholder). It cannot affect the pre-stated gate:
    # Platt calibration acts on logit(sigmoid(S / scale)) = S / scale, which it
    # rescales exactly unless |S| exceeds ~690 Hz (the 1e-15 probability clip), and
    # actions depend only on the sign of S. It sets only the accuracy arm's raw
    # forecast (hence its teaching signal) and the uncalibrated metrics. The
    # ACCEPTED validation's seed-mean scores (-3.7 to -29.1 Hz) map to 0.45-0.19,
    # far from saturation.
    score_scale: float = 20.0
    decision_margin: float = 0.0
    # Per-decision ignition tracking (DECIDED 2026-10-09; reported, never gating).
    # The same thresholds as every left-only diagnostic: a non-stimulated KC is
    # "recruited" in a trial above ignition_active_hz, and a trial is labelled
    # ignited when the recruited fraction of non-stimulated KCs exceeds
    # ignition_spread_fraction.
    ignition_active_hz: float = 0.5
    ignition_spread_fraction: float = 0.01
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


def option_b_variant(cfg: SyntheticConfig) -> str:
    """Stimulus construction for the configured mitigation, always named explicitly
    so the encoder-wide default (kept for historical runners) can never leak in."""
    return OPTION_B_BALANCED if cfg.mitigation == TOTAL_DRIVE_BALANCING else OPTION_B_UNBALANCED


def assert_pools_left_only(encoder: KCEncoder, kc_sides: Mapping[int, str]) -> None:
    """Abort unless every KC in every feature pool and the balance pool is
    annotated left-hemisphere. Port of the graded runners' ``_assert_pools_left_only``
    (docs/design/graded-encoding-left-only-mirrored.md, 3.1). Defence in depth: the
    encoder is given only left KCs to draw from, but this checks the drawn pools
    directly rather than trusting that alone. An unannotated KC counts as not left."""
    all_pool_ids = [int(i) for pool in encoder.pools.values() for i in pool]
    all_pool_ids += [int(i) for i in encoder.balance_pool]
    wrong = [i for i in all_pool_ids if kc_sides.get(i) != LEFT]
    if wrong:
        raise RuntimeError(
            f"{len(wrong)} pool KC(s) are not left-hemisphere: {sorted(wrong)[:5]}..."
        )


def setup_encoder(sim: Simulator, cfg: SyntheticConfig, kc_sides: Mapping[int, str]) -> KCEncoder:
    """The ACCEPTED encoder: pools drawn from the simulator's LEFT-hemisphere KCs
    only (the same draw as the graded validation), then guarded."""
    left = [int(k) for k in sim.kc_ids if kc_sides.get(int(k)) == LEFT]
    if not left:
        raise RuntimeError("no left-hemisphere KCs among the simulator's KCs")
    encoder = KCEncoder(left, params=cfg.encoder)
    assert_pools_left_only(encoder, kc_sides)
    return encoder


def _stimuli(
    encoder: KCEncoder,
    market: Market,
    cfg: SyntheticConfig,
) -> OptionBStimuli:
    pair = encoder.option_b_stimuli(market_features(market), variant=option_b_variant(cfg))
    if cfg.mitigation != TOTAL_DRIVE_BALANCING:
        # The ACCEPTED encoder: the five feature pools only. The balance pool is
        # drawn by the constructor but must never be presented.
        feature_kcs = sum(pool.size for pool in encoder.pools.values())
        for stimulus in (pair.yes, pair.no):
            if BALANCE_FEATURE in stimulus.feature_rates_hz or np.isin(
                stimulus.kc_ids, encoder.balance_pool
            ).any():
                raise RuntimeError("balance pool present in an unbalanced stimulus; aborting")
            if stimulus.kc_ids.size != feature_kcs:
                raise RuntimeError(
                    f"stimulus drives {stimulus.kc_ids.size} KCs, expected {feature_kcs}"
                )
    return pair


@dataclass(frozen=True)
class Presentation:
    """One Option B decision's raw material: KC patterns, per-MBON rates, scores,
    and the per-trial ignition record of each framing."""

    kc_yes: np.ndarray
    kc_no: np.ndarray
    mbon_yes: np.ndarray
    mbon_no: np.ndarray
    score_yes: float
    score_no: float
    ignition_yes: dict
    ignition_no: dict


def ignition_record(
    kc_ids: Sequence[int],
    kc_per_trial: np.ndarray,
    apl_per_trial: np.ndarray,
    stimulated_kc_ids: Sequence[int],
    kc_sides: Mapping[int, str],
    cfg: SyntheticConfig,
) -> dict:
    """Per-trial ignition measures of one presentation (decided 2026-10-09).

    Per trial: the recruited fraction of non-stimulated KCs (overall, left, right),
    the recruited count, the recruited KCs' mean rate (None when none), and the
    mean APL rate. ``ignited_any_trial`` is true when any trial's overall fraction
    exceeds ``cfg.ignition_spread_fraction``. Reported, never gating.
    """
    ids = np.asarray(kc_ids, dtype=np.int64)
    rates = np.asarray(kc_per_trial, dtype=float)
    if rates.ndim != 2 or rates.shape[1] != ids.size:
        raise ValueError("kc_per_trial must be [n_trials, n_kc] in kc_ids order")
    free = ~np.isin(ids, np.asarray(list(stimulated_kc_ids), dtype=np.int64))
    sides = np.array([kc_sides.get(int(i), "unknown") for i in ids.tolist()])
    masks = {"overall": free, "left": free & (sides == LEFT), "right": free & (sides == "right")}
    out: dict = {k: [] for k in ("spread", "spread_left", "spread_right",
                                 "n_recruited", "recruited_mean_hz", "apl_hz")}
    for t in range(rates.shape[0]):
        active = rates[t] > cfg.ignition_active_hz
        for key, mask in (("spread", masks["overall"]), ("spread_left", masks["left"]),
                          ("spread_right", masks["right"])):
            n = int(mask.sum())
            out[key].append(round(float((active & mask).sum() / n), 6) if n else None)
        recruited = active & free
        out["n_recruited"].append(int(recruited.sum()))
        out["recruited_mean_hz"].append(
            round(float(rates[t][recruited].mean()), 4) if recruited.any() else None)
        out["apl_hz"].append(round(float(np.mean(apl_per_trial[t])), 4))
    out["ignited_any_trial"] = any(
        s is not None and s > cfg.ignition_spread_fraction for s in out["spread"])
    return out


def _score_pair(
    sim: Simulator,
    readout: Readout,
    pair: OptionBStimuli,
    seed: int,
    cfg: SyntheticConfig,
    kc_sides: Mapping[int, str],
) -> Presentation:
    shown = {}
    for name, stim in (("yes", pair.yes), ("no", pair.no)):
        kc, mbon, kc_trials, apl_trials = sim.present_trials(
            stim.rates_by_kc_id(), seed, cfg.duration_ms, cfg.trials)
        shown[name] = (np.asarray(kc), np.asarray(mbon), ignition_record(
            sim.kc_ids, kc_trials, apl_trials, stim.kc_ids.tolist(), kc_sides, cfg))
    (kc_yes, mbon_yes, ign_yes), (kc_no, mbon_no, ign_no) = shown["yes"], shown["no"]
    return Presentation(
        kc_yes, kc_no, mbon_yes, mbon_no,
        readout.score(mbon_yes), readout.score(mbon_no),
        ign_yes, ign_no,
    )


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
    if condition in PROFIT_LIKE:
        gross = market.outcome - market.quote if action is Action.YES else market.quote - market.outcome
        profit = gross - cfg.fee_per_trade - 0.5 * cfg.spread
        value = profit_reward(profit, cfg.reward)
    elif condition == ACCURACY:
        value = brier_improvement_reward(forecast, market.outcome, market.quote, cfg.reward)
    else:
        raise ValueError(f"unknown condition {condition!r}")
    return dopamine_signal(value, cfg.reward).strengths()


def compute_innate_scores(
    sim: Simulator,
    cfg: SyntheticConfig,
    strength: float,
    market_seed: int,
    *,
    kc_sides: Mapping[int, str],
) -> list[Tuple[float, float]]:
    """Exact per-stimulus scores at baseline weights (two runs per market)."""
    markets = generate_signal_markets(
        cfg.markets_per_seed, market_seed, strength, cfg.price_deviation
    )
    encoder = setup_encoder(sim, cfg, kc_sides)
    readout = Readout(sim.mbon_labels, _first_learning_config())
    sim.set_weights(sim.baseline_weights())
    out = []
    for index, market in enumerate(markets):
        pair = _stimuli(encoder, market, cfg)
        shown = _score_pair(
            sim, readout, pair, simulation_seed(cfg, strength, market_seed, index), cfg, kc_sides
        )
        out.append((shown.score_yes, shown.score_no))
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
    kc_sides: Mapping[int, str],
    innate_scores: Optional[Sequence[Tuple[float, float]]] = None,
) -> dict:
    """Run one strength/seed/condition chain on an injected simulator.

    ``kc_sides`` (``{kc_root_id: "left" | "right"}``, from the frozen neuron-ID
    table) is required: encoder pools are drawn from left-hemisphere KCs only and
    guarded by :func:`assert_pools_left_only` before anything is presented."""
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
    encoder = setup_encoder(sim, cfg, kc_sides)
    readout = Readout(sim.mbon_labels, _first_learning_config())
    baseline = np.asarray(sim.baseline_weights(), dtype=float)
    cmap = CompartmentMap.from_dopamine_counts(
        list(sim.mbon_labels), load_dopamine_counts(), 80.0
    )
    # The drift sensitivity condition differs from the profit arm in one value.
    plasticity = (
        replace(cfg.plasticity, drift_rate=0.0)
        if condition == PROFIT_DRIFT_OFF
        else cfg.plasticity
    )
    plastic = PlasticKCMBON(baseline, cmap, plasticity)
    records = []

    for index, market in enumerate(markets):
        train = index < cfg.train_count
        sim.set_weights(plastic.weights if condition != LEARNING_OFF else baseline)
        pair = _stimuli(encoder, market, cfg)
        shown = _score_pair(
            sim, readout, pair, simulation_seed(cfg, strength, market_seed, index), cfg, kc_sides
        )
        innate_yes, innate_no = (innate_scores[index] if innate_scores is not None else (None, None))
        difference = score_difference(
            shown.score_yes,
            shown.score_no,
            mitigation=cfg.mitigation,
            innate_yes_score=innate_yes,
            innate_no_score=innate_no,
        )
        raw_probability = _sigmoid(difference / cfg.score_scale)
        action = _action(difference, cfg, train=train, market_seed=market_seed, index=index)
        if train and condition != LEARNING_OFF and action is not Action.ABSTAIN:
            chosen_kc = shown.kc_yes if action is Action.YES else shown.kc_no
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
                # Exact presented drive (sum of KC rates) of each framing. Under
                # no mitigation D_YES - D_NO is the drive confound, reported with
                # every decision for the innate-policy metric.
                "drive_yes_hz": float(np.sum(pair.yes.rates_hz)),
                "drive_no_hz": float(np.sum(pair.no.rates_hz)),
                # Per-trial ignition record of each framing (decided 2026-10-09):
                # reported, never gating; used by the pre-stated sensitivity
                # analysis that excludes test markets with an ignited framing.
                "ignition_yes": shown.ignition_yes,
                "ignition_no": shown.ignition_no,
                # Per-MBON rates are saved for the preregistered left-only POST-HOC
                # RESCORING (see ``left_only_rescore``), which adds no simulation and
                # is never an arm or a condition: it rescores these runs as they
                # actually happened, it does not replay the decision loop.
                "mbon_yes": [round(float(x), 4) for x in shown.mbon_yes],
                "mbon_no": [round(float(x), 4) for x in shown.mbon_no],
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
        "drift_rate": plasticity.drift_rate,
        "mbon_ids": [int(i) for i in sim.mbon_ids],
        "mbon_labels": list(sim.mbon_labels),
        "train": train_records,
        "test": test_records,
        "calibrator": asdict(calibrated.scaler),
    }


def left_only_rescore(output: Mapping, cfg: SyntheticConfig, side: str = LEFT,
                      sides: Optional[Dict[int, str]] = None) -> dict:
    """POST-HOC RESCORING of a finished job under a left-hemisphere-only readout.

    Preregistered (decided 2026-09-22); reported, never gating, and never an arm or
    a condition: no run is added.

    NOT EXACT HERE. This experiment's loop is closed - score -> action -> teaching -
    so a left-only readout would have produced different decisions and different
    weight updates. This rescores the runs as they actually happened under a
    left-only readout; it does not replay the decision loop, so it cannot show what
    a left-only system would have done. (The first learning test differs: its
    teaching signal comes from the condition, not the readout, so the rescoring
    there is exact - see ``first_learning.left_only_rescore``.) Its score units also
    differ, so its decision margin would have to be calibrated separately on
    training markets.
    """
    labels, mbon_ids = list(output["mbon_labels"]), list(output["mbon_ids"])
    mask = side_mask(mbon_ids, side, sides)
    readout = Readout([l for l, keep in zip(labels, mask.tolist()) if keep], _first_learning_config())

    def rescore(rows: Sequence[Mapping]) -> list[dict]:
        out = []
        for row in rows:
            yes = readout.score(np.asarray(row["mbon_yes"])[mask])
            no = readout.score(np.asarray(row["mbon_no"])[mask])
            out.append({
                "sequence": row["sequence"],
                "score_yes": yes,
                "score_no": no,
                "score_difference": yes - no,
                "raw_probability": _sigmoid((yes - no) / cfg.score_scale),
            })
        return out

    return {
        "side": side,
        "n_instances": int(mask.sum()),
        "condition": output["condition"],
        "strength": output["strength"],
        "market_seed": output["market_seed"],
        "note": ("post-hoc rescoring of the runs as they actually happened; the decision loop "
                 "was not replayed, so this cannot show what a left-only system would have done"),
        "train": rescore(output["train"]),
        "test": rescore(output["test"]),
    }


#: equal-width price bins for the innate-policy report
INNATE_POLICY_PRICE_BINS = 10


def _slope_and_r(x: np.ndarray, y: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    if x.size < 2 or np.ptp(x) == 0.0:
        return None, None
    slope = float(np.polyfit(x, y, 1)[0])
    r = None if np.ptp(y) == 0.0 else float(np.corrcoef(x, y)[0, 1])
    return slope, r


def innate_policy(rows: Sequence[Mapping]) -> dict:
    """The learning-off arm's decision pattern versus price. REPORTED, NEVER GATING.

    Decided 2026-10-09: under no mitigation the drive confound gives the untouched
    circuit an innate policy (expected: a tendency to bet against the higher-priced
    side), which must be measured and reported, not removed. ``rows`` are
    learning-off records. Learning-off never changes weights, so every row - train
    and test - is a baseline-weight decision; the innate choice is the sign of the
    raw score difference (an exact tie is ``tie``). This equals the held-out action
    exactly (margin 0, ties abstain) and differs from a training action only where
    training-only exploration broke a tie.
    """
    price = np.asarray([r["quote"] for r in rows], dtype=float)
    diff = np.asarray([r["score_difference"] for r in rows], dtype=float)
    choice = np.where(diff > 0, 1, np.where(diff < 0, -1, 0))  # YES, NO, tie
    out: dict = {
        "note": "reported, never gating; innate choice = sign of the raw learning-off score",
        "n_decisions": int(price.size),
        "fraction_yes": float(np.mean(choice == 1)) if price.size else None,
        "fraction_no": float(np.mean(choice == -1)) if price.size else None,
        "fraction_tie": float(np.mean(choice == 0)) if price.size else None,
    }
    # Higher-priced side: YES when price > 0.5, NO when price < 0.5 (0.5 excluded).
    sided = (price != 0.5) & (choice != 0)
    backs_higher = np.where(price > 0.5, choice == 1, choice == -1)
    out["n_sided_decisions"] = int(sided.sum())
    out["fraction_backing_higher_priced_side"] = (
        float(np.mean(backs_higher[sided])) if sided.any() else None
    )
    out["score_vs_price_slope_hz"], out["score_vs_price_r"] = _slope_and_r(price, diff)
    if rows and "drive_yes_hz" in rows[0]:
        drive = np.asarray([r["drive_yes_hz"] - r["drive_no_hz"] for r in rows]) / 1000.0
        out["score_vs_drive_difference_slope_hz_per_khz"], out["score_vs_drive_difference_r"] = (
            _slope_and_r(drive, diff)
        )
    edges = np.linspace(0.0, 1.0, INNATE_POLICY_PRICE_BINS + 1)
    which = np.clip(np.digitize(price, edges[1:-1]), 0, INNATE_POLICY_PRICE_BINS - 1)
    bins = []
    for b in range(INNATE_POLICY_PRICE_BINS):
        m = which == b
        n = int(m.sum())
        bins.append({
            "price_low": float(edges[b]),
            "price_high": float(edges[b + 1]),
            "n": n,
            "fraction_yes": float(np.mean(choice[m] == 1)) if n else None,
            "fraction_no": float(np.mean(choice[m] == -1)) if n else None,
            "fraction_tie": float(np.mean(choice[m] == 0)) if n else None,
            "mean_score_difference": float(np.mean(diff[m])) if n else None,
        })
    out["by_price_bin"] = bins
    return out


#: arms whose ignition excludes a test market from the sensitivity analysis: the two
#: simulated arms the pre-stated gate compares (the market price is not simulated)
SENSITIVITY_ARMS = (PROFIT, LEARNING_OFF)
#: bootstrap seed offsets of the sensitivity analysis (gate: +0 and +100)
SENSITIVITY_SEED_OFFSETS = (200, 300)


def _ignited(row: Mapping) -> bool:
    return bool(row["ignition_yes"]["ignited_any_trial"] or row["ignition_no"]["ignited_any_trial"])


def ignition_exposure(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: "SyntheticConfig",
                      strength: float) -> dict:
    """Decisions with an ignited framing, per arm and split. Reported, never gating."""
    out = {}
    for condition in CONDITIONS:
        rows = {split: [r for seed in cfg.market_seeds
                        for r in outputs[(strength, seed, condition)][split]]
                for split in ("train", "test")}
        try:
            out[condition] = {f"{split}_decisions_with_ignited_framing": sum(_ignited(r) for r in rs)
                              for split, rs in rows.items()}
        except KeyError as missing:
            return {"available": False, "reason": f"ignition record missing ({missing})"}
        out[condition]["decisions"] = sum(len(rs) for rs in rows.values())
    return out


def sensitivity_excluding_ignited(
    outputs: Mapping[Tuple[float, int, str], Mapping], cfg: "SyntheticConfig", strength: float,
    vs_market: np.ndarray, vs_off: np.ndarray,
) -> dict:
    """PRE-STATED SENSITIVITY ANALYSIS (2026-10-09). REPORTED ONLY, NEVER GATING.

    Re-evaluates the Section 6 gate after excluding every held-out market in which
    either framing ignited in any trial, in either arm the gate compares (profit or
    learning-off). Known limits (spec Section 6 revision): the excluded markets are
    not a random subset (they are low-drive feature combinations), and learning from
    ignited TRAINING presentations is already in the weights and cannot be removed.
    """
    try:
        excluded = np.zeros(vs_market.size, dtype=bool)
        for condition in SENSITIVITY_ARMS:
            rows = [r for seed in cfg.market_seeds for r in outputs[(strength, seed, condition)]["test"]]
            excluded |= np.array([_ignited(r) for r in rows], dtype=bool)
    except KeyError as missing:
        return {"available": False, "reason": f"ignition record missing ({missing})"}
    keep = ~excluded
    out = {
        "note": ("reported only, never gating; excluded markets are not random and learning "
                 "from ignited training presentations cannot be removed"),
        "available": True,
        "n_test_markets": int(vs_market.size),
        "n_excluded": int(excluded.sum()),
        "n_remaining": int(keep.sum()),
    }
    if keep.sum() < 2:
        out.update(available=False, reason="fewer than two markets remain")
        return out
    i = cfg.signal_strengths.index(strength)
    cis = [bootstrap_confidence_interval(
        values[keep], np.mean, confidence_level=cfg.confidence_level,
        n_resamples=cfg.bootstrap_resamples, seed=cfg.bootstrap_seed + offset + i)
        for values, offset in ((vs_market, SENSITIVITY_SEED_OFFSETS[0]),
                               (vs_off, SENSITIVITY_SEED_OFFSETS[1]))]
    out["profit_improvement_vs_market"] = asdict(cis[0])
    out["profit_improvement_vs_learning_off"] = asdict(cis[1])
    out["both_lower_bounds_above_zero"] = bool(cis[0].lower > 0.0 and cis[1].lower > 0.0)
    return out


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
    innate_rows: list = []
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
        off_rows = [
            row
            for seed in cfg.market_seeds
            for split in ("train", "test")
            for row in outputs[(strength, seed, LEARNING_OFF)][split]
        ]
        innate_rows.extend(off_rows)
        strengths_out[str(strength)] = {
            "circuit": circuit,
            "baselines": baseline_summary,
            "innate_policy": innate_policy(off_rows),
            "profit_improvement_vs_market": asdict(market_ci),
            "profit_improvement_vs_learning_off": asdict(off_ci),
            "passes": passes,
            # Reported, never gating (pre-stated 2026-10-09).
            "ignition_exposure": ignition_exposure(outputs, cfg, strength),
            "sensitivity_excluding_ignited": sensitivity_excluding_ignited(
                outputs, cfg, strength, vs_market, vs_off),
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
        # Reported, never gating (decided 2026-10-09). Pooled across strengths:
        # price, recent change, time to resolution and liquidity are identical at
        # every strength for a given market seed; only the signal feature differs.
        "innate_policy_pooled": innate_policy(innate_rows),
        # Reported, never gating: the smallest strength whose sensitivity analysis
        # (ignited test markets excluded) has both lower bounds above zero.
        "sensitivity_excluding_ignited_smallest_strength": next(
            (st for st in cfg.signal_strengths
             if strengths_out[str(st)]["sensitivity_excluding_ignited"].get(
                 "both_lower_bounds_above_zero")), None),
        "strengths": strengths_out,
    }


def results_dir_for(base: Path, cfg: SyntheticConfig) -> Path:
    return Path(base) / f"synthetic_market_{cfg.config_hash()}"
