# Mushroom-body learning interface: design record and preregistration

**Status: design record, written before implementation and revised since.** The
"pure logic" parts (the input encoder, the readout, the reward signal and the
learning rule) now exist as tested code that works on plain arrays of numbers.
**None of it has been run against the brain model**, and one thing it depends on
— whether the circuit's output follows *how hard* a cell group is driven — has
never been tested (Section 8; the test is written down in advance in
[`graded-encoding.md`](graded-encoding.md)). This document says what we decided,
why, what is still unknown, and what we will not claim. It is meant to be
revised; see "How to give feedback" at the end. Revision history: Section 13.

A note on who this is for: this document is written to be read by people with
no background in neuroscience, machine learning, or finance. Every special term
is explained the first time it appears. If you hit a word that is not
explained, that is a bug in this document — please flag it.

---

## 1. What this project is

We take a computer simulation of part of a fruit fly's brain — built by other
scientists from a detailed map of real fly brain wiring — and we test whether a
small, well-understood piece of it can help make better *probability forecasts*
about yes/no questions, of the kind traded on "prediction markets" (places
where people bet on whether some future event will happen). We are not claiming
the fly brain is good at finance. We are asking a narrow, testable question:
when we add a simple learning mechanism of our own to this brain circuit, does
it forecast yes/no outcomes better than ordinary, conventional methods — and if
so, is that because of the brain-derived structure, or just because we gave it
more knobs to tune? The whole project is built around controls and honesty
about what we can and cannot conclude.

---

## 2. What we are actually using

We use the brain model published by **Shiu and colleagues in 2024** (in the
journal *Nature*, volume 634, pages 210–219;
[doi:10.1038/s41586-024-07763-9](https://doi.org/10.1038/s41586-024-07763-9)).

A few terms, defined:

- **Connectome:** a wiring diagram of a brain — which neuron connects to which,
  measured from real tissue. This one comes from the *FlyWire* project, which
  reconstructed a full adult fruit fly brain from electron-microscope images.
- **Neuron:** a single brain cell that sends electrical pulses.
- **Spike:** one such pulse. Neurons communicate by spikes.
- **Spiking simulation:** a computer program that mimics each neuron producing
  spikes over time, based on the wiring diagram. The Shiu model is one of
  these. It contains roughly 130,000 neurons.
- **Firing rate:** how many spikes a neuron produces per second, measured in
  **hertz (Hz)** — 150 Hz means 150 spikes per second. Firing rate is how we
  will represent "how strong" a signal is.

**The single most important fact about this model: it does not learn anything on
its own.** It has fixed wiring and fixed connection strengths taken from the
real fly. Nothing about it changes with experience. There is no memory, no
training, no reward built in. **Any learning in this project is ours, added on
top. It is not part of the Shiu model, and we will never describe it as
theirs.**

The model's wiring exists in two published versions, and we use both for
different purposes:

- **Version 630** ("v630"): the wiring the original authors shipped with their
  code. We used it to confirm we could reproduce their published result (see
  Section 3).
- **Version 783** ("v783"): a later, revised version of the same wiring. We
  used it for all of our own mushroom-body analysis, because the neuron labels
  we needed (which cell is which type) are published against v783.

---

## 3. What we found before designing this

All of the findings below come from our own reproduction work. The full detail,
with exact numbers and the commands that produced them, is in:

- [`docs/reproduction/shiu2024.md`](../reproduction/shiu2024.md) — installing
  the model and reproducing the authors' published result.
- [`docs/reproduction/mushroom_body_check.md`](../reproduction/mushroom_body_check.md)
  — testing whether we can get clean signals in and out of the memory circuit.
- [`docs/design/speed-calibration.md`](speed-calibration.md) — measuring how
  short we can make each simulation run.

### 3a. The model reproduces the published result

The Shiu paper's headline demonstration is a "sugar response": stimulate the
fly's sugar-taste neurons, and a specific downstream motor neuron (called MN9,
which drives the mouthparts during feeding) responds more strongly on one side
than the other. We reproduced this qualitatively: the correct side-to-side
ordering appeared, and the top three responding neurons matched the authors'
own output in identity and order. Our absolute firing rates ran about 10% lower
than theirs, for reasons we could not fully explain; the paper itself warns
that exact firing-rate numbers are not expected to be reliable. One likely
cause: the upstream code's default stimulation rate is 150 Hz, but the
authors' notebook prose states 200 Hz, so their bundled example output may
have been produced at the higher rate — which would explain rates that run
consistently above ours (**unverified**). We treat this as a successful
qualitative reproduction, not an exact numerical match.

### 3b. Sending information in through the smell pathway FAILS

To understand the rest of this section, three more pieces of the fly's smell
system:

- **Antennal lobe:** the first brain region that processes smell. Think of it
  as the entrance hall.
- **Projection neuron (PN):** a neuron that carries smell signals *out* of the
  antennal lobe toward the memory circuit. Each responds to a particular smell
  channel (a "glomerulus" — one cluster of the entrance hall).
- **Kenyon cell (KC):** a neuron in the **mushroom body**, which is the fly's
  learning-and-memory center. There are about 5,000 of them. In a healthy fly,
  any one smell is expected to activate only a small, distinctive handful of
  Kenyon cells — this is called **sparse coding**, and it is what makes
  different smells easy to tell apart and easy to learn about.

We tried to feed information into the model by stimulating projection neurons —
the natural "smell input" — and checking whether different smells produced
different, sparse Kenyon-cell patterns. **They did not.** A single smell
activated about **65% of all Kenyon cells** (we wanted something closer to
5–10%). Worse, two different smells produced almost identical Kenyon-cell
patterns: their overlap was **0.99 on a 0-to-1 scale** (this overlap measure is
the *Jaccard index* — the fraction of active cells two patterns share; 0 means
no shared cells, 1 means identical). Two smells that should look different
looked the same. This is the opposite of sparse coding.

We traced where this "everything lights up" spread begins. It starts in the
antennal lobe. The wiring map assigns each connection a **sign** — excitatory
(pushes the target to fire) or inhibitory (pushes it to stay quiet). In this
data, the antennal lobe's local neurons (the ones that normally keep activity in
check) come out **about 68% excitatory** onto projection neurons, rather than
mostly inhibitory. So instead of damping activity, the entrance hall amplifies
it, and the amplification floods the memory circuit. (Full sign audit with exact
counts is in the mushroom-body reproduction document.)

