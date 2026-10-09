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

> **REVISION 2026-10-09 (project owner), before any synthetic-market run:
> `recent_change` bound ±1 (Proposal A).** The original text above is kept
> unchanged.
>
> *The change.* The recent change is still the difference from the preceding
> synthetic price. Its clip widens from ±0.2 to **±1**, the natural range of a
> difference between two probabilities, in the generator
> (`simulator.generate_signal_markets`). The encoder's `FeatureSpec` widens to
> `[-1, 1]` to match, still mirrored under NO. A change of 0 still encodes to
> 90 Hz.
>
> *Why.* At ±0.2, 57% of markets sat at the clip (28.6% low, 28.4% high), so the
> feature's pool mostly fired at 30 or 150 Hz. The unclipped change has
> sd 0.34, median |change| 0.24 and maximum |change| 0.94. At ±1 nothing clips,
> and the rates are graded: sd about 20 Hz, spanning 40–146 Hz.
>
> *What it touches:*
>
> - **Only the clip.** The generator's random stream is untouched. True
>   probabilities, prices, outcomes, distractors, time to resolution and liquidity
>   are identical to before.
> - **No validated stimulus changes.** Every earlier graded run and diagnostic
>   held `recent_change` at 0.0, which encodes to 90 Hz under either bound.
> - **The momentum baseline.** It is `clip(price + recent_change, 0, 1)`, so it
>   now uses the unclipped change. It is a reported baseline and never gates.
> - **Drive.** Per-framing drive now runs from 22.8 to 67.5 kHz, and
>   **2.12% of presentations exceed 60 kHz** (was 6.1%). The largest YES−NO drive
>   difference is 30.0 kHz (was 33.4).
> - **Config hash.** The sweep's configuration hash is now `3e0cab12f7`.
>
> *Caveat, on record.* The synthetic markets are independent, so `recent_change`
> remains **largely a noisy copy of price**: its correlation with price is 0.69,
> and 0.35 with the outcome. It is **not a true price-dynamics feature**.
>
> - **Where the signal requirement is measured.** The synthetic phase measures it
>   through the **signal** feature (Section 6), not through `recent_change`.
> - **Deferred to Phase 2.** A realistic within-market change (Proposal B) is
>   deferred to Phase 2, where real price histories exist (Kalshi;
>   [`open-decisions.md`](open-decisions.md), item 6).

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
validation is superseded and balanced re-validation is pending. *[Corrected
2026-10-09: stale. The balanced re-validation ran and FAILED
([`balanced-encoding-failure.md`](balanced-encoding-failure.md)). The encoder the
sweep uses — left-only pools, mirrored NO framing, no balancing, 30–150 Hz — was
then ACCEPTED ([`graded-encoding-left-only-mirrored.md`](graded-encoding-left-only-mirrored.md),
commit `c084908`). See the revision at the head of Section 4.]* Each decision uses
Option B: one YES framing and one NO framing. A presentation is **1000 ms × 5
trials**, because 100 ms × 1 trial was below the pre-stated single-shot noise margin.
YES and NO use the same simulation seed for a market; seeds start at 20270000 and are
a fixed function of strength, market seed and chronological index.

The primary CIRCUIT-80, per-type-mean readout is converted to an uncalibrated
probability by `sigmoid(mitigated_score_difference / 20)`. The 20-Hz scale is an
**unverified fixed placeholder**; Platt calibration is intended to absorb scale, but
could be affected by saturation. *[Decided 2026-10-09: 20 Hz is fixed. It cannot
affect the Section 6 gate:]*
- *Platt calibration acts on `logit(sigmoid(S/20)) = S/20` and rescales it
  exactly unless |S| exceeds about 690 Hz (the 1e-15 probability clip). So
  saturation does not arise at any realistic score.*
- *Actions depend only on the sign of S.*
- *It sets only two things: the accuracy arm's raw forecast (and so that arm's
  teaching signal) and the uncalibrated metrics.*
