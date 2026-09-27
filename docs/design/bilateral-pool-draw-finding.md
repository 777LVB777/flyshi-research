# Finding: the bilateral KC pool draw, not the architecture, drove the graded-test ignition and noise

**Status: RECORDED FINDING, 2026-09-27.** Written after the left-only
population-scaling ladder
([`left-only-population-scaling-diagnostic.md`](left-only-population-scaling-diagnostic.md))
ran in full: 24 of 24 files, summary
`repro/mushroom_body/results/left_only_scaling_summary.json`, log
`repro/mushroom_body/run_log_left_only_ladder.txt`. Every number here comes from
saved result files. No simulation was run to write this document.

This is a finding drawn from diagnostics, **not a validation**. It changes no
pre-stated criterion, and it **does not alter or withdraw** any recorded verdict.
The two FAIL verdicts it concerns stand as recorded. This document explains what
they were measuring.

## 1. The bug

`KCEncoder` draws its pools from whatever KC IDs it is given. Its docstring
(`src/flyshi_research/learning/encoder.py:165`) says: *"pass LEFT-hemisphere
KCs; this class does not know or filter hemisphere"*. The unbalanced diagnostic's
own pre-statement (§2) says pools are "drawn from left-hemisphere KCs, as every
cue-direct experiment does".

Both graded runners instead passed **all 5,177 KCs** of both hemispheres:

- `repro/mushroom_body/run_graded_encoding_balanced.py:80`, `KCEncoder(sim.kc_ids)`
- `repro/mushroom_body/run_unbalanced_g_diagnostic.py:127`, `KCEncoder(sim.kc_ids)`

At pool seed 20260401 this gives feature pools split between the hemispheres,
recomputed here with the encoder alone (no simulation):

| pool | left | right |
|---|---:|---:|
| `price` | 51 | 49 |
| `recent_change` | 52 | 48 |
| `time_to_resolution` | 52 | 48 |
| `liquidity` | 54 | 46 |
| `signal` | 43 | 57 |

The balanced run's 300-KC balance pool was drawn from the same all-KC list. Its
side split was not recomputed here.

**The runners have not been changed.** The bug is identified, not fixed. Any
rerun through those two runners would repeat it.

## 2. The evidence

At matched KC count and a uniform 90 Hz per KC, with pools nested in the same
order:

| KCs | total drive | ignited (left-only / bilateral) | score SD, Hz (left-only / bilateral) | APL, Hz (left-only / bilateral) |
|---:|---:|---|---|---|
| 100 | 9,000 | 0/6 / 0/6 | 0.48 / 0.58 | 100.2 / 166.2 |
| 200 | 18,000 | 0/6 / **6/6** | 0.81 / **60.09** | 128.0 / 252.8 |
| 300 | 27,000 | 1/6 / **6/6** | 5.11 / **72.43** | 155.5 / 294.6 |
| 400 | 36,000 | not run / 6/6 | not run / 37.91 | not run / 312.3 |
| 500 | 45,000 | 0/6 / **6/6** | 1.23 / **82.48** | 177.5 / 298.4 |

Also relevant:

- **Single pool at 150 Hz** (15,000 Hz): left-only 0/6 ignited, score SD 1.12 Hz;
  bilateral 4/6, score SD 25.90 Hz
  ([`left-only-pool-diagnostic.md`](left-only-pool-diagnostic.md)).
- **Bilateral `ladder_400`** is exactly the unbalanced diagnostic's background: the
  same four pools at 90 Hz with `price` silent. It ignited 6/6, with 67.1% spread.

The graded tests failed on noise, in the same bilateral regime:

- **Unbalanced:** same-stimulus MBON noise was 70–137 Hz, and the per-value score
  SD was 37.8–63.0 Hz.
- **Balanced:** same-stimulus MBON noise was 24.9–183.5 Hz.

A left-only drive of up to 45,000 Hz gives score SDs of 0.5–5.1 Hz.

**What follows.**

- **Pool composition decides whether the network ignites.** In these diagnostics,
  ignition and the large run-to-run noise that comes with it depend on pool
  composition, not on the model or on drive level alone.
- **Left-only pools stay contained.** Drawn as the encoder was meant to draw them,
  they did not ignite at any tested count up to 500 KCs at 90 Hz. The one exception
  (§5) is a weak event.
- **Bilateral pools ignite.** At the same count and rate they ignited from 200 KCs
  upward.
- **The same connectome and model produced both outcomes.** So the ignition and
  noise that sank both graded tests are attributed to the bilateral draw, not to
  the architecture.

## 3. Scope: what this finding does not establish

Recorded so the finding is not quoted more strongly than the evidence allows:

1. **Ignition was not measured in the graded runs themselves.** Their result files
   store MBON rates only, not KC rates, so non-stimulated KC spread cannot be
   computed for them. That they ignited is an inference, supported by three things:
   - their noise matches the bilateral ladder's;
   - `ladder_400` ignites and is exactly the unbalanced background;
   - every bilateral rung from 200 KCs up ignited 6/6.
2. **The graded regime's drive was not tested left-only.**
   - The graded stimuli delivered 39,600–60,000 Hz across five pools at unequal
     rates (30–150 Hz), plus a 300-KC balance pool in the balanced run.
   - The left-only ladder tested only uniform 90 Hz, up to 45,000 Hz.
   - Whether left-only pools stay contained at encoder-realistic drive is **open**
     (the §6 proposal).
3. **Hemisphere and pool draw remain confounded.**
   - Each left-only rung is a different set of cells from its bilateral
     counterpart; they share only 3, 10, 20 and 50 KCs.
   - "Bilateral draw" here means *this* bilateral draw at pool seed 20260401.
   - Whether any bilateral pool ignites, or only this one, is not shown.
4. **It does not make either encoder viable.**
   - The balanced encoder's mirroring antisymmetry
     ([`balanced-encoding-failure.md`](balanced-encoding-failure.md) §2a) is exact
     and structural. It has nothing to do with hemispheres, and it would survive a
     left-only rerun.
   - Whether either encoder carries an above-noise value signal once pools are
     left-only is untested.

## 4. APL: headroom versus ceiling (correlational, not mechanism)

APL rates recorded next to the ladders:

- **Left-only**, rising steadily with count and not levelling off by 500 KCs:
  - 100.2 Hz at 100 KCs
  - 128.0 Hz at 200
  - 155.5 Hz at 300
  - 177.5 Hz at 500
- **Bilateral**, contained at 100 KCs and then flattening once runs ignite:
  - 166.2 Hz at 100 KCs (contained)
  - 252.8 Hz at 200
  - 294.6 Hz at 300
  - 312.3 Hz at 400
  - 298.4 Hz at 500

The pattern: left-only APL stays below every ignited bilateral level (≤ 179 Hz
against ≥ 253 Hz) and is still rising. Ignited bilateral APL levels off at about
295–312 Hz. A reading consistent with this is that left-only stimuli leave APL
inhibition headroom, while ignited bilateral stimuli drive APL to a ceiling and
the inhibition is overrun.

**This is correlation only.** APL's rate is an outcome of the same runs, so it
cannot separate these two readings:

- **Cause:** APL saturation lets ignition happen.
- **Consequence:** APL saturation is what an ignited network does to APL.

It also cannot say whether the hemispheric structure of APL input and output
matters. No manipulation of APL was made. Testing mechanism would need an
intervention, such as clamping APL or scaling APL→KC weights, pre-stated in its
own document.

## 5. The 300-KC anomaly (exploratory; not pre-stated)

The only left-only ignition in 24 runs was **seed 20260317 at 300 KCs**. The same
seed stayed contained at 200 and at 500, and 500 contains the 300 pool.

Per-seed values from the saved files (ratio = measured / imposed 90 Hz):

| rung | seed | spread (all) | left | right | APL Hz | active MBONs | score | stim-KC ratio |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 200 | 20260317 | 0.0% | 0.0% | 0.0% | 128.1 | 41 | −50.97 | 0.990 |
| **300** | **20260317** | **58.7%** | **63.4%** | **54.6%** | **160.6** | **70** | **−91.56** | **0.992** |
| 500 | 20260317 | 0.0% | 0.0% | 0.0% | 179.0 | 51 | −164.29 | 0.990 |
| 300 | other five seeds | 0.0% | 0.0% | 0.0% | 153.5–155.1 | 49–50 | −77.0 to −83.0 | 0.989–0.995 |

- **Stimulated KCs were driven normally.** The ratio is 0.992, inside the 0.989–0.995
  of the contained 300-KC seeds. The event is not a drive artefact.
- **The spread crossed hemispheres**: 63% of non-stimulated left KCs and 55% of
  right KCs reached 0.5 Hz.
- **APL barely moved.** It rose 6 Hz above the other 300-KC seeds, to 160.6 Hz,
  far below the ≥ 253 Hz seen in bilateral ignition.
- **It is a much weaker state than bilateral ignition.** An additional exploratory
  check on recruited-KC rates:

  | run | mean rate of recruited non-stimulated KCs | KCs below 2 Hz |
  |---|---:|---:|
  | this run | **1.17 Hz** (median 1.2 Hz) | 2,805 of 2,863 |
  | bilateral `ladder_300`, six seeds | 13.7–34.2 Hz | 30–59 per seed |

  Rates are 5-second means in 0.2 Hz steps, so 1.2 Hz is about six spikes per KC
  across all five trials. The 1% ignition label counts both states the same way,
  but by rate they are very different.

**Stochastic near threshold, or specific to the 300 draw?**

