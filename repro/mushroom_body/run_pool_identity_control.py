#!/usr/bin/env python3
"""Pool-identity control: the price pool against a substitute pool at matched drive.

Pre-stated protocol: docs/design/pool-identity-control.md, written before this code
and before any run of the substitute pool. Nothing here may be changed to fit a
result.

DIAGNOSTIC, NOT A VALIDATION (is_a_validation: false, has_pass_criterion: false, no
verdict field). It measures; it does not judge. The summary passes the same
enforcement check as the other diagnostics (check_no_verdict of the realistic-drive
runner).

Price arm P: the left-only mirrored validation's saved presentations at v = 0.56,
0.73, 0.94 (never re-simulated, except one reproducibility check). Substitute arm
Q: the same stimuli with the price pool's 100 KCs replaced by 100 other LEFT KCs
(substitute-pool seed 20260930, disjoint from all five feature pools and the
balance pool) at the same rate. Same 500 KCs' worth of drive, same D_YES and D_NO,
same background, same seeds; only which KCs carry the value differs.
3 values x 2 framings x 6 seeds = 36 substitute simulations + 1 check = 37.

Running without --analyze-only or --dry-run executes 37 real Brian2 simulations and
loads the connectome. Importing this file, --dry-run and --analyze-only do neither.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations, permutations
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # sibling runners; import no Brian2 at module level

from flyshi_research.learning import graded_check as gc  # noqa: E402
from flyshi_research.learning.encoder import KCEncoder, NO, YES  # noqa: E402
from flyshi_research.learning.readout import (  # noqa: E402
    circuit_score_difference,
    load_sign_table,
)
import run_graded_encoding_left_only_mirrored as mirrored  # noqa: E402
from run_left_only_pool_diagnostic import kc_side_map, left_kc_ids  # noqa: E402
from run_left_only_realistic_drive_diagnostic import (  # noqa: E402
    MAX_FILE_BYTES,
    PER_TRIAL_POPULATIONS,
    _present_with_trials,
    _write_json,
    check_no_verdict,
)
from run_population_scaling_diagnostic import POPULATIONS, SECONDS_PER_BUILD  # noqa: E402

RESULTS_DIR = HERE / "results"
IDS_PATH = HERE / "neuron_ids_783.json"
SPEC = "docs/design/pool-identity-control.md"

# ---- FIXED by the pre-statement (spec sections 2-5) ------------------------------- #
VALUES: Tuple[float, ...] = (0.56, 0.73, 0.94)
FRAMINGS: Tuple[str, ...] = (YES, NO)
PRIMARY_SEED = 20260316
SEEDS: Tuple[int, ...] = (20260316, 20260317, 20260318, 20260319, 20260320, 20260321)
REPEAT_SEEDS: Tuple[int, ...] = SEEDS[1:]
SUBSTITUTE_SEED = 20260930
SUBSTITUTE_POOL = "substitute"
REPLACED_POOL = "price"
POOL_SIZE = 100
N_KCS_PER_FRAMING = 500
ZERO = 0.50  # c(0.50) = 0 exactly in both arms, by mirroring; never simulated
CHANGES: Tuple[Tuple[float, float], ...] = (
    (0.50, 0.94), (0.50, 0.56), (0.50, 0.73), (0.56, 0.73), (0.73, 0.94), (0.56, 0.94),
)
PRIMARY_CHANGE: Tuple[float, float] = (0.50, 0.94)
NOISE_MARGIN = 3.0
REPRO_CHECK: Tuple[float, str, int] = (0.94, YES, 20260316)
SIGN_TABLE = mirrored.SIGN_TABLE
AGGREGATION = mirrored.AGGREGATION
DURATION_MS = mirrored.DURATION_MS
TRIALS = mirrored.TRIALS
POOL_SIDE = "left"

WITHIN, BEYOND = "within_noise", "beyond_noise"
PRICE_FLOOR_ONLY = "beyond the price arm's floor only"
REPRO_CHANGED = "cross-arm comparison across a simulator change"

# Planning figures only (spec section 8); UNVERIFIED elsewhere; never used by a statistic.
SECONDS_PER_SIMULATION = mirrored.SECONDS_PER_SIMULATION
SECONDS_PER_SIMULATION_OLD = mirrored.SECONDS_PER_SIMULATION_OLD


def parser() -> argparse.ArgumentParser:
    command = (
        "caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/run_pool_identity_control.py"
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


def _key(value: float) -> str:
    return format(value, ".2f").replace(".", "p")


def change_name(change: Tuple[float, float]) -> str:
    return f"{change[0]:.2f}->{change[1]:.2f}"


def output_path(value: float, framing: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"pool_identity_Q_value_{_key(value)}_{framing}_seed_{seed}.json"


def price_arm_path(value: float, framing: str, seed: int, results_dir: Path = RESULTS_DIR) -> Path:
    """The validation's saved presentation; the price arm is read, not re-run."""
    return mirrored.output_path(value, framing, seed, results_dir)


