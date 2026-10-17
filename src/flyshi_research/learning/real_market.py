"""Phase 2: the circuit on real Polymarket markets (Design A). Pure numpy.

Pre-stated in docs/design/phase2-preregistration.md (2026-10-16), from
docs/design/phase2-design.md, Sections 6, 7 and 10. Nothing here makes a network
request or imports Brian2; the simulator is injected exactly as in the synthetic
sweep, and the per-market decision loop IS the synthetic sweep's
(``synthetic_market.decision_loop``): the same encoder (left-only pools, unbalanced
Option B, mirrored NO framing), readout, locked learning parameters, teaching signal
and ignition tracking. Only the markets differ.

Pipeline, each step blind to what it must not see:

1. ``assemble_chains``: 40 disjoint chains of 70 training + 180 test markets, taken
   in the fill plan's pre-stated hash order (IDs and dates only, no outcome).
2. ``isotonic_comparator.fit_comparator`` on every TRAINING market of the market
   file, frozen with a SHA-256 before any job runs.
3. ``run_chain``: one (chain, arm) job of 500 runs: 70 training decisions with
   plasticity, then 180 held-out decisions with the weights frozen.
4. ``evaluate``: the pre-stated gate, null control and reported-only analyses.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.evaluation.calibration import fit_and_apply_calibration
from flyshi_research.evaluation.isotonic_comparator import FrozenComparator
from flyshi_research.evaluation.metrics import bootstrap_confidence_interval
from flyshi_research.simulator import Market

from . import synthetic_market as sm
from .encoder import KCEncoder
from .params import OPTION_B_UNBALANCED

# ---- arms and design (pre-stated 2026-10-16) ------------------------------------- #
PROFIT = sm.PROFIT
LEARNING_OFF = sm.LEARNING_OFF
#: the profit arm taught with outcomes permuted across its chain's training markets
NULL_PERMUTED = "null_permuted"
ARMS = (PROFIT, LEARNING_OFF, NULL_PERMUTED)
N_CHAINS = 40
#: the synthetic sweep's chain shape: markets 0-69 train, 70-249 test (int(250 * 0.28) = 70)
TRAIN_PER_CHAIN = sm.SyntheticConfig().train_count
TEST_PER_CHAIN = sm.SyntheticConfig().test_count
RUNS_PER_JOB = 2 * (TRAIN_PER_CHAIN + TEST_PER_CHAIN)
#: presentation seed = base + chain * 1000 + index (the same in every arm)
SIMULATION_SEED_BASE = 20280000
#: null control: numpy default_rng([NULL_PERMUTATION_SEED, chain]).permutation(70)
NULL_PERMUTATION_SEED = 20261016
#: bootstrap seeds: gate +0 (vs comparator) and +100 (vs learning_off); null +200;
#: >= $100k subset +300/+400; ignition sensitivity +500/+600
BOOTSTRAP_SEED = 20261016
BOOTSTRAP_RESAMPLES = 2000
CONFIDENCE_LEVEL = 0.95
HIGH_VOLUME_USDC = 100_000.0
#: 80% power, two-sided alpha 0.05: z(0.975) + z(0.80), rounded as in phase2-design.md, Section 7
MDE_FACTOR = 2.80
CHAINS_FORMAT = "flyshi.phase2.chains/v1"
assert (TRAIN_PER_CHAIN, TEST_PER_CHAIN) == (70, 180)


def locked_config() -> sm.SyntheticConfig:
    """The synthetic sweep's decided configuration, unchanged: encoder, readout,
    plasticity, reward, presentation, decision margin, exploration seed, ignition
    thresholds and costs. Its signal-sweep fields are not used here."""
    return sm.SyntheticConfig()


def simulation_seed(chain: int, index: int) -> int:
    if not 0 <= index < 1000:
        raise ValueError("index must be < 1000")
    return SIMULATION_SEED_BASE + chain * 1000 + index


# ---- market file ----------------------------------------------------------------- #
@dataclass(frozen=True)
class RealMarket:
    market_id: str
    market: Market
    decision_time: str
    closed_time: str
    final_volume: Optional[float]


def load_market_file(path: Path) -> Tuple[Dict[str, RealMarket], Dict[str, RealMarket], dict]:
    """``(train, test, header)`` from the build step's output, keyed by market ID."""
    payload = json.loads(Path(path).read_text())
    if payload.get("format") != "flyshi.simulator.Market/v1":
        raise ValueError("not a flyshi.simulator.Market/v1 market file")

    def to_real(r: Mapping) -> RealMarket:
        meta = r["meta"]
        m = Market(latent_probability=math.nan, quote=float(r["quote"]), outcome=int(r["outcome"]),
                   signal=float(r["signal"]), recent_change=float(r["recent_change"]),
                   time_to_resolution=float(r["time_to_resolution"]), liquidity=float(r["liquidity"]),
                   sequence=int(r["sequence"]))
        fv = meta.get("final_volume")
        return RealMarket(str(meta["market_id"]), m, meta["decision_time"], meta["closed_time"],
                          None if fv is None else float(fv))

    train = {x.market_id: x for x in map(to_real, payload["train"])}
    test = {x.market_id: x for x in map(to_real, payload["test"])}
    if set(train) & set(test):
        raise ValueError("a market is in both the training and the test list")
    header = {k: payload.get(k) for k in ("frozen_list_sha256", "split", "counts")}
    return train, test, header


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- 1. chains ------------------------------------------------------------------- #
def assemble_chains(plan: Mapping, train_closed: Mapping[str, str], test_decided: Mapping[str, str],
                    n_chains: int = N_CHAINS, train_per_chain: int = TRAIN_PER_CHAIN,
                    test_per_chain: int = TEST_PER_CHAIN) -> dict:
    """Disjoint chains from the fill plan (FINAL 2026-10-16, 10.11 (b), step 5).

    Each pool's usable IDs are taken in the plan's hash order (sha256 of
    ``SAMPLE_ORDER_SEED|id``), keeping those present in the market file. Chain c gets
    ranks [70c, 70c + 70) of the training pool and [180c, 180c + 180) of the test
    pool; the remaining built markets are the reserve. Within a chain, training
    markets are presented in resolution order and test markets in decision-time
    order (Section 5, rule 8; ties by market ID). Inputs are IDs, the plan's order,
    close times and decision times only: no outcome and no price."""
    out_counts = {}
    ranked = {}
    for pool, present, need in (("train", train_closed, n_chains * train_per_chain),
                                ("test", test_decided, n_chains * test_per_chain)):
        usable = [str(i) for i in plan["pools"][pool]["usable_ids"]]
        built = [i for i in usable if i in present]
        if len(built) < need:
            raise ValueError(f"{pool} pool: {len(built)} built markets, {need} needed")
        ranked[pool] = built[:need]
        out_counts[pool] = {"usable_in_plan": len(usable), "built": len(built), "in_chains": need,
                            "reserve": len(built) - need, "usable_not_built": len(usable) - len(built)}
    chains = []
    for c in range(n_chains):
        tr = ranked["train"][c * train_per_chain:(c + 1) * train_per_chain]
        te = ranked["test"][c * test_per_chain:(c + 1) * test_per_chain]
        chains.append({"chain": c,
                       "train": sorted(tr, key=lambda i: (train_closed[i], i)),
                       "test": sorted(te, key=lambda i: (test_decided[i], i))})
    return {"format": CHAINS_FORMAT, "frozen_sha256": plan.get("frozen_sha256"),
            "sample_seed": plan.get("seed"), "n_chains": n_chains, "train_per_chain": train_per_chain,
            "test_per_chain": test_per_chain, "counts": out_counts, "chains": chains}