**A caveat we must state loudly and keep stating:** we stimulated projection
neurons *directly* at 150 Hz. That is **not** how a real smell arrives. In a
real fly, odor molecules hit *receptor neurons* first, which then drive the
projection neurons more gently and indirectly. We have not yet tested
receptor-neuron input at lower, more realistic rates. **Until we do, we do not
claim this model "fails at smell" in general.** We claim only this: *the
specific, artificial way we tried to inject information — strong direct
projection-neuron drive — does not produce clean, separable patterns in this
model.* Testing gentler, more realistic smell input is planned future work.

### 3c. Sending information directly into Kenyon cells WORKS

Because the smell entrance was unusable, we tried injecting signal one step
later — directly into the Kenyon cells, skipping the antennal lobe. We picked
two separate groups of 100 Kenyon cells (chosen by a fixed random seed, so the
choice is reproducible and the two groups never overlap) and stimulated one
group for "cue A" and the other for "cue B."

This worked cleanly:

- **Zero spread.** Only the cells we stimulated fired. The fraction of *other*
  Kenyon cells that lit up was 0%.
- **Completely separate patterns.** Cue A and cue B shared no active Kenyon
  cells (overlap 0.0).
- **The output neurons responded.** 33 mushroom-body output neurons (defined
  next) produced activity, so a readable signal comes out the other end.

- **MBON (mushroom-body output neuron):** a neuron that reads out the Kenyon
  cells and carries the mushroom body's "verdict" onward. There are 96 of them
  in this model. They are where we will read the circuit's answer.

So: the front door (smell) is broken in our test setup, but the room behind it
(the Kenyon cells and their outputs) behaves well when we step inside directly.
That single finding is what makes the rest of this design possible.

### 3d. Calibration: short, cheap runs separate cues as well as long ones

We swept the two settings that cost the most simulation time:

- **Duration:** how long each simulated run lasts (1000, 500, 200, or 100
  milliseconds).
- **Trials:** how many times we repeat each run and average (5, 2, or 1).

For each combination we measured a **separation score**: how different cue A's
output pattern is from cue B's, on a 0-to-1 scale where higher means more
distinguishable (defined precisely in Section 4b). Result: **every combination
we tried kept the two cues separable, and the cheapest setting — 100
milliseconds, 1 trial — separated them at least as well as, and by our measure
slightly better than, the most expensive setting (1000 ms, 5 trials).** Spread
stayed at 0% everywhere. This means we can run the study at the cheap setting.

One honest limitation: we could **not** use the wall-clock timings from these
runs for planning. This work runs on an 8-gigabyte Mac, and the measured run
times were dominated by whatever else the computer was doing at the time — a
100-millisecond run sometimes took *longer* than a 1000-millisecond run, which
is impossible if timing reflected real work. So we trust the *separation*
results but treat the *timing* results as unusable. Speed on real research
hardware is an open question (Section 8).

#### Input separation is excellent; readout separation is small — flagged as our biggest risk, and since tested and resolved

It is important not to blur two different "separations" here, because one looked
great and the other looked worrying:

- **Input side (the Kenyon cells):** the two cues drive **completely separate**
  Kenyon-cell patterns. They share *no* active cells — overlap **0.0**. This is
  as good as it gets.
- **Output side (the MBONs — the thing we actually read):** the two cues'
  output patterns differ by a cosine distance of only **about 0.05** on the
  0-to-1 scale (higher means more different). That is **small**.

In plain terms: the two cues go *in* looking totally distinct, but by the time
the signal reaches the neurons we read the answer from, the two responses look
**nearly identical** by that one summary number. We read the output, not the
input — so it is the small number that seemed to govern whether this can work.

**We originally flagged this gap as the single biggest technical risk in the
project:** if a readout difference of about 0.05 were too small for any learning
rule to build on, the whole approach could fail regardless of how clean the
input is. We did not, at first, know whether it was enough.

**Update — this risk has now been tested and resolved (see
[`docs/design/mbon-separability.md`](mbon-separability.md)).** The "0.05" turned
out to be misleading: cosine distance is *normalized* by the large activity the
two cues share in common, so it hides a difference that is actually large in
absolute terms (tens of Hz) and concentrated in a handful of MBONs. We measured
the run-to-run noise directly (repeating the same cue under five different
simulation seeds) and found that, at 1000 ms / 5 trials, the cue-A-vs-cue-B
readout difference is **15.6× the same-cue noise**, with **all 8** consistently
discriminating MBONs passing an individual per-neuron check. The two cues are
reliably distinguishable at the readout. The residual caveats now live in
**Section 8**; this is no longer an existential risk.

---

## 4. The four design decisions

Each decision below is stated as: **what we decided**, **why**, **what could go
wrong**, and **what control or ablation test checks it**. An **ablation** is a
test where we deliberately remove or break one part of the system to see whether
it actually mattered — like unplugging one wire to find out if the light needed
it.

### 4a. INPUT — market information enters directly at the Kenyon-cell layer

**What we decided.** We skip the smell pathway entirely and inject market
information straight into the Kenyon cells, because that is the part that works
(Section 3c). Each piece of market information — each **feature** — gets its own
fixed, pre-assigned, non-overlapping pool of Kenyon cells. The planned features:

- **Price:** the market's current quoted probability that the answer is "yes."
- **Recent price change:** how the price has moved lately.
- **Time to resolution:** how long until the question is settled.
- **Liquidity:** roughly, how much trading activity/depth the market has.
- **Signal feature (synthetic markets only):** in our made-up test markets, an
  extra input that carries known information, used to measure how much signal
  the system needs (see Section 7).

The **value** of each feature is turned into a **firing rate**: a bigger value
makes that feature's pool of Kenyon cells fire faster. The pools are chosen once
with a fixed random seed, so they never change and never overlap.

**How the "NO" framing treats each feature (decided 2026-09-21).** Section 4b
presents every market twice: as "YES at price *p*" and as "NO at price 1 − *p*".
For the NO presentation, a feature's value is **mirrored** — replaced by its
opposite within its allowed range, so a price of 0.7 becomes 0.3 — if it is
*evidence for or against YES*, and left alone if it *means the same thing for
both framings*:

| Feature | Under NO | Why |
|---|---|---|
| Price | mirrored (*p* → 1 − *p*) | It is the market's probability of YES; seen from the NO side the same fact reads 1 − *p*. |
| Recent price change | mirrored (up ↔ down) | A rising price is good news for YES and bad news for NO. |
| Signal (synthetic markets only) | mirrored | It is built to carry evidence about the outcome, so it points the opposite way from the NO side. |
| Time to resolution | not mirrored | Days left is a fact about the market, not about a side. |
| Liquidity | not mirrored | How thin the market is is likewise the same from either side. |

