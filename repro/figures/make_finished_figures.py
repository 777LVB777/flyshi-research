#!/usr/bin/env python3
"""Paper figures from FINISHED results only. Reads no synthetic-sweep or Phase 2 file.

    .venv/bin/python repro/figures/make_finished_figures.py            # SVG + PNG
    .venv/bin/python repro/figures/make_finished_figures.py --no-png   # SVG only

Each figure is drawn from the finished, pre-stated diagnostic's or test's own
summary (or, for the first learning test, from the test's own pre-stated
evaluation, ``first_learning.evaluate_results``). Every pre-stated threshold is
drawn, labelled as such. A figure never recomputes a verdict differently from the
record. The sources and their SHA-256 are written to ``MANIFEST.json`` beside the
figures.

| figure | source | pre-stated threshold drawn |
|---|---|---|
| fig1_first_learning | results/first_learning_6fea97ac91 (evaluate_results) | +-3 sigma on Delta(A-B); +-3 sigma_B on cue B |
| fig2_first_learning_ignition_recheck | results/first_learning_ignition_recheck_20261012/ignition_recheck_summary.json | 3 sigma on the cascade-adjusted Delta_main |
| fig3_population_scaling_ignition | results/left_only_scaling_summary.json, results/population_scaling_summary.json | 1% ignition label |
| fig4_graded_encoding | results/graded_left_mirrored_verdict.json | 3 x d_change endpoint gate |
| fig5_pool_identity_control | results/pool_identity_control_summary.json | 3 x W_P and 3 x max(W_P, W_Q) |
| fig6_low_drive_followup | results/low_drive_followup_summary.json | the 25 and 30 kHz band edges |
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import svgplot as sp  # noqa: E402

RESULTS = REPO / "repro" / "mushroom_body" / "results"
OUT = HERE / "finished"
#: never read: the synthetic sweep (not finished; blinded) and anything Phase 2
FORBIDDEN = re.compile(r"synthetic_market|synthetic_extremes|phase2|real_market|fill_plan|histories_|"
                       r"markets_[0-9a-f]{12}|data/polymarket")

FIRST_LEARNING = RESULTS / "first_learning_6fea97ac91"
RECHECK = RESULTS / "first_learning_ignition_recheck_20261012" / "ignition_recheck_summary.json"
LEFT_SCALING = RESULTS / "left_only_scaling_summary.json"
POP_SCALING = RESULTS / "population_scaling_summary.json"
GRADED = RESULTS / "graded_left_mirrored_verdict.json"
POOL_ID = RESULTS / "pool_identity_control_summary.json"
LOW_DRIVE = RESULTS / "low_drive_followup_summary.json"


def allowed(path: Path) -> Path:
    path = Path(path)
    if FORBIDDEN.search(str(path)):
        raise PermissionError(f"refusing to read {path}: synthetic-sweep and Phase 2 results are not read here")
    return path


def read_json(path: Path) -> dict:
    return json.loads(allowed(path).read_text())


def sha256(path: Path) -> str:
    p = Path(path)
    if p.is_dir():
        h = hashlib.sha256()
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            h.update(str(f.relative_to(p)).encode())
            h.update(f.read_bytes())
        return h.hexdigest()
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
CONDITIONS = ("main", "a_plasticity_off", "b_reward_b", "c_reward_both", "d_punish_a")
CONDITION_LABELS = {"main": "main\nreward A", "a_plasticity_off": "(a) plasticity\noff",
                    "b_reward_b": "(b) reward B", "c_reward_both": "(c) reward both\n[diagnostic]",
                    "d_punish_a": "(d) punish A"}


def fig1_first_learning() -> Tuple[sp.Figure, List[Path]]:
    from flyshi_research.learning import first_learning as fl

    d = allowed(FIRST_LEARNING)
    cfg = fl.ExperimentConfig.from_dict(read_json(d / "config.json"))
    v = fl.evaluate_results(d, cfg)
    fig = sp.Figure(1100, 520, f"First learning test: {v['verdict']} (pre-stated; 5 test seeds)",
                    caption=("Points: per-seed paired change; diamonds: the pre-stated measure (change of the 5-seed mean). "
                             "Dashed: the pre-stated thresholds. (c) is a reported diagnostic and never gates.\n"
                             f"σ = {v['sigma']:.2f} Hz (SD of the pre-training A−B difference over seeds); "
                             f"σ_B = {v['sigma_B']:.2f} Hz. Source: {d.relative_to(REPO)}"))
    a = fig.add_axes(90, 60, 440, 340)
    a.xcats = [CONDITION_LABELS[c] for c in CONDITIONS]
    a.title = "A  Change in cue A − cue B score"
    a.ylabel = "Δ(A−B) after training (Hz)"
    T = v["threshold"]
    a.hband(-T, T, label=f"|Δ| < 3σ = {T:.2f} Hz")
    a.hline(T, color=sp.VERMILLION, label="±3σ (pre-stated)")
    a.hline(-T, color=sp.VERMILLION)
    a.hline(0, color="#999", dash=None, width=0.8)
    for i, c in enumerate(CONDITIONS):
        paired = v["diagnostics"].get(f"{c}_paired_changes") or []
        a.scatter([i + 0.08 * (k - 2) for k in range(len(paired))], paired, color=sp.BLUE, size=3.2, opacity=0.8)
        delta = v["conditions"][c]["delta"] if c in v["conditions"] else \
            v["reported_diagnostics"][c]["delta"]
        a.scatter([i], [delta], color=sp.ORANGE, marker="D", size=5)
    a.legend_items.append(("per-seed paired change", "marker:o", sp.BLUE))
    a.legend_items.append(("pre-stated Δ", "marker:D", sp.ORANGE))
    a.legend_loc = "upper right"

    b = fig.add_axes(620, 60, 440, 340)
    b.xcats = a.xcats
    b.title = "B  Change in cue B's own score"
    b.ylabel = "cue B score change (Hz)"
    TB = v["threshold_B"]
    b.hband(-TB, TB, label=f"(d) criterion: |change| < 3σ_B = {TB:.2f} Hz")
    b.hline(TB, color=sp.VERMILLION)
    b.hline(-TB, color=sp.VERMILLION)
    b.hline(0, color="#999", dash=None, width=0.8)
    for i, c in enumerate(CONDITIONS):
        change = v["diagnostics"].get(f"{c}_cue_B_score_change")
        if change is not None:
            b.scatter([i], [change], color=sp.GREEN, marker="D", size=5)
    b.legend_items.append(("change of the 5-seed mean", "marker:D", sp.GREEN))
    b.legend_loc = "upper left"
    changes = [v["diagnostics"].get(f"{c}_cue_B_score_change") for c in CONDITIONS]
    top = max(x for x in changes if x is not None)
    b.ylim = (-0.2 * top, 1.45 * top)  # room for the legend above the points
    return fig, [d]


def fig2_ignition_recheck() -> Tuple[sp.Figure, List[Path]]:
    s = read_json(RECHECK)
    rep, read = s["report"], s["readings"]
    fig = sp.Figure(1100, 520, "First learning test, ignition re-check: KC cascades only on rewarded cues (diagnostic)",
                    caption=("Each point is one 1 s test trial (5 seeds x 5 trials per cue). Red crosses: ignited trials "
                             "(> 1% of non-stimulated KCs above 0.5 Hz; the sweep's definition).\n"
                             f"Main condition: Δ = {read['main']['delta']:.2f} Hz, {read['main']['delta_adjusted']:.2f} Hz "
                             f"without ignited trials; pre-stated threshold 3σ = {read['main']['threshold_original']:.2f} Hz "
                             "(unchanged). Descriptive only; the verdict stands. Source: "
                             f"{RECHECK.relative_to(REPO)}"))
    a = fig.add_axes(90, 60, 980, 340)
    groups = [("pretest", rep["pretest"])] + [(c, rep["conditions"][c]["posttest"]) for c in CONDITIONS]
    names = []
    for gi, (name, rows) in enumerate(groups):
        for ci, cue in enumerate(("A", "B")):
            x0 = gi * 2 + ci
            names.append(f"{'pre-test' if name == 'pretest' else CONDITION_LABELS[name].split(chr(10))[0]}\ncue {cue}")
            pts, ign = [], []
            for r in rows:
                if r["cue"] != cue:
                    continue
                for k, (score, flag) in enumerate(zip(r["trial_scores"], r["ignited"])):
                    x = x0 + 0.06 * (k - 2) + 0.012 * (int(r["seed"]) % 5)
                    (ign if flag else pts).append((x, score))
            a.scatter([p[0] for p in pts], [p[1] for p in pts], color=sp.BLUE if cue == "A" else sp.ORANGE,
                      size=2.8, opacity=0.75)
            a.scatter([p[0] for p in ign], [p[1] for p in ign], color=sp.VERMILLION, marker="x", size=5)
    a.xcats = names
    a.ylabel = "CIRCUIT-80 score, one trial (Hz)"
    a.hline(0, color="#999", dash=None, width=0.8)
    a.legend_items += [("cue A trial", "marker:o", sp.BLUE), ("cue B trial", "marker:o", sp.ORANGE),
                       ("ignited trial (cascade)", "marker:x", sp.VERMILLION)]
    a.legend_loc = "lower left"
    return fig, [RECHECK]


def fig3_population_scaling() -> Tuple[sp.Figure, List[Path]]:
    left = read_json(LEFT_SCALING)
    pop = read_json(POP_SCALING)
    label = left["ignition_label_spread_fraction"]
    lo_ign = sum(c["ignited_runs"] for c in left["conditions"].values())
    lo_n = sum(c["n_seeds"] for c in left["conditions"].values())
    bi = {c["n_kcs_driven"]: (c["ignited_runs"], c["n_seeds"]) for c in left["bilateral_reference"].values()}
    bi_text = ", ".join(f"{k}/{n} at {kc}" for kc, (k, n) in sorted(bi.items()))
    fig = sp.Figure(1100, 520, f"Population scaling at 90 Hz per KC: bilateral runs ignited {bi_text} KCs; "
                               f"left-only runs {lo_ign}/{lo_n}",
                    caption=("Six seeds per rung (points); 1 s x 5 trials per run. Ignition label (pre-stated, for reporting "
                             f"only; no pass criterion): non-stimulated KC active fraction above {label:.0%}.\n"
                             "Bilateral 400-KC rung: only the six-seed mean was recorded (pale square). Sources: "
                             f"{LEFT_SCALING.relative_to(REPO)}, {POP_SCALING.relative_to(REPO)}"))
    a = fig.add_axes(90, 60, 440, 340)
    a.title = "A  Recruitment beyond the stimulated KCs"
    a.xlabel = "stimulated KCs (90 Hz each)"
    a.ylabel = "non-stimulated KCs active (fraction)"
    a.xlim, a.ylim = (50, 550), (-0.03, 1.1)  # headroom for the legend
    a.xticks = [100, 200, 300, 400, 500]
    a.hline(label, color=sp.VERMILLION, label=f"{label:.0%} ignition label (pre-stated)")
    for name, cond in left["bilateral_reference"].items():
        n = cond["n_kcs_driven"]
        ys = cond["nonstimulated_kc_active_fraction_per_seed"]
        a.scatter([n - 8 + 2.5 * k for k in range(len(ys))], ys, color=sp.BLUE, size=3.4)
    p400 = pop["conditions"]["ladder_400"]
    a.scatter([400], [p400["nonstimulated_kc_active_fraction"]], color=sp.SKY, marker="s", size=4)
    for name, cond in left["conditions"].items():
        n = cond["n_kcs_driven"]
        ys = cond["nonstimulated_kc_active_fraction_per_seed"]
        a.scatter([n + 8 + 2.5 * k for k in range(len(ys))], ys, color=sp.ORANGE, marker="^", size=3.4)
    a.legend_items += [("bilateral pools", "marker:o", sp.BLUE), ("left-only pools", "marker:^", sp.ORANGE),
                       ("bilateral 400 KCs: mean only", "marker:s", sp.SKY)]
    a.legend_loc = "upper left"

    b = fig.add_axes(620, 60, 440, 340)
    b.title = "B  Seed-to-seed score noise"
    b.xlabel = "stimulated KCs (90 Hz each)"
    b.ylabel = "SD of the score across seeds (Hz, log scale)"
    b.ylog = True
    b.xlim, b.xticks = (50, 550), [100, 200, 300, 400, 500]
    bil = sorted((c["n_kcs_driven"], c["score_sd"]) for c in pop["conditions"].values() if c["per_kc_rate_hz"] == 90.0)
    lo = sorted((c["n_kcs_driven"], c["score_sd"]) for c in left["conditions"].values())
    b.line([x for x, _ in bil], [y for _, y in bil], color=sp.BLUE, label="bilateral pools")
    b.scatter([x for x, _ in bil], [y for _, y in bil], color=sp.BLUE)
    b.line([x for x, _ in lo], [y for _, y in lo], color=sp.ORANGE, dash="5 3", label="left-only pools")
    b.scatter([x for x, _ in lo], [y for _, y in lo], color=sp.ORANGE, marker="^")
    b.legend_loc = "lower right"
    return fig, [LEFT_SCALING, POP_SCALING]


def fig4_graded() -> Tuple[sp.Figure, List[Path]]:
    g = read_json(GRADED)
    vals = g["values"]
    fig = sp.Figure(1100, 520, f"Graded price encoding, left-only mirrored: {g['verdict']} (pre-stated validation)",
                    caption=("Score of the unbalanced Option B pair (YES at p, NO at 1 - p), 500 left-hemisphere KCs per framing. "
                             "Monotonicity is judged on the six-seed mean (pre-stated).\n"
                             f"Endpoint gate: primary-seed distance must exceed {g['noise_margin']:g} x d_change "
                             f"(d_change from the five repeat seeds). Validated range {g['validated_value_range']}. "
                             f"Source: {GRADED.relative_to(REPO)}"))
    a = fig.add_axes(90, 60, 520, 340)
    a.title = "A  Score versus encoded price"
    a.xlabel = "encoded price p (YES framing)"
    a.ylabel = "CIRCUIT-80 score difference (Hz)"
    a.xlim, a.xticks = (0.52, 0.98), vals
    for seed, scores in g["scores_by_seed"].items():
        primary = int(seed) == g["primary_seed"]
        a.scatter(vals, scores, color=sp.VERMILLION if primary else sp.SKY, marker="s" if primary else "o",
                  size=3.6 if primary else 2.8)
    a.line(vals, g["seed_mean_scores"], color=sp.BLUE, width=2.0, label="six-seed mean")
    a.legend_items += [("primary seed", "marker:s", sp.VERMILLION), ("repeat seeds", "marker:o", sp.SKY)]
    a.legend_loc = "upper right"

    b = fig.add_axes(720, 60, 340, 340)
    b.title = "B  Endpoint gate (0.56 → 0.94)"
    b.xcats = ["endpoint\ndistance", "3 × d_change"]
    b.ylabel = "MBON-vector distance (Hz)"
    b.ylim = (0, max(g["endpoint_distance_hz"], g["endpoint_threshold_hz"]) * 1.25)
    b.bar([0], [g["endpoint_distance_hz"]], color=sp.BLUE)
    b.bar([1], [g["endpoint_threshold_hz"]], color=sp.VERMILLION)
    b.hline(g["endpoint_threshold_hz"], color=sp.VERMILLION, label="pre-stated gate")
    lift = 0.03 * b.ylim[1]
    b.text(0, g["endpoint_distance_hz"] + lift, f"{g['endpoint_distance_hz']:.1f} Hz", anchor="middle", size=11)
    b.text(1, g["endpoint_threshold_hz"] + lift, f"{g['endpoint_threshold_hz']:.1f} Hz", anchor="middle", size=11)
    b.legend_loc = "upper right"
    return fig, [GRADED]


def fig5_pool_identity() -> Tuple[sp.Figure, List[Path]]:
    p = read_json(POOL_ID)
    changes = list(p["changes"])
    fig = sp.Figure(1100, 540, "Pool-identity control: a substitute KC pool in place of the price pool (diagnostic)",
                    caption=(f"X: the cross-arm difference (price pool P against substitute pool Q) for each change in encoded "
                             f"price; thresholds {p['noise_margin']:g} x W_P (the price arm's floor) and "
                             f"{p['noise_margin']:g} x max(W_P, W_Q) (pre-stated).\n"
                             f"Primary change {p['primary_change']}: {p['primary_interpretation'][:120]}. "
                             f"Source: {POOL_ID.relative_to(REPO)}"))
    for k, (part, title, xlab) in enumerate((("scalar", "A  Score change (scalar)", "|X| (Hz)"),
                                             ("vector", "B  MBON-vector change", "X (Hz)"))):
        ax = fig.add_axes(90 + k * 520, 60, 440, 340)
        ax.title = title
        ax.ylabel = f"{xlab}: cross-arm difference"
        ax.xcats = [c.replace("->", " →\n") + ("\n[primary]" if p["changes"][c]["primary"] else "") for c in changes]
        xs = list(range(len(changes)))
        x_vals = [abs(p["changes"][c][part]["cross_X_hz"]) for c in changes]
        t_p = [p["noise_margin"] * p["changes"][c][part]["floor_W_P_hz"] for c in changes]
        t_m = [p["noise_margin"] * max(p["changes"][c][part]["floor_W_P_hz"], p["changes"][c][part]["floor_W_Q_hz"])
               for c in changes]
        ax.bar(xs, x_vals, color=sp.BLUE, label="|X|")
        ax.scatter(xs, t_p, color=sp.VERMILLION, marker="D", size=4.5, label="3 × W_P (pre-stated)")
        ax.scatter(xs, t_m, color=sp.PURPLE, marker="^", size=4.5, label="3 × max(W_P, W_Q) (pre-stated)")
        ax.ylim = (0, max(x_vals + t_m) * 1.2)
        ax.legend_loc = "upper left"
    return fig, [POOL_ID]


def fig6_low_drive() -> Tuple[sp.Figure, List[Path]]:
    s = read_json(LOW_DRIVE)
    stim = s["stimuli"]
    fig = sp.Figure(1100, 540, "Low-drive follow-up: rare single-trial ignition at the sweep's lowest drives (diagnostic)",
                    caption=(f"Ten of the sweep's own presentations at baseline weights, 10 seeds x 5 trials each. A run is "
                             f"labelled ignited when any trial exceeds {s['ignition_label_spread_fraction']:.0%} non-stimulated "
                             f"KC spread (> {s['active_hz']:g} Hz).\n"
                             f"Error bars: Clopper-Pearson {s['ci_level']:.0%}. Shaded: the pre-stated bands, below 25 kHz and "
                             f"25-30 kHz. Source: {LOW_DRIVE.relative_to(REPO)}"))
    a = fig.add_axes(90, 60, 600, 360)
    a.title = "A  Runs with an ignited trial, per presentation"
    a.xlabel = "total drive of the presentation (kHz)"
    a.ylabel = "ignited runs (fraction of 10)"
    a.xlim, a.ylim = (22.0, 30.5), (-0.02, 0.6)
    a.vband(22.0, 25.0, color=sp.SKY, opacity=0.12, label="below 25 kHz (pre-stated band)")
    a.vband(25.0, 30.0, color=sp.ORANGE, opacity=0.10, label="25-30 kHz (pre-stated band)")
    a.vline(25.0, color=sp.GREY)
    a.vline(30.0, color=sp.GREY)
    xs, ys, lo, hi = [], [], [], []
    for name, v in stim.items():
        r = v["runs_any_trial_ignited"]
        xs.append(v["total_drive_hz"] / 1000)
        ys.append(r["rate"])
        lo.append(r["ci95_lower"])
        hi.append(r["ci95_upper"])
    a.errorbar(xs, ys, lo, hi, color=sp.BLUE)
    a.scatter(xs, ys, color=sp.BLUE, size=4, label="presentation (10 runs)")
    a.legend_loc = "upper left"

    b = fig.add_axes(790, 60, 270, 360)
    b.title = "B  Pooled by band"
    b.xcats = ["below\n25 kHz", "25-30\nkHz", "all"]
    b.ylabel = "ignited runs (fraction)"
    b.ylim = (-0.01, 0.2)
    pooled = s["pooled"]
    keys = ("below25", "band25_30", "all")
    rates = [pooled[k]["runs_any_trial_ignited"] for k in keys]
    b.errorbar([0, 1, 2], [r["rate"] for r in rates], [r["ci95_lower"] for r in rates],
               [r["ci95_upper"] for r in rates], color=sp.BLUE)
    b.scatter([0, 1, 2], [r["rate"] for r in rates], color=sp.BLUE, marker="D", size=4.5)
    for i, r in enumerate(rates):
        b.text(i + 0.12, r["rate"], f"{r['k']}/{r['n']}", size=10)
    return fig, [LOW_DRIVE]


FIGURES: Dict[str, Callable[[], Tuple[sp.Figure, List[Path]]]] = {
    "fig1_first_learning": fig1_first_learning,
    "fig2_first_learning_ignition_recheck": fig2_ignition_recheck,
    "fig3_population_scaling_ignition": fig3_population_scaling,
    "fig4_graded_encoding": fig4_graded,
    "fig5_pool_identity_control": fig5_pool_identity,
    "fig6_low_drive_followup": fig6_low_drive,
}


def make(out: Path = OUT, png: bool = True, only=None) -> dict:
    out = Path(out)
    manifest = {"note": "figures from finished results only; no synthetic-sweep or Phase 2 file is read",
                "png": "rendered from the SVG with macOS qlmanage + sips" if png else "not made (--no-png)",
                "figures": {}}
    for name, build in FIGURES.items():
        if only and name not in only:
            continue
        fig, sources = build()
        svg = out / f"{name}.svg"
        made_png = fig.save(svg, png=png and sp.png_tools_available())
        manifest["figures"][name] = {
            "svg": svg.name, "png": made_png.name if made_png else None,
            "sources": {str(Path(s).relative_to(REPO)): sha256(s) for s in sources}}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--no-png", action="store_true")
    args = p.parse_args(argv)
    manifest = make(args.out, png=not args.no_png)
    for name, entry in manifest["figures"].items():
        print(f"{name}: {entry['svg']}" + (f", {entry['png']}" if entry["png"] else "") +
              f"  <- {', '.join(entry['sources'])}")
    if not args.no_png and not sp.png_tools_available():
        print("PNG not made: qlmanage/sips not found (macOS only); SVGs are complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
