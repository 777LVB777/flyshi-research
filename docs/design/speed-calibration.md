# Speed calibration for `--stim-mode kc` (pre-stated, before running)

This document is written **before** `repro/mushroom_body/calibrate_speed.py` is
executed, so the grid, the separation-score definition, and the acceptance
rule cannot be shifted retroactively based on results.

> **Correction note (2026-09-18), added after the run.** This calibration's
> headline result — that **100 ms / 1 trial separates the two cues as well as
> 1000 ms / 5 trials** — was based on the **cosine distance of a single A/B
> pair per cell**. That single-pair measure **cannot see run-to-run noise**: it
> compares one cue-A run against one cue-B run, with no repeat of either cue to
> reveal how much a rate would jitter from seed to seed. The later noise-floor
> experiment (see [`mbon-separability.md`](mbon-separability.md)) repeated the
> same cue under five seeds and found the cheap 100 ms / 1 trial setting is in
> fact **much noisier** — signal-to-noise ratio only **1.9×**, versus **15.6×**
> at 1000 ms / 5 trials. **That experiment supersedes the timing/separation
> conclusion below for the purpose of choosing a run setting.** Corrected
> planning assumption: budget **~28 s per run at 1000 ms / 5 trials on a quiet
> machine** (the wall-clock timings *within* this calibration are host-load
> dominated and unusable — see "Two competing cost models" — but the clean
> same-cell noise-floor runs measured ~28 s each), and remember the **Option B
> readout needs two runs per decision**. A cheaper setting is only usable if its
> run-to-run noise is re-checked and averaged down (e.g. more trials or a longer
> window), not by dropping to a single short trial.

## Purpose

