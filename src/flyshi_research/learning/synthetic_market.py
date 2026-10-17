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
from flyshi_research.simulator import (
    PRICE_CEILING,
    PRICE_FLOOR,
    TRUE_PROBABILITY_HIGH,
    TRUE_PROBABILITY_LOW,
    Action,
    Market,
    MarketObservation,
    generate_signal_markets,
    observe_market,
    price_only_posterior_mean,
)

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
# DECIDED 2026-10-09 (synthetic-market-experiment.md, Sections 1, 2 and 6
# revisions; was strengths 0, 0.1, 0.2, 0.4, 0.8 and seeds 20261001-20261005 with
# 100 markets per seed, 70 train / 30 test). 0 is the null control, 1.0 the
# positive control (the signal equals the hidden probability); 0.4 is
# pre-stated as underpowered.
SIGNAL_STRENGTHS = (0.0, 0.4, 0.8, 1.0)
MARKET_SEEDS = tuple(range(20261001, 20261021))
NULL_CONTROL_STRENGTH = 0.0
#: strength -> pre-stated note; a non-pass there reads "undetermined", not "absent"
UNDERPOWERED_STRENGTHS = {
    0.4: "ideal-forecaster power about 0.70 at 3,600 test markets; a non-pass is undetermined, not absent",
}
#: the gate's market comparator (DECIDED 2026-10-09; was the Platt-calibrated price)
PRICE_ONLY_POSTERIOR = "price_only_bayes_posterior"
MARKET_COMPARATORS = (PRICE_ONLY_POSTERIOR,)
#: the design before the 2026-10-09 power revision. Kept so the completed extremes
#: containment and low-drive follow-up diagnostics, whose stimuli were selected
#: from that design's presentations, still reproduce their frozen tables.
PRE_REVISION_DESIGN = {
    "signal_strengths": (0.0, 0.1, 0.2, 0.4, 0.8),
    "market_seeds": (20261001, 20261002, 20261003, 20261004, 20261005),
    "markets_per_seed": 100,
    "train_fraction": 0.70,
}


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
    # DECIDED 2026-10-09: 250 markets per seed, markets 0-69 train, 70-249 test
    # (train_count = int(250 * 0.28) = 70; pinned by a test).
    markets_per_seed: int = 250
    train_fraction: float = 0.28
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
    market_comparator: str = PRICE_ONLY_POSTERIOR
    encoder: EncoderParams = field(default_factory=EncoderParams)
    plasticity: PlasticityParams = field(default_factory=PlasticityParams)
    reward: RewardParams = field(default_factory=RewardParams)
    prestated: bool = True

    def __post_init__(self) -> None:
        if self.mitigation not in MITIGATIONS:
            raise ValueError(f"mitigation must be one of {MITIGATIONS}")
        if self.market_comparator not in MARKET_COMPARATORS:
            raise ValueError(f"market_comparator must be one of {MARKET_COMPARATORS}")
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


def pre_revision_config() -> "SyntheticConfig":
    """The sweep design before the 2026-10-09 power revision (historical only)."""
    return replace(SyntheticConfig(), **PRE_REVISION_DESIGN)


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


#: Two-phase run order (pre-stated 2026-10-11, synthetic-market-experiment.md
#: Section 7): phase 1 is the two arms the gate compares, phase 2 the reported
#: arms. Not part of SyntheticConfig: the order changes no job's output, so the
#: config hash is unchanged. Phase 2 runs regardless of phase 1, and no phase 1
#: result is analysed until phase 2 is complete.
GATE_ARMS = (PROFIT, LEARNING_OFF)
RUN_PHASES = {1: GATE_ARMS, 2: (ACCURACY, PROFIT_DRIFT_OFF)}
assert sorted(a for arms in RUN_PHASES.values() for a in arms) == sorted(CONDITIONS)


def phase_of(condition: str) -> int:
    return next(phase for phase, arms in RUN_PHASES.items() if condition in arms)