- *The ACCEPTED validation's seed-mean scores, −3.7 to −29.1 Hz, map to 0.45–0.19.* The decision margin is zero.

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
the real-market phase will use; `drift_rate = 0.01` is still a placeholder. *[Corrected
2026-10-09: stale. `drift_rate = 0.01` was decided on 2026-09-30, together with
`profit_scale` 1.0, `learning_rate` 0.1 and `floor_fraction` 0.1
([`open-decisions.md`](open-decisions.md), item 5).]* The
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

> **REVISION 2026-10-09 (project owner), before any synthetic-market run:
> per-decision ignition tracking.** The original text above is kept unchanged.
>
> *Why.* The extremes containment diagnostic found a single-trial,
> population-wide event at the sweep's lowest-drive stimulus (22,759 Hz, 1 of 2
> seeds). In that trial 65% of free KCs were recruited, on both sides. The event
> moved that framing's CIRCUIT score by 15 Hz, and made about 2,400
> non-stimulated KCs eligible for plasticity.
>
> *What is recorded, every decision, both framings, per trial (binned exactly as
> in the diagnostics):*
>
> - the recruited fraction of non-stimulated KCs (above 0.5 Hz in that trial):
>   overall, left and right;
> - the recruited count;
> - the recruited KCs' mean rate;
> - the mean APL rate;
> - `ignited_any_trial`: true when any trial's overall fraction exceeds 1%.
>
> These are the thresholds of every left-only diagnostic. They are now config
> fields (`ignition_active_hz = 0.5`, `ignition_spread_fraction = 0.01`).
>
> *Implementation.* The simulator interface now requires `present_trials`. The
> real backend wraps the population simulator: one `run_cue_rates` call, binned
> with the diagnostics' `bin_spikes`. Its trial means equal the former
> `present` exactly, so scores, actions, eligibility and learning are unchanged.
> The tracking is **reported, never gating**, and it changes no stimulus, seed or
> run.
>
> *Config hash.* It changes from `3e0cab12f7` to **`688d1064a3`** (new
> threshold fields and output schema). The run count is unchanged.
>
> **DRAFT — NOT ADOPTED (2026-10-09). Optional safeguard: no plasticity update on
> an ignited presentation.** The project owner will decide after the low-drive
> follow-up diagnostic
> ([`low-drive-ignition-followup-diagnostic.md`](low-drive-ignition-followup-diagnostic.md)).
> Nothing below is implemented; the code has no such switch.
>
> - *Rule (draft).* On a **training** market, if either framing has
>   `ignited_any_trial`, treat the decision like an abstention for learning: no
>   `record_decision`, no dopamine-gated update and no drift step. This mirrors
>   the existing rule that an abstention teaches nothing and advances no drift.
>   The action is still taken and recorded, along with
>   `learning_skipped_ignition: true`.
>   - Test markets are unaffected, because weights are already frozen there.
>   - The learning-off arm is unaffected.
>   - A narrower variant checks only the chosen framing. That protects
>     eligibility, but it would still teach from a decision made on a score the
>     other framing's event distorted.
> - *Detection threshold.* The tracking label: a trial is ignited when more than
>   1% of non-stimulated KCs fire above 0.5 Hz in that 1-s trial (at least one
>   spike).
>   - Per-trial binning catches single-trial events that a trial mean would
>     dilute.
>   - In the saved runs, all 749 contained trials with per-trial data had at
>     most 0.021% spread (598 exactly zero; the rest were the single γ-lobe KC
>     below). The one ignited trial had 65%.
>   - The one steadily driven KC (`KCg-s2`, 1 of about 4,677) is 0.02%, far
>     below the threshold. False positives are therefore not expected, but that
>     is unverified under learned weights.
> - *What it protects against:*
>   - eligibility spread onto recruited non-stimulated KCs (about 2,400 at about
>     0.013 each in the observed event, roughly 17% extra eligibility mass);
>   - reward credited to a decision taken on an event-distorted score (+15 Hz
>     in the observed event, against a contained score SD of about 1.2 Hz).
> - *What it costs:*
>   - **Less learning from low-drive markets.** Up to the 83 training
>     presentations below 30 kHz, times their actual ignition rate.
>   - **A selection effect.** The skipped markets are not random: they are
>     low-drive feature combinations, such as a NO framing at a high price with
>     short time to resolution and low liquidity. So the learned weights are
>     systematically under-trained there.
>   - **A data-dependent drift clock.** Drift then also depends on a stochastic
>     network event.
>   - **A new gate on learning.** It is one more data-dependent rule, absent from
>     the first learning test under which learning was demonstrated.
>   - **Adoption.** It would need a config field, a config-hash change and a
>     dated revision **before** the run.

