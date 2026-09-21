"""First learning test: does the circuit learn that cue A is rewarded and cue B is not?

Pre-stated spec: docs/design/first-learning-test.md (written before this code and
before any run). This module is pure numpy: the simulator is passed in, so every
line here can be tested on a fake simulator. The real Brian2 backend lives in
repro/mushroom_body/run_first_learning_test.py.

"Delivering reward" = applying OUR plasticity rule with the PAM teaching signal to
the KC->MBON weights, using the KC pattern measured during that presentation, in the
compartments the dopamine family innervates (connectome-derived map, unverified).
Dopamine is represented ABSTRACTLY as a teaching signal. No dopamine neurons are
stimulated in the network (the simulated brain has no dopamine-dependent plasticity,
so stimulating them could not change a weight and would only fire their fast
synapses, including the suspect DAN->KC excitation), and no dopamine release or
dopamine-neuron activity is simulated. The "stimulation rate" from the reward module
is only a recorded number, UNANCHORED and unused by the network.

Control (c), reward both cues equally, is a REPORTED DIAGNOSTIC, not a gate (demoted
before any run; see the spec's revision history): A and B drive MBON populations of
different composition, so equal reward changes their scores unequally even under
perfectly cue-specific learning. Control (b), reward B instead of A, is the specificity
test.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

import numpy as np

from .params import PlasticityParams, RewardParams
from .plasticity import CompartmentMap, PlasticKCMBON
from .readout import circuit_score, load_dopamine_counts, load_sign_table
from .reward import dopamine_signal, profit_reward

CUE_A, CUE_B = "A", "B"
NOISE_MARGIN = 3.0

# ---- verdicts ------------------------------------------------------------------ #
DEMONSTRATED = "LEARNING DEMONSTRATED"
NOT_DEMONSTRATED = "NOT DEMONSTRATED"
CONFOUNDED = "CONFOUNDED"
INCONCLUSIVE = "INCONCLUSIVE"


# ---- conditions ---------------------------------------------------------------- #
@dataclass(frozen=True)
class Condition:
    """Teaching signal after each cue: None (nothing), +1 (reward -> PAM) or -1
    (punishment -> PPL1). ``plastic=False`` disables the rule entirely (no drift)."""

    name: str
    after_a: Optional[int]
    after_b: Optional[int]
    plastic: bool = True
    description: str = ""
    gating: bool = True  # False: result is reported as a diagnostic and cannot affect the verdict


CONDITIONS: Tuple[Condition, ...] = (
    Condition("main", +1, None, True, "reward A (PAM after A), nothing after B"),
    Condition("a_plasticity_off", None, None, False, "control (a): rule disabled, no drift"),
    Condition("b_reward_b", None, +1, True, "control (b): reward B instead of A"),
    Condition("c_reward_both", +1, +1, True,
              "control (c): reward after both cues equally [REPORTED DIAGNOSTIC, not a gate]",
              gating=False),
    Condition("d_punish_a", -1, None, True, "smells-bad check: PPL1 after A, nothing after B"),
)


GATING_CONDITIONS = tuple(c.name for c in CONDITIONS if c.gating)
DIAGNOSTIC_CONDITIONS = tuple(c.name for c in CONDITIONS if not c.gating)


# ---- configuration (every value an explicit placeholder; see spec section 6) ---- #
@dataclass(frozen=True)
class ExperimentConfig:
    n_training: int = 40
    kc_set_size: int = 100
    kc_set_seed: int = 20260316
    cue_rate_hz: float = 150.0
    test_seeds: Tuple[int, ...] = (20260317, 20260318, 20260319, 20260320, 20260321)
    test_duration_ms: float = 1000.0
    test_trials: int = 5
    train_duration_ms: float = 1000.0
    train_trials: int = 1
    order_seed: int = 20260402
    train_seed_base: int = 20260500
    reward_strength: float = 1.0
    sign_table: str = "circuit_80"
    aggregation: str = "type_mean"
    compartment_threshold_pct: float = 80.0
    plasticity: PlasticityParams = field(default_factory=PlasticityParams)
    reward: RewardParams = field(default_factory=RewardParams)
    prestated: bool = True

    def __post_init__(self) -> None:
        if self.n_training < 2 or self.n_training % 2:
            raise ValueError("n_training must be a positive even number")
        if len(self.test_seeds) < 2 or len(set(self.test_seeds)) != len(self.test_seeds):
            raise ValueError("need at least 2 distinct test seeds (SD needs 2)")
        train_seeds = {self.train_seed_base + k for k in range(self.n_training)}
        if train_seeds & set(self.test_seeds):
            raise ValueError("training seeds overlap test seeds")
        if not 0.0 < self.reward_strength <= 1.0:
            raise ValueError("reward_strength must be in (0, 1]")

    @classmethod
    def smoke(cls) -> "ExperimentConfig":
        """Tiny pipeline check. NOT the pre-stated test."""
        return cls(n_training=2, test_seeds=(20260317, 20260318), test_duration_ms=100.0,
                   test_trials=1, train_duration_ms=100.0, prestated=False)

    def to_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:10]


# ---- simulator interface -------------------------------------------------------- #
class Simulator(Protocol):
    """What the experiment needs from a simulator.

    ``kc_ids``/``mbon_ids``: row/column order of the weight matrix and rate vectors.
    ``mbon_labels``: cell-type label per MBON (same order). ``cue_sets``: {"A": ids,
    "B": ids}. ``baseline_weights()``: dense KC x MBON KC->MBON weights (0 = no
    synapse). ``set_weights(W)``: write W into the network. ``present(rates_by_kc_id,
    seed, duration_ms, n_trials)`` -> (kc_rates, mbon_rates) mean Hz vectors.
    """

    kc_ids: Sequence[int]
    mbon_ids: Sequence[int]
    mbon_labels: Sequence[str]
    cue_sets: Mapping[str, Sequence[int]]

    def baseline_weights(self) -> np.ndarray: ...
    def set_weights(self, weights: np.ndarray) -> None: ...
    def present(self, rates_by_kc_id: Mapping[int, float], seed: int,
                duration_ms: float, n_trials: int) -> Tuple[np.ndarray, np.ndarray]: ...


# ---- plan ------------------------------------------------------------------------ #
def training_order(cfg: ExperimentConfig) -> List[str]:
    """N cues, alternating in pairs: each consecutive pair has one A and one B; which
    goes first is drawn from default_rng(order_seed). Identical for every condition."""
    rng = np.random.default_rng(cfg.order_seed)
    order: List[str] = []
    for _ in range(cfg.n_training // 2):
        order += [CUE_A, CUE_B] if rng.random() < 0.5 else [CUE_B, CUE_A]
    return order


def train_seed(cfg: ExperimentConfig, k: int) -> int:
    return cfg.train_seed_base + k


@dataclass(frozen=True)
class RunCount:
    pretest: int
    per_condition_training: int
    per_condition_posttest: int
    n_conditions: int

    @property
    def total(self) -> int:
        return self.pretest + self.n_conditions * (self.per_condition_training + self.per_condition_posttest)

    def simulated_trial_seconds(self, cfg: ExperimentConfig) -> float:
        test_s = cfg.test_duration_ms / 1000.0 * cfg.test_trials
        train_s = cfg.train_duration_ms / 1000.0 * cfg.train_trials
        return (self.pretest * test_s
                + self.n_conditions * (self.per_condition_training * train_s
                                       + self.per_condition_posttest * test_s))


def run_count(cfg: ExperimentConfig, conditions: Sequence[Condition] = CONDITIONS) -> RunCount:
    tests = 2 * len(cfg.test_seeds)
    return RunCount(tests, cfg.n_training, tests, len(conditions))


# ---- measurement ----------------------------------------------------------------- #
class Readout:
    def __init__(self, labels: Sequence[str], cfg: ExperimentConfig) -> None:
        self.labels = list(labels)
        self.table = load_sign_table(cfg.sign_table)
        self.aggregation = cfg.aggregation

    def score(self, mbon_rates: np.ndarray) -> float:
        return circuit_score(mbon_rates, self.labels, self.table, self.aggregation).score


def stimulus(sim: Simulator, cue: str, cfg: ExperimentConfig) -> Dict[int, float]:
    return {int(k): float(cfg.cue_rate_hz) for k in sim.cue_sets[cue]}


def run_test_stage(sim: Simulator, weights: np.ndarray, readout: Readout,
                   cfg: ExperimentConfig) -> dict:
    """Present A then B at each test seed with ``weights`` frozen."""
    sim.set_weights(weights)
    per_seed = []
    for s in cfg.test_seeds:
        row = {"seed": s}
        for cue in (CUE_A, CUE_B):
            _, mbon = sim.present(stimulus(sim, cue, cfg), s, cfg.test_duration_ms, cfg.test_trials)
            row[f"score_{cue}"] = readout.score(mbon)
            row[f"mbon_{cue}"] = [round(float(x), 4) for x in mbon]
        per_seed.append(row)
    return {"per_seed": per_seed}


def teaching_signal(value: Optional[int], cfg: ExperimentConfig) -> Tuple[Dict[str, float], float]:
    """(strengths for the plasticity rule, RECORDED unanchored "rate" in Hz; never given to the network)."""
    if value is None:
        return {}, 0.0
    sig = dopamine_signal(profit_reward(value * cfg.reward_strength, cfg.reward), cfg.reward)
    return sig.strengths(), sig.rate_hz


def _weight_summary(W: np.ndarray, W0: np.ndarray, rows: Mapping[str, np.ndarray],
                    cmap: CompartmentMap) -> dict:
    out = {}
    for cue, r in rows.items():
        for fam, mask in cmap.masks.items():
            cols = np.flatnonzero(mask > 0)
            base = np.abs(W0[np.ix_(r, cols)]).sum()
            now = np.abs(W[np.ix_(r, cols)]).sum()
            out[f"rows_{cue}_cols_{fam}_fraction_of_baseline"] = (
                float(now / base) if base > 0 else None)
    other = np.ones(W.shape[0], dtype=bool)
    for r in rows.values():
        other[r] = False
    out["other_rows_changed"] = int(np.any(W[other] != W0[other], axis=1).sum())
    return out


# ---- the experiment (restartable) ------------------------------------------------ #
def _write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(path)


def results_dir_for(base: Path, cfg: ExperimentConfig) -> Path:
    return Path(base) / f"first_learning_{cfg.config_hash()}"


class Experiment:
    def __init__(self, sim: Simulator, cfg: ExperimentConfig, results_base: Path,
                 conditions: Sequence[Condition] = CONDITIONS,
                 log: Callable[[str], None] = print) -> None:
        self.sim, self.cfg, self.conditions, self.log = sim, cfg, tuple(conditions), log
        self.dir = results_dir_for(results_base, cfg)
        self.dir.mkdir(parents=True, exist_ok=True)
        cfg_path = self.dir / "config.json"
        cfg_json = json.dumps(cfg.to_dict(), sort_keys=True, indent=1)
        if cfg_path.exists() and cfg_path.read_text() != cfg_json:
            raise RuntimeError(f"{cfg_path} does not match this configuration")
        cfg_path.write_text(cfg_json)
        self.readout = Readout(sim.mbon_labels, cfg)
        self.W0 = np.array(sim.baseline_weights(), dtype=np.float64)
        n_kc, n_mbon = self.W0.shape
        if (n_kc, n_mbon) != (len(sim.kc_ids), len(sim.mbon_ids)):
            raise ValueError("baseline weight shape does not match kc_ids x mbon_ids")
        self.cmap = CompartmentMap.from_dopamine_counts(
            list(sim.mbon_labels), load_dopamine_counts(), cfg.compartment_threshold_pct)
        index = {int(k): i for i, k in enumerate(sim.kc_ids)}
        self.cue_rows = {c: np.array([index[int(k)] for k in sim.cue_sets[c]]) for c in (CUE_A, CUE_B)}
        if set(self.cue_rows[CUE_A]) & set(self.cue_rows[CUE_B]):
            raise ValueError("cue sets overlap")

    # -- stages --
    def pretest_path(self) -> Path:
        return self.dir / "pretest.json"

    def condition_path(self, c: Condition) -> Path:
        return self.dir / f"condition_{c.name}.json"

    def checkpoint_path(self, c: Condition) -> Path:
        return self.dir / f"checkpoint_{c.name}.npz"

    def run(self) -> dict:
        if self.pretest_path().exists():
            self.log("pre-training test: already done (restartable)")
        else:
            self.log("pre-training test ...")
            res = run_test_stage(self.sim, self.W0, self.readout, self.cfg)
            _write_json(self.pretest_path(), res)
        for c in self.conditions:
            if self.condition_path(c).exists():
                self.log(f"condition {c.name}: already done (restartable)")
                continue
            self._run_condition(c)
        verdict = self.evaluate()
        _write_json(self.dir / "verdict.json", verdict)
        return verdict

    def _run_condition(self, c: Condition) -> None:
        cfg = self.cfg
        net = PlasticKCMBON(self.W0, self.cmap, cfg.plasticity)
        order = training_order(cfg)
        curve: List[dict] = []
        start = 0
        ck = self.checkpoint_path(c)
        if ck.exists():
            data = np.load(ck, allow_pickle=False)
            W = self.W0.copy()
            rows = data["rows"]
            W[rows] = data["values"]
            net.load_weights(W)
            start = int(data["next_k"])
            curve = json.loads(str(data["curve"]))
            self.log(f"condition {c.name}: resuming at presentation {start}/{cfg.n_training}")
        else:
            self.log(f"condition {c.name}: training {cfg.n_training} presentations ...")
        for k in range(start, cfg.n_training):
            cue = order[k]
            self.sim.set_weights(net.weights)
            kc, mbon = self.sim.present(stimulus(self.sim, cue, cfg), train_seed(cfg, k),
                                        cfg.train_duration_ms, cfg.train_trials)
            value = c.after_a if cue == CUE_A else c.after_b
            strengths, rate = teaching_signal(value, cfg)
            if c.plastic:
                net.record_decision(f"p{k}", kc, "YES")
                net.resolve(f"p{k}", strengths)
            curve.append({"k": k, "cue": cue, "score": round(self.readout.score(mbon), 4),
                          "teaching": strengths if c.plastic else {},
                          "dopamine_rate_hz_unanchored": rate if c.plastic else 0.0,
                          "n_eligible_kc": int(np.sum(kc > cfg.plasticity.kc_active_threshold_hz))})
            self._checkpoint(c, net.weights, k + 1, curve)
        post = run_test_stage(self.sim, net.weights, self.readout, cfg)
        out = {"condition": asdict(c), "posttest": post, "training_curve": curve,
               "weight_summary": _weight_summary(np.asarray(net.weights), self.W0, self.cue_rows, self.cmap)}
        _write_json(self.condition_path(c), out)
        if ck.exists():
            ck.unlink()

    def _checkpoint(self, c: Condition, W: np.ndarray, next_k: int, curve: List[dict]) -> None:
        W = np.asarray(W)
        rows = np.flatnonzero(np.any(W != self.W0, axis=1))
        ck = self.checkpoint_path(c)
        tmp = ck.with_name(ck.name + ".partial.npz")
        np.savez_compressed(tmp, rows=rows, values=W[rows], next_k=next_k, curve=json.dumps(curve))
        tmp.replace(ck)

    # -- verdict --
    def evaluate(self) -> dict:
        pre = json.loads(self.pretest_path().read_text())["per_seed"]
        posts = {}
        for c in self.conditions:
            p = self.condition_path(c)
            if not p.exists():
                if c.gating:
                    return {"verdict": INCONCLUSIVE, "reason": f"missing condition {c.name}"}
                continue  # a diagnostic that was not run is simply absent from the report
            posts[c.name] = json.loads(p.read_text())["posttest"]["per_seed"]
        out = evaluate_scores(pre, posts, self.cfg)
        # MBON-vector diagnostic for cue B in the smells-bad condition (not a criterion)
        if "d_punish_a" in posts:
            dist = [float(np.linalg.norm(np.array(a["mbon_B"]) - np.array(b["mbon_B"])))
                    for a, b in zip(pre, posts["d_punish_a"])]
            out["diagnostics"]["d_punish_a_cue_B_mbon_vector_change_hz_per_seed"] = dist
        return out


# ---- verdict logic (pure; pre-stated in spec sections 4-5) ----------------------- #
def _sd(x: Sequence[float]) -> float:
    return float(np.std(np.asarray(x, dtype=np.float64), ddof=1))


def evaluate_scores(pre: Sequence[Mapping], posts: Mapping[str, Sequence[Mapping]],
                    cfg: ExperimentConfig) -> dict:
    """``pre``/``posts[cond]``: per-seed dicts with score_A, score_B (same seed order)."""
    seeds = [r["seed"] for r in pre]
    for name, rows in posts.items():
        if [r["seed"] for r in rows] != seeds:
            raise ValueError(f"condition {name}: test seeds differ from the pre-training test")
    d_pre = [r["score_A"] - r["score_B"] for r in pre]
    b_pre = [r["score_B"] for r in pre]
    m_pre, sigma, sigma_b = float(np.mean(d_pre)), _sd(d_pre), _sd(b_pre)
    T, T_b = NOISE_MARGIN * sigma, NOISE_MARGIN * sigma_b
    base = {"prestated_test": cfg.prestated, "m_pre": m_pre, "sigma": sigma, "threshold": T,
            "sigma_B": sigma_b, "threshold_B": T_b, "conditions": {}, "diagnostics": {},
            "reported_diagnostics": {}}

    def bad(x: float) -> bool:
        return not math.isfinite(x) or x <= 0.0

    if bad(sigma) or bad(sigma_b):
        return {**base, "verdict": INCONCLUSIVE,
                "reason": "noise measurement failed: sigma or sigma_B is zero or not finite"}

    deltas = {}
    for name, rows in posts.items():
        d = [r["score_A"] - r["score_B"] for r in rows]
        deltas[name] = float(np.mean(d)) - m_pre
        base["diagnostics"][f"{name}_paired_changes"] = [x - y for x, y in zip(d, d_pre)]
        base["diagnostics"][f"{name}_cue_B_score_change"] = float(np.mean([r["score_B"] for r in rows])) - float(np.mean(b_pre))

    crit = {  # the GATING conditions; control (c) is deliberately not here
        "main": lambda: deltas["main"] >= T,
        "a_plasticity_off": lambda: abs(deltas["a_plasticity_off"]) < T,
        "b_reward_b": lambda: deltas["b_reward_b"] <= -T,
        "d_punish_a": lambda: abs(base["diagnostics"]["d_punish_a_cue_B_score_change"]) < T_b,
    }
    missing = [n for n in crit if n not in posts]
    if missing:
        return {**base, "verdict": INCONCLUSIVE, "reason": f"missing conditions {missing}"}
    for name in crit:
        base["conditions"][name] = {"delta": deltas[name], "pass": bool(crit[name]())}
    failed_controls = [n for n in crit if n != "main" and not base["conditions"][n]["pass"]]
    if not base["conditions"]["main"]["pass"]:
        verdict = NOT_DEMONSTRATED
    elif failed_controls:
        verdict = CONFOUNDED
    else:
        verdict = DEMONSTRATED

    # Control (c): REPORTED, never gating. If learning is cue-specific and the readout roughly
    # additive, rewarding both cues should change A-B by about (main + reward-B), not by zero.
    if "c_reward_both" in deltas:
        dc = deltas["c_reward_both"]
        pred = deltas["main"] + deltas["b_reward_b"]
        base["reported_diagnostics"]["c_reward_both"] = {
            "delta": dc, "delta_over_sigma": dc / sigma, "exceeds_3_sigma": bool(abs(dc) >= T),
            "additive_prediction_main_plus_b": pred, "residual_from_additive_prediction": dc - pred,
        }
    else:
        base["reported_diagnostics"]["c_reward_both"] = None  # not run
    return {**base, "verdict": verdict, "failed_controls": failed_controls}


def summary_lines(v: dict) -> List[str]:
    lines = []
    if not v.get("prestated_test", True):
        lines.append("!!! NOT THE PRE-STATED TEST (smoke/override config); exploratory only !!!")
    if "sigma" in v:
        lines.append(f"pre-training A-B: mean {v['m_pre']:.3f}, noise sigma {v['sigma']:.3f} "
                     f"-> threshold 3 sigma = {v['threshold']:.3f}; cue-B sigma {v['sigma_B']:.3f}")
    for name, c in v.get("conditions", {}).items():
        lines.append(f"  {name:18s} delta = {c['delta']:+.3f}  {'pass' if c['pass'] else 'FAIL'}")
    cd = (v.get("reported_diagnostics") or {}).get("c_reward_both")
    if cd:
        lines.append(f"  c_reward_both      delta = {cd['delta']:+.3f} ({cd['delta_over_sigma']:+.2f} sigma)  "
                     f"REPORTED ONLY, not a criterion; additive prediction (main + b) "
                     f"{cd['additive_prediction_main_plus_b']:+.3f}, residual {cd['residual_from_additive_prediction']:+.3f}")
    lines.append(f"VERDICT: {v['verdict']}")
    if v.get("failed_controls"):
        lines.append(f"failed controls: {', '.join(v['failed_controls'])}")
    if v.get("reason"):
        lines.append(f"reason: {v['reason']}")
    return lines