def plan_jobs(cfg: SyntheticConfig, arms: Optional[Sequence[str]] = None) -> list[Job]:
    """Every job of the sweep, or only those of the named arms (plus the innate jobs
    they depend on). Selecting arms changes which jobs exist, never their contents."""
    jobs = _plan_all_jobs(cfg)
    if arms is None:
        return jobs
    unknown = set(arms) - set(CONDITIONS)
    if unknown:
        raise ValueError(f"unknown arm(s) {sorted(unknown)}; arms are {CONDITIONS}")
    selected = [j for j in jobs if j.kind == "condition" and j.condition in arms]
    needed = {d for j in selected for d in j.deps}
    return [j for j in jobs if j in selected or j.id in needed]


def run_order(jobs: Sequence[Job]) -> list[Job]:
    """Jobs in the pre-stated run order: innate jobs, then phase 1, then phase 2;
    plan order within each. A launcher started on the whole sweep therefore starts
    every phase 1 job before any phase 2 job, and phase 2 fills slots as phase 1
    drains, with no idle tail between the phases."""
    def key(job: Job) -> int:
        return 0 if job.kind == "innate" else phase_of(job.condition)
    return sorted(jobs, key=key)  # stable: plan order within a phase


def _plan_all_jobs(cfg: SyntheticConfig) -> list[Job]:
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