## 4. Intensity-bias mitigation — SELECTED 2026-09-22

> **REVISION 2026-10-09 (project owner), before any synthetic-market run:
> NO MITIGATION.** This supersedes the 2026-09-22 selection below. The original
> text is kept unchanged as the record.
>
> **What the sweep uses.** The validated encoder exactly as ACCEPTED: pools drawn
> from left-hemisphere KCs only, guarded by `assert_pools_left_only`; mirrored NO
> framing; no balancing (Option B `unbalanced`, 500 feature-pool KCs per framing,
> the balance pool never presented); 30–150 Hz. Decisions use the raw CIRCUIT-80
> per-type-mean score difference `S_YES − S_NO`. In code this is
> `mitigation = "none"`, the default of the config, the runner and the launcher.
>
> **Rationale:**
>
> 1. *What was validated.* The ACCEPTED graded validation measured the raw,
>    unmitigated score, so the raw score is the validated quantity. Innate-score
>    subtraction would read a quantity no validation has measured.
> 2. *The control isolates learning.* The learning-off control has the same drive
>    confound but no learning. So the Section 6 learning comparison (profit
>    against learning-off) isolates learning.
> 3. *Cost.* Innate subtraction would add 25% more runs, double the longest
>    chain, and make every learning-off decision an exact tie.
>
> **The innate policy is measured and reported, not removed.** The untouched
> circuit has a drive-driven policy: an expected tendency to bet against the
> higher-priced side. It is reported in `innate_policy` (per strength, and
> pooled) and is never part of the gate. It is computed from the learning-off
> arm's decisions: the sign of the raw score at baseline weights, over all 100
> markets per seed. Two things make this exact:
>
> - *Test actions.* With margin 0, a held-out action is exactly that sign.
> - *Training actions.* They differ from it only where training-only exploration
>   broke a tie.
>
> The report gives:
>
> - the fractions of YES, NO and tie;
> - the fraction backing the higher-priced side;
> - the slope and correlation of the score on price, and on `D_YES − D_NO`;
> - YES/NO/tie fractions and the mean score in ten equal-width price bins.
>
> Every decision now records the exact presented drive of both framings
> (`drive_yes_hz`, `drive_no_hz`).
>
> *(The drive and price figures in this paragraph are for the original ±0.2
> `recent_change` bound. For the ±1 bound adopted later the same day, see the
> revision in Section 1: 2.12% of presentations above 60 kHz, drive 22.8–67.5 kHz,
> largest YES−NO difference 30.0 kHz. The price figure is unchanged.)*
>
> **Scope of the validation, on record.** It varied only the price pool, with the
> other features held at their midpoint (90 Hz). The sweep varies all five
> features, three of them mirrored. As a result:
>
> - YES−NO drive differences reach ±33 kHz, against at most 10.6 kHz validated.
> - Per-framing drive runs from 19.9 to 70.1 kHz; 6.1% of presentations exceed
>   60 kHz, the highest drive ever run with left-only pools.
> - 7.8% of prices fall outside the validated 0.06–0.94.
>
> These extremes are the subject of a separate pre-stated **diagnostic**, not a
> validation, which has not been run:
> [`synthetic-extremes-containment-diagnostic.md`](synthetic-extremes-containment-diagnostic.md).
>
> **Naming.** "Left-only *pools*" means the encoder draws its pools from
> left-hemisphere KCs; this is part of the primary sweep. It is distinct from the
> preregistered left-only *MBON readout* post-hoc rescoring in Section 3, which
> is unchanged.
>
> **Unchanged:** the Section 6 criterion, the arms, the seeds and the strengths.

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

