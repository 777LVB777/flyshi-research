"""First learning test: ignition re-check. A DIAGNOSTIC (is_a_validation: false), no verdict.

Pre-stated spec: docs/design/first-learning-ignition-recheck-diagnostic.md (written
2026-10-12, before this code and before any run).

Re-runs the first learning test's exact protocol (config hash 6fea97ac91, all five
conditions, original seeds) with the unchanged backend and experiment code, plus an
opt-in per-trial recorder (``FastRunnerSimulator.trial_sink``) that saves per-trial
spike counts of every KC, MBON and APL neuron. Scores are computed by the unchanged
code, so they must reproduce the saved results exactly; ``--analyze`` checks that
FIRST and refuses to compute any ignition figure if one value differs.

Writes ONLY under results/first_learning_ignition_recheck_20261012/ (the experiment
code puts its files in that base's first_learning_6fea97ac91/ subfolder). It never
writes to the original results folder and never writes verdict.json.

  --dry-run   plan; simulates nothing
  --run       the 260 Brian2 runs, sequential, one process (restartable)
  --analyze   validity check, then (only if valid) the pre-stated ignition report; no Brian2

Run on the Mac (from the repository root):
  caffeinate -i .venv-shiu/bin/python repro/mushroom_body/run_first_learning_ignition_recheck.py --run
  .venv-shiu/bin/python repro/mushroom_body/run_first_learning_ignition_recheck.py --analyze
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.learning import first_learning as fl
from flyshi_research.learning import synthetic_market as sm

HERE = Path(__file__).resolve().parent
RESULTS_ROOT = HERE / "results"
EXPECTED_HASH = "6fea97ac91"
ORIGINAL_DIR = RESULTS_ROOT / f"first_learning_{EXPECTED_HASH}"
RECHECK_BASE = RESULTS_ROOT / "first_learning_ignition_recheck_20261012"
IDS_PATH = HERE / "neuron_ids_783.json"
SUMMARY_NAME = "ignition_recheck_summary.json"
SPEC = "docs/design/first-learning-ignition-recheck-diagnostic.md"

SPLIT_HIGH = (20260317, 20260319, 20260321)  # cue-B change about +181 in b_reward_b
SPLIT_LOW = (20260318, 20260320)             # cue-B change about +102
LINEARITY_TOL_HZ = 1e-6
EXPLAIN_REDUCTION, PARTLY_REDUCTION = 0.75, 0.25


# --------------------------------------------------------------------------- #
# paths and configuration guards
# --------------------------------------------------------------------------- #
def recheck_config() -> fl.ExperimentConfig:
    cfg = fl.ExperimentConfig()
    if cfg.config_hash() != EXPECTED_HASH:
        raise SystemExit(f"config hash {cfg.config_hash()} != {EXPECTED_HASH}: not the first learning test")
    return cfg


def check_base(base: Path) -> Path:
    base = Path(base).resolve()
    if base == RESULTS_ROOT.resolve() or base == ORIGINAL_DIR.resolve() or ORIGINAL_DIR.resolve() in base.parents:
        raise SystemExit(f"refusing results base {base}: it would write into or beside the original results")
    return base


def trials_dir(base: Path) -> Path:
    return Path(base) / "trials"


def trial_file(base: Path, job_id: str, seed: int, cue: str) -> Path:
    return trials_dir(base) / f"{job_id.replace(':', '_')}__seed_{seed}__cue_{cue}.npz"


# --------------------------------------------------------------------------- #
# recorder (the simulator's trial_sink)
# --------------------------------------------------------------------------- #
class TrialRecorder:
    """Saves one presentation's per-trial spike counts (KC, MBON, APL) to its own file.
    Never alters what the simulator returns."""

    def __init__(self, base: Path, cue_sets: Mapping[str, Sequence[int]], kc_brian: np.ndarray,
                 mbon_brian: np.ndarray, apl_brian: np.ndarray) -> None:
        self.base = Path(base)
        self.cue_by_ids = {frozenset(int(k) for k in ids): cue for cue, ids in cue_sets.items()}
        self.kc, self.mbon, self.apl = kc_brian, mbon_brian, apl_brian
        self.job: Optional[str] = None
        trials_dir(self.base).mkdir(parents=True, exist_ok=True)

    def __call__(self, rates_by_kc_id: Mapping[int, float], seed: int, duration_ms: float,
                 n_trials: int, counts: np.ndarray) -> None:
        if self.job is None:
            raise RuntimeError("recorder has no job set")
        cue = self.cue_by_ids.get(frozenset(int(k) for k in rates_by_kc_id))
        if cue is None:
            raise RuntimeError("presented KC set matches neither cue")
        path = trial_file(self.base, self.job, seed, cue)
        tmp = path.with_name(path.name + ".partial.npz")
        np.savez_compressed(tmp, kc=counts[:, self.kc].astype(np.uint16),
                            mbon=counts[:, self.mbon].astype(np.uint16),
                            apl=counts[:, self.apl].astype(np.uint16),
                            seed=seed, cue=cue, job=self.job, duration_ms=duration_ms, n_trials=n_trials)
        tmp.replace(path)


def write_meta(base: Path, sim, apl_ids: Sequence[int], kc_sides: Mapping[int, str]) -> None:
    meta = {"kc_ids": [int(k) for k in sim.kc_ids], "mbon_ids": [int(m) for m in sim.mbon_ids],
            "mbon_labels": list(sim.mbon_labels), "apl_ids": [int(a) for a in apl_ids],
            "cue_sets": {c: [int(k) for k in ids] for c, ids in sim.cue_sets.items()},
            "kc_sides": {str(k): s for k, s in kc_sides.items()},
            "spec": SPEC, "is_a_validation": False, "has_pass_criterion": False}
    text = json.dumps(meta, sort_keys=True)
    path = Path(base) / "meta.json"
    if path.exists() and path.read_text() != text:
        raise RuntimeError(f"{path} does not match this simulator")
    path.write_text(text)


# --------------------------------------------------------------------------- #
# the run (Brian2)
# --------------------------------------------------------------------------- #
def run(base: Path) -> None:
    cfg = recheck_config()
    base = check_base(base)
    sys.path.insert(0, str(HERE))
    from run_first_learning_test import FastRunnerSimulator  # imports Brian2 lazily inside

    payload = json.loads(IDS_PATH.read_text())
    kc_sides = {int(r["root_id"]): str(r["side"]) for r in payload["kenyon_cells"]["records"]}
    apl_ids = [int(r["root_id"]) for r in payload["apl_neurons"]["records"]]

    sim = FastRunnerSimulator(cfg)
    flyid2i = sim.bundle["flyid2i"]
    write_meta(base, sim, apl_ids, kc_sides)
    rec = TrialRecorder(base, sim.cue_sets, sim._kc_brian, sim._mbon_brian,
                        np.array([flyid2i[a] for a in apl_ids]))
    sim.trial_sink = rec
    exp = fl.Experiment(sim, cfg, base)
    if exp.dir.resolve() == ORIGINAL_DIR.resolve():
        raise SystemExit("refusing: experiment directory is the original results folder")
    for s in cfg.test_seeds:
        rec.job = f"pretest:{s}"
        exp.run_pretest_seed(s)
    for c in fl.CONDITIONS:
        rec.job = f"train:{c.name}"
        exp.train(c)
        for s in cfg.test_seeds:
            rec.job = f"posttest:{c.name}:{s}"
            exp.run_posttest_seed(c, s)
    written = fl.assemble(exp.dir, cfg)  # merge job files only; finish()/verdict.json never called
    print(f"[recheck] done; merged {written or 'nothing new'}; now run --analyze")


# --------------------------------------------------------------------------- #
# analysis (no Brian2)
# --------------------------------------------------------------------------- #
def _load_set(d: Path) -> dict:
    out = {"pretest": json.loads((d / "pretest.json").read_text())["per_seed"], "conditions": {}}
    for c in fl.CONDITIONS:
        out["conditions"][c.name] = json.loads((d / f"condition_{c.name}.json").read_text())
    return out


def validity_mismatches(orig: dict, new: dict) -> List[str]:
    """Every value the pre-statement requires to match exactly; empty list = valid."""
    bad: List[str] = []

    def cmp_rows(where: str, a: Sequence[Mapping], b: Sequence[Mapping]) -> None:
        if [r["seed"] for r in a] != [r["seed"] for r in b]:
            bad.append(f"{where}: seed order differs")
            return
        for ra, rb in zip(a, b):
            for k in ("score_A", "score_B", "mbon_A", "mbon_B"):
                if ra[k] != rb[k]:
                    bad.append(f"{where} seed {ra['seed']} {k}: {_short(ra[k])} vs {_short(rb[k])}")

    cmp_rows("pretest", orig["pretest"], new["pretest"])
    for name, oc in orig["conditions"].items():
        nc = new["conditions"][name]
        cmp_rows(f"posttest {name}", oc["posttest"]["per_seed"], nc["posttest"]["per_seed"])
        if len(oc["training_curve"]) != len(nc["training_curve"]):
            bad.append(f"training {name}: curve length differs")
        for ea, eb in zip(oc["training_curve"], nc["training_curve"]):
            for k in ("k", "cue", "score", "teaching", "n_eligible_kc"):
                if ea[k] != eb[k]:
                    bad.append(f"training {name} k={ea['k']} {k}: {ea[k]} vs {eb[k]}")
        if oc["weight_summary"] != nc["weight_summary"]:
            bad.append(f"weight_summary {name}: {oc['weight_summary']} vs {nc['weight_summary']}")
    return bad


def _short(x) -> str:
    return f"[{len(x)} values]" if isinstance(x, list) else repr(x)


def presentation_record(npz: Mapping, meta: Mapping, readout: fl.Readout,
                        kc_sides: Mapping[int, str], scfg: sm.SyntheticConfig) -> dict:
    """Per-trial ignition (sweep definition) and per-trial scores of one presentation."""
    dur_s = float(npz["duration_ms"]) / 1000.0
    kc_rates = np.asarray(npz["kc"], dtype=float) / dur_s
    mbon_rates = np.asarray(npz["mbon"], dtype=float) / dur_s
    apl_rates = np.asarray(npz["apl"], dtype=float) / dur_s
    cue = str(npz["cue"])
    ign = sm.ignition_record(meta["kc_ids"], kc_rates, apl_rates, meta["cue_sets"][cue], kc_sides, scfg)
    flags = [s is not None and s > scfg.ignition_spread_fraction for s in ign["spread"]]
    return {"job": str(npz["job"]), "seed": int(npz["seed"]), "cue": cue,
            "trial_scores": [readout.score(m) for m in mbon_rates],
            "ignited": flags, "ignition": ign}


def adjusted_score(p: Mapping) -> Optional[float]:
    """Mean per-trial score over NON-ignited trials; None if every trial ignited."""
    kept = [s for s, f in zip(p["trial_scores"], p["ignited"]) if not f]
    return float(np.mean(kept)) if kept else None


def _delta(pre: Mapping[int, Mapping[str, float]], post: Mapping[int, Mapping[str, float]],
           seeds: Sequence[int]) -> Tuple[float, float]:
    """(delta, threshold): fl.evaluate_scores' definitions from per-seed {A, B} scores."""
    d_pre = [pre[s]["A"] - pre[s]["B"] for s in seeds]
    d_post = [post[s]["A"] - post[s]["B"] for s in seeds]
    return float(np.mean(d_post)) - float(np.mean(d_pre)), fl.NOISE_MARGIN * float(np.std(d_pre, ddof=1))