def decision_loop(
    sim: Simulator,
    cfg: SyntheticConfig,
    markets: Sequence[Market],
    train_count: int,
    condition: str,
    *,
    kc_sides: Mapping[int, str],
    seed_for,
    exploration_key: int,
    innate_scores: Optional[Sequence[Tuple[float, float]]] = None,
    teach_as: Optional[str] = None,
    teaching_markets: Optional[Sequence[Market]] = None,
) -> Tuple[list, PlasticityParams]:
    """The chronological Option B decision loop shared by the synthetic sweep
    (``run_dataset``) and the Phase 2 real-market chains (``real_market``): one
    encoder, readout, plasticity rule and teaching signal for both.

    Markets ``0 .. train_count - 1`` are training (plasticity on, seeded
    exploration breaks ties); the rest are held out with the weights frozen.
    ``seed_for(index)`` gives each presentation's simulation seed and
    ``exploration_key`` keys the exploration draw. ``teach_as`` (default:
    ``condition``) names the teaching rule, and ``teaching_markets`` (default:
    ``markets``) supplies the outcome and quote the teaching signal reads; the
    shuffled-outcome null control passes the profit rule with permuted outcomes.
    Every record carries the market's TRUE outcome. Returns ``(records,
    plasticity params used)``."""
    teach_as = condition if teach_as is None else teach_as
    teaching_markets = markets if teaching_markets is None else teaching_markets
    if len(teaching_markets) != len(markets):
        raise ValueError("teaching_markets must match markets one to one")
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
        train = index < train_count
        sim.set_weights(plastic.weights if condition != LEARNING_OFF else baseline)
        pair = _stimuli(encoder, market, cfg)
        shown = _score_pair(sim, readout, pair, seed_for(index), cfg, kc_sides)
        innate_yes, innate_no = (innate_scores[index] if innate_scores is not None else (None, None))
        difference = score_difference(
            shown.score_yes,
            shown.score_no,
            mitigation=cfg.mitigation,
            innate_yes_score=innate_yes,
            innate_no_score=innate_no,
        )
        raw_probability = _sigmoid(difference / cfg.score_scale)
        action = _action(difference, cfg, train=train, market_seed=exploration_key, index=index)
        if train and condition != LEARNING_OFF and action is not Action.ABSTAIN:
            chosen_kc = shown.kc_yes if action is Action.YES else shown.kc_no
            plastic.record_decision(f"m{index}", chosen_kc, action.value)
            plastic.resolve(
                f"m{index}",
                _teaching(teach_as, teaching_markets[index], action, raw_probability, cfg),
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
    return records, plasticity


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
    records, plasticity = decision_loop(
        sim, cfg, markets, cfg.train_count, condition, kc_sides=kc_sides,
        seed_for=lambda index: simulation_seed(cfg, strength, market_seed, index),
        exploration_key=market_seed, innate_scores=innate_scores,
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
                      strength: float, arms: Sequence[str] = CONDITIONS) -> dict:
    """Decisions with an ignited framing, per arm and split. Reported, never gating."""
    out = {}
    for condition in arms:
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


def _ignited_trials(record: Mapping, cfg: "SyntheticConfig") -> int:
    return sum(s is not None and s > cfg.ignition_spread_fraction for s in record["spread"])


def _ignited_training_counts(rows: Sequence[Mapping], condition: str, cfg: "SyntheticConfig") -> dict:
    taught = [r for r in rows if condition != LEARNING_OFF and r["action"] != Action.ABSTAIN.value]
    chosen = {Action.YES.value: "ignition_yes", Action.NO.value: "ignition_no"}
    return {
        "training_decisions": len(rows),
        "training_decisions_with_ignited_framing": sum(_ignited(r) for r in rows),
        "teaching_decisions": len(taught),
        "teaching_decisions_with_ignited_framing": sum(_ignited(r) for r in taught),
        "teaching_decisions_chosen_framing_ignited": sum(
            bool(r[chosen[r["action"]]]["ignited_any_trial"]) for r in taught),
        "ignited_trials_in_teaching_decisions": sum(
            _ignited_trials(r[side], cfg) for r in taught for side in ("ignition_yes", "ignition_no")),
    }


def ignited_training_presentations(
    outputs: Mapping[Tuple[float, int, str], Mapping], cfg: "SyntheticConfig",
    arms: Sequence[str] = CONDITIONS,
) -> dict:
    """PRE-STATED COUNT (2026-10-09). REPORTED ONLY, NEVER GATING.

    Per arm and per signal strength (and pooled over strengths): how many TRAINING
    decisions had a framing that ignited in any trial, and how many of those taught
    the circuit (learning arm, not an abstention), split by whether the taught,
    chosen framing itself ignited. The learning-off arm teaches nothing; its counts
    show the baseline-weight exposure. The safeguard that would skip these updates
    was considered and NOT adopted (spec Section 3), so these decisions did teach.
    """
    out = {"note": ("reported only, never gating; decisions that could have taught the "
                    "circuit from a presentation with an ignited trial (safeguard not adopted)")}
    try:
        for condition in arms:
            per_strength = {}
            pooled_rows = []
            for strength in cfg.signal_strengths:
                rows = [r for seed in cfg.market_seeds
                        for r in outputs[(strength, seed, condition)]["train"]]
                pooled_rows.extend(rows)
                per_strength[str(strength)] = _ignited_training_counts(rows, condition, cfg)
            out[condition] = {"by_strength": per_strength,
                              "all_strengths": _ignited_training_counts(pooled_rows, condition, cfg)}
    except KeyError as missing:
        return {"available": False, "reason": f"ignition record missing ({missing})"}
    out["available"] = True
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


#: Price regions of the profit report (DECIDED 2026-10-09; reported, never gating).
#: "clipped": the price sits at PRICE_FLOOR or PRICE_CEILING. "outer": unclipped,
#: but within price_deviation of the bounded truth range, where the price alone is
#: a biased forecast. "interior": the price-only posterior mean equals the price.
PRICE_REGIONS = ("clipped", "outer", "interior")
#: Labels of the gate's two comparisons (DECIDED 2026-10-09).
COMPARISON_LABELS = {
    "profit_improvement_vs_market": "signal edge over the best price-only forecast",
    "profit_improvement_vs_learning_off": "learning effect, any source",
}


def market_comparator_forecast(quotes: np.ndarray, cfg: SyntheticConfig) -> np.ndarray:
    """The gate's market comparator: the exact price-only Bayes posterior mean."""
    if cfg.market_comparator != PRICE_ONLY_POSTERIOR:
        raise ValueError(f"unknown market comparator {cfg.market_comparator!r}")
    return np.array([price_only_posterior_mean(float(q), cfg.price_deviation) for q in quotes])


def price_region(quote: float, cfg: SyntheticConfig) -> str:
    if quote <= PRICE_FLOOR or quote >= PRICE_CEILING:
        return "clipped"
    if quote < TRUE_PROBABILITY_LOW + cfg.price_deviation or quote > TRUE_PROBABILITY_HIGH - cfg.price_deviation:
        return "outer"
    return "interior"


def price_only_reference_actions(quotes: np.ndarray, cfg: SyntheticConfig) -> list:
    """The price-only Bayes trader: trades only when the posterior clears the cost."""
    cost = cfg.fee_per_trade + 0.5 * cfg.spread
    posterior = market_comparator_forecast(quotes, cfg)
    return [Action.YES if f - q > cost else Action.NO if q - f > cost else Action.ABSTAIN
            for f, q in zip(posterior, quotes)]


def profit_by_price_region(
    condition_vectors: Mapping[str, Tuple[np.ndarray, np.ndarray, np.ndarray, list]], cfg: SyntheticConfig
) -> dict:
    """REPORTED ONLY, NEVER GATING (DECIDED 2026-10-09). Held-out P/L after costs per
    arm and per price region, next to the price-only Bayes trader, which earns from
    the price alone wherever the bounded truth range makes the price biased."""
    _, outcomes, quotes, _ = next(iter(condition_vectors.values()))
    regions = np.array([price_region(float(q), cfg) for q in quotes])
    traders = {c: v[3] for c, v in condition_vectors.items()}
    traders["price_only_bayes_trader_reference"] = price_only_reference_actions(quotes, cfg)
    out = {"note": "reported only, never gating; the reference trader uses no signal",
           "regions": {r: int(np.sum(regions == r)) for r in PRICE_REGIONS}}
    for name, actions in traders.items():
        pnl = per_market_pnl(quotes, outcomes, actions, fee_per_trade=cfg.fee_per_trade, spread=cfg.spread)
        out[name] = {"all": {"pnl_after_costs": float(pnl.sum()), "pnl_per_market": float(pnl.mean())}}
        for r in PRICE_REGIONS:
            mask = regions == r
            out[name][r] = {"pnl_after_costs": float(pnl[mask].sum()),
                            "pnl_per_market": float(pnl[mask].mean()) if mask.any() else None}
    return out


def evaluate_signal_requirement(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: SyntheticConfig,
                                arms: Sequence[str] = CONDITIONS) -> dict:
    """Evaluate complete job outputs and apply the pre-stated paired-bootstrap gate.

    ``arms``: the conditions to evaluate (default: all four). The gate needs only
    GATE_ARMS; evaluate_phase1 passes exactly those."""
    if not set(GATE_ARMS) <= set(arms) or set(arms) - set(CONDITIONS):
        raise ValueError(f"arms must include {GATE_ARMS} and be among {CONDITIONS}")
    strengths_out: Dict[str, dict] = {}
    qualifying = []
    innate_rows: list = []
    profit_by_strength: Dict[float, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for strength in cfg.signal_strengths:
        circuit: Dict[str, dict] = {}
        condition_vectors: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, list[Action]]] = {}
        for condition in arms:
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
        # DECIDED 2026-10-09: the comparator is the exact price-only Bayes posterior
        # (was the Platt-calibrated price, baseline_rows[MARKET_PRICE]["calibrated"],
        # still reported among the baselines). Platt on logit(price) is pulled flat by
        # the clipped prices and lost to the raw price, so a forecaster with no
        # signal could pass at strength 0.
        if not np.array_equal(condition_vectors[PROFIT][2], q):
            raise ValueError("circuit and baseline test quotes are not aligned")
        market_p = market_comparator_forecast(q, cfg)
        profit_by_strength[strength] = (profit_p, y, q)
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
        # Strength 0 is the null control (DECIDED 2026-10-09): it never sets the
        # signal requirement; a pass there is a pipeline or generator problem.
        if passes and strength != NULL_CONTROL_STRENGTH:
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
            "market_comparator": cfg.market_comparator,
            "profit_improvement_vs_market": asdict(market_ci),
            "profit_improvement_vs_learning_off": asdict(off_ci),
            "comparison_labels": dict(COMPARISON_LABELS),
            "passes": passes,
            "role": ("null control" if strength == NULL_CONTROL_STRENGTH
                     else "positive control" if strength == 1.0 else "test"),
            "prestated_power_note": UNDERPOWERED_STRENGTHS.get(strength),
            # Reported, never gating (DECIDED 2026-10-09).
            "profit_by_price_region": profit_by_price_region(condition_vectors, cfg),
            # Reported, never gating (pre-stated 2026-10-09).
            "ignition_exposure": ignition_exposure(outputs, cfg, strength, arms),
            "sensitivity_excluding_ignited": sensitivity_excluding_ignited(
                outputs, cfg, strength, vs_market, vs_off),
        }
    null = strengths_out.get(str(NULL_CONTROL_STRENGTH))
    null_failed = bool(null and null["passes"])
    # Secondary, non-gating (DECIDED 2026-10-09): the profit arm at strength s
    # against the profit arm at strength 0 on the same held-out markets. Prices
    # and outcomes are identical across strengths; only the signal differs.
    for strength in cfg.signal_strengths:
        if strength == NULL_CONTROL_STRENGTH:
            continue
        entry: dict = {"note": "secondary, never gating; same markets, only the signal differs"}
        if NULL_CONTROL_STRENGTH not in profit_by_strength:
            entry.update(available=False, reason="strength 0 not in the sweep")
        else:
            p0, y0, q0 = profit_by_strength[NULL_CONTROL_STRENGTH]
            ps, ys, qs = profit_by_strength[strength]
            if not (np.array_equal(y0, ys) and np.array_equal(q0, qs)):
                raise ValueError("strength-0 and strength-s test markets are not identical")
            ci = bootstrap_confidence_interval(
                (p0 - ys) ** 2 - (ps - ys) ** 2, np.mean,
                confidence_level=cfg.confidence_level, n_resamples=cfg.bootstrap_resamples,
                seed=cfg.bootstrap_seed + 400 + cfg.signal_strengths.index(strength))
            entry.update(available=True, improvement=asdict(ci), lower_bound_above_zero=ci.lower > 0.0)
        strengths_out[str(strength)]["secondary_profit_vs_strength0"] = entry
    requirement = min(qualifying) if qualifying and not null_failed else None
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
        "market_comparator": cfg.market_comparator,
        "success": bool(qualifying) and not null_failed,
        "signal_requirement": requirement,
        "higher_strength_failures": higher_failures,
        # DECIDED 2026-10-09: a pass at strength 0 under the price-only posterior
        # comparator indicates a pipeline or generator problem, not a finding.
        "null_control": None if null is None else {
            "strength": NULL_CONTROL_STRENGTH,
            "passes": null_failed,
            "interpretation": ("NULL CONTROL FAILED: a pipeline or generator problem, not a finding; "
                               "no signal requirement is reported" if null_failed
                               else "null control did not pass, as expected"),
        },
        # Reported, never gating (decided 2026-10-09). Pooled across strengths:
        # price, recent change, time to resolution and liquidity are identical at
        # every strength for a given market seed; only the signal feature differs.
        "innate_policy_pooled": innate_policy(innate_rows),
        # Reported, never gating: the smallest strength whose sensitivity analysis
        # (ignited test markets excluded) has both lower bounds above zero.
        "sensitivity_excluding_ignited_smallest_strength": next(
            (st for st in cfg.signal_strengths
             if st != NULL_CONTROL_STRENGTH
             and strengths_out[str(st)]["sensitivity_excluding_ignited"].get(
                 "both_lower_bounds_above_zero")), None),
        # Reported, never gating (pre-stated 2026-10-09): training decisions that
        # could have taught the circuit from a presentation with an ignited trial.
        "ignited_training_presentations": ignited_training_presentations(outputs, cfg, arms),
        "strengths": strengths_out,
    }


