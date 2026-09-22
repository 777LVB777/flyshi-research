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
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

import numpy as np

from .params import PlasticityParams, RewardParams
from .plasticity import CompartmentMap, PlasticKCMBON
from .mbon_sides import LEFT, side_mask
from .readout import circuit_score, load_dopamine_counts, load_sign_table
from .reward import dopamine_signal, profit_reward

CUE_A, CUE_B = "A", "B"
NOISE_MARGIN = 3.0
LEFT_ONLY_KEY = "circuit_80|left_only"

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

    @classmethod
    def from_dict(cls, d: Mapping) -> "ExperimentConfig":
        """Inverse of to_dict (reads a results directory's config.json)."""
        d = dict(d)
        d["test_seeds"] = tuple(d["test_seeds"])
        d["plasticity"] = PlasticityParams(**d["plasticity"])
        d["reward"] = RewardParams(**d["reward"])
        return cls(**d)

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
    def __init__(self, labels: Sequence[str], cfg: ExperimentConfig,
                 table: Optional[str] = None, aggregation: Optional[str] = None) -> None:
        self.labels = list(labels)
        self.table = load_sign_table(table or cfg.sign_table)
        self.aggregation = aggregation or cfg.aggregation

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


# ---- jobs: the unit of parallel execution --------------------------------------- #
# The protocol splits into independent jobs (spec section 10). Dependencies:
#   pretest:<seed>          none              (2 runs: A then B, baseline weights)
#   train:<condition>       none              (N runs, strictly sequential: each
#                                              presentation sees the weights learned so far)
#   posttest:<cond>:<seed>  train:<cond>      (2 runs, frozen trained weights)
# Every job writes its own file under parts/; assemble() merges them into the same
# pretest.json / condition_<name>.json the sequential run writes, so the verdict code
# never knows how the work was scheduled.
@dataclass(frozen=True)
class Job:
    id: str
    kind: str  # "pretest" | "train" | "posttest"
    condition: Optional[str]
    seed: Optional[int]
    deps: Tuple[str, ...]
    n_runs: int


def plan_jobs(cfg: ExperimentConfig, conditions: Sequence[Condition] = CONDITIONS) -> List[Job]:
    """All jobs of the protocol, longest first within each dependency level."""
    jobs = [Job(f"train:{c.name}", "train", c.name, None, (), cfg.n_training) for c in conditions]
    jobs += [Job(f"pretest:{s}", "pretest", None, s, (), 2) for s in cfg.test_seeds]
    jobs += [Job(f"posttest:{c.name}:{s}", "posttest", c.name, s, (f"train:{c.name}",), 2)
             for c in conditions for s in cfg.test_seeds]
    return jobs


def critical_path_runs(cfg: ExperimentConfig) -> int:
    """Runs on the longest dependency chain: one condition's training + one post-test job."""
    return cfg.n_training + 2


def _write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(path)


def results_dir_for(base: Path, cfg: ExperimentConfig) -> Path:
    return Path(base) / f"first_learning_{cfg.config_hash()}"


class ResultPaths:
    """Where every stage and job writes. Needs no simulator."""

    def __init__(self, results_dir: Path) -> None:
        self.dir = Path(results_dir)
        self.parts = self.dir / "parts"

    def pretest(self) -> Path:
        return self.dir / "pretest.json"

    def condition(self, name: str) -> Path:
        return self.dir / f"condition_{name}.json"

    def checkpoint(self, name: str) -> Path:
        return self.dir / f"checkpoint_{name}.npz"

    def labels(self) -> Path:
        return self.dir / "mbon_labels.json"

    def mbon_ids(self) -> Path:
        """MBON root IDs in rate-vector order; needed by the left-only check."""
        return self.dir / "mbon_ids.json"

    def pretest_part(self, seed: int) -> Path:
        return self.parts / f"pretest_seed_{seed}.json"

    def trained_part(self, name: str) -> Path:
        return self.parts / f"trained_{name}.npz"

    def posttest_part(self, name: str, seed: int) -> Path:
        return self.parts / f"posttest_{name}_seed_{seed}.json"

    def job_output(self, job: Job) -> Path:
        if job.kind == "pretest":
            return self.pretest_part(job.seed)
        if job.kind == "train":
            return self.trained_part(job.condition)
        return self.posttest_part(job.condition, job.seed)

    def job_done(self, job: Job) -> bool:
        """A job is done when its own output exists, or when the merged file that
        contains its result exists (so a finished experiment is never redone)."""
        merged = self.pretest() if job.kind == "pretest" else self.condition(job.condition)
        return merged.exists() or self.job_output(job).exists()