The rationale: "YES at *p*" and "NO at 1 − *p*" are the *same* bet seen from two
sides, so evidence must flip and market facts must not. If we mirrored the
side-neutral features we would invent a difference between the two framings that
the market does not contain; if we failed to mirror the evidence features, both
framings would show the circuit the same evidence and it could not tell them
apart. A consequence we want: at price 0.5 with a flat price history and a
neutral signal, the two framings are identical, the two scores tie, and the
system abstains. **Unverified:** only the price rule (*p* → 1 − *p*) was fixed
before the code was written; mirroring recent change and the signal is our
extension of it, and we have no evidence yet that the circuit responds to the
mirrored inputs usefully. The signal feature also assumes the synthetic signal
points toward YES; if it is defined differently it must be re-examined.

**Why.** Direct Kenyon-cell stimulation is the only input route we have shown to
be clean (no spread, fully separable). Giving each feature its own dedicated,
non-overlapping pool means the circuit can, in principle, tell the features
apart. Using a fixed seed makes the whole thing reproducible.

**What could go wrong.** *Graded rates are untested.* Every simulation so far
drove cells at one rate (150 Hz), so we know the circuit tells *which* cells were
driven, but not whether its output changes in an orderly way with *how hard* they
are driven. Encoding a value as a rate depends on exactly that. The test, with its
acceptance criterion fixed in advance, is in
[`graded-encoding.md`](graded-encoding.md). **It has since been run (2026-09-21)
and the verdict is ACCEPTED**: with one group of 100 cells driven at 30, 60, 90, 120
and 150 Hz, the CIRCUIT readout score was strictly monotonic — but *decreasing*:
−9.6, −18.5, −33.9, −51.9, −66.8 — and the difference between the output-neuron
patterns at 30 and 150 Hz was 222.9 Hz against a threshold of 15.3 Hz (three times
the same-cue noise floor). So the encoding by rate works in the sense that the
readout follows the rate. (The other two possible verdicts were *usable range*, a
monotonic stretch shorter than the whole range, and *fail*.) Caveats: one seed, one
group of cells at a uniform rate; several groups driven at once have not been
tested. **The decreasing direction reveals a bias that matters for Option B: see
4b, problem 4.**