The data fit a stochastic event near threshold better than a property of the 300
pool alone:

- **It is not deterministic.** The pool is identical across all six seeds and only
  the noise realisation differs, so the 300 pool does not ignite on its own merits.
- **It is not seed-specific in a simple way.** Seed 20260317 does not ignite at
  200 or 500.
- **A tipping point fits the magnitudes.**
  - Active MBONs are 70, against 49–50 at the other seeds.
  - APL shows a small rise.
  - The recruited activity is weak and brief.

  This looks like a network that briefly tipped and was pulled back, not one that
  entered the bilateral ignited state.
- **Containment at 500 fits a rising APL.** APL rose to 175.6–179.0 Hz at 500, so
  more inhibition may offset more drive. This is correlation, per §4.

Something specific to the 300 draw is still **not excluded**. The third pool
(`liquidity`) may put the network nearer to a tipping point than the 500-KC
stimulus does, so that only 300 is close enough for noise to push it over. That
is still "stochastic near threshold", but the threshold would depend on pool
identity, not on count.

**What six seeds cannot determine:**

- **The ignition probability at 300.** One of six has a 95% interval of roughly
  0.4%–64%. That interval is consistent with near-zero rates at 200 and 500 as
  well, so the rungs cannot be ranked by ignition probability.
- **Whether 200 and 500 ever ignite.** Zero of six has a 95% upper bound of
  about 46%.
- **When the event happened within the run.** Only 5-trial, 1000 ms mean rates
  were saved. There are no per-trial or time-resolved rates, so it cannot be told
  whether the event happened in one trial or in all five, or how long it lasted.
- **Whether seed 20260317 matters.** It has not been checked that one seed gives
  the same noise realisation at different rungs; with a different stimulated set
  it very likely does not. So the same seed at 200, 300 and 500 should not be read
  as the same noise.
- **Whether the event would recur with another pool seed or nesting order.**

## 6. Next diagnostic (proposed, not written, not pre-stated)

**Left-only pools at encoder-realistic drive.** The ladder tested uniform 90 Hz
up to 45,000 Hz. The graded tests ran five pools at unequal rates, totalling
39,600–60,000 Hz. Proposal:

- **Encoder:** `KCEncoder` given left KCs only, default `EncoderParams`, pool seed
  20260401. These are the same pools as `left_ladder_500`.
- **Stimuli:** the encoder's own output for the five-feature YES-framed stimuli at
  the unbalanced value set (`v = 0.05, 0.22, 0.41, 0.63, 0.88`):
  - price pool 36.0–135.6 Hz;
  - the four background pools at 90 Hz;
  - totals 39,600–49,560 Hz.
- **Two further stimuli, reaching the 54,000–60,000 Hz regime:**
  - the balanced encoder's `v = 0.00` and `v = 0.25` YES stimuli, with the
    left-drawn 300-KC balance pool at 70 Hz and 50 Hz;
  - totals 60,000 Hz and 57,000 Hz.

  An alternative is two unbalanced stimuli with the four background pools raised
  to reach 54,000 and 60,000 Hz. That departs from encoder output, so the balanced
  stimuli are preferred.
- **Size:** 7 stimuli × 6 seeds (20260316–20260321), 1000 ms × 5 trials, so
  **42 simulations**.
  - Planning figure: about 35 minutes at 50.5 s per simulation, unverified.
  - The left-only 90 Hz ladder gave a 50.5 s estimate. Realistic drive could run
    slower if it ignites.
- **Records:** everything the left-only ladder records, including hemisphere-split
  spread, APL and stimulated-KC measured vs imposed rate.
  - **Add per-trial KC and MBON rates**, so a §5-style event can be placed in time.
    This needs a runner change; the current path saves 5-trial means only.
  - Add the same statistic the unbalanced diagnostic used, with its same-stimulus
    noise, so the result can be set beside the recorded FAIL.
  - **No verdict field**, as before.

**Would establish:**

- Whether left-only pools stay contained at the drive level and rate pattern the
  encoder actually produces.
- What the same-stimulus noise is there. That is the number that decides whether a
  graded re-validation with left-only pools is worth running.
- An **exploratory** look at whether the single-framing score varies with price
  above that noise.

**Would not establish:**

- **Encoder viability.** It is a diagnostic. Only a new pre-stated graded test can
  do that.
- **Anything about the balanced encoder's mirroring antisymmetry**, which is
  structural and hemisphere-independent.
- **The hemisphere versus pool-draw separation.** It uses one left draw. A second
  pool seed, or a right-only draw, would be needed.
- **Any mechanism for containment.** APL would again only be correlated.
- **Other pool seeds or other feature values.**

It should be pre-stated in its own dated document, with the stimuli fixed before
anything is run. The two graded runners should also be corrected, or left-only
variants written, before any graded re-validation, so the bug is not repeated.