def _save_trained(path: Path, W: np.ndarray, W0: np.ndarray, curve: List[dict],
                  summary: dict) -> None:
    rows = np.flatnonzero(np.any(W != W0, axis=1))
    tmp = path.with_name(path.name + ".partial.npz")
    np.savez_compressed(tmp, rows=rows, values=W[rows], curve=json.dumps(curve),
                        weight_summary=json.dumps(summary))
    tmp.replace(path)


def _load_trained(path: Path, W0: np.ndarray) -> np.ndarray:
    data = np.load(path, allow_pickle=False)
    W = W0.copy()
    W[data["rows"]] = data["values"]
    return W


def assemble(results_dir: Path, cfg: ExperimentConfig,
             conditions: Sequence[Condition] = CONDITIONS) -> List[str]:
    """Merge finished job files into pretest.json / condition_<name>.json (pure file
    work, no simulator). Returns the names of the files written."""
    P = ResultPaths(results_dir)
    written = []
    if not P.pretest().exists() and all(P.pretest_part(s).exists() for s in cfg.test_seeds):
        rows = [json.loads(P.pretest_part(s).read_text()) for s in cfg.test_seeds]
        _write_json(P.pretest(), {"per_seed": rows})
        written.append(P.pretest().name)
    for c in conditions:
        if P.condition(c.name).exists() or not P.trained_part(c.name).exists():
            continue
        if not all(P.posttest_part(c.name, s).exists() for s in cfg.test_seeds):
            continue
        data = np.load(P.trained_part(c.name), allow_pickle=False)
        rows = [json.loads(P.posttest_part(c.name, s).read_text()) for s in cfg.test_seeds]
        out = {"condition": asdict(c), "posttest": {"per_seed": rows},
               "training_curve": json.loads(str(data["curve"])),
               "weight_summary": json.loads(str(data["weight_summary"]))}
        _write_json(P.condition(c.name), out)
        written.append(P.condition(c.name).name)
    return written


# ---- the experiment (restartable) ------------------------------------------------ #
class Experiment:
    def __init__(self, sim: Simulator, cfg: ExperimentConfig, results_base: Path,
                 conditions: Sequence[Condition] = CONDITIONS,
                 log: Callable[[str], None] = print) -> None:
        self.sim, self.cfg, self.conditions, self.log = sim, cfg, tuple(conditions), log
        self.dir = results_dir_for(results_base, cfg)
        self.paths = ResultPaths(self.dir)
        self.paths.parts.mkdir(parents=True, exist_ok=True)
        # config.json and mbon_labels.json: several parallel jobs may write them at once,
        # so each write is atomic and each existing copy must match exactly.
        _write_or_check(self.dir / "config.json", json.dumps(cfg.to_dict(), sort_keys=True, indent=1),
                        "this configuration")
        _write_or_check(self.paths.labels(), json.dumps(list(sim.mbon_labels)),
                        "this simulator's MBON labels")
        # Saved so the preregistered left-only readout can be recomputed from the
        # per-MBON rates in the test rows without rerunning anything.
        _write_or_check(self.paths.mbon_ids(), json.dumps([int(i) for i in sim.mbon_ids]),
                        "this simulator's MBON ids")
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
        self._by_name = {c.name: c for c in self.conditions}

    # -- paths (kept for callers of the sequential API) --
    def pretest_path(self) -> Path:
        return self.paths.pretest()

    def condition_path(self, c: Condition) -> Path:
        return self.paths.condition(c.name)

    def checkpoint_path(self, c: Condition) -> Path:
        return self.paths.checkpoint(c.name)

    # -- sequential run: every job in dependency order, in this one process --
    def run(self) -> dict:
        for s in self.cfg.test_seeds:
            self.run_pretest_seed(s)
        for c in self.conditions:
            if self.condition_path(c).exists():
                self.log(f"condition {c.name}: already done (restartable)")
                continue
            self.train(c)
            for s in self.cfg.test_seeds:
                self.run_posttest_seed(c, s)
        assemble(self.dir, self.cfg, self.conditions)
        return self.finish()

    def finish(self) -> dict:
        return finish(self.dir, self.cfg, self.conditions)

    # -- one job (the parallel launcher runs each in its own process) --
    def run_job(self, job_id: str) -> None:
        job = {j.id: j for j in plan_jobs(self.cfg, self.conditions)}.get(job_id)
        if job is None:
            raise ValueError(f"unknown job {job_id!r}")
        if job.kind == "pretest":
            self.run_pretest_seed(job.seed)
        elif job.kind == "train":
            self.train(self._by_name[job.condition])
        else:
            self.run_posttest_seed(self._by_name[job.condition], job.seed)

    def _test_row(self, weights: np.ndarray, seed: int) -> dict:
        self.sim.set_weights(weights)
        row = {"seed": seed}
        for cue in (CUE_A, CUE_B):
            _, mbon = self.sim.present(stimulus(self.sim, cue, self.cfg), seed,
                                       self.cfg.test_duration_ms, self.cfg.test_trials)
            row[f"score_{cue}"] = self.readout.score(mbon)
            row[f"mbon_{cue}"] = [round(float(x), 4) for x in mbon]
        return row

    def run_pretest_seed(self, seed: int) -> None:
        if self.paths.pretest().exists() or self.paths.pretest_part(seed).exists():
            self.log(f"pre-training test seed {seed}: already done (restartable)")
            return
        self.log(f"pre-training test seed {seed} ...")
        _write_json(self.paths.pretest_part(seed), self._test_row(self.W0, seed))

    def run_posttest_seed(self, c: Condition, seed: int) -> None:
        P = self.paths
        if P.condition(c.name).exists() or P.posttest_part(c.name, seed).exists():
            self.log(f"post-test {c.name} seed {seed}: already done (restartable)")
            return
        if not P.trained_part(c.name).exists():
            raise RuntimeError(f"post-test {c.name} needs train:{c.name} to finish first")
        self.log(f"post-test {c.name} seed {seed} ...")
        W = _load_trained(P.trained_part(c.name), self.W0)
        _write_json(P.posttest_part(c.name, seed), self._test_row(W, seed))

    def train(self, c: Condition) -> None:
        P = self.paths
        if P.condition(c.name).exists() or P.trained_part(c.name).exists():
            self.log(f"training {c.name}: already done (restartable)")
            return
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
            self.log(f"training {c.name}: resuming at presentation {start}/{cfg.n_training}")
        else:
            self.log(f"training {c.name}: {cfg.n_training} presentations ...")
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
        W = np.asarray(net.weights)
        _save_trained(P.trained_part(c.name), W, self.W0, curve,
                      _weight_summary(W, self.W0, self.cue_rows, self.cmap))
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
        return evaluate_results(self.dir, self.cfg, self.conditions)