def chains_from_market_file(plan: Mapping, train: Mapping[str, RealMarket],
                            test: Mapping[str, RealMarket], **kw) -> dict:
    """``assemble_chains`` given the loaded market file; passes only the dates on."""
    return assemble_chains(plan, {i: m.closed_time for i, m in train.items()},
                           {i: m.decision_time for i, m in test.items()}, **kw)


def chain_markets(chains: Mapping, chain: int, train: Mapping[str, RealMarket],
                  test: Mapping[str, RealMarket]) -> Tuple[List[RealMarket], List[RealMarket]]:
    entry = chains["chains"][chain]
    if entry["chain"] != chain:
        raise ValueError("chains file is out of order")
    return [train[i] for i in entry["train"]], [test[i] for i in entry["test"]]


# ---- 3. one (chain, arm) job ----------------------------------------------------- #
def null_permutation(chain: int, n: int = TRAIN_PER_CHAIN) -> np.ndarray:
    """Pre-stated: training position i is taught with the outcome of training
    position perm[i] of the same chain."""
    return np.random.default_rng([NULL_PERMUTATION_SEED, chain]).permutation(n)


def run_chain(sim: sm.Simulator, cfg: sm.SyntheticConfig, chain: int, train: Sequence[RealMarket],
              test: Sequence[RealMarket], arm: str, *, kc_sides: Mapping[int, str]) -> dict:
    """One job: 70 training decisions then 180 held-out decisions, through the
    synthetic sweep's own decision loop. ``kc_sides`` is required (left-only pools,
    guarded before anything is presented).

    ``null_permuted`` is the profit arm with the TRAINING outcomes permuted within
    the chain: its teaching signal and its own Platt calibrator see only the
    permuted outcomes. Every record keeps the true outcome, which scores the test."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    if len(train) != TRAIN_PER_CHAIN or len(test) != TEST_PER_CHAIN:
        raise ValueError(f"a chain is {TRAIN_PER_CHAIN} training and {TEST_PER_CHAIN} test markets")
    markets = [r.market for r in (*train, *test)]
    teaching, teach_as, perm = None, None, None
    taught_outcomes = [m.outcome for m in markets[:TRAIN_PER_CHAIN]]
    if arm == NULL_PERMUTED:
        perm = null_permutation(chain)
        taught_outcomes = [train[int(j)].market.outcome for j in perm]
        teaching = [replace(m, outcome=o) for m, o in zip(markets, taught_outcomes)] + markets[TRAIN_PER_CHAIN:]
        teach_as = PROFIT
    records, plasticity = sm.decision_loop(
        sim, cfg, markets, TRAIN_PER_CHAIN, PROFIT if arm == NULL_PERMUTED else arm, kc_sides=kc_sides,
        seed_for=lambda index: simulation_seed(chain, index), exploration_key=chain,
        teach_as=teach_as, teaching_markets=teaching)
    ids = [r.market_id for r in (*train, *test)]
    for record, market_id in zip(records, ids):
        record["market_id"] = market_id
    train_rows, test_rows = records[:TRAIN_PER_CHAIN], records[TRAIN_PER_CHAIN:]
    if arm == NULL_PERMUTED:
        for row, o in zip(train_rows, taught_outcomes):
            row["teaching_outcome"] = int(o)
    calibrated = fit_and_apply_calibration([r["raw_probability"] for r in train_rows], taught_outcomes,
                                           [r["raw_probability"] for r in test_rows])
    for row, probability in zip(test_rows, calibrated.calibrated_test):
        row["calibrated_probability"] = float(probability)
    return {"arm": arm, "chain": chain, "drift_rate": plasticity.drift_rate,
            "null_permutation": None if perm is None else [int(x) for x in perm],
            "mbon_ids": [int(i) for i in sim.mbon_ids], "mbon_labels": list(sim.mbon_labels),
            "train": train_rows, "test": test_rows, "calibrator": asdict(calibrated.scaler)}


@dataclass(frozen=True)
class RealJob:
    id: str
    chain: int
    condition: str
    deps: Tuple[str, ...] = ()
    n_runs: int = RUNS_PER_JOB


def job_id(arm: str, chain: int) -> str:
    return f"real:{arm}:{chain:02d}"


def plan_jobs(n_chains: int = N_CHAINS) -> List[RealJob]:
    """40 chains x 3 arms = 120 jobs of 500 runs (60,000 runs), chain by chain."""
    return [RealJob(job_id(arm, c), c, arm) for c in range(n_chains) for arm in ARMS]


# ---- 4. evaluation --------------------------------------------------------------- #
def mde(sigma_d: float, n_test: int) -> float:
    """Minimum detectable mean paired Brier difference at 80% power, two-sided 0.05."""
    return MDE_FACTOR * sigma_d / math.sqrt(n_test)


def _ci(values: np.ndarray, offset: int) -> dict:
    return asdict(bootstrap_confidence_interval(values, np.mean, confidence_level=CONFIDENCE_LEVEL,
                                                n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED + offset))


def _aligned_test(outputs: Mapping[Tuple[int, str], Mapping], chains: Mapping) -> dict:
    """Test vectors in chain order; refuses unless every arm saw exactly the chain's
    markets with identical quotes and outcomes."""
    missing = [job_id(a, e["chain"]) for e in chains["chains"] for a in ARMS if (e["chain"], a) not in outputs]
    if missing:
        raise ValueError(f"{len(missing)} job output(s) missing, e.g. {missing[:3]}")
    vec: Dict[str, list] = {a: [] for a in ARMS}
    ids, y, q, ignited = [], [], [], {a: [] for a in ARMS}
    actions: Dict[str, list] = {a: [] for a in ARMS}
    for e in chains["chains"]:
        rows = {a: outputs[(e["chain"], a)]["test"] for a in ARMS}
        for a in ARMS:
            if [r["market_id"] for r in rows[a]] != list(e["test"]):
                raise ValueError(f"chain {e['chain']}, arm {a}: test markets differ from the chains file")
            if outputs[(e["chain"], a)]["arm"] != a or outputs[(e["chain"], a)]["chain"] != e["chain"]:
                raise ValueError(f"job output for chain {e['chain']}, arm {a} is labelled otherwise")
        base = rows[PROFIT]
        for a in ARMS:
            if [(r["quote"], r["outcome"]) for r in rows[a]] != [(r["quote"], r["outcome"]) for r in base]:
                raise ValueError(f"chain {e['chain']}: arms disagree on test quotes or outcomes")
            vec[a].extend(r["calibrated_probability"] for r in rows[a])
            ignited[a].extend(sm._ignited(r) for r in rows[a])
            actions[a].extend(r["action"] for r in rows[a])
        ids.extend(r["market_id"] for r in base)
        y.extend(r["outcome"] for r in base)
        q.extend(r["quote"] for r in base)
    return {"ids": ids, "y": np.asarray(y, float), "q": np.asarray(q, float),
            "p": {a: np.asarray(v, float) for a, v in vec.items()},
            "ignited": {a: np.asarray(v, bool) for a, v in ignited.items()}, "actions": actions}


GROSS_PNL_LABEL = "gross, before fees and spread, not achievable as stated"


def gross_pnl(actions: Sequence[str], quotes: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Per-market profit of one contract at the decision-time price, with NO fee and NO
    spread: YES earns outcome - price, NO earns price - outcome, ABSTAIN earns 0."""
    a = np.asarray(actions)
    return np.where(a == "YES", outcomes - quotes, np.where(a == "NO", quotes - outcomes, 0.0))