# ---- phase 1 only: gate-only evaluation --------------------------------------------- #
# Pre-stated exception (synthetic-market-experiment.md, Section 7 revision 2026-10-11):
# phase 2 (accuracy, profit_drift_off) was dropped for budget, so the gate is reported
# from the phase 1 arms alone and the dropped arms are marked "not run". Written on
# 2026-10-12, after that decision and before any phase 1 result file was read; tested
# on fake job files only. The gate, its comparator, bootstrap seeds, null control and
# every report are the pre-stated ones: this only restricts which arms are evaluated.
PHASE1_ARMS = RUN_PHASES[1]
DROPPED_ARMS = RUN_PHASES[2]
NOT_RUN_NOTE = "not run (dropped for budget, 2026-10-11)"
PHASE1_EVALUATION_LABEL = (
    "phase 1 only: gate-only evaluation per the 2026-10-11 budget revision; written "
    "2026-10-12, after that decision and before any phase 1 result was read")
#: fields the ignition report reads (2026-10-12 revision, point 4); nothing else
IGNITION_REPORT_FIELDS = ("sequence", "drive_yes_hz", "drive_no_hz", "ignition_yes", "ignition_no")
#: fixed framing-drive bands of the ignition report, in kHz: [low, high)
IGNITION_DRIVE_BANDS_KHZ = ((None, 25.0), (25.0, 30.0), (30.0, 40.0), (40.0, 50.0), (50.0, 70.0), (70.0, None))
IGNITION_DRIVE_BAND_LABELS = ("<25 kHz", "25-30 kHz", "30-40 kHz", "40-50 kHz", "50-70 kHz", ">=70 kHz")
IGNITION_BLOCK_DECISIONS = 10
_Z95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = _Z95) -> Tuple[Optional[float], Optional[float]]:
    """Wilson score interval for k successes out of n (None, None when n = 0)."""
    if n == 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def newcombe_difference(k1: int, n1: int, k2: int, n2: int) -> dict:
    """p1 - p2 with Newcombe's hybrid score interval (method 10), from Wilson intervals."""
    if n1 == 0 or n2 == 0:
        return {"difference": None, "lower": None, "upper": None}
    p1, p2 = k1 / n1, k2 / n2
    (l1, u1), (l2, u2) = wilson_interval(k1, n1), wilson_interval(k2, n2)
    d = p1 - p2
    return {"difference": d, "lower": float(d - np.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            "upper": float(d + np.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))}


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"ignited": int(k), "total": int(n), "rate": (k / n) if n else None, "wilson_95": [lo, hi]}


