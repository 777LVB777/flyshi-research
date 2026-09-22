"""Plain-language summary of the first learning test, for pasting to collaborators.

Reads a results directory (config.json, pretest.json, condition_*.json, verdict.json)
and prints one self-contained summary: the verdict, what each control showed, the
readout sensitivity variants, and the key numbers. It never simulates anything and
never writes into the results directory; with --out it writes the text to a file.

  .venv-shiu/bin/python repro/mushroom_body/report_first_learning.py
  .venv-shiu/bin/python repro/mushroom_body/report_first_learning.py --results-dir PATH --out report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from flyshi_research.learning import first_learning as fl

HERE = Path(__file__).resolve().parent
RESULTS_BASE = HERE / "results"

MEANING = {
    fl.DEMONSTRATED: "the rewarded cue's score rose beyond noise, and every gating control "
                     "behaved as real, cue-specific learning predicts.",
    fl.NOT_DEMONSTRATED: "after reward, the difference between cue A and cue B did not rise by "
                         "at least 3 noise units (3σ), so this test found no learning.",
    fl.CONFOUNDED: "the main effect appeared, but at least one control failed, so the effect "
                   "cannot be attributed to cue-specific learning.",
    fl.INCONCLUSIVE: "the test could not reach a verdict (missing results or a failed noise "
                     "measurement); this is not evidence either way.",
}

GATES = {
    "main": ("Main: reward after cue A",
             "cue A minus cue B should RISE by at least 3σ"),
    "a_plasticity_off": ("Control (a): learning rule switched off",
                         "the same presentations without learning should move A−B by LESS than 3σ "
                         "(checks that repetition alone does not produce the effect)"),
    "b_reward_b": ("Control (b): reward after cue B instead",
                   "A−B should FALL by at least 3σ (checks the effect follows the rewarded cue)"),
    "d_punish_a": ("Control (d): punishment after cue A (\"smells bad\")",
                   "cue B's own score should change by LESS than 3σ_B (checks that changing "
                   "A does not spill over onto B)"),
}

VARIANT_TEXT = {
    "circuit_70": "CIRCUIT rule at 70% (threshold sensitivity)",
    "circuit_90": "CIRCUIT rule at 90% (threshold sensitivity)",
    "circuit_80_no_gamma3": "CIRCUIT-80 with MBON08 and MBON09 (γ3) set to zero",
    "strict": "STRICT: only confidently labelled MBONs (robustness)",
    "group": "GROUP: group-level behavioural labels (robustness)",
    "circuit_80|instance_sum": "CIRCUIT-80 summed per neuron instead of per type",
    fl.LEFT_ONLY_KEY: "CIRCUIT-80 over left-hemisphere MBONs only (hemisphere sensitivity)",
}


def _sig(x: float, sigma: Optional[float]) -> str:
    return f" ({x / sigma:+.1f}σ)" if sigma else ""


def report_lines(results_dir: Path) -> List[str]:
    d = Path(results_dir)
    cfg_path = d / "config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"no config.json in {d}: not a first-learning results directory")
    cfg = fl.ExperimentConfig.from_dict(json.loads(cfg_path.read_text()))
    vpath = d / "verdict.json"
    v = json.loads(vpath.read_text()) if vpath.exists() else fl.evaluate_results(d, cfg)
    paths = fl.ResultPaths(d)
    jobs = fl.plan_jobs(cfg)
    n_done = sum(paths.job_done(j) for j in jobs)

    L: List[str] = []
    L.append("# First learning test: summary")
    L.append("")
    if not cfg.prestated:
        L.append("**WARNING: this is NOT the pre-stated test (smoke/override settings). "
                 "Exploratory only; do not cite as a result.**")
        L.append("")
    L.append(f"**Verdict: {v['verdict']}**: {MEANING.get(v['verdict'], '')}")
    if v.get("reason"):
        L.append(f"Reason: {v['reason']}.")
    if not vpath.exists():
        L.append("(verdict.json not written yet; the verdict above was computed from the files present)")
    L.append("")
    L.append("## What was tested")
    L.append(f"Two groups of {cfg.kc_set_size} Kenyon cells (cue A, cue B; selection seed "
             f"{cfg.kc_set_seed}) were stimulated at {cfg.cue_rate_hz:g} Hz in the Shiu et al. "
             "(2024) fly-brain model. The score is the CIRCUIT-80 readout of the mushroom-body "
             "output neurons (per-type mean; higher = more approach-like). Cue A's and cue B's "
             f"scores were measured at {len(cfg.test_seeds)} test seeds before training and again "
             f"after {cfg.n_training} training presentations ({cfg.n_training // 2} of each cue) "
             "in each condition. \"Reward\" is applied by our own learning rule to the "
             "KC→MBON synapses in the compartments reward-type dopamine neurons innervate; "
             "no dopamine neurons are stimulated (dopamine is represented abstractly).")
    L.append(f"Results: `{d}`; jobs finished: {n_done} of {len(jobs)}; "
             f"config hash {cfg.config_hash()}.")
    L.append("")
    if "sigma" in v:
        L.append("## Noise and threshold")
        L.append(f"Before training, A−B averaged {v['m_pre']:+.2f} with a seed-to-seed standard "
                 f"deviation σ = {v['sigma']:.2f}. A change counts only if it reaches 3σ = "
                 f"{v['threshold']:.2f}. For cue B alone σ_B = {v['sigma_B']:.2f} "
                 f"(3σ_B = {v['threshold_B']:.2f}).")
        L.append("")
    if v.get("conditions"):
        L.append("## Main result and controls (these decide the verdict)")
        for name, (title, expect) in GATES.items():
            c = v["conditions"].get(name)
            if c is None:
                L.append(f"- **{title}**: not available.")
                continue
            if name == "d_punish_a":
                bchg = v["diagnostics"].get("d_punish_a_cue_B_score_change")
                num = f"cue B changed by {bchg:+.2f}{_sig(bchg, v.get('sigma_B'))}"
            else:
                num = f"A−B changed by {c['delta']:+.2f}{_sig(c['delta'], v.get('sigma'))}"
            L.append(f"- **{title}**: {num}. Expected: {expect}. "
                     f"**{'PASS' if c['pass'] else 'FAIL'}**.")
        L.append("")
    cd = (v.get("reported_diagnostics") or {}).get("c_reward_both")
    L.append("## Reported only (does not affect the verdict)")
    if cd:
        L.append(f"- Control (c), reward after both cues: A−B changed by {cd['delta']:+.2f}"
                 f"{_sig(cd['delta'], v.get('sigma'))}. If learning is cue-specific and roughly "
                 f"additive, we expect about main + (b) = {cd['additive_prediction_main_plus_b']:+.2f} "
                 f"(difference {cd['residual_from_additive_prediction']:+.2f}). This is not a gate: "
                 "cues A and B drive differently composed MBON populations, so equal reward need "
                 "not leave A−B unchanged.")
    else:
        L.append("- Control (c), reward after both cues: not run or not available.")
    L.append("")
    sens = v.get("readout_sensitivity") or {}
    if sens:
        L.append("## Does the result depend on how MBON activity is read out?")
        L.append("The same rules, recomputed from the saved MBON firing rates with each "
                 "preregistered alternative readout (no extra simulation). These are reported "
                 "only; the verdict above uses CIRCUIT-80.")
        computed = {n: sv for n, sv in sens.items() if "unavailable" not in sv}
        for name, sv in sens.items():
            if name not in computed:
                L.append(f"- {VARIANT_TEXT.get(name, name)}: **NOT COMPUTED** ({sv['unavailable']})")
                continue
            main = sv["conditions"].get("main", {}).get("delta")
            extra = (f"; main A−B change {main:+.2f} vs 3σ = {sv['threshold']:.2f}"
                     if main is not None and sv.get("threshold") else "")
            fails = f"; failed: {', '.join(sv['failed_controls'])}" if sv.get("failed_controls") else ""
            L.append(f"- {VARIANT_TEXT.get(name, name)}: **{sv['verdict']}**{extra}{fails}")
        sens = computed
        agree = [n for n, sv in sens.items() if sv["verdict"] == v["verdict"]]
        L.append("")
        if len(agree) == len(sens):
            L.append(f"All {len(sens)} variants give the same verdict as the primary readout.")
        else:
            differ = [n for n in sens if n not in agree]
            L.append(f"{len(differ)} of {len(sens)} variants give a DIFFERENT verdict "
                     f"({', '.join(differ)}); the result must be reported as depending on the readout.")
        g3 = sens.get("circuit_80_no_gamma3")
        if g3 and v["verdict"] == fl.DEMONSTRATED and g3["verdict"] != fl.DEMONSTRATED:
            L.append("In particular, the effect does not survive removing MBON09/MBON08 (γ3), the type "
                     "whose CIRCUIT sign contradicts its behavioural label.")
        L.append("")
    main_file = paths.condition("main")
    if main_file.exists():
        ws = json.loads(main_file.read_text())["weight_summary"]
        pam = ws.get("rows_A_cols_PAM_fraction_of_baseline")
        if pam is not None:
            L.append("## What changed in the network (main condition)")
            L.append(f"Cue A's synapses onto reward-compartment (PAM) MBONs ended at {pam:.0%} of "
                     "their starting strength; cue B's synapses ended at "
                     f"{ws.get('rows_B_cols_PAM_fraction_of_baseline', float('nan')):.0%}; synapses from "
                     f"other Kenyon cells changed in {ws.get('other_rows_changed')} rows.")
            L.append("")
    L.append("## Caveats (stated before the run)")
    L.append("- One simulated network, one pair of cues, placeholder learning parameters; "
             "this is a feasibility test, not a measurement of fly learning.")
    L.append("- Dopamine is abstract: our rule changes weights where reward-type dopamine neurons "
             "project; the model itself has no dopamine-dependent plasticity.")
    L.append("- The fast simulator path's equivalence test against the original path had not "
             "been run when the protocol was fixed (docs/design/fast-runner.md).")
    L.append("- Full criteria: docs/design/first-learning-test.md.")
    return L


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--results-dir", type=Path, default=None,
                   help="Results directory (default: the pre-stated config's directory).")
    p.add_argument("--smoke", action="store_true", help="Use the smoke config's directory.")
    p.add_argument("--results-base", type=Path, default=RESULTS_BASE)
    p.add_argument("--out", type=Path, default=None, help="Also write the summary to this file.")
    args = p.parse_args(argv)
    d = args.results_dir or fl.results_dir_for(
        args.results_base, fl.ExperimentConfig.smoke() if args.smoke else fl.ExperimentConfig())
    try:
        text = "\n".join(report_lines(d)) + "\n"
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    print(text, end="")
    if args.out:
        args.out.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
