# Drive-adjusted readout: secondary analysis of the left-only mirrored validation

**Status: PRE-STATED, 2026-09-28 00:24 EDT.** This was written while the
left-only mirrored validation
([`graded-encoding-left-only-mirrored.md`](graded-encoding-left-only-mirrored.md))
was still running:

- 59 of its 60 result files existed;
- **its verdict file did not exist** (checked by directory listing only);
- **no result file of that validation was opened** in writing this document or
  computing its constants.

> **Timeline, recorded exactly (file modification times; the verdict was not
> opened):**
>
> - `drive-adjusted-readout-constants.json` frozen at **00:24:10**;
> - verdict absence checked at **00:24:36**;
> - `graded_left_mirrored_verdict.json` written by the running validation at
>   **00:24:52**;
> - this document first saved at **00:25:31**.
>
> So **the constants predate the verdict**. This document's text was completed
> **39 s after** the verdict file appeared. The verdict had not been opened, read
> or summarised by anyone involved in writing it, and nothing in it depends on the
> verdict. The claim above that the verdict file "did not exist" was true at the
> 00:24:36 check, not at the moment of saving. This note corrects that; nothing
> else is changed.

The analysis is **not implemented yet**. Its formula, constants, decision rule,
outputs and interpretation are fixed here and must not be revised after the
primary verdict or any validation result has been seen.

## 1. Status relative to the primary verdict

**The primary pre-stated verdict stands, whatever this analysis shows.** That is
the ACCEPTED / USABLE RANGE / FAIL returned by
`run_graded_encoding_left_only_mirrored.py` under its own spec. This analysis:

- is **secondary**. It is reported beside the primary verdict and **cannot
  overturn, replace, qualify or re-grade it**;
- **authorises nothing**. It validates no encoder and invalidates none (§5);
- **exists for one reason**: the drive confound
  ([`drive-confound.md`](drive-confound.md)) was identified before the primary
  verdict was seen, and this is the one mitigation that can be applied to that
  validation's saved data.

## 2. Motivation: pool identity registers in the MBON vector, not in the score

From saved left-only realistic-drive results, collected before this validation
(`drive-confound.md` §2.3):

- **The drive directions nearly coincide.** Adding drive through a 300-KC balance
  pool the price sweep never touches moves the 96-instance MBON vector almost the
  same way as raising the price pool's rate: **cosine 0.977**.
- **About 21% of that change points elsewhere.** For example, 40 Hz of a 186 Hz
  change is orthogonal to the price-change direction.
- **That remainder is real.** It exceeds both reference levels:
  - the **split-half** self-agreement of each change, cosine 0.997–0.999 (≈ 0.998);
  - the **operating-point drift** along the price sweep itself on the same KCs,
    cosine 0.995.
- **The scalar score does not register it.** Over 40–60 kHz, the CIRCUIT-80
  per-type-mean score of all seven left-only stimuli fits a single function of
  total drive. A quadratic fitted only to the price sweep predicts the two
  balance-pool stimuli to within 0.11 and 0.32 Hz, inside one standard error.

**This points at the readout, not the encoder.** The information that separates
KC sets is present in the MBON pattern. The per-type mean appears to discard it,
or compress it into a direction that is almost collinear with generic drive.

**Open question, not addressed here:** would a vector-level or pattern-sensitive
readout recover what the per-type mean discards? Examples include a projection
orthogonal to the generic-drive direction, a per-instance weighted readout, or a
classifier on the MBON vector. Any such readout would need its own pre-statement
and its own validation. Nothing below tests it.

## 3. The analysis

### 3.1 Fitted constants (frozen)

Stored in
[`drive-adjusted-readout-constants.json`](drive-adjusted-readout-constants.json),
SHA-256 `86fd10391520f4bafb0657d94b593cbe10ce26f000011099b72e306f94e7f995`. They
were computed only from the left-only realistic-drive diagnostic's files, whose
SHA-256 hashes are recorded in that file. **All of those data were collected
before this validation; none of the constants was tuned on it.**

Units: drive `D` is total imposed KC drive in **kHz**; slopes are in Hz of score
(or of MBON rate) per kHz.

