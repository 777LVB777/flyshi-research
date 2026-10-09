# Synthetic-market extremes: containment diagnostic

**Status: PRE-STATED; NOT RUN.** Written 2026-10-09, before any simulation of this
protocol. **Revised 2026-10-09, still before any run,** for the `recent_change`
bound of ±1 (see the revision note in Section 3). The revision changes only the
stimuli table and the numbers in Section 1 that depend on it. The rule, the seeds,
the count and the measures are unchanged. The runner, `repro/mushroom_body/run_synthetic_extremes_containment_diagnostic.py`,
was written alongside this document and has only been dry-run. If anything here
needs to change, write a new dated pre-statement rather than editing this one.

**THIS IS A DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false`). It measures and does not judge. The output carries no
verdict, and none of PASS, FAIL, ACCEPTED or USABLE RANGE (enforced by the shared
`check_no_verdict`). Its result does not authorise or block anything. Whether to
run the sweep afterwards is the project owner's decision.

## 1. Question

The synthetic-market sweep ([`synthetic-market-experiment.md`](synthetic-market-experiment.md))
will present stimuli outside anything run so far with left-only pools:

- **Total drive.** Per-framing total drive in the sweep runs from 19.9 to
  70.1 kHz. Of the 5,000 presentations, 6.1% exceed 60 kHz, the highest drive
  ever presented left-only (realistic-drive diagnostic, contained 0/6). The
  lowest tested drive was 39.6 kHz.
- **Price.** 7.8% of prices fall outside 0.06–0.94, the price range the ACCEPTED
  validation covered (set B and its mirror image). That puts the price pool
  outside 37.2–142.8 Hz.

At the sweep's most extreme stimuli, **do the pools stay contained, or do they
ignite? And how strongly do non-stimulated KCs get recruited?**

## 2. Encoder (fixed)

The sweep's own encoder, built the same way as the sweep builds it:

- `KCEncoder(left_kc_ids())` with default `EncoderParams`: pool seed 20260401,
  pools of 100 KCs, 30–150 Hz. These are the ACCEPTED validation's pools.
- The guard `synthetic_market.assert_pools_left_only` is checked before the model
  is built.
- Option B `unbalanced`, mirrored NO framing. Every stimulus drives exactly the
  500 feature-pool KCs, with no balance pool. This is checked before the model is
  built.

## 3. Stimuli: a fixed rule over the sweep's own presentations

The candidate set is every presentation the decided sweep makes: 5 strengths ×
5 market seeds × 100 markets × 2 framings = 5,000. Learning changes weights, never
stimuli, so every arm presents exactly these. Six stimuli are chosen, in this
order:

1. the **three highest total drives**;
2. the **lowest price-pool rate**;
3. the **highest price-pool rate**;
4. the **lowest total drive**.

Two rules apply throughout:

- **Ties.** Ties break in sweep order (strength, then market seed, then index,
  then YES before NO).
- **One pick per market.** Each pick must come from a market not already
  chosen. A market's price, change, time to resolution and liquidity are the
  same at every strength, so two picks from one market would be near-duplicates.

Before the model is built, the runner checks:

- every highest-drive pick exceeds 60,000 Hz;
- both price picks lie outside 37.2–142.8 Hz;
- every stimulus is the unbalanced 500-KC stimulus;
- the rule reproduces **exactly** the table below.

> **REVISION 2026-10-09 (before any run): `recent_change` bound ±1.**
>
> *Why the table changed.* The project owner adopted Proposal A: the
> `recent_change` bound widens from ±0.2 to ±1, in both the generator's clip and
> `FeatureSpec` ([`synthetic-market-experiment.md`](synthetic-market-experiment.md),
> revision in Section 1). That changes the sweep's stimuli, so the frozen-table
> check aborted the runner, as designed.
>
> *What changed.* The **same fixed rule**, applied to the revised sweep, now
> selects the table below. The runner's `EXPECTED_SELECTION` was updated to it,
> and the dry run reproduces it exactly.
>
> *Section 1 numbers under the revised sweep:*
>
> - per-framing drive runs from 22.8 to 67.5 kHz;
> - **106 of 5,000 presentations (2.12%) exceed 60 kHz**, down from 6.1%;
> - 7.8% of prices still fall outside 0.06–0.94;
> - no presentation reaches the ±1 bound.
>
> | stimulus | sweep presentation (strength, seed, market, framing) | price | price pool Hz | total drive Hz |
> |---|---|---:|---:|---:|
> | `highest_drive_1` | 0.8, 20261004, 7, YES | 0.982 | 147.8 | 67,541 |
> | `highest_drive_2` | 0.8, 20261001, 17, YES | 0.990 | 148.8 | 67,030 |
> | `highest_drive_3` | 0.8, 20261005, 25, NO | 0.028 | 146.7 | 66,643 |
> | `lowest_price_rate` | 0.0, 20261001, 51, YES | 0.010 | 31.2 | 37,670 |
> | `highest_price_rate` | 0.0, 20261001, 98, YES | 0.990 | 148.8 | 58,022 |
> | `lowest_drive` | 0.0, 20261005, 61, NO | 0.941 | 37.0 | 22,759 |
>
> *What carries over.*
>
> - Two of the original markets are kept: `lowest_price_rate` (seed 20261001,
>   market 51) and `lowest_drive` (seed 20261005, market 61). Their drives change,
>   because the `recent_change` rate changes.
> - One market remains a high-drive pick, now at a different drive: seed
>   20261005, market 25.
> - **No stimulus now sits at a `recent_change` clip.**
>
> *Superseded.* The original table below is kept as the record. It no longer
> describes the sweep and must not be run.

The rule produced this table on 2026-10-09 (**SUPERSEDED** by the revision above):

| stimulus | sweep presentation (strength, seed, market, framing) | price | price pool Hz | total drive Hz |
|---|---|---:|---:|---:|
| `highest_drive_1` | 0.8, 20261005, 25, NO | 0.028 | 146.7 | 70,116 |
| `highest_drive_2` | 0.8, 20261001, 57, NO | 0.143 | 132.8 | 69,184 |
| `highest_drive_3` | 0.8, 20261004, 5, NO | 0.048 | 144.3 | 68,581 |
| `lowest_price_rate` | 0.0, 20261001, 51, YES | 0.010 | 31.2 | 34,031 |
| `highest_price_rate` | 0.0, 20261001, 17, YES | 0.990 | 148.8 | 67,018 |
| `lowest_drive` | 0.0, 20261005, 61, NO | 0.941 | 37.0 | 19,871 |

- **`recent_change` at its clip (original bound only).** Four of the six sit at the ±0.2 clip of
  `recent_change`, at 30 or 150 Hz.
- **If the sweep changes, so does this table.** That includes the open
  `recent_change` proposal in `synthetic-market-experiment.md`. The runner then
  **aborts** on the frozen-table check, and a new dated pre-statement is
  required. It does not silently choose new stimuli.
- **The lowest-drive pick.** It is included because 19.9 kHz is about half the
  lowest drive tested. It also prices at 0.941, just outside the validated
  interval.

## 4. Seeds, presentation, count

- **Seeds:** 20261101 and 20261102. Neither has been used by any earlier run or
  by the sweep, whose simulation seeds start at 20270000.
- **Presentation:** 1000 ms × 5 trials, as in the sweep.
- **Weights:** baseline (connectome) weights, the same weights the sweep's
  learning-off arm uses.
- **Count:** 6 stimuli × 2 seeds = **12 simulations**. At about 55 s each that is
  roughly 11 minutes plus one network build. This is a planning figure, not
  measured on the server.

## 5. Measured and reported (no criterion)

Each run saves trial-mean rates for MBONs, KCs, APL, PAM and PPL1, plus per-trial
KC, MBON and APL rates. The file layout and the 5 MB ceiling are the same as in
the realistic-drive diagnostic. The summary reports, per stimulus:

- **ignition label per seed:** the run is labelled ignited when the active
  fraction of non-stimulated KCs (active means above 0.5 Hz) exceeds 1%. This is
  a reporting label, as in the earlier diagnostics;
- **spread:** the active fraction of non-stimulated KCs, by side;
- **recruitment intensity:** the mean and median rate of recruited KCs, per seed
  and per trial ([`recruitment-intensity-measure.md`](recruitment-intensity-measure.md));
- measured against imposed rate for each pool, the APL rate per trial, active
  MBONs, PAM/PPL1 activity, and the CIRCUIT-80 per-type-mean score of the
  presented framing.

## 6. What this can and cannot conclude

- **Can:** whether these six stimuli stay contained at baseline weights, at two
  seeds, and how much they recruit.
- **Cannot:**
  - anything about learned weights. The training arms move weights; containment
    under learned weights is not tested;
  - anything about the rest of the 5,000 presentations;
  - the score's relation to price;
  - noise. Two seeds is too few for a noise floor, and none is computed.
- **Two seeds** can show that ignition happens. They cannot estimate how often it
  happens.

## 7. Command

```bash
# plan only (no simulation, writes nothing):
.venv-shiu/bin/python repro/mushroom_body/run_synthetic_extremes_containment_diagnostic.py --dry-run
# the pre-stated run (12 simulations), then the summary:
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/run_synthetic_extremes_containment_diagnostic.py
# summary from existing files only:
.venv-shiu/bin/python repro/mushroom_body/run_synthetic_extremes_containment_diagnostic.py --analyze-only
```

Outputs: `results/synthetic_extremes_<stimulus>_seed_<seed>.json` (12 files) and
`results/synthetic_extremes_containment_summary.json`. Stop once the summary is
written. Do not add stimuli or seeds after seeing results.

## Results

*None. Append results here after the run; do not edit the protocol above.*
