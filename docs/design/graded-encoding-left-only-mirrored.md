# Graded-encoding validation: left-only pools, mirrored NO framing, no balancing

**Status: PRE-STATED; NOT RUN. The runner does not exist yet.** Written
2026-09-27, before any simulation of this protocol and before the code that would
run it. Everything below — pools, framing, value set, seeds, statistic, noise
floor, gates, verdict rule — is fixed by this document. If anything needs to
change, write a new dated pre-statement rather than editing this one. The single
exception is §3.4: the project owner may substitute candidate set A or C for the
adopted set B **before the runner is written**, by a dated note in §3.4 alone.
After the runner exists, the value set is frozen.

**THIS IS A VALIDATION** (`is_a_validation: true`, `has_pass_criterion: true` in
the output). This is unlike the diagnostics that led here: the left-only pool,
left-only ladder, realistic-drive and unbalanced single-framing documents
measured without a verdict, or with a diagnostic PASS/FAIL that authorised
nothing. This document produces exactly one verdict from the preregistered
graded vocabulary: **ACCEPTED**, **USABLE RANGE** or **FAIL**. The diagnostic
word PASS is not part of that vocabulary and must not appear in its output (§9).

**Supersedes, without editing:** [`graded-encoding-balanced.md`](graded-encoding-balanced.md)
(balanced encoder, bilateral pools by a since-fixed bug, recorded FAIL) and, for
the current encoder, [`graded-encoding.md`](graded-encoding.md) (uniform-rate
cue-direct sweep). Both stay as historical records. Their verdicts are unchanged.

---

## 1. Question

Does the Option B score `S(v)` of the **mirrored, unbalanced** market encoder,
with pools drawn from **left-hemisphere KCs only**, vary monotonically with the
price feature? And does it vary by more than its directly measured run-to-run
change-in-contrast noise?

## 2. Why this design (decision recorded 2026-09-27)

The project owner decided on four things: left-only pools, keep mirroring, drop
balancing, and use a non-reflective value set. The reasons are recorded here
because each one depends on a measurement. Where a stated reason was checked
against the repository and needed correcting, the correction is marked.

### 2.1 Left-only pools

The realistic-drive diagnostic
([`left-only-realistic-drive-diagnostic.md`](left-only-realistic-drive-diagnostic.md),
results in `results/left_only_realistic_drive_summary.json`) ran the encoder's own
YES stimuli, drawn left-only, at 39,600–60,000 Hz total drive. It recorded:

| stimulus | ignited | score SD (Hz) | same-stimulus noise (Hz) |
|---|---:|---:|---:|
| unbalanced `v` = 0.05 | 0/6 | 1.56 | 9.73 |
| unbalanced `v` = 0.22 | 0/6 | 2.12 | 9.66 |
| unbalanced `v` = 0.41 | 0/6 | 0.92 | 11.05 |
| unbalanced `v` = 0.63 | 0/6 | 1.72 | 9.73 |
| unbalanced `v` = 0.88 | 0/6 | 1.59 | 8.31 |
| balanced `v` = 0.00 | 0/6 | 1.34 | 7.83 |
| balanced `v` = 0.25 | 0/6 | 2.03 | 9.28 |

That is, score SD was **0.92–2.12 Hz** and same-stimulus noise **7.83–11.05 Hz**.
(The decision note gave the SD range as 1.3–2.1 Hz; the recorded minimum is 0.92
Hz, at `v` = 0.41.)

Compare the unbalanced single-framing diagnostic. It used the same five YES
stimuli at the same drive, KC count and per-pool rates, but with bilateral pools.
There, score SD was 37.8–63.0 Hz and same-stimulus noise 70.4–136.9 Hz. The
bilateral 90 Hz ladder had score SD 60–82 Hz once ignited.