def repro_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "pool_identity_repro_check.json"


def summary_path(results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / "pool_identity_control_summary.json"


def planned_presentations() -> Tuple[Tuple[float, str, int], ...]:
    """Every substitute (value, framing, seed), seed-major."""
    return tuple((value, framing, seed)
                 for seed in SEEDS for value in VALUES for framing in FRAMINGS)


def missing_presentations(results_dir: Path = RESULTS_DIR) -> List[Tuple[float, str, int]]:
    return [p for p in planned_presentations() if not output_path(*p, results_dir).exists()]


def missing_price_arm(results_dir: Path = RESULTS_DIR) -> List[Tuple[float, str, int]]:
    return [p for p in planned_presentations() if not price_arm_path(*p, results_dir).exists()]


def planned_simulations() -> int:
    return len(planned_presentations()) + 1  # + the reproducibility check


def simulations_to_run(results_dir: Path = RESULTS_DIR) -> int:
    return len(missing_presentations(results_dir)) + (0 if repro_path(results_dir).exists() else 1)


# --------------------------------------------------------------------------- #
# the stimuli (pure data; no Brian2, no connectome) - spec section 2
# --------------------------------------------------------------------------- #
def draw_substitute_pool(left_ids: Sequence[int], excluded: Sequence[int],
                         seed: int = SUBSTITUTE_SEED, size: int = POOL_SIZE) -> List[int]:
    """Sort the left KCs outside every encoder pool, permute with ``seed``, take
    the first ``size``, sort (spec section 2.1)."""
    taken = {int(i) for i in excluded}
    candidates = np.array(sorted(int(i) for i in left_ids if int(i) not in taken), dtype=np.int64)
    if candidates.size < size:
        raise RuntimeError(f"only {candidates.size} candidate KCs for a {size}-KC pool")
    chosen = candidates[np.random.default_rng(seed).permutation(candidates.size)[:size]]
    return sorted(int(i) for i in chosen)


def substitute_record(record: Mapping, price_ids: Sequence[int], q_ids: Sequence[int]) -> dict:
    """``record`` with the price pool's KCs replaced by Q's, at the same rate."""
    price_set = {int(i) for i in price_ids}
    rate = float(record["pool_rates_hz"][REPLACED_POOL])
    rates = {int(k): float(r) for k, r in record["rates_by_kc_id"].items()
             if int(k) not in price_set}
    rates.update({int(q): rate for q in q_ids})
    pools = {name: list(ids) for name, ids in record["pools"].items() if name != REPLACED_POOL}
    pools[SUBSTITUTE_POOL] = [int(q) for q in q_ids]
    pool_rates = {name: float(r) for name, r in record["pool_rates_hz"].items()
                  if name != REPLACED_POOL}
    pool_rates[SUBSTITUTE_POOL] = rate
    return {
        "rates_by_kc_id": rates,
        "stimulated_kc_ids": sorted(rates),
        "pools": pools,
        "pool_rates_hz": pool_rates,
        "total_drive_hz": float(np.sum(np.array(sorted(rates.values()), dtype=float))),
    }


def _check_arms(value: float, framing: str, p: Mapping, q: Mapping,
                price_ids: Sequence[int], q_ids: Sequence[int]) -> None:
    """Spec section 2.2, checks 1-4, for one stimulus."""
    where = f"v={value} {framing}"
    if len(q["rates_by_kc_id"]) != N_KCS_PER_FRAMING:
        raise RuntimeError(f"{where}: Q drives {len(q['rates_by_kc_id'])} KCs, "
                           f"expected {N_KCS_PER_FRAMING}")
    if not np.isclose(q["total_drive_hz"], p["total_drive_hz"], rtol=0.0, atol=1e-6):
        raise RuntimeError(f"{where}: Q drive {q['total_drive_hz']:g} Hz differs from P's "
                           f"{p['total_drive_hz']:g} Hz")
    if sorted(q["rates_by_kc_id"].values()) != sorted(p["rates_by_kc_id"].values()):
        raise RuntimeError(f"{where}: the per-KC rate multisets differ between arms")
    for name, ids in p["pools"].items():
        if name == REPLACED_POOL:
            continue
        if (q["pools"].get(name) != ids
                or q["pool_rates_hz"].get(name) != p["pool_rates_hz"][name]
                or any(q["rates_by_kc_id"].get(int(i)) != p["rates_by_kc_id"][int(i)]
                       for i in ids)):
            raise RuntimeError(f"{where}: background pool {name} differs between arms")
    difference = set(p["rates_by_kc_id"]) ^ set(q["rates_by_kc_id"])
    if difference != {int(i) for i in price_ids} | {int(i) for i in q_ids}:
        raise RuntimeError(f"{where}: the arms differ in more than the price pool and Q")


def build_stimuli(ids_path: Path = IDS_PATH) -> dict:
    """Both arms at every value, with every spec section 2 check.

    Aborts unless: every encoder pool is left (the validation's own checks run
    first, via its ``build_pairs``); Q is 100 left KCs, disjoint from all 800
    encoder-pool KCs; each Q stimulus matches its P counterpart in KC count, total
    drive, rate multiset and background, differing only by price pool <-> Q;
    NO_Q(v) equals YES_Q(1-v) bit-for-bit; nothing is clipped.
    """
    pairs = mirrored.build_pairs(ids_path)  # left-only guard and validation section 3.1
    left = left_kc_ids(ids_path)
    encoder = KCEncoder(left)
    encoder_pools = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    encoder_pools["__balance__"] = sorted(int(i) for i in encoder.balance_pool)
    excluded = [i for ids in encoder_pools.values() for i in ids]
    q_ids = draw_substitute_pool(left, excluded)

    sides = kc_side_map(ids_path)
    wrong = [i for i in q_ids if sides.get(i) != POOL_SIDE]
    if wrong:
        raise RuntimeError(f"{len(wrong)} substitute KC(s) are not left-hemisphere: {wrong[:5]}")
    if len(q_ids) != POOL_SIZE or len(set(q_ids)) != POOL_SIZE:
        raise RuntimeError("the substitute pool is not 100 distinct KCs")
    if set(q_ids) & set(excluded):
        raise RuntimeError("the substitute pool overlaps an encoder pool")

    price_ids = encoder_pools[REPLACED_POOL]
    pool_ids = {name: sorted(int(i) for i in ids) for name, ids in encoder.pools.items()}
    stimuli: Dict[float, dict] = {}
    for value in VALUES:
        pair = pairs[value]
        if pair[YES]["pools"][REPLACED_POOL] != price_ids:
            raise RuntimeError(f"v={value}: the validation's price pool is not the encoder's")
        arms = {}
        for framing in FRAMINGS:
            q = substitute_record(pair[framing], price_ids, q_ids)
            _check_arms(value, framing, pair[framing], q, price_ids, q_ids)
            arms[framing] = {"P": pair[framing], "Q": q}
        mirror = encoder.option_b_stimuli(
            {"price": mirrored.presented_value(value, NO), **mirrored.BACKGROUND},
            variant=mirrored.VARIANT).yes
        if mirror.was_clipped:
            raise RuntimeError(f"v={value}: a feature value was clipped")
        mirror_q = substitute_record(mirrored._stimulus_record(mirror, pool_ids), price_ids, q_ids)
        if mirror_q["rates_by_kc_id"] != arms[NO]["Q"]["rates_by_kc_id"]:
            raise RuntimeError(f"v={value}: NO_Q(v) is not YES_Q(1-v) bit-for-bit")
        stimuli[value] = {**arms, "d_yes_hz": pair["d_yes_hz"], "d_no_hz": pair["d_no_hz"]}
    return {"substitute_pool": q_ids, "encoder_pools": encoder_pools, "by_value": stimuli}


# --------------------------------------------------------------------------- #
# simulation (the only part that constructs the model)
# --------------------------------------------------------------------------- #
def _presentation_payload(sim, stim: Mapping, means: Mapping, trials: Mapping,
                          value: float, framing: str, seed: int) -> dict:
    return {
        "value": value,
        "framing": framing,
        "presented_price_value": mirrored.presented_value(value, framing),
        "variant": mirrored.VARIANT,
        "pool_side": POOL_SIDE,
        "pools": stim["pools"],
        "pool_rates_hz": stim["pool_rates_hz"],
        "n_kcs_driven": len(stim["stimulated_kc_ids"]),
        "total_drive_hz": stim["total_drive_hz"],
        "stimulated_kc_ids": stim["stimulated_kc_ids"],
        "mbon_labels": list(sim.mbon_type_labels),
        "population_ids": {p: list(sim.population_ids[p]) for p in POPULATIONS},
        "rates_hz": {p: np.asarray(v, dtype=float).tolist() for p, v in means.items()},
        "per_trial_rates_hz": {p: np.asarray(v, dtype=float).tolist() for p, v in trials.items()},
        "seed": seed,
        "duration_ms": DURATION_MS,
        "trials": TRIALS,
    }


def simulate_missing(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
                     log: Callable[[str], None] = print) -> None:
    todo = missing_presentations(results_dir)
    repro_todo = not repro_path(results_dir).exists()
    for presentation in planned_presentations():
        if presentation not in todo:
            log(f"Output exists, skipping: {output_path(*presentation, results_dir).name}")
    if not repro_todo:
        log(f"Output exists, skipping: {repro_path(results_dir).name}")
    if not todo and not repro_todo:
        return

    from run_population_scaling_diagnostic import _build_population_simulator

    built = build_stimuli(ids_path)  # every section 2 check, before the model is built
    sim = _build_population_simulator()

    if repro_todo:  # first, so an environment change shows before 36 runs are spent
        value, framing, seed = REPRO_CHECK
        stim = built["by_value"][value][framing]["P"]
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], seed,
                                             DURATION_MS, TRIALS)
        payload = _presentation_payload(sim, stim, means, trials, value, framing, seed)
        payload["arm"] = "price"
        payload["purpose"] = "reproducibility check against the validation's saved file"
        _write_json(repro_path(results_dir), payload, max_bytes=MAX_FILE_BYTES)
        log(f"reproducibility check v={value:.2f} {framing} seed {seed}: "
            f"wrote {repro_path(results_dir).name}")

    for value, framing, seed in todo:
        stim = built["by_value"][value][framing]["Q"]
        means, trials = _present_with_trials(sim, stim["rates_by_kc_id"], seed,
                                             DURATION_MS, TRIALS)
        payload = _presentation_payload(sim, stim, means, trials, value, framing, seed)
        payload.update({
            "arm": "substitute",
            "substitute_pool_seed": SUBSTITUTE_SEED,
            "replaces_pool": REPLACED_POOL,
            "nominal_value_rate_hz": stim["pool_rates_hz"][SUBSTITUTE_POOL],
            "pair_d_yes_hz": built["by_value"][value]["d_yes_hz"],
            "pair_d_no_hz": built["by_value"][value]["d_no_hz"],
        })
        _write_json(output_path(value, framing, seed, results_dir), payload,
                    max_bytes=MAX_FILE_BYTES)
        log(f"Q v={value:.2f} {framing:<3} ({stim['pool_rates_hz'][SUBSTITUTE_POOL]:.1f} Hz on Q, "
            f"{stim['total_drive_hz']:,.0f} Hz), seed {seed}: "
            f"wrote {output_path(value, framing, seed, results_dir).name}")


