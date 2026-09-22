# Balanced Option-B encoding: FAIL, diagnosis, and candidate redesigns

**Status: the balanced Option-B encoder is NOT VIABLE as currently specified.**
The pre-stated re-validation in
[`graded-encoding-balanced.md`](graded-encoding-balanced.md) ran in full (60
simulations, all 60 result files present) and returned **FAIL** against criteria
frozen before the run. Nothing in that specification is changed by this document,
and no criterion was loosened after seeing the result. This document records what
failed, why, what survives, and the candidate redesigns — **no redesign is
recommended or selected here.**

Written 2026-09-22, after the run. Everything below is computed from the saved
result files in `repro/mushroom_body/results/`; no simulation was run to produce
it. Where a number is an estimate rather than a measurement, it says so.

---

## 1. The recorded result

From `repro/mushroom_body/results/graded_encoding_balanced_verdict.json`:

| feature value `v` | nominal pre-balance YES price rate | score `S(v)` |
|---|---|---|
| 0.00 | 30 Hz | **+30.306** |
| 0.25 | 60 Hz | **−102.339** |
| 0.50 | 90 Hz | **0.000** |
| 0.75 | 120 Hz | **+102.339** |
| 1.00 | 150 Hz | **−30.306** |

- Strictly monotonic across all five values: **no**.
- Endpoint contrast distance `||c(0.00) − c(1.00)||` = **122.41 Hz**, measured
  change-in-contrast noise `d_change(0.00,1.00)` = **148.74 Hz**, threshold
  `3 × d_change` = **446.21 Hz** → fails.
- Chosen longest monotonic sub-range 60–120 Hz: distance **365.40 Hz** against
  its own threshold **1128.44 Hz** → also fails.
- Verdict: **FAIL**. Per the specification, "the balanced value encoding must
  change before any learning experiment."

One process note: the analysis step initially crashed rather than returning this
verdict, because it scored the contrast vector directly and the readout rejects
negative entries. That was a coding error in the analysis, fixed to match the
specification's own definition `S(v) = CIRCUIT(m_yes(v)) − CIRCUIT(m_no(v))`; the
two routes are mathematically identical (the readout is linear) and agree to
1.4 × 10⁻¹⁴ Hz on this data. **The FAIL is not an artifact of that bug.**

---

## 2. Diagnosis

### 2a. The scores are antisymmetric by construction, not by chance

At every one of the six seeds, in the saved files:

- `YES(v)` and `NO(1−v)` are the **same stimulus**, and `NO(v)` and `YES(1−v)`
  are the same stimulus — identical rates on every KC, including the balancing
  pool;
- at the MBON output, `m_yes(v) == m_no(1−v)` elementwise over all 96 instances;
- therefore `max |c(v) + c(1−v)| = 0.000e+00` exactly: `c(1−v) = −c(v)`;
- at `v = 0.50` the YES and NO stimuli are **literally identical**, so `c(0.50)`
  is the zero vector and `S(0.50) = 0.000` is forced, not measured.

The per-pool rates delivered (pools are disjoint and uniform, so this is the full
per-KC pattern):

| `v` | framing | price | recent_change | time_to_res | liquidity | signal | balance | total drive |
|---|---|---|---|---|---|---|---|---|
| 0.00 | YES | 30 | 90 | 90 | 90 | 90 | **70** | 60,000 |
| 0.00 | NO | 150 | 90 | 90 | 90 | 90 | **30** | 60,000 |
| 0.25 | YES | 60 | 90 | 90 | 90 | 90 | **50** | 57,000 |
| 0.25 | NO | 120 | 90 | 90 | 90 | 90 | **30** | 57,000 |
| 0.50 | YES | 90 | 90 | 90 | 90 | 90 | 30 | 54,000 |
| 0.50 | NO | 90 | 90 | 90 | 90 | 90 | 30 | 54,000 |
| 0.75 | YES | 120 | 90 | 90 | 90 | 90 | 30 | 57,000 |
| 0.75 | NO | 60 | 90 | 90 | 90 | 90 | 50 | 57,000 |
| 1.00 | YES | 150 | 90 | 90 | 90 | 90 | 30 | 60,000 |
| 1.00 | NO | 30 | 90 | 90 | 90 | 90 | 70 | 60,000 |

**Mechanism.** The NO framing is defined as the mirror of the YES framing. In
this sweep the only varying feature, `price`, is mirrored (`p → 1−p`), and every
other mirrored feature sits at its own mirror-fixed point (`recent_change = 0` is
the midpoint of [−0.2, 0.2]; `signal = 0.5` is the midpoint of [0, 1]), while the
unmirrored features are held constant. Hence `NO(v) ≡ YES(1−v)` identically, and

