# Left-only population-scaling diagnostic: where does a left-only ladder ignite?

**Status: PRE-STATED; NOT RUN.** Written 2026-09-23, before the runner and before
any simulation. Fixed here: the conditions, the pools, the seeds, what is
recorded, how a run is labelled, and what the comparison may and may not conclude.

**DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false` in the output). **No pass criterion**, no verdict
field: this is a measurement. PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL belong
to validations and must not be applied to anything here.

## 1. Question

The bilateral population-scaling ladder
([`population-scaling-diagnostic.md`](population-scaling-diagnostic.md)) at 90 Hz
per KC was contained at 100 KCs (0/6 runs ignited, 0.0% non-stimulated KC
spread) and ignited at every rung from 200 KCs up (6/6 each, 65–68% spread).
The left-only pool diagnostic
([`left-only-pool-diagnostic.md`](left-only-pool-diagnostic.md)) then found that
a left-only 100-KC pool at 150 Hz stayed contained in 0/6 runs, where the bilateral
pool at the same count, rate and drive ignited in 4/6.

That is one point. This runs the same ladder with left-hemisphere-only pools, to
find where (if anywhere up to 500 KCs) a left-only stimulus ignites at 90 Hz, and
to set that beside the bilateral ladder at matched count and rate.

## 2. Stimulus and runs (fixed)

- Pools: `KCEncoder` given **left-hemisphere KCs only** (side `left` in
  `repro/mushroom_body/neuron_ids_783.json`, 2,580 KCs), default `EncoderParams`,
  pool seed **20260401**, exactly as in the left-only pool diagnostic.
- **Nested**, in the bilateral ladder's pool order: `recent_change`,
  `time_to_resolution`, `liquidity`, `signal`, `price`. Each rung is the previous
  rung plus the next pool(s), so the count changes and the KCs already driven do
  not. The runner asserts, and aborts otherwise, that each rung is exactly its
  count, every KC is annotated `left`, and each rung contains the one below it.
- Rate: **90 Hz** on every driven KC, matching the bilateral ladder.

| condition | pools | KCs | per-KC rate | total drive | bilateral counterpart |
|---|---:|---:|---:|---:|---|
| `left_ladder_100` | 1 | 100 | 90 Hz | 9,000 | `ladder_100` (0/6 ignited) |
| `left_ladder_200` | 2 | 200 | 90 Hz | 18,000 | `ladder_200` (6/6) |
| `left_ladder_300` | 3 | 300 | 90 Hz | 27,000 | `ladder_300` (6/6) |
| `left_ladder_500` | 5 | 500 | 90 Hz | 45,000 | `ladder_500` (6/6) |

There is no 400-KC rung. The 500 rung still uses all five pools, so the nesting
is unbroken. The runs skip 400; the pools do not.

- Seeds: **20260316, 20260317, 20260318, 20260319, 20260320, 20260321**.
- Presentation: **1000 ms × 5 trials**.

**4 conditions × 6 seeds = 24 simulations.**

**Why the 100-KC rung is rerun rather than reused.** The left-only pool
diagnostic's six files contain *the same 100 KCs* as `left_ladder_100` (the
left-drawn `recent_change` pool, seed 20260401; checked by test). But they were
driven at **150 Hz**, not 90 Hz. The stimulus is therefore not identical, and
the condition for reuse is not met. Those files are left untouched and play no
part here.

## 3. What is recorded and reported (fixed)

Per (condition, seed), the full per-neuron mean rate vector for **MBONs, Kenyon
cells, APL, PAM and PPL1**, recorded the same way as in the population-scaling
runner, plus the stimulated KC IDs, the pools and the rung's side composition.

Reported per condition, in the same form as the bilateral ladder so the two can
be read side by side:

- **ignition count out of 6** and the per-seed ignited/contained label;
- **per-seed non-stimulated KC active fraction, overall and split by
  hemisphere** (left / right);
- **active MBONs** (> 0.5 Hz), per seed and mean;
- **APL rate**, per seed and mean;
- **CIRCUIT-80 per-type-mean score**: mean, SD, and all six values;
- **stimulated-KC rate, measured against imposed**: the imposed 90 Hz, the
  measured mean per seed and across seeds, and the ratio;
- also, as in the earlier runners: mean pairwise MBON vector distance, mean MBON
  rate, non-stimulated KC mean rate, PAM and PPL1 mean rates and active counts.

**`bilateral_reference`**: the same statistics, computed by the same code with
the same hemisphere split, from the committed `population_scaling_ladder_{100,
200,300,500}` result files, plus each bilateral rung's side composition and its
overlap with the matching left-only rung. The comparison sits inside the summary
file. **No summary is written unless those 24 bilateral files are present.**

**Run labelling, for reporting only:** a run is *ignited* when its
non-stimulated KC active fraction exceeds **1%**, and *contained* otherwise. This
is the same label as in the left-only pool diagnostic. It describes the bimodal
outcome seen so far (0.0% or 65–68%). It is **not** a pass criterion, and no
verdict is derived from it.

## 4. What this can and cannot conclude

**Can:**

- **Locate the left-only ignition threshold on this ladder at 90 Hz**, to the
  resolution of the rungs: the lowest rung with ignited runs, or "not reached by
  500 KCs".
- **Compare it with the bilateral ladder at matched count and rate.** Bilateral
  ignites 6/6 from 200 KCs. If the left-only ladder is contained at 200 or above,
  a left-only nested stimulus needs more KCs to ignite than this bilateral one.
  If it ignites from 200 as well, the two thresholds lie in the same 100–200
  interval.
- Show whether, when a left-only stimulus does ignite, the spread stays in the
  left hemisphere or reaches the right, which the per-hemisphere split records.

**Cannot:**

- **Separate hemisphere from pool draw.** Each left-only rung is a different set
  of cells from its bilateral counterpart. They share only 3, 10, 20 and 50 KCs at
  100, 200, 300 and 500. Any difference in threshold is consistent with
  hemisphere composition *or* with which cells were drawn. The two stay
  confounded however many rungs are run, because both sides use one draw each.
- **Test a five-pool stimulus.** This runs a single nested pool sequence from
  one pool seed, with every driven KC at one uniform rate. The 500 rung covers
  the KCs of all five pools, but it is not an encoded five-feature stimulus: there
  are no per-feature rates and no balancing pool. It is also not an independent
  redraw. Nothing here speaks to other nestings, other pool seeds or encoder
  output.
- **Resolve the threshold below 100 KCs, or at 400.** Between rungs nothing is
  measured. A threshold between 300 and 500 cannot be told apart from one at 400
  or 500.
- **Generalise across rates.** Everything is at 90 Hz. The 150 Hz left-only point
  is a different stimulus and is not a rung of this ladder.
- **Estimate an ignition probability precisely.** Six runs per rung give a count,
  with roughly ±0.2 uncertainty on any probability read from it.

## 5. Outputs and stopping rule

One JSON per (condition, seed) holding every population's rates and the stimulus
description (`left_only_scaling_<condition>_seed_<seed>.json`). Then one summary
JSON, `left_only_scaling_summary.json`, with the per-condition statistics of
Section 3, a side-by-side ladder table, and the `bilateral_reference` block.
**No verdict field.** Each file stays below 1 MB.

Restartable: a (condition, seed) whose file exists is skipped. **No summary is
produced unless all 24 left-only files and all 24 bilateral reference files
exist.** Do not add rungs or seeds after inspecting results. Any further analysis
is exploratory and must be labelled as such.

## 6. Cost

24 simulations at 1000 ms × 5 trials. At the 50.5 s per simulation measured on
the author's machine, plus one ~4 s build, this is **about 20.3 minutes**. The
figure is UNVERIFIED on other machines and nothing reported depends on it.

## 7. Exact command

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_left_only_population_scaling_diagnostic.py
```

To plan without simulating, or to re-derive the summary from existing files
(neither loads the connectome):

```bash
.venv-shiu/bin/python repro/mushroom_body/run_left_only_population_scaling_diagnostic.py --dry-run
.venv-shiu/bin/python repro/mushroom_body/run_left_only_population_scaling_diagnostic.py --analyze-only
```