def _gross_pnl_report(v: Mapping) -> dict:
    out: dict = {"label": GROSS_PNL_LABEL, "note": "reported only, never gating (pre-stated 2026-10-16)",
                 "per_arm": {}}
    for i, a in enumerate(ARMS):
        pnl = gross_pnl(v["actions"][a], v["q"], v["y"])
        acts = np.asarray(v["actions"][a])
        out["per_arm"][a] = {"total": float(pnl.sum()), "per_market": float(pnl.mean()),
                             "per_market_ci": _ci(pnl, 700 + i),
                             "trades": int(np.sum(acts != "ABSTAIN")), "abstentions": int(np.sum(acts == "ABSTAIN")),
                             "markets": int(pnl.size)}
    return out


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _gate(d_comp: np.ndarray, d_off: np.ndarray, d_null: Optional[np.ndarray], offset: int) -> dict:
    comp, off = _ci(d_comp, offset), _ci(d_off, offset + 100)
    out = {"n": int(d_comp.size), "profit_improvement_vs_comparator": comp,
           "profit_improvement_vs_learning_off": off,
           "both_lower_bounds_above_zero": bool(comp["lower"] > 0.0 and off["lower"] > 0.0)}
    if d_null is not None:
        out["null_improvement_vs_comparator"] = _ci(d_null, offset + 200)
    return out