`--stim-mode kc` (see `docs/reproduction/mushroom_body_check.md`, "KC-direct
stimulation: result") was found to be "contained": two disjoint 100-KC sets
produce zero overlap in active KCs and only rate-level (not identity-level)
differences at the MBON readout. The full planned study (Option B readout:
two stimuli per decision) needs on the order of **~80,000 stimulus runs**,
and at the reference setting (150 Hz, 5 trials, 1000 ms) a single condition
run currently costs roughly 10-30 s in the typical case, based on 15 prior
runs logged in `repro/mushroom_body/run_log_*.txt` (median 23 s, range
16-184 s — the high end driven by two documented unexplained-timing outliers,
see `mushroom_body_check.md`, "Timing anomaly: kc_set_b runtime"). At even
the low end of that range, 80,000 runs is infeasible (80,000 x 10 s ≈ 222
hours; at the high end, 80,000 x 30 s ≈ 667 hours — days to weeks either
way). This calibration sweeps trial count and trial duration to find the
cheapest configuration that still separates two disjoint KC sets at the
MBON readout, so the full study can run at a viable per-run cost.

## Grid

- `duration_ms` in `{1000, 500, 200, 100}`
- `trials` in `{5, 2, 1}`
- 12 grid cells (`duration_ms` x `trials`); each cell runs **both** disjoint
  KC sets (`set_a`, `set_b`) with the same `--kc-set-size 100`,
  `--kc-set-seed 20260316`, `--pn-rate 150`.
- **Baseline is run once per duration** (4 baseline runs total, not one per
  grid cell), at `trials = 5` — the largest trial count in the grid, chosen
  as the most conservative check that the unstimulated network stays silent
  at that duration. The same baseline result is reused as the reference for
  all three trial-count cells at that duration.
- Reference cell for all "relative to reference" comparisons:
  `duration_ms=1000, trials=5` (the setting already validated in
  `mushroom_body_check.md`).

This is implemented in `calibrate_speed.py` by importing and reusing
`check_mb_response.py`'s existing KC-direct machinery
(`select_disjoint_kc_sets`, `run_condition`, `jaccard`, annotation/ID
loading) — no simulation or rate-analysis logic is duplicated.

## Separation score: definition

For a given grid cell, let `mbon_a` and `mbon_b` be the per-MBON nonzero rate
maps (`root_id -> rate_hz`) for conditions `kc_set_a` and `kc_set_b`
respectively (from `run_condition`'s `mbons_nonzero` output — MBONs with rate
0 in a condition are simply absent from that condition's map).

1. Let `support` = the sorted union of MBON root IDs that are nonzero in
   *either* condition.
2. Build two vectors over `support`, filling 0 for any MBON in `support` that
   is zero in that particular condition.
3. **Separation score = 1 − cosine_similarity(vector_a, vector_b)**, i.e.
   cosine *distance* between the two per-MBON rate vectors, restricted to
   `support`.

Because MBON rates are non-negative, cosine similarity over this support is
always in `[0, 1]`, so **the separation score is always in `[0, 1]`**: `0`
means set A and set B drive the MBON population in identical relative
proportions (no separation); `1` means fully separated (orthogonal MBON
readouts).

**Degenerate cases (defined here, before running, to avoid ad hoc judgment
calls later):**
- If `support` is empty (neither condition drives *any* MBON above 0 Hz),
  the score is **undefined** and reported as `None`/blank — there is nothing
  to compare, and this is different from "separated."
- If `support` is non-empty but one condition's vector is entirely zero over
  `support` (i.e. one condition drives some MBON that the other never
  touches, and drives nothing else in `support`), the dot product is
  literally 0, so similarity is treated as `0` and the distance is `1.0` —
  maximal separation, by convention, since the two conditions share no
  active MBON in that case.

The compact raw per-MBON rate vectors themselves (for both conditions, every
grid cell) are saved alongside the summary, so the separation score can be
recomputed or re-derived by hand if needed.

## Acceptance rule (pre-stated)

A grid cell (a candidate cheaper `duration_ms`/`trials` setting) is
**acceptable** if, relative to the reference cell (`duration_ms=1000,
trials=5`):

1. `separation_score(cell) / separation_score(reference) >= 0.9`, **and**
2. Non-stimulated KC active fraction stays **below 10%** on both hemispheres,
   in both `kc_set_a` and `kc_set_b` (i.e. `max` of the four
   left/right x A/B fractions `< 0.10`).

Both conditions must hold. If the reference cell's own separation score is
`None` (undefined) or `<= 0`, no cell can be judged acceptable by this rule,
and that is reported rather than silently defaulted to pass or fail.

The **cheapest acceptable cell** (by total wall-clock time for `set_a` +
`set_b`) is the calibration's recommended setting for the full ~80,000-run
study. This document does not pre-judge which cell that will be.

## Runtime estimate (before running)

### Empirical basis

`repro/mushroom_body/run_log_*.txt` contains 15 prior "Elapsed time" lines,
all from runs at `duration_ms=1000, trials=5` (duration was never varied in
any prior run, so these logs alone cannot empirically distinguish the two
cost models below — that is one of the things this grid will resolve):

```
19, 23, 23   (run_log_dan_kc_off.txt: baseline, odor_a, odor_b)
20, 22, 22   (run_log_kckc_off.txt: baseline, odor_a, odor_b)
18, 65, 52   (run_log_pn50.txt: baseline, odor_a, odor_b)
16, 27, 25   (run_log_diagnostics.txt: baseline, odor_a, odor_b)
25, 34, 184  (run_log_kc_direct.txt: baseline, kc_set_a, kc_set_b)
```

Min/median/mean/max = 16 / 23 / 38.3 / 184 s. Two values (65 s and 52 s in
`run_log_pn50.txt`; 184 s in `run_log_kc_direct.txt`) are documented
unexplained host-load anomalies (`mushroom_body_check.md`, "Timing anomaly:
kc_set_b runtime") — not attributed to `--pn-rate`, stim mode, or any other
swept parameter. Excluding those 3, the remaining 12 runs have
median 22.5 s / mean 22.8 s. Dividing by 5 trials (= 5 stimulus-seconds at
1000 ms, so the two quantities are numerically identical here) gives an
empirical per-stimulus-second/per-trial rate of **~4.6 s (median, all 15
runs)** up to **~7.67 s (mean, outliers included)**.

### Two competing cost models

- **Stimulus-second model**: cost scales with
  `duration_ms/1000 * trials`. This is the model implied by "run for less
  simulated time = pay less."
- **Trial-dominated model**: `model.py`'s `run_trial()` calls
  `create_model()` — which reads the full connectivity parquet and rebuilds
  the entire ~138k-neuron network — once **per trial**, and
  `check_mb_response.run_condition()` runs trials serially (`n_proc=1`, no
  parallel workers). Under this model, cost is dominated by trial **count**,
  largely independent of `duration_ms`, because most of the per-trial cost is
  the fixed network-rebuild, not Brian2's `net.run()` integration time.

Applying the empirical rates above to the full grid (12 cells, each running
`set_a` + `set_b`, plus 4 baselines at `trials=5`):

| Model | Rate used | Total | Total (min) |
|---|---|---|---|
| Stimulus-second | 4.6 s/stim-s (median) | 174 s | 2.9 |
| Stimulus-second | 7.67 s/stim-s (mean, w/ outliers) | 290 s | 4.8 |
| Trial-dominated | 4.5 s/trial (clean median, outliers excluded) | 378 s | 6.3 |
| Trial-dominated | 7.67 s/trial (mean, w/ outliers) | 644 s | 10.7 |

**Most conservative estimate across both models: 644 s (~10.7 min).** This is
comfortably under the ~45-minute threshold, so **no grid reduction is
proposed** — the full grid above runs as specified.

### Reuse: the reference cell is already available

The `duration_ms=1000, trials=5` cell — the grid's single most expensive
cell, and the one that includes the documented 184 s anomaly — was already
run as a plain `--stim-mode kc` diagnostic in a prior turn, with identical
`--pn-rate 150 --seed 20260316 --kc-set-size 100 --kc-set-seed 20260316`
(`repro/mushroom_body/results/mb_response_seed_20260316_trials_5_duration_ms_1000_pn_rate_hz_150_stim_kc_size_100_kc_seed_20260316.json`).
`calibrate_speed.py` detects this file (`seed_cache_from_existing_run`),
verifies its parameters match exactly, and reuses it instead of
re-simulating — saving ~243 s (25 + 34 + 184) of duplicate work if this is a
fresh run. That lowers the realistic total further, to roughly 5-9 minutes
for the 11 remaining cells plus 3 remaining baselines.

### If the estimate had exceeded 45 minutes

It does not, under either model, but the pre-stated fallback is: **drop
`trials=2`** (keep only `trials` in `{5, 1}`) at every duration, cutting 12
grid cells to 8 (~33% less work). Tradeoff: `trials=2` is the grid's only
interior sample of the duration/trials interaction — dropping it means the
acceptance decision rests on just the two extremes (5 and 1 trials) per
duration, so a non-monotonic effect at `trials=2` (e.g. a cost or separation
cliff that isn't visible at the endpoints) would be missed. This fallback is
not applied here since it is not needed.

## Outputs

- `repro/mushroom_body/results/speed_calibration_summary_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv` —
  one row per grid cell: wall-clock times, stimulated-KC mean rate,
  non-stimulated KC active fraction (left/right, both sets), nonzero-MBON
  counts, MBON identity Jaccard, separation score, ratio to reference, and
  `passes_acceptance`.
- `repro/mushroom_body/results/speed_calibration_mbon_rates_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv` —
  compact raw per-MBON rate vectors (nonzero only) for every grid cell and
  condition, backing the separation-score computation.
- `repro/mushroom_body/results/speed_calibration_kc_size_.../` — per-baseline
  and per-cell cached JSON, enabling restart (an interrupted run skips any
  cell whose output file already exists).

## Exact run command

```bash
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/calibrate_speed.py --pn-rate 150 --seed 20260316 --kc-set-size 100 --kc-set-seed 20260316
```

Preview the plan first without simulating anything:

```bash
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/calibrate_speed.py --dry-run
```

The real run executes many short Brian2 simulations serially over an
estimated ~5-11 minutes (see "Runtime estimate" above); on macOS, prefix with
`caffeinate -i` so the machine does not sleep mid-run:

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/calibrate_speed.py
```