The same model and connectome produced both results. The noise that failed the
earlier graded tests is therefore attributed to the bilateral pool draw, not to
the architecture ([`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md)).
Hemisphere and pool draw are still confounded, because each side is one draw. So
this validation is a claim about **this** left draw (pool seed 20260401), not
about left pools in general (§8).

### 2.2 Keep mirroring

`NO(v) ≡ YES(1−v)` exactly. At a shared seed, `S(1−v) = −S(v)` and `S(0.50) = 0`
([`balanced-encoding-failure.md`](balanced-encoding-failure.md) §2a, verified
bit-for-bit). The owner's reasons for keeping this:

- **The forced zero is correct.** A market at 0.50 offers no edge in either
  direction.
- **The antisymmetry is correct.** `v` and `1−v` are equal and opposite edges,
  and a calibrated forecaster should score them as such.
- **The real cost is fixable.** Mirroring's cost is redundancy: `v` and `1−v` are
  one measurement taken twice. With reflective endpoints the endpoint gate also
  measures `−2·c(0)`, which doubles its noise. A non-reflective value set removes
  both problems (§3).
- **Dropping mirroring is worse.** Without it, YES and NO would be carried by
  structurally different codes. Their difference would include a
  wiring-determined term with no structural cancellation, and nothing learned for
  one framing would transfer to the other.

**Correction: what the ~79 Hz figure measures.** The decision note gives that
wiring term as about 79 Hz. That number is `d_AB` = 79.44 Hz from
[`mbon-separability.md`](mbon-separability.md): the **Euclidean MBON-vector
distance** between two *different* 100-KC left sets (cue A vs cue B) at 150 Hz,
1000 ms × 5 trials. It shows that pool identity alone moves the MBON vector by
about 79 Hz, roughly 15× the 5.10 Hz same-cue noise. It is **not** a measured
offset between YES and NO framings, and it is not in CIRCUIT-score units. It
supports the argument by analogy, and is recorded here as exactly that.

### 2.3 Drop balancing

**Correction: YES and NO drive is not equal within a pair.** The decision note
says total drive is equal between YES and NO by construction under mirroring.
That is not what the encoder does. Checked with the encoder alone (no
simulation), the YES and NO stimuli of one pair differ in total drive by

```text
D_YES(v) − D_NO(v) = 100 KCs × [r(v) − r(1−v)] = 12,000 × (2v − 1) Hz,
```

which is zero only at `v` = 0.50. For example, at `v` = 0.94 the difference is
+10,560 Hz (50,280 against 39,720 Hz).

**What is true, and is the actual case for dropping balancing:**

- **No framing is favoured.** The drive a framing receives depends only on the
  value it presents: `D_NO(v) = D_YES(1−v)` exactly. Neither framing carries a
  drive advantage of its own.
- **The pair's combined drive is constant.** `D_YES(v) + D_NO(v)` = 90,000 Hz at
  every `v`.
- **The drive difference behaves like the edge.** It is antisymmetric in `v` and
  zero at 0.50.
- **Balancing adds cost for no structural gain.** It added a 300-KC pool and up
  to 21,000 Hz of drive to remove this within-pair difference. Its opposition to
  the price pool was measured only on bilateral pools
  (`balanced-encoding-failure.md` §2b). That observation may not reproduce with
  left-only pools, and this design does not rely on it either way.

**What dropping balancing costs, stated so it is not assumed away.** Within a
pair, the favoured framing is also the more strongly driven one. `S(v)` therefore
confounds price-pool identity with total-drive magnitude, which is the
intensity-bias confound balancing was introduced to remove
(`unbalanced-single-framing-diagnostic.md` §6).

- **What this validation covers.** It validates the encoder as a whole: pattern
  plus drive, which is exactly what a market decision would present.
- **What it cannot do.** It cannot say how much of `S` comes from pool identity
  and how much from drive.
- **Intensity-bias mitigation is still open.** Before any learning experiment,
  it must be decided separately whether the drive component is acceptable or
  needs mitigation, for example by innate-score subtraction, whose validation gap
  is recorded in `balanced-encoding-failure.md` §4c.
- **Encoder defaults are unchanged.** The runner passes
  `variant = OPTION_B_UNBALANCED` explicitly. The `EncoderParams` default
  (`total_drive_balanced`) is not changed here; changing it is a separate
  decision.

## 3. Protocol (fixed)

### 3.1 Encoder and pools

- **Encoder:** `KCEncoder(left_kc_ids())`, default `EncoderParams`, pool seed
  **20260401**.
- **Feature pools:** five pools of 100 KCs: `price`, `recent_change`,
  `time_to_resolution`, `liquidity`, `signal`. These are **identical to
  `left_ladder_500`'s pools** and to the realistic-drive diagnostic's feature
  pools, because the encoder is constructed the same way.
- **Balance pool:** the constructor still draws a 300-KC balance pool, but it is
  **never presented**.
- **Guard:** before the model is built, `_assert_pools_left_only` (as in the fixed
  graded runners) must confirm that every KC in every pool, including the unused
  balance pool, is annotated left. The runner aborts otherwise.
- **Variant:** `OPTION_B_UNBALANCED`. The YES and NO stimuli each drive exactly
  500 KCs, with no `__total_drive_balance__` entry.
- **Background:** `recent_change = 0.0`, `time_to_resolution = 182.5`,
  `liquidity = 0.5`, `signal = 0.5`, each encoding to 90 Hz. The two mirrored
  background features (`recent_change` and `signal`) sit at their mirror-fixed
  points. That is what makes `NO(v) ≡ YES(1−v)` exact.
- **Price rate:** `r(v) = 30 + 120 v` Hz. The YES price pool presents `r(v)` and
  the NO price pool presents `r(1−v)`.

**Checks before any simulation (the runner aborts on failure, with no verdict):**

1. For each tested `v`, the NO stimulus equals the YES stimulus at `1−v`: same
   KC IDs, same rates, bit-for-bit.
2. Neither stimulus contains the balance pool, and each drives 500 KCs.
3. No feature value is clipped.
4. `D_YES − D_NO` equals `12,000 × (2v − 1)` Hz to floating-point precision. It is
   recorded for each value, not required to be zero.

### 3.2 Seeds, presentation, count

- **Primary seed:** **20260316**.
- **Repeat seeds:** **20260317, 20260318, 20260319, 20260320, 20260321**.
- **Common random numbers:** at every seed, YES and NO at all five values share
  that seed, as in the superseded spec.
- **Presentation:** 1000 ms × 5 trials per stimulus.
- **Count:** 6 seeds × 5 values × 2 framings = **60 simulations**. None is
  shared with any earlier run: set B's stimuli were never presented (§3.4).

### 3.3 Why non-reflective

With a reflective set, the same numbers get counted twice:

- `v` and `1−v` are one measurement taken twice.
- The midpoint score is forced to zero rather than measured.
- The endpoint change `c(1) − c(0)` equals `−2·c(0)` exactly. That doubles the
  endpoint signal and its noise together, so the "doubling" is an artefact of
  the construction, not extra evidence.

This is why the balanced run's pairwise noise table repeated itself (§2a there).
A **non-reflective** set therefore requires:

- no two values sum to 1;
- no value is 0.50;
- every mirrored partner `1−v` maps to a rate inside 30–150 Hz, so nothing clips.

### 3.4 Candidate value sets

For each set, `min |vᵢ+vⱼ−1|` is the reflection margin: how close its nearest
pair comes to being a reflection. Zero would be a reflection.

| set | values | sided | min \|vᵢ+vⱼ−1\| | YES price Hz | NO price Hz |
|---|---|---|---:|---|---|
| **A** | 0.05, 0.22, 0.41, 0.63, 0.88 | two-sided | 0.04 | 36.0–135.6 | 44.4–144.0 |
| **B (adopted)** | **0.56, 0.64, 0.73, 0.83, 0.94** | **one-sided** | **0.20** | **97.2–142.8** | **37.2–82.8** |
| **C** | 0.10, 0.31, 0.58, 0.78, 0.96 | two-sided | 0.06 | 42.0–145.2 | 34.8–138.0 |

**Set A: the unbalanced diagnostic's set.**

- *For:* it is continuous with two recorded runs, and it spans the whole range.
- *Against, redundancy:* its closest pair (0.41 and 0.63, sum 1.04) is nearly a
  reflection, so `S(0.41) ≈ −S(0.63)`.
- *Against, a free step:* its middle step crosses 0.50, where antisymmetry
  guarantees a sign change.
- *Against, contamination:* **its five YES stimuli have already been presented
  left-only**, in the realistic-drive diagnostic. Their six-seed mean scores were
  −146.38, −154.58, −159.27, −167.86 and −176.27 Hz, which is monotone. Half of
  this set's stimuli are therefore already seen.

**Set B: one-sided (adopted).**

- *Structure:* all values lie above 0.50, so every pairwise sum exceeds 1 and the
  set cannot be reflective. The reflection margin is 0.20, set by 0.56 + 0.64.
- *Edges:* the edge sizes `|v−0.5|` are 0.06, 0.14, 0.23, 0.33 and 0.44. They run
  from almost no edge to almost the maximum, in unequal steps of 0.08, 0.09, 0.10
  and 0.11. The steps don't line up with the quartile grid or with set A.
- *Uncontaminated:* none of its ten stimuli (YES at `v`, NO = YES at
  0.44, 0.36, 0.27, 0.17, 0.06) has been presented before.
- *Nothing is lost by using one side.* The lower half of the value range is not
  left untested, because the NO framings present 37–83 Hz on the price pool.
  Mirroring makes `S` at `v < 0.5` equal to `−S(1−v)` at the same seed, so a
  lower-side set would add no information.

**Set C: two-sided, as far from reflection as a full-range set allows.** A
search over 0.01 steps found 0.06 to be about the best reflection margin
available to a five-value set spanning [≤ 0.10, ≥ 0.90] with values on both sides
of 0.50. This is a structural point: a two-sided set that spans the range cannot
avoid a near-reflective pair.

- *For:* it keeps full-range coverage while cutting A's near-redundancy.
- *Against:* it keeps the free sign-crossing step. It is also partly
  contaminated: NO(0.78) = YES(0.22), which the realistic-drive diagnostic already
  presented.

**Why the one-sided set is the more demanding test:**

1. **No free step.** In a two-sided set, antisymmetry forces `S` to change sign
   between the last value below 0.50 and the first above it. Any encoder whose
   contrast has the right sign passes that step, however weak it is. In set B
   every step must come from `S` growing with the edge.
2. **Five distinct edges, not roughly two and a half.** No pair is close to a
   reflection, so each value measures a different edge size.
3. **Smaller, finer steps.** Successive edges differ by 0.08–0.11, and the set
   includes a near-zero edge (0.06) right next to the forced zero. That tests
   resolution where the signal is smallest.
4. **No near-doubling at the endpoints.** A two-sided set's endpoints are close
   to opposite contrasts, so the endpoint distance is roughly `2|c|`. In set B it
   is `‖c(0.94) − c(0.56)‖`, a genuine difference between two edges on one side.

**Adopted: set B.** The owner may substitute A or C under the exception in the
status block.

## 4. Statistic (fixed)

Let `m_yes,s(v)` and `m_no,s(v)` be the 96-instance MBON mean-rate vectors at
seed `s`, with silent instances counted as zero. Then

```text
c_s(v) = m_yes,s(v) − m_no,s(v)
S_s(v) = circuit_score_difference(m_yes,s(v), m_no,s(v), labels, CIRCUIT-80, "type_mean")
       = CIRCUIT(m_yes,s(v)) − CIRCUIT(m_no,s(v))
```

using the **CIRCUIT-80** sign table and the **per-type mean** aggregation. The
contrast vector is never passed to `circuit_score` directly: the readout rejects
negative entries, and the difference form is the one the superseded spec's
analysis was corrected to use (`balanced-encoding-failure.md` §1). The seed mean
is

```text
S̄(v) = mean over all six seeds of S_s(v).
```

## 5. Noise floor: measured directly, never derived analytically

For repeat seed `k` (the five repeat seeds only) and any pair of tested values
`(a, b)`:

```text
Δ_k(a,b)      = c_k(b) − c_k(a)
d_change(a,b) = mean over i<j of ‖Δ_i(a,b) − Δ_j(a,b)‖        (10 seed pairs)
T(a,b)        = 3 × d_change(a,b)
```

This is computed for all 10 value pairs, not only the endpoints, because the
sub-range gate needs pair-specific thresholds.

**Why the analytic shortcut is rejected.** An analytic threshold would treat the
YES and NO runs as independent, and approximate the change-in-contrast noise as
`√2` times a single-contrast noise. That is `3 × √2 × 5.10 = 21.64 Hz` from the
old `d_AA`. The superseded spec already refused it, before its run, and the run
showed why:

- **Shared seeds correlate the noise.** YES and NO share a seed, and the
  seed-differences of the two framings were positively correlated (mean cosine
  +0.174 at `v` = 0.00, +0.591 at `v` = 0.25).
- **The measured factor was ×1.02, not ×1.41.** Combining the four runs behind
  one change-in-contrast cost almost nothing (`balanced-encoding-failure.md` §2c).
- **Noise depends on the stimulus.** It varied about sevenfold across stimuli of
  one family (§2d there).

No number derived from `d_AA`, from `√2`, or from any earlier run is used as a
threshold here. There is no numeric threshold until the repeat data exist. What
is fixed in advance is the formula, the seeds and the factor of 3
(`gc.NOISE_MARGIN`).

## 6. Pre-stated criteria (three outcomes)

The standard is carried over **unchanged** from
[`graded-encoding-balanced.md`](graded-encoding-balanced.md) §5, with one
exception: monotonicity is judged on the seed mean (§7). Write `v₁ < … < v₅` for
the adopted set, so for set B `v₁` = 0.56 and `v₅` = 0.94.

"Strictly monotonic" means every successive difference of `S̄` is greater than
zero, or every one is less than zero. An exact tie breaks monotonicity. Either
direction is accepted, and the direction is reported.

- **ACCEPTED.** Both of:
  - `S̄(v)` is strictly monotonic across all five values;
  - the primary-seed endpoint distance `‖c₀(v₁) − c₀(v₅)‖` is at least
    `T(v₁, v₅)`, where `c₀` is the contrast at seed 20260316.
- **USABLE RANGE.** All of:
  - the full endpoint distance passes;
  - `S̄` is not strictly monotonic across all five values;
  - the longest strictly monotonic **contiguous** sub-range spanning at least
    three tested values (`gc.MIN_SUBRANGE_RATES` = 3) has a primary-seed endpoint
    distance at least its own pair-specific `T(a, b)`.
- **FAIL.** Any of:
  - the full endpoint distance is below `T(v₁, v₅)`;
  - no strictly monotonic contiguous sub-range spans at least three values;
  - the chosen sub-range's endpoint distance is below its `T(a, b)`.

  The encoder must then change before any learning experiment.

Gate order and sub-range rules, as before:

- The full endpoint gate is applied first.
- Among tied longest sub-ranges, choose the one with the larger absolute change
  in `S̄` between its endpoints, then the lower starting value.
- The sub-range gate is applied to that one chosen range only, with no fallback.

**For USABLE RANGE:**

- Report the validated interval of `v`, its YES price rates and its mirrored NO
  rates.
- The reflected interval (`1−b` … `1−a`) is validated **by the exact identity
  `S(1−v) = −S(v)`, not by a separate measurement**. Report it as such.
- A USABLE RANGE result does not silently change `min_rate_hz` or
  `max_rate_hz`. A restricted mapping must be specified before learning.

**For FAIL,** no range is validated.

**Proposal not adopted.** The balanced failure analysis also proposed requiring
each step to clear its own noise (`balanced-encoding-failure.md` §2b-bis, items
2–3). That is **not** adopted, so the standard stays as it was.

## 7. Deliberate change: monotonicity on the seed mean (2026-09-27)

**What changes.** The superseded spec judged monotonicity from the primary seed
alone. This spec judges it from `S̄`, the mean over **all six** seeds. All six
per-seed sequences `S_s(v)` are reported beside the mean. The endpoint and
sub-range distance gates still use the primary seed's contrast vectors against
thresholds from the five repeat seeds, exactly as before.

**Why.** It carries forward a recorded finding: a one-seed monotonicity judgement
is underpowered (`balanced-encoding-failure.md` §2b-bis). In the balanced run, the
primary seed's −102.3 at `v` = 0.25 sat about 1.1 SD from the repeat-seed mean
(+2.6 ± 41.8 SE). The single-seed ordering the verdict recorded was a noise
artefact. The same rule was already used, for that diagnostic only, in the
unbalanced single-framing diagnostic §5. It is adopted here for a validation,
written before the run it governs.

**What this change does not do.** It does not loosen the endpoint gate, the
factor of 3, the three-value minimum or the gate order.

## 8. Planning estimate (not a criterion)

This estimate uses data **already seen** (the realistic-drive YES scores at set
A's values). It is recorded so the power of the design is visible on paper, and
nothing in §6 depends on it.

Interpolating those scores linearly gives a slope of about −36 Hz per unit `v`,
so `S(v) ≈ −36 × (2v − 1)` Hz. At set B that predicts:

- `S` ≈ −4.3, −10.1, −16.6, −23.8, −31.7 Hz;
- successive steps of about 5.8–7.9 Hz.

With a per-seed score SD of 0.9–2.1 Hz, `S_s` should have an SD of about 1.3–3.0
Hz if its two halves are independent. The six-seed mean would then have a
standard error of about 0.5–1.2 Hz, so each predicted step would be about 5–15
standard errors. **The endpoint distance gate cannot be estimated this way.** It
compares a 96-dimensional vector distance against a vector noise floor, and no
left-only change-in-contrast has ever been measured. The gate may fail even if
`S̄` is monotone. That is an honest risk of this design, not something to tune
away.

## 9. Recorded, reported, enforced

**Per (value, seed) file:**

- the pools and the YES and NO per-pool rates;
- `D_YES`, `D_NO` and their difference;
- for **both** framings, the trial-mean rate vectors for MBONs, Kenyon cells,
  APL, PAM and PPL1;
- per-trial Kenyon cell, MBON and APL rates, as in the realistic-drive runner;
- the stimulated KC IDs, seed, duration and trial count;
- **no verdict**.

**Recruitment intensity for every presentation (60 × 2 = 120).** Reported
beside the binary label, which it does not replace
([`recruitment-intensity-measure.md`](recruitment-intensity-measure.md)):

- the binary ignition label: non-stimulated KC active fraction above 1%, from
  the trial mean;
- the active fraction split by hemisphere;
- `recruited_kc_mean_rate_hz` and `recruited_kc_median_rate_hz` (null when
  nothing is recruited), per presentation and per trial.

Ignition is **reported, not gated**. The superseded standard had no ignition
criterion, and adding one would change the standard.

**Verdict file:**

- `S_s(v)` for every seed, `S̄(v)`, the direction, and whether `S̄` is monotonic;
- all 10 values of `d_change(a,b)` and the thresholds actually used;
- the primary-seed endpoint and sub-range distances, and the chosen sub-range;
- the reflected interval, if there is one;
- a per-stimulus recruitment summary;
- `is_a_validation: true`, `has_pass_criterion: true`, `spec`, and the value set;
- the verdict.

**Enforcement, which differs from the diagnostics.** The diagnostic enforcement
(no `verdict` key, `has_pass_criterion: false`, and none of PASS, FAIL, ACCEPTED
or USABLE RANGE anywhere) **does not apply** and must not be reused. For this
validation:

1. The verdict file must contain `is_a_validation: true`,
   `has_pass_criterion: true`, and exactly one `verdict` whose value is one of
   `ACCEPTED`, `USABLE RANGE` or `FAIL`.
2. The diagnostic word `PASS` must not appear anywhere in the verdict file.
3. No per-(value, seed) file may carry a verdict.
4. No verdict is produced unless all 60 files exist and every §3.1 check has
   passed.
5. The runner's gate constants must equal the pre-stated ones: factor 3.0, a
   three-value minimum sub-range, seeds and value set as in §3.

The runner's tests must check all five, on fakes only. They must include at
least one fake dataset for each outcome, and a canary that must fail if a
diagnostic word or a missing verdict slips through.

## 10. What this can and cannot conclude

**Can:**

- Return ACCEPTED, USABLE RANGE or FAIL for **the mirrored, unbalanced market
  encoder, with left-only pools from pool seed 20260401**, on the price feature,
  with the other features at their midpoints.
- Say whether `S̄` is monotone across edges from 0.06 to 0.44 (set B), and
  whether its endpoint change clears three times its directly measured noise.
- Extend any validated interval to its reflection, by exact identity.

**Cannot:**

- **Validate anything other than this encoder.** Not balanced Option B, not a
  non-mirrored framing, not Option A, not bilateral pools, not another pool seed
  or pool size.
- **Test the learning rule** (plasticity, reward, dopamine compartments), **the
  market task** (synthetic or real markets, abstention, margins), or **any
  framing other than mirrored**.
- **Separate price-pool identity from total drive** (§2.3). The intensity-bias
  mitigation question stays open.
- **Say anything about features other than price**, or about non-midpoint
  backgrounds. With a background feature off its mirror-fixed point, the swap
  identity no longer holds.
- **Separate hemisphere from pool draw.** One left draw is tested.
- **Generalise beyond 1000 ms × 5 trials**, or beyond the six seeds' estimate of
  noise.

## 11. Cost

60 simulations at 1000 ms × 5 trials, plus one build of about 4 s:

- at **54.4 s per simulation**, measured from the realistic-drive diagnostic's
  file-write times on the author's machine at this drive level: about
  **54.5 minutes**;
- at the older 50.5 s planning figure: about 50.6 minutes.

Both figures are unverified on other machines. Nothing reported here depends on
them.

## 12. Outputs, stopping rule, command

- **Files:** one JSON per (value, seed),
  `graded_left_mirrored_value_<v>_seed_<seed>.json`, and one verdict file,
  `graded_left_mirrored_verdict.json`. Each file stays below 5 MB, the ceiling
  that allows for the per-trial arrays.
- **Order:** the 50 repeat-seed simulations run first and the 10 primary-seed
  simulations last, as before.
- **Restarts:** the runner skips any (value, seed) whose file already exists.
- **Stopping:** stop once the verdict is computed. Do not add values or seeds,
  change the statistic or the thresholds, or loosen a gate after seeing results.
  Any later analysis is exploratory and must be labelled as such.

**The runner does not exist yet.** Once
`repro/mushroom_body/run_graded_encoding_left_only_mirrored.py` is written to this
document, the run is:

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_graded_encoding_left_only_mirrored.py
```

`--dry-run` and `--analyze-only` must neither build the model nor open the
connectome, and importing the module must not either.