def _spread_flags(record: Mapping, cfg: SyntheticConfig) -> list:
    return [s is not None and s > cfg.ignition_spread_fraction for s in record["spread"]]


def _range_summary(values: Sequence) -> Optional[dict]:
    v = [float(x) for x in values if x is not None]
    return {"median": float(np.median(v)), "min": min(v), "max": max(v), "n": len(v)} if v else None


def _drive_band(drive_hz: float) -> str:
    khz = drive_hz / 1000.0
    for (lo, hi), label in zip(IGNITION_DRIVE_BANDS_KHZ, IGNITION_DRIVE_BAND_LABELS):
        if (lo is None or khz >= lo) and (hi is None or khz < hi):
            return label
    raise AssertionError("bands cover every drive")


def _ignition_trials(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: SyntheticConfig,
                     strength: float, condition: str) -> list:
    """One entry per (decision, framing, trial), built from IGNITION_REPORT_FIELDS only."""
    out = []
    for seed in cfg.market_seeds:
        for split in ("train", "test"):
            for row in outputs[(strength, seed, condition)][split]:
                r = {k: row[k] for k in IGNITION_REPORT_FIELDS}
                for framing in ("yes", "no"):
                    record = r[f"ignition_{framing}"]
                    for t, flag in enumerate(_spread_flags(record, cfg)):
                        out.append({"seed": seed, "split": split, "sequence": int(r["sequence"]),
                                    "framing": framing, "drive_hz": float(r[f"drive_{framing}_hz"]),
                                    "flag": flag, "trial": t, "record": record})
    return out


