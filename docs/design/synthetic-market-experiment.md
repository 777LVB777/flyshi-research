# Synthetic-market signal-requirement experiment

**Status: pre-statement, written 2026-09-21 before any synthetic-market brain-model
run. Nothing in this protocol has been run against the real model.** The implementation
is tested only with pure-numpy fake simulators. If a fixed value or criterion must
change, append a dated revision before running; do not loosen it after seeing results.

This is the calibration stage in Section 7 of
[`mb-learning-interface.md`](mb-learning-interface.md), not the historical-market
study. Its narrow question is: **how much controlled extra information must the
engineered signal feature contain before the learned circuit improves held-out
probability forecasts?**

## 1. Synthetic markets

Each chronological sequence contains 100 independent binary markets. For each market:

1. Draw the hidden true YES probability uniformly from 0.1 to 0.9.
2. Draw the market price by adding uniform error in `[-0.20, +0.20]` to the true
   probability and clipping to `[0.01, 0.99]`. The maximum deviation 0.20 is an
   **unverified synthetic-design choice**, not an empirical claim about markets.
3. Draw the resolved outcome from the hidden true probability.
4. Draw an independent distractor probability uniformly from 0.05 to 0.95.
5. Construct the signal feature as
   `signal = (1-strength)*distractor + strength*true_probability`.

At strength 0 the signal is independent of truth in the population; at strength 1
it equals the hidden true probability. Using the same market seed at every strength
keeps the true probabilities, prices, outcomes, distractors, time-to-resolution and
liquidity identical. Only the mixture forming `signal` changes. Recent price change
is the clipped difference from the preceding synthetic price. Time-to-resolution and
normalised liquidity are seeded independent distractors. These constructions are
engineered and **unverified as models of real market data**.

The fixed sweep is **0, 0.1, 0.2, 0.4, 0.8**. The five market seeds are
**20261001–20261005**, giving 500 markets per strength and 2,500 market instances in
the complete sweep.

## 2. Chronological split and leakage controls

Within each 100-market sequence, markets 0–69 are training markets and 70–99 are
held-out test markets. The order is never shuffled. Circuit weights and every fitted
component use training markets only; circuit plasticity is frozen throughout test.
The test outcomes are passed only to final scoring.

Every non-neural baseline uses the identical markets, chronological split, feature
matrix and shared Platt calibration implementation in
`src/flyshi_research/evaluation/`. The circuit also fits that same calibration step
from its training forecasts and training outcomes. Calibrated and uncalibrated
forecast metrics are both retained. Using online, changing-weight training forecasts
to fit the circuit calibrator is an **unverified choice** and a limitation: their
distribution may differ from frozen-weight test forecasts.

## 3. Circuit presentation and learning

The encoder uses all five feature pools: price, recent change, time to resolution,
liquidity and signal. Its nominal rate range is 30–150 Hz; the earlier unbalanced
validation is superseded and balanced re-validation is pending. Each decision uses
Option B: one YES framing and one NO framing. A presentation is **1000 ms × 5
trials**, because 100 ms × 1 trial was below the pre-stated single-shot noise margin.
YES and NO use the same simulation seed for a market; seeds start at 20270000 and are
a fixed function of strength, market seed and chronological index.

The primary CIRCUIT-80, per-type-mean readout is converted to an uncalibrated
probability by `sigmoid(mitigated_score_difference / 20)`. The 20-Hz scale is an
**unverified fixed placeholder**; Platt calibration is intended to absorb scale, but
could be affected by saturation. The decision margin is zero.

An untouched circuit can tie. Because abstentions teach nothing, training would
otherwise never start. Therefore, **on training markets only**, an exact abstention
is replaced by a seeded 50/50 YES/NO exploratory action (exploration seed 20261090).
It is a real acted-on decision and may learn; test ties always abstain. This
training-only exploration rule is an **unverified engineering choice** required to
bootstrap the stated learning rule. It must be reported and must not silently carry
into the held-out test.

