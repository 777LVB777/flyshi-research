# Balanced graded-encoding re-validation

**Status: PRE-STATED; NOT RUN.** Written before any balanced graded-encoding
simulation or result was inspected. The earlier result in
[`graded-encoding.md`](graded-encoding.md) used unbalanced stimuli and is
**SUPERSEDED** for the current encoder. It remains a historical result, not
evidence that the balanced encoder is valid.

## 1. Question

Does the Option B MBON contrast vary monotonically and by more than its directly
measured run-to-run noise when a directional market feature changes, while total
YES and NO KC drive is held equal?

This test varies **feature value**, not a freely selected uniform KC rate. Total
drive balancing makes a stimulus a multi-pool rate pattern.

## 2. Fixed encoder and sweep

Use the default encoder and its fixed seeded, disjoint pools:

- feature-pool size: 100 KCs;
- feature-pool seed: 20260401;
- balancing-pool size: 300 KCs;
- feature rate bounds: 30–150 Hz;
- Option B variant: `total_drive_balanced`.

Sweep the normalized `price` feature through

```text
v = 0.00, 0.25, 0.50, 0.75, 1.00.
```

Hold every other feature at the midpoint of its declared range:
`recent_change = 0`, `time_to_resolution = 182.5`, `liquidity = 0.5`, and
`signal = 0.5`. The optional signal is present, so the active feature-pool set is
identical at all five points.

At each value, generate the default balanced Option B pair. Before balancing,
the YES price pool's linear encoding is

```text
r_nominal(v) = 30 Hz + v (150 Hz - 30 Hz),
```

giving labels 30, 60, 90, 120, and 150 Hz. The NO price pool receives the
mirrored value `1-v`, so its nominal rates run in reverse. In this document,
**“input rate” means only this nominal, pre-balance YES price-pool rate**. It is
an axis label for the feature-value sweep. It does not mean that every KC is
stimulated at that rate, and it is not an independently adjustable rate after
balancing. The actual input is the complete per-KC balanced pattern, which must
be saved with the result.

For each pair, verify before simulation that

```text
sum_i r_yes,i = sum_i r_no,i
```

to floating-point precision. A failed invariant check aborts the test and
produces no verdict.

## 3. Simulation and readout

- Model and connectome: the unchanged Shiu et al. model, v783.
- Path: the accepted reusable per-neuron-rate runner.
- Duration: 1000 ms per trial.
- Trials: 5 per stimulus.
- Primary-test seed: 20260316 for every YES and NO presentation. Reusing the seed
  is a common-random-number design choice; its effect on paired contrast noise
  is measured by the dedicated repeats in Section 4.
- Primary-test runs: five feature values × two framings = **10 simulations**.
- Primary readout: CIRCUIT 80%, per-type mean.

Let `m_yes(v)` and `m_no(v)` be the vectors of mean firing rates over all MBON
instances, with silent MBONs included as zero. Define the Option B contrast
vector and score as

```text
c(v) = m_yes(v) - m_no(v)
S(v) = CIRCUIT(m_yes(v)) - CIRCUIT(m_no(v)) = CIRCUIT(c(v)).
```

The last equality holds because the fixed CIRCUIT readout is linear. The five
`S(v)` values are the sequence used for monotonicity. Euclidean gates use the
corresponding contrast vectors `c(v)`.

## 4. Dedicated change-in-contrast noise floor and fixed gate

The old `d_AA = 5.10 Hz` is **not used as the balanced verdict threshold**. It
is the mean distance between two independent realizations of one unbalanced
single-cue vector. That already contains noise from two runs. Under the special
assumptions that every stimulus has identical noise covariance and all relevant
runs are independent, one YES-minus-NO contrast would have the same covariance
as a same-cue run difference, while the difference between two contrasts would
have twice that covariance. On those assumptions only, its norm scale would be
approximately `sqrt(2) × d_AA`, and a threefold gate would be approximately
`3 × sqrt(2) × 5.10 = 21.64 Hz`.

That analytic value is **not adopted**. YES and NO use the same simulation seed,
the endpoint values use different KC rate patterns, and network noise may depend
on which KCs and rates are stimulated. Those facts introduce unknown covariance
and heteroscedasticity, so neither 15.30 Hz nor 21.64 Hz is a verified threshold
for the statistic used here.

