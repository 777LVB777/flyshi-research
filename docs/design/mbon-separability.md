# Are the two cues separable from MBON activity alone?

**Status: analysis of existing data. No new simulations were run.** This
re-analyzes the per-MBON firing rates already saved from the KC-direct speed
calibration (`repro/mushroom_body/results/speed_calibration_mbon_rates_kc_size_100_kc_seed_20260316_pn_rate_hz_150_seed_20260316.csv`),
which covers two disjoint 100-Kenyon-cell cue sets ("cue A", "cue B") across 12
grid cells (4 durations × 3 trial counts). The earlier stand-alone KC-direct run
is **not** extra data: the calibration reused it as the 1000 ms / 5-trial cell,
so it is already included.

Derived tables written alongside this doc (both < 1 KB):
`repro/mushroom_body/results/mbon_separability_per_cell.csv` and
`repro/mushroom_body/results/mbon_separability_consistency.csv`.

## The question

Our design reads decisions from mushroom-body output-neuron (MBON) firing rates.
The two cue sets produce MBON patterns that differ by a **cosine distance of only
~0.05** (0 = identical, 1 = orthogonal). If that small difference is just noise,
no learning rule can use it and the design fails. If it is a real, structured
signal, a readout can exploit it. This document tests which.

## Verdict

**VIABLE — CONFIRMED against the pre-stated criterion.** The noise-floor
experiment (§4) has now been run: at the definitive fine cell (1000 ms / 5
trials) the cue-A-vs-cue-B difference is **R = 15.6×** the same-cue run-to-run
noise (pre-stated threshold: ≥ 3.0), and **all 8** consistently-discriminating
MBONs individually clear the 3×-standard-deviation bar. The ~0.05 cosine
difference is a real, reproducible, concentrated signal, not noise. **One
qualification:** at the cheap 100 ms / 1 trial cell the ratio is only **R =
1.9×** — the signal is still real there but *too noisy for a single run per
decision*, so the study must average trials or use a longer duration at that end
(§4 decision rule, secondary clause). Details below.

The headline reason the "0.05" is misleading: cosine distance is **normalized by
the total MBON activity**, which is large because both cues drive many of the
same MBONs hard in common. The *raw* discriminating differences are **not** tiny
— they are tens of Hz on specific MBONs (max per-MBON |A−B| = 30–50 Hz; whole-
vector Euclidean distance 76–100 Hz). The small cosine number reflects a large
shared "common-mode" activity with a smaller but very real difference riding on
top, concentrated in a handful of MBONs.

---

## 1. How many MBONs differ by more than plausible noise; are they consistent?

Per cell, using an **approximate Poisson counting-noise model** (see §3 and its
caveat), the count of MBONs whose |A−B| exceeds both 3× the modeled noise and the
rate-quantization step ("n_signif") ranges from 18 (at 1000 ms / 5 trials, the
finest-resolution cell) down to 0 (at the coarsest short/low-trial cells). That
drop is **a measurement-resolution effect, not a loss of signal** — shorter, lower-
trial runs quantize rates coarsely (step rises to 10 Hz at 100 ms / 1 trial), so
the noise test simply loses power. The cosine distance and the discriminating
MBON identities stay stable across all cells.

**The same MBONs are consistently the most discriminating, with a consistent
direction, across all 12 independent cells.** Times each MBON appears in a cell's
top-10 |A−B| list (out of 12), mean signed difference (A−B), and whether its sign
never flips:

| MBON (cell_type) | in top-10 of | mean A−B (Hz) | sign consistent? |
|---|---:|---:|:--:|
| MBON03 (…90316) | 12/12 | −32.4 | yes (B>A always) |
| MBON02 (…52340) | 12/12 | +22.7 | yes (A>B always) |
| MBON07 (…90134) | 12/12 | −22.6 | yes (B>A always) |
| MBON07 (…02365) | 12/12 | −23.5 | yes (B>A always) |
| MBON04 (…34376) | 11/12 | −29.0 | yes (B>A always) |
| MBON26 (…81440) | 11/12 | −17.3 | yes (B>A always) |
| MBON11 (…01833) | 10/12 | +18.8 | yes (A>B always) |
| MBON23 (…67206) | 9/12 | −15.9 | yes (B>A always) |
| MBON35 (…02938) | 6/12 | +15.1 | yes (A>B always) |
| MBON09 (…64847) | 6/12 | −13.4 | yes (B>A always) |

