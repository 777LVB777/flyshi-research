# Pool-identity control: price pool versus a substitute pool at matched drive

**Status: PRE-STATED, 2026-09-30; NOT RUN.** Written before any simulation of the
substitute pool and before the runner that would run it. The stimuli, seeds,
statistics, noise floors, factor and readings below are fixed by this document.
If anything needs to change, write a new dated pre-statement rather than editing
this one.

**THIS IS A DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false`, no `verdict` field). It measures one counterfactual
and states in advance what each result would mean. It authorises nothing,
validates no encoder and invalidates none. Its output passes the same enforcement
check as the other diagnostics (`check_no_verdict` of the realistic-drive runner):
no `verdict`, `pass`, `passed` or `pass_criterion` key, and none of the words
PASS, FAIL, ACCEPTED or USABLE RANGE anywhere in the summary.

**What has already been seen.** This control is written **after** the left-only
mirrored validation returned its verdict
([`graded-encoding-left-only-mirrored.md`](graded-encoding-left-only-mirrored.md),
ACCEPTED). Its saved data are the price arm here and **have been seen**. The
noise floors quoted in §5 were computed from them for this document. The
**substitute arm has never been simulated**: no stimulus that drives the
substitute pool has ever been presented.

It carries out the measurement proposed in
[`drive-confound.md`](drive-confound.md) §3.5, in its "swap which pool carries the
price value" form. That document is not edited.

---

## 1. Question

In the mirrored, unbalanced, left-only encoder, YES and NO present the same 500
KCs. They differ only in the price pool's rate, so the drive difference **is** the
price-pool rate difference (`drive-confound.md` §1). The question is the
counterfactual stated there:

> **Would the same rate change, applied to some other 100 left KCs at the same
> total drive, produce the same `S(v)`?**

- If it would, `S(v)` reflects generic total drive, and the price pool's
  identity contributes little to the scalar.
- If it would not, part of `S(v)` is specific to which KCs carry the value.

It also asks the same question of the 96-instance MBON vector. Pool identity
showed up there before (cosine 0.977 against the price-sweep direction,
`drive-confound.md` §2.3) but not in the scalar. That comparison added KCs and
crossed operating ranges. This one does neither.

## 2. Stimuli (fixed)

### 2.1 The substitute pool Q

- **Source:** the left-hemisphere KCs of the frozen ID table
  (`repro/mushroom_body/neuron_ids_783.json`, 2,580 left KCs), minus **every**
  KC the encoder (pool seed 20260401) assigns to a pool. That is the five
  100-KC feature pools and the 300-KC balance pool, 800 KCs in all, leaving
  1,780 candidates.
- **Why the balance pool is excluded as well.** The request only requires Q to
  be disjoint from the price and feature pools. The balance pool was presented in
  the realistic-drive diagnostic's balanced stimuli. Excluding it too keeps Q
  apart from every KC the encoder has ever driven.
- **Draw:** sort the candidates. Permute them with
  `numpy.random.default_rng(20260930)`, take the first 100, and sort those.
  **Substitute-pool seed 20260930.** The runner records the drawn IDs.
- **Guard:** before the model is built, every KC in every encoder pool and in Q
  must be annotated left, and Q must have 100 KCs, be disjoint from all 800
  encoder-pool KCs, and contain no duplicates. The runner aborts otherwise.

### 2.2 The two arms

Everything is identical to the validation's protocol except where stated: default
`EncoderParams`, `OPTION_B_UNBALANCED`, the midpoint background
(`recent_change = 0.0`, `time_to_resolution = 182.5`, `liquidity = 0.5`,
`signal = 0.5`, each 90 Hz), `r(v) = 30 + 120 v` Hz, 1000 ms × 5 trials.

- **Price arm P (not re-simulated).** This is exactly the validation's stimuli:
  the four background pools at 90 Hz, plus the **price pool** at `r(v)` (YES) or
  `r(1−v)` (NO). The runner reads these from the validation's saved files.
- **Substitute arm Q (new).** Each P stimulus, with the price pool's 100 KCs
  **replaced by Q's 100 KCs at the same rate**. So YES presents Q at `r(v)` and
  NO presents Q at `r(1−v)`. The price pool is not driven.

**What is matched exactly, and checked before any simulation (the runner aborts
on failure):**

1. Each Q stimulus drives 500 KCs, and its total drive equals its P counterpart's
   to floating-point precision. So `D_YES` and `D_NO` are the same in both arms,
   and `D_YES − D_NO = 12,000 (2v − 1)` Hz in both.
2. The sorted multiset of per-KC rates is identical between the arms.
3. The four background pools have the same KC IDs and rates in both arms.
4. The symmetric difference of the two arms' KC sets is exactly the price pool
   plus Q.
5. **Mirroring holds in Q:** `NO_Q(v)` equals `YES_Q(1−v)` bit-for-bit, so
   `S_Q(1−v) = −S_Q(v)` and `S_Q(0.50) = 0` exactly, as in P.
6. No feature value is clipped.

**What differs:** only which 100 KCs carry the value. KC count, total drive,
per-KC rate distribution, background, seeds and framing rule are all the same.

### 2.3 Values, seeds, count

- **Values:** `V = (0.56, 0.73, 0.94)`, a subset of the frozen set B. These are
  its endpoints and its middle value, with edges 0.06, 0.23 and 0.44.
  - Q's YES price rates: 97.2, 117.6 and 142.8 Hz.
  - Q's NO price rates: 82.8, 62.4 and 37.2 Hz.
- **Seeds:** 20260316, 20260317, 20260318, 20260319, 20260320 and 20260321,
  the validation's six. At every seed the Q presentations use the same seed as
  the P presentations they are compared with.
- **Substitute simulations:** 3 values × 2 framings × 6 seeds = **36**.
- **Reproducibility check:** 1 more simulation. The P stimulus at `v` = 0.94,
  YES, seed 20260316 is re-simulated and compared with its saved file (§6).
- **Total: 37 simulations.** No P presentation other than the check is re-run.

## 3. Changes compared

Mirroring makes the contrast at 0.50 exactly zero in both arms
(`c(0.50) = 0` because YES(0.50) ≡ NO(0.50) at a shared seed). Every `S(v)` is
therefore itself a **score change** from a fixed zero. The six changes are:

| change | what it is |
|---|---|
| **(0.50 → 0.94)** | **PRIMARY:** `S(0.94)`, the largest edge (drive difference 10,560 Hz) |
| (0.50 → 0.56) | `S(0.56)` |
| (0.50 → 0.73) | `S(0.73)` |
| (0.56 → 0.73) | the lower step |
| (0.73 → 0.94) | the upper step |
| (0.56 → 0.94) | the validation's endpoint change |

Only the primary change carries a pre-stated reading (§5). The other five are
reported with the same statistics and are labelled secondary. With five
secondary comparisons, one of them crossing its threshold by chance is not
evidence.

For arm `A` (P or Q), seed `s` and change `(a → b)`:

```text
c_A,s(v)        = m_yes,A,s(v) − m_no,A,s(v)       (96-instance MBON vector; c(0.50) = 0)
S_A,s(v)        = circuit_score_difference(m_yes, m_no, labels, CIRCUIT-80, "type_mean")
ΔS_A,s(a → b)   = S_A,s(b) − S_A,s(a)              (S(0.50) = 0)
Δc_A,s(a → b)   = c_A,s(b) − c_A,s(a)
```

This is the same readout, sign table and aggregation as the validation.

## 4. Statistics

Split the six seeds into two triples. The **ten splits** `(H₁, H₂)` are the ten
triples containing the seed 20260316 (`H₁`), each with its complement (`H₂`).
Write `m_H(·)` for the mean over the seeds in `H`. For each change:

**Scalar**

```text
W_S,P  = mean over 10 splits of | m_H₁(ΔS_P) − m_H₂(ΔS_P) |                 price arm's own floor
W_S,Q  = the same for Q                                                    substitute's own floor
X_S    = mean over 10 splits × both orientations of | m_H₁(ΔS_Q) − m_H₂(ΔS_P) |   cross-arm (20 terms)
```

**Vector:** the same three quantities with `‖·‖` (Euclidean, Hz) over `Δc`,
giving `W_V,P`, `W_V,Q` and `X_V`.

**Why this form.** `X` compares a three-seed Q estimate with a three-seed P
estimate from **disjoint seeds**. `W_P` compares two three-seed P estimates from
disjoint seeds. If Q and P carry the same change and the same noise, `X` and
`W_P` estimate the same quantity. So the comparison needs no independence
assumption and no `√2` or `√n` factor. Every number comes from measured seeds,
as in the validation's `d_change` (spec §5 there), which did not derive noise
analytically.

**Also reported (descriptive; no reading attached):**

- the six-seed means `ΔS̄_P` and `ΔS̄_Q`, their ratio `R = ΔS̄_Q / ΔS̄_P`, and
  every per-seed value in both arms;
- the same-seed paired differences `ΔS_Q,s − ΔS_P,s`, with their mean and SD;
- for the six-seed mean vectors `Δc̄_P` and `Δc̄_Q`:
  - their norms and norm ratio;
  - the cosine between them;
  - the component of `Δc̄_Q` orthogonal to `Δc̄_P`: its norm, and its fraction of
    `‖Δc̄_Q‖`;
- the **split-half cosine ceilings**, the mean over the ten splits of
  `cos(m_H₁(Δc_A), m_H₂(Δc_A))`, for each arm. This is the reference the 0.977
  was read against in `drive-confound.md` §2.3;
- the validation's single-seed floor `d_change_P(a,b)`. It is recomputed from
  the five repeat seeds with the validation's own formula, for the pairs that
  exist there. Beside it are `d_change_Q` and the single-seed cross distance
  `d_cross` (mean over ordered pairs `i ≠ j` of repeat seeds of
  `‖Δc_Q,i − Δc_P,j‖`);
- the ignition label, recruitment intensity and APL rate of every Q
  presentation, as in the validation;
- Q's imposed rate against its measured stimulated-KC rate.

## 5. Noise floors (measured) and pre-stated readings

### 5.1 The price arm's floors, from the validation's saved data

Computed for this document from the 36 validation files the price arm uses
(CIRCUIT-80, per-type mean; six seeds):

| change | `ΔS̄_P` (Hz) | per-seed SD | `W_S,P` (Hz) | `3 W_S,P` | `‖Δc̄_P‖` (Hz) | `W_V,P` (Hz) | `3 W_V,P` | split-half cosine | `d_change_P` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **0.50 → 0.94** | **−29.09** | 1.71 | **1.08** | **3.24** | 104.24 | **6.60** | **19.79** | 0.998 | n/a |
| 0.50 → 0.56 | −3.69 | 2.60 | 1.75 | 5.26 | 14.24 | 7.69 | 23.07 | 0.862 | n/a |
| 0.50 → 0.73 | −15.90 | 1.11 | 0.77 | 2.32 | 55.32 | 6.69 | 20.06 | 0.993 | n/a |
| 0.56 → 0.73 | −12.22 | 3.35 | 2.23 | 6.70 | 41.58 | 10.95 | 32.84 | 0.966 | 17.05 |
| 0.73 → 0.94 | −13.18 | 2.63 | 1.73 | 5.19 | 49.28 | 10.08 | 30.24 | 0.980 | 17.28 |
| 0.56 → 0.94 | −25.40 | 1.92 | 1.45 | 4.35 | 90.37 | 9.80 | 29.39 | 0.994 | 17.39 |

The `d_change_P` values equal those recorded in the validation's verdict file.
**The thresholds are not typed into the runner.** The runner recomputes them from
the saved files by the formula of §4, and reports them with the Q results.

### 5.2 Readings (primary change, 0.50 → 0.94)

These readings are pre-stated labels for the measurement. They are not a pass
criterion. The factor 3 is the project's `NOISE_MARGIN`.

- **Scalar:** `within_noise` if `X_S ≤ 3 W_S,P`; `beyond_noise` if
  `X_S > 3 W_S,P`.
- **Vector:** `within_noise` if `X_V ≤ 3 W_V,P`; `beyond_noise` if
  `X_V > 3 W_V,P`.

**Robustness line (reported, not decisive).** Each comparison is also recomputed
against `3 × max(W_P, W_Q)`. If Q is noisier than P, `X` rises without any
difference in the mean change. A `beyond_noise` reading that becomes
`within_noise` against the larger floor is reported as **"beyond the price arm's
floor only"** and is not attributed to pool identity.

### 5.3 What each outcome means

| scalar | vector | meaning |
|---|---|---|
| within | within | **The scalar signal is largely generic drive.** Neither `S` nor the MBON vector distinguishes the two pools at matched drive and KC count. The orthogonal component in `drive-confound.md` §2.3 was then more likely due to KC count or operating range than to identity. |
| within | beyond | **The scalar signal is largely generic drive, and identity is present in the vector.** This is §2.3's pattern, reproduced under the proper counterfactual. The per-type-mean readout discards pool identity. That supports the open question in `drive-adjusted-readout-prestatement.md` §2 without answering it. |
| beyond | beyond | **Pool identity contributes to `S`.** `R` gives the part of the price arm's change that another pool reproduces at the same drive (item a below). |
| beyond | within | **Unexpected.** The scalar is a fixed linear function of the vector, and the vector floor is coarser per unit of change. This is reported as a scalar-only difference and not interpreted further. |

**How to read `R` under `beyond_noise`** (descriptive, not a further
threshold):

- a. **`0 < R < 1`:** Q reproduces a fraction of the change. On the reading that
  Q carries no identity effect of its own, about `R` of `S` is generic drive and
  `1 − R` is price-pool-specific. That assumption cannot be checked with one
  substitute draw (§7).
- b. **`R ≥ 1`:** Q moves the score at least as much as the price pool does. The
  pools differ, but the difference cannot be attributed to the price pool.
- c. **`R ≤ 0`:** Q moves the score the other way. The direction of `S` is set by
  which KCs carry the value, not by drive.

**Under `within_noise`,** a difference in the primary change smaller than about
`3 W_S,P` = 3.2 Hz (about 11% of the 29.1 Hz change) cannot be excluded. The
reading is "reproduced within the measured noise", **not** "identity is
irrelevant".

**Planning expectation (not a criterion).** On the drive-only model of
`drive-confound.md` §2.4, `S_Q(0.94) ≈ S_P(0.94) ≈ −29` Hz, so the expected
readings are scalar `within_noise`, `R ≈ 1`. That model was fitted on stimuli that
change KC count, so the expectation is weak.

## 6. Reproducibility check

The price arm is read from files written on 2026-09-28, not re-simulated. One P
presentation (`v` = 0.94, YES, seed 20260316) is re-simulated with the current
code and environment. Its MBON, KC and APL trial-mean rate vectors are then
compared element by element with the saved file.

- **Identical:** reported as such. Cross-arm comparisons then rest on a verified
  identical simulator.
- **Not identical:** the maximum absolute difference is reported, and every
  cross-arm number is labelled **"cross-arm comparison across a simulator
  change"**. The readings of §5 are still computed and reported, and are not
  suppressed.

## 7. What this can and cannot conclude

**Can:**

- Say whether one other left 100-KC pool, carrying exactly the price pool's rates
  at exactly the same total drive and KC count, reproduces the price pool's
  `S(v)` and MBON contrast within the validation's measured noise.
- Tell §3.2 and §3.4 of `drive-confound.md` apart in expectation:
  - under `within_noise` on the scalar, both would leave little scalar signal;
  - under `beyond_noise`, `R` estimates how much each would leave.

**Cannot:**

- **Separate "the price pool is special" from "any two pools differ".** There is
  one substitute draw, so Q's own identity effect is confounded with the price
  pool's. A second draw would need a new pre-statement.
- **Generalise beyond this operating range** (39.7–50.3 kHz), the midpoint
  background, left pool seed 20260401, substitute-pool seed 20260930, 1000 ms ×
  5 trials or six seeds.
- **Say anything about learning.** The learned term `K` of `drive-confound.md`
  §4.2 depends only on price-pool synapses, whatever this shows.
- **Change or qualify any verdict:** not the validation's ACCEPTED, and not the
  first learning test's.

## 8. Outputs, stopping rule, command

**Files:**

- one JSON per Q presentation,
  `pool_identity_Q_value_<v>_<framing>_seed_<seed>.json`, carrying the same
  fields as the validation's per-presentation files plus the Q pool and its seed.
  These are data only, with no verdict;
- one reproducibility file, `pool_identity_repro_check.json`;
- one summary, `pool_identity_control_summary.json`, with `is_a_validation:
  false`, `has_pass_criterion: false`, `prestated_diagnostic: true` and `spec`.

**Order:** seed-major. The reproducibility check runs first, so an environment
change shows up before 36 simulations are spent.

**Restarts:** any presentation whose file exists is skipped.

**No summary unless:**

- all 36 Q files, the check file and the 36 required P files exist;
- every saved stimulus equals the rebuilt one;
- every §2.2 check holds.

**Stopping:** stop once the summary is written. Do not add values, seeds or
substitute draws, or change a statistic, the factor or the primary change, after
seeing results. Any later analysis is exploratory and must be labelled as such.

**Cost:** 37 simulations plus one build of about 4 s. That is about **33.6
minutes** at the measured 54.4 s per simulation, or 31.2 minutes at the older
50.5 s figure. Both figures were measured on the author's machine and are
unverified elsewhere.

**Command:**

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_pool_identity_control.py
```

