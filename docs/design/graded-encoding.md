# Graded encoding test: does the readout follow the input rate?

**Status: pre-statement, written 2026-09-21 BEFORE any run.** The script exists
and its analysis is unit-tested on synthetic files, but **it has not been run and
no result exists.** The verdict rule below is fixed; if it ever needs to change,
write a new dated pre-statement rather than editing this one after seeing data.
Results, when they exist, go in a new section at the bottom, without touching
anything above it.

**Revision notice: the verdict rule in Section 4 was revised before the test was
run, twice.** First, from a two-outcome rule (accepted / not accepted) to the
three-outcome rule (ACCEPTED / USABLE RANGE / FAIL). Second, a sub-range gate was
added: a USABLE RANGE must also have its *own* endpoint distance clear the noise
threshold. No data existed under any version (no graded-rate result file had been
produced when either revision was made). The earlier wordings are preserved in
"Revision history" at the bottom, because they were never committed and git
cannot show them.

**Update, 2026-09-21: the test has since been run and the verdict was ACCEPTED**
(see "Results" at the bottom). The sentences above and below describe the state at
the time of the pre-statement; no criterion in this document was changed after the run.

Terms used here (Kenyon cell, MBON, firing rate, cell type, noise floor) are
explained in [`mb-learning-interface.md`](mb-learning-interface.md) and
[`mbon-separability.md`](mbon-separability.md).

---

## 1. The question, and why it has to be asked before any learning run

Our encoder ([`mb-learning-interface.md`](mb-learning-interface.md), 4a) turns a
market feature's *value* into a Kenyon-cell *firing rate*: a bigger value makes
that feature's pool of cells fire faster. That only works if the circuit's
output actually changes, in an orderly way, when the input rate changes.

**Every result we have so far used one rate: 150 Hz.** All the separability
findings compare *which* cells were driven, never *how hard*. Whether the output
neurons respond in a graded, monotonic way to *how hard* one pool is driven has
**never been tested** (marked unverified in the encoder's parameters). If it does
not, a price of 0.3 and a price of 0.7 could look the same to the readout, and no
learning rule could fix that.

## 2. Setup (fixed)

| Item | Value |
|---|---|
| Stimulated cells | one pool of 100 Kenyon cells: **set A**, `--kc-set-size 100 --kc-set-seed 20260316` (the same set A as the earlier cue experiments) |
| Stimulation rates | **30, 60, 90, 120 and 150 Hz**, one run per rate (the same rate for all 100 cells in a run) |
| Run length | **1000 ms**, **5 trials** per run |
| Simulation seed | **20260316**, the same for all five runs (the KC-set seed and the simulation seed are different things) |
| Code path | the **existing upstream path** (`check_mb_response.run_condition`, exactly as `run_single_cue.py` uses it), **not** `fast_runner` |

Why the existing path and not `fast_runner`: the noise floor we compare against
(`d_AA = 5.10 Hz`, below) was measured on the existing path. The fast path is
believed equivalent but its equivalence run
([`fast-runner.md`](fast-runner.md), section 4) **has not been done** (no
`fast_mbon_cue_*` result files exist), so comparing fast-path output to an
existing-path noise floor would mix two unverified things.

## 3. What is measured (fixed)

- **MBON vector.** The firing rate (Hz, mean over the 5 trials) of **all 96 output
  neurons** in the model (48 left, 48 right), in a fixed order. Neurons that did
  not fire are exactly 0, so a saved file that lists only the neurons that fired
  is filled in with zeros. This is the same vector the earlier noise-floor
  distances used (they took the union of active neurons and zero-filled, which
  is identical because everything outside the union is zero).
- **CIRCUIT score.** The readout of the design doc (4b): the `circuit_80` sign
  table (a neuron type is approach-like, +1, if dopamine neurons of the
  punishment family PPL1 supply at least 80% of its annotated dopamine input;
  avoidance-like, −1, if PAM supplies at least 80%; otherwise 0), aggregated by
  the **per-type mean** (`type_mean`): the rates of all instances of a cell type
  are averaged first, then each type gets one vote.
  - The mean is taken over **every instance of the type, in both hemispheres,
    including silent ones** (e.g. MBON10 has 9 instances: 4 left, 5 right). Right-
    hemisphere output neurons do respond in this model (in an existing set-A run
    a right-hemisphere MBON03 fired at ~80 Hz), so we do not restrict to the
    left. **This choice of instances is a decision made here, not one the design
    doc settled; it changes each type's mean by an instance-count-dependent
    factor.** Labels absent from the sign table (`MBON15-like`, `MBON17-like`,
    `MBON25,MBON34`, MBON20/22/24 and others) carry weight 0.
  - The sign table is **unverified at compartment level** (design docs).

## 4. Pre-stated verdict rule (fixed): three outcomes

Two things are computed from the five runs: the **CIRCUIT score at each rate**
(a sequence of five numbers) and the **endpoint distance**, the Euclidean distance
between the MBON vectors at 30 Hz and at 150 Hz. The noise floor is
`d_AA = 5.10 Hz` (mean Euclidean distance between repeated runs of the *same* cue
at different simulation seeds, 1000 ms / 5 trials;
[`mbon-separability.md`](mbon-separability.md)), so the endpoint threshold is
3 × 5.10 = **15.30 Hz**, inclusive (≥).

**Strictly monotonic** means all successive differences in a stretch of the
sequence are positive, or all are negative. Either direction counts (the learning
rule can adapt to either sign); an exact tie between neighbouring rates is a
violation. *(The word "monotonic" could be read as allowing plateaus; we chose
the strict reading because a plateau means two different values are
indistinguishable to the readout, which is exactly the failure this test exists to
catch.)*

The verdict is exactly one of:

- **ACCEPTED** — the CIRCUIT score is strictly monotonic across **all five** rates
  **and** the endpoint distance is ≥ 15.30 Hz.
- **USABLE RANGE** — the endpoint distance passes (≥ 15.30 Hz), but the score is
  not strictly monotonic across all five rates (the expected case: monotonicity
  breaks at the top or bottom of the range), **and** the **longest strictly
  monotonic contiguous sub-range spanning at least three rates** has its **own
  endpoint distance** — the Euclidean distance between the MBON vectors at that
  sub-range's first and last rates — of at least 15.30 Hz (the **sub-range
  gate**). Report that sub-range. **The encoder's rate bounds must then equal that
  sub-range before any learning experiment.**