Before a verdict, repeat the complete five-value, two-framing balanced protocol
at five seeds distinct from the primary-test seed:

```text
20260317, 20260318, 20260319, 20260320, 20260321.
```

Use the same seed for YES and NO and across all five values within a repeat,
matching the common-random-number structure of the primary test. This is
`5 seeds × 5 values × 2 framings = 50` dedicated noise-floor simulations. These
runs are used only to estimate noise; the primary score sequence and endpoint
vectors still come only from seed 20260316.

For repeat seed `k`, define

```text
c_k(v) = m_yes,k(v) - m_no,k(v)
Delta_k(a,b) = c_k(b) - c_k(a).
```

For every endpoint pair `(a,b)` needed by the verdict, define its directly
measured change-in-contrast noise floor as

```text
d_change(a,b) = mean over i<j of ||Delta_i(a,b) - Delta_j(a,b)||.
```

The deterministic value effect cancels in the pairwise differences, while the
calculation retains the actual YES/NO, cross-value, and shared-seed covariance.
This deliberately follows the earlier `d_AA` convention: mean pairwise distance
between independent repeat estimates of the same statistic. The fixed gate for
pair `(a,b)` is

```text
T(a,b) = 3 × d_change(a,b).
```

Thus there is no numeric balanced threshold before the repeat data exist; the
formula, seeds, statistic, and factor of three are fixed before any run. Inspecting
the repeat vectors must not be used to revise the sweep, gate, or verdict rule.

“Strictly monotonic” means that every successive score difference is greater
than zero, or every successive score difference is less than zero. An exact tie
breaks monotonicity.

## 5. Pre-stated three-outcome verdict

The gate order and sub-range logic are exactly the same as in the original
graded-encoding specification, with the five feature values (and their nominal
rate labels) replacing five freely imposed uniform rates.

- **ACCEPTED** — `S(v)` is strictly monotonic across **all five** values, and the
  Euclidean distance `||c(0.00)-c(1.00)||` is at least
  `T(0.00,1.00) = 3 × d_change(0.00,1.00)`.

- **USABLE RANGE** — the full endpoint distance passes, but `S(v)` is not
  strictly monotonic across all five values, and the longest strictly monotonic
  **contiguous** sub-range spanning at least three tested values has its own
  endpoint contrast-vector distance at least its pair-specific threshold
  `T(a,b) = 3 × d_change(a,b)`.

- **FAIL** — the full endpoint distance is below `T(0.00,1.00)`, or no strictly
  monotonic contiguous sub-range spans at least three tested values, or the
  chosen sub-range's own endpoint distance is below its pair-specific `T(a,b)`.
  The balanced value encoding must change before any learning experiment.

For tied longest sub-ranges, choose the one with the larger absolute endpoint
score change, then the lower starting feature value. The full `v=0` versus
`v=1` endpoint gate is applied first. The sub-range gate is applied to the one
chosen longest range; there is no fallback to a shorter or tied alternative.

For **USABLE RANGE**, report both the normalized feature-value interval and its
nominal pre-balance rate labels. This result does not by itself authorize a
silent change to `min_rate_hz`/`max_rate_hz`: a restricted balanced value mapping
must be specified before learning. For **FAIL**, no range is validated.

## 6. Outputs and stopping rule

Save each pair's feature value, nominal rate, exact per-pool rates, total drive,
all-MBON YES and NO vectors, seed, duration, and trial count. Save all pairwise
`d_change(a,b)` values, the thresholds actually used, the five primary contrast
scores, endpoint distances, selected sub-range (if any), and verdict.
Keep outputs below 1 MB per file.

The runner is restartable and skips a completed value/seed file. Run the 50
noise-floor simulations before the 10 primary-test simulations. No verdict may
be produced unless all 60 results exist. Stop after the fixed verdict has been
computed. Do not add values or seeds, change the threshold formula, or loosen a
criterion after inspecting results. Any later diagnostic is exploratory and
must be labelled as such.

## 7. Exact command (runs the real simulation)

From the repository root on the prepared machine:

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_graded_encoding_balanced.py
```

This command is intentionally not run during implementation.