def ignition_report(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: SyntheticConfig,
                    arms: Sequence[str] = PHASE1_ARMS) -> dict:
    """PRE-STATED 2026-10-12 (revision, point 4). REPORTED ONLY, NEVER GATING.

    Per arm x strength: ignited trials (Wilson 95%, pooled over seeds, with the
    seed-to-seed range), decisions with an ignited framing (training, test),
    presentations by number of ignited trials, and the spread, recruited count,
    recruited mean rate and APL rate of ignited trials; the rise during training
    (ignited trials per 10-decision block of ``sequence``, training against test);
    the drive relationship (fixed framing-drive bands, YES against NO); and the
    per-strength comparison (profit minus learning-off, and profit at s against
    profit at 0; Newcombe 95%). Reads only IGNITION_REPORT_FIELDS, the strength and
    the seed: no score, action, forecast, outcome, reward or P/L field."""
    report: dict = {"note": ("reported only, never gating; ignition fields, drives, sequence and "
                             "strength only (2026-10-12 revision, point 4)"),
                    "definition": {"active_hz": cfg.ignition_active_hz,
                                   "spread_fraction": cfg.ignition_spread_fraction},
                    "by_arm": {}, "per_strength_comparison": {}}
    counts: Dict[Tuple[str, float], Tuple[int, int]] = {}
    try:
        for condition in arms:
            per_strength = {}
            for strength in cfg.signal_strengths:
                trials = _ignition_trials(outputs, cfg, strength, condition)
                k, n = sum(t["flag"] for t in trials), len(trials)
                counts[(condition, strength)] = (k, n)
                seed_rates = []
                for seed in cfg.market_seeds:
                    ts = [t for t in trials if t["seed"] == seed]
                    seed_rates.append(sum(t["flag"] for t in ts) / len(ts) if ts else None)
                presentations: Dict[Tuple[int, str, int], int] = {}
                decisions: Dict[str, set] = {"train": set(), "test": set()}
                all_decisions: Dict[str, set] = {"train": set(), "test": set()}
                for t in trials:
                    key = (t["seed"], t["framing"], t["sequence"])
                    presentations[key] = presentations.get(key, 0) + t["flag"]
                    all_decisions[t["split"]].add((t["seed"], t["sequence"]))
                    if t["flag"]:
                        decisions[t["split"]].add((t["seed"], t["sequence"]))
                by_count = {str(c): sum(v == c for v in presentations.values()) for c in range(1, cfg.trials + 1)}
                ignited = [t for t in trials if t["flag"]]
                detail = {f: _range_summary([t["record"][f][t["trial"]] for t in ignited])
                          for f in ("spread", "n_recruited", "recruited_mean_hz", "apl_hz")}
                blocks = []
                for start in range(0, cfg.markets_per_seed, IGNITION_BLOCK_DECISIONS):
                    bt = [t for t in trials if start <= t["sequence"] < start + IGNITION_BLOCK_DECISIONS]
                    blocks.append({"first_sequence": start,
                                   "split": "train" if start < cfg.train_count else "test",
                                   "ignited_trials": sum(t["flag"] for t in bt), "trials": len(bt)})
                split_rates = {s: _rate(sum(t["flag"] for t in trials if t["split"] == s),
                                        sum(1 for t in trials if t["split"] == s)) for s in ("train", "test")}
                band_of = [_drive_band(t["drive_hz"]) for t in trials]
                bands = {label: _rate(sum(t["flag"] for t, b in zip(trials, band_of) if b == label),
                                      band_of.count(label))
                         for label in IGNITION_DRIVE_BAND_LABELS}
                framing = {f: _rate(sum(t["flag"] for t in trials if t["framing"] == f),
                                    sum(1 for t in trials if t["framing"] == f)) for f in ("yes", "no")}
                rates = [r for r in seed_rates if r is not None]
                per_strength[str(strength)] = {
                    "trials": _rate(k, n),
                    "seed_to_seed_range": [min(rates), max(rates)] if rates else None,
                    "decisions_with_ignited_framing": {
                        s: {"ignited": len(decisions[s]), "total": len(all_decisions[s])} for s in ("train", "test")},
                    "presentations_by_ignited_trials": by_count,
                    "ignited_trials_detail": detail,
                    "rise_during_training": {"blocks": blocks, "training_rate": split_rates["train"],
                                             "test_rate": split_rates["test"],
                                             "note": "descriptive; no trend test"},
                    "drive_bands": bands,
                    "framing": framing,
                }
            report["by_arm"][condition] = per_strength
    except KeyError as missing:
        return {"available": False, "reason": f"ignition record missing ({missing})"}
    for strength in cfg.signal_strengths:
        entry = {}
        if (PROFIT, strength) in counts and (LEARNING_OFF, strength) in counts:
            entry["profit_minus_learning_off"] = newcombe_difference(*counts[(PROFIT, strength)],
                                                                     *counts[(LEARNING_OFF, strength)])
        if strength != NULL_CONTROL_STRENGTH and (PROFIT, NULL_CONTROL_STRENGTH) in counts:
            entry["profit_minus_profit_at_strength0"] = newcombe_difference(
                *counts[(PROFIT, strength)], *counts[(PROFIT, NULL_CONTROL_STRENGTH)])
        report["per_strength_comparison"][str(strength)] = entry
    report["available"] = True
    return report