def evaluate(outputs: Mapping[Tuple[int, str], Mapping], chains: Mapping, comparator: FrozenComparator,
             final_volume: Mapping[str, Optional[float]], comparator_training_ids: Sequence[str]) -> dict:
    """The pre-stated Phase 2 verdict (docs/design/phase2-preregistration.md).

    GATE: on the 7,200 held-out markets, the profit arm's paired Brier improvement
    over the frozen comparator AND over learning_off both have 95% percentile
    bootstrap lower bounds strictly above zero (2,000 resamples, by market; one
    market per event). NULL CONTROL: if null_permuted's improvement over the frozen
    comparator has its lower bound above zero, the verdict is NULL CONTROL FAILED.
    Reported only, never gating: the realised sigma_d and MDE, the >= $100k subset,
    ignition exposure and the sensitivity analysis excluding ignited test markets."""
    v = _aligned_test(outputs, chains)
    leaked = set(v["ids"]) & {str(i) for i in comparator_training_ids}
    if leaked:
        raise ValueError(f"{len(leaked)} test market(s) were in the comparator's training set")
    y, q, p = v["y"], v["q"], v["p"]
    comp = comparator.predict(q)
    sq = {a: (p[a] - y) ** 2 for a in ARMS}
    d_comp = (comp - y) ** 2 - sq[PROFIT]
    d_off = sq[LEARNING_OFF] - sq[PROFIT]
    d_null = (comp - y) ** 2 - sq[NULL_PERMUTED]
    gate = _gate(d_comp, d_off, d_null, 0)
    passes = gate["both_lower_bounds_above_zero"]
    null_fails = gate["null_improvement_vs_comparator"]["lower"] > 0.0
    n = int(y.size)
    sigma = {"vs_comparator": float(np.std(d_comp, ddof=1)), "vs_learning_off": float(np.std(d_off, ddof=1))}
    realised = {k: {"sigma_d": s, "mde": mde(s, n)} for k, s in sigma.items()}

    hv = np.array([(final_volume.get(i) or 0.0) >= HIGH_VOLUME_USDC for i in v["ids"]])
    subset: dict = {"note": "reported only, never gating (pre-stated 2026-10-16)",
                    "threshold_usdc": HIGH_VOLUME_USDC, "n": int(hv.sum())}
    if hv.sum() >= 2:
        g = _gate(d_comp[hv], d_off[hv], None, 300)
        subset.update(g, available=True,
                      realised_mde={"vs_comparator": mde(float(np.std(d_comp[hv], ddof=1)), int(hv.sum())),
                                    "vs_learning_off": mde(float(np.std(d_off[hv], ddof=1)), int(hv.sum()))})
    else:
        subset.update(available=False, reason="fewer than two markets")

    excluded = v["ignited"][PROFIT] | v["ignited"][LEARNING_OFF]
    keep = ~excluded
    sens: dict = {"note": ("reported only, never gating; excluded markets are not random, and learning from "
                           "ignited training presentations cannot be removed"),
                  "n_excluded": int(excluded.sum()), "n_remaining": int(keep.sum())}
    if keep.sum() >= 2:
        sens.update(_gate(d_comp[keep], d_off[keep], None, 500), available=True)
    else:
        sens.update(available=False, reason="fewer than two markets remain")
    exposure = {}
    for a in ARMS:
        rows = [r for e in chains["chains"] for s in ("train", "test") for r in outputs[(e["chain"], a)][s]]
        exposure[a] = {"decisions": len(rows),
                       "train_decisions_with_ignited_framing": sum(
                           sm._ignited(r) for e in chains["chains"] for r in outputs[(e["chain"], a)]["train"]),
                       "test_decisions_with_ignited_framing": int(v["ignited"][a].sum())}

    verdict = {
        "prestated": "docs/design/phase2-preregistration.md (2026-10-16)",
        "success": bool(passes and not null_fails),
        "gate_passes": bool(passes),
        "n_test_markets": n,
        "comparator": {"choice": comparator.choice, "cv_brier_raw": comparator.cv_brier_raw,
                       "cv_brier_calibrated": comparator.cv_brier_calibrated, "n_train": comparator.n_train,
                       "sha256": comparator.sha256()},
        "gate": gate,
        "null_control": {"passes": bool(null_fails), "interpretation": (
            "NULL CONTROL FAILED: a pipeline problem, not a finding; no edge is reported" if null_fails
            else "null control did not pass, as expected")},
        "brier_test": {**{a: _brier(p[a], y) for a in ARMS}, "comparator": _brier(comp, y),
                       "raw_price": _brier(q, y)},
        "realised": realised,
        "limitations": list(LIMITATIONS),
        "gross_pnl": _gross_pnl_report(v),
        "high_volume_subset": subset,
        "ignition_exposure": {"note": "reported only, never gating", **exposure},
        "sensitivity_excluding_ignited": sens,
    }
    verdict["readings"] = readings(verdict)
    return verdict