def _scores(stage: Mapping[Tuple[int, str], Mapping], seeds: Sequence[int], adjust: bool,
            fallback: Mapping[int, Mapping[str, float]]) -> Tuple[Dict[int, Dict[str, Optional[float]]], List[str]]:
    out, uncomputable = {}, []
    for s in seeds:
        out[s] = {}
        for cue in (fl.CUE_A, fl.CUE_B):
            p = stage[(s, cue)]
            if adjust and any(p["ignited"]):
                v = adjusted_score(p)
                if v is None:
                    uncomputable.append(f"seed {s} cue {cue}")
                out[s][cue] = v
            else:
                out[s][cue] = fallback[s][cue]
    return out, uncomputable


def main_reading(pre_stage, post_stage, pre_scores, post_scores, seeds, threshold_orig) -> dict:
    n_post = sum(sum(post_stage[(s, c)]["ignited"]) for s in seeds for c in (fl.CUE_A, fl.CUE_B))
    n_pre = sum(sum(pre_stage[(s, c)]["ignited"]) for s in seeds for c in (fl.CUE_A, fl.CUE_B))
    delta, _ = _delta(pre_scores, post_scores, seeds)
    out = {"ignited_trials_posttest": n_post, "ignited_trials_pretest": n_pre, "delta": delta}
    if n_post == 0 and n_pre == 0:
        out["reading"] = "no test-time cascade in main; cascades contribute nothing to delta_main"
        return out
    adj_pre, u1 = _scores(pre_stage, seeds, True, pre_scores)
    adj_post, u2 = _scores(post_stage, seeds, True, post_scores)
    if u1 or u2:
        lo, hi = _bounded_delta(adj_pre, adj_post, seeds)
        out.update(not_computable=u1 + u2, delta_adjusted_bounds=[lo, hi],
                   reading=f"not computable for {', '.join(u1 + u2)} (all 5 trials ignited); "
                           f"delta_main(adjusted) bounded within [{lo:.3f}, {hi:.3f}]")
        return out
    d_adj, t_adj = _delta(adj_pre, adj_post, seeds)
    out.update(delta_adjusted=d_adj, shift=delta - d_adj, threshold_adjusted=t_adj,
               threshold_original=threshold_orig,
               reading=f"cascades move delta_main by {delta - d_adj:+.3f}"
                       + ("; the main result does not depend on them" if d_adj >= threshold_orig else ""))
    return out