def phase1_readings(verdict: Mapping, cfg: SyntheticConfig) -> dict:
    """The pre-stated wording of each outcome (Sections 1 and 6 revisions, 2026-10-09;
    ignition revision, 2026-10-12, point 5). Wording only; it decides nothing."""
    out = {}
    for strength in cfg.signal_strengths:
        s = verdict["strengths"][str(strength)]
        if strength == NULL_CONTROL_STRENGTH:
            out[str(strength)] = verdict["null_control"]["interpretation"]
            continue
        if s["passes"]:
            text = ("passes: both lower bounds above zero; the market comparison is a signal edge over the "
                    "best price-only forecast, and the learning-off comparison is 'learning effect, any source'")
        else:
            text = ("does not pass; ambiguous between (a) no learning of the signal and (b) learning-induced "
                    "ignition degrading the readout, which this sweep cannot separate; the ignition report and "
                    "the sensitivity analysis are shown alongside and cannot turn it into a pass")
            if strength in UNDERPOWERED_STRENGTHS:
                text += f"; pre-stated: {UNDERPOWERED_STRENGTHS[strength]}"
        out[str(strength)] = text
    if verdict["null_control"] and verdict["null_control"]["passes"]:
        overall = verdict["null_control"]["interpretation"]
    elif verdict["signal_requirement"] is not None:
        overall = f"signal requirement: {verdict['signal_requirement']:g}"
    else:
        tested = [st for st in cfg.signal_strengths if st != NULL_CONTROL_STRENGTH]
        overall = (f"no signal requirement demonstrated within {min(tested):g}-{max(tested):g}"
                   if tested else "no tested strength")
    out["overall"] = overall
    if verdict["higher_strength_failures"]:
        out["instability"] = ("pre-stated instability: strength(s) "
                              f"{', '.join(f'{x:g}' for x in verdict['higher_strength_failures'])} "
                              "fail after a lower strength passes")
    out["sensitivity"] = ("the exclusion-sensitivity analysis is reported only; it cannot rescue or "
                          "overturn the criterion")
    return out


