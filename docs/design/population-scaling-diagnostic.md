# Population-scaling diagnostic: what sets MBON score noise?

**Status: PRE-STATED; NOT RUN.** Written 2026-09-23, before the runner and before
any simulation. Fixed here: the conditions, the KC pools, the seeds, the
statistics reported, and what each comparison may and may not conclude.

**This is a DIAGNOSTIC, not a validation** (`is_a_validation: false` in every
output). **It has no pass criterion**, because it measures rather than judges.
The PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL vocabularies are reserved for
validations and pre-stated tests; nothing here may be quoted as either. No result
from this document can authorise an encoder, change a preregistered criterion, or
settle a design decision on its own.

## 1. Why

Two failures have been recorded — the balanced Option-B re-validation
([`balanced-encoding-failure.md`](balanced-encoding-failure.md)) and the
unbalanced single-framing diagnostic
([`unbalanced-single-framing-diagnostic.md`](unbalanced-single-framing-diagnostic.md))
— and the diagnosis of both ends at the same wall: same-stimulus, across-seed
score variability of 38–81 Hz when ~500–800 Kenyon cells are driven at once,
against 1.78 Hz when 100 are.

Existing data cannot say what drives that, because between the two regimes the
KC count (100 → 500), the total drive (15,000 → ~45,000 Hz), the number of active
MBONs (29 → 84) and the mean MBON rate (22 → 57 Hz) all move together. There is
also no measurement anywhere between 100 and 500 driven KCs, which is exactly
where the change happens. And APL — among the hardest-firing cells in the
antennal-lobe failure, and the mushroom body's main inhibitory element — has
never been recorded in any of these runs.

## 2. Conditions (fixed)

All stimuli are drawn from the **encoder's own seeded feature pools**
(`pool_seed = 20260401`, 100 KCs per pool), so every run here is directly
comparable with the balanced and unbalanced runs already saved. Ladder pools are
**nested** — each rung adds one pool to the previous rung — so the ladder varies
count without also re-drawing the KC identity.

Ladder pool order, fixed: `recent_change`, `time_to_resolution`, `liquidity`,
`signal`, `price`. This order makes the 400-KC rung **exactly the background of
the unbalanced diagnostic** (its four midpoint features, all at 90 Hz) and the
500-KC rung the full encoder at its midpoint.

| condition | KCs | per-KC rate | total drive | role |
|---|---:|---:|---:|---|
| `ladder_100` | 100 | 90 Hz | 9,000 | ladder rung |
| `ladder_200` | 200 | 90 Hz | 18,000 | ladder rung |
| `ladder_300` | 300 | 90 Hz | 27,000 | ladder rung |
| `ladder_400` | 400 | 90 Hz | 36,000 | ladder rung **and background alone** |
| `ladder_500` | 500 | 90 Hz | 45,000 | ladder top; encoder at midpoint |
| `drive_matched_500at30` | 500 | 30 Hz | **15,000** | 5× the KCs at the validated cue's drive |
| `anchor_100at150` | 100 | 150 Hz | **15,000** | same drive, 1× the KCs, same pool as `ladder_100` |

Seeds: **20260316, 20260317, 20260318, 20260319, 20260320, 20260321** — the same
six used by every other run in this series. Presentation: **1000 ms × 5 trials**,
the cell used throughout.

**7 conditions × 6 seeds = 42 simulations.**

## 3. What is recorded (fixed)

Per (condition, seed), the full per-neuron mean rate vector for each population,
from the same spike monitor the existing runners already use:

- **MBONs** (96 instances, with labels) — the readout population;
- **Kenyon cells** (5,177), split into stimulated and non-stimulated;
- **APL** (2), **PAM** (307), **PPL1** (16).

Derived per condition, over the six seeds: the scalar CIRCUIT-80 per-type-mean
score (mean, SD, and all six values); mean pairwise Euclidean distance between
the MBON vectors; active-MBON count (> 0.5 Hz); mean MBON rate; mean stimulated-KC
rate; **non-stimulated KC active fraction and mean rate**; APL mean rate; PAM and
PPL1 mean rates and active counts.