def _bounded_delta(adj_pre, adj_post, seeds) -> Tuple[float, float]:
    """Fill each uncomputable score with the min/max of the other seeds' scores for the same
    cue and stage; return the smallest and largest resulting delta."""
    def fills(stage):
        options = {}
        for s in seeds:
            for cue in (fl.CUE_A, fl.CUE_B):
                if stage[s][cue] is None:
                    others = [stage[o][cue] for o in seeds if o != s and stage[o][cue] is not None]
                    options[(s, cue)] = (min(others), max(others)) if others else (math.nan, math.nan)
        return options

    fp, fq = fills(adj_pre), fills(adj_post)
    deltas = []
    for pick in range(2 ** (len(fp) + len(fq))):
        pre = {s: dict(v) for s, v in adj_pre.items()}
        post = {s: dict(v) for s, v in adj_post.items()}
        bits = pick
        for (s, cue), (lo, hi) in fp.items():
            pre[s][cue] = hi if bits & 1 else lo
            bits >>= 1
        for (s, cue), (lo, hi) in fq.items():
            post[s][cue] = hi if bits & 1 else lo
            bits >>= 1
        deltas.append(_delta(pre, post, seeds)[0])
    return float(min(deltas)), float(max(deltas))


def split_reading(pre_stage, post_stage, pre_scores, post_scores) -> dict:
    def b_change(pre, post, s):
        return post[s][fl.CUE_B] - pre[s][fl.CUE_B]

    def gap(pre, post):
        return (float(np.mean([b_change(pre, post, s) for s in SPLIT_HIGH]))
                - float(np.mean([b_change(pre, post, s) for s in SPLIT_LOW])))

    ign = {s: sum(post_stage[(s, fl.CUE_B)]["ignited"]) for s in SPLIT_HIGH + SPLIT_LOW}
    low_n, high_n = sum(ign[s] for s in SPLIT_LOW), sum(ign[s] for s in SPLIT_HIGH)
    g = gap(pre_scores, post_scores)
    out = {"cue_B_post_ignited_trials_by_seed": ign, "gap": g}
    if all(ign[s] == 5 for s in SPLIT_LOW) and high_n == 0:
        out["reading"] = ("the split coincides exactly with test-time cascades; "
                          "consistent with, but not proof of, a cascade explanation")
        return out
    if high_n > low_n:
        out["reading"] = "do not explain as hypothesised (cascades are in seeds 17/19/21, not 18/20)"
        return out
    if low_n == 0 or low_n <= high_n:
        out["reading"] = "do not explain (condition (i) fails)"
        return out
    seeds = SPLIT_HIGH + SPLIT_LOW
    adj_pre, u1 = _scores(pre_stage, seeds, True, pre_scores)
    adj_post, u2 = _scores(post_stage, seeds, True, post_scores)
    if u1 or u2:
        out.update(not_computable=u1 + u2,
                   reading="not computable (all 5 trials ignited in a presentation, but not the exact-confound pattern)")
        return out
    g_adj = gap(adj_pre, adj_post)
    reduction = 1.0 - abs(g_adj) / abs(g) if g else math.nan
    out.update(gap_adjusted=g_adj, reduction=reduction,
               reading=("test-time cascades explain the split" if reduction >= EXPLAIN_REDUCTION else
                        "test-time cascades partly explain the split" if reduction >= PARTLY_REDUCTION else
                        "do not explain (reduction under 25%)"))
    return out