def evaluate_phase1(outputs: Mapping[Tuple[float, int, str], Mapping], cfg: SyntheticConfig) -> dict:
    """The pre-stated gate and reports from the phase 1 arms only (profit, learning_off).

    Every phase 1 job output must be present; outputs of other arms are ignored. The
    dropped arms are reported as NOT_RUN_NOTE wherever an arm would appear."""
    missing = [condition_job_id(c, s, seed) for s in cfg.signal_strengths for seed in cfg.market_seeds
               for c in PHASE1_ARMS if (s, seed, c) not in outputs]
    if missing:
        raise ValueError(f"{len(missing)} phase 1 job output(s) missing, e.g. {missing[:3]}")
    phase1 = {k: v for k, v in outputs.items() if k[2] in PHASE1_ARMS}
    verdict = evaluate_signal_requirement(phase1, cfg, arms=PHASE1_ARMS)
    not_run = {arm: NOT_RUN_NOTE for arm in DROPPED_ARMS}
    for entry in verdict["strengths"].values():
        entry["circuit"].update(not_run)
        if entry["ignition_exposure"].get("available", True):
            entry["ignition_exposure"].update(not_run)
    if verdict["ignited_training_presentations"].get("available"):
        verdict["ignited_training_presentations"].update(not_run)
    verdict["ignition_report"] = ignition_report(phase1, cfg, PHASE1_ARMS)
    verdict["readings"] = phase1_readings(verdict, cfg)
    return {"evaluation": PHASE1_EVALUATION_LABEL, "arms_evaluated": list(PHASE1_ARMS),
            "arms_not_run": not_run, **verdict}


def results_dir_for(base: Path, cfg: SyntheticConfig) -> Path:
    return Path(base) / f"synthetic_market_{cfg.config_hash()}"
