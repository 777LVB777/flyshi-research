# Rate-weighted recruitment: a measure alongside the binary ignition label

**Status: RETROSPECTIVE ANALYSIS, 2026-09-27. Not a validation, no pass
criterion, no verdict.** Computed by
`repro/mushroom_body/analyze_recruitment_intensity.py` from result files already
on disk. No simulation was run to produce this document, and no existing result
or summary file was changed.

## 1. Why

The left-only population-scaling ladder's one ignition event, seed 20260317 at
300 KCs, recruits non-stimulated KCs at a mean of **1.17 Hz**. The bilateral
ladder's ignited runs recruit at **14–34 Hz**
([`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md) §5). The
existing binary label — active fraction above 1% — counts both as *ignited* and
reports nothing else about them. It cannot express that difference, because it
was never designed to: it answers "did the network cross this fraction
threshold", not "how hard are the cells it recruited firing".

## 2. The measure

For a saved (condition, seed) result, with `N` the non-stimulated KCs and
`ACTIVE_HZ = 0.5` the existing per-cell active threshold (unchanged, used
elsewhere for MBON/PAM/PPL1 "active" counts too):

```text
active(N)  = { i in N : rate_i > 0.5 Hz }
```

**Kept, unchanged:**

```text
active_fraction  = |active(N)| / |N|
ignited          = active_fraction > 0.01        # the existing 1% label
```

**Added:**

```text
recruited_kc_mean_rate_hz   = mean(rate_i for i in active(N))
recruited_kc_median_rate_hz = median(rate_i for i in active(N))
```

**Null, not zero, when nothing is recruited.** If `active(N)` is empty, both
new fields are reported as `null`. Zero recruited KCs is a different claim from
recruited KCs firing at 0 Hz, and the whole point of this measure is not to blur
that kind of distinction; reporting `0.0` would blur it.

**What this does not change.** `active_fraction` and `ignited` are computed
exactly as before, from the same per-neuron rate vectors, with the same
threshold. Nothing about the existing label is redefined, and no result or
summary file was rewritten — this is a new, separate readout of data already
saved.

**Median alongside mean.** Reported because a mean over a few thousand active
KCs could in principle be dragged by a handful of outliers; in every row
computed here the two are close, so the mean is not misleading in this data, but
both are reported rather than asserting that in advance.

## 3. Applied retrospectively: full results

All figures from `repro/mushroom_body/analyze_recruitment_intensity.py --json`.
`—` means zero non-stimulated KCs were active (fields are `null`), not a
measured 0 Hz.

### 3a. Bilateral population-scaling ladder

| condition | seed | active% | ignited | recruited mean Hz | recruited median Hz |
|---|---:|---:|---|---:|---:|
| `ladder_100` | all 6 | 0.0% | no | — | — |
| `ladder_200` | 20260316 | 65.5% | yes | 16.06 | 16.40 |
| `ladder_200` | 20260317 | 65.6% | yes | 20.52 | 21.00 |
| `ladder_200` | 20260318 | 65.1% | yes | 9.43 | 9.60 |
| `ladder_200` | 20260319 | 65.6% | yes | 16.15 | 16.40 |
| `ladder_200` | 20260320 | 65.9% | yes | 30.33 | 31.00 |
| `ladder_200` | 20260321 | 65.6% | yes | 19.78 | 20.20 |
| `ladder_300` | 20260316 | 66.5% | yes | 34.17 | 35.00 |
| `ladder_300` | 20260317 | 66.4% | yes | 31.46 | 32.20 |
| `ladder_300` | 20260318 | 66.5% | yes | 30.39 | 31.20 |
| `ladder_300` | 20260319 | 66.6% | yes | 29.08 | 29.80 |
| `ladder_300` | 20260320 | 66.1% | yes | 13.67 | 14.00 |
| `ladder_300` | 20260321 | 66.5% | yes | 25.58 | 26.20 |
| `ladder_400` | 20260316 | 67.0% | yes | 23.76 | 24.40 |
| `ladder_400` | 20260317 | 67.1% | yes | 28.00 | 28.60 |
| `ladder_400` | 20260318 | 67.1% | yes | 26.98 | 27.60 |
| `ladder_400` | 20260319 | 67.2% | yes | 32.59 | 33.40 |
| `ladder_400` | 20260320 | 67.2% | yes | 34.39 | 35.20 |
| `ladder_400` | 20260321 | 67.1% | yes | 29.76 | 30.40 |
| `ladder_500` | 20260316 | 66.7% | yes | **5.60** | 5.60 |
| `ladder_500` | 20260317 | 67.5% | yes | 21.44 | 22.00 |
| `ladder_500` | 20260318 | 67.9% | yes | 27.04 | 27.80 |
| `ladder_500` | 20260319 | 66.9% | yes | 9.46 | 9.60 |
| `ladder_500` | 20260320 | 67.4% | yes | 17.11 | 17.50 |
| `ladder_500` | 20260321 | 67.3% | yes | 10.47 | 10.80 |
| `anchor_100at150` | 20260316 | 47.0% | yes | **0.85** | 0.80 |
| `anchor_100at150` | 20260317 | 62.6% | yes | **1.95** | 2.00 |
| `anchor_100at150` | 20260318 | 0.0% | no | — | — |
| `anchor_100at150` | 20260319 | 63.2% | yes | **2.19** | 2.20 |
| `anchor_100at150` | 20260320 | 65.1% | yes | 8.58 | 8.80 |
| `anchor_100at150` | 20260321 | 0.0% | no | — | — |
| `drive_matched_500at30` | 20260316 | 0.0% | no | — | — |
| `drive_matched_500at30` | 20260317 | 65.7% | yes | 24.97 | 25.40 |
| `drive_matched_500at30` | 20260318 | 65.5% | yes | 15.08 | 15.40 |
| `drive_matched_500at30` | 20260319 | 65.3% | yes | 10.83 | 11.00 |
| `drive_matched_500at30` | 20260320 | 64.7% | yes | **4.26** | 4.40 |
| `drive_matched_500at30` | 20260321 | 0.0% | no | — | — |

### 3b. Left-only population-scaling ladder

| condition | seed | active% | ignited | recruited mean Hz | recruited median Hz |
|---|---:|---:|---|---:|---:|
| `left_ladder_100` | all 6 | 0.0% | no | — | — |
| `left_ladder_200` | all 6 | 0.0% | no | — | — |
| `left_ladder_300` | 20260317 | 58.7% | yes | **1.17** | 1.20 |
| `left_ladder_300` | other 5 | 0.0% | no | — | — |
| `left_ladder_500` | all 6 | 0.0% | no | — | — |

### 3c. Left-only pool diagnostic (150 Hz)

All 6 seeds: 0.0% active, not ignited, `—`. Nothing to add; included for
completeness since it is part of the same retrospective sweep.

## 4. How the ladder tables change

**4a. "6/6 ignited" at a mature rung hides up to a 6× spread in recruitment
intensity, even though the active fraction barely moves.** Within `ladder_500`,
active fraction is 66.7–67.9% at every seed — a 1.2-point range — while the
recruited mean rate ranges from **5.60 to 27.04 Hz**, a 4.8× range. `ladder_400`
is tighter (23.76–34.39 Hz) but still a 1.4× range at a near-constant fraction
(67.0–67.2%). The binary label and the fraction it thresholds both look stable
across seeds at a mature rung; the intensity measure shows they are not.

**4b. `anchor_100at150` — the bilateral benchmark used throughout the left-only
diagnostics — turns out to be weak-intensity ignition, not saturating
ignition.** This condition (100 KCs, 150 Hz) is the one the left-only pool
diagnostic compares against directly
([`left-only-pool-diagnostic.md`](left-only-pool-diagnostic.md)): "0/6 ignited"
left-only versus "4/6 ignited, score SD 25.90 Hz" bilateral. Its four ignited
seeds recruit at **0.85, 1.95, 2.19 and 8.58 Hz** — an order of magnitude below
the 9–34 Hz seen once the ladder reaches 200+ KCs, and the same order of
magnitude as `left_ladder_300`'s single 1.17 Hz event. **Read this way, the
recorded "0/6 vs 4/6" comparison is better described as "contained vs weakly,
low-intensity recruited" than as "contained vs saturating".** The score SD
(25.90 Hz) is still far above the left-only ladder's 0.5–5.1 Hz, so the finding
in [`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md) that pool
composition drives the noise is unaffected; what changes is how "ignited" at
this specific condition should be read in comparison with the mature rungs.

**4c. `drive_matched_500at30` spans both regimes within one condition.** Its
four ignited seeds run 4.26 to 24.97 Hz — from the weak end to well into the
range seen at mature bilateral rungs.

**4d. No clean bimodal split.** Sorting every ignited seed's recruited mean rate
across every bilateral condition: 0.85, 1.95, 2.19, **4.26**, **5.60**, 8.58,
9.43, 9.46, 10.47, 10.83, 13.67, 15.08, 16.06, 16.15, 17.11, 19.78, 20.52, 21.44,
23.76, 24.97, 25.58, 26.98, 27.04, 28.00, 29.08, 29.76, 30.33, 30.39, 31.46,
32.59, 34.17, 34.39. The low end (0.85–2.19 Hz, all from `anchor_100at150`) and
the high end (23.76–34.39 Hz, all from `ladder_300`/`ladder_400`) are clearly
separated, but the middle is filled in continuously — `ladder_500`'s 5.60 Hz and
`drive_matched_500at30`'s 4.26 Hz sit inside what would otherwise look like a
gap. **This is reported as a continuum, not a second bimodal structure**;
claiming a clean low/high split would overstate what 32 ignited seeds show.

## 5. What this does and does not establish

**Does:**

- Show concretely that the binary ignition label collapses a **≥30-fold** range
  of recruitment intensity (0.85 to 34.4 Hz among ignited seeds) into one
  category.
- Show that `anchor_100at150`'s ignition and `left_ladder_300`'s single event
  are the same order of magnitude, both far below the mature bilateral rungs.
- Give a concrete number for "weak" versus "strong" recruitment that a future
  pre-statement can use, if one chooses to.

**Does not:**

- **Define or endorse a new threshold.** No pass/fail line is drawn on
  recruited rate anywhere in this document. §4d reports a continuum precisely so
  no such line is misread into it.
- **Explain why intensity varies.** This is descriptive, like the APL
  observation in [`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md)
  §4: correlation with rung, seed and condition, not a mechanism.
- **Apply to the two graded runs** (balanced, unbalanced Option-B). Both save
  MBON rates only, not per-KC Kenyon-cell rates, so `active(N)` cannot be
  computed for them. This is the same gap already recorded in
  [`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md) §3.1: their
  ignition is inferred, not measured, and this measure cannot close that gap
  retrospectively without new simulation.
- **Replace the binary label.** `active_fraction` and `ignited` remain exactly
  as defined and computed everywhere they were before; this is reported beside
  them, not instead of them.

## 6. Script and outputs

`repro/mushroom_body/analyze_recruitment_intensity.py`: reads existing
`population_scaling_*`, `left_only_scaling_*` and `left_only_pool_*` result
files under `repro/mushroom_body/results/`, computes the measures in §2, and
prints the table in §3. `--json PATH` additionally writes the full per-seed
data. It runs no simulation and imports no Brian2 at module level or otherwise;
it only reads files already on disk. It does not write to, or modify, any
existing result or summary file.