```text
c(v) = g(v) - g(1-v),
```

where `g` is the network's response to the YES-framed stimulus at the shared
seed. Any function of that form is antisymmetric about 0.5 with an exact zero at
the midpoint.

**Which design choice causes it.** Checked with the encoder alone (pure numpy, no
connectome, no simulation):

- **mirroring without balancing** (`unbalanced` variant): the swap symmetry is
  **still exactly present** — so balancing is not the cause, and removing it alone
  would not remove the symmetry;
- **balancing without mirroring**: the YES and NO stimuli become **identical at
  every value**, so the contrast is identically zero — degenerate, and worse.

So the antisymmetry is caused by **mirroring**, interacting with a sweep whose
only varying feature is mirrored and whose other mirrored features sit at
mirror-fixed points. Balancing preserves the symmetry (its rule depends only on
which framing has the larger drive and on `|D_Y − D_N|`, both of which swap with
the framings) but does not create it.

**Precision about what is lost.** Value information is not entirely destroyed:
`S(v) = g(v) − g(1−v)` could in principle be monotone in `v`, and its sign does
distinguish `v` from `1−v`. What the construction destroys is any even component;
it forces `S(0.50) = 0`; and it makes `v` and `1−v` the same measurement twice, so
the five sampled points carry three distinct magnitudes, one of them structurally
zero. The pairwise noise table shows the same redundancy:
`d_change(0.00,0.25) = d_change(0.75,1.00) = 258.74 Hz`, and
`d_change(0.25,0.75) = 376.15 Hz = 2 × d_change(0.25,0.50)`.

### 2b. Balancing opposes the price signal, breaking monotonicity

Total-drive balancing leaves feature-pool rates untouched and equalises totals by
moving drive into the reserved pool. At `v = 0.00` it sets a price-pool drive gap
of **−12,000 Hz across 100 KCs** against a balance-pool gap of **+12,000 Hz across
300 KCs**; at `v = 0.25`, −6,000 against +6,000. The two pools are unrelated
random KC sets with different downstream wiring, so the MBON contrast is the
difference of two large opposing effects, and there is no reason for that
difference to grow with `|v − 0.5|`.

It does not: `|S|` is **102.34 at v = 0.25** but only **30.31 at v = 0.00**, even
though the price difference at the endpoints (30 vs 150 Hz) is twice as large as
at the quartiles (60 vs 120 Hz). This is a second, independent defect: even with
the antisymmetry accepted, a monotone sequence would require `|S|` to grow with
`|v − 0.5|`, and the balancing opposition prevents it. It also makes the endpoint
gate — the one the verdict applies first — the **weakest** point of the sweep.

### 2c. The noise floor is dominated by the drive regime, not the statistic

Rebuilt from the files (`d_change` reproduces at 148.74 Hz exactly):

| step | value | factor |
|---|---|---|
| Same stimulus, two seeds (balanced regime), v = 0.00 YES | 73.21 Hz | **14.4 × the old `d_AA` = 5.10 Hz** |
| Contrast of two stimuli, differenced over two seeds | 74.37 Hz | × 1.02 |
| Endpoint `Δ_k = −2·c_k(0)` → doubles it | 148.74 Hz | × 2 |