Four arms use identical markets and seeds:

- `profit`: headline arm; abstract PAM/PPL1 strength comes from net paper P&L.
- `accuracy`: comparison arm; strength comes from Brier improvement over market
  price, using the probability available at decision time.
- `learning_off`: no plasticity, with everything else unchanged.
- `profit_drift_off`: the profit arm with `drift_rate = 0` — the preregistered
  **drift sensitivity check** (added 2026-09-22). It is its own *training*
  condition because drift acts inside the learning loop and cannot be recovered
  from a run that had drift on. It is reported next to the profit arm and is
  **not** part of the Section 6 gate, which is defined on `profit` against the
  market price and against `learning_off`.

Dopamine remains an abstract teaching signal applied by our plasticity rule. No
dopamine neuron is stimulated. The inferred compartment map retains the
**unverified** status documented elsewhere.

**Decided 2026-09-22** ([`open-decisions.md`](open-decisions.md), items 2–4):
the accuracy arm uses `brier_scale = 0.04` with symmetric `[-1, 1]` clipping and
`dead_zone = 0`, so its reward size matches the example profit reward and the
arms differ in signal type rather than size (typicality of that example is
**unverified**). Drift advances one step per acted-on resolution, the same clock
the real-market phase will use; `drift_rate = 0.01` is still a placeholder. The
readout uses all 96 MBON instances in both hemispheres. Left-hemisphere-only
MBONs and drift disabled are both preregistered, and neither changes the success
criterion in Section 6 — but they are different kinds of thing. Drift-off is the
fourth *arm* above and is in the Section 7 job list. **Left-only is a POST-HOC
RESCORING, never an arm or a condition**, and adds no runs: every job saves the
per-MBON rates of both framings for every market, plus the MBON root IDs and type
labels, and the rescoring applies the frozen side table
(`src/flyshi_research/learning/data/mbon_sides_783.json`) to them. **Here the
rescoring is NOT exact**, because this experiment's loop is closed — score →
action → teaching — so a left-only readout would have produced different decisions
and different weight updates. It rescores the runs as they actually happened under
a left-only readout; it does not replay the decision loop, so it cannot show what
a left-only system would have done. (The first learning test is the exception: its
teaching signal comes from the condition and not the readout, so the rescoring
there is exact — [`first-learning-test.md`](first-learning-test.md), Section 7.)
The left-only decision margin would also have to be calibrated separately on
training markets.

## 4. Intensity-bias mitigation — SELECTED 2026-09-22

The primary experiment uses `total_drive_balancing`. It is the default Option B
encoder. `innate_score_subtraction` is not selected.

### Option A: `total_drive_balancing`

A fixed, disjoint pool of `B=300` balancing KCs is added to both framings. If
`D_s = sum_f n_f r_s,f` is the raw feature-pool drive, the higher-drive framing's
balancing pool fires at 30 Hz and the lower-drive framing's pool fires at
`30 + |D_YES-D_NO|/B` Hz. Both totals are therefore
`max(D_YES,D_NO) + B×30`, without changing any feature-pool rate. This removes a
fake score term that depends only on aggregate rate.

**Unverified:** equal summed drive need not mean equal circuit effect because different
KCs reach different MBONs. Several simultaneous pools and the 300-KC filler pool have
not been validated by a real graded-style experiment. The filler also carries the
original imbalance inversely rather than destroying it.

### Not selected: `innate_score_subtraction`

For each exact market stimulus, run both framings at original weights and save their
scores. Decisions use `(current_yes - innate_yes) - (current_no - innate_no)`. The
innate score is simulated exactly, not approximated by a fitted model. Baseline-score
jobs are shared across the three arms.

**Unverified:** this doubles the runs per market, differences two noisy quantities,
can retain an intensity×learning interaction, removes useful innate structure, and
makes the learning-off score identically zero (hence its test behavior is abstention).

The options are not combined in the primary experiment. The selected name remains
part of the configuration hash. The old unbalanced encoder remains available as a
named ablation, not as the primary stimulus.

