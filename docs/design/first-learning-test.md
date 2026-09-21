# First learning test: does the circuit learn that cue A is rewarded and cue B is not?

**Status: pre-statement, written 2026-09-21 BEFORE any code and BEFORE any run.**
Nothing described here has been run. The criteria below are fixed. If one needs to
change, write a new dated revision at the bottom *before* running, never after
seeing data. Results go in a new section at the very end, without editing anything
above it.

**Revision notice (both changes made before any run; see "Revision history"):** the
reward mechanism was approved as described in Section 2, and control (c), rewarding
both cues equally, was demoted from a pass/fail gate to a reported diagnostic
(Section 5).

Terms (Kenyon cell (KC), MBON, CIRCUIT readout, per-type mean, compartment, PAM,
PPL1) are explained in [`mb-learning-interface.md`](mb-learning-interface.md) and
[`readout-and-plasticity-options.md`](readout-and-plasticity-options.md).

---

## 1. The question

The Shiu et al. model has no learning of its own. We added a learning rule
([`mb-learning-interface.md`](mb-learning-interface.md), 4d): when a teaching
signal arrives, weaken the connections from recently active KCs onto the output
neurons (MBONs) in the compartment of the dopamine family that fired. This test
asks the simplest question that rule must answer before anything else is attempted.
**If one group of KCs (cue A) is repeatedly followed by reward and another (cue B)
is not, does the circuit's readout come to prefer A over B, by more than the
run-to-run noise?** It also asks whether that happens *for the right reason*
(the controls in Section 5).

No market, price or encoder is involved. It is a pure cue-reward association test.

## 2. What "delivering reward" means in this test — read this first

**The simulated brain contains no dopamine-dependent plasticity.** Stimulating PAM
neurons inside the Brian2 simulation cannot change any synaptic weight; the only
thing it would do is drive their fast (and, for DAN→KC synapses, already suspect)
synaptic outputs. The weight change is produced entirely by *our* rule, computed
outside the simulator on the KC→MBON weight matrix and then written back into the
network before the next presentation.

**Decided (approved 2026-09-21):** dopamine is represented **abstractly, as a
teaching signal.** "Deliver reward after A" means: apply our plasticity rule with the
PAM (reward-family) teaching signal, using the KC activity pattern recorded while
cue A was presented, **to the KC→MBON weights of the MBONs in the compartments that
dopamine family innervates.** The biological grounding is that compartment map
(inferred from the connectome, **unverified** at compartment level), not any
simulated dopamine neuron. **No dopamine neurons are stimulated in the network, and
no dopamine release or dopamine-neuron activity is simulated during learning.**

The strength of the signal is the normalised reward magnitude (Section 6). The
reward module also converts it to a "stimulation rate" (magnitude ×
`dopamine_max_rate_hz`); that number is recorded in the results but **the network
never sees it.**

- **Unverified: the recorded PAM rate is unanchored.** Dopamine stimulation has never
  been simulated in this project, so we do not know what rate would correspond to any
  given teaching strength, or whether directly driven PAM neurons behave sensibly in
  this model. Nothing in this test depends on that number; it is recorded only so a
  later test that *does* stimulate dopamine neurons can be compared with this one.

## 3. Protocol (fixed)

**Cues.** Two disjoint sets of 100 left-hemisphere KCs, **set A and set B**, chosen
by `--kc-set-seed 20260316` (`check_mb_response.select_disjoint_kc_sets`, the same
two sets as every earlier cue experiment). A presentation drives every KC of the
set at **150 Hz**: the only KC-direct rate simulated so far, and the one at which
cue separability was established. The graded-rate test is not needed here because
the rate never varies.

**Simulator.** The fast runner's per-neuron-rate path
(`repro/mushroom_body/fast_runner.py`, `run_cue_rates`): the network is built once;
each presentation resets neuron state but keeps the current KC→MBON weights.

**Weights that learn.** Only KC→MBON synapses. The learning module holds a dense
matrix (every KC × every MBON, zero where no synapse exists) whose entries are
exactly the network's KC→MBON weights. After each teaching event the new values
are written back into those synapses; nothing else in the network changes.

**Compartments.** Family-level map from direct dopamine→MBON wiring at the same
80% dominant-family threshold as the readout: MBONs that are PAM-dominant are in
the PAM compartment, PPL1-dominant ones in the PPL1 compartment, all others in
none (never plastic). **Unverified** at compartment level (design docs).