# --------------------------------------------------------------------------- #
# statistics (pure numpy) - spec sections 3-5
# --------------------------------------------------------------------------- #
def splits(seeds: Sequence[int] = SEEDS) -> List[Tuple[Tuple[int, ...], Tuple[int, ...]]]:
    """The ten 3+3 splits: each triple containing the first seed, and its complement."""
    first, rest = seeds[0], tuple(seeds[1:])
    out = []
    for pair in combinations(rest, 2):
        h1 = (first,) + pair
        out.append((h1, tuple(s for s in seeds if s not in h1)))
    return out


def _distance(x, y) -> float:
    return float(np.linalg.norm(np.asarray(x, dtype=float) - np.asarray(y, dtype=float)))


def _mean(by_seed: Mapping[int, object], seeds: Sequence[int]):
    return np.mean([np.asarray(by_seed[s], dtype=float) for s in seeds], axis=0)


def split_floor(by_seed: Mapping[int, object]) -> float:
    """W: mean over the ten splits of the distance between the two half means."""
    return float(np.mean([_distance(_mean(by_seed, h1), _mean(by_seed, h2))
                          for h1, h2 in splits()]))


def split_cross(q: Mapping[int, object], p: Mapping[int, object]) -> float:
    """X: mean over the ten splits, both orientations (20 terms), of the distance
    between a Q half mean and the P mean over the complementary seeds."""
    terms = []
    for h1, h2 in splits():
        terms.append(_distance(_mean(q, h1), _mean(p, h2)))
        terms.append(_distance(_mean(q, h2), _mean(p, h1)))
    return float(np.mean(terms))