(Full list in `mbon_separability_consistency.csv`. Ellipsis shows the last 5
digits of the FlyWire root ID; several cell types have multiple neurons, e.g.
two MBON07 and several MBON09, listed separately by ID.)

**Consistency across the 12 cells is the strongest evidence available in hand.**
The cells use different durations and trial counts, so each is effectively a
different simulation realization. If the ~0.05 difference were noise, the
most-different MBONs and their signs would vary randomly from cell to cell.
Instead the same ~8 MBONs top the list with a fixed sign every time. Made
quantitative: the per-MBON difference vector (A−B across all MBONs) has a
**pairwise cosine similarity between cells of median 0.94 (min 0.85, all 66 cell-
pairs > 0.80).** Independent realizations point the same way. That is what real
structure looks like; noise would give near-zero alignment.

## 2. Distribution of per-MBON differences: uniform, or concentrated?

**Concentrated — the workable case.** The difference is not spread thinly across
all MBONs; a few carry most of it. Fraction of the total squared difference held
by the single largest-differing MBON is **0.14–0.29**, and by the top 5 MBONs is
**0.52–0.64**, in every cell. So roughly half to two-thirds of the entire A-vs-B
signal lives in just five MBONs, and about a fifth in one. A readout that weights
those few strongly-discriminating MBONs can exploit the signal even though the
whole-population cosine distance is small. This is exactly the case §2 of the
task hoped for over the "nearly identical everywhere" alternative.

## 3. Separability quantified honestly

Because each grid cell has only 2 conditions (one A, one B), **we cannot train or
test a classifier** — there are no repeats to train on and no held-out examples to
test on. What we can report per cell (all in `mbon_separability_per_cell.csv`):

| Cell | cosine dist | Euclidean (Hz) | max\|diff\| (Hz) | SNR (max/std) | top5 frac |
|---|---:|---:|---:|---:|---:|
| 1000×5 | 0.0510 | 78.6 | 35.2 | 2.85 | 0.56 |
| 1000×2 | 0.0482 | 76.4 | 33.0 | 2.70 | 0.55 |
| 1000×1 | 0.0506 | 78.9 | 33.0 | 2.58 | 0.54 |
| 500×5 | 0.0484 | 76.4 | 33.2 | 2.76 | 0.56 |
| 500×2 | 0.0491 | 77.9 | 30.0 | 2.27 | 0.53 |
| 500×1 | 0.0516 | 79.0 | 30.0 | 2.18 | 0.57 |
| 200×5 | 0.0462 | 75.6 | 34.0 | 2.74 | 0.53 |
| 200×2 | 0.0469 | 75.8 | 32.5 | 2.64 | 0.52 |
| 200×1 | 0.0506 | 79.7 | 35.0 | 2.52 | 0.55 |
| 100×5 | 0.0619 | 85.0 | 40.0 | 2.84 | 0.57 |
| 100×2 | 0.0706 | 93.3 | 50.0 | 3.10 | 0.64 |
| 100×1 | 0.0827 | 100.0 | 50.0 | 2.83 | 0.58 |

- **(a) Cosine distance** — small (~0.05) and stable at long durations; rises to
  ~0.08 at 100 ms. That rise is **not** "more separation": at coarse resolution,
  small common-mode rates quantize to zero and drop out of the shared component,
  so the surviving vector is dominated by the big discriminators, mechanically
  inflating cosine distance. It measures *relative* pattern difference and is the
  most comparable single number across cells.
- **(b) Euclidean distance** — the raw size of the difference, 76–100 Hz. Also
  inflated at short durations (a neuron firing once in 100 ms reads as 10 Hz), so
  absolute distances are not directly comparable across cells.
- **(c) Signal-to-noise proxy (max |diff| ÷ standard deviation of diffs across
  MBONs)** — 2.2–3.1 in every cell. This says the largest discriminating MBON
  stands 2–3× above the spread of all MBON differences. It is a *within-vector*
  contrast (one MBON vs. the population), **not** a signal-vs-run-noise ratio.

**What these can tell us:** the difference is large in absolute terms,
concentrated in a few MBONs, and structurally the same across 12 independent
realizations. **What they cannot tell us:** the precise probability that a
readout will decode A vs B correctly on a *fresh* run — that needs repeats (§5).
The SNR proxy in (c) is contrast within one measurement, not signal over noise.

## 4. Could the cross-cell variation be trial-count / noise rather than cue signal?

Partly yes, and this is the key honest limitation:

- **Trial count changes noise averaging.** More trials average more spike
  realizations, so 5-trial cells are less noisy than 1-trial cells; fewer trials
  and shorter durations also coarsen rate quantization. This is why "n_signif"
  (§1) falls at short/low-trial cells while the underlying signal (cosine
  distance, discriminating-MBON identity, sign) persists. The variation *in the
  noise test* across cells is largely a resolution artifact.
- **Crucially, cue A and cue B within a cell are NOT independent noise draws.**
  `run_condition()` in `check_mb_response.py` resets the RNG to the same seed
  (`np.random.seed(20260316)`, `brian_seed(20260316)`) **before every condition**
  (lines 456–457). Every condition in every cell used the one seed 20260316. So
  the Poisson input streams for A and B are paired (the i-th stimulated cell in A
  and in B receives the same input realization), and **there is no run of the same
  cue under a different seed anywhere in this dataset.**
- **Therefore we cannot measure the noise floor directly, and cannot compute a
  rigorous signal-to-noise ratio from this data.** The Poisson noise model used
  for "n_signif" is an assumption (spiking-LIF output is not guaranteed Poisson,
  and the shared seed may make the true A−B noise *smaller* than the independent-
  Poisson assumption), so **n_signif is an approximate, unverified indicator**,
  not a measured false-positive-controlled count.

The cross-cell consistency (§1) is strong *circumstantial* evidence of real
signal precisely because it does not rely on the noise model — but it is not a
substitute for a direct noise measurement, since the 12 cells differ in duration
and trials and so are not clean replicates of one condition.

### The noise-floor experiment (specified here; not yet run)

Rerun the **same** cue set (cue A) under **different simulation seeds**, at a
fixed cell, holding the KC-set choice fixed, so the only thing that varies is the
simulation's random noise. This measures the noise directly:

- Keep `--kc-set-seed 20260316` so the identical 100 Kenyon cells are stimulated
  every time.
- Run **cue A only** at **5 new seeds** (`20260317, 20260318, 20260319, 20260320,
  20260321`), all distinct from the existing `20260316`, at **two cells**: the
  low-noise fine cell (**1000 ms / 5 trials**) and the coarse cheap cell
  (**100 ms / 1 trial**). That is 10 runs.
- The spread among the 5 cue-A vectors is the **noise** (A vs A′). The existing
  cue-B vector at each cell (from the calibration data, seed 20260316) is the
  comparison, giving the **signal** (A vs B).

The dedicated script `repro/mushroom_body/run_single_cue.py` runs exactly one cue
at one seed and saves its per-MBON rates; it reuses `check_mb_response.py`'s
KC-direct machinery and is restartable (skips a seed whose output file already
exists).

### Pre-stated acceptance criterion (recorded BEFORE the run)

Written now, before any noise run exists, so the outcome cannot move the bar.
All vectors are per-MBON firing-rate vectors over the union of MBONs nonzero in
any cue-A noise run or in the existing cue-B run at that cell; missing MBONs are
filled with 0. Distances are Euclidean (Hz).

Define, **per cell**, using the 5 new-seed cue-A vectors `A_1..A_5` and the
existing cue-B vector `B` (seed 20260316):

- **Noise (A vs A′)** `d_AA` = the mean Euclidean distance between distinct pairs
  of the 5 cue-A vectors — the typical run-to-run difference of the *same* cue.
- **Signal (A vs B)** `d_AB` = the mean Euclidean distance from each of the 5
  cue-A vectors to `B` — the typical cue-A-to-cue-B difference.
- **Separation ratio** `R = d_AB / d_AA`.

**Decision rule (numeric margin = 3×):**

1. **Separability is CONFIRMED (signal is real, not noise) if `R ≥ 3.0` at the
   fine cell (1000 ms / 5 trials).** This is the definitive, low-noise test: the
   cue-A-vs-cue-B difference must be at least three times the same-cue run-to-run
   spread. If `1.0 ≤ R < 3.0`, the signal is present but not by a clear margin
   ("marginal"); if `R < 1.0`, the ~0.05 difference is **not** distinguishable
   from noise and the readout design fails.
2. **Cheap-setting usability (secondary):** the 100 ms / 1 trial cell is usable
   for a single run per decision if `R ≥ 3.0` there too; if `1.0 ≤ R < 3.0`, the
   signal is real at that cell but too noisy for a single shot, so the study must
   average trials (or use the fine cell); if `R < 1.0`, that cell is unusable per
   decision.