| constant | value | SE | source |
|---|---:|---:|---|
| `b_A`, score slope, price sweep | **−2.936** Hz/kHz | 0.063 | 5 unbalanced YES stimuli; only the price pool's rate varies, on the same 500 KCs; per-seed linear fits, 6 seeds |
| `β_A`, per-MBON slope vector (96) | in constants file | per instance | same stimuli, linear fit of each instance's seed-mean rate |
| `b_B`, score slope, non-price drive | **−2.672** Hz/kHz | 0.044 | balanced `v`=0.00 vs unbalanced `v`=0.05, and balanced `v`=0.25 vs unbalanced `v`=0.22, paired by seed; drive added through the 300-KC balance pool |
| `β_B`, per-MBON slope vector (96) | in constants file | per instance | same comparisons, paired by seed |

The two slope vectors `β_A` and `β_B` agree at cosine 0.977. The runner must
check that the validation's MBON label order equals the `mbon_labels` stored in
the constants file, and abort otherwise.

**Two adjustments are pre-stated, not one:**

- **Adjustment A** is the analysis the project owner specified, using the
  price-sweep slope −2.94 Hz/kHz.
- **Adjustment B** was added in writing this pre-statement, because of §3.4: with
  A's constant, the adjusted score collapses toward zero by construction, however
  much pool identity matters. B uses the only pre-validation estimate of drive
  delivered through non-price KCs.

Both are reported. Neither is preferred over the other, and neither affects the
primary verdict.

### 3.2 Formula

For each presentation `p` (value `v`, framing YES or NO, seed `s`) with imposed
drive `D_p` in kHz:

```text
score_adj,X(p) = CIRCUIT(m_p) − b_X · (D_p − 45)            X ∈ {A, B}
m_adj,X(p)     = m_p − β_X · (D_p − 45)
```

The reference point 45 kHz cancels in every contrast and has no effect on any
result. For set B, the imposed drives are known exactly from the stimuli:
`D_YES = 36 + 0.1·r(v)` and `D_NO = 36 + 0.1·r(1−v)`, with
`r(v) = 30 + 120 v`. So

```text
ΔD(v)      = D_YES − D_NO = 12 (2v − 1) kHz           (1.44, 3.36, 5.52, 7.92, 10.56)
S_adj,X(v) = S(v) − b_X · ΔD(v)
c_adj,X(v) = c(v) − β_X · ΔD(v)
```

- `S(v) = CIRCUIT(m_yes) − CIRCUIT(m_no)` is computed exactly as the primary
  analysis does, via `circuit_score_difference`, CIRCUIT-80, per-type mean.
- The scalar adjustment uses `b_X`; the vector adjustment uses `β_X`.
- The adjusted vector is never passed to the readout.

**Noise floors are unchanged, exactly.** The adjustment is a fixed function of
`v`, identical at every seed. In
`Δ_i(a,b) − Δ_j(a,b) = [c_i(b) − c_i(a)] − [c_j(b) − c_j(a)]` the adjustment
terms `β_X (ΔD(b) − ΔD(a))` cancel. Therefore
`d_change,adj(a,b) = d_change(a,b)` for every pair, and the thresholds
`T(a,b) = 3 × d_change(a,b)` are the primary analysis's thresholds. They are not
re-estimated.

### 3.3 Decision rule (identical in form to the primary rule)

For each adjustment X, apply the primary spec's §6 rule without change, with:

- monotonicity judged on the six-seed mean `S̄_adj,X(v)`;
- the endpoint and sub-range distances computed from the **primary seed's**
  `c_adj,X`, against the **unchanged** thresholds `T(a,b)`;
- the same three-value minimum sub-range, gate order and tie-breaks.

This yields an **adjusted outcome**, one of ACCEPTED, USABLE RANGE or FAIL, for
each of A and B.

**Sensitivity check (reported, not decisive).** Recompute each adjusted outcome at
`b_X ± 2 SE`, with `β_X` scaled by the same factor. The adjusted outcome reported
is the one at the point estimate.

### 3.4 Predictions, stated before any validation result is seen

For every value in set B, `D_YES + D_NO = 90 kHz` exactly. Take any smooth
drive–score curve `g` on this one-dimensional stimulus family, and expand it to
second order. Then `S(v) = g(D_YES) − g(D_NO) = ΔD(v) · g′(45 kHz)` exactly: the
quadratic terms cancel because the two drives sum to a constant. The quadratic
fitted to the price sweep has `g′(45) = −2.918` Hz/kHz. If the validation
reproduces the realistic-drive curve, then:

- **A:** `S̄_adj,A(v) ≈ ΔD · (−2.918 + 2.936) = +0.018 · ΔD`. That is **0.03–0.19
  Hz, essentially zero**. The expected adjusted outcome is **FAIL**, and it is
  expected **by construction**.