def analyze(base: Path) -> int:
    cfg = recheck_config()
    base = check_base(base)
    new_dir = fl.results_dir_for(base, cfg)
    summary = {"kind": "diagnostic", "spec": SPEC, "is_a_validation": False,
               "has_pass_criterion": False, "verdict": None}
    missing = [p for p in [new_dir / "pretest.json"] + [new_dir / f"condition_{c.name}.json" for c in fl.CONDITIONS]
               if not p.exists()]
    if missing:
        print(f"[recheck] incomplete: missing {[p.name for p in missing]}; finish --run first")
        return 2
    orig, new = _load_set(ORIGINAL_DIR), _load_set(new_dir)
    bad = validity_mismatches(orig, new)
    summary["valid"] = not bad
    summary["mismatches"] = bad
    out_path = base / SUMMARY_NAME
    if bad:
        out_path.write_text(json.dumps(summary, indent=1))
        print(f"[recheck] VALIDITY CHECK FAILED: {len(bad)} value(s) differ from the saved first learning test.")
        print("Pre-stated rule: STOP. No ignition figure is computed or interpreted.")
        for line in bad[:50]:
            print("  " + line)
        return 3
    print("[recheck] validity check passed: every pre-/post-test score and every other "
          "required value matches the saved files exactly")

    meta = json.loads((base / "meta.json").read_text())
    kc_sides = {int(k): v for k, v in meta["kc_sides"].items()}
    readout = fl.Readout(meta["mbon_labels"], cfg)
    scfg = sm.SyntheticConfig()
    seeds = list(cfg.test_seeds)

    def load(job: str, seed: int, cue: str) -> dict:
        path = trial_file(base, job, seed, cue)
        if not path.exists():
            raise SystemExit(f"[recheck] missing per-trial file {path.name}; re-run --run")
        with np.load(path, allow_pickle=False) as z:
            return presentation_record(z, meta, readout, kc_sides, scfg)

    pre_stage = {(s, c): load(f"pretest:{s}", s, c) for s in seeds for c in (fl.CUE_A, fl.CUE_B)}
    pre_scores = {r["seed"]: {"A": r["score_A"], "B": r["score_B"]} for r in new["pretest"]}
    linearity = [abs(float(np.mean(pre_stage[(s, c)]["trial_scores"])) - pre_scores[s][c])
                 for s in seeds for c in (fl.CUE_A, fl.CUE_B)]
    order = fl.training_order(cfg)
    report: dict = {"pretest": _stage_table(pre_stage, pre_scores, seeds), "conditions": {}}
    stages = {}
    for c in fl.CONDITIONS:
        post_stage = {(s, cue): load(f"posttest:{c.name}:{s}", s, cue) for s in seeds for cue in (fl.CUE_A, fl.CUE_B)}
        post_scores = {r["seed"]: {"A": r["score_A"], "B": r["score_B"]}
                       for r in new["conditions"][c.name]["posttest"]["per_seed"]}
        linearity += [abs(float(np.mean(post_stage[(s, cue)]["trial_scores"])) - post_scores[s][cue])
                      for s in seeds for cue in (fl.CUE_A, fl.CUE_B)]
        training = []
        for k in range(cfg.n_training):
            p = load(f"train:{c.name}", fl.train_seed(cfg, k), order[k])
            if any(p["ignited"]):
                training.append({"k": k, "cue": order[k], "spread": p["ignition"]["spread"],
                                 "n_recruited": p["ignition"]["n_recruited"]})
        stages[c.name] = (post_stage, post_scores)
        report["conditions"][c.name] = {"posttest": _stage_table(post_stage, post_scores, seeds),
                                        "training_cascades": training}
    max_lin = float(max(linearity))
    report["linearity_max_abs_diff_hz"] = max_lin
    readings = {}
    if max_lin < LINEARITY_TOL_HZ:
        t_orig = fl.NOISE_MARGIN * float(np.std([pre_scores[s]["A"] - pre_scores[s]["B"] for s in seeds], ddof=1))
        readings["main"] = main_reading(pre_stage, stages["main"][0], pre_scores, stages["main"][1],
                                        seeds, t_orig)
        for name in ("b_reward_b", "c_reward_both"):
            readings[name] = split_reading(pre_stage, stages[name][0], pre_scores, stages[name][1])
    else:
        readings["note"] = f"adjusted figures not computable: linearity difference {max_lin:g} Hz >= {LINEARITY_TOL_HZ:g}"
    summary.update(report=report, readings=readings)
    out_path.write_text(json.dumps(summary, indent=1))
    print("\n".join(summary_lines(summary)))
    print(f"[recheck] summary written to {out_path}")
    return 0


