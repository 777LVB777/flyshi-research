#!/usr/bin/env python3
"""Render the "Phase 2 results" section of docs/design/phase2-preregistration.md.

Every number in the section is read from the committed aggregates
(repro/real_market/results/phase2_<sha12>/verdict.json and hashes.json); none is typed
by hand. Prints Markdown to stdout. With --check FILE, exits 1 unless FILE contains
the rendered section verbatim.

  python3 repro/real_market/render_phase2_results.py
  python3 repro/real_market/render_phase2_results.py --check docs/design/phase2-preregistration.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "repro" / "real_market" / "results" / "phase2_0777ae92f0dd"
VERDICT_COMMIT = "88152c7"
GROSS_LABEL = "gross, before fees and spread, not achievable as stated"


def f4(v: float) -> str:
    s = f"{v:+.4f}"
    return s.replace("-", "−")


def f2(v: float) -> str:
    return f"{v:+.2f}".replace("-", "−")


def ci(c: dict) -> str:
    return f"{f4(c['estimate'])} [{f4(c['lower'])}, {f4(c['upper'])}]"


def n(v: int) -> str:
    return f"{v:,}"


def yes_no(b: bool) -> str:
    return "yes" if b else "no"


def render(v: dict, h: dict) -> str:
    g, comp, r, b = v["gate"], v["comparator"], v["realised"], v["brier_test"]
    design = h["manifest"]["design"]
    pnl = v["gross_pnl"]
    hv, sens, ign = v["high_volume_subset"], v["sensitivity_excluding_ignited"], v["ignition_exposure"]
    rows = (("vs_comparator", "profit_improvement_vs_comparator"),
            ("vs_learning_off", "profit_improvement_vs_learning_off"))
    labels = v["readings"]["comparisons"]
    nm = v["n_test_markets"]
    out = []
    w = out.append
    w("## Phase 2 results (written 2026-11-12, after the verdict)")
    w("")
    w("*Appended after the verdict. Sections 1–12 above are unchanged. Every number in this "
      "section is read from the committed verdict by "
      "[`repro/real_market/render_phase2_results.py`](../../repro/real_market/render_phase2_results.py); "
      "none is typed by hand.*")
    w("")
    w("**Source.**")
    w("")
    w(f"- `repro/real_market/results/phase2_0777ae92f0dd/verdict.json` and `hashes.json` "
      f"(commit `{VERDICT_COMMIT}`). Verdict SHA-256 `{h['verdict_sha256']}`.")
    w(f"- Computed by `run_real_market_experiment.py --finish` on the server autopilot, on code "
      f"`{h['code_commit'][:7]}` (tag `phase2-frozen`), from {n(len(h['job_files_sha256']))} job files "
      f"whose SHA-256s are in `hashes.json`.")
    w(f"- Market file SHA-256 `{h['market_file_sha256']}`; frozen market list `{h['manifest']['frozen_sha256']}`; "
      f"locked circuit configuration `{h['manifest']['locked_config_hash']}`.")
    w(f"- Estimated Phase 2 server spend: ${h['estimated_spend_usd']:.2f}.")
    w("")
    w("### Verdict")
    w("")
    w(f"`success = {str(v['success']).lower()}`, `gate_passes = {str(v['gate_passes']).lower()}`. "
      "The pre-stated reading (Section 8), verbatim from `readings.overall`:")
    w("")
    w(f"> {v['readings']['overall']}")
    w("")
    w("### The two gate comparisons (Section 5)")
    w("")
    w(f"Paired per-market Brier improvements of the `profit` arm on the {n(g['n'])} held-out test markets. "
      "Positive values favour the profit arm. 95% percentile bootstrap, "
      f"{n(g['profit_improvement_vs_comparator']['n_resamples'])} resamples by market. "
      "The MDE is 2.80 · σ_d / √n (Section 9), at the realised σ_d.")
    w("")
    w("| comparison | reading | estimate [95% CI] | realised σ_d | MDE | lower bound above zero | bootstrap seed |")
    w("|---|---|---|---:|---:|---|---:|")
    for key, gk in rows:
        c = g[gk]
        w(f"| `{key}` | {labels[key]} | {ci(c)} | {r[key]['sigma_d']:.4f} | {r[key]['mde']:.4f} | "
          f"{yes_no(c['lower'] > 0)} | {c['seed']} |")
    w("")
    w(f"Both lower bounds above zero: **{yes_no(g['both_lower_bounds_above_zero'])}**. Both intervals lie "
      "entirely below zero: on these markets the trained circuit's forecasts had a higher Brier score than "
      "the comparator and than its own learning-off control.")
    w("")
    w("**The comparator.** The pre-stated guard (Section 4) keeps the raw price unless the isotonic "
      "calibration has a lower 5-fold cross-validated Brier score on the training markets. "
      f"On the {n(comp['n_train'])} training markets the raw price scored {comp['cv_brier_raw']:.5f} and "
      f"the calibrated price {comp['cv_brier_calibrated']:.5f}, so the frozen comparator is "
      f"**`{comp['choice']}`**: the market price itself. The pre-stated reading's phrase "
      "\"calibrated on training markets only\" therefore describes a calibration step that kept the raw "
      f"price. Comparator SHA-256 `{comp['sha256']}`.")
    w("")
    w(f"**Brier scores on the test markets** (lower is better): `profit` {b['profit']:.4f}, "
      f"`learning_off` {b['learning_off']:.4f}, `null_permuted` {b['null_permuted']:.4f}, "
      f"comparator {b['comparator']:.4f}, raw price {b['raw_price']:.4f}.")
    w("")
    w("### Null control (Section 6)")
    w("")
    nc = g["null_improvement_vs_comparator"]
    w(f"- `null_vs_comparator` (the profit arm taught with permuted training outcomes, against the "
      f"comparator): {ci(nc)}, seed {nc['seed']}.")
    w(f"- Lower bound above zero: {yes_no(nc['lower'] > 0)}. `null_control.passes = "
      f"{str(v['null_control']['passes']).lower()}`: \"{v['null_control']['interpretation']}\". "
      "The null control is clean, so the verdict is not NULL CONTROL FAILED.")
    w("")
    w("### Test-set counts")
    w("")
    w(f"- {n(nm)} held-out test markets: {design['n_chains']} chains × {design['test_per_chain']}, "
      f"each chain after {design['train_per_chain']} training markets.")
    w(f"- The comparator was fitted on {n(comp['n_train'])} training markets, none of them a test market.")
    w("")
    w("| arm | test decisions | trades | abstentions |")
    w("|---|---:|---:|---:|")
    for arm, a in pnl["per_arm"].items():
        w(f"| `{arm}` | {n(a['markets'])} | {n(a['trades'])} | {n(a['abstentions'])} |")
    w("")
    w("### Reported only (Section 7; none of this can change the verdict)")
    w("")
    w(f"`readings.reported_only`: \"{v['readings']['reported_only']}\".")
    w("")
    w(f"**Gross P&L per arm: {pnl['label']}.** One contract per test market at the decision-time price, "
      "no fee and no spread: YES earns outcome − price, NO earns price − outcome, ABSTAIN earns 0. "
      "The CLOB price history has no spread at the decision time, so P&L after costs is not computed. "
      "**The verdict does not use these numbers**, and a positive gross figure is not an edge: "
      "the gate above is the test.")
    w("")
    w(f"| arm | total, units ({pnl['label']}) | per market [95% CI] | trades | abstentions |")
    w("|---|---:|---|---:|---:|")
    for arm, a in pnl["per_arm"].items():
        w(f"| `{arm}` | {f2(a['total'])} | {ci(a['per_market_ci'])} | {n(a['trades'])} | {n(a['abstentions'])} |")
    w("")
    w(f"**Markets with final volume ≥ ${hv['threshold_usdc']:,.0f}** ({n(hv['n'])} test markets).")
    w("")
    w("| comparison | estimate [95% CI] | MDE | lower bound above zero |")
    w("|---|---|---:|---|")
    for key, gk in rows:
        c = hv[gk]
        w(f"| `{key}` | {ci(c)} | {hv['realised_mde'][key]:.4f} | {yes_no(c['lower'] > 0)} |")
    w("")
    w("**Ignition exposure** (decisions with an ignited framing, of "
      f"{n(ign['profit']['decisions'])} per arm):")
    w("")
    w("| arm | training | test |")
    w("|---|---:|---:|")
    for arm in ("profit", "learning_off", "null_permuted"):
        e = ign[arm]
        w(f"| `{arm}` | {n(e['train_decisions_with_ignited_framing'])} | "
          f"{n(e['test_decisions_with_ignited_framing'])} |")
    w("")
    w(f"**Sensitivity analysis excluding ignited test markets** ({n(sens['n_excluded'])} excluded, "
      f"{n(sens['n_remaining'])} remaining): `vs_comparator` {ci(sens['profit_improvement_vs_comparator'])}, "
      f"`vs_learning_off` {ci(sens['profit_improvement_vs_learning_off'])}; both lower bounds above zero: "
      f"{yes_no(sens['both_lower_bounds_above_zero'])}. {sens['note'][0].upper() + sens['note'][1:]}.")
    w("")
    w("### Limitations")
    w("")
    w("- **This is not evidence of no edge.** The verdict says only that no edge larger than the realised "
      f"MDE (about {r['vs_comparator']['mde']:.4f} over the comparator and "
      f"{r['vs_learning_off']['mde']:.4f} over learning_off, in Brier units) was detected.")
    w("- **The circuit sees only three numbers per market**: the last recorded price before the decision "
      "time (at most 24 hours old), its change over the previous 24 hours, and the days to the scheduled end (Section 2; "
      "`realdata/polymarket.py`, `decision_features`). The encoder's other two pools, signal and "
      "liquidity, are set to the constant 0.5 (90 Hz in both framings) for every market, so they carry "
      "no market information. The result says nothing about a circuit given outside evidence.")
    w("- **The price-only trading rule on the project website is a display choice made on 2026-10-18**, "
      "after this preregistration and before any real-market result. The preregistration defines no "
      "trading rule for the comparator; the website's rule (YES when the comparator's forecast is above "
      "the price, NO when below) is not part of the verdict. Because the comparator kept the raw price, "
      "that rule never trades.")
    for item in v["limitations"]:
        w(f"- {item[0].upper() + item[1:]}.")
    w("- The circuit configuration, encoder and learning rule are the synthetic sweep's, unchanged; the "
      "result holds for that configuration only.")
    w("")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--check", type=Path, help="exit 1 unless this file contains the rendered section")
    a = p.parse_args(argv)
    v = json.loads((RESULTS / "verdict.json").read_text())
    h = json.loads((RESULTS / "hashes.json").read_text())
    text = render(v, h)
    if a.check:
        ok = text in a.check.read_text()
        print("matches" if ok else "DIFFERS", file=sys.stderr)
        return 0 if ok else 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