3. **Per-MBON companion check (interpretability, not the gate):** on the eight
   consistently-discriminating MBONs identified in §1 (MBON03·90316, MBON02·52340,
   MBON07·90134, MBON07·02365, MBON04·34376, MBON26·81440, MBON11·01833,
   MBON23·67206), the criterion should also hold per-MBON — `|mean_A − B| ≥ 3 ×
   SD_across_seeds(A)` — for a **majority (≥ 5 of 8)** at the fine cell. This is a
   sanity check that the ratio is driven by the expected MBONs, not an artifact.

**One-sided caveat, stated in advance:** this measures noise from **cue A only**
(as scoped). It therefore assumes cue B has comparable run-to-run noise; the true
noise on the A−B difference is roughly `√(SD_A² + SD_B²) ≈ √2 · SD_A` if the two
are symmetric. Comparing `d_AB` to the cue-A-only `d_AA` with a **3× margin**
deliberately builds in headroom against that assumption. The symmetry assumption
is **unverified**; running cue B at the same 5 seeds (optional, 10 more runs)
would remove it. The existing seed-20260316 cue-A data is *not* mixed into the
noise estimate (its RNG is paired with B — see §4); it is available only as
corroboration.

### Exact commands to run yourself

Run in a normal terminal (each is a Brian2 simulation). On macOS prefix with
`caffeinate -i` so the machine does not sleep. Order runs the cheap cell first.
Runs are restartable — re-running skips any seed already saved.

```bash
# --- Cheap cell: 100 ms / 1 trial, cue A, 5 seeds ---
for S in 20260317 20260318 20260319 20260320 20260321; do
  caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
    .venv-shiu/bin/python repro/mushroom_body/run_single_cue.py \
    --cue a --seed "$S" --duration-ms 100 --trials 1 \
    --pn-rate 150 --kc-set-size 100 --kc-set-seed 20260316
done

# --- Fine cell: 1000 ms / 5 trials, cue A, 5 seeds (the definitive test) ---
for S in 20260317 20260318 20260319 20260320 20260321; do
  caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
    .venv-shiu/bin/python repro/mushroom_body/run_single_cue.py \
    --cue a --seed "$S" --duration-ms 1000 --trials 5 \
    --pn-rate 150 --kc-set-size 100 --kc-set-seed 20260316
done
```

Each run writes one small CSV,
`repro/mushroom_body/results/mbon_noise_floor_cue_a_duration_ms_<D>_trials_<T>_pn_rate_hz_150_kc_size_100_kc_seed_20260316_seed_<S>.csv`.

### Noise-floor results (run 2026-09-17), against the pre-stated criterion

All 10 runs completed (cue A, seeds 20260317–20260321, both cells;
logs `run_log_noise_cheap.txt`, `run_log_noise_fine.txt`). Metrics computed
**exactly as pre-stated above** — the criterion was not changed. Support = union
of MBONs nonzero in any cue-A noise run or in the existing cue-B run; absent
MBONs are zero (see the support note below).

| Cell | d_AA (noise, Hz) | d_AB (signal, Hz) | **R = d_AB/d_AA** | verdict |
|---|---:|---:|---:|---|
| **1000 ms / 5 trials (fine)** | 5.10 | 79.44 | **15.57** | **CONFIRMED** (≥ 3.0) |
| **100 ms / 1 trial (cheap)** | 46.09 | 88.25 | **1.91** | marginal (1.0–3.0): real but too noisy for a single run |

**Primary verdict (fine cell): CONFIRMED.** R = 15.6 is far above the pre-stated
3.0 threshold — the cue-A-vs-cue-B difference (~79 Hz) is ~15× the same-cue
run-to-run spread (~5 Hz). The ~0.05 cosine separation carries real, decodable
information.

**Cheap-cell usability (secondary): marginal.** R = 1.91 falls in the pre-stated
1.0–3.0 band: the signal is real (it exceeds the noise) but not by the clear 3×
margin, so a single 100 ms / 1 trial run per decision is too noisy to rely on.
Per the pre-stated rule, the study must **average trials** (or use a longer
duration) at the cheap end, or use the fine cell. The earlier speed-calibration
finding that "100 ms / 1 trial separates as well as 1000 ms / 5 trials" was based
on the *cosine distance of a single pair*, which does not see run-to-run noise;
this noise-floor test now shows that single-shot cheap runs are in fact much
noisier, and the calibration's cost saving must be spent on trial-averaging, not
on dropping to one short trial.

**Per-MBON companion check** (|mean_A − B| ≥ 3 × SD_across_seeds(A), on the 8
consistent discriminators):