## 5. Baselines and metrics

All baselines in `flyshi_research.evaluation.baselines` run on the identical split:

- seeded random;
- always the training-set base rate;
- market price as forecast;
- simple momentum (`price + recent_change`, clipped);
- NumPy logistic regression on the same five encoder features.

Each gets the same Platt calibration procedure and retains uncalibrated output. The
logistic L2 strength, Platt suitability and 10-bin ECE remain **unverified defaults**
that must not be tuned on test results.

For every circuit arm and baseline report: Brier score, clipped log loss, equal-width
ECE plus reliability data, P&L after a 0.01 per-unit fee and 0.02 full spread, maximum
absolute drawdown, turnover and abstention rate. The fee/spread values and cost model
are **unverified synthetic placeholders**. Forecast and trading metrics remain
separate claims.

## 6. Pre-stated success criterion and signal requirement

The primary arm is `profit`. For every held-out market compute two paired Brier
improvements:

- market improvement = market-price squared error minus profit-arm squared error;
- learning improvement = learning-off squared error minus profit-arm squared error.

Pool the 150 held-out markets at a strength (30 per seed × 5 seeds) and form seeded
**95% percentile bootstrap intervals**, resampling markets, with 2,000 resamples.
Bootstrap seeds are 20261099 plus fixed offsets recorded in the configuration.

A strength passes only if **both lower interval bounds are strictly above zero**.
Thus the learned circuit must beat the calibrated market-price baseline and its own
learning-off control, not merely one of them. The reported **signal requirement** is
the smallest swept strength that passes. If none passes, the result is “no signal
requirement demonstrated within 0–0.8.” The accuracy arm and every other baseline are
reported comparisons and cannot rescue a failed primary criterion.

No correction for selecting the minimum across five ordered strengths is applied;
this is a stated limitation. Results need not be monotonic, but any higher strength
that fails after a lower one passes must be highlighted as instability.

Fake verdict tests are required: a simulator whose weights cannot affect output must
not pass, while a deliberately learnable fake must pass. Fake success validates the
pipeline and verdict logic only, not the biological model.

## 7. Jobs, restartability and estimated cost

The unit of parallel work is one `(strength, market seed, arm)` chain. Its 70 training
markets are strictly sequential; its 30 test markets follow with weights frozen.
Finished job files are skipped. Restartability is currently **job-granular**: an
interrupted 100-market chain restarts that chain, while every completed chain is
preserved. Per-market checkpoints are not implemented (**unverified operational
risk**). Each process owns one network.

- Selected total-drive-balancing run: 5 strengths × 5 seeds × **4 arms** × 100 markets × 2 framings
  = **20,000 simulation runs** in **100 jobs**. (Before the drift-off arm was added
  on 2026-09-22 this was 3 arms, 15,000 runs in 75 jobs; the extra 5,000 runs are
  the drift sensitivity check.)

Each job also saves the per-MBON rates of both framings for all 100 markets (for
the left-only post-hoc rescoring, which adds no runs), about 150 KB per job and
roughly 15 MB across the sweep — an arithmetic estimate from 96 instances × 2 framings × 100 markets, not a
measured file size.

Each run is 1000 ms × 5 trials, so this is 100,000 simulated
trial-seconds respectively, plus network builds. Wall-clock time and memory on the
server are **unverified**. The fast runner equivalence test has since been run
and PASSED (git commit `6a00cdd`; mean old-vs-new distance 4.61 Hz against the
5.10 Hz tolerance; all 8 discriminator signs correct —
[`fast-runner.md`](fast-runner.md), section 4). A real `run_cue_rates` execution
remains a prerequisite.

The runner's `--dry-run` path imports no Brian2 backend, builds no network, and writes
nothing. The parallel launcher follows the first-learning launcher pattern and limits
processes by RAM.

## Results

*None. Append results here after the selected mitigation has completed;
do not edit the protocol or criterion above in response to results.*