**Readout.** CIRCUIT score, `circuit_80` table, **per-type mean** (`type_mean`),
over all 96 MBON instances in both hemispheres with silent instances at 0 Hz: the
same readout as the graded-rate test. Rewarding A should raise A's score. Reward is
PAM, which depresses cue-A synapses onto PAM-compartment MBONs. CIRCUIT calls those
MBONs avoidance-like, so A's avoidance-like activity falls and its score rises.
**The rewarded direction of (score_A − score_B) is therefore positive.** This rests
on KC→MBON synapses being excitatory in the model, as the model's sign assignment
makes them; that sign is itself **unverified** biologically.

**Stages, for each condition in Section 5:**

1. **Pre-training test (weights = connectome).** For each of the 5 test seeds
   `20260317, 20260318, 20260319, 20260320, 20260321`: present A, then B, each for
   **1000 ms × 5 trials** at that seed, and compute score_A and score_B. These are
   the seeds and the cell of the noise-floor experiment. Because the weights are
   identical in every condition before training, this stage is run **once** and
   shared by all conditions.
2. **Training.** **N** presentations (placeholder N = 40), half A and half B, in a
   fixed seeded order that is alternating in pairs. For each consecutive pair,
   which cue goes first is drawn from `numpy.random.default_rng(20260402)`, so
   neither cue appears more than twice in a row. Presentation *k* uses simulation
   seed `20260500 + k` and lasts **1000 ms × 1 trial**. After each presentation:
   the KCs' measured firing rates during it are the "recently active" pattern; the
   condition's teaching signal for that cue (if any) is applied through the
   plasticity rule; then the rule's slow drift toward the connectome weights takes
   `drift_steps_per_resolution` steps (also after presentations with no teaching
   signal, exactly as for a resolved market with nothing to teach). **The cue order
   and every seed are identical across conditions**; only the teaching signal
   differs.
3. **Post-training test (plasticity frozen).** Identical to stage 1 (same seeds,
   same settings), with the trained weights and no further weight change.

## 4. Primary measure and the noise measurement (fixed)

For a set of weights and test seed *s*, let `D(s) = score_A(s) − score_B(s)`.

- **Pre-training difference:** `D_pre(s)` for the 5 test seeds; `m_pre` = its mean.
- **Run-to-run noise of the difference:** `σ` = the **sample standard deviation
  (ddof = 1) of `D_pre(s)` across the 5 test seeds**. It is the typical
  seed-to-seed spread of *one* A−B measurement under unchanged weights, measured
  on the same simulator path, settings and readout as the post-training test.
  It is therefore independent of the earlier `d_AA = 5.10 Hz`, which was measured
  on a different code path and as a vector distance, not a score.
- **Post-training difference for condition c:** `D_c(s)` at the same 5 seeds;
  `m_c` = its mean.
- **Primary measure:** `Δ_c = m_c − m_pre`, the change in the mean A−B difference.
  (Per-seed paired changes `D_c(s) − D_pre(s)` are reported as a diagnostic.)
- **Threshold:** `T = 3σ`. Because Δ compares two means of 5, its own noise is about
  `σ·√(2/5) ≈ 0.63σ`. A 3σ threshold is therefore about 4.7 standard errors:
  deliberately conservative.
- If `σ` is zero or not finite, the noise measurement has failed and the verdict is
  **INCONCLUSIVE**. A zero spread across seeds would mean the seeds are not changing
  the simulation, not that noise is absent.

## 5. Conditions and pre-stated criteria (fixed)

All five conditions use the identical pre-training test (shared), cue order, seeds
and plasticity parameters. They differ only in the teaching signal. **Four of them
are gates** (they decide the verdict); **control (c) is a reported diagnostic.**

| Condition | Teaching signal after A | after B | Role | Pre-stated criterion |
|---|---|---|---|---|
| **main** — reward A | PAM | none | gate | `Δ ≥ +T` (moves in the rewarded direction by at least 3σ) |
| **(a) plasticity off** | none, rule disabled | none, rule disabled | gate | `|Δ| < T` |
| **(b) reward B** | none | PAM | gate | `Δ ≤ −T` (must move the OTHER way): the clean specificity test |
| **(c) reward both** | PAM | PAM | **reported diagnostic only** | none: reported, never affects the verdict |
| **(d) punish A only** ("everything smells bad") | PPL1 | none | gate | cue B's readout unchanged: `|mean score_B post − mean score_B pre| < 3σ_B`, with `σ_B` the sample SD (ddof = 1) of pre-training `score_B` across the 5 test seeds |

Notes:
- (a) disables the rule completely, including drift, so its weights stay exactly at
  the connectome values. With identical seeds its post-training test should
  reproduce the pre-training test (Δ = 0) if the simulator is deterministic for a
  given seed and resets cleanly. Any nonzero Δ in (a) points to leaked state or
  non-determinism in the simulator path, and is reported as such.
