# Left-only pool diagnostic: is the containment difference hemisphere or identity?

**Status: PRE-STATED; NOT RUN.** Written 2026-09-23, before the runner and before
any simulation. Fixed here: the stimulus, the seeds, what is recorded, how a run
is classified, and what the comparison may and may not conclude.

**DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false` in the output). **No pass criterion**, no verdict
field: this is a measurement. PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL belong
to validations and must not be applied to anything here.

## 1. Question

The population-scaling diagnostic
([`population-scaling-diagnostic.md`](population-scaling-diagnostic.md)) found
that 100 KCs at 150 Hz — 15,000 Hz of total drive — ignites the network in 4 of 6
runs, while the historical cue-A result at the *same* count, rate and drive
stayed contained in 5 of 5 runs (`d_AA` = 5.10 Hz, 0.00% non-stimulated KC
spread).

The two stimuli differ in two ways at once:

| | historical cue A | `anchor_100at150` |
|---|---|---|
| drawn from | left-hemisphere KCs only (2,580) | all 5,177 KCs, both hemispheres |
| composition | 100 left / 0 right | 52 left / 48 right |
| overlap | — | 3 of 100 KCs shared |

So hemisphere composition is confounded with pool identity, and 15,000 Hz sits at
the stochastic ignition threshold where small differences plausibly decide the
outcome. This runs the encoder's own drawing procedure restricted to the left
hemisphere, which holds the procedure fixed and changes only the population it
draws from.

## 2. Stimulus and runs (fixed)

- Pool: `KCEncoder` given **left-hemisphere KCs only** (side `left` in
  `repro/mushroom_body/neuron_ids_783.json`), default `EncoderParams`, pool seed
  **20260401** — the encoder's usual seed. The pool used is **`recent_change`**,
  the first pool in the population-scaling ladder order, so it is the left-only
  counterpart of `ladder_100` / `anchor_100at150`.
- The runner asserts the pool is exactly 100 KCs, all annotated `left`, and
  aborts otherwise.
- Rate: **150 Hz** on every KC in the pool → 15,000 Hz total drive, matching
  `anchor_100at150` and the historical cue-A cell.
- Seeds: **20260316, 20260317, 20260318, 20260319, 20260320, 20260321**.
- Presentation: **1000 ms × 5 trials**.

**6 simulations.**

## 3. What is recorded and reported (fixed)

Per seed, the full per-neuron mean rate vector for **MBONs, Kenyon cells, APL,
PAM and PPL1**, exactly as the population-scaling runner records them, plus the
stimulated KC IDs and the pool's side composition.

Reported across the six seeds: the CIRCUIT-80 per-type-mean score (mean, SD, all
six values); mean pairwise MBON vector distance; active-MBON count; mean MBON
rate; stimulated-KC mean rate; **non-stimulated KC active fraction, overall and
split by hemisphere**; APL mean rate per seed; PAM and PPL1 mean rates and active
counts.

**Run classification for reporting only:** a run is called *ignited* when its
non-stimulated KC active fraction exceeds **1%**, and *contained* otherwise. This
threshold is a label for describing the bimodal outcome already observed (runs
land at either 0.0% or 65–68%); it is **not** a pass criterion, and no verdict is
derived from it.

## 4. What this can and cannot conclude

**Can:** show whether a left-only pool drawn by the encoder's own procedure, at
the same count, rate and total drive, ignites as often as the bilateral pool
(4/6). A markedly lower ignition count is evidence that hemisphere composition
matters; an equal count is evidence that it does not, and that the historical
cue-A result reflects its particular draw rather than its hemisphere.

**Cannot:**

- **Separate hemisphere from identity in one step.** This pool is left-only *and*
  a different draw from both earlier sets. A low ignition count would be
  consistent with either. Distinguishing them needs several independent left-only
  and bilateral pools at this drive, which this does not run.
- **Establish a threshold or a rate.** Six runs at one drive level estimate an
  ignition probability with an uncertainty of roughly ±0.2 at best; 4/6 versus
  2/6 is not a reliable difference.
- **Replicate the historical cue-A measurement.** That used a different pool, a
  different runner path and five seeds, and saved no KC, APL, PAM or PPL1 rates.
  It remains a second left-only reference point, not a control run here.
- **Say anything about multi-feature stimuli**, which drive more KCs than this.

## 5. Outputs and stopping rule

One JSON per seed with every population's rates and the stimulus description,
then one summary JSON with the statistics of Section 3 and, when the
population-scaling results are present, a side-by-side block against
`anchor_100at150`. **No verdict field.** Each file stays below 1 MB.

Restartable: a seed whose file exists is skipped. **No summary is produced unless
all 6 result files exist.** Do not add seeds after inspecting results; further
analysis is exploratory and must be labelled as such.

## 6. Cost

6 simulations at 1000 ms × 5 trials. At the 50.5 s per simulation measured on the
author's machine, plus one ~4 s build, **about 5.2 minutes** — UNVERIFIED
elsewhere, and used by nothing that is reported.

## 7. Exact command

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_left_only_pool_diagnostic.py
```

Plan without simulating, and re-derive the summary from existing files (neither
loads the connectome):

```bash
.venv-shiu/bin/python repro/mushroom_body/run_left_only_pool_diagnostic.py --dry-run
.venv-shiu/bin/python repro/mushroom_body/run_left_only_pool_diagnostic.py --analyze-only
```
