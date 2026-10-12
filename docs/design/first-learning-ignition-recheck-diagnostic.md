# First learning test: ignition re-check diagnostic

**Status: pre-statement, written 2026-10-12, before the code and before any run.**
This is a **DIAGNOSTIC** (`is_a_validation: false`, `has_pass_criterion: false`).
It produces **no verdict** and cannot change the first learning test's recorded
result (tag `layer3-learning-demonstrated`, results `first_learning_6fea97ac91`,
config hash `6fea97ac91`). The protocol is fixed below. If it must change, append
a dated revision before running, and never after seeing ignition figures.

Runner: `repro/mushroom_body/run_first_learning_ignition_recheck.py`. It uses
the first learning test's own backend
(`run_first_learning_test.FastRunnerSimulator`) and experiment code
(`flyshi_research.learning.first_learning`) unchanged, plus an opt-in per-trial
recorder.

## 1. Why

The synthetic-market sweep (2026-10-12 operational check;
[`synthetic-market-experiment.md`](synthetic-market-experiment.md), revision
2026-10-12) found **learning-induced KC cascades**:

- 66% of non-stimulated KCs recruited in a single trial;
- in 4.2% of `profit` trials, against 0.14% of `learning_off` trials.

The first learning test saved no KC rates for its test presentations, so it
could not be checked for the same thing. Its training records already show one
training cascade each in `b_reward_b` and `c_reward_both`: presentation k = 31,
cue B, with `n_eligible_kc` of 3,423 and 3,430 against 100 otherwise. After
those cascades, about 3,250 KC rows outside the cue sets changed weight.

Their post-test cue-B scores split by seed:

- seeds 20260317, 20260319 and 20260321 changed by about +181;
- seeds 20260318 and 20260320 changed by about +102.

Two questions:

1. Did any `main` post-test (or pre-test) trial cascade? If so, how much could
   that move Δ_main = +154.49?
2. Do test-time cascades explain the `b_reward_b` and `c_reward_both` seed split?

## 2. What runs

- **The exact first learning test protocol, unchanged:**
  - `ExperimentConfig()` defaults, which must hash to **`6fea97ac91`** (the
    runner aborts otherwise);
  - all five conditions (`main`, `a_plasticity_off`, `b_reward_b`,
    `c_reward_both`, `d_punish_a`);
  - the original seeds: test 20260317–20260321, training 20260500–20260539,
    order seed 20260402, KC-set seed 20260316;
  - 1000 ms × 5 trials per test presentation, 1000 ms × 1 trial per training
    presentation.
- **Runs:** 10 pre-test + 5 × (40 training + 10 post-test) = **260 runs**, the
  same as the original, sequential in one process.
- **Where it writes:** a **new** results base,
  `repro/mushroom_body/results/first_learning_ignition_recheck_20261012/`. The
  experiment code writes into its `first_learning_6fea97ac91/` subfolder.
  - The runner refuses to start if that base is the default results folder.
  - The runner never opens the original folder for writing.
  - `verdict.json` is **never** written: the runner calls `assemble` (merging job
    files) but not `finish`.

## 3. What is recorded (does not affect scores)

**Mechanism.** `FastRunnerSimulator.present` gets an optional `trial_sink`, which
is `None` by default. When set, it receives per-trial spike counts computed from
the **same** spike table. The returned trial-mean KC and MBON rates are computed
by the **unchanged** original lines. So scores, eligibility, learning and every
saved original field are unaffected. The original runner's behaviour is
identical when no sink is set, and a test checks this on a fake.

**Per presentation** (pre-test, training and post-test), saved as one compressed
`.npz`:

- per-trial spike counts of every KC, MBON and APL neuron;
- the seed, the cue and the job ID.

KC rate per trial = count / 1 s, the sweep's definition.

**Ignition.** Labelled with the sweep's own `synthetic_market.ignition_record`,
using `SyntheticConfig()` defaults:

- a non-stimulated KC is recruited in a trial if its rate is **above 0.5 Hz**;
- a trial is **ignited** if recruited KCs **exceed 1%** of non-stimulated KCs;
- "non-stimulated" means not in the presented cue's 100-KC set.

