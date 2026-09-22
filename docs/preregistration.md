# Preregistration: fly mushroom-body circuit as a forecasting substrate

**Document type:** consolidated preregistration, assembled retrospectively from
existing dated design documents (most pre-statements were written and committed
to git *before* the corresponding run; this document does not change any of
them, it collects them). **Status of this document itself: draft for
confirmation — see Section 11, "Open decisions and confirmations needed."**

**Sources consolidated (verbatim quotes are marked with quotation marks and a
file citation; everything else is this document's own summary):**

- `docs/design/mb-learning-interface.md` (hereafter **MB-LEARN**)
- `docs/design/readout-and-plasticity-options.md` (hereafter **READOUT**)
- `docs/design/first-learning-test.md` (hereafter **FIRST-LEARN**)
- `docs/design/graded-encoding.md` (hereafter **GRADED**)
- `docs/design/mbon-separability.md` (hereafter **SEPARABILITY**)
- `docs/design/synthetic-market-experiment.md` (hereafter **SYNTH-MARKET**)
- `docs/design/degree-preserving-connectome-control.md` (hereafter **SHUFFLE**)
- `docs/design/reduced-mushroom-body-control.md` (hereafter **REDUCED-MB**)

Two additional documents are referenced by the above and are cited by name
where relevant but were not in the list of documents to copy criteria from:
`docs/design/fast-runner.md` (hereafter **FAST-RUNNER**) and
`docs/design/mbon-valence.md` (hereafter **VALENCE**).

**Where a doc's own wording could not be found for something the task asked
this document to state, that gap is quoted and flagged for confirmation rather
than paraphrased or invented.** Search marker used throughout: **[NEEDS
LUCA'S CONFIRMATION]**.

---

## 1. Hypotheses

The source documents are written as engineering pre-statements (protocol +
pass/fail rule) rather than as single-sentence hypotheses. The closest
statements of the overarching hypothesis, quoted:

> "when we add a simple learning mechanism of our own to this brain circuit,
> does it forecast yes/no outcomes better than ordinary, conventional
> methods — and if so, is that because of the brain-derived structure, or just
> because we gave it more knobs to tune?" (MB-LEARN, Section 1)

This decomposes into the per-experiment questions and pre-stated criteria
below (Section 4). No single global statistical hypothesis (e.g., "H1: circuit
profit > baseline profit") is stated in one place in the source docs; the
closest is the synthetic-market pass criterion (Section 4.6) and the
first-learning-test verdict rule (Section 4.5). **[NEEDS LUCA'S CONFIRMATION]:**
if a single top-line hypothesis statement is wanted for the OSF record, it is
not already written down verbatim anywhere in the source docs and would need
to be composed new, which this document does not do on its own authority.

---

## 2. The model

- Published model: "the brain model published by **Shiu and colleagues in
  2024** (in the journal *Nature*, volume 634, pages 210–219;
  doi:10.1038/s41586-024-07763-9)" (MB-LEARN, Section 2).
- Two wiring versions are used for different purposes: "**Version 630**
  ('v630'): the wiring the original authors shipped with their code. We used
  it to confirm we could reproduce their published result... **Version 783**
  ('v783'): a later, revised version of the same wiring. We used it for all of
  our own mushroom-body analysis" (MB-LEARN, Section 2).
- "The single most important fact about this model: it does not learn
  anything on its own... **Any learning in this project is ours, added on top.
  It is not part of the Shiu model, and we will never describe it as theirs.**"
  (MB-LEARN, Section 2).

---

## 3. Design overview: three stages

Quoted verbatim (MB-LEARN, Section 7):

> "1. **Synthetic markets first.** These are made-up markets where *we* set
> the hidden truth, so we know the right answer exactly. **This is
> calibration, not the study:** their purpose is to measure how much signal
> the system needs before it can forecast at all, using the known-information
> 'signal feature' from Section 4a.
> 2. **Historical real prediction-market data next.** Real past markets with
> known outcomes. **This is the actual study.**
> 3. **Prospective forecasts last.** Forecasts logged *before* the outcomes are
> known, so there is no possibility of hindsight creeping in."

This preregistration covers stage 1 (synthetic markets) in full protocol
detail (Section 4.6 below) plus the circuit-diagnostic and infrastructure
experiments that had to be run before stage 1 could be attempted. Stages 2 and
3 have no chosen dataset yet (Section 11) and are not otherwise specified.

---

## 4. Experiments, conditions, controls, and pre-stated pass/fail criteria

Each subsection gives: the question, the fixed design, the exact pass/fail
wording (quoted), the seeds, and the run status as of this document's
assembly.

### 4.1 Graded-rate encoding test — **COMPLETED, verdict ACCEPTED**

**Question** (GRADED, Section 1): "Whether the output neurons respond in a
graded, monotonic way to *how hard* one pool is driven has **never been
tested**... If it does not, a price of 0.3 and a price of 0.7 could look the
same to the readout, and no learning rule could fix that."

**Design (fixed, GRADED Section 2):**

| Item | Value |
|---|---|
| Stimulated cells | "one pool of 100 Kenyon cells: **set A**, `--kc-set-size 100 --kc-set-seed 20260316`" |
| Stimulation rates | "**30, 60, 90, 120 and 150 Hz**, one run per rate" |
| Run length | "**1000 ms**, **5 trials** per run" |
| Simulation seed | "**20260316**, the same for all five runs" |
| Code path | "the **existing upstream path** (`check_mb_response.run_condition`)... **not** `fast_runner`" |

**Pre-stated verdict rule, quoted in full (GRADED, Section 4):**

> "- **ACCEPTED** — the CIRCUIT score is strictly monotonic across **all five**
> rates **and** the endpoint distance is ≥ 15.30 Hz.
> - **USABLE RANGE** — the endpoint distance passes (≥ 15.30 Hz), but the
> score is not strictly monotonic across all five rates..., **and** the
> **longest strictly monotonic contiguous sub-range spanning at least three
> rates** has its **own endpoint distance**... of at least 15.30 Hz (the
> **sub-range gate**).
> - **FAIL** — the endpoint distance is below 15.30 Hz, **or** no strictly
> monotonic contiguous sub-range spans at least three rates, **or** the chosen
> sub-range's own endpoint distance is below 15.30 Hz (any combination)."

The 15.30 Hz threshold is 3 × d_AA (5.10 Hz; see Section 4.2), fixed before
this test's run: "the endpoint threshold is 3 × 5.10 = **15.30 Hz**, inclusive
(≥)" (GRADED, Section 4).

**Result (GRADED, "Results" section): Verdict ACCEPTED.** Score strictly
monotonic decreasing over 30–150 Hz (−9.6, −18.5, −33.9, −51.9, −66.8), 30-vs-150
Hz endpoint distance 222.88 Hz (≈14.6× the 15.30 Hz threshold). Validated range
30–150 Hz, matching the encoder's bounds. Secondary, non-criterion finding: the
same five files scored under other preregistered sign tables show the score
*rising* with drive under STRICT and GROUP, and falling under CIRCUIT 70/80/90%
and `instance_sum` — "the **dependence on intensity is robust, but its
direction is not**" (GRADED, "What the result shows"). This is the origin of
the intensity bias discussed in Sections 4.4 and 4.6 below.

### 4.2 MBON-separability / noise-floor test — **COMPLETED, verdict CONFIRMED**

**Question** (SEPARABILITY, "The question"): the two cue sets' MBON patterns
differ by cosine distance ~0.05; "If that small difference is just noise, no
learning rule can use it and the design fails."

**Pre-stated acceptance criterion, quoted in full (SEPARABILITY, "Pre-stated
acceptance criterion (recorded BEFORE the run)"):**

> "1. **Separability is CONFIRMED (signal is real, not noise) if `R ≥ 3.0` at
> the fine cell (1000 ms / 5 trials).** ... If `1.0 ≤ R < 3.0`, the signal is
> present but not by a clear margin ('marginal'); if `R < 1.0`, the ~0.05
> difference is **not** distinguishable from noise and the readout design
> fails.
> 2. **Cheap-setting usability (secondary):** the 100 ms / 1 trial cell is
> usable for a single run per decision if `R ≥ 3.0` there too; if `1.0 ≤ R <
> 3.0`, the signal is real at that cell but too noisy for a single shot...; if
> `R < 1.0`, that cell is unusable per decision.
> 3. **Per-MBON companion check (interpretability, not the gate):** on the
> eight consistently-discriminating MBONs..., the criterion should also hold
> per-MBON... for a **majority (≥ 5 of 8)** at the fine cell."

**Seeds:** "cue A only at **5 new seeds** (`20260317, 20260318, 20260319,
20260320, 20260321`)... at **two cells**: ... (**1000 ms / 5 trials**) and ...
(**100 ms / 1 trial**)" (SEPARABILITY, "The noise-floor experiment").

**Result:** "Fine cell: d_AA = 5.10 Hz, d_AB = 79.44 Hz, **R = 15.57**,
verdict **CONFIRMED**. Cheap cell: d_AA = 46.09 Hz, d_AB = 88.25 Hz, R = 1.91,
verdict marginal." Per-MBON companion check: "**Fine cell: 8/8 pass**
(majority ≥ 5 → MET). ... **Cheap cell: 6/8 pass.**" (SEPARABILITY,
"Noise-floor results").

**One-sided caveat, quoted (SEPARABILITY, "One-sided caveat, stated in
advance"):** "this measures noise from **cue A only**... it therefore assumes
cue B has comparable run-to-run noise... The symmetry assumption is
**unverified**."

### 4.3 Fast-runner equivalence test — **COMPLETED, verdict ACCEPTED**

**Question:** whether a reusable-network fast simulator path
(`fast_runner.py`) is interchangeable with the existing per-trial-rebuild path,
so the fast path can be used for the (much more expensive) learning
experiments.

**Pre-stated criteria, quoted in full (FAST-RUNNER, Section 4):**

> "**Equivalence is ACCEPTED if BOTH hold:**
> 1. The **mean Euclidean distance** between the old-path and new-path per-MBON
> rate vectors (averaged over the 5 seeds, union MBON support, zero-filled) is
> **≤ the measured same-cue noise floor `d_AA = 5.10 Hz`**...
> 2. **All 8 consistent discriminating MBONs keep the same sign** of the cue-A
> − cue-B difference under the new path...
> If criterion 1 fails, the new path is not equivalent. If criterion 2 fails,
> the readout direction changed and the fast path must not be used for the
> study."

**Seeds:** same five as Section 4.2 (20260317–20260321), cue A, 1000 ms × 5
trials.

**Result: not recorded inside `fast-runner.md` itself** — the design doc's own
"Results" mechanism (used by GRADED and REDUCED-MB) was not filled in for this
test. **The result is recorded only in git history and a run log**: commit
`6a00cdd` ("Fast-runner equivalence test ACCEPTED: mean distance 4.61Hz, 8/8
discriminator signs match") and `repro/mushroom_body/run_log_fast_full.txt`,
which reports: mean old-vs-new distance = 4.606 Hz (per-seed: 5.463, 3.231,
6.053, 3.904, 4.382 Hz) against the 5.10 Hz tolerance — **PASS**; sign check
8/8 — **PASS**; overall verdict line: "ACCEPTED: new path is equivalent to the
existing path within the pre-stated bounds." **This is flagged in Section 10
as a doc/reality inconsistency**, not because the criteria differ from what is
quoted above, but because FAST-RUNNER's own text was never updated to record
that its pre-stated test has now been run and passed.

### 4.4 First learning test — **NOT YET RUN.** Now cleared to run (Section 4.3 dependency satisfied).

**Question, quoted (FIRST-LEARN, Section 1):** "If one group of KCs (cue A) is
repeatedly followed by reward and another (cue B) is not, does the circuit's
readout come to prefer A over B, by more than the run-to-run noise? It also
asks whether that happens *for the right reason* (the controls in Section 5)."

**Protocol (fixed, FIRST-LEARN Section 3):** cue A / cue B = two disjoint sets
of 100 left-hemisphere KCs at 150 Hz (`--kc-set-seed 20260316`); fast runner's
`run_cue_rates`; only KC→MBON weights learn; compartments from the same 80%
dominant-family map as the readout; readout = CIRCUIT `circuit_80`, per-type
mean, all 96 instances, silent = 0 Hz.

**Stages, quoted (FIRST-LEARN, Section 3):**

> "1. **Pre-training test (weights = connectome).** For each of the 5 test
> seeds `20260317, 20260318, 20260319, 20260320, 20260321`: present A, then B,
> each for **1000 ms × 5 trials**...
> 2. **Training.** **N** presentations (placeholder N = 40), half A and half B,
> in a fixed seeded order that is alternating in pairs... Presentation *k* uses
> simulation seed `20260500 + k` and lasts **1000 ms × 1 trial**.
> 3. **Post-training test (plasticity frozen).** Identical to stage 1..."

**Primary measure and threshold, quoted (FIRST-LEARN, Section 4):**

> "`D(s) = score_A(s) − score_B(s)`... `σ` = the **sample standard deviation
> (ddof = 1) of `D_pre(s)`** across the 5 test seeds... `Δ_c = m_c − m_pre`...
> **Threshold:** `T = 3σ`... If `σ` is zero or not finite, the noise
> measurement has failed and the verdict is **INCONCLUSIVE**."

**Conditions and pre-stated criteria, quoted in full (FIRST-LEARN, Section 5
table):**

| Condition | Teaching signal after A | after B | Role | Pre-stated criterion |
|---|---|---|---|---|
| **main** — reward A | PAM | none | gate | `Δ ≥ +T` |
| **(a) plasticity off** | none, rule disabled | none, rule disabled | gate | `\|Δ\| < T` |
| **(b) reward B** | none | PAM | gate | `Δ ≤ −T` |
| **(c) reward both** | PAM | PAM | **reported diagnostic only** | none: reported, never affects the verdict |
| **(d) punish A only** | PPL1 | none | gate | cue B's readout unchanged: `\|mean score_B post − mean score_B pre\| < 3σ_B` |

**Verdict rule, quoted in full (FIRST-LEARN, Section 5):**

> "- **INCONCLUSIVE** — the noise measurement failed (`σ` or `σ_B` is zero or
> not finite), or the result of a gating condition (main, (a), (b), (d)) is
> missing.
> - **NOT DEMONSTRATED** — the main condition fails its criterion, including a
> change of the right size in the *wrong* direction.
> - **CONFOUNDED** — the main condition passes but at least one of the gating
> controls (a), (b), (d) fails.... **Control (c) alone can never produce this
> verdict.**
> - **LEARNING DEMONSTRATED** — the main condition and the three gating
> controls pass."

**Readout sensitivity variants (preregistered, reported, never gating),
quoted (FIRST-LEARN, Section 5b table):** `circuit_70`, `circuit_90`,
`circuit_80_no_gamma3` (γ3 variant — MBON08 and MBON09 zero-weighted), `strict`,
`group`, `circuit_80` summed per instance (`instance_sum`). "**None of them can
change the primary verdict.**"

**Parameters (all placeholders, FIRST-LEARN Section 6):** N = 40 (20 A, 20 B);
training presentation 1000 ms × 1 trial; test presentation 1000 ms × 5 trials;
cue rate 150 Hz; reward strength 1.0; `dopamine_max_rate_hz` = 150
(unanchored); `learning_rate` = 0.1; `floor_fraction` = 0.1; `drift_rate` =
0.01; `drift_steps_per_resolution` = 1; `kc_active_threshold_hz` = 1.0;
`kc_rate_ref_hz` = 150; training-order seed 20260402; training simulation
seeds 20260500 + k (k = 0…39); test seeds 20260317–20260321.

**Dependency now satisfied:** FIRST-LEARN, Section 7, states: "**Run the
fast-runner equivalence test first**" as a precondition, because the test's
cost estimate and validity depend on `run_cue_rates`, and at the time of
writing "the fast runner['s]... equivalence test against the existing path
has not been run." Per Section 4.3 above, that test has since run and passed
(commit `6a00cdd`). **Per the pasted task brief for this document: "the
fast-runner equivalence test has now passed (mean distance 4.61 Hz vs 5.10 Hz
tolerance, 8/8 discriminator signs correct) — the learning test is now cleared
to run."** No run of the first learning test itself has occurred as of this
document.

### 4.5 Synthetic-market signal-requirement experiment — **NOT YET RUN.** One open decision blocks it (Section 11).

**Question, quoted (SYNTH-MARKET, header):** "how much controlled extra
information must the engineered signal feature contain before the learned
circuit improves held-out probability forecasts?"

**Synthetic market construction, quoted (SYNTH-MARKET, Section 1):**

> "1. Draw the hidden true YES probability uniformly from 0.1 to 0.9.
> 2. Draw the market price by adding uniform error in `[-0.20, +0.20]` to the
> true probability and clipping to `[0.01, 0.99]`.
> 3. Draw the resolved outcome from the hidden true probability.
> 4. Draw an independent distractor probability uniformly from 0.05 to 0.95.
> 5. Construct the signal feature as `signal = (1-strength)*distractor +
> strength*true_probability`."

Sweep: "**0, 0.1, 0.2, 0.4, 0.8**." Market seeds: "**20261001–20261005**, giving
500 markets per strength and 2,500 market instances in the complete sweep."

**Chronological split, quoted (SYNTH-MARKET, Section 2):** "markets 0–69 are
training markets and 70–99 are held-out test markets. The order is never
shuffled."

**Arms (SYNTH-MARKET, Section 3):** `profit` (headline), `accuracy`
(comparison), `learning_off`.

**Intensity-bias mitigation — explicitly an open decision, quoted in full
(SYNTH-MARKET, Section 4):**

> "The full run has **no default mitigation**. Luca must choose one explicitly
> before any job is launched. Both are implemented and fake-tested; neither has
> been tested on the real model."

Option A (`total_drive_balancing`) and Option B (`innate_score_subtraction`)
are both specified (SYNTH-MARKET, Section 4) but "**The options are not
combined**." This is carried into Section 11 as an open decision blocking the
run.

**Pre-stated success criterion, quoted in full (SYNTH-MARKET, Section 6):**

> "The primary arm is `profit`. For every held-out market compute two paired
> Brier improvements: market improvement = market-price squared error minus
> profit-arm squared error; learning improvement = learning-off squared error
> minus profit-arm squared error. Pool the 150 held-out markets at a strength
> (30 per seed × 5 seeds) and form seeded **95% percentile bootstrap
> intervals**, resampling markets, with 2,000 resamples. Bootstrap seeds are
> 20261099 plus fixed offsets recorded in the configuration.
>
> A strength passes only if **both lower interval bounds are strictly above
> zero**. Thus the learned circuit must beat the calibrated market-price
> baseline and its own learning-off control, not merely one of them. The
> reported **signal requirement** is the smallest swept strength that passes.
> If none passes, the result is 'no signal requirement demonstrated within
> 0–0.8.'"

Stated limitation, quoted: "No correction for selecting the minimum across
five ordered strengths is applied; this is a stated limitation." (SYNTH-MARKET,
Section 6.)

**Baselines run alongside (SYNTH-MARKET, Section 5):** seeded random;
always the training-set base rate; market price; simple momentum
(`price + recent_change`, clipped); NumPy logistic regression on the five
encoder features. All get the same Platt calibration and retain uncalibrated
output.

**Fake-verdict pipeline test required, quoted (SYNTH-MARKET, Section 6):** "a
simulator whose weights cannot affect output must not pass, while a
deliberately learnable fake must pass. Fake success validates the pipeline and
verdict logic only, not the biological model."

### 4.6 Controls (MB-LEARN, Section 6)

Quoted list of controls to be run "on the same markets and seeds" (MB-LEARN,
Section 6):

> "- **Learning switched off**...
> - **Degree-preserving shuffled connectome**...
> - **Reduced mushroom-body model**...
> - **Logistic regression**...
> - **Market price as the forecast**...
> - **Random**...
> - **Always-base-rate**..."

"Every baseline receives the **same calibration step** and the same tuning
budget as the neural model" (MB-LEARN, Section 6).

**4.6.1 Learning-off.** Same circuit, no teaching signal applied. Used as
condition (a) in the first learning test (Section 4.4) and as the
`learning_off` arm in the synthetic-market experiment (Section 4.5).

**4.6.2 Degree-preserving shuffled connectome — implementation and
synthetic-graph tests complete; real v783 shuffle not yet generated; scope not
yet chosen.**

Method, quoted (SHUFFLE, "Method"): "For two directed edge rows `a -> b` and
`c -> d`, propose `a -> d`, `c -> b` and keep the proposal only when it
satisfies the chosen self-loop and parallel edge policy... The default is ten
accepted swaps per eligible edge; failure to achieve every requested swap
within the attempt limit is an error, not a partial success."

What stays fixed vs. destroyed: SHUFFLE, "What stays fixed" and "What is
destroyed" sections (quoted in Section 9 below, not repeated here for length).

**Scope is an explicit, unresolved open decision, quoted (SHUFFLE, "Scope is
an open study decision"):** "**Open decision for the project owner:** choose
the scope [mushroom-body-only vs. whole-network] and, for the MB scope, freeze
the exact neuron-ID membership file before generation. Neither option is
selected here."

**Pre-stated generation checks, quoted in full (SHUFFLE, "Pre-stated
generation checks"):**

> "A real shuffled artifact passes generation only if all of the following
> hold:
> - row count, each neuron's in/out row degree, and the full `(synapse count,
> sign)` multiset match exactly;
> - non-eligible rows match exactly for the MB-only scope;
> - no self-loop or parallel edge appears when absent from the input;
> - every requested swap was accepted; and
> - endpoint-pair overlap with the original is below 0.50, counting parallel
> edges with multiplicity."

Status line, quoted (SHUFFLE, header): "**Status:** implementation and
synthetic-graph tests complete 2026-09-21. The real v783 connectivity file has
not been read or shuffled. All resource figures and real-connectome behavior
below are **unverified**."

**4.6.3 Reduced mushroom-body model (Bennett, Philippides & Nowotny, 2021) —
protocol-fidelity check COMPLETED and passed; this is not a validated
numerical match to the paper.**

Source, quoted (REDUCED-MB, "Sources and selected model"): "Bennett,
Philippides & Nowotny, 'Learning with reinforcement prediction errors in a
model of the Drosophila mushroom body,' *Nature Communications* 12, 2569
(2021), doi:10.1038/s41467-021-22592-4." Implements "the MV model using the
paper's Eq. 8 plasticity rule, expressed as the discrete update in Methods
Eq. 22."

**Pre-stated reproduction protocol, quoted in full (REDUCED-MB, "Pre-stated
published-result reproduction"):**

> "The unit test reproduces the qualitative result in **Fig. 3d** that the MV
> model's reinforcement prediction tracks an unbounded stepped reinforcement
> schedule.
>
> Protocol, fixed before executing the test:
> - 20 KCs and two non-overlapping cues of 10 KCs at 1 Hz each;
> - 180 trials, cue 1 forced on every trial as in the authors' `choose1=true`;
> - the Fig. 3 schedule from Methods: blocks of 20 trials at `0, +1, +2, +1, 0,
> -1, -2, -1, 0`;
> - Gaussian reinforcement noise with standard deviation 0.1, the paper's
> default;
> - 10 independently seeded NumPy runs;
> - source settings `gamma=1`, `beta=5`, learning rate `0.0125`, initial
> weights in `[0,0.1]`, and a zero weight floor;
> - compare the mean pre-update reinforcement prediction at the final trial of
> each 20-trial block with that block's noiseless reinforcement.
>
> **Pass criterion:** root-mean-square error across those nine endpoints must
> be at most **0.15 reinforcement units**. The paper reports accurate tracking
> but does not state this numerical tolerance; 0.15 is an **unverified,
> pre-stated reproduction tolerance**, not a value attributed to the paper."

**Result, quoted (REDUCED-MB, "Test result"):** "The six reduced-model unit
tests passed on 2026-09-21, including the Fig. 3d endpoint-RMSE gate above.
This verifies the NumPy implementation against its hand-computed one-step
values and the stated qualitative learning-curve target; it is **not an
independent replication of the paper's full MATLAB analysis**."

Explicitly flagged limits, quoted (REDUCED-MB, "Limits"): "The market
adaptation, exact equivalence of NumPy and MATLAB trajectories, and
performance on Flyshi synthetic markets remain **unverified**."

**4.6.4 Logistic regression, market price, random, always-base-rate.** These
are specified only at the level of "run on the identical split" with the same
calibration (SYNTH-MARKET, Section 5; MB-LEARN, Section 6). No separate
pass/fail criterion is stated for these individually anywhere in the source
docs beyond their role inside the Section 4.5 bootstrap comparison (which
compares against `market price` and `learning_off` specifically, not against
logistic regression, random, or base-rate). **[NEEDS LUCA'S CONFIRMATION]:**
whether logistic regression / random / base-rate are meant to also gate the
Section 4.5 pass/fail decision, or are reported comparisons only, is not
stated explicitly; SYNTH-MARKET Section 6 says only "The accuracy arm and every
other baseline are reported comparisons and cannot rescue a failed primary
criterion" — which answers this for the *accuracy* arm and, by the phrase
"every other baseline," appears to extend to logistic regression, random, and
base-rate too, but they are never named individually in the criterion itself.

---

## 5. Metrics

Quoted in full (MB-LEARN, Section 5):

> "- **Brier score** — the average squared difference between the forecast
> probability and what actually happened (0 or 1). *Lower is better.*
> - **Log loss** — another forecast-accuracy score that punishes confident
> wrong answers much more harshly than Brier does. *Lower is better.*
> - **Calibration** — whether the stated probabilities match reality...
> - **Profit and loss after fees and spread**...
> - **Maximum drawdown**...
> - **Turnover**...
> - **Abstention rate** — the fraction of markets on which the system chose
> not to decide... Reported alongside every other number, for every arm.
> - **Performance across multiple seeds**...
> - **Bootstrap intervals**..."

> "Two guardrails we commit to: **good forecast scores do not prove the
> strategy can make money, and profit does not prove the forecasts are
> well-calibrated.**"

Synthetic-market-experiment-specific metric detail, quoted (SYNTH-MARKET,
Section 5): "Brier score, clipped log loss, equal-width ECE plus reliability
data, P&L after a 0.01 per-unit fee and 0.02 full spread, maximum absolute
drawdown, turnover and abstention rate. The fee/spread values and cost model
are **unverified synthetic placeholders**."

---

## 6. The readout, encoder, reward, and learning rule (shared infrastructure)

### 6.1 Input encoding (MB-LEARN, Section 4a)

- Input route: "We skip the smell pathway entirely and inject market
  information straight into the Kenyon cells" — chosen because direct
  projection-neuron (smell) stimulation produced non-sparse, non-separable KC
  activity (65% of KCs active, Jaccard overlap 0.99 between two different
  smells; MB-LEARN Section 3b), while direct KC stimulation produced zero
  spread and fully separable patterns (MB-LEARN Section 3c).
- Features: "Price," "Recent price change," "Time to resolution," "Liquidity,"
  and, "Signal feature (synthetic markets only)" (MB-LEARN, Section 4a).
- Encoder rate bounds, quoted: "the bounds are **30 to 150 Hz**" (MB-LEARN,
  Section 4a), validated by the graded-rate test (Section 4.1 above).
- NO-framing mirroring rule, quoted in full (MB-LEARN, Section 4a table):

  | Feature | Under NO | Why |
  |---|---|---|
  | Price | mirrored (*p* → 1 − *p*) | "It is the market's probability of YES; seen from the NO side the same fact reads 1 − *p*." |
  | Recent price change | mirrored (up ↔ down) | "A rising price is good news for YES and bad news for NO." |
  | Signal (synthetic markets only) | mirrored | "It is built to carry evidence about the outcome, so it points the opposite way from the NO side." |
  | Time to resolution | not mirrored | "Days left is a fact about the market, not about a side." |
  | Liquidity | not mirrored | "How thin the market is is likewise the same from either side." |

  "**Unverified:** only the price rule (*p* → 1 − *p*) was fixed before the
  code was written; mirroring recent change and the signal is our extension of
  it" (MB-LEARN, Section 4a).

### 6.2 Readout — "Option B" (MB-LEARN, Section 4b)

- Run the circuit twice per decision ("YES at price p" and "NO at price
  1 − p"); score each; pick the higher-scoring framing "**but only if the gap
  between the two scores clears a threshold**"; otherwise abstain, which
  "**teaches the circuit nothing**."
- **CIRCUIT sign rule, quoted (MB-LEARN, Section 4b):** "For each output
  neuron, we add its annotated direct PAM and PPL1 dopamine synapses. It gets
  an avoidance-like sign if PAM... supplies at least **80%**; it gets an
  approach-like sign if PPL1... supplies at least 80%. Otherwise it gets zero
  weight." Adopted primary threshold: 80%. "We will report 70% and 90% as
  preregistered sensitivity checks." STRICT and GROUP are "preregistered
  robustness readouts" (also quoted in Section 7 below).
- **Per-type mean aggregation, quoted (MB-LEARN, Section 4b):** "first
  **average the firing rates of the instances within each type**, then apply
  the sign... and add the types up, so **each type gets one vote**...
  **Sum-over-instances remains available in the code as a named variant
  (`instance_sum`), not as the default**."
- **Which instances enter the mean is explicitly unsettled**, quoted (MB-LEARN,
  Section 4b): "Which instances to count (both hemispheres, or left only) is
  **not settled by this document**; the graded-encoding test fixes a choice
  (all instances in both hemispheres) for its own purposes, and it is listed
  as open in Section 8." (See Section 11 of this document.)
- **Intensity bias, "problem 4," quoted at length (MB-LEARN, Section 4b):**
  "The score depends strongly on *how hard* the input cells are driven,
  whatever the input means... Except at a price of exactly 0.5, the 'YES at
  *p*' framing and the 'NO at 1 − *p*' framing drive the price group at
  different rates, so they differ in total drive before the circuit has
  learned anything... Under 'choose the higher score,' the circuit innately
  prefers NO whenever YES is the expensive side, and YES whenever it is cheap:
  a price-dependent, contrarian lean unrelated to anything learned." Direction
  is readout-dependent: "CIRCUIT at 70% and 90% also fall, but **STRICT (0.0 →
  +53.2) and GROUP (+10.8 → +77.6) rise**." Two proposed, unbuilt remedies:
  total-drive balancing and innate-score subtraction (both "**Not decided**").
  "**Any market experiment must address this bias first.**"

### 6.3 CIRCUIT assignment detail and its disagreement with behavioral labels
(READOUT)

- "The explicit 80% disagreements are MBON08 and MBON09. γ3 is therefore a
  genuine exception: MBON08 is zero under the direct-connectivity rule, while
  MBON09 is PAM/avoidance-like, although both have a group-level approach
  label. This exception is reported, not corrected." (READOUT, "Validation
  against the activation-valence table at 80%.")
- γ3 sensitivity variant, quoted (READOUT, "γ3 sensitivity variant"):
  "**Preregistered 2026-09-21, before any learning run,** as an additional
  sensitivity variant (sign table `circuit_80_no_gamma3`...). It is the
  primary CIRCUIT-80 table with the two γ3 types set to zero readout weight."
  Rationale: "**MBON09 is the largest contributor to the intensity bias.**"

### 6.4 Reward (MB-LEARN, Section 4c)

- "we represent dopamine **abstractly**: it is a number saying which dopamine
  family fired and how strongly, applied by our own learning rule (4d), not a
  set of neurons we make fire inside the simulation." "**We do not simulate
  dopamine release or dopamine-neuron activity during learning.**"
- **Reward type is a preregistered experimental variable**, quoted (MB-LEARN,
  Section 4c): "**Profit-based reward (headline arm):** the teaching signal is
  how much money the decision made or lost. **Accuracy-based reward
  (comparison arm):** the teaching signal is how much the *forecast* improved,
  measured by the improvement in Brier score... **Improvement over what?**
  Decided 2026-09-21: **over the market's own quoted probability.**"
- Motivation for two reward types, quoted: "A previous fly-and-markets project
  reportedly saw its model learn a **blanket aversion**... (this account of
  that prior project is **unverified** by us; we include it as motivation, not
  as established fact)."

### 6.5 Learning rule (MB-LEARN, Section 4d)

- "Only one set of connections is allowed to change: the connections **from
  Kenyon cells to output neurons (KC→MBON)**." "Plasticity is
  **compartment-matched**." "When the teaching signal... arrives, **weaken**
  the connections coming from Kenyon cells that were **recently active**." "A
  **floor** stops any connection from being driven below a minimum strength."
  "A **slow drift** continuously nudges every connection back toward its
  original measured value."
- "**Abstentions teach nothing (decided 2026-09-21).**" quoted: "If the
  readout abstained on a market, nothing is saved, and when that market
  resolves **no learning update happens at all**."
- The queue mechanism for delayed outcomes is described but not itself framed
  as a pass/fail criterion.

---

## 7. Sensitivity variants (consolidated)

All quoted from FIRST-LEARN Section 5b unless noted:

| Variant | What changes | Status |
|---|---|---|
| `circuit_70` | CIRCUIT threshold 70% | "preregistered threshold sensitivity check" |
| `circuit_90` | CIRCUIT threshold 90% (MBON04, MBON10, MBON15 drop to zero relative to the 80% primary) | "preregistered threshold sensitivity check" |
| `circuit_80_no_gamma3` | CIRCUIT-80 with MBON08 and MBON09 set to zero weight | preregistered γ3 sensitivity variant (READOUT, MB-LEARN) |
| `strict` | only confidently labelled types (MBON05, MBON21, MBON11, MBON12) | "preregistered robustness check" |
| `group` | STRICT plus group-level behavioural labels | "preregistered robustness check" |
| `instance_sum` | `circuit_80` summed per instance instead of per-type mean | "the named aggregation variant" (not one of the preregistered robustness checks per MB-LEARN Section 4b, unless separately added) |

"None of them can change the primary verdict" of the first learning test
(FIRST-LEARN, Section 5b). For the graded-rate test they are reported as
"exploratory... no criterion, and it does not change the verdict" (GRADED,
"Qualification found while checking").

---

## 8. Seeds (consolidated)

| Purpose | Seed(s) | Source |
|---|---|---|
| KC cue-set A/B selection (fixed, all cue-direct experiments) | `20260316` | GRADED, FIRST-LEARN, SEPARABILITY |
| Graded-rate test simulation seed | `20260316` | GRADED |
| Noise-floor / fast-runner-equivalence seeds | `20260317, 20260318, 20260319, 20260320, 20260321` | SEPARABILITY, FAST-RUNNER, FIRST-LEARN (test seeds) |
| First-learning-test training-order seed | `20260402` | FIRST-LEARN |
| First-learning-test training simulation seeds | `20260500 + k`, k = 0…N−1 | FIRST-LEARN |
| Synthetic-market market seeds | `20261001–20261005` | SYNTH-MARKET |
| Synthetic-market training-only exploration seed | `20261090` | SYNTH-MARKET |
| Synthetic-market bootstrap seed | `20261099` plus fixed offsets recorded in the configuration | SYNTH-MARKET |
| Synthetic-market simulation seeds | "start at 20270000 and are a fixed function of strength, market seed and chronological index" | SYNTH-MARKET |
| Reduced-MB reproduction test | "10 independently seeded NumPy runs" (specific integers not given in the doc) | REDUCED-MB |
| Degree-preserving shuffle | "A seeded NumPy random generator chooses edge pairs"; command shows a `SEED` placeholder, no fixed integer specified in the doc | SHUFFLE |

**[NEEDS LUCA'S CONFIRMATION]:** the reduced-MB and shuffle-connectome docs do
not give concrete seed integers (only "seeded" / a `SEED` placeholder); if a
fixed seed list is wanted for the formal preregistration record, it is not yet
written down.

---

## 9. Degree-preserving shuffle: what is preserved and destroyed (quoted in full)

Quoted verbatim (SHUFFLE, "What stays fixed" / "What is destroyed"):

> "What stays fixed:
> - The neuron set and number of edge rows.
> - Every neuron's unweighted out-degree and in-degree, exactly...
> - The global joint distribution of `(synapse count, sign)`, exactly.
> - Each presynaptic neuron's multiset of outgoing synapse counts and signs...
> - Rows outside the chosen scope, exactly.
> - No self-loop or parallel edge is introduced if the input contains none...
>
> What is destroyed:
> - Specific pre/post partners, motifs, paths, compartments, and cell-type
> preferences within the selected scope.
> - Each target's weighted in-degree and balance of excitatory/inhibitory
> input.
> - Correlations between target identity and synapse count or sign.
> - If parallel rows are present and allowed, distinct-neighbor counts need
> not be preserved even though row-count degrees are preserved."

---

## 10. Exclusion rules and stopping rules

**Exclusion rules.** No source document states an exclusion rule for markets,
trials, seeds, or MBONs in the sense an OSF template asks for (criteria for
dropping a data point after collection). The closest analogues found are
readout-level exclusions of *neuron types from a sign table* (e.g., "MBON02 is
excluded from STRICT and GROUP because the table calls its activation valence
conflicted," READOUT), which are a modeling-assumption choice, not a
data-exclusion rule. **[NEEDS LUCA'S CONFIRMATION]:** no exclusion rule for
market-level data (e.g., markets with missing prices, degenerate liquidity, or
extreme outcomes) is written down anywhere in the eight source documents; if
one is intended for the historical-market stage, it does not yet exist in
writing.

**Stopping rules.** No document states a stopping rule in the sense of "stop
collecting/running once X is observed." What exists instead are:

- Pre-stated pass/fail *verdicts* that, once computed, are final and are not
  used to justify collecting more data before reporting (e.g., GRADED: "if it
  ever needs to change, write a new dated pre-statement rather than editing
  this one after seeing data").
- Operational restart/checkpoint mechanics (FIRST-LEARN Section 9, SYNTH-MARKET
  Section 7) describing how an *interrupted* run resumes, which is not a
  stopping rule for the experiment's sample size.
- SYNTH-MARKET's fixed strength sweep (0, 0.1, 0.2, 0.4, 0.8) with an explicit
  non-correction: "No correction for selecting the minimum across five
  ordered strengths is applied; this is a stated limitation" (Section 6) — the
  sweep runs to completion regardless of intermediate results, which is the
  closest thing to a stated stopping rule ("run all five, do not stop early").

**[NEEDS LUCA'S CONFIRMATION]:** no document states what happens if, e.g., the
first-learning test returns INCONCLUSIVE (whether it is rerun with more seeds,
abandoned, or reported as-is); FIRST-LEARN Section 4 only defines when
INCONCLUSIVE is reached, not what follows it.

---

## 11. List of every decision still open

Consolidated from MB-LEARN Section 8 (quoted verbatim per item, headings
retained) plus explicit open items found in the other seven documents. Items
already resolved since MB-LEARN was last revised are marked so.

1. **MBON valence labels — three key claims still need spot-checking.**
   Quoted (MB-LEARN, Section 8): "MBON11 approach (Aso et al. 2014b, *eLife*
   3:e04580, Fig. 2C); MBON21 avoidance (Rubin & Aso 2023, *eLife* RP90523,
   Fig. 3H–I); MBON02 attraction (Mohammad et al. 2024, *PLOS Biology*)."
2. **Graded encoding — resolved (ACCEPTED), but two things remain open**
   (MB-LEARN, Section 8): "(i) it is one seed and one group of cells at a
   uniform rate, so several groups driven at once are untested; (ii) the
   intensity bias it revealed."
3. **The intensity bias must be addressed before any market experiment**
   (MB-LEARN, Section 8; SYNTH-MARKET Section 4). Two remedies proposed,
   **neither chosen nor tested on the real model**. This is the specific open
   decision blocking Section 4.5 above from being launched.
4. **Which output-neuron instances enter the per-type mean is open** (MB-LEARN,
   Section 8): "whether that means both hemispheres... or only the left has
   not been decided."
5. **Reward normalization is unsettled** (MB-LEARN, Section 8): "the exact
   clip-and-normalize scheme for the teaching signal... is not decided."
6. **The accuracy-arm reward scale must be set before the preregistered
   experiment** (MB-LEARN, Section 8): "the placeholder is 0.25... No tuned
   value exists (**unverified**); the scale must be set from training data
   only and frozen before the preregistered experiment, never tuned on its
   results."
7. **The pace of the slow drift is unsettled** (MB-LEARN, Section 8): "whether
   one 'step' should instead mean one resolution, one trading day, or
   something else is open."
8. **The market data source is not chosen** (MB-LEARN, Section 8): "We have
   not selected which real prediction-market dataset to use." (Blocks stage 2
   of Section 3.)
9. **Speed on research hardware is an open question** (MB-LEARN, Section 8).
   Partially informed since: the fast-runner run log records build times of
   1.3–4.6 s (paid once) and simulate times of ~44–48 s per 5-trial run on the
   author's local machine (`repro/mushroom_body/run_log_fast_full.txt`), but
   this is local-machine, not "research hardware," and is not framed anywhere
   as answering the open question.
10. **The FlyWire v783 data license is unresolved** (MB-LEARN, Section 8):
    "at least one secondary source lists it as **CC BY-NC**... the true status
    is genuinely unclear... This must be resolved before any release."
11. **Degree-preserving shuffle scope not chosen** (SHUFFLE): mushroom-body-only
    vs. whole-network; "**Open decision for the project owner:**... Neither
    option is selected here."
12. **Intensity-bias mitigation for the synthetic-market run not chosen**
    (SYNTH-MARKET, Section 4): "Luca must choose one explicitly before any job
    is launched" — Option A (total-drive balancing) or Option B (innate-score
    subtraction).
13. **First-learning-test parameter placeholders not yet tuned/confirmed**
    (FIRST-LEARN, Section 6): "Every value in this table is a placeholder. It
    must be fixed before the run and must not be tuned on this test's
    results." (Listed here because the values are placeholders by the doc's
    own admission, not because anything is wrong with them; they are usable
    as-is but are explicitly not final validated constants.)
14. **Real historical-market baseline/backtest details** are entirely
    unspecified beyond MB-LEARN Section 3's naming of stage 2 — no dataset,
    date range, fee schedule, or market-selection criteria exist in any of the
    eight documents for that stage.
15. **A top-line, single-sentence hypothesis statement** is not written down
    verbatim anywhere in the eight documents (see Section 1 above);
    **[NEEDS LUCA'S CONFIRMATION]** whether one should be composed for the OSF
    record.
16. **Whether logistic regression / random / base-rate individually gate the
    Section 4.5 pass/fail decision** is not stated explicitly (see Section 4.6.4
    above).
17. **Concrete seed integers for the reduced-MB reproduction test and the
    degree-preserving shuffle** are not given in the source docs (see Section
    8 above).
18. **What follows an INCONCLUSIVE first-learning-test verdict** is not stated
    (see Section 10 above).

---

## 12. Cross-document consistency check

Every numeric and logical claim that appears in more than one of the eight
source documents was checked against every occurrence found. **No
outright contradiction was found between any two of the eight source
documents** (e.g., the 80% CIRCUIT threshold, the d_AA = 5.10 Hz noise floor,
the 15.30 Hz graded-test threshold, the "8 consistent discriminators" and
their identities, the MBON09/MBON08 disagreement with behavioral labels, and
the intensity-bias numbers at 150 Hz all agree, word-for-word or number-for-
number, everywhere they are repeated).

**One real inconsistency was found, between the design documents and the
project's actual state (not between two design documents):**

- **FIRST-LEARN, Section 7,** states: "This estimate, and the whole test,
  depends on the fast runner, whose equivalence test against the existing
  path has not been run ([`fast-runner.md`](fast-runner.md), section 4)...
  **Run the fast-runner equivalence test first.**"
- **SYNTH-MARKET, Section 7,** states: "The fast runner equivalence test and a
  real `run_cue_rates` execution remain prerequisites."
- Both statements are now stale: the fast-runner equivalence test was run and
  accepted (git commit `6a00cdd`; `repro/mushroom_body/run_log_fast_full.txt`;
  Section 4.3 above), but **neither FIRST-LEARN nor SYNTH-MARKET, nor
  FAST-RUNNER itself, was updated to record that.** This does not change any
  pass/fail criterion in either document, but a reader of FIRST-LEARN or
  SYNTH-MARKET alone would incorrectly conclude the first learning test is
  still blocked. **[NEEDS LUCA'S CONFIRMATION]:** whether to append a dated
  "Results" note to `fast-runner.md` and a short update to FIRST-LEARN
  Section 7 / SYNTH-MARKET Section 7 recording that this prerequisite is now
  satisfied — this preregistration does not edit those files itself (the task
  restricted this pass to `docs/preregistration.md` and
  `docs/paper/methods-draft.md`, and the "no simulations, no commits" rule
  applies to this session).

No other contradiction was found. Two apparent tensions were checked closely
and found to be internally consistent on careful reading, noted here so they
are not mistaken for contradictions later:

- READOUT's "Dominant-family threshold" table describes each threshold row
  (70/80/90%) **relative to the historical any-connection rule**, not relative
  to each other; read that way, the 90%-row's "MBON04 remains zero" and
  "MBON10... becomes zero" are consistent with MBON04 and MBON10 being
  *nonzero* at 80% (as FIRST-LEARN's `circuit_90` variant description says).
- FIRST-LEARN's own noise threshold (`σ`, computed from `D_pre(s)` scores) and
  SEPARABILITY's `d_AA` (a vector distance, not a score) are two different
  noise measurements on two different quantities; FIRST-LEARN says so
  explicitly ("It is therefore independent of the earlier `d_AA = 5.10 Hz`").
  They should not be conflated even though both use a "3×" margin.

---

## 13. Status summary at time of writing

| Experiment | Status |
|---|---|
| Graded-rate encoding test (4.1) | **Run. Verdict: ACCEPTED.** |
| MBON-separability / noise-floor test (4.2) | **Run. Verdict: CONFIRMED** (fine cell); marginal at the cheap cell. |
| Fast-runner equivalence test (4.3) | **Run. Verdict: ACCEPTED** (recorded only in git/run log, not in the design doc). |
| First learning test (4.4) | **Not run.** Blocking dependency (fast-runner equivalence) now satisfied. |
| Synthetic-market experiment (4.5) | **Not run.** Blocked on an explicit open decision (intensity-bias mitigation choice, item 12 above). |
| Learning-off control (4.6.1) | Not run standalone; embedded as a condition/arm of 4.4 and 4.5. |
| Degree-preserving shuffled connectome (4.6.2) | Implementation and synthetic-graph tests complete; real shuffle not generated; scope not chosen (item 11 above). |
| Reduced mushroom-body model (4.6.3) | **Protocol-fidelity unit test run and passed** against an unverified, invented tolerance; not a validated numerical match to the source paper; market-scale performance untested. |
| Logistic regression / market price / random / base-rate (4.6.4) | Implemented as baselines; not yet run against real or synthetic markets outside the pipeline's own fake-simulator tests. |