The non-stimulated KC active fraction is the same sparseness measure the
antennal-lobe failure was diagnosed with (65% of KCs active, Jaccard 0.99), which
is why it is recorded in the same form.

## 4. What each comparison can and cannot conclude

**4a. `ladder_400` (background alone) against the unbalanced diagnostic's five
stimuli.** *Can:* bound how much of that diagnostic's 70–137 Hz same-stimulus
noise is already present with the price pool silent. *Cannot:* attribute the
remainder to the price pool, because adding those 100 KCs also raises total drive
and shifts the network state; and cannot decompose variance, since the diagnostic
stimuli are not the background plus an independent term.

**4b. `drive_matched_500at30` against `anchor_100at150`.** Both deliver 15,000 Hz.
*Can:* say whether noise follows KC count or total drive at this one drive level —
the only comparison in the set that breaks that confound. *Cannot:* separate KC
count from active-MBON recruitment, which will move with it and is not
independently controllable; cannot generalise the answer to other drive levels;
and cannot rule out that 30 Hz per KC is simply below some threshold the model has.

**4c. The ladder (100 → 500 at 90 Hz).** *Can:* locate the count at which
active-MBON recruitment and score SD rise, at this per-KC rate. *Cannot:* separate
count from cumulative drive — along the ladder they rise together by construction
(4b is what breaks that at one point); cannot establish that the transition sits
at the same count for other rates; cannot claim the curve between rungs is
monotone or smooth, as only five points are measured; and cannot distinguish a
sharp threshold from a steep continuous rise at 100-KC resolution.

**4d. APL, PAM, PPL1 and KC rates.** *Can:* show whether APL is driven hard in the
wide-input regime, and whether KC activity spreads beyond the stimulated set —
the two signatures of the antennal-lobe failure. If APL stays quiet and
non-stimulated KCs stay silent, the two failures do **not** share that mechanism.
*Cannot:* establish causation in either direction. Seven conditions give seven
points, APL drive co-varies with everything else, and nothing here is an
intervention on APL.

**4e. `anchor_100at150` against the historical cue-A result** (100 KCs, 150 Hz,
`d_AA` = 5.10 Hz). *Can:* indicate whether a different 100-KC pool at the same
count and rate produces a comparable noise level. *Cannot:* be read as a
replication — it is a different KC set through a path whose pool-identity effect
on the *response* is known to be large (`d_AB` = 79.44 Hz between two disjoint
100-KC pools) and whose effect on *noise* is unmeasured, which is part of what
this condition is for.

## 5. Outputs and stopping rule

One JSON per (condition, seed) holding every population's rate vector, the
stimulated KC IDs, the per-pool rates, total drive, seed, duration and trial
count. Then one summary JSON with the per-condition statistics of Section 3, the
two paired comparisons of 4b and 4e, and the ladder table — and **no verdict
field**. Keep each file below 1 MB.

The runner is restartable and skips a completed (condition, seed). No summary is
produced unless all 42 result files exist. Do not add conditions or seeds after
inspecting results; any further analysis is exploratory and must be labelled as
such. Because this is a measurement, there is nothing here to loosen — but the
conditions and recorded statistics are fixed by this document so that the
measurement cannot be steered after the fact.

## 6. Cost

42 simulations at 1000 ms × 5 trials. At the 50.5 s per simulation measured
during the balanced run on the author's machine, plus one ~4 s network build,
that is **about 35.5 minutes** — UNVERIFIED on any other machine, and never used
by any criterion.

## 7. Exact command

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_population_scaling_diagnostic.py
```

Plan without simulating:

```bash
.venv-shiu/bin/python repro/mushroom_body/run_population_scaling_diagnostic.py --dry-run
```

Re-derive the summary from existing files, loading no connectome:

```bash
.venv-shiu/bin/python repro/mushroom_body/run_population_scaling_diagnostic.py --analyze-only
```