- (d) is the check against the failure a prior project reportedly showed, where
  punishing one thing made *everything* aversive (reportedly; unverified by us).
  The rule only touches rows of KCs that were active, so cue B's KC→MBON weights are
  untouched by construction. This checks that the *network* also leaves B's output
  alone. In (d), (score_A − score_B) is expected to move negative; that is reported
  as a diagnostic, not a criterion.
- In the main condition, the change in cue B's own score is also reported (a
  diagnostic of the same "smells bad" kind).
- **Why (c) is not a gate (demoted before any run).** Cues A and B drive different
  MBON populations: their readout vectors differ by about 79 Hz, concentrated in a
  few MBONs ([`mbon-separability.md`](mbon-separability.md)). Rewarding both cues
  equally therefore changes their scores *unequally* even under perfectly
  cue-specific learning, so a non-zero result in (c) cannot be read as a failure of
  specificity. Control (b), reward B instead of A, is the clean specificity test.
  (c) is still simulated, and its result is kept in the output: its change in
  A−B, that change in units of σ, whether it exceeds 3σ, and an **additive
  prediction** — if learning is cue-specific and the readout roughly additive,
  rewarding both should change A−B by about `Δ_main + Δ_(b)`, and the residual from
  that prediction is reported. The prediction and residual are for interpretation
  only; they carry no threshold.

**Verdict (exactly one):**

- **INCONCLUSIVE** — the noise measurement failed (`σ` or `σ_B` is zero or not
  finite), or the result of a gating condition (main, (a), (b), (d)) is missing.
- **NOT DEMONSTRATED** — the main condition fails its criterion, including a change
  of the right size in the *wrong* direction.
- **CONFOUNDED** — the main condition passes but at least one of the gating controls
  (a), (b), (d) fails. The failing controls are named. A movement that also happens
  with plasticity off, does not reverse when the reward moves to B, or spills onto an
  untrained cue is not evidence of a cue-specific association. **Control (c) alone
  can never produce this verdict.**
- **LEARNING DEMONSTRATED** — the main condition and the three gating controls pass.

## 6. Parameters: explicit placeholders, fixed before the run

**Every value in this table is a placeholder. It must be fixed before the run and
must not be tuned on this test's results.** A different set of values is a
different experiment: the results directory is keyed by a hash of the full
configuration, so a changed value cannot be silently mixed with existing results.

| Parameter | Placeholder | Meaning |
|---|---|---|
| N (training presentations) | 40 (20 A, 20 B) | Must be even. |
| training presentation | 1000 ms × 1 trial | Only KC rates (eligibility) and a learning-curve score are taken from it. |
| test presentation | 1000 ms × 5 trials | Matches the fine noise-floor cell. |
| cue rate | 150 Hz | All KCs of the presented set. |
| reward strength | 1.0 | Normalised reward (the clipped maximum), giving PAM (or PPL1 for punishment) teaching strength 1.0 via the reward module. |
| `dopamine_max_rate_hz` | 150 | Recorded PAM/PPL1 stimulation rate = strength × this. **Unanchored; not used in the simulation.** |
| `learning_rate` | 0.1 | Fraction of the gap to the floor closed per unit gate. |
| `floor_fraction` | 0.1 | Weight magnitude never below 10% of its connectome value. |
| `drift_rate` | 0.01 | Fraction of the gap back to the connectome value closed per drift step. |
| `drift_steps_per_resolution` | 1 | Drift steps after every presentation (with or without teaching). |
| `kc_active_threshold_hz` | 1.0 | KCs at or below this rate are not eligible. |
| `kc_rate_ref_hz` | 150 | KC rate at which eligibility saturates. |
| training-order seed | 20260402 | |
| training simulation seeds | 20260500 + k | k = 0 … N−1 |
| test seeds | 20260317 – 20260321 | |

All plasticity values are the package defaults in `flyshi_research.learning.params`,
recorded verbatim in the results.

## 7. Cost (estimate, not measured)

Simulation runs = 10 (shared pre-training test: 5 seeds × 2 cues) + 5 conditions ×
(N training + 10 post-training test). **At N = 40 this is 10 + 5 × 50 = 260 runs.**
Of these, 60 are 5-trial test runs and 200 are 1-trial training runs: 500 simulated
trial-seconds in total, plus one network build per process. **Wall-clock time is
unknown.** Timings on this 8-GB machine are unusable
([`speed-calibration.md`](speed-calibration.md)).