- **FAIL** — the endpoint distance is below 15.30 Hz, **or** no strictly monotonic
  contiguous sub-range spans at least three rates, **or** the chosen sub-range's
  own endpoint distance is below 15.30 Hz (any combination).
  **Value encoding by rate fails, and the encoder must change before any learning
  experiment.** (Changing the encoder means a new design and a new pre-statement;
  it does not mean loosening this rule.)

| Endpoint distance (30 vs 150 Hz) ≥ 15.30 Hz | Monotonic over all five | A ≥3-rate monotonic sub-range exists | Chosen sub-range's own distance ≥ 15.30 Hz | Verdict |
|---|---|---|---|---|
| no | — | — | — | **FAIL** |
| yes | yes | (the whole range) | (same as the endpoint distance) | **ACCEPTED** |
| yes | no | yes | yes | **USABLE RANGE** |
| yes | no | yes | no | **FAIL** |
| yes | no | no | — | **FAIL** |

**Why the sub-range gate.** Without it, the 30-vs-150 Hz comparison alone could let
through a sub-range whose own change is inside the run-to-run noise: the endpoints
could differ a lot while the stretch we would actually use barely moves the readout
(for example, all the change happens where the response is *not* monotonic). A
sub-range that does not clear the same 3 × d_AA bar cannot carry a value any better
than a full range that does not, so it fails by the same standard.

**Why a third outcome.** Saturation at high rates is plausible neuron behaviour:
a neuron cannot fire faster than its maximum rate, and a pool driven harder may
stop responding in proportion. A readout that follows the input up to some rate
and then flattens or turns over indicates a *usable range*, not a failed encoding.
Restricting the encoder to the range where the readout still follows the input
keeps every encoded value on the part of the curve where different values can be
told apart. (The same reasoning plausibly applies at the low end, where a pool
driven below its firing threshold may not respond at all; that is our extension of
the argument and is likewise untested.)

**Details the rule left open, fixed here before any run:**

- **Order.** The endpoint-distance gate (30 vs 150 Hz) is applied first. A run that
  fails it is a FAIL whatever the scores do. The sub-range gate is applied after a
  sub-range has been chosen.
- **"Contiguous"** means adjacent among the five tested rates (30-60-90 counts;
  30-90-150 does not).
- **Direction.** Sub-ranges of either direction are considered, including a
  response that rises and then falls.
- **Where the break is.** "At the top or bottom" describes the expected case, not
  a restriction: any pattern that leaves a strictly monotonic run of at least
  three adjacent rates, including a break in the interior, is a USABLE RANGE.