#: stated with every verdict (decided 2026-10-16)
LIMITATIONS = (
    "per-series caps were not applied: markets in the same series may be correlated, so the bootstrap "
    "intervals over markets may be somewhat narrow",
    "final volume is known only afterwards and selects markets that drew attention (phase2-design.md, 10.6)",
    "markets that closed before their decision time are excluded, which under-represents early resolutions",
    "the universe is what Polymarket's /markets/keyset serves; archived markets on other endpoints are not covered",
)


def readings(verdict: Mapping) -> dict:
    """Pre-stated wording; it decides nothing."""
    mde_c = verdict["realised"]["vs_comparator"]["mde"]
    mde_o = verdict["realised"]["vs_learning_off"]["mde"]
    if verdict["null_control"]["passes"]:
        overall = verdict["null_control"]["interpretation"]
    elif verdict["gate_passes"]:
        overall = ("passes: on held-out real markets the circuit's Brier score beats both the frozen "
                   "training-calibrated price and its own learning-off control (both 95% lower bounds above zero)")
    else:
        overall = (f"does not pass: no detectable edge larger than the minimum detectable effect at the realised "
                   f"sigma_d (about {mde_c:.4f} over the comparator, {mde_o:.4f} over learning_off, in Brier "
                   "units). This is not evidence of no edge.")
    return {"overall": overall,
            "comparisons": {"vs_comparator": "edge over the market price, calibrated on training markets only",
                            "vs_learning_off": "learning effect, any source"},
            "reported_only": ("the >= $100k subset, gross P&L, ignition exposure and the ignited-market "
                              "sensitivity analysis cannot turn a non-pass into a pass or overturn a pass")}