**This estimate, and the whole test, depends on the fast runner, whose equivalence
test against the existing path has not been run**
([`fast-runner.md`](fast-runner.md), section 4). In addition, `run_cue_rates` has
never executed a real `net.run` (only its no-simulation self-test). The criteria
above do not rely on the fast runner matching the old path, because the noise is
measured within this test on the same path. But a broken fast path (for example,
state leaking between presentations) would invalidate everything. Control (a)
would expose some but not all such problems. (One relevant fact in the other
direction: in the graded-rate test, the 150 Hz run reproduced the earlier set-A run at
the same seed to 0.00 Hz, so the *existing* path is deterministic per seed. There is
no such evidence yet for the fast path.) **Run the fast-runner equivalence test
first.** Note that 50 of the 260 runs are control (c), which is now only a reported
diagnostic; dropping it would reduce the total to 210.

## 8. Other limitations, stated in advance

- **Five seeds** give a rough estimate of σ; the 3σ threshold is conservative
  partly for that reason.
- **One pair of cue sets, one cue rate, one N.** A pass shows the mechanism can
  work for this pair under these placeholders, not that it works generally or for
  market encodings.
- **The learning curve** (score of each training presentation, 1 trial each) is
  recorded for interpretation only; it is noisier than the test measurements and is
  not part of any criterion.
- **Weight-change summaries** (how much the A and B rows changed, per compartment)
  are recorded for interpretation only.
- **The intensity bias found by the graded-rate test does not affect this test.** In
  the graded-rate test (ACCEPTED, 2026-09-21) the CIRCUIT score fell steeply as one
  cue's drive rose (see [`graded-encoding.md`](graded-encoding.md), Results, and
  [`mb-learning-interface.md`](mb-learning-interface.md), 4b). Here **both cues are
  driven at the same constant 150 Hz**, so neither has an intensity advantage, and
  the primary measure is a *change* in A−B from before to after training, in which
  any fixed offset (from intensity or from the two cues' different composition)
  cancels. **What this test therefore does not show:** whether learning works when
  the drive varies, as it will for market features. The market experiments must
  address the bias separately.
- **Drift makes the conditions slightly asymmetric.** A and B are taught at
  different positions in the fixed order, so drift acts on their changes for
  different lengths of time; control (b) is a near-mirror of the main
  condition, not an exact one.

## 9. How to run it (nothing has been run)

```bash
# plan and run-count estimate only; no simulation, no network build
.venv-shiu/bin/python repro/mushroom_body/run_first_learning_test.py --dry-run

# the full pre-stated test (Brian2 simulations; on macOS use caffeinate -i)
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/run_first_learning_test.py
```

- **Restartable.** Each stage writes its own small JSON on completion. An
  interrupted training stage resumes from a checkpoint written after every
  presentation. Presentation seeds depend only on the presentation index, so a
  resumed run is identical to an uninterrupted one (assuming the simulator is
  deterministic per seed, which control (a) checks). The checkpoint is deleted when
  the stage completes.
- **Compact output** in `repro/mushroom_body/results/first_learning_<config hash>/`.
  Total is well under 1 MB: scores, 96-value MBON vectors, per-trial learning curve,
  weight summaries, verdict.
- `--smoke` runs a tiny version (N = 2, two test seeds, 100 ms) to check the
  pipeline end-to-end. Its verdict is labelled **NOT THE PRE-STATED TEST**, and it
  writes to a different directory.

The experiment logic lives in `src/flyshi_research/learning/first_learning.py` (pure
numpy, simulator passed in). `tests/learning/test_first_learning.py` exercises it
on fake simulators: one where learning should be detected, and several where it
must not be. The tests never call the real simulator.

---

## Revision history

- **2026-09-21.** First version, written before any code or run.
- **2026-09-21, same day, before any run.** Added the two limitations above on
  control (c) and drift asymmetry, found while testing the code on fake simulators.
  No criterion changed.
- **2026-09-21, before any run: reward mechanism approved.** Section 2 now records
  the decision: dopamine is represented abstractly as a teaching signal applied by
  our rule in the compartments each dopamine family innervates; no dopamine neurons
  are stimulated in the network, and no dopamine release or neuron activity is
  simulated. (This describes what the code already did; it is now a decision.)
- **2026-09-21, before any run: control (c) demoted.** Control (c), reward both cues
  equally, changed from a pass/fail gate (`|Δ| < T`) to a **reported diagnostic**
  with no threshold, and CONFOUNDED can no longer be triggered by (c) alone.
  Rationale (Section 5): cues A and B drive MBON populations that differ by about
  79 Hz, so equal reward changes their scores unequally even under perfectly
  cue-specific learning; control (b) is the clean specificity test. The verdict now
  depends on the main condition and gates (a), (b), (d). The additive-prediction
  diagnostic was added with it. Nothing else changed; no result existed.

---

## Results

*None yet. Append a new dated section here after the run; do not edit anything
above.*