- **B:** `S̄_adj,B(v) ≈ ΔD · (−2.918 + 2.672) = −0.246 · ΔD`. That is −0.35 to
  −2.60 Hz, with successive steps of about −0.5 to −0.65 Hz. Those steps are at or
  below the expected standard error of a seed-mean step (about 0.7–1.7 Hz, from
  the per-seed score SD of 0.9–2.1 Hz). The expected adjusted outcome is **FAIL or
  USABLE RANGE, decided largely by noise**.

These predictions are recorded so that a result matching them is not later
mistaken for a discovery, and a result departing from them is visible as such.

## 4. Outputs and ordering

- **Files:** one file, `repro/mushroom_body/results/graded_left_mirrored_drive_adjusted.json`.
  The primary verdict file is never modified.
- **Contents:**
  - `secondary_analysis: true`, `overrides_primary: false`, `is_a_validation: false`;
  - `primary_verdict_reported_unchanged`, copied from the primary verdict file;
  - for A and B: the constants used, `S̄_adj,X`, all per-seed `S_adj,X`,
    `adjusted_outcome_X`, the adjusted endpoint and sub-range distances, the
    thresholds (identical to the primary ones), and the sensitivity outcomes at
    ±2 SE;
  - the §3.4 predictions next to the observed values;
  - `constants_sha256` for the frozen constants file.
- **Key names:** the file uses `adjusted_outcome_*`, never `verdict`. It is never
  written into the primary verdict file, so the primary runner's rule of exactly
  one verdict key is untouched. The diagnostic word PASS does not appear.
- **Ordering:** the analysis code is written, and tested on fakes only, against
  this document. It may be written after the primary verdict exists, because the
  formula, constants and rule are frozen here. It is run once, on the 60 saved
  files. Nothing here may be revised after that.

## 5. What this analysis can and cannot conclude

**Neither outcome, for either adjustment, validates or invalidates the encoder
on its own.** The encoder's status is the primary verdict.

**Adjustment A (price-sweep constant):**

- **It cannot distinguish generic drive from pool identity.** Its constant was
  estimated by varying the price pool's own rate on the same 500 KCs. Every
  validation presentation lies on that same family of stimuli. Subtracting it
  removes the drive-proportional part of the price pool's own effect, whether
  that effect is generic intensity or specific to the price pool. **A collapse
  toward zero is predicted by construction (§3.4) and is not evidence that the
  baseline score is generic drive.**
- **What it can show** is a consistency check: whether the validation's `S(v)`
  reproduces the drive–score curve of the earlier diagnostic. A monotone,
  above-noise adjusted residual would mean the two datasets disagree. The cause
  could be run-to-run non-reproducibility, higher-order curvature, or an error.
  It would **not** show pool-identity encoding, because the calibration and the
  validation use the same pool.

**Adjustment B (non-price constant):**

- **What its interpretation would be, if it held.** The adjustment subtracts
  what the same drive delivered through *other* KCs would do.
  - If `S̄_adj,B` collapses toward the §3.4 prediction, that is **evidence
    consistent with the baseline score being largely generic drive**.
  - If it stays monotone and above noise **well beyond** that prediction, that is
    **evidence consistent with a price-pool-specific component**.
- **Why that is weaker than it sounds.** The constant is confounded in three
  ways:
  1. It was measured by **adding** 300 KCs (500 → 800), not by changing the rate
     of an equal-sized pool.
  2. It was measured over **40–60 kHz**, where the drive curve is shallower than
     at the validation's 45 kHz centre. §3.4's −0.246·ΔD residual is exactly this
     operating-point gap, and it would appear even with no identity effect.
  3. It rests on **two comparisons** that share one balance pool.
- **What B cannot do.** It cannot separate identity from KC count or operating
  point, and its predicted residual is near the noise. So B **cannot establish**
  pool-identity encoding, and it **cannot establish its absence**.

**Both adjustments:**

- They adjust the **scalar** readout by a **linear** drive model. They do not test
  the vector-level identity component of §2, and they do not test any other
  readout.
- They apply only to this encoder, this value set, the midpoint background and
  this pool draw.

**The measurement that would answer the question** is the pool-identity control
in [`drive-confound.md`](drive-confound.md) §3.5: the same rate changes applied
to a non-price pool of the same size, on the same KCs, at the same drives. It is
not part of this pre-statement.