def split_cosine(by_seed: Mapping[int, object]) -> float:
    return float(np.mean([cosine(_mean(by_seed, h1), _mean(by_seed, h2))
                          for h1, h2 in splits()]))


def cosine(x, y) -> float:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    nx, ny = np.linalg.norm(x), np.linalg.norm(y)
    return float(x @ y / (nx * ny)) if nx > 0 and ny > 0 else float("nan")


def single_seed_distance(a: Mapping[int, object], b: Optional[Mapping[int, object]] = None) -> float:
    """Over the five repeat seeds: the validation's d_change (``b`` None: pairs i<j
    within ``a``) or the cross distance (ordered pairs i != j, ``a`` against ``b``)."""
    if b is None:
        return float(np.mean([_distance(a[i], a[j]) for i, j in combinations(REPEAT_SEEDS, 2)]))
    return float(np.mean([_distance(a[i], b[j]) for i, j in permutations(REPEAT_SEEDS, 2)]))


def reading(cross: float, floor_p: float, floor_q: float) -> Tuple[str, str]:
    """(reading against 3 x W_P, reading against 3 x max(W_P, W_Q)); spec 5.2."""
    primary = BEYOND if cross > NOISE_MARGIN * floor_p else WITHIN
    robust = BEYOND if cross > NOISE_MARGIN * max(floor_p, floor_q) else WITHIN
    return primary, robust


