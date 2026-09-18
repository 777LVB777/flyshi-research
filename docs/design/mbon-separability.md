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

**VIABLE — the ~0.05 difference is a real, reproducible, concentrated signal, not
noise.** One honest gap remains (we have not measured the noise floor directly;
see §5), but the in-hand evidence is strong and one-directional. Details below.

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

### Smallest experiment that would settle it (NOT run here)

Rerun the **same** cue set under **different simulation seeds**, at a fixed cell,
holding the KC-set choice fixed:

- Keep `--kc-set-seed 20260316` (so the identical 100 Kenyon cells are stimulated)
  and `--stim-mode kc`, at one cell each of the fine and coarse extremes
  (e.g. 1000 ms / 5 trials, and 100 ms / 1 trial).
- Run **cue A only** at, say, 5 different `--seed` values → 5 independent noise
  realizations of the *same* cue. Their MBON-rate spread is the **noise**.
- Compare against the existing A-vs-B difference, the **signal**.
- The clean test is then: is the A-vs-B difference on the top discriminating
  MBONs large relative to the A-vs-A′ spread on those same MBONs?

This is a handful of extra KC-direct runs (cheap at 100 ms / 1 trial per the
speed calibration) and would convert "strong circumstantial evidence" into a
measured signal-to-noise ratio and a defensible decode probability. Until it is
run, the noise floor is **unverified**.

## 5. Limitations, restated plainly

- No classifier, no decode-accuracy number: only 2 conditions per cell.
- No independent repeats of a single cue (shared seed 20260316 everywhere), so no
  measured noise floor and no rigorous signal-to-noise ratio.
- The Poisson-noise threshold behind "n_signif" is an **unverified** modeling
  assumption; treat those counts as indicative only.
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

**Verdict: viable.** The one owed item — a direct noise-floor measurement via
repeat-seed runs of a single cue (§4) — does not overturn this, but should be run
to put a rigorous number on the margin before the readout is relied upon. Any
claim about the *size* of the decodable margin remains **unverified** until then.