`--dry-run` and `--analyze-only` build no model and load no connectome, and
neither does importing the module. They read only the frozen neuron-ID table and
saved result files.

---

## Results (recorded 2026-09-30, after the run)

**Everything above this section is the pre-statement, unchanged.** This section
records the run and applies §5 as written. No stimulus, seed, statistic,
threshold or reading rule was changed.

**The run.** 37 simulations (36 substitute + 1 reproducibility check). The log is
`repro/mushroom_body/run_log_pool_identity.txt`, and the summary is
`results/pool_identity_control_summary.json`.

**Correction to the runner's wording (made after the run, before this section
was written).** The runner, as first committed, printed and saved the §5.3 row
"scalar and vector beyond noise: pool identity contributes to S; see R". It did
that even though it also flagged the primary scalar as "beyond the price arm's
floor only". §5.2 says such a reading "is not attributed to pool identity", so
the first wording contradicted the pre-statement.

- **The fix.** The runner now uses the §5.3 table only when no beyond-noise
  reading is flagged. Otherwise it states each part on its own.
- **Regenerating the summary.** The summary was rebuilt with `--analyze-only`,
  with no simulation. Only its `primary_interpretation` field changed; every
  number is identical. The run log still shows the original wording.

### Reproducibility and containment

- **Reproducibility check** (`v` = 0.94, YES, seed 20260316): **identical** to the
  validation's saved file. The maximum absolute difference is 0.0 Hz for MBONs,
  KCs and APL. The cross-arm comparison is therefore not across a simulator
  change.