def compare_change(ds_p: Mapping[int, float], ds_q: Mapping[int, float],
                   dc_p: Mapping[int, np.ndarray], dc_q: Mapping[int, np.ndarray],
                   single_seed: bool) -> dict:
    """Every spec section 4 statistic for one change."""
    mean_p, mean_q = float(_mean(ds_p, SEEDS)), float(_mean(ds_q, SEEDS))
    paired = [float(ds_q[s] - ds_p[s]) for s in SEEDS]
    w_s_p, w_s_q, x_s = split_floor(ds_p), split_floor(ds_q), split_cross(ds_q, ds_p)
    w_v_p, w_v_q, x_v = split_floor(dc_p), split_floor(dc_q), split_cross(dc_q, dc_p)
    s_read, s_robust = reading(x_s, w_s_p, w_s_q)
    v_read, v_robust = reading(x_v, w_v_p, w_v_q)

    vec_p, vec_q = _mean(dc_p, SEEDS), _mean(dc_q, SEEDS)
    norm_p, norm_q = float(np.linalg.norm(vec_p)), float(np.linalg.norm(vec_q))
    along = (vec_q @ vec_p) / (norm_p ** 2) * vec_p if norm_p > 0 else np.zeros_like(vec_q)
    orthogonal = float(np.linalg.norm(vec_q - along))
    return {
        "scalar": {
            "per_seed_P_hz": [float(ds_p[s]) for s in SEEDS],
            "per_seed_Q_hz": [float(ds_q[s]) for s in SEEDS],
            "mean_P_hz": mean_p,
            "mean_Q_hz": mean_q,
            "ratio_R": mean_q / mean_p if mean_p != 0 else None,
            "paired_difference_per_seed_hz": paired,
            "paired_difference_mean_hz": float(np.mean(paired)),
            "paired_difference_sd_hz": float(np.std(paired, ddof=1)),
            "floor_W_P_hz": w_s_p,
            "floor_W_Q_hz": w_s_q,
            "cross_X_hz": x_s,
            "threshold_hz": NOISE_MARGIN * w_s_p,
            "reading": s_read,
            "reading_against_larger_floor": s_robust,
        },
        "vector": {
            "norm_P_hz": norm_p,
            "norm_Q_hz": norm_q,
            "norm_ratio": norm_q / norm_p if norm_p > 0 else None,
            "cosine_P_Q": cosine(vec_p, vec_q),
            "orthogonal_component_hz": orthogonal,
            "orthogonal_fraction": orthogonal / norm_q if norm_q > 0 else None,
            "split_half_cosine_P": split_cosine(dc_p),
            "split_half_cosine_Q": split_cosine(dc_q),
            "floor_W_P_hz": w_v_p,
            "floor_W_Q_hz": w_v_q,
            "cross_X_hz": x_v,
            "threshold_hz": NOISE_MARGIN * w_v_p,
            "reading": v_read,
            "reading_against_larger_floor": v_robust,
            "d_change_P_hz": single_seed_distance(dc_p) if single_seed else None,
            "d_change_Q_hz": single_seed_distance(dc_q) if single_seed else None,
            "d_cross_hz": single_seed_distance(dc_q, dc_p) if single_seed else None,
        },
    }


def evaluate(mbons: Mapping[Tuple[str, float, str, int], Sequence[float]],
             labels: Sequence[str]) -> Dict[str, dict]:
    """All six changes. ``mbons[(arm, value, framing, seed)]`` is the MBON vector,
    arm "P" or "Q"."""
    table = load_sign_table(SIGN_TABLE)
    score: Dict[Tuple[str, float, int], float] = {}
    contrast: Dict[Tuple[str, float, int], np.ndarray] = {}
    n = None
    for arm in ("P", "Q"):
        for value in VALUES:
            for seed in SEEDS:
                yes = np.asarray(mbons[(arm, value, YES, seed)], dtype=float)
                no = np.asarray(mbons[(arm, value, NO, seed)], dtype=float)
                score[(arm, value, seed)] = float(
                    circuit_score_difference(yes, no, labels, table, AGGREGATION))
                contrast[(arm, value, seed)] = yes - no
                n = yes.size

    def s(arm, value, seed):
        return 0.0 if value == ZERO else score[(arm, value, seed)]

    def c(arm, value, seed):
        return np.zeros(n) if value == ZERO else contrast[(arm, value, seed)]

    out: Dict[str, dict] = {}
    for a, b in CHANGES:
        ds = {arm: {seed: s(arm, b, seed) - s(arm, a, seed) for seed in SEEDS} for arm in "PQ"}
        dc = {arm: {seed: c(arm, b, seed) - c(arm, a, seed) for seed in SEEDS} for arm in "PQ"}
        out[change_name((a, b))] = {
            "primary": (a, b) == PRIMARY_CHANGE,
            **compare_change(ds["P"], ds["Q"], dc["P"], dc["Q"], single_seed=a != ZERO),
        }
    return out


