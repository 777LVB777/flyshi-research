# Low-drive ignition follow-up diagnostic

**Status: PRE-STATED; NOT RUN.** Written 2026-10-09, before any simulation of this
protocol. The runner, `repro/mushroom_body/run_low_drive_ignition_followup_diagnostic.py`,
was written alongside this document and has only been dry-run. If anything here
needs to change, add a dated revision note and keep the original text.

**Run 2026-10-09.** The protocol above ran unchanged (100 of 100 simulations).
Results are appended under [Results](#results); the protocol text is not edited.

**THIS IS A DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false`). It measures and does not judge. The output carries no
verdict, and none of PASS, FAIL, ACCEPTED or USABLE RANGE (enforced by the shared
`check_no_verdict`). The project owner decides after it whether to adopt the
drafted plasticity safeguard in
[`synthetic-market-experiment.md`](synthetic-market-experiment.md), Section 3.

## 1. Question

The extremes containment diagnostic
([`synthetic-extremes-containment-diagnostic.md`](synthetic-extremes-containment-diagnostic.md))
found an ignition at its lowest-drive stimulus (22,759 Hz): 1 of 2 runs, confined
to one trial of five. In that trial 65% of free KCs were recruited, on both sides,
at about 8 Hz. Across all saved left-only runs, ignition (trial-mean label) is:

| total drive | runs ignited |
|---|---:|
| 0–20 kHz | 0/18 |
| **20–30 kHz** | **2/8** (`ladder_300`, `lowest_drive`) |
| 30–40 kHz | 0/20 |
| 40–70 kHz | 0/134 |

Two in eight has a 95% interval of 3–65%. The questions are:

1. **How often** do the sweep's own lowest-drive stimuli ignite, per run and per
   trial?
2. **Is the 20–30 kHz window real?** That is, is ignition elevated there compared
   with neighbouring drive levels?

## 2. Encoder (fixed)

This is the decided sweep's encoder, as in the extremes diagnostic:

- `KCEncoder(left_kc_ids())`, default `EncoderParams` (pool seed 20260401,
  pools of 100 KCs, 30–150 Hz, `recent_change` range ±1), guarded by
  `synthetic_market.assert_pools_left_only`;
- Option B `unbalanced`, mirrored NO framing;
- every stimulus is the 500-KC feature-pool stimulus, with no balance pool.

## 3. Stimuli: a fixed rule over the sweep's 5,000 presentations

1. **Every presentation below 25 kHz** total drive, in ascending drive. There are
   6.
2. **Four 25–30 kHz presentations.** For each target of 26, 27, 28 and 29 kHz,
   take the 25–30 kHz presentation closest to it, from a market not already
   selected.

Ties break in sweep order. Before the model is built, the runner checks that the
rule reproduces exactly this table and that each stimulus is the unbalanced
500-KC stimulus. If either check fails, it aborts.

| stimulus | sweep presentation (strength, seed, market, framing) | price | total drive Hz |
|---|---|---:|---:|
| `below25_1` | 0.0, 20261005, 61, NO | 0.941 | 22,759 |
| `below25_2` | 0.1, 20261005, 61, NO | 0.941 | 22,838 |
| `below25_3` | 0.2, 20261005, 61, NO | 0.941 | 22,916 |
| `below25_4` | 0.4, 20261005, 61, NO | 0.941 | 23,073 |
| `below25_5` | 0.8, 20261005, 61, NO | 0.941 | 23,387 |
| `below25_6` | 0.8, 20261004, 23, YES | 0.165 | 24,691 |
| `band25_30_near26k` | 0.8, 20261004, 56, NO | 0.922 | 25,952 |
| `band25_30_near27k` | 0.1, 20261003, 61, NO | 0.664 | 27,024 |
| `band25_30_near28k` | 0.8, 20261004, 81, YES | 0.199 | 27,893 |
| `band25_30_near29k` | 0.1, 20261005, 14, NO | 0.648 | 28,978 |

**On record:**

- **Five of the six below-25 kHz presentations are one market.** Seed 20261005,
  market 61, NO framing, at the five signal strengths. They differ only in the
  signal pool (48.2–54.5 Hz).
- **This is the extremes diagnostic's `lowest_drive` market.** `below25_1` is that
  stimulus itself, run here at new seeds.
- **Why they are kept.** That is how often each arm of the sweep presents this
  market. It gives a well-sampled estimate for one market, but little generality.
- **Coverage.** The ten stimuli cover **six distinct markets**.

## 4. Seeds, presentation, count

- **Seeds:** 20261201–20261210. None was used before.
- **Presentation:** 1000 ms × 5 trials, at baseline weights.
- **Count:** 10 stimuli × 10 seeds = **100 simulations**, about 92 minutes in one
  serial process at about 55 s per simulation, plus one network build. This is a
  planning figure, not measured on the server.

## 5. Measured and reported (no criterion)

Each run saves trial-mean and per-trial rates (KC, MBON, APL; trial means also
for PAM and PPL1). Labels:

- a non-stimulated KC is **recruited** in a trial when it fires above 0.5 Hz;
- a **trial is ignited** when recruited KCs exceed 1% of non-stimulated KCs;
- a **run is ignited (any trial)** when any of its five trials is ignited;
- the **trial-mean label** (the 1% rule applied to the trial-mean rates) is the
  label every earlier diagnostic used. It is reported beside the others, for
  comparison.

Per stimulus, and pooled (all ten; the below-25 group; the 25–30 group), the
runner reports:

- ignited runs out of 10 (any trial, and trial-mean label) and ignited trials out
  of 50, each with an exact **Clopper–Pearson 95% interval**;
- spread per trial and seed;
- mean APL in ignited trials and in other trials;
- the realistic-drive diagnostic's full per-stimulus statistics (recruitment
  intensity, spread by side, active MBONs, APL, PAM/PPL1, CIRCUIT-80 score).

## 6. Window against neighbouring drive levels (descriptive)

The new runs are compared with **already-saved** left-only runs in three bands:

- **below:** 0–20 kHz (18 runs);
- **above:** 30–40 kHz (20 runs; 100 trials with per-trial data);
- **above:** 40–70 kHz (134 runs; 640 trials).

The bands are drawn from these result families:

- the left-only pool;
- the left-only ladder;
- realistic-drive;
- the left-only mirrored graded validation;
- the pool-identity control;
- the synthetic extremes.

Runs from those files inside 20–30 kHz (`ladder_300` and `lowest_drive`) are
listed as prior in-window runs. They are not pooled with the new runs.

For each band, the runner reports:

- the band's rate with its 95% interval;
- a **one-sided Fisher exact p** that the new runs' rate is higher, using
  trial-mean labels for runs and per-trial labels where both sides have them;
- a descriptive reading: **"elevated in the window"** if p < 0.05, otherwise
  **"not distinguishable"**.

That reading describes rates. It is not a pass criterion and authorises nothing.

**Known limits:**

- **Detectability.** With these band sizes, a difference can only be seen if the
  window rate is large enough. The new runs need at least **17/100** ignited to
  separate from the 0–20 kHz band, **16/100** from the 30–40 kHz band, and
  **4/100** from the 40–70 kHz band. A lower true window rate will read as "not
  distinguishable" from the smaller neighbouring bands.
- **The neighbouring runs are not matched controls.** They come from other
  constructions: uniform-rate ladders, single-feature graded stimuli, and sweep
  presentations. Drive is not the only thing that differs between bands.
- **No mechanism.** No spike times are saved, so the timing of an event within a
  trial is unknown. APL is reported, but the run cannot separate cause from
  response.

## 7. What this can and cannot conclude

- **Can:**
  - the ignition rate of these ten presentations at baseline weights, per run and
    per trial, with intervals;
  - whether that rate is distinguishable from the saved neighbouring bands, within
    the detectability limits above.
- **Cannot:**
  - the rate under learned weights;
  - the rate at the other 96 presentations below 30 kHz;
  - the mechanism;
  - whether the sweep's result depends on these events. That is what the sweep's
    own per-decision tracking and the pre-stated sensitivity analysis are for.

## 8. Command

```bash
# plan only (no simulation, writes nothing):
.venv-shiu/bin/python repro/mushroom_body/run_low_drive_ignition_followup_diagnostic.py --dry-run
# the pre-stated run (100 simulations), then the summary:
.venv-shiu/bin/python repro/mushroom_body/run_low_drive_ignition_followup_diagnostic.py
# summary from existing files only:
.venv-shiu/bin/python repro/mushroom_body/run_low_drive_ignition_followup_diagnostic.py --analyze-only
```

Outputs: `results/low_drive_followup_<stimulus>_seed_<seed>.json` (100 files) and
`results/low_drive_followup_summary.json`. Stop once the summary is written. Do not
add stimuli or seeds after seeing results.

## Results

*None. Append results here after the run; do not edit the protocol above.*

### Results, 2026-10-09 (`is_a_validation: false`, no verdict)

Source: `results/low_drive_followup_summary.json`, from the 100 run files
(`results/low_drive_followup_<stimulus>_seed_<seed>.json`). All ten stimuli at all
ten seeds ran; nothing was added or re-run after the results were seen.

**Pooled rates (exact Clopper–Pearson 95% intervals):**

| group | runs ignited (any trial) | trials ignited |
|---|---:|---:|
| all ten stimuli | **3/100** (0.006–0.085) | **3/500** (0.001–0.017) |
| below 25 kHz (6 stimuli) | 1/60 (0.000–0.089) | 1/300 (0.000–0.018) |
| 25–30 kHz (4 stimuli) | 2/40 (0.006–0.169) | 2/200 (0.001–0.036) |

The trial-mean label agrees with the any-trial label in every run (3/100).

**The three ignited runs.** Each is confined to a **single trial of five**, and
each is a different market:

| stimulus | presentation (strength, seed, market, framing) | drive Hz | sim seed | ignited trial | spread in that trial | APL, that trial | score (run) | score, other 9 seeds, mean ± SD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `below25_4` | 0.4, 20261005, 61, NO | 23,073 | 20261205 | 3 | 65.4% | 189.5 Hz | −61.8 | −46.3 ± 2.7 |
| `band25_30_near26k` | 0.8, 20261004, 56, NO | 25,952 | 20261201 | 3 | 66.5% | 250.0 Hz | −101.5 | −63.4 ± 1.9 |
| `band25_30_near28k` | 0.8, 20261004, 81, YES | 27,893 | 20261202 | 1 | 64.7% | 172.0 Hz | −88.5 | −83.4 ± 2.8 |

- Each event recruited about two-thirds of non-stimulated KCs on **both** sides,
  as in the extremes diagnostic's event (65%).
- APL in non-ignited trials was 144–158 Hz across stimuli.
- The ignited runs' CIRCUIT-80 scores sit 15.5, 38.1 and 5.1 Hz below the other
  nine seeds' mean for the same stimulus. The seven stimuli with no event have
  score SDs of 1.2–2.7 Hz.
- **The `lowest_drive` market itself (`below25_1`, the extremes diagnostic's
  stimulus) did not ignite in 10 runs.** The same market ignited once at strength
  0.4 (`below25_4`). The other four stimuli in that market: 0/40.

**Window against neighbouring drive levels (descriptive).** Readings follow the
pre-stated rule (one-sided Fisher p < 0.05 means "elevated in the window"):

| band | saved runs ignited | Fisher p, runs | Fisher p, trials | reading |
|---|---:|---:|---:|---|
| 0–20 kHz | 0/18 | 0.61 | n/a | not distinguishable |
| 30–40 kHz | 0/20 (trials 0/100) | 0.58 | 0.58 | not distinguishable |
| 40–70 kHz | 0/134 (trials 0/640) | 0.077 | 0.084 | not distinguishable |

**On record:**

- The new window rate, 3/100, is below every pre-stated detectability threshold
  (17/100, 16/100, 4/100). So "not distinguishable" is what a low true rate would
  produce. It does **not** show that the rate equals the neighbours' rate. Against
  the largest band (40–70 kHz, 0/134), p is 0.077.
- The earlier 2/8 in-window estimate (interval 3–65%) is not reproduced at that
  size. These ten presentations ignite in about 3% of runs (upper bound 8.5%).
- No mechanism is identified, as pre-stated: no spike times were saved.
- Scope: baseline weights only; ten presentations in six markets; five of them
  are one market.