- **Ignition: 0 of 36** substitute presentations. The non-stimulated KC active
  fraction was 0.0 in every one.
- **Q's measured rate** was 0.987–0.999 of the imposed rate.

### All six changes

Hz throughout. The P and Q columns are six-seed means. "3 max" is
`3 × max(W_P, W_Q)`. "Flagged" means "beyond the price arm's floor only".

| change | `S_P` / `ΔS_P` | `S_Q` / `ΔS_Q` | `R` | `X_S` | `3 W_S,P` | 3 max | scalar | cosine | `X_V` | `3 W_V,P` | 3 max | vector |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| **0.50 → 0.94 (primary)** | **−29.09** | **−22.02** | **0.76** | 7.07 | 3.24 | 8.06 | beyond_noise (flagged) | 0.974 | 24.48 | 19.79 | 20.85 | beyond_noise |
| 0.50 → 0.56 | −3.69 | −2.49 | 0.68 | 1.44 | 5.26 | 5.42 | within_noise | 0.891 | 8.67 | 23.07 | 23.07 | within_noise |
| 0.50 → 0.73 | −15.90 | −11.06 | 0.70 | 4.84 | 2.32 | 6.07 | beyond_noise (flagged) | 0.971 | 13.92 | 20.06 | 20.89 | within_noise |
| 0.56 → 0.73 | −12.22 | −8.57 | 0.70 | 3.65 | 6.70 | 8.39 | within_noise | 0.950 | 14.66 | 32.84 | 32.84 | within_noise |
| 0.73 → 0.94 | −13.18 | −10.96 | 0.83 | 2.36 | 5.19 | 7.66 | within_noise | 0.964 | 15.03 | 30.24 | 30.24 | within_noise |
| 0.56 → 0.94 | −25.40 | −19.52 | 0.77 | 5.88 | 4.35 | 13.48 | beyond_noise (flagged) | 0.969 | 23.42 | 29.39 | 32.43 | within_noise |