def price_floor_only(part: Mapping) -> bool:
    """Beyond 3 x W_P but within 3 x max(W_P, W_Q): spec 5.2's robustness flag."""
    return part["reading"] == BEYOND and part["reading_against_larger_floor"] == WITHIN


def interpretation(primary: Mapping) -> str:
    """The pre-stated meaning of the primary readings (spec sections 5.2-5.3).

    The section 5.3 table is used only when no beyond-noise reading is flagged.
    A flagged reading "is not attributed to pool identity" (spec 5.2), so every
    table row that would attribute it is withheld, and each part is stated alone.
    """
    s, v = primary["scalar"]["reading"], primary["vector"]["reading"]
    flag_s, flag_v = price_floor_only(primary["scalar"]), price_floor_only(primary["vector"])
    if flag_s or flag_v:
        if flag_s:
            scalar = f"scalar {PRICE_FLOOR_ONLY}: not attributed to pool identity"
        else:
            scalar = f"scalar {s.replace('_', ' ')}" + (" against both floors" if s == BEYOND else "")
        if flag_v:
            vector = f"vector {PRICE_FLOOR_ONLY}: not attributed to pool identity"
        elif v == BEYOND:
            vector = ("vector beyond noise against both floors: pool identity is present "
                      "in the MBON vector")
        else:
            vector = "vector within noise"
        return f"{scalar}; {vector} (spec 5.2; no row of the spec 5.3 table applies)"
    if s == WITHIN and v == WITHIN:
        return ("scalar and vector within noise: the scalar signal is largely generic drive; "
                "neither S nor the MBON vector distinguishes the pools at matched drive")
    if s == WITHIN:
        return ("scalar within, vector beyond noise: the scalar signal is largely generic "
                "drive; pool identity is present in the MBON vector but not in the "
                "per-type-mean score")
    if v == BEYOND:
        return "scalar and vector beyond noise: pool identity contributes to S; see R"
    return ("scalar beyond, vector within noise: unexpected; reported as a scalar-only "
            "difference and not interpreted further")


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
def check_constants() -> None:
    """The runner's constants must equal the pre-stated ones."""
    if NOISE_MARGIN != 3.0 or NOISE_MARGIN != gc.NOISE_MARGIN:
        raise ValueError("noise margin differs from the pre-stated factor 3")
    if VALUES != (0.56, 0.73, 0.94) or not set(VALUES) <= set(mirrored.VALUES):
        raise ValueError("values differ from the pre-stated subset of set B")
    if SEEDS != (20260316, 20260317, 20260318, 20260319, 20260320, 20260321) \
            or set(SEEDS) != set(mirrored.SEEDS):
        raise ValueError("seeds differ from the pre-statement")
    if SUBSTITUTE_SEED != 20260930 or POOL_SIZE != 100:
        raise ValueError("substitute pool differs from the pre-statement")
    if PRIMARY_CHANGE != (0.50, 0.94) or REPRO_CHECK != (0.94, YES, 20260316):
        raise ValueError("primary change or reproducibility check differs from the pre-statement")


def _check_saved(payload: Mapping, stim: Mapping, value: float, framing: str, seed: int,
                 what: str) -> None:
    mirrored.check_presentation_file(payload)
    if (payload["stimulated_kc_ids"] != stim["stimulated_kc_ids"]
            or payload["pool_rates_hz"] != stim["pool_rates_hz"]
            or payload["framing"] != framing or payload["seed"] != seed):
        raise ValueError(f"{what} v={value} {framing} seed {seed}: saved stimulus differs from "
                         "the pre-stated one; no summary")


def repro_comparison(check: Mapping, saved: Mapping) -> dict:
    diffs = {}
    for population in ("mbons", "kenyon_cells", "apl_neurons"):
        a = np.asarray(check["rates_hz"][population], dtype=float)
        b = np.asarray(saved["rates_hz"][population], dtype=float)
        diffs[population] = float(np.max(np.abs(a - b))) if a.shape == b.shape else None
    identical = (check["population_ids"] == saved["population_ids"]
                 and all(d == 0.0 for d in diffs.values()))
    return {"presentation": {"value": REPRO_CHECK[0], "framing": REPRO_CHECK[1],
                             "seed": REPRO_CHECK[2]},
            "identical": identical,
            "max_abs_difference_hz": diffs,
            "label": None if identical else REPRO_CHANGED}