# ---- total-drive check (arithmetic only, no simulation) ---------------------------- #
#: presentations above this per-framing drive count as high-drive (the synthetic sweep's 2.12% line)
HIGH_DRIVE_KHZ = 60.0
LOW_DRIVE_KHZ = 30.0


def framing_drives(markets: Sequence[Market], cfg: Optional[sm.SyntheticConfig] = None) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Per-framing total drive (sum of presented KC rates, Hz) of each market's YES
    and NO stimuli under the locked encoder (unbalanced Option B, the five feature
    pools), plus clip counts per feature. Drive does not depend on which KCs form a
    pool, so any 800 integer IDs give the exact figures."""
    cfg = cfg or locked_config()
    enc = KCEncoder(np.arange(1, 5 * cfg.encoder.pool_size + cfg.encoder.balance_pool_size + 1),
                    params=cfg.encoder)
    yes, no, clips = [], [], {}
    for m in markets:
        pair = enc.option_b_stimuli(sm.market_features(m), variant=OPTION_B_UNBALANCED)
        yes.append(float(np.sum(pair.yes.rates_hz)))
        no.append(float(np.sum(pair.no.rates_hz)))
        for e in pair.yes.clip_events:
            clips[f"{e.feature}_{e.direction}"] = clips.get(f"{e.feature}_{e.direction}", 0) + 1
    return np.asarray(yes), np.asarray(no), clips


def drive_profile(markets: Sequence[Market], cfg: Optional[sm.SyntheticConfig] = None) -> dict:
    yes, no, clips = framing_drives(markets, cfg)
    both = np.concatenate([yes, no]) / 1000.0
    diff = np.abs(yes - no) / 1000.0
    bands = {}
    for (lo, hi), label in zip(sm.IGNITION_DRIVE_BANDS_KHZ, sm.IGNITION_DRIVE_BAND_LABELS):
        sel = np.ones(both.size, bool)
        if lo is not None:
            sel &= both >= lo
        if hi is not None:
            sel &= both < hi
        bands[label] = int(sel.sum())
    return {"markets": len(markets), "presentations": int(both.size),
            "drive_khz": {"min": float(both.min()), "p01": float(np.percentile(both, 1)),
                          "median": float(np.median(both)), "p99": float(np.percentile(both, 99)),
                          "max": float(both.max())},
            "fraction_above_60_khz": float(np.mean(both > HIGH_DRIVE_KHZ)),
            "fraction_below_30_khz": float(np.mean(both < LOW_DRIVE_KHZ)),
            "yes_minus_no_khz": {"median_abs": float(np.median(diff)), "max_abs": float(diff.max())},
            "presentations_by_drive_band": bands, "clipped_markets_by_feature": clips}


def synthetic_reference(cfg: Optional[sm.SyntheticConfig] = None) -> dict:
    """The validated condition: every market of the decided synthetic sweep
    (all strengths x seeds x 250 markets), encoded exactly as it ran."""
    from flyshi_research.simulator import generate_signal_markets

    cfg = cfg or locked_config()
    markets = [m for s in cfg.signal_strengths for seed in cfg.market_seeds
               for m in generate_signal_markets(cfg.markets_per_seed, seed, s, cfg.price_deviation)]
    return drive_profile(markets, cfg)


def drive_check(train: Sequence[Market], test: Sequence[Market], cfg: Optional[sm.SyntheticConfig] = None) -> dict:
    """Compare real markets' encoder drive with the validated synthetic range
    (phase2-design.md, Section 3). Reads features only, never an outcome; runs no
    simulation. The owner signs off before any run."""
    ref = synthetic_reference(cfg)
    lo, hi = ref["drive_khz"]["min"], ref["drive_khz"]["max"]
    out = {"note": "arithmetic only, no simulation; features only, no outcome",
           "validated_reference": ref, "splits": {}}
    for name, markets in (("train", train), ("test", test)):
        prof = drive_profile(markets, cfg)
        yes, no, _ = framing_drives(markets, cfg)
        both = np.concatenate([yes, no]) / 1000.0
        prof["outside_validated_range"] = {"below": int(np.sum(both < lo)), "above": int(np.sum(both > hi))}
        prof["more_high_drive_than_validated"] = prof["fraction_above_60_khz"] > ref["fraction_above_60_khz"]
        prof["more_low_drive_than_validated"] = prof["fraction_below_30_khz"] > ref["fraction_below_30_khz"]
        out["splits"][name] = prof
    flags = [f"{s}: {k}" for s, p in out["splits"].items()
             for k in ("more_high_drive_than_validated", "more_low_drive_than_validated") if p[k]]
    flags += [f"{s}: {n} presentation(s) outside the validated {lo:.1f}-{hi:.1f} kHz"
              for s, p in out["splits"].items() for n in [sum(p["outside_validated_range"].values())] if n]
    out["flags"] = flags
    out["sign_off"] = ("REQUIRED before any run (phase2-design.md, Section 3): "
                       + ("the flags above put presentations outside the validated condition" if flags
                          else "no flag raised; the drive is within the validated condition"))
    return out