Also recorded: spread (overall, left, right), recruited count, recruited mean
rate, mean APL rate, and the **per-trial CIRCUIT-80 type-mean score** (the
primary readout applied to that trial's MBON rates).

## 4. Validity check (pre-stated; it gates any interpretation)

Before any ignition figure is computed or printed, the analysis compares the
re-run with the saved original:

- **Required, exact (float equality):** every pre-test and post-test `score_A`
  and `score_B`, all 5 seeds × 5 conditions plus the pre-test.
- **Also required, exact:** every saved `mbon_A` and `mbon_B` value (both are
  rounded to 4 dp in both files). From each `training_curve` entry: `cue`,
  `score`, `teaching` and `n_eligible_kc`. Every `weight_summary` field.

**If any value differs: STOP.** The summary records `valid: false` and lists
every mismatch. No ignition figure is computed, printed or interpreted. The
owner decides what follows.

## 5. What is reported (only if valid)

Per condition × seed × cue, for pre-test and post-test:

- ignited trials out of 5;
- for each ignited trial: spread (overall, left, right), recruited count and
  recruited mean rate;
- per-trial scores of ignited and of non-ignited trials;
- the presentation score.

Also reported: training cascades per condition (presentation k, cue, spread),
using the sweep definition.

**Linearity check.** The presentation score is the score of the trial-mean MBON
rates. With the type-mean readout it should equal the mean of the per-trial
scores. The largest absolute difference is reported. The adjusted figures below
are computed only if it is below 1e-6 Hz. Otherwise they are reported as "not
computable".

## 6. Pre-stated readings (descriptive; no verdict)

**Adjusted presentation score.** The mean per-trial score of a presentation's
**non-ignited** trials. It is undefined if all 5 trials ignited.

**(1) `main`, and the +154.49.**

- **No ignited trial** in any `main` post-test presentation or any pre-test
  presentation: *"no test-time cascade in `main`; cascades contribute nothing to
  Δ_main"*.
- **Otherwise:** recompute Δ_main from adjusted scores in every presentation that
  had an ignited trial, using the pre-test's m_pre with the same adjustment.
  Report Δ_main(adjusted) and the shift Δ_main − Δ_main(adjusted).
  - Also report the threshold recomputed from the adjusted pre-test (3 ×
    sample SD of A − B), next to the original 6.545.
  - Reading: *"cascades move Δ_main by X"*. If Δ_main(adjusted) is still at
    least the original threshold, add: *"the main result does not depend on
    them"*.
  - If any affected presentation had all 5 trials ignited: *"not computable for
    seed S; at most bounded by …"*. The bound replaces that presentation's
    score with the range of the other seeds' scores for the same cue.

**(2) The `b_reward_b` and `c_reward_both` seed split.** For each condition, the
**gap** is the mean cue-B score change (post-test minus pre-test) of seeds
20260317, 20260319 and 20260321, minus that of seeds 20260318 and 20260320. In
the original it is about 79 in `b_reward_b`.

- *"Test-time cascades explain the split"* requires both:
  - (i) the cue-B post-test of seeds 20260318 and 20260320 together has more
    ignited trials than that of the other three seeds;
  - (ii) recomputing the gap from adjusted scores reduces its absolute size by
    **at least 75%**.
- *"Partly explain"*: (i) holds and the reduction is 25–75%.
- *"Do not explain"*: (i) fails, or the reduction is under 25%.
- **Every-trial confound.** If seeds 20260318 and 20260320 have cue-B cascades
  in all 5 trials while the other three have none, adjustment is impossible. The
  reading is then *"the split coincides exactly with test-time cascades;
  consistent with, but not proof of, a cascade explanation"*.
- **Reversed pattern.** If cascades occur instead in seeds 20260317, 20260319 and
  20260321, the reading is *"do not explain as hypothesised"*. The pattern is
  reported as observed.

**Not inferred.** No mechanism is inferred. Spike timing within a trial is not
analysed. Nothing here changes the first learning test's verdict, which was
decided under its own pre-stated rules.

## 7. Cost and running

- **Local, $0.** The original took 78 min, sequential in one process, on this
  machine (file times 2026-09-28 00:32–01:51). That is about 46 s per 5-trial test
  run and about 9.5 s per training presentation.
- **Estimate:** 80–90 min, including one network build. Recording adds a
  bincount and one small file write per presentation. **Not measured.**
- **Memory:** one process. The original ran on this 8 GB Mac.
- **The server sweep is not touched.** Nothing is uploaded, and no server
  command is involved.

Commands are in the runner's docstring and `--help`. The run is
`--run`, and the analysis, which needs no Brian2, is `--analyze`.

## Results

*None yet. Append a dated section after the run; do not edit anything above.*