- **Ties between equally long sub-ranges.** The rule does not say; we fix the
  **tie-break** here: choose the one with the larger absolute change in CIRCUIT
  score from its first to its last rate, and if those are exactly equal, the one
  starting at the lower rate. All tied sub-ranges are reported.
- **The first gate always uses the 30 Hz and 150 Hz vectors**, even when the
  selected sub-range excludes one of them; the sub-range gate is in addition to it,
  not instead of it.
- **The sub-range gate applies to the one chosen sub-range only.** "Chosen" means
  the longest, after the tie-break. There is **no fall-back**: if the chosen
  sub-range fails the gate the verdict is FAIL, even if a shorter sub-range, or a
  sub-range tied for longest that lost the tie-break, would have passed. (The
  tie-break looks at the change in CIRCUIT *score*, the gate at the change in the
  MBON *vector*, so these can disagree; we accept that rather than search among
  alternatives after seeing the data.)
- **What the encoder does with the verdict.** After the test runs, the encoder's
  `min_rate_hz` and `max_rate_hz` **must equal the validated range**: all five
  rates (30 and 150 Hz) for ACCEPTED, or the chosen sub-range's lowest and highest
  rate for USABLE RANGE. For FAIL there is no validated range and the encoder must
  change. `graded_check.encoder_params_for(result)` builds parameters with those
  bounds, and `graded_check.require_encoder_matches(params, result)` raises if they
  differ. Until the test has run, the encoder's placeholder bounds are 30-150 Hz
  (Section 6).

## 5. Reported but NOT part of the criterion (diagnostics)

- The MBON vector itself: the distance from the 30 Hz vector to each of the other
  four (does it move steadily away as the rate rises?), and how many of the
  neurons active at any rate never reverse direction across the five rates.
- The number of active MBONs at each rate, and the CIRCUIT score at each rate.
- The sub-range gate's distance is *not* a diagnostic: it is part of the verdict
  (Section 4) and is printed and saved whenever a sub-range exists, including when
  it is the cause of a FAIL.
- A reproducibility check: the 150 Hz run compared with the existing cue-A run at
  the same seed and path. A distance far above 5.10 Hz would point to a setup
  difference rather than to the encoding.

These are for interpretation only. They cannot change the verdict.

## 6. Limitations, stated in advance

- **One seed, no tolerance.** Each rate is run once at one seed, and the
  monotonicity check has no allowance for noise. A marginal reversal could be
  noise rather than a real failure; the criterion was fixed without a tolerance
  and we will not add one afterward. A re-test would need its own pre-statement
  (for example, several seeds).
- **No fall-back among sub-ranges.** A shorter or tied sub-range that would have
  cleared the sub-range gate is not considered once the chosen one fails (Section 4).
  This is deliberately literal and can turn a marginal USABLE RANGE into a FAIL.
- **The tested range is 30-150 Hz; nothing below 30 Hz has been tested.** Even an
  ACCEPTED verdict validates only 30-150 Hz, so the encoder must not emit a rate
  below the lowest tested one. The encoder's placeholder minimum rate was 0 Hz (a
  silent pool at a feature's minimum value); **as of 2026-09-21 it is 30 Hz**, so
  the placeholder bounds are 30-150 Hz, the range this test covers. A consequence:
  no feature pool is ever silent, even at its minimum value. After the test the
  bounds must equal the validated range (Section 4). The 30-150 Hz placeholders are
  themselves unverified until the test has run.
- **The noise floor is from 150 Hz.** `d_AA = 5.10 Hz` was measured driving the
  pool at 150 Hz. Noise at 30 Hz, where far fewer spikes occur, may be
  different (**unverified**), which is why the comparison is against the fixed
  measured number rather than against something re-estimated here.
- **One pool only.** The real encoder drives up to five feature pools at once at
  different rates. This test says nothing about how those interact.
- **Rate, not value.** Passing shows the readout follows the drive rate for one
  pool. It does not show that a *market price* is encoded usefully.
- **Runtime is an estimate** (unverified): about 30 s per run on the existing
  path, so a few minutes in total, plus start-up.

## 7. How to run it (you run it; nothing has been run)