> **REVISION 2026-10-09 (project owner), before any synthetic-market run:
> pre-stated sensitivity analysis excluding ignited test markets.** The criterion
> above is unchanged, and this analysis **cannot rescue or overturn it**. It is
> reported only, never gating.
>
> - *Procedure.* At each strength, drop every held-out market (strength, seed,
>   index) in which **either framing ignited in any trial** (`ignited_any_trial`)
>   in **either arm the gate compares**: `profit` or `learning_off`. The market
>   price is not simulated.
> - *Recompute.* On the remaining markets, recompute both paired Brier
>   improvements. Use the same 95% percentile bootstrap: 2,000 resamples,
>   resampling markets, with seeds 20261099 + 200 + i (versus market) and
>   20261099 + 300 + i (versus learning-off), where i is the strength's index.
> - *Report:*
>   - excluded and remaining counts;
>   - both intervals;
>   - whether both lower bounds lie above zero;
>   - the smallest strength at which they do;
>   - each arm's training and test decisions with an ignited framing.
>
> **Known limits, stated before any run:**
>
> 1. **The excluded markets are not random.** They are low-drive feature
>    combinations. The remaining set is a biased subset, and its result describes
>    those markets, not the sweep.
> 2. **Learning from ignited training presentations cannot be removed
>    afterward.** The loop is closed (score → action → teaching). Excluding test
>    markets does not undo weight changes made during training. Only the drafted
>    safeguard in Section 3 would prevent them, and it is not adopted.
> 3. **The comparison arms may differ.** The two arms can, in principle, differ in
>    which presentations ignite, because their weights differ. The union over both
>    is excluded.
> 4. **Removed markets cut the 150 paired markets.** Excluding them widens the
>    intervals.

Fake verdict tests are required: a simulator whose weights cannot affect output must
not pass, while a deliberately learnable fake must pass. Fake success validates the
pipeline and verdict logic only, not the biological model.

## 7. Jobs, restartability and estimated cost

> **REVISION 2026-10-09 (with the Section 4 revision).**
>
> - **Plan.** Under no mitigation the plan is the same as under balancing:
>   **20,000 simulation runs in 100 jobs**. Each job is one 200-run chain, there
>   are no innate jobs, and the longest chain is 200 runs.
> - **Innate subtraction, for the record.** It would have needed 125 jobs and
>   25,000 runs, with a 400-run longest chain.
> - **The launcher's memory rule** now applies as stated below. It was ported
>   from the first learning launcher on this date.

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
remains a prerequisite. *[Corrected 2026-10-09: stale. `run_cue_rates` has since run
on the real model in every left-only diagnostic and in the ACCEPTED graded
validation (60 simulations, commit `c084908`).]*

The runner's `--dry-run` path imports no Brian2 backend, builds no network, and writes
nothing. The parallel launcher follows the first-learning launcher pattern and limits
processes by RAM. *[Corrected 2026-10-09: until this date the synthetic launcher did
not limit processes by RAM. It used a fixed `--max-procs`, default 1. It now reuses
the first learning launcher's rule: `floor((available − headroom) / 5 GB)`, capped
at the core count and `--max-procs`, with a memory re-check before each start and
staggered starts. The 5 GB per process is not measured on the server.]*

> **REVISION 2026-10-09 (with the Section 3 ignition-tracking revision).**
>
> - **Per-job output grows** by the per-trial ignition record: about 300 bytes
>   per framing, about 60 KB per job (an arithmetic estimate, not a measured file
>   size).
> - **The backend** is now the population simulator with per-trial binning. One
>   simulation per framing, as before, so the plan is unchanged: **20,000 runs in
>   100 jobs**, longest chain 200 runs.
> - **Config hash:** `688d1064a3`.
> - **Run order.** The low-drive follow-up diagnostic (100 simulations, about
>   92 minutes serial) is pre-stated to run before the sweep.

## Results

*None. Append results here after the selected mitigation has completed;
do not edit the protocol or criterion above in response to results.*