def _write_or_check(path: Path, text: str, what: str) -> None:
    if path.exists():
        if path.read_text() != text:
            raise RuntimeError(f"{path} does not match {what}")
        return
    tmp = path.with_name(f"{path.name}.{os.getpid()}.partial")
    tmp.write_text(text)
    tmp.replace(path)


def finish(results_dir: Path, cfg: ExperimentConfig,
           conditions: Sequence[Condition] = CONDITIONS) -> dict:
    """Merge finished job files, evaluate, write verdict.json. No simulator needed, so the
    parallel launcher calls this once every job is done."""
    assemble(results_dir, cfg, conditions)
    verdict = evaluate_results(results_dir, cfg, conditions)
    _write_json(Path(results_dir) / "verdict.json", verdict)
    return verdict


def evaluate_results(results_dir: Path, cfg: ExperimentConfig,
                     conditions: Sequence[Condition] = CONDITIONS) -> dict:
    """Verdict from the merged result files alone (no simulator)."""
    P = ResultPaths(results_dir)
    if not P.pretest().exists():
        return {"verdict": INCONCLUSIVE, "reason": "missing pre-training test"}
    pre = json.loads(P.pretest().read_text())["per_seed"]
    posts = {}
    for c in conditions:
        p = P.condition(c.name)
        if not p.exists():
            if c.gating:
                return {"verdict": INCONCLUSIVE, "reason": f"missing condition {c.name}"}
            continue  # a diagnostic that was not run is simply absent from the report
        posts[c.name] = json.loads(p.read_text())["posttest"]["per_seed"]
    out = evaluate_scores(pre, posts, cfg)
    # MBON-vector diagnostic for cue B in the smells-bad condition (not a criterion)
    if "d_punish_a" in posts:
        dist = [float(np.linalg.norm(np.array(a["mbon_B"]) - np.array(b["mbon_B"])))
                for a, b in zip(pre, posts["d_punish_a"])]
        out.setdefault("diagnostics", {})["d_punish_a_cue_B_mbon_vector_change_hz_per_seed"] = dist
    if P.labels().exists():
        labels = json.loads(P.labels().read_text())
        out["readout_sensitivity"] = readout_sensitivity(pre, posts, labels, cfg)
        if P.mbon_ids().exists():
            mbon_ids = json.loads(P.mbon_ids().read_text())
            try:
                left = left_only_sensitivity(pre, posts, labels, mbon_ids, cfg)
            except KeyError as exc:  # e.g. a fake simulator's invented MBON ids
                left = {"unavailable": str(exc)}
            out["readout_sensitivity"][LEFT_ONLY_KEY] = left
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