The defaults **are** the pre-stated settings, so no arguments are needed. Each
run is a Brian2 simulation, so on macOS use `caffeinate -i`.

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/run_graded_rate.py
```

- **Restartable.** A rate whose result file already exists is skipped; a run that
  is interrupted leaves no half-written file (results are written to a temporary
  name and renamed). Re-run the same command to continue.
- **Analysis only** (no simulation; needs all five result files):
  `.venv-shiu/bin/python repro/mushroom_body/run_graded_rate.py --analyze-only`
- Overriding any setting (for instance a short smoke run) is allowed, but the
  printed verdict is then labelled **NOT THE PRE-STATED TEST** and must not be
  reported as the result.
- Outputs, in `repro/mushroom_body/results/`: one
  `graded_rate_cue_a_stim_hz_<rate>_..._seed_20260316.csv` per rate, plus
  `graded_rate_cue_a_..._summary.csv` and `..._verdict.json` (which records the
  verdict, the validated range for the encoder or `null` on FAIL, the chosen
  sub-range with its own endpoint distance, and the reasons for a FAIL). The
  verdict is printed to the terminal.

The verdict logic lives in `src/flyshi_research/learning/graded_check.py` (pure
numpy, unit-tested on synthetic data in `tests/learning/test_graded_check.py`,
including a test that this document states the same numbers as the code).

---

## Revision history (all before any run)

- **2026-09-21, first version.** Two outcomes. *ACCEPTED* if (a) the CIRCUIT score
  was strictly monotonic across the five rates **and** (b) the endpoint distance
  (30 vs 150 Hz) was at least 3 × 5.10 Hz = 15.30 Hz; *otherwise NOT ACCEPTED*. If
  the score was not monotonic, value encoding by rate fails and the encoder must
  change before any learning experiment; a monotonic score with an endpoint
  distance inside the noise was likewise not accepted. This version was never
  committed to git.
- **2026-09-21, first revision, before the test was run.** Replaced by the
  three-outcome rule in Section 4 (ACCEPTED / USABLE RANGE / FAIL), on the
  reasoning given there: saturation at high rates indicates a usable range, not a
  failed encoding. The two conditions of ACCEPTED are unchanged. What changed: a
  score that is monotonic over only part of the range (with the endpoint distance
  passing) is now a USABLE RANGE rather than a failure, with the encoder bounds
  restricted to that range; and FAIL is now defined by the endpoint distance or by
  the absence of any three-rate monotonic sub-range. Along with the rule, the
  tie-break and other details listed at the end of Section 4 were fixed. No result
  existed at either version.
- **2026-09-21, second revision, also before the test was run (this version).** The
  **sub-range gate was added before any run**: a USABLE RANGE must additionally have
  the chosen sub-range's *own* endpoint distance (MBON vectors at its first and last
  rates) at least 3 × d_AA = 15.30 Hz, and otherwise the verdict is FAIL. Reason: the
  30-vs-150 Hz gate alone let a sub-range through even when the stretch the encoder
  would actually use changed the readout by less than the noise. This *replaces* the
  earlier treatment of that number as a diagnostic that did not affect the verdict.
  Decided with it: the gate applies to the one chosen sub-range with no fall-back;
  and after the test the encoder's `min_rate_hz` and `max_rate_hz` must equal the
  validated range, with the encoder's placeholder minimum changed from 0 to 30 Hz in
  the meantime. Nothing else in the rule changed. No result existed.

---

## Results

### 2026-09-21: the pre-stated run

Run with the pre-stated settings (all defaults; the verdict file says
`prestated_test: true`): set A, seed 20260316, 1000 ms × 5 trials, existing upstream
path. Outputs in `repro/mushroom_body/results/` (`graded_rate_cue_a_*`, about 28 KB in
all) and the run log `repro/mushroom_body/run_log_graded.txt`.

**Verdict: ACCEPTED.**

| Stimulation rate | CIRCUIT score | Step from previous rate | MBONs active (of 96) | MBON-vector distance from 30 Hz |
|---:|---:|---:|---:|---:|
| 30 Hz | −9.6 | | 5 | 0.0 Hz |
| 60 Hz | −18.5 | −8.9 | 27 | 65.4 Hz |
| 90 Hz | −33.9 | −15.4 | 32 | 121.6 Hz |
| 120 Hz | −51.9 | −18.0 | 23 | 176.3 Hz |
| 150 Hz | −66.8 | −15.0 | 33 | 222.9 Hz |

- **Strictly monotonic across all five rates: yes, and decreasing** (all four steps
  negative).
- **Endpoint gate:** the 30-vs-150 Hz distance was 222.88 Hz against the 15.30 Hz
  threshold (about 14.6 times it). Because the score is monotonic over the whole
  range, the chosen sub-range is the whole range, so the sub-range gate is the same
  number.
- **Validated range: 30–150 Hz.** The encoder's bounds (`min_rate_hz` 30,
  `max_rate_hz` 150) equal it; `require_encoder_matches(EncoderParams(), result)`
  passes (checked 2026-09-21 on the real result files).
- **Diagnostics (not part of the verdict):** the vector distance from 30 Hz never
  decreases as the rate rises; 22 of the 38 MBONs active at any rate never reverse
  direction across the five rates. **The 150 Hz run reproduced the earlier set-A run
  (same seed, same path) to 0.00 Hz**, so the existing path is deterministic per
  seed.

### What the result shows, and the bias it reveals

The readout **follows the drive rate**, so encoding a value as a rate is viable
between 30 and 150 Hz. But the score *falls* as the drive rises, and this is a
property of the *readout*, not of any meaning in the input. Where it comes from,
computed from the same five files (analysis only):

| Rate | Sum of approach-like type means | Sum of avoidance-like type means |
|---:|---:|---:|
| 30 Hz | 1.9 Hz | 11.5 Hz |
| 60 Hz | 19.3 Hz | 37.8 Hz |
| 90 Hz | 46.9 Hz | 80.8 Hz |
| 120 Hz | 73.7 Hz | 125.6 Hz |
| 150 Hz | 101.2 Hz | 168.0 Hz |

Both kinds of type respond more as the drive rises, but the avoidance-like ones grow
faster. At 150 Hz the largest single contributors are MBON09 (63.7 Hz), MBON02
(43.5 Hz) and MBON03 (40.0 Hz); at 30 Hz only MBON09 (11.2), MBON14 (1.9) and MBON03
(0.3) respond among the weighted types.

**The bias, in one sentence:** under the primary CIRCUIT readout, stronger stimulation
pushes the score toward avoidance whatever the stimulus means. Under Option B
([`mb-learning-interface.md`](mb-learning-interface.md), 4b, problem 4), a market
priced at 0.8 drives the YES framing's price group at a high rate (126 Hz) and the
NO framing's at a low one (54 Hz), so the circuit innately prefers NO whenever YES is
the expensive side, before any learning. (Illustration only, unverified: straight
lines between the five points, price group alone: YES ≈ −55, NO ≈ −17.)

**Qualification found while checking, after seeing the primary result** (exploratory;
no criterion, and it does not change the verdict): the same files scored under the
other preregistered sign tables (type-mean aggregation unless noted):

| Sign table | Score at 30 / 60 / 90 / 120 / 150 Hz | Direction |
|---|---|---|
| CIRCUIT 80% (primary) | −9.6 / −18.5 / −33.9 / −51.9 / −66.8 | strictly decreasing |
| CIRCUIT 70% | same as 80% | strictly decreasing |
| CIRCUIT 90% | −9.6 / −17.9 / −33.4 / −50.1 / −57.9 | strictly decreasing |
| STRICT | 0.0 / 2.5 / 22.4 / 39.1 / 53.2 | strictly **increasing** |
| GROUP | 10.8 / 20.4 / 36.5 / 57.6 / 77.6 | strictly **increasing** |
| CIRCUIT 80%, sum over instances (`instance_sum`) | −37.8 / −58.8 / −98.8 / −153.2 / −202.6 | strictly decreasing |

So the **dependence on intensity is robust, but its direction is not**: under STRICT
and GROUP more drive means a more approach-like score, and Option B would lean toward
the *more expensive* side instead. MBON09, the largest contributor, is exactly the type
where CIRCUIT (avoidance-like) and the group-level label (approach) disagree.

**Two remedies are proposed in the design doc, not chosen:** (a) *total-drive
balancing*, so the YES and NO framings deliver equal total stimulation (costs: more
groups of cells, untested with several groups at once, and equal total drive is not
equal effect, which could leave a smaller, less visible lean); (b) *innate-score
subtraction* using pre-learning scores (costs: two more runs per market or a fitted
model of the innate score, more noise, and a learning-off control that would always
abstain; could hide an intensity-times-learning interaction). Details in the design
doc. **The first learning test (A vs B, both cues at a constant 150 Hz) is unaffected;
any market experiment must address this bias first.**

### Limitations that still apply

One seed and no tolerance (a score reversal could have been noise; none occurred);
`d_AA = 5.10 Hz` was measured at 150 Hz; one group of cells at a uniform rate, so the
interaction of several groups is untested; the sign table is unverified at compartment
level.

### Runtime correction

Section 6 estimated about 30 s per run. Observed: 530, 592, 571 and 621 s for the
30, 60, 90 and 120 Hz runs, and 89 s for the 150 Hz run. This machine's timings
depend heavily on background load ([`speed-calibration.md`](speed-calibration.md)),
so these are recorded as observed, not as a benchmark.
