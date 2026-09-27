#!/usr/bin/env python3
"""Left-only realistic-drive diagnostic: containment and same-stimulus noise.

Pre-stated protocol: docs/design/left-only-realistic-drive-diagnostic.md, written
before this code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. No pass criterion,
no verdict field; PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL are deliberately
absent, as they belong to validations.

Seven YES-framed encoder stimuli, pools drawn from LEFT-hemisphere Kenyon cells
only: the unbalanced diagnostic's five price values (39,600-49,560 Hz) and the
balanced encoder's v = 0.00 and v = 0.25 (60,000 and 57,000 Hz). Seven stimuli x
six seeds = 42 simulations. Every run records MBON, Kenyon cell, APL, PAM and PPL1
trial-mean rates, plus per-trial Kenyon cell, MBON and APL rates.

YES only: the NO framing, the contrast c(v) and S(v) are never built, so nothing
here bears on the mirroring antisymmetry (spec section 4).

Running without --analyze-only or --dry-run executes 42 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; import no Brian2 at module level

from flyshi_research.learning.encoder import BALANCE_FEATURE, KCEncoder  # noqa: E402
from flyshi_research.learning.params import (  # noqa: E402
    OPTION_B_BALANCED,
    OPTION_B_UNBALANCED,
)
from analyze_recruitment_intensity import recruitment_from_rates  # noqa: E402
from run_left_only_pool_diagnostic import (  # noqa: E402
    IGNITION_SPREAD_FRACTION,
    kc_side_map,
    left_kc_ids,
    statistics,
)
from run_left_only_population_scaling_diagnostic import side_counts  # noqa: E402
from run_population_scaling_diagnostic import (  # noqa: E402
    POPULATIONS,
    SECONDS_PER_BUILD,
    SECONDS_PER_SIMULATION,
)
from run_unbalanced_g_diagnostic import _assert_pools_left_only  # noqa: E402

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
SPEC = "docs/design/left-only-realistic-drive-diagnostic.md"

# ---- fixed by the pre-statement (spec sections 2-3) ------------------------------ #
POOL_SIDE = "left"
FRAMING = "YES"
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
DURATION_MS = 1000.0
TRIALS = 5
BACKGROUND: Dict[str, float] = {
    "recent_change": 0.0,
    "time_to_resolution": 182.5,
    "liquidity": 0.5,
    "signal": 0.5,
}
#: populations whose per-trial rates are saved (spec section 3)
PER_TRIAL_POPULATIONS: Tuple[str, ...] = ("kenyon_cells", "mbons", "apl_neurons")
#: per-file ceiling, relaxed from 1 MB for the per-trial arrays (spec section 5)
MAX_FILE_BYTES = 5 * 1024 * 1024
#: words that belong to validations and must never appear in this output
BANNED_WORDS: Tuple[str, ...] = ("PASS", "FAIL", "ACCEPTED", "USABLE RANGE")
BANNED_KEYS: Tuple[str, ...] = ("verdict", "pass", "passed", "pass_criterion")


@dataclass(frozen=True)
class StimulusSpec:
    name: str
    price_value: float
    variant: str
    source: str

    def features(self) -> Dict[str, float]:
        return {"price": self.price_value, **BACKGROUND}


STIMULI: Tuple[StimulusSpec, ...] = (
    StimulusSpec("unbalanced_v0p05", 0.05, OPTION_B_UNBALANCED, "unbalanced diagnostic, v=0.05"),
    StimulusSpec("unbalanced_v0p22", 0.22, OPTION_B_UNBALANCED, "unbalanced diagnostic, v=0.22"),
    StimulusSpec("unbalanced_v0p41", 0.41, OPTION_B_UNBALANCED, "unbalanced diagnostic, v=0.41"),
    StimulusSpec("unbalanced_v0p63", 0.63, OPTION_B_UNBALANCED, "unbalanced diagnostic, v=0.63"),
    StimulusSpec("unbalanced_v0p88", 0.88, OPTION_B_UNBALANCED, "unbalanced diagnostic, v=0.88"),
    StimulusSpec("balanced_v0p00", 0.00, OPTION_B_BALANCED, "balanced graded spec, v=0.00"),
    StimulusSpec("balanced_v0p25", 0.25, OPTION_B_BALANCED, "balanced graded spec, v=0.25"),
)
BY_NAME: Dict[str, StimulusSpec] = {s.name: s for s in STIMULI}

#: the pre-statement's table (spec section 2), checked against the encoder's output
EXPECTED_TOTAL_DRIVE_HZ: Dict[str, float] = {
    "unbalanced_v0p05": 39_600.0, "unbalanced_v0p22": 41_640.0,
    "unbalanced_v0p41": 43_920.0, "unbalanced_v0p63": 46_560.0,
    "unbalanced_v0p88": 49_560.0, "balanced_v0p00": 60_000.0, "balanced_v0p25": 57_000.0,
}
EXPECTED_N_KCS: Dict[str, int] = {s.name: (800 if s.variant == OPTION_B_BALANCED else 500)
                                  for s in STIMULI}


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_left_only_realistic_drive_diagnostic.py"
    )
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog=f"Exact pre-stated run:\n  {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--analyze-only", action="store_true",
                   help="Summarise existing files; never simulates.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan and the runtime estimate; never simulates.")
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--ids", type=Path, default=IDS_PATH)
    return p


def output_path(stimulus: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"left_only_realistic_drive_{stimulus}_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "left_only_realistic_drive_summary.json"


def _write_json(path: Path, payload: dict, max_bytes: Optional[int] = None) -> None:
    text = json.dumps(payload, separators=(",", ":"))
    if max_bytes is not None and len(text.encode()) > max_bytes:
        raise RuntimeError(f"{path.name}: {len(text.encode()):,} bytes exceeds the "
                           f"{max_bytes:,}-byte ceiling (spec section 5); not written")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text)
    partial.replace(path)


def planned_pairs() -> Tuple[Tuple[str, int], ...]:
    return tuple((s.name, seed) for s in STIMULI for seed in SEEDS)


def missing_pairs(results_dir: Path = RESULTS_DIR) -> List[Tuple[str, int]]:
    return [(name, seed) for name, seed in planned_pairs()
            if not output_path(name, seed, results_dir).exists()]


# --------------------------------------------------------------------------- #
# the stimuli (pure data; no Brian2, no connectome)
# --------------------------------------------------------------------------- #
def build_stimuli(ids_path: Path = IDS_PATH) -> Dict[str, dict]:
    """Every stimulus, from one left-only encoder, checked against the spec.

    Aborts unless every drawn KC is left-hemisphere, each stimulus drives the
    stated number of KCs at the stated total, and only the balanced stimuli carry
    the balance pool.
    """
    encoder = KCEncoder(left_kc_ids(ids_path))
    _assert_pools_left_only(encoder, ids_path=ids_path)
    pool_ids = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    pool_ids[BALANCE_FEATURE] = sorted(int(i) for i in encoder.balance_pool)

    built: Dict[str, dict] = {}
    for spec in STIMULI:
        stim = encoder.option_b_stimuli(spec.features(), variant=spec.variant).yes
        if stim.side != FRAMING:
            raise RuntimeError(f"{spec.name}: expected the {FRAMING} framing")
        has_balance = BALANCE_FEATURE in stim.feature_rates_hz
        if has_balance != (spec.variant == OPTION_B_BALANCED):
            raise RuntimeError(f"{spec.name}: balance pool presence does not match variant")
        if stim.was_clipped:
            raise RuntimeError(f"{spec.name}: a feature value was clipped")
        rates = stim.rates_by_kc_id()
        total = float(np.sum(stim.rates_hz))
        if len(rates) != EXPECTED_N_KCS[spec.name]:
            raise RuntimeError(f"{spec.name}: expected {EXPECTED_N_KCS[spec.name]} KCs, "
                               f"built {len(rates)}")
        if not np.isclose(total, EXPECTED_TOTAL_DRIVE_HZ[spec.name], rtol=0.0, atol=1e-6):
            raise RuntimeError(f"{spec.name}: total drive {total:g} Hz, spec says "
                               f"{EXPECTED_TOTAL_DRIVE_HZ[spec.name]:g} Hz")
        pools = {name: pool_ids[name] for name in stim.feature_rates_hz}
        built[spec.name] = {
            "rates_by_kc_id": rates,
            "stimulated_kc_ids": sorted(rates),
            "pools": pools,
            "pool_rates_hz": {k: float(v) for k, v in stim.feature_rates_hz.items()},
            "total_drive_hz": total,
        }
    return built


# --------------------------------------------------------------------------- #
# per-trial binning (pure numpy; the simulator only supplies the spike table)
# --------------------------------------------------------------------------- #
def bin_spikes(neuron_index: np.ndarray, trial: np.ndarray, n_neurons: int,
               n_trials: int, duration_ms: float) -> Tuple[np.ndarray, np.ndarray]:
    """(per_trial_rate [n_trials, n_neurons], trial_mean_rate [n_neurons]).

    ``per_trial_rate[t, i] = count(i, t) / duration_s``. The trial mean equals the
    population-scaling runner's ``counts / (duration_s * n_trials)`` exactly.
    """
    neuron_index = np.asarray(neuron_index, dtype=int)
    trial = np.asarray(trial, dtype=int)
    if neuron_index.shape != trial.shape:
        raise ValueError("neuron_index and trial must be parallel")
    if trial.size and (trial.min() < 0 or trial.max() >= n_trials):
        raise ValueError(f"trial index outside 0..{n_trials - 1}")
    counts = np.zeros((n_trials, n_neurons), dtype=float)
    np.add.at(counts, (trial, neuron_index), 1.0)
    duration_s = duration_ms / 1000.0
    return counts / duration_s, counts.sum(axis=0) / (duration_s * n_trials)


def _present_with_trials(sim, rates_by_kc_id: Mapping[int, float], seed: int,
                         duration_ms: float, n_trials: int) -> Tuple[dict, dict]:
    """Run one stimulus; return (trial-mean rates, per-trial rates) by population."""
    sim.bundle["params"]["t_run"] = duration_ms * sim._ms
    spikes, _ = sim._fr.run_cue_rates(
        sim.bundle, dict(rates_by_kc_id), n_trials, seed, "left_only_realistic_drive")
    flyid2i = sim.bundle["flyid2i"]
    if len(spikes):
        index = np.array([flyid2i[f] for f in spikes["flywire_id"]], dtype=int)
        trial = np.asarray(spikes["trial"], dtype=int)
    else:
        index = trial = np.zeros(0, dtype=int)
    per_trial, mean = bin_spikes(index, trial, sim.bundle["n"], n_trials, duration_ms)
    means = {name: mean[ix] for name, ix in sim.population_index.items()}
    trials = {name: per_trial[:, sim.population_index[name]] for name in PER_TRIAL_POPULATIONS}
    return means, trials


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    todo = missing_pairs(results_dir)
    for name, seed in planned_pairs():
        if (name, seed) not in todo:
            log(f"Output exists, skipping: {output_path(name, seed, results_dir).name}")
    if not todo:
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    stimuli = build_stimuli(ids_path)  # validated before the model is built
    sim = _build_population_simulator()
    for name, seed in todo:
        spec, stim = BY_NAME[name], stimuli[name]
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], seed,
                                             DURATION_MS, TRIALS)
        _write_json(
            output_path(name, seed, results_dir),
            {
                "stimulus": name,
                "source": spec.source,
                "variant": spec.variant,
                "framing": FRAMING,
                "price_value": spec.price_value,
                "pool_side": POOL_SIDE,
                "pools": stim["pools"],
                "pool_rates_hz": stim["pool_rates_hz"],
                "n_kcs_driven": len(stim["stimulated_kc_ids"]),
                "per_kc_rate_hz": None,  # unequal across pools; see pool_rates_hz
                "total_drive_hz": stim["total_drive_hz"],
                "stimulated_kc_ids": stim["stimulated_kc_ids"],
                "mbon_labels": list(sim.mbon_type_labels),
                "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
                "rates_hz": {p: np.asarray(v, dtype=float).tolist() for p, v in means.items()},
                "per_trial_rates_hz": {p: np.asarray(v, dtype=float).tolist()
                                       for p, v in trials.items()},
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
            max_bytes=MAX_FILE_BYTES,
        )
        log(f"{name} ({len(stim['stimulated_kc_ids'])} left KCs, "
            f"{stim['total_drive_hz']:,.0f} Hz), seed {seed}: "
            f"wrote {output_path(name, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# measurement (no verdict: this is a diagnostic)
# --------------------------------------------------------------------------- #
def per_pool_measured(payloads: Sequence[Mapping]) -> Dict[str, dict]:
    """Stimulated-KC rate, measured against imposed, for each driven pool."""
    kc_ids = [int(i) for i in payloads[0]["population_ids"]["kenyon_cells"]]
    position = {kc: n for n, kc in enumerate(kc_ids)}
    out: Dict[str, dict] = {}
    for pool, members in payloads[0]["pools"].items():
        ix = np.array([position[int(i)] for i in members])
        imposed = float(payloads[0]["pool_rates_hz"][pool])
        measured = [float(np.asarray(p["rates_hz"]["kenyon_cells"], dtype=float)[ix].mean())
                    for p in payloads]
        out[pool] = {
            "n_kcs": len(members),
            "imposed_rate_hz": imposed,
            "measured_rate_per_seed_hz": measured,
            "measured_rate_mean_hz": float(np.mean(measured)),
            "measured_over_imposed": (float(np.mean(measured)) / imposed) if imposed else None,
        }
    return out


def recruitment(payloads: Sequence[Mapping]) -> dict:
    """The rate-weighted recruitment measure, per seed and per trial."""
    kc_ids = payloads[0]["population_ids"]["kenyon_cells"]
    per_seed, per_trial = [], []
    for p in payloads:
        per_seed.append(recruitment_from_rates(kc_ids, p["rates_hz"]["kenyon_cells"],
                                               p["stimulated_kc_ids"]))
        per_trial.append([recruitment_from_rates(kc_ids, row, p["stimulated_kc_ids"])
                          for row in p["per_trial_rates_hz"]["kenyon_cells"]])
    means = [s["recruited_kc_mean_rate_hz"] for s in per_seed]
    recruited = [m for m in means if m is not None]
    return {
        "recruited_kc_mean_rate_hz_per_seed": means,
        "recruited_kc_median_rate_hz_per_seed":
            [s["recruited_kc_median_rate_hz"] for s in per_seed],
        "recruited_kc_mean_rate_hz_over_recruiting_seeds":
            float(np.mean(recruited)) if recruited else None,
        "recruited_kc_mean_rate_hz_per_trial": [
            [t["recruited_kc_mean_rate_hz"] for t in seed] for seed in per_trial],
        "nonstimulated_kc_active_fraction_per_trial": [
            [t["active_fraction"] for t in seed] for seed in per_trial],
        "recruitment_note": (
            "recruited_kc_mean_rate_hz is the mean rate of non-stimulated KCs above "
            "0.5 Hz; null when none are active. Reported beside the binary ignition "
            "label, which it does not replace (recruitment-intensity-measure.md)."
        ),
    }


def stimulus_statistics(payloads: Sequence[Mapping], sides: Mapping[int, str]) -> dict:
    labels = payloads[0]["mbon_labels"]
    if any(p["mbon_labels"] != labels for p in payloads):
        raise ValueError(f"{payloads[0]['stimulus']}: MBON label order differs between seeds")
    stimulated = payloads[0]["stimulated_kc_ids"]
    if any(p["stimulated_kc_ids"] != stimulated for p in payloads):
        raise ValueError(f"{payloads[0]['stimulus']}: stimulated KCs differ between seeds")
    stats = statistics(payloads, sides)
    stats.pop("per_kc_rate_hz", None)  # unequal across pools here
    apl_trials = [np.asarray(p["per_trial_rates_hz"]["apl_neurons"], dtype=float)
                  for p in payloads]
    stats.update({
        "variant": payloads[0]["variant"],
        "framing": payloads[0]["framing"],
        "price_value": payloads[0]["price_value"],
        "pool_rates_hz": payloads[0]["pool_rates_hz"],
        "pool_side_counts": side_counts(stimulated, sides),
        "stimulated_kc_by_pool": per_pool_measured(payloads),
        "apl_per_trial_mean_hz": [[float(row.mean()) for row in t] for t in apl_trials],
        **recruitment(payloads),
    })
    return stats


def check_no_verdict(summary: Mapping) -> None:
    """Diagnostic enforcement: raise unless the summary is a bare measurement."""
    if summary.get("is_a_validation") is not False:
        raise ValueError("is_a_validation must be False")
    if summary.get("has_pass_criterion") is not False:
        raise ValueError("has_pass_criterion must be False")

    def keys(obj):
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                yield str(k)
                yield from keys(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                yield from keys(v)

    bad = sorted({k for k in keys(summary) if k.lower() in BANNED_KEYS})
    if bad:
        raise ValueError(f"validation keys present: {bad}")
    text = json.dumps(summary)
    words = [w for w in BANNED_WORDS if w in text]
    if words:
        raise ValueError(f"validation vocabulary present: {words}")


def _load(paths: Sequence[Path]) -> List[dict]:
    return [json.loads(p.read_text()) for p in paths]


def summarise(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
              log: Callable[[str], None] = print) -> Optional[dict]:
    missing = missing_pairs(results_dir)
    if missing:
        log(f"Cannot summarise: missing {len(missing)} of {len(planned_pairs())} "
            "stimulus/seed results")
        return None
    sides = kc_side_map(ids_path)
    planned = build_stimuli(ids_path)

    per_stimulus: Dict[str, dict] = {}
    for spec in STIMULI:
        payloads = _load([output_path(spec.name, s, results_dir) for s in SEEDS])
        if payloads[0]["stimulated_kc_ids"] != planned[spec.name]["stimulated_kc_ids"]:
            raise ValueError(f"{spec.name}: saved stimulated KCs differ from the "
                             "pre-stated stimulus; refusing to summarise")
        per_stimulus[spec.name] = {"source": spec.source,
                                   **stimulus_statistics(payloads, sides)}

    table = [
        {
            "stimulus": spec.name,
            "total_drive_hz": per_stimulus[spec.name]["total_drive_hz"],
            "n_kcs_driven": per_stimulus[spec.name]["n_kcs_driven"],
            "ignited_runs": per_stimulus[spec.name]["ignited_runs"],
            "spread": per_stimulus[spec.name]["nonstimulated_kc_active_fraction"],
            "recruited_kc_mean_rate_hz_over_recruiting_seeds":
                per_stimulus[spec.name]["recruited_kc_mean_rate_hz_over_recruiting_seeds"],
            "active_mbons": per_stimulus[spec.name]["active_mbons"],
            "apl_hz": per_stimulus[spec.name]["apl_mean_rate_hz"],
            "score_sd": per_stimulus[spec.name]["score_sd"],
            "mbon_vector_distance_hz": per_stimulus[spec.name]["mbon_vector_distance_hz"],
        }
        for spec in STIMULI
    ]

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": SPEC,
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "framing": FRAMING,
        "pool_side": POOL_SIDE,
        "background_features": dict(BACKGROUND),
        "ignition_label_spread_fraction": IGNITION_SPREAD_FRACTION,
        "per_trial_populations": list(PER_TRIAL_POPULATIONS),
        "stimuli": per_stimulus,
        "table": table,
        "scope_note": (
            "Tests containment and same-stimulus noise only. YES framing only: the NO "
            "framing, c(v) and S(v) are never built, so this cannot address the "
            "mirroring antisymmetry, which is independent of hemisphere. One left "
            "pool draw (seed 20260401), the same feature pools as left_ladder_500."
        ),
        "bilateral_reference_note": (
            "No bilateral run exists at these seven stimuli, so there is no matched "
            "reference block. The recorded graded runs are the closest bilateral "
            "analogues; their ignition is inferred, not measured (MBON rates only)."
        ),
    }
    check_no_verdict(summary)
    _write_json(summary_path(results_dir), summary)

    log("=== Left-only realistic-drive diagnostic "
        "(MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"{'stimulus':<18}{'driveHz':>9}{'KCs':>5}{'ign':>6}{'spread':>8}"
        f"{'recruitHz':>10}{'actMBON':>9}{'APL':>8}{'SD':>8}{'noiseHz':>9}")
    for row in table:
        r = row["recruited_kc_mean_rate_hz_over_recruiting_seeds"]
        log(f"{row['stimulus']:<18}{row['total_drive_hz']:>9,.0f}{row['n_kcs_driven']:>5}"
            f"{row['ignited_runs']:>4}/6{100 * row['spread']:>7.1f}%"
            f"{('--' if r is None else f'{r:.2f}'):>10}"
            f"{row['active_mbons']:>9.1f}{row['apl_hz']:>8.1f}{row['score_sd']:>8.2f}"
            f"{row['mbon_vector_distance_hz']:>9.2f}")
    log("per seed (label from the trial mean; recruited rate beside it):")
    for spec in STIMULI:
        s = per_stimulus[spec.name]
        cells = []
        for i in range(len(SEEDS)):
            r = s["recruited_kc_mean_rate_hz_per_seed"][i]
            cells.append(f"{'ign' if s['ignited_per_seed'][i] else 'con'}"
                         f"({'--' if r is None else f'{r:.2f}'})")
        log(f"  {spec.name:<18}" + " ".join(cells))
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def estimated_seconds(n_todo: int) -> float:
    return n_todo * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if n_todo else 0.0)


def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> int:
    todo = missing_pairs(results_dir)
    total = len(planned_pairs())
    log("Left-only realistic-drive diagnostic: DRY RUN")
    log(f"spec: {SPEC} (PRE-STATED)")
    log("DIAGNOSTIC, not a validation: no pass criterion, no verdict is produced")
    log(f"framing: {FRAMING} only; pools drawn from {POOL_SIDE}-hemisphere KCs only")
    try:
        stimuli = build_stimuli(ids_path)
        sides = kc_side_map(ids_path)
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        stimuli, sides = {}, {}
        log(f"stimuli could not be built from {ids_path}: {exc}")
    log(f"{'stimulus':<18}{'variant':<22}{'priceHz':>8}{'KCs':>5}{'driveHz':>10}  sides")
    for spec in STIMULI:
        if spec.name in stimuli:
            s = stimuli[spec.name]
            log(f"{spec.name:<18}{spec.variant:<22}{s['pool_rates_hz']['price']:>8.1f}"
                f"{len(s['stimulated_kc_ids']):>5}{s['total_drive_hz']:>10,.0f}  "
                f"{side_counts(s['stimulated_kc_ids'], sides)}")
        else:
            log(f"{spec.name:<18}{spec.variant:<22}{'?':>8}{EXPECTED_N_KCS[spec.name]:>5}"
                f"{EXPECTED_TOTAL_DRIVE_HZ[spec.name]:>10,.0f}  ?")
    log(f"seeds: {list(SEEDS)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials")
    log(f"recorded populations (trial mean): {list(POPULATIONS)}")
    log(f"recorded populations (per trial): {list(PER_TRIAL_POPULATIONS)}")
    log(f"planned simulations: {total}  (already done: {total - len(todo)}, to run: {len(todo)})")
    log(f"estimated runtime: {estimated_seconds(len(todo)) / 60:.1f} min "
        f"({SECONDS_PER_SIMULATION:g} s per simulation + one {SECONDS_PER_BUILD:g} s build; "
        "measured on the author's machine on smaller stimuli, UNVERIFIED here)")
    log("No connectome loaded, no model built, no simulation run, nothing written.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run and args.analyze_only:
        raise SystemExit("--dry-run and --analyze-only are mutually exclusive")
    if args.dry_run:
        return dry_run(args.results_dir, args.ids)
    if not args.analyze_only:
        simulate_missing(args.results_dir, args.ids)
    return 0 if summarise(args.results_dir, args.ids) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
