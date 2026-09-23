#!/usr/bin/env python3
"""Population-scaling diagnostic: what sets MBON score noise?

Pre-stated protocol: docs/design/population-scaling-diagnostic.md, written before
this code and before any run.

DIAGNOSTIC, NOT A VALIDATION. It measures; it does not judge. There is no pass
criterion and no verdict field, and the PASS/FAIL and ACCEPTED / USABLE RANGE /
FAIL vocabularies are deliberately absent - they belong to validations.

Seven conditions x six seeds = 42 simulations. Every run records the mean rate of
every MBON, Kenyon cell, APL, PAM and PPL1 neuron, because APL and the
non-stimulated KC fraction are the two signatures needed to compare this with the
antennal-lobe failure, and neither has ever been recorded in this series.

Running without --analyze-only or --dry-run executes 42 real Brian2 simulations
and loads the connectome. Importing this file, --dry-run and --analyze-only do
neither.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from flyshi_research.learning import graded_check as gc
from flyshi_research.learning.encoder import KCEncoder
from flyshi_research.learning.readout import circuit_score, load_sign_table

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

# ---- fixed by the pre-statement (spec sections 2-3) --------------------------- #
#: pools are added in this order, so the 400-KC rung IS the unbalanced
#: diagnostic's background and the 500-KC rung is the encoder at its midpoint.
LADDER_POOL_ORDER: Tuple[str, ...] = (
    "recent_change", "time_to_resolution", "liquidity", "signal", "price",
)
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
DURATION_MS = 1000.0
TRIALS = 5
SIGN_TABLE = "circuit_80"
AGGREGATION = "type_mean"
ACTIVE_HZ = 0.5  # an instance counts as "active" above this rate
POPULATIONS: Tuple[str, ...] = ("mbons", "kenyon_cells", "apl_neurons",
                                "pam_dopamine_neurons", "ppl1_dopamine_neurons")

# Planning figures only, measured on the author's machine during the balanced
# run; UNVERIFIED elsewhere and never used by any reported statistic.
SECONDS_PER_SIMULATION = 50.5
SECONDS_PER_BUILD = 4.0


@dataclass(frozen=True)
class Condition:
    name: str
    n_pools: int
    rate_hz: float
    role: str

    @property
    def n_kcs(self) -> int:
        return 100 * self.n_pools

    @property
    def total_drive_hz(self) -> float:
        return self.n_kcs * self.rate_hz

    def pools(self) -> Tuple[str, ...]:
        return LADDER_POOL_ORDER[: self.n_pools]


CONDITIONS: Tuple[Condition, ...] = (
    Condition("ladder_100", 1, 90.0, "ladder rung"),
    Condition("ladder_200", 2, 90.0, "ladder rung"),
    Condition("ladder_300", 3, 90.0, "ladder rung"),
    Condition("ladder_400", 4, 90.0, "ladder rung and background alone"),
    Condition("ladder_500", 5, 90.0, "ladder top; encoder at midpoint"),
    Condition("drive_matched_500at30", 5, 30.0, "5x the KCs at the validated cue's drive"),
    Condition("anchor_100at150", 1, 150.0, "same drive, 1x the KCs, same pool as ladder_100"),
)
BY_NAME: Dict[str, Condition] = {c.name: c for c in CONDITIONS}


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_population_scaling_diagnostic.py"
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
    return p


def output_path(condition: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"population_scaling_{condition}_seed_{seed}.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "population_scaling_summary.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, separators=(",", ":")))
    partial.replace(path)


def planned_pairs() -> Tuple[Tuple[str, int], ...]:
    return tuple((c.name, seed) for c in CONDITIONS for seed in SEEDS)


def missing_pairs(results_dir: Path = RESULTS_DIR) -> List[Tuple[str, int]]:
    return [(name, seed) for name, seed in planned_pairs()
            if not output_path(name, seed, results_dir).exists()]


def stimulus_for(encoder: KCEncoder, condition: Condition) -> Dict[int, float]:
    """The condition's per-KC rates: its nested pools, every KC at one rate."""
    rates: Dict[int, float] = {}
    for pool_name in condition.pools():
        for kc_id in encoder.pools[pool_name].tolist():
            rates[int(kc_id)] = condition.rate_hz
    if len(rates) != condition.n_kcs:
        raise RuntimeError(
            f"{condition.name}: expected {condition.n_kcs} KCs, built {len(rates)}"
        )
    return rates


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def _build_population_simulator():
    """Import Brian2 and return a simulator that returns EVERY population's rates."""
    import sys

    sys.path.insert(0, str(HERE))
    from run_first_learning_test import FastRunnerSimulator
    import check_mb_response as mbr
    from flyshi_research.learning.first_learning import ExperimentConfig

    class PopulationSimulator(FastRunnerSimulator):
        """Adds whole-network rate readout. The spike monitor already records every
        neuron, so APL/PAM/PPL1 rates cost nothing beyond slicing."""

        def __init__(self, cfg: ExperimentConfig) -> None:
            super().__init__(cfg)
            payload = mbr.read_ids()
            flyid2i = self.bundle["flyid2i"]
            self.population_ids: Dict[str, List[int]] = {}
            self.population_index: Dict[str, np.ndarray] = {}
            for name in POPULATIONS:
                ids = [int(r["root_id"]) for r in payload[name]["records"]]
                known = [i for i in ids if i in flyid2i]
                if len(known) != len(ids):
                    raise RuntimeError(f"{name}: {len(ids) - len(known)} IDs absent from the model")
                self.population_ids[name] = known
                self.population_index[name] = np.array([flyid2i[i] for i in known])
            self.mbon_type_labels = [str(r["cell_type"]) for r in payload["mbons"]["records"]]

        def present_populations(
            self, rates_by_kc_id: Mapping[int, float], seed: int,
            duration_ms: float, n_trials: int,
        ) -> Dict[str, np.ndarray]:
            self.bundle["params"]["t_run"] = duration_ms * self._ms
            spikes, _ = self._fr.run_cue_rates(
                self.bundle, dict(rates_by_kc_id), n_trials, seed, "population_scaling")
            n = self.bundle["n"]
            if len(spikes):
                idx = np.array([self.bundle["flyid2i"][f] for f in spikes["flywire_id"]], dtype=int)
                counts = np.bincount(idx, minlength=n)
            else:
                counts = np.zeros(n)
            rate = counts / (duration_ms / 1000.0 * n_trials)
            return {name: rate[index] for name, index in self.population_index.items()}

    return PopulationSimulator(ExperimentConfig())