- **Fine cell: 8 / 8 pass** (majority ≥ 5 → MET). Every discriminator's
  cue-A rate is stable across seeds (SD ≤ ~0.9 Hz) while its A−B gap is 17–36 Hz.
- **Cheap cell: 6 / 8 pass.** MBON07·90134 (|A−B| = 16.0 vs 3·SD = 16.4) and
  MBON11·01833 (14.0 vs 16.4) narrowly fail — both because coarse 100 ms / 1
  trial quantization (10 Hz steps) both shrinks their measured gap and inflates
  their per-seed SD (5.48 Hz). This is consistent with the cheap cell being
  noise-limited, not with the discriminators being spurious.

**Noise structure (are the discriminators the noisiest MBONs?) — No.** At the
fine cell the mean across-seed SD of the 8 discriminators is **0.51 Hz** versus
**0.41 Hz** for all other MBONs — essentially the same, and both ~30–70× smaller
than the discriminators' A−B gaps. Only 4 of the 8 discriminators appear in the
top-10 noisiest MBONs, and the two single noisiest MBONs (both MBON12 variants)
are *not* discriminators. At the cheap cell the discriminators are, if anything,
slightly *less* noisy than average (3.98 vs 4.71 Hz). **The result is therefore
not an artifact of the discriminating MBONs being unusually noisy** — the
opposite of the weakening scenario flagged in the task.

**Support / varying-count note (pre-stated data-handling).** Nonzero MBON counts
varied across runs — 34–38 (cue A) and 33 (cue B) at the fine cell; 23–29 (cue A)
and 30 (cue B) at the cheap cell. The saved CSVs store *only* MBONs that fired
(rate > 0), so a MBON absent from a run's file had rate **exactly 0** in that run
— zero-fill on the union support is the faithful value, not an imputation choice.
This does not affect the verdict: at the fine cell R = 15.6 has enormous margin,
and the per-MBON check is computed per neuron regardless of union membership. At
the cheap cell the coarse quantization (which drives the count variation) is
already the reason R is only marginal, and zero-fill is the correct reading of
"did not fire."

**Remaining unverified caveats (unchanged by this experiment):** the noise was
measured from cue A only, so the A-vs-B noise is assumed symmetric (the 3× margin
builds in headroom; running cue B at these seeds would remove the assumption);
and this is for two *specific* random 100-KC cue sets, not the eventual
market-feature encoding.

## 5. Limitations, restated plainly

- No classifier, no decode-accuracy number: only 2 conditions per cell in the
  original calibration data. (The noise-floor experiment in §4 added 5 same-cue
  repeats per cell, which measured the noise floor directly — see those results.)
- The noise floor is **now measured** at the two tested cells (fine: R = 15.6;
  cheap: R = 1.9); it is *not* measured at the other 10 grid cells, and the noise
  was sampled from cue A only (cue-B symmetry assumed).
- The Poisson-noise threshold behind "n_signif" (§1) is an **unverified** modeling
  assumption; treat those counts as indicative only. The §4 measured noise, not
  this model, is the basis for the verdict.
- All results are for two *specific* random 100-KC cue sets. Whether a similar
  margin holds for arbitrary market-feature encodings (the real design input) is
  **not** established here and must be checked once the encoding exists.
- Absolute Hz distances are inflated at short durations by coarse quantization;
  compare cells using cosine distance, not Euclidean.

## Conclusion

The two cues **are** separable from MBON activity alone. The ~0.05 cosine
distance understates the case: the discriminating differences are large (tens of
Hz), concentrated in ~5–8 MBONs, sign-stable, and reproduced with median-0.94
alignment across 12 independent duration/trial realizations. This is the
"few strongly different MBONs a readout can weight" regime, not "identical
everywhere."

**Verdict: viable — CONFIRMED.** The owed item — a direct noise-floor measurement
via repeat-seed runs of a single cue (§4) — has now been run and confirms the
result: at 1000 ms / 5 trials the signal is **15.6× the run-to-run noise** (pre-
stated threshold 3.0), with all 8 discriminating MBONs individually clearing the
bar. The decodable margin at the fine setting is now measured, not merely
plausible. The remaining qualification is operational, not existential: single
100 ms / 1 trial runs are too noisy (R = 1.9), so the study must average trials
or use a longer duration; and the margin for the eventual market-feature encoding
(rather than these specific 100-KC cue sets) still has to be checked once that
encoding exists.