def summarise(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
              log: Callable[[str], None] = print) -> Optional[dict]:
    check_constants()
    missing_q = missing_presentations(results_dir)
    missing_p = missing_price_arm(results_dir)
    if missing_q or missing_p or not repro_path(results_dir).exists():
        log(f"No summary: missing {len(missing_q)} of {len(planned_presentations())} substitute "
            f"files, {len(missing_p)} of {len(planned_presentations())} price-arm files, "
            f"reproducibility check {'present' if repro_path(results_dir).exists() else 'missing'}")
        return None
    built = build_stimuli(ids_path)  # re-runs every section 2 check
    sides = kc_side_map(ids_path)
    q_ids = built["substitute_pool"]

    payloads: Dict[Tuple[str, float, str, int], dict] = {}
    for value, framing, seed in planned_presentations():
        arms = built["by_value"][value][framing]
        p = json.loads(price_arm_path(value, framing, seed, results_dir).read_text())
        _check_saved(p, arms["P"], value, framing, seed, "price arm")
        q = json.loads(output_path(value, framing, seed, results_dir).read_text())
        _check_saved(q, arms["Q"], value, framing, seed, "substitute arm")
        payloads[("P", value, framing, seed)] = p
        payloads[("Q", value, framing, seed)] = q
    check = json.loads(repro_path(results_dir).read_text())
    mirrored.check_presentation_file(check)
    value, framing, seed = REPRO_CHECK
    _check_saved(check, built["by_value"][value][framing]["P"], value, framing, seed,
                 "reproducibility check")

    labels = payloads[("P", VALUES[0], YES, PRIMARY_SEED)]["mbon_labels"]
    if any(p["mbon_labels"] != labels for p in list(payloads.values()) + [check]):
        raise ValueError("MBON label order differs between files; no summary")

    changes = evaluate({k: p["rates_hz"]["mbons"] for k, p in payloads.items()}, labels)
    primary = changes[change_name(PRIMARY_CHANGE)]
    repro = repro_comparison(check, payloads[("P", *REPRO_CHECK)])

    recruitment = [mirrored.presentation_recruitment(payloads[("Q", *p)], sides)
                   for p in planned_presentations()]
    q_measured = []
    for v in VALUES:
        for fr in FRAMINGS:
            rows = []
            for sd in SEEDS:
                pl = payloads[("Q", v, fr, sd)]
                position = {int(k): i for i, k in
                            enumerate(pl["population_ids"]["kenyon_cells"])}
                rates = np.asarray(pl["rates_hz"]["kenyon_cells"], dtype=float)
                rows.append(float(rates[[position[i] for i in q_ids]].mean()))
            imposed = built["by_value"][v][fr]["Q"]["pool_rates_hz"][SUBSTITUTE_POOL]
            q_measured.append({"value": v, "framing": fr, "imposed_rate_hz": imposed,
                               "measured_rate_per_seed_hz": rows,
                               "measured_over_imposed": float(np.mean(rows)) / imposed})

    summary = {
        "prestated_diagnostic": True,
        "is_a_validation": False,
        "has_pass_criterion": False,
        "spec": SPEC,
        "encoder": {"pool_side": POOL_SIDE, "variant": mirrored.VARIANT,
                    "framing_rule": "mirrored", "pool_seed": 20260401},
        "substitute_pool": {"seed": SUBSTITUTE_SEED, "size": POOL_SIZE, "kc_ids": q_ids,
                            "replaces": REPLACED_POOL,
                            "excluded": "all five feature pools and the balance pool"},
        "values": list(VALUES),
        "seeds": list(SEEDS),
        "splits": [[list(h1), list(h2)] for h1, h2 in splits()],
        "noise_margin": NOISE_MARGIN,
        "value_rates_hz": {f"{v:.2f}": {YES: mirrored.nominal_rate_hz(v),
                                        NO: mirrored.nominal_rate_hz(1 - v)} for v in VALUES},
        "pair_drive_hz": {f"{v:.2f}": {"D_YES": built["by_value"][v]["d_yes_hz"],
                                       "D_NO": built["by_value"][v]["d_no_hz"]} for v in VALUES},
        "price_arm_source": mirrored.SPEC,
        "primary_change": change_name(PRIMARY_CHANGE),
        "primary_interpretation": interpretation(primary),
        "primary_price_floor_only": {
            part: price_floor_only(primary[part]) for part in ("scalar", "vector")},
        "changes": changes,
        "reproducibility_check": repro,
        "substitute_rate_measured": q_measured,
        "recruitment_by_substitute_presentation": recruitment,
        "ignited_substitute_presentations": sum(r["ignited"] for r in recruitment),
        "notes": {
            "status": "diagnostic measurement; the readings are pre-stated labels, not a "
                      "criterion, and authorise nothing",
            "secondary": "only the primary change carries a pre-stated reading; the other "
                         "five are secondary",
            "price_floor_only": f"a {BEYOND} reading that is {WITHIN} against 3 x max(W_P, W_Q) "
                                f"is reported as '{PRICE_FLOOR_ONLY}', not as pool identity",
            "one_draw": "one substitute draw: Q's own identity is confounded with the price "
                        "pool's",
            "within_noise": "a within-noise reading means reproduced within the measured "
                            "noise, not that identity is irrelevant",
        },
    }
    check_no_verdict(summary)
    _write_json(summary_path(results_dir), summary)

    log("=== Pool-identity control (DIAGNOSTIC; no verdict, no pass criterion) ===")
    if not repro["identical"]:
        log(f"reproducibility check NOT identical ({repro['max_abs_difference_hz']}): "
            f"every number below is a {REPRO_CHANGED}")
    else:
        log("reproducibility check: identical to the validation's saved file")
    log(f"{'change':<11}{'S_P':>9}{'S_Q':>9}{'R':>7}{'X_S':>7}{'3W_S':>7}  scalar"
        f"{'':<8}{'cos':>7}{'X_V':>8}{'3W_V':>8}  vector")
    for name, ch in changes.items():
        sc, vc = ch["scalar"], ch["vector"]
        r = "--" if sc["ratio_R"] is None else f"{sc['ratio_R']:.2f}"
        log(f"{name:<11}{sc['mean_P_hz']:>9.2f}{sc['mean_Q_hz']:>9.2f}{r:>7}"
            f"{sc['cross_X_hz']:>7.2f}{sc['threshold_hz']:>7.2f}  {sc['reading']:<14}"
            f"{vc['cosine_P_Q']:>7.3f}{vc['cross_X_hz']:>8.2f}{vc['threshold_hz']:>8.2f}  "
            f"{vc['reading']}{'  (primary)' if ch['primary'] else ''}")
    for part, flag in summary["primary_price_floor_only"].items():
        if flag:
            log(f"primary {part}: {PRICE_FLOOR_ONLY}")
    log(f"primary: {summary['primary_interpretation']}")
    log(f"ignited substitute presentations: {summary['ignited_substitute_presentations']} "
        f"of {len(recruitment)}")
    log(f"Wrote {summary_path(results_dir).name}")
    return summary


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #
def estimated_seconds(n_todo: int, per_simulation: float = SECONDS_PER_SIMULATION) -> float:
    return n_todo * per_simulation + (SECONDS_PER_BUILD if n_todo else 0.0)