def simulate_missing(results_dir: Path = RESULTS_DIR, log: Callable[[str], None] = print) -> None:
    todo = missing_pairs(results_dir)
    for name, seed in planned_pairs():
        if (name, seed) not in todo:
            log(f"Output exists, skipping: {output_path(name, seed, results_dir).name}")
    if not todo:
        return

    sim = _build_population_simulator()
    encoder = KCEncoder(sim.kc_ids)
    for name, seed in todo:
        condition = BY_NAME[name]
        rates = stimulus_for(encoder, condition)
        populations = sim.present_populations(rates, seed, DURATION_MS, TRIALS)
        stimulated = sorted(rates)
        _write_json(
            output_path(name, seed, results_dir),
            {
                "condition": name,
                "role": condition.role,
                "n_kcs_driven": condition.n_kcs,
                "per_kc_rate_hz": condition.rate_hz,
                "total_drive_hz": condition.total_drive_hz,
                "pools": list(condition.pools()),
                "stimulated_kc_ids": stimulated,
                "mbon_labels": list(sim.mbon_type_labels),
                "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
                "rates_hz": {p: np.asarray(v, dtype=float).tolist()
                             for p, v in populations.items()},
                "seed": seed,
                "duration_ms": DURATION_MS,
                "trials": TRIALS,
            },
        )
        log(f"{name} (KCs {condition.n_kcs}, {condition.rate_hz:g} Hz), seed {seed}: "
            f"wrote {output_path(name, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# measurement (no verdict: this is a diagnostic)
# --------------------------------------------------------------------------- #
def mean_pairwise_distance(vectors: Sequence[np.ndarray]) -> float:
    return float(np.mean([gc.euclidean(a, b) for a, b in combinations(vectors, 2)]))


def condition_statistics(payloads: Sequence[Mapping]) -> dict:
    """Everything Section 3 of the spec says to report, for one condition."""
    table = load_sign_table(SIGN_TABLE)
    labels = payloads[0]["mbon_labels"]
    mbon = [np.asarray(p["rates_hz"]["mbons"], dtype=float) for p in payloads]
    kc = [np.asarray(p["rates_hz"]["kenyon_cells"], dtype=float) for p in payloads]
    apl = [np.asarray(p["rates_hz"]["apl_neurons"], dtype=float) for p in payloads]
    pam = [np.asarray(p["rates_hz"]["pam_dopamine_neurons"], dtype=float) for p in payloads]
    ppl1 = [np.asarray(p["rates_hz"]["ppl1_dopamine_neurons"], dtype=float) for p in payloads]

    scores = [circuit_score(v, labels, table, AGGREGATION).score for v in mbon]
    kc_ids = payloads[0]["population_ids"]["kenyon_cells"]
    stimulated = set(payloads[0]["stimulated_kc_ids"])
    is_stim = np.array([int(i) in stimulated for i in kc_ids])

    return {
        "n_seeds": len(payloads),
        "n_kcs_driven": payloads[0]["n_kcs_driven"],
        "per_kc_rate_hz": payloads[0]["per_kc_rate_hz"],
        "total_drive_hz": payloads[0]["total_drive_hz"],
        "score_per_seed": [float(s) for s in scores],
        "score_mean": float(np.mean(scores)),
        "score_sd": float(np.std(scores, ddof=1)),
        "mbon_vector_distance_hz": mean_pairwise_distance(mbon),
        "active_mbons": float(np.mean([(v > ACTIVE_HZ).sum() for v in mbon])),
        "mbon_mean_rate_hz": float(np.mean(mbon)),
        "stimulated_kc_mean_rate_hz": float(np.mean([v[is_stim].mean() for v in kc])),
        "nonstimulated_kc_active_fraction": float(
            np.mean([(v[~is_stim] > ACTIVE_HZ).mean() for v in kc])),
        "nonstimulated_kc_mean_rate_hz": float(np.mean([v[~is_stim].mean() for v in kc])),
        "apl_mean_rate_hz": float(np.mean(apl)),
        "apl_per_seed_mean_hz": [float(v.mean()) for v in apl],
        "pam_mean_rate_hz": float(np.mean(pam)),
        "active_pam": float(np.mean([(v > ACTIVE_HZ).sum() for v in pam])),
        "ppl1_mean_rate_hz": float(np.mean(ppl1)),
        "active_ppl1": float(np.mean([(v > ACTIVE_HZ).sum() for v in ppl1])),
    }


def summarise(results_dir: Path = RESULTS_DIR, log: Callable[[str], None] = print) -> Optional[dict]:
    missing = missing_pairs(results_dir)
    if missing:
        log(f"Cannot summarise: missing {len(missing)} of {len(planned_pairs())} condition/seed results")
        return None
    per_condition = {}
    for condition in CONDITIONS:
        payloads = [json.loads(output_path(condition.name, seed, results_dir).read_text())
                    for seed in SEEDS]
        labels = payloads[0]["mbon_labels"]
        if any(p["mbon_labels"] != labels for p in payloads):
            raise ValueError(f"{condition.name}: MBON label order differs between seeds")
        per_condition[condition.name] = condition_statistics(payloads)

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": "docs/design/population-scaling-diagnostic.md",
        "seeds": list(SEEDS),
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
        "conditions": per_condition,
        "ladder": [
            {"condition": c.name, "n_kcs": c.n_kcs,
             "total_drive_hz": c.total_drive_hz,
             "active_mbons": per_condition[c.name]["active_mbons"],
             "score_sd": per_condition[c.name]["score_sd"],
             "mbon_vector_distance_hz": per_condition[c.name]["mbon_vector_distance_hz"]}
            for c in CONDITIONS if c.name.startswith("ladder_")
        ],
        "drive_matched_comparison": {
            "note": ("equal total drive, 5x the KC count; isolates count from drive at "
                     "this one drive level only (spec 4b)"),
            "total_drive_hz": BY_NAME["anchor_100at150"].total_drive_hz,
            "kc_100_at_150": per_condition["anchor_100at150"],
            "kc_500_at_30": per_condition["drive_matched_500at30"],
        },
        "historical_comparison": {
            "note": ("anchor_100at150 vs the cue-A d_AA = 5.10 Hz result: a DIFFERENT "
                     "100-KC pool, so not a replication (spec 4e)"),
            "historical_d_aa_hz": 5.10,
            "anchor_mbon_vector_distance_hz":
                per_condition["anchor_100at150"]["mbon_vector_distance_hz"],
        },
    }
    _write_json(summary_path(results_dir), summary)

    log("=== Population-scaling diagnostic (MEASUREMENT; no verdict, no pass criterion) ===")
    log(f"{'condition':<24}{'KCs':>5}{'driveHz':>9}{'scoreSD':>9}{'vecdist':>9}"
        f"{'actMBON':>9}{'APLHz':>8}{'nonstimKC%':>11}")
    for c in CONDITIONS:
        s = per_condition[c.name]
        log(f"{c.name:<24}{s['n_kcs_driven']:>5}{s['total_drive_hz']:>9,.0f}"
            f"{s['score_sd']:>9.2f}{s['mbon_vector_distance_hz']:>9.2f}"
            f"{s['active_mbons']:>9.1f}{s['apl_mean_rate_hz']:>8.1f}"
            f"{100 * s['nonstimulated_kc_active_fraction']:>10.1f}%")
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def dry_run(results_dir: Path = RESULTS_DIR, log: Callable[[str], None] = print) -> int:
    todo = missing_pairs(results_dir)
    total = len(planned_pairs())
    seconds = len(todo) * SECONDS_PER_SIMULATION + (SECONDS_PER_BUILD if todo else 0.0)
    log("Population-scaling diagnostic: DRY RUN")
    log("spec: docs/design/population-scaling-diagnostic.md (PRE-STATED)")
    log("DIAGNOSTIC, not a validation: no pass criterion, no verdict is produced")
    log(f"ladder pool order: {list(LADDER_POOL_ORDER)} (nested; 400 KCs = background alone)")
    log(f"{'condition':<24}{'KCs':>5}{'rateHz':>8}{'driveHz':>10}  role")
    for c in CONDITIONS:
        log(f"{c.name:<24}{c.n_kcs:>5}{c.rate_hz:>8.0f}{c.total_drive_hz:>10,.0f}  {c.role}")
    log(f"seeds: {list(SEEDS)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials")
    log(f"recorded populations: {list(POPULATIONS)}")
    log(f"planned simulations: {total}  (already done: {total - len(todo)}, to run: {len(todo)})")
    log(f"estimated runtime: {seconds / 60:.1f} min "
        f"({SECONDS_PER_SIMULATION:g} s per simulation + one {SECONDS_PER_BUILD:g} s build; "
        "measured on the author's machine, UNVERIFIED elsewhere)")
    log("No connectome loaded, no model built, no simulation run, nothing written.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.dry_run and args.analyze_only:
        raise SystemExit("--dry-run and --analyze-only are mutually exclusive")
    if args.dry_run:
        return dry_run(args.results_dir)
    if not args.analyze_only:
        simulate_missing(args.results_dir)
    return 0 if summarise(results_dir=args.results_dir) is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