- **Combining four runs costs almost nothing** (×1.02, not the ×√2 the
  specification's analytic sketch assumed). The common-random-number design
  works: the YES and NO seed-differences are positively correlated (mean cosine
  **+0.174** at v = 0.00, **+0.591** at v = 0.25), so differencing cancels part of
  the noise.
- **A factor of exactly 2 is the antisymmetry itself.** Because `c(1) = −c(0)`,
  the endpoint change is `Δ_k = −2·c_k(0)` (verified exactly), so the endpoint
  gate measures a doubled copy of a single contrast and doubles its noise with it.
- **The remaining ~14× is the balanced drive regime.** A single balanced stimulus
  is far noisier run-to-run than the old single-cue stimulus: the balanced
  stimulus drives ~800 KCs at 30–150 Hz rather than 100 KCs at 150 Hz, giving mean
  MBON rates ~60 Hz with peaks above 200 Hz.

### 2d. Heteroscedasticity

Same-stimulus across-seed distance (YES framing) by value: **73.21, 183.50,
121.97, 167.37, 24.90 Hz** at v = 0.00, 0.25, 0.50, 0.75, 1.00 — a 7× spread
across the sweep. The specification anticipated this ("network noise may depend on
which KCs and rates are stimulated") and was right to refuse the analytic
21.64 Hz threshold in favour of a directly measured, pair-specific one. Any
redesign that assumes one noise scale across a sweep is unsafe.

### 2e. Signal and noise live in the same MBONs

Pooled across the five values, per-instance across-seed SD of the YES response:

| index | type | pooled SD (Hz) | mean rate (Hz) | \|c(0.25)\| (Hz) |
|---|---|---:|---:|---:|
| 41 | MBON01 | 29.8 | 28.7 | 48.8 |
| 15 | MBON22 | 29.1 | 25.3 | 50.0 |
| 64 | MBON05 | 25.9 | 111.6 | 41.8 |
| 74 | MBON22 | 24.8 | 21.7 | 42.4 |
| 67 | MBON24 | 23.6 | 20.8 | 39.8 |
| 81 | MBON06 | 20.9 | 22.2 | 35.0 |
| 95 | MBON07 | 20.0 | 95.6 | 34.2 |
| 26 | MBON05 | 19.8 | 134.2 | 39.6 |

(Indices are instance positions in the saved rate vectors; two MBON22 and two
MBON05 rows are different instances of the same type.) Mean pooled SD over all 96
instances is **7.89 Hz**, median **5.68 Hz**; the top 8 instances carry **44%** of
the total variance, and only **16 of 96** instances have a pooled SD below 1 Hz.
The instances carrying the largest contrast are the same ones carrying the largest
noise, so the noise does not average away inside the per-type mean.

---

## 3. What this run established that survives any redesign

These are measurements of the model in the balanced drive regime. They are not
tied to the verdict and remain valid if the encoder is redesigned:

1. **Balanced-regime run-to-run noise is ~14× the single-cue `d_AA`.** Same
   stimulus, two seeds: 73.21 Hz at v = 0.00 (per-instance SD 4.57 Hz), against
   `d_AA = 5.10 Hz` and ~0.41–0.51 Hz per-instance SD in the 100-KC cue-direct
   regime. **Any** design that drives ~800 KCs should budget noise of this order,
   and no design should reuse `d_AA` as its threshold.
2. **Common random numbers buy a real reduction.** Sharing the seed between two
   stimuli makes their noise positively correlated (cosine +0.174 and +0.591 at
   the two values measured), so a paired difference costs ×1.02 rather than the
   ×√2 of independent runs. Worth keeping in any paired design.
3. **Noise is strongly stimulus-dependent** (24.90 to 183.50 Hz across five
   stimuli of the same family). Pair-specific, directly measured thresholds are
   necessary; a single global threshold is not defensible.
4. **A short list of high-variance instances** (table in 2e: MBON01, MBON22 ×2,
   MBON05 ×2, MBON24, MBON06, MBON07), carrying 44% of the variance and also much
   of the contrast. Useful as a prior for which instances will dominate both
   signal and noise in any readout over this drive regime.
5. **The exact-swap property of the mirrored encoder is now a verified fact about
   the code**, not a hypothesis: it holds bit-for-bit, with and without balancing,
   and can be checked without simulation.

Also unaffected, because they do not depend on the market encoder at all:
the fast-runner equivalence result, the `run_cue_rates` equivalence result, the
MBON-separability result (cue-direct 100-KC sets), the reduced-MB control, the
shuffled-connectome machinery and its frozen membership file, the MBON side
table, and the CIRCUIT sign tables. **The first learning test is also unaffected**:
it presents cue-direct KC sets, not Option-B market framings, and its 260-run plan
stands.

---

## 4. Candidate redesigns (none recommended, none selected)

Cost figures are arithmetic from the existing protocol shapes and are **estimates,
not measured runtimes**. "Graded re-validation" means a replacement for
[`graded-encoding-balanced.md`](graded-encoding-balanced.md), which must be
pre-stated in a new dated document before it is run, whichever option is chosen.

### (a) Drop mirroring — YES and NO use different feature mappings, not reflections

**Fixes.** Removes the antisymmetry at its source: if `NO(v)` is no longer
`YES(1−v)`, then `c(v)` is no longer forced to `g(v) − g(1−v)`, `S(0.50)` is no
longer structurally zero, and `v` and `1−v` stop being the same measurement twice.

**Leaves broken.** Says nothing about the balance-pool opposition (2b) or the
~14× drive-regime noise (2c) — with balancing retained, both persist. It also
requires a new, justified rule for what the NO stimulus *is*, and mirroring was
chosen precisely because it makes the two framings commensurable; an asymmetric
mapping needs an argument that the two scores remain comparable at all.

**Preserves.** The Option-B readout, the per-type mean, the sign tables, the
intensity-bias decision, the synthetic-market structure and run counts.

**Invalidates.** The DECIDED mirroring rule (MB-LEARN 4a) and every
`FeatureSpec.mirror_for_no` flag; the balance-pool capacity rule, which is derived
from the worst-case mirrored difference and would need re-deriving.

**Re-validation cost.** ~60 simulations (5 values × 2 framings, plus 5 noise seeds
× 5 values × 2 framings), the same shape as the failed test.

### (b) Drop Option B for Option A — single stimulus, signed score

Note: "Option A" is the name used in the request for a single-stimulus design
with a signed score. **No written specification of it exists in this repository**;
it would have to be written from scratch.

**Fixes.** Removes the antisymmetry, the balance-pool opposition and the
intensity-bias problem in one move, because there is no second framing to balance
against and no mirror. Halves the per-decision simulation cost.

**Leaves broken.** The ~14× drive-regime noise (2c) and the heteroscedasticity
(2d) are properties of driving ~800 KCs and survive untouched. It also gives up
the paired-difference cancellation measured in 3.2, so the effective noise per
decision may be *worse* than a paired design. A signed score needs a zero point:
with one stimulus there is no second score to subtract, so the decision threshold
must be calibrated against something else, and the intensity dependence that
motivated Option B returns as a bias on that absolute score.

**Preserves.** The sign tables, the per-type mean, the MBON side table, the noise
measurements in Section 3, the first learning test.

**Invalidates.** The Option-B readout decision (MB-LEARN 4b) and everything
derived from it: the two-framing abstention rule and margin semantics, the
intensity-bias mitigation decision, the balancing parameters
(`balance_pool_size`, `option_b_variant`), and the synthetic-market run counts
(20,000 runs → ~10,000, since the two framings per market disappear). Large parts
of the preregistration's Sections 4.5 and 6.2 would need rewriting.

**Re-validation cost.** ~30 simulations for a graded re-validation (5 values × 1
stimulus + 5 seeds × 5 values), plus a new noise-floor statistic, since
`d_change` is defined on contrasts that no longer exist.

### (c) Drop balancing — keep mirroring, handle intensity bias by innate-score subtraction

**Fixes.** Removes the balance-pool opposition (2b), so the score magnitude is
driven by the price pool alone and has a plausible reason to grow with
`|v − 0.5|`. Reduces total drive, which should reduce absolute noise (2c) —
by how much is **unverified**. Innate-score subtraction is already implemented
(`bias_mitigation.score_difference`) and was pre-stated as the alternative
mitigation.

**Leaves broken.** **Does not fix the antisymmetry** — verified: the swap holds
exactly in the `unbalanced` variant too. `S(0.50) = 0` and `c(1−v) = −c(v)`
survive, so the same sweep would fail for the same structural reason. Innate-score
subtraction also inherits the noise of the innate runs, which is not cancelled by
common random numbers unless the innate runs share seeds with the decision runs.

**Preserves.** Mirroring, the Option-B readout, the sign tables, the graded
sweep's shape.

**Invalidates.** The 2026-09-22 intensity-bias decision (total-drive balancing as
the Option-B default) and the encoder parameters that implement it; the
synthetic-market cost model, which grows because innate scores need their own
runs.

**Re-validation cost.** ~60 simulations for a graded re-validation, **plus** the
synthetic-market increase already encoded in the job planner: 125 jobs / 25,000
runs under innate-score subtraction against 100 jobs / 20,000 runs under
balancing, and the longest dependency chain doubles from 200 to 400 runs.

### (d) Keep everything, redesign the sweep asymmetrically

**Fixes.** Nothing structural. It stops the *sweep* from sampling the symmetry
head-on: values not placed symmetrically about 0.5 would not produce paired
±identical scores, and the midpoint's forced zero could be left out.

**Leaves broken.** Everything in 2a–2e. `c(1−v) = −c(v)` and `c(0.50) = 0` remain
true of the encoder whether or not the sweep samples those points; the
balance-pool opposition still governs how `|S|` varies; the noise is unchanged.
This option changes what the test can see, not what the encoder does — and a
criterion redesigned after a FAIL, on an encoder known to carry the defect, is
exactly the move the project's own rules forbid without a new pre-statement and a
stated rationale independent of this result.

**Preserves.** Every existing decision and parameter; no code change.

**Invalidates.** Nothing, but it also validates nothing: a pass under an
asymmetric sweep would not show that the encoder carries value information in a
form the learning rule can use, only that the sweep avoided the structurally
degenerate points.

**Re-validation cost.** ~60 simulations, or more if the new sweep has more than
five values.

---

## 5. Open, for the project owner

No option above is selected, and this document does not rank them. Whichever is
chosen, the replacement graded test must be written as a new dated pre-statement
with its own thresholds before it is run, and it must not reuse `d_AA` or any
threshold from the failed test. The balanced Option-B encoder stays marked **NOT
VIABLE** until such a test passes.