def _stage_table(stage, scores, seeds) -> List[dict]:
    rows = []
    for s in seeds:
        for cue in (fl.CUE_A, fl.CUE_B):
            p = stage[(s, cue)]
            ig = p["ignition"]
            rows.append({
                "seed": s, "cue": cue, "score": scores[s][cue], "ignited_trials": int(sum(p["ignited"])),
                "trial_scores": p["trial_scores"], "ignited": p["ignited"],
                "ignited_trial_detail": [
                    {"trial": t, "spread": ig["spread"][t], "spread_left": ig["spread_left"][t],
                     "spread_right": ig["spread_right"][t], "n_recruited": ig["n_recruited"][t],
                     "recruited_mean_hz": ig["recruited_mean_hz"][t], "apl_hz": ig["apl_hz"][t]}
                    for t, f in enumerate(p["ignited"]) if f],
                "score_ignited_trials_mean": (float(np.mean([x for x, f in zip(p["trial_scores"], p["ignited"]) if f]))
                                              if any(p["ignited"]) else None),
                "score_non_ignited_trials_mean": adjusted_score(p),
            })
    return rows


def summary_lines(summary: Mapping) -> List[str]:
    rep = summary["report"]
    lines = ["FIRST LEARNING TEST IGNITION RE-CHECK (DIAGNOSTIC; no verdict)",
             f"linearity (presentation score vs mean of trial scores): max |diff| {rep['linearity_max_abs_diff_hz']:.2e} Hz"]

    def table(title, rows):
        lines.append(title)
        for r in rows:
            det = "; ".join(f"t{d['trial']} spread {d['spread']:.3f} n {d['n_recruited']}" for d in r["ignited_trial_detail"])
            ig = r["score_ignited_trials_mean"]
            lines.append(f"  seed {r['seed']} cue {r['cue']}: ignited {r['ignited_trials']}/5  score {r['score']:.3f}"
                         + (f"  [ignited mean {ig:.3f}, non-ignited mean {r['score_non_ignited_trials_mean']}]  {det}"
                            if r["ignited_trials"] else ""))

    table("pre-test:", rep["pretest"])
    for name, c in rep["conditions"].items():
        table(f"post-test {name}:", c["posttest"])
        tc = c["training_cascades"]
        lines.append(f"  training cascades: {len(tc)}" + (
            " (" + ", ".join(f"k={t['k']} cue {t['cue']} max spread {max(x for x in t['spread'] if x is not None):.3f}"
                             for t in tc) + ")" if tc else ""))
    for name, r in summary["readings"].items():
        lines.append(f"READING {name}: {r['reading'] if isinstance(r, dict) else r}")
    return lines


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def plan_lines(base: Path) -> List[str]:
    cfg = recheck_config()
    rc = fl.run_count(cfg)
    return [
        "First learning test ignition re-check: PLAN (dry run; nothing is simulated)",
        f"  DIAGNOSTIC, is_a_validation false, no verdict; spec {SPEC}",
        f"  config hash {cfg.config_hash()} (original protocol, unchanged); conditions "
        + ", ".join(c.name for c in fl.CONDITIONS),
        f"  runs: {rc.total} ({rc.simulated_trial_seconds(cfg):g} simulated trial-seconds), sequential, one process",
        f"  writes only under {base}; original {ORIGINAL_DIR.name} is read by --analyze only",
        "  estimated wall-clock on this Mac: 80-90 min (original run: 78 min; not measured for this runner)",
    ]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Print the plan; simulate nothing.")
    g.add_argument("--run", action="store_true", help="Run the 260 Brian2 presentations (restartable).")
    g.add_argument("--analyze", action="store_true", help="Validity check, then the ignition report; no Brian2.")
    p.add_argument("--results-base", type=Path, default=RECHECK_BASE)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    base = check_base(args.results_base)
    if args.dry_run:
        print("\n".join(plan_lines(base)))
        return 0
    if args.run:
        run(base)
        return 0
    return analyze(base)


if __name__ == "__main__":
    sys.exit(main())