def dry_run(results_dir: Path = RESULTS_DIR, ids_path: Path = IDS_PATH,
            log: Callable[[str], None] = print) -> int:
    check_constants()
    n_todo = simulations_to_run(results_dir)
    total = planned_simulations()
    log("Pool-identity control: DRY RUN")
    log(f"spec: {SPEC} (PRE-STATED)")
    log("DIAGNOSTIC, not a validation: no pass criterion, no verdict is produced")
    try:
        built = build_stimuli(ids_path)
        log(f"substitute pool: {POOL_SIZE} left KCs, seed {SUBSTITUTE_SEED}, disjoint from "
            f"{sum(len(v) for v in built['encoder_pools'].values())} encoder-pool KCs")
        log("section 2 checks: left-only pools, matched drive and KC count, same rate "
            "multiset and background, arms differ only by price pool <-> Q, "
            "NO_Q(v) == YES_Q(1-v), no clipping: all hold")
        log(f"{'v':>5}{'YES Hz':>8}{'NO Hz':>8}{'D_YES':>9}{'D_NO':>9}")
        for v in VALUES:
            b = built["by_value"][v]
            log(f"{v:>5.2f}{mirrored.nominal_rate_hz(v):>8.1f}"
                f"{mirrored.nominal_rate_hz(1 - v):>8.1f}{b['d_yes_hz']:>9,.0f}{b['d_no_hz']:>9,.0f}")
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        log(f"section 2 checks could not be completed from {ids_path}: {exc}")
    missing_p = missing_price_arm(results_dir)
    log(f"price arm: {len(planned_presentations()) - len(missing_p)} of "
        f"{len(planned_presentations())} validation files present (read, not re-simulated)")
    log(f"seeds: {list(SEEDS)}; values {list(VALUES)}; primary change "
        f"{change_name(PRIMARY_CHANGE)}")
    log(f"presentation: {DURATION_MS:g} ms x {TRIALS} trials; per trial: "
        f"{list(PER_TRIAL_POPULATIONS)}")
    log(f"planned simulations: {total} (36 substitute + 1 reproducibility check)  "
        f"(already done: {total - n_todo}, to run: {n_todo})")
    log(f"estimated runtime: {estimated_seconds(n_todo) / 60:.1f} min at "
        f"{SECONDS_PER_SIMULATION:g} s per simulation "
        f"({estimated_seconds(n_todo, SECONDS_PER_SIMULATION_OLD) / 60:.1f} min at "
        f"{SECONDS_PER_SIMULATION_OLD:g} s) + one {SECONDS_PER_BUILD:g} s build; "
        "author's machine, UNVERIFIED elsewhere")
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