**Encoder rate bounds (decided 2026-09-21).** The encoder maps a feature's lowest
value to a minimum firing rate and its highest to a maximum. **After the graded
test, that minimum and maximum must equal the validated range** — all five tested
rates (30 to 150 Hz) if accepted, or the chosen stretch if a usable range. The test
was accepted, so the bounds are **30 to 150 Hz**, which is what the encoder uses
(the minimum was changed from 0 to 30 Hz so it cannot emit a rate below anything
tested; one consequence is that no feature's group of cells is ever silent, even at
that feature's lowest value). The code checks this
(`encoder_params_for`, `require_encoder_matches` in `graded_check.py`; the check
passes with the default bounds). The range is validated for one group of cells only.

Real Kenyon cells do not normally receive input this
way, so this is an engineered interface, not a biological claim — we are using
the circuit as a substrate, not modeling how a fly actually senses markets.
Also, hand-assigning one pool per feature builds in a structure we chose; if the
system works, some of the credit may belong to our clean encoding rather than to
anything fly-derived.

**What tests it.** The **shuffled-connectome control** (Section 6) keeps our
exact input encoding but scrambles the fly wiring while preserving each neuron's
number of connections. If performance survives shuffling, the fly structure was
not the source of the benefit — our encoding was. Comparing against **logistic
regression** on the same features (Section 6) checks whether the neural circuit
beats a plain statistical model reading identical inputs.

### 4b. READOUT — "Option B": two separate stimuli per decision

**What we decided.** For each yes/no question, we run the circuit **twice**,
presenting two separate framings of the same market:

- once as **"YES at price p"**, and
- once as **"NO at price 1 − p"**

(if the market prices "yes" at 0.6, then "no" is priced at 0.4). We score each
run on its own. The **score** adds up the activity of output neurons assigned an
**approach-like** sign and subtracts the activity of output neurons assigned an
**avoidance-like** sign by the CIRCUIT rule — explained just below — with one
detail, decided 2026-09-21, about how neurons of the same kind are combined
(the **per-type mean**, also explained below). We then pick whichever framing
(YES or NO) scored higher,
**but only if the gap between the two scores clears a threshold**. The threshold
is set using training data only (never the final test data). If the gap is too
small, the system **abstains** — it declines to decide, which is a valid,
zero-stake action in our setup. An abstention also **teaches the circuit
nothing** (Section 4d), and we always report the **abstention rate** (Section 5).

Three terms:

- **Compartment:** a small, named zone of the mushroom body where a particular
  dopamine teaching neuron and a particular output neuron meet the same
  Kenyon-cell inputs. It is the local piece of circuit we use to decide which
  teaching signal belongs with which output.
- **CIRCUIT sign:** our primary readout is a modelling assumption based on the
  direct circuit wiring, not a behavioural measurement. For each output neuron,
  we add its annotated direct PAM and PPL1 dopamine synapses. It gets an
  avoidance-like sign if PAM, the reward-family dopamine neurons, supplies at
  least **80%**; it gets an approach-like sign if PPL1, the punishment-family
  dopamine neurons, supplies at least 80%. Otherwise it gets zero weight and
  does not affect the score. We chose 80% before any learning results, on
  connectivity grounds: clean compartments have near-total dominance, while
  the margin filters stray synapses without calling genuinely mixed input one
  family. The map is inferred from v783 wiring and is **unverified** at
  compartment level. We will report 70% and 90% as preregistered sensitivity
  checks.
- **STRICT and GROUP checks:** we will also rerun the analysis with two
  preregistered robustness readouts. STRICT uses only individually supported
  activation-valence labels; GROUP adds explicitly declared group-level labels.
  Any result that appears only under CIRCUIT will be reported as CIRCUIT-only.
- **Cell type and instance:** the model has 96 output neurons, but they come in
  a few dozen *types* (MBON01, MBON02, …), each type having one or more
  individual neurons — its *instances*, typically one or two per brain hemisphere
  (MBON10 has nine: four on the left, five on the right).
- **Per-type mean (the default aggregation, decided 2026-09-21):** first
  **average the firing rates of the instances within each type**, then apply the
  sign (+1, −1 or 0) and add the types up, so **each type gets one vote,
  regardless of how many instances it has.** The alternative — adding up every
  instance — would let a type with many instances dominate for a purely
  anatomical reason. The concrete case is MBON10: it has nine instances (six
  responded in our data) and is an "atypical" output neuron whose input branches
  lie largely outside the mushroom-body lobes, so a raw sum would give it the
  loudest voice in the score for a reason unrelated to what the circuit computes.
  **Sum-over-instances remains available in the code as a named variant
  (`instance_sum`), not as the default**; it is *not* one of the preregistered
  robustness checks unless we add it. Two consequences: (i) the threshold below
  is measured in different units under the two aggregations, so a threshold set
  under one is not valid under the other; (ii) **the mean is only as good as the
  list of instances it is given** — it must include the silent instances (rate
  0) of every type, in whichever hemispheres we decide to count, because
  averaging only the neurons that fired would inflate each type by a different,
  arbitrary factor. Which instances to count (both hemispheres, or left only) is
  **not settled by this document**; the graded-encoding test fixes a choice (all
  instances in both hemispheres) for its own purposes, and it is listed as open
  in Section 8.
- **Threshold:** a minimum confidence gap required before we act. Its units
  depend on the aggregation above.
- **Abstain:** choosing not to bet. In our markets, abstaining costs and earns
  nothing, and (decided 2026-09-21) it causes **no learning update** — see 4d.
  Because a system that abstains often could look accurate on the few decisions
  it does make, the **abstention rate** is a tracked output of the readout and is
  reported next to every forecast metric.

**Why.** Scoring the two framings separately and taking the difference is a
simple way to turn neural activity into a yes/no lean plus a confidence level,
and it is symmetric *provided the two framings deliver equal drive* (see problem 4
below: they do not). The abstain option keeps the system from acting on noise.

**What could go wrong — four real problems, stated plainly:**

1. **Cost.** This readout needs **two simulation runs per decision**, doubling
   the compute for every market. That is a deliberate trade for symmetry, and it
   matters given our speed uncertainty (Section 8).
2. **A circuit-logic assumption that can be wrong.** CIRCUIT does not use a
   behavioural label for every output neuron. It assigns signs from the dopamine
   family mapped to each compartment. That mapping is inferred rather than
   directly annotated, and it disagrees with the group-level approach labels of
   MBON08/09 in the γ3 pathway: MBON08 has no direct annotated dopamine input
   and is zero; MBON09 is PAM-dominant and avoidance-like. This genuine
   exception is reported, not corrected. STRICT and GROUP are therefore required
   robustness checks, and we will not present a CIRCUIT-only effect as a general
   result.
3. **A hidden confound around calibration.** We may pass the raw score through a
   fitted step that converts it into a probability (this is **calibration** —
   adjusting outputs so that, when the system says "70%," the event really
   happens about 70% of the time). The danger: that fitted step is itself a
   small trainable model, and it might be doing the real forecasting work, with
   the fly circuit contributing little. To catch this, **we will apply the exact
   same calibration step to every baseline** (Section 6), so no method gets a
   free advantage, **and we will always also report an uncalibrated version** of
   the results, so anyone can see how much the calibration step contributed.
4. **An intensity bias, found by the graded-rate test (2026-09-21).** The score
   depends strongly on *how hard* the input cells are driven, whatever the input
   means. When one group of 100 Kenyon cells was driven at 30, 60, 90, 120 and 150 Hz
   the CIRCUIT score fell steadily (−9.6 → −66.8; one seed; [`graded-encoding.md`](graded-encoding.md)).
   Both kinds of output neuron respond more as the drive rises, but the
   avoidance-like ones grow faster: at 150 Hz the summed type means were 168 Hz
   avoidance-like against 101 Hz approach-like, the largest single contributor being
   MBON09, then MBON02 and MBON03.

   *Why it matters for Option B.* Except at a price of exactly 0.5, the "YES at
   *p*" framing and the "NO at 1 − *p*" framing drive the price group at different
   rates, so they differ in total drive before the circuit has learned anything.
   Illustration (**unverified**: it draws straight lines between the five tested
   points for the price group alone and ignores the other features): at a price of
   0.8 the YES framing drives the price group at 30 + 0.8 × 120 = 126 Hz and the NO
   framing at 54 Hz. Those give scores of about −55 and −17, so NO scores higher by
   roughly 38 units *with no learning at all*. Under "choose the higher score," the
   circuit innately prefers NO whenever YES is the expensive side, and YES whenever
   it is cheap: a price-dependent, contrarian lean unrelated to anything learned.

   *A qualification that matters: the direction depends on the readout, the
   dependence itself does not.* The same five files scored under the other sign
   tables (analysis only, no new simulation): CIRCUIT at 70% and 90% also fall,
   but **STRICT (0.0 → +53.2) and GROUP (+10.8 → +77.6) rise**. Under those tables
   more drive means a more approach-like score, and Option B would lean toward the
   *more expensive* side instead. The biggest contributor, MBON09, is exactly the
   type where CIRCUIT and the group-level label disagree (problem 2). So "stronger
   drive pushes toward avoidance" is a statement about the primary CIRCUIT readout,
   not about the circuit in general, and the bias must be measured under every
   preregistered table.

   *Why it can mislead.* The lean is a function of price, and price is itself the
   market's forecast. A lean that costs money against well-calibrated prices could
   earn something in a market with a favorite–longshot bias, which would look like
   skill but would not be learning. The **learning-off control (Section 6) is
   therefore essential in every market experiment**: it shows what the innate lean
   alone earns.

   *Two ways to remove it. Proposed, not chosen, and neither has been built.*

   **(a) Total-drive balancing:** design the encoding so the YES and NO framings
   deliver equal total stimulation. For example, give each evidence feature a "for"
   and an "against" group of cells that swap rates between the framings, or add a
   filler group that tops the total up.
   *Costs:* more groups of cells (three extra for the three mirrored features);
   several groups driven at once is untested, so the encoder change needs its own
   graded-style test and pre-statement; a filler group carries the total *inversely*,
   so the intensity information is moved, not removed. *Could hide:* equal total
   drive is not equal effect, because different groups reach different output
   neurons (cues A and B differ by about 79 Hz at the readout), so a smaller lean
   tied to *which* group is driven harder would remain, harder to see because the
   total looks balanced and so falsely reassuring.

   **(b) Innate-score subtraction:** score each framing before learning, with the
   original connection strengths, and use *score now − innate score* in the decision,
   so only what learning changed counts.
   *Costs:* the innate score is needed for the exact stimulus of every decision:
   either two more simulation runs per market (four instead of two), or a fitted
   model of innate score as a function of the input rates — one more fitted
   component with its own error, open to the confound of problem 3. The difference
   of two noisy scores is noisier than either, and the noise of these scores is not
   yet measured. *Could hide:* learning may act multiplicatively (weakening a
   connection removes more when the drive is high), so the learned change itself
   scales with intensity and the bias can return as an intensity-times-learning
   term the subtraction does not remove; it deletes any innate structure that
   happens to be useful, by construction; and with unchanged weights every
   subtracted score is zero, so the learning-off control would always abstain and
   stop measuring the innate lean, so a separate innate-only arm would be needed.

   The two can be combined. **Not decided.** *The first learning test
   ([`first-learning-test.md`](first-learning-test.md)) is unaffected:* it drives
   both cues at the same constant 150 Hz and measures a *change* in the difference
   between them, so any fixed offset cancels. It does not show that learning works
   when the drive varies. **Any market experiment must address this bias first.**

**The separation score, defined precisely (used in Section 3d).** For two cues,
take each output neuron's firing rate under cue A and under cue B, forming two
lists of numbers. The separation score is the **cosine distance** between those
two lists. Cosine distance measures the *angle* between two lists of numbers: 0
means they point the same way (identical pattern, not separable), 1 means they
are at right angles (completely different pattern). We restrict this to output
neurons that fired under at least one of the two cues.

### 4c. REWARD — after the outcome, a dopamine-family teaching signal is applied by our learning rule

**What we decided (approved 2026-09-21).** After a market resolves (the true
yes/no answer becomes known), we teach the circuit with a **teaching signal**, and
we represent dopamine **abstractly**: it is a number saying which dopamine family
fired and how strongly, applied by our own learning rule (4d), not a set of
neurons we make fire inside the simulation.

- **Dopamine neuron:** a neuron that releases dopamine, a chemical that, in the
  fly's mushroom body, acts as a teaching signal — it tells the circuit "what
  just happened was good" or "was bad." Two groups matter here: **PAM** neurons,
  associated with reward (good), and **PPL1** neurons, associated with
  punishment (bad).

How it works, step by step: (1) the outcome decides which family the signal
belongs to (PAM if the outcome was good, PPL1 if bad) and how strong it is (the
clipped, normalized size described below); (2) our learning rule (4d) applies
that signal to the connections **from the Kenyon cells that were active for that
decision onto the output neurons in the compartments that family innervates**
(the connectome-derived compartment map). The rule runs outside the simulator, on
the table of KC→MBON connection strengths, and the new strengths are written back
into the network before the next run.

**Why not stimulate the dopamine neurons in the simulation?** The Shiu model has
no dopamine-dependent plasticity — nothing in it changes with experience — so
making PAM or PPL1 neurons fire there could not teach anything. It would only make
them send their *fast* signals to their targets, including onto Kenyon cells, and
that dopamine→Kenyon-cell excitation is one we flagged as biologically suspect
(the model gives every dopamine-neuron synapse a fast-excitatory sign, whereas in
a real fly dopamine acts as a slow modulator of Kenyon-cell plasticity; see the
sign audit in [`mushroom_body_check.md`](../reproduction/mushroom_body_check.md)).
So we do
not do it.

**The biological grounding is the compartment map, not simulated dopamine
neurons.** The map — which output neurons sit in the compartments each dopamine
type innervates — is inferred from the fly's wiring and is **unverified** at
compartment level (Section 4d). **We do not simulate dopamine release or dopamine
neuron activity during learning** (see also Section 10).

One loose end: the reward code still computes a "stimulation rate" (signal
strength × a placeholder maximum). It is only *recorded* in the results, is
**unanchored** (dopamine stimulation has never been simulated here), and is never
given to the network. It is kept so that a later experiment which does stimulate
dopamine neurons could be compared with these.

The size of each teaching signal is **clipped and normalized**: clipping caps
extreme values, and normalizing rescales them to a common range, so that a few
unusually large outcomes cannot dominate all the learning.

**Reward type is a preregistered experimental variable** — meaning we commit,
in advance, to testing two versions on identical markets and identical random
seeds:

- **Profit-based reward (headline arm):** the teaching signal is how much money
  the decision made or lost.
- **Accuracy-based reward (comparison arm):** the teaching signal is how much
  the *forecast* improved, measured by the improvement in **Brier score** (a
  forecast-accuracy measure defined in Section 5). **Improvement over what?**
  Decided 2026-09-21: **over the market's own quoted probability.** The reward is
  the market's Brier error minus our Brier error on that market: zero if we
  merely echoed the market's price, positive if our forecast landed closer to what
  happened than the market's did, negative if the market's was closer. So this arm
  rewards *beating the market*, not merely being better than a coin flip. (An
  alternative baseline of 0.5, "no opinion", is available in the code as a named
  variant, not the default.)

**Why two reward types, and why profit alone is a noisy teacher.** Profit is a
*noisy* signal because you can be right and still lose (a good forecast can lose
to bad luck on a single outcome), or wrong and still win. If you teach only from
profit, the circuit gets punished for good forecasts that happened to lose and
rewarded for bad forecasts that happened to win. A previous fly-and-markets
project reportedly saw its model learn a **blanket aversion** — it essentially
learned to avoid acting at all — which is the kind of degenerate outcome noisy
profit-teaching can cause (this account of that prior project is **unverified**
by us; we include it as motivation, not as established fact). Teaching also from
accuracy gives a cleaner, less luck-driven signal to compare against.

**What could go wrong.** The clip-and-normalize details are not yet settled
(Section 8), and different choices could change results. One consequence of the
market-price baseline is already visible: market prices are good forecasts, so
our improvement over them will usually be *small* — a forecast two percentage
points better than the market on a YES outcome improves the Brier error by only
about 0.016, which is 6% of the placeholder scale (0.25) we currently divide by.
Until that scale is set from training data, the accuracy arm's teaching signal is
likely to be weak (**unverified**; the placeholder is not a tuned value). The
accuracy arm also needs a *probability* forecast from us, which comes from the
calibration step discussed in 4b and is not yet specified. Representing
dopamine as an abstract teaching signal is, again, an engineered route, not a claim
about how flies learn or about what the model's dopamine neurons do; and the
compartment map that grounds it is an unverified inference.

**What tests it.** Running the **profit** and **accuracy** arms on identical
markets and seeds is itself the control: it isolates how much the *choice of
teaching signal* matters. The **learning-off control** (Section 6) shows what
the circuit does with no teaching at all.

### 4d. LEARNING RULE — dopamine-gated weakening of recently-active KC→MBON connections

**What we decided.** Only one set of connections is allowed to change: the
connections **from Kenyon cells to output neurons (KC→MBON)**. Everything else
in the model stays fixed at its measured values. The rule for changing them:

- Plasticity is **compartment-matched**: each dopamine-neuron type can change
  only the KC→MBON connections in the compartment(s) it innervates. It cannot
  change KC→MBON connections elsewhere in the mushroom body. The current
  v783-derived compartment map is an **unverified** inference and ambiguous
  mappings remain disabled unless we explicitly declare an assumption.
- When the teaching signal (dopamine, represented abstractly; see 4c) arrives,
  **weaken** the connections coming
  from Kenyon cells that were **recently active** for that decision. ("Gated"
  means the weakening only happens when dopamine is present.)
- A **floor** stops any connection from being driven below a minimum strength.
- A **slow drift** continuously nudges every connection back toward its original
  measured value from the connectome.

The floor and the drift exist to **prevent collapse** — without them, repeated
weakening could drive connections to zero and destroy the circuit's ability to
respond at all.

**Why this shape.** Weakening-of-active-connections under a dopamine gate is the
best-established direction of learning in the fly mushroom body, so it is the
natural, literature-motivated starting point. Restricting change to KC→MBON
keeps the learning interpretable and keeps everything else anchored to the real
measured brain.

**The timing problem and our fix — a queue.** The model has **no short-term
memory**: once a run ends, it retains nothing. But a real market outcome arrives
much later than the decision. So at decision time we **save** the Kenyon-cell
activity pattern for that market into a **queue** (a waiting list). When that
specific market finally resolves, we pull its saved pattern off the queue and
apply the learning update then. This lets a delayed outcome teach the circuit
about the decision it actually caused.

**Abstentions teach nothing (decided 2026-09-21).** Only decisions we actually
*acted on* (chose YES or NO) go into the queue. If the readout abstained on a
market, nothing is saved, and when that market resolves **no learning update
happens at all** — neither the weakening of connections nor the slow drift back
toward the original values. The weights are left exactly as they were. Two
consequences to keep in mind: the slow drift only advances when an acted-on
market resolves (time passing with no resolutions can be advanced separately);
and an abstained market's outcome carries no lesson for the circuit, so a system
that abstains a lot learns slowly. This is why the abstention rate is tracked
and reported.

**What could go wrong.** The learning could still collapse or saturate despite
the floor and drift; the "recently active" window and the drift speed are
tuning choices that could dominate results. (The earlier worry that the built-in
cue separation might be too small for any rule to learn from has since been
tested and resolved — Section 8 — though the separability of the eventual
market-feature encoding still has to be confirmed.)

**What tests it.** The **learning-off control** (Section 6) is the direct
ablation: same everything, learning disabled. If performance is no better with
learning on than off, the rule is not doing what we hoped. Comparing against the
**reduced mushroom-body model** (Section 6) checks whether the full connectome
is needed or whether a simpler circuit learns just as well.

---

## 5. What we will measure

We report several numbers, not one, because each captures a different way of
being right or wrong. Reporting only profit would hide most of them.

- **Brier score** — the average squared difference between the forecast
  probability and what actually happened (0 or 1). *Lower is better.* It rewards
  being both accurate and appropriately confident.
- **Log loss** — another forecast-accuracy score that punishes confident wrong
  answers much more harshly than Brier does. *Lower is better.* It matters
  because overconfidence is a specific, dangerous failure we want to catch.
- **Calibration** — whether the stated probabilities match reality: of all the
  times the system says "70%," do about 70% come true? This matters because a
  forecast can be accurate on average yet systematically over- or
  under-confident.
- **Profit and loss after fees and spread** — money made or lost, *after
  subtracting trading costs*. **Fees** are the charge per trade; the **spread**
  is the gap between the buy price and the sell price, which you pay just by
  trading. Costs matter because a strategy that looks profitable before costs
  can be a loser after them.
- **Maximum drawdown** — the worst peak-to-trough drop in cumulative money over
  the run. It matters because a strategy with good average profit but a huge
  crash along the way may be unusable in practice.
- **Turnover** — how much trading the strategy does. High turnover means high
  cost exposure and is a warning sign.
- **Abstention rate** — the fraction of markets on which the system chose not to
  decide. It matters because abstaining is free: a system can look accurate simply
  by acting only when it is nearly certain. It also controls how much the circuit
  gets to learn (abstentions teach nothing, 4d). Reported alongside every other
  number, for every arm.
- **Performance across multiple seeds** — we rerun everything with many
  different random seeds and report the spread of results, not one lucky run.
- **Bootstrap intervals** — a way of estimating uncertainty by repeatedly
  resampling our own results; it gives an honest range ("the true value is
  probably in here") rather than a single point.

Two guardrails we commit to: **good forecast scores do not prove the strategy
can make money, and profit does not prove the forecasts are well-calibrated.**
We report the forecast quality and the trading behavior separately and never let
one stand in for the other.

---

## 6. Controls we will run

A result only means something next to the right comparisons. We will run all of
these on the same markets and seeds:

- **Learning switched off** — the same circuit with no teaching. Isolates
  whether learning added anything.
- **Degree-preserving shuffled connectome** — the fly wiring randomly rewired,
  but with each neuron keeping its original *number* of connections. This keeps
  the "size and shape" of the network while destroying the specific fly
  structure, so it separates *structure* from *raw capacity*. The fixed method,
  scope options, and pre-run checks are in
  [`degree-preserving-connectome-control.md`](degree-preserving-connectome-control.md).
- **Reduced mushroom-body model** — a smaller, simpler model of the same circuit
  from Bennett, Philippides & Nowotny, 2021
  ([doi:10.1038/s41467-021-22592-4](https://doi.org/10.1038/s41467-021-22592-4)).
  Checks whether the full connectome is needed or a stripped-down version does
  as well. The source-verified equations, selected MV variant, parameters,
  adaptation, and reproduction criterion are recorded in
  [`reduced-mushroom-body-control.md`](reduced-mushroom-body-control.md).
- **Logistic regression** — a standard, simple statistical method for yes/no
  prediction, reading the same features. A basic "can a plain model do this?"
  bar.
- **Market price as the forecast** — just use the market's own quoted
  probability as the prediction. Prediction-market prices are often hard to
  beat; this is a demanding baseline.
- **Random** — decide by coin-flip. A floor: anything useful must beat this.
- **Always-base-rate** — always predict the overall historical yes-rate. Catches
  cases where a single fixed guess is deceptively hard to beat.

Every baseline receives the **same calibration step** and the same tuning budget
as the neural model, so none is handicapped or advantaged (see Section 4b).

---

## 7. Study order

We proceed in three stages, from most controlled to most realistic:

1. **Synthetic markets first.** These are made-up markets where *we* set the
   hidden truth, so we know the right answer exactly. **This is calibration, not
   the study:** their purpose is to measure how much signal the system needs
   before it can forecast at all, using the known-information "signal feature"
   from Section 4a.
2. **Historical real prediction-market data next.** Real past markets with known
   outcomes. **This is the actual study.**
3. **Prospective forecasts last.** Forecasts logged *before* the outcomes are
   known, so there is no possibility of hindsight creeping in.

Plainly: synthetic markets tell us whether the machinery *can* work and how much
signal it needs; real markets tell us whether it *does* work; prospective
forecasts are the honesty check.

---

## 8. Open questions and risks

Stated without softening. These are real, and some could stop the project.

- **MBON valence labels: the table exists; three key claims still need
  spot-checking.** The table of which output neurons are "approach-like" and
  which "avoidance-like" is in [`mbon-valence.md`](mbon-valence.md) (22 output-
  neuron types, each with the strength of its evidence). It was compiled with an AI
  research assistant, and its three key claims are **still to be spot-checked
  against the original papers**: MBON11 approach (Aso et al. 2014b, *eLife*
  3:e04580, Fig. 2C); MBON21 avoidance (Rubin & Aso 2023, *eLife* RP90523,
  Fig. 3H–I); MBON02 attraction (Mohammad et al. 2024, *PLOS Biology*). **The
  adopted readout is CIRCUIT at the 80% threshold** (Section 4b), with 70% and 90%
  as preregistered sensitivity checks. CIRCUIT's signs come from each output
  neuron's direct dopamine wiring, not from these behavioural labels, so the
  readout can be built and does not wait on the labels. The labels are used by the
  STRICT and GROUP robustness checks and to judge where CIRCUIT agrees with
  behaviour (it disagrees for MBON08 and MBON09, which is reported, not
  corrected), so the spot-check must be done before those results are reported.
  CIRCUIT's compartment map is itself an inference from wiring and is
  **unverified** at compartment level.
- **Cue separation at the readout — RESOLVED (was flagged "could be fatal").**
  We originally worried that the two cues' output patterns differed by a cosine
  distance of only **about 0.05** (Section 3d), and that this might be too small
  for any learning rule to use. We have now measured this directly (see
  [`docs/design/mbon-separability.md`](mbon-separability.md)): the "0.05" is
  small only because cosine distance is normalized by the large activity the two
  cues share; the actual difference is tens of Hz, concentrated in a few MBONs.
  Measuring the run-to-run noise (same cue, five different simulation seeds), the
  readout difference is **15.6× the same-cue noise at 1000 ms / 5 trials, with
  8/8 discriminating MBONs passing the per-neuron check.** The cues are reliably
  distinguishable; this is no longer an existential risk. **Two residual caveats
  remain:** (a) at the cheap 100 ms / 1 trial setting the ratio is only **1.9×**,
  too noisy for a single run per decision, so the study must **average trials or
  use a longer window** at that end; and (b) this was shown for two *specific*
  random 100-Kenyon-cell cue sets, **not** for the eventual market-feature
  encoding (Section 4a), whose separability **must be checked separately** once
  that encoding exists.
- **Graded encoding: tested and accepted; two things remain open.** The graded-rate
  test ([`graded-encoding.md`](graded-encoding.md)) was run on 2026-09-21 and the
  verdict is ACCEPTED: the readout is strictly monotonic (decreasing) across 30–150 Hz
  and the encoder's bounds equal that range (Section 4a). Still open: (i) it is one
  seed and one group of cells at a uniform rate, so several groups driven at once are
  untested; (ii) the intensity bias it revealed (next item).
- **The intensity bias must be addressed before any market experiment.** The score
  depends strongly on input intensity, so under Option B the two framings differ
  innately whenever the price is not 0.5, and the direction of that lean depends on
  the sign table (CIRCUIT falls with drive; STRICT and GROUP rise) — see 4b, problem
  4. Two remedies are proposed (total-drive balancing; innate-score subtraction).
  **The choice is undecided and neither is built or tested.** The bias must also be
  measured under STRICT, GROUP and the 70/90% variants, and the noise of the scores
  at the stimuli used in markets is not yet measured.
- **Which output-neuron instances enter the per-type mean is open.** The mean
  (Section 4b) must be taken over every instance of a type, silent ones included,
  but whether that means both hemispheres (right-hemisphere output neurons do
  respond, sometimes strongly, even though we only stimulate left-hemisphere
  Kenyon cells) or only the left has not been decided. The choice changes each
  type's mean by an instance-count-dependent factor. The graded-encoding test
  uses all instances in both hemispheres; that is a choice for that test, not a
  settled design decision.
- **Reward normalization is unsettled.** The exact clip-and-normalize scheme for
  the teaching signal (Section 4c) is not decided, and different choices could
  change the outcome. (The accuracy arm's scale is a separate open item, next.)
- **The accuracy-arm reward scale must be set before the preregistered
  experiment.** The accuracy arm divides its Brier improvement over the market
  price by a scale before clipping (Section 4c). The placeholder is 0.25, the
  largest improvement possible over a 0.5 baseline, but improvements over a market
  price are much smaller: a 2-point edge over the market (forecast 0.62 against a
  price of 0.60, and YES happens) improves the Brier error by 0.0156, which is
  currently only about 6% of the placeholder scale, so the teaching signal is weak.
  No tuned value exists (**unverified**); the scale must be set from training data
  only and frozen before the preregistered experiment, never tuned on its results.
- **The pace of the slow drift is unsettled.** It advances only when an acted-on
  market resolves (Section 4d); whether one "step" should instead mean one
  resolution, one trading day, or something else is open.
- **The market data source is not chosen.** We have not selected which real
  prediction-market dataset to use.
- **Speed is unmeasurable locally.** On the 8-gigabyte Mac, run timings are
  dominated by unrelated system load and cannot be used for planning (Section
  3d). We do not know the real per-decision cost on research hardware, and the
  Option B readout doubles it (Section 4b).
- **The FlyWire v783 data license is unresolved.** The public Zenodo record for
  the connectivity data has been seen showing a **CC BY 4.0** license (a permissive
  "credit the source" license), but at least one secondary source lists it as
  **CC BY-NC** (a "non-commercial only" license), and the separate neuron-labels
  repository has **no license file at all**. Our own reproduction notes recorded
  the Zenodo license field as *blank* at the time we checked, which does not
  match the CC BY 4.0 sighting — so the true status is genuinely unclear. **All
  of this is unverified, and because of it we do not redistribute the neuron
  annotation table.** This must be resolved before any release.

---

## 9. Prior work we are not claiming to have invented

We did not originate the idea of connecting a fly connectome model to markets.
At least two prior projects did:

- **fly-vs-tradeflare**
  ([github.com/sepehrasgarian/fly-vs-tradeflare](https://github.com/sepehrasgarian/fly-vs-tradeflare)),
  and
- **Stonkfly**.

(Both are described to us as having connected fly connectome models to markets;
we have **not** independently verified either project's contents, so these
descriptions are **unverified**.)

**Our contribution is not the premise. It is the rigor:** the controls
(Section 6), the honest metrics (Section 5), the preregistered reward comparison
(Section 4c), and above all the **synthetic-signal calibration** (Section 7)
that measures how much signal the system actually needs. If this project has
value, it is in doing the careful version, not in the idea of "fly plays
markets."

---

## 10. What we will NOT claim

Each of these matters, so each is explained:

- **This is not a whole-brain emulation.** We use one circuit from a partial
  brain model, not a working copy of a fly's mind. Claiming otherwise would
  massively overstate what a connectome-derived simulation supports.
- **We do not claim the simulation feels reward, pleasure, or preference.** When
  we call a teaching signal "reward," that is an engineering label for a teaching
  signal. The simulation does not experience anything. Saying it "wants" or
  "likes" would be false and misleading.
- **We do not simulate dopamine release or dopamine-neuron activity during
  learning.** Dopamine appears only as an abstract teaching signal that our own
  learning rule applies, in the compartments each dopamine family innervates (4c).
  We do not claim that the model's dopamine neurons do anything during learning, or
  that our rule reproduces what dopamine does biochemically; the compartment map
  that grounds it is an inference from wiring and is unverified.
- **The learning rule is ours, not from Shiu et al.** The published model has no
  learning (Section 2). Attributing our added mechanism to the original authors
  would misrepresent their work and ours.
- **The playful public framing stays out of scientific claims.** A fun name or a
  light description for outreach is fine in outreach. It must never appear in,
  or stand in for, a scientific claim. The two audiences get the same facts, but
  the claims we defend are the careful ones.

The reason all four matter is the same: this project sits at the meeting point
of neuroscience, machine learning, and finance, where it is very easy to imply
more than the evidence supports. Naming the narrowest accurate claim is the
whole point.

---

## 11. Scope, money, and roles

**No real money is involved at any stage of the work described here.** Every
market we use is either **synthetic** (made up by us, Section 7) or
**historical** (real past markets whose outcomes are already known). The
**prospective** stage records forecasts *before* outcomes are known, but it
still places **no trades** — the forecasts are logged for scoring, not acted on
with money.

**Any future live-money phase is out of scope for this design.** It would
require ethics, legal, financial, and security review *first*, and none of that
is covered or authorized by this document. Nothing here should be read as a plan
to trade real money.

**Who does what:**

- **Luca** leads technical implementation, experimentation, and writing.
- A **second collaborator** focuses on testing and on writing up results.
- A **third collaborator** leads the ethics workstream.

Ethics review is meant to **shape the design and the public communication from
the start** — it is part of how decisions get made, not a box ticked at the end.

---

## 12. How to give feedback

This document is meant to be argued with and revised.

- **To raise a concern or question:** open a GitHub issue on this repository, or
  send a comment directly to Luca. Either is fine; use whichever is easier.
- **This is a living document.** It will change as questions in Section 8 get
  resolved. Every change is tracked in git, so the full history of what we
  decided and when is always recoverable.
- **If any term in here was not clear,** that is a defect worth reporting on its
  own — this document is only doing its job if a non-specialist can follow it.

---

## 13. Revision log

- **2026-09-21.** Decisions recorded: (1) the NO-framing mirroring rule for each
  feature and its rationale (4a); (2) the readout averages MBON instances within
  each cell type first and gives each type one vote, with sum-over-instances kept
  as a named variant (4b); (3) accuracy reward is Brier improvement over the
  market's own price (4c); (4) abstentions trigger no learning update, and the
  abstention rate is tracked and reported (4b, 4d, 5). Also: the graded-rate
  encoding test and its pre-stated criterion were written down, unrun
  ([`graded-encoding.md`](graded-encoding.md)); the status line was updated now
  that the pure-logic code exists. Nothing here has been validated against the
  brain model.
- **2026-09-21 (later).** (1) The graded-rate test's verdict rule was revised,
  before any run, from two outcomes to three (accepted / usable range / fail); 4a
  and Section 8 describe the new consequences. (2) Section 8's stale claim that the
  MBON valence labels are missing and the readout cannot be built was replaced with
  the current status: the table exists ([`mbon-valence.md`](mbon-valence.md)), its
  three key claims still await spot-checking, and CIRCUIT at 80% is the adopted
  readout; the closing note had the same stale wording and was corrected too.
  (3) Added an open item: the accuracy-arm reward scale must be set before the
  preregistered experiment.
- **2026-09-21 (later still).** (1) The graded-rate test's rule gained a *sub-range
  gate*, added before any run: a usable range must also have its own endpoint
  distance clear 3 × the noise floor, or the verdict is fail. (2) Encoder rate
  bounds: after the graded test they must equal the validated range; meanwhile the
  placeholder minimum rate was changed from 0 to 30 Hz (4a). Neither has been run
  or validated.
- **2026-09-21 (evening).** (1) *Reward described accurately (4c, 4d, 10).* Approved:
  dopamine is represented abstractly as a teaching signal applied by our learning
  rule in the compartments each dopamine family innervates; no dopamine neurons are
  stimulated in the network; the biological grounding is the connectome-derived
  compartment map. Text saying reward is delivered by stimulating PAM/PPL1 was
  removed or corrected, and Section 10 now says we do not simulate dopamine release
  or dopamine-neuron activity during learning. (2) *Graded-rate test result
  (ACCEPTED).* Recorded in 4a and Section 8. (3) *Intensity bias.* Recorded in 4b
  (problem 4) with two proposed remedies, undecided. It was checked against the
  other sign tables: the dependence on intensity holds in all of them, but the
  direction flips between CIRCUIT and STRICT/GROUP.

---

*Unverified items are marked "unverified" inline throughout. No citations were
invented; where a citation is required but not yet in hand (most importantly the three key
claims of the MBON valence table, which still need spot-checking against the
original papers), that gap is stated as a gap rather than filled.*