# ---- readout sensitivity variants (pre-stated in spec section 5b; REPORTED, never gating) ---- #
# Learning itself does not depend on the readout (the rule uses KC rates and the teaching
# signal only), so every variant is computed by re-scoring the MBON rates already saved
# for each test presentation: no extra simulation.
READOUT_VARIANTS: Tuple[Tuple[str, str], ...] = (
    ("circuit_70", "type_mean"),            # CIRCUIT threshold sensitivity
    ("circuit_90", "type_mean"),            # CIRCUIT threshold sensitivity
    ("circuit_80_no_gamma3", "type_mean"),  # MBON08 and MBON09 set to zero weight
    ("strict", "type_mean"),                # robustness: confident behavioural labels only
    ("group", "type_mean"),                 # robustness: group-level behavioural labels
    ("circuit_80", "instance_sum"),         # aggregation variant
)


def variant_key(table: str, aggregation: str) -> str:
    return table if aggregation == "type_mean" else f"{table}|{aggregation}"


def _rescore(rows: Sequence[Mapping], readout: Readout,
             mask: Optional[np.ndarray] = None) -> List[dict]:
    def score(rates: Sequence[float]) -> float:
        r = np.asarray(rates)
        return readout.score(r if mask is None else r[mask])

    return [{"seed": r["seed"], "score_A": score(r["mbon_A"]),
             "score_B": score(r["mbon_B"])} for r in rows]


def left_only_sensitivity(pre: Sequence[Mapping], posts: Mapping[str, Sequence[Mapping]],
                          labels: Sequence[str], mbon_ids: Sequence[int],
                          cfg: ExperimentConfig, side: str = LEFT,
                          sides: Optional[Dict[int, str]] = None) -> dict:
    """The primary readout restricted to one hemisphere's MBON instances.

    Preregistered sensitivity check (decided 2026-09-22); REPORTED, never gating.
    Computed by re-scoring the per-MBON rates already saved for each test
    presentation, so it adds no simulation. Exact here because the teaching signal
    in this test is fixed by the condition, not by the readout.
    """
    mask = side_mask(mbon_ids, side, sides)
    kept = [label for label, keep in zip(list(labels), mask.tolist()) if keep]
    ro = Readout(kept, cfg)
    v = evaluate_scores(_rescore(pre, ro, mask), {n: _rescore(r, ro, mask) for n, r in posts.items()}, cfg)
    cd = (v.get("reported_diagnostics") or {}).get("c_reward_both")
    return {
        "verdict": v["verdict"], "reason": v.get("reason"),
        "sigma": v.get("sigma"), "threshold": v.get("threshold"),
        "conditions": v.get("conditions", {}), "failed_controls": v.get("failed_controls", []),
        "c_reward_both_delta": cd["delta"] if cd else None,
        "n_instances": int(mask.sum()), "side": side,
    }


def readout_sensitivity(pre: Sequence[Mapping], posts: Mapping[str, Sequence[Mapping]],
                        labels: Sequence[str], cfg: ExperimentConfig,
                        variants: Sequence[Tuple[str, str]] = READOUT_VARIANTS) -> dict:
    """The same pre-stated verdict rules, applied with each variant readout. Reported
    alongside the primary (CIRCUIT-80, type mean) verdict; they never change it."""
    out = {}
    for table, agg in variants:
        ro = Readout(labels, cfg, table=table, aggregation=agg)
        v = evaluate_scores(_rescore(pre, ro), {n: _rescore(r, ro) for n, r in posts.items()}, cfg)
        cd = (v.get("reported_diagnostics") or {}).get("c_reward_both")
        out[variant_key(table, agg)] = {
            "verdict": v["verdict"], "reason": v.get("reason"),
            "sigma": v.get("sigma"), "threshold": v.get("threshold"),
            "conditions": v.get("conditions", {}), "failed_controls": v.get("failed_controls", []),
            "c_reward_both_delta": cd["delta"] if cd else None,
        }
    return out


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
    sens = v.get("readout_sensitivity") or {}
    if sens:
        lines.append("readout sensitivity variants (REPORTED ONLY; the verdict above is CIRCUIT-80, type mean):")
        for name, sv in sens.items():
            if "unavailable" in sv:
                lines.append(f"  {name:28s} NOT COMPUTED ({sv['unavailable']})")
                continue
            main = sv["conditions"].get("main", {}).get("delta")
            lines.append(f"  {name:28s} {sv['verdict']}"
                         + (f"  (main delta {main:+.3f}, threshold {sv['threshold']:.3f})" if main is not None else ""))
    return lines