**`R` ranges from 0.68 to 0.83 across all six changes.**

### The primary change (0.50 → 0.94)

**Scalar.** `S_P` = −29.09 Hz and `S_Q` = −22.02 Hz, so `R` = 0.76.

- **Reading:** `X_S` = 7.07 > `3 W_S,P` = 3.24, so the reading is
  `beyond_noise`.
- **Robustness line:** Q's own floor is `W_S,Q` = 2.69 Hz, against
  `W_S,P` = 1.08 Hz. So `X_S` ≤ `3 × max` = 8.06, and the reading becomes
  `within_noise` against the larger floor.
- **Label:** the scalar is **"beyond the price arm's floor only"**.

**Vector.**

- **Reading:** `X_V` = 24.48 > `3 W_V,P` = 19.79, and it stays above
  `3 × max(W_V,P, W_V,Q)` = 20.85. The reading is `beyond_noise` **against both
  floors**.
- **Size of the difference:**
  - the cosine between the mean changes is 0.974, against split-half ceilings of
    0.998 (P) and 0.998 (Q);
  - the norm ratio is 1.006;
  - the component of Q's change orthogonal to P's is 23.9 Hz, 22.8% of Q's change.

### Conclusion, in the pre-statement's terms

- **The scalar difference is not attributed to pool identity (§5.2).** The §5.3
  row "beyond | beyond: **Pool identity contributes to `S`**" requires the
  scalar reading to count, and §5.2 withholds exactly that for a flagged
  reading. For the same reason, the `R` reading of §5.3 item a ("about `R` of
  `S` is generic drive and `1 − R` is price-pool-specific") is not applied. `R`
  is reported only as a description.
- **Nor does the pre-statement support "the scalar signal is largely generic
  drive".** That conclusion belongs to the rows whose scalar reading is
  `within_noise`, and the primary scalar reading is `beyond_noise` against the
  price arm's floor. The scalar question is therefore **not resolved** by this
  control. The difference exceeds the price arm's measured noise but not the
  substitute arm's.
- **Pool identity is present in the MBON vector.** At matched total drive, KC
  count, rate distribution and background, moving the value onto another 100
  KCs changes the MBON contrast beyond both arms' measured noise. This
  reproduces the orthogonal component of `drive-confound.md` §2.3: cosine 0.974
  here, against 0.977 there. The earlier comparison changed KC count and
  operating range; this one changes neither, so the component is not explained
  by either.
- **Limits (§7) apply unchanged.** There was one substitute draw, so Q's own
  identity effect is confounded with the price pool's.

### Descriptive observations (post hoc; they change no reading)

- **`R` < 1 in all six changes.** Q's score change is smaller in magnitude than
  P's everywhere, including the three changes whose scalar reading is
  `within_noise`.
- **One seed drives the flag.** In the primary change, the paired same-seed
  differences `ΔS_Q,s − ΔS_P,s` are 6.8–9.5 Hz at five seeds and 1.3 Hz at seed
  20260317. There, `S_Q` = −28.74 Hz, against −18.69 to −24.21 Hz at the other
  seeds. That seed is what raises `W_S,Q` above `W_S,P`, and so what produces
  the flag. Checked post hoc: replacing that one value with the mean of the
  other five seeds lowers `W_S,Q` from 2.69 to 1.41 Hz. `X_S` (8.41) would then
  exceed `3 × max` (4.24), and the flag would not arise. This is an exploratory
  counterfactual, not a reading. The pre-stated reading stands as recorded
  above.
- **What would resolve the scalar question.** Settling it would need more seeds
  or more substitute draws. Either would need a new pre-statement.
