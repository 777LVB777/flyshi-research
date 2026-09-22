# Methods (first draft)

**Status: first draft, assembled from existing design and reproduction
documents.** This prose has not been reviewed against the underlying result
files independently of those documents. Numbers are reproduced from
`docs/design/mb-learning-interface.md`, `docs/design/readout-and-plasticity-options.md`,
`docs/design/graded-encoding.md`, `docs/design/mbon-separability.md`,
`docs/design/first-learning-test.md`, `docs/design/synthetic-market-experiment.md`,
`docs/design/degree-preserving-connectome-control.md`,
`docs/design/reduced-mushroom-body-control.md`, `docs/design/fast-runner.md`,
`docs/design/mbon-valence.md`, and `docs/reproduction/shiu2024.md`. No claim is
made here beyond what those documents support, and no reference is cited that
is not already present in them.

## Model

We use the spiking model of the adult *Drosophila melanogaster* brain
published by Shiu et al. (2024), built from a whole-brain electron-microscopy
connectome reconstructed by the FlyWire project and comprising approximately
130,000 neurons. The published model contains no synaptic plasticity: its
connection weights are fixed at values derived from measured synapse counts,
and it exhibits no learning or memory on its own. All learning described below
is a mechanism we added on top of the published model; it is not part of the
Shiu et al. model and is not attributed to its authors. The model's
connectome is available in two published wiring versions. We used version 630
("v630"), the version shipped with the authors' code, to reproduce the
authors' published result. We used version 783 ("v783"), a later revision
against which the cell-type annotations we required are published, for all
subsequent mushroom-body analysis.

## Reproduction of the published result

We reproduced the paper's headline demonstration: electrical stimulation of
21 right-hemisphere sugar-sensing gustatory receptor neurons and readout from
motor neuron MN9, which drives proboscis extension during feeding. Using the
model's code-defined default parameters (1,000 ms per trial, 30 trials, 150 Hz
stimulation) and a fixed simulation seed, two independent repetitions produced
identical results (410,625 spikes each), confirming that the simulation is
deterministic under a fixed seed. The reproduction was qualitative rather than
numerical: the expected contralateral-over-ipsilateral ordering of MN9 firing
rates was reproduced (left/right ratio 1.47 locally versus 1.51 in the bundled
author output), and the three most strongly responding downstream neurons
matched the authors' own output in both identity and rank order. Absolute
firing rates ran consistently below the bundled author output — by 10.1% for
the left MN9 and 7.7% for the right — for reasons we could not fully explain.
One candidate explanation is a discrepancy between the model code's default
stimulation rate (150 Hz) and the value stated in the authors' notebook prose
(200 Hz); this explanation is unverified. The original publication states that
its absolute firing-rate predictions are not expected to be quantitatively
reliable, and we treat this as a successful qualitative reproduction, not an
exact numerical match.

## Circuit diagnostics

Before designing an input interface for our own use, we characterized how
information propagates through the model's olfactory and mushroom-body
pathways under two candidate stimulation routes.

**Olfactory-pathway stimulation does not produce sparse, separable
activity.** Driving projection neurons — the model's natural olfactory input
route into the mushroom body — at 150 Hz activated approximately 65% of
Kenyon cells, far above the 5–10% expected for sparse coding, and two
different simulated odors produced Kenyon-cell activation patterns with a
Jaccard overlap of 0.99, indicating that the two patterns were nearly
identical rather than distinguishable. Tracing the source of this spread, we
found that the model's antennal-lobe local neurons — which normally suppress
projection-neuron activity — are annotated as approximately 68% excitatory
onto projection neurons rather than predominantly inhibitory, so that
activity is amplified rather than damped before it reaches the mushroom body.
We stimulated projection neurons directly, which is not how odor input
arrives in a real fly (odorant receptor neurons drive projection neurons
indirectly and at lower rates); we therefore do not conclude that the model
fails to represent olfaction in general, only that this specific stimulation
route does not produce clean, separable Kenyon-cell patterns in our hands.

**Direct Kenyon-cell stimulation is contained and separable.** Stimulating
two disjoint, fixed pools of 100 Kenyon cells each (chosen by a fixed random
seed) produced no measurable spread to unstimulated Kenyon cells and no
overlap between the two cues' active-cell sets. Thirty-three mushroom-body
output-neuron (MBON) instances, spanning 20 distinct FlyWire cell-type
labels, responded downstream. We adopted direct Kenyon-cell stimulation as
our input route on this basis; it is an engineered interface, not a claim
about how a fly's Kenyon cells are normally driven.

**Output-neuron separability and the run-to-run noise floor.** The two
cues' 96-dimensional MBON firing-rate vectors differed by a cosine distance
of only approximately 0.05, a small number driven by the two cues sharing a
large common-mode activity level. The absolute, per-neuron differences were
substantially larger: a maximum per-MBON difference of 30–50 Hz and a
whole-vector Euclidean distance of 76–100 Hz, concentrated in a small number
of MBONs (the single largest-differing MBON accounted for 14–29% of the total
squared difference across twelve independent duration/trial settings, and the
top five MBONs for 52–64%). Eight MBON instances were consistently among the
most discriminating across all twelve settings, each with a sign (cue A
greater or cue B greater) that never reversed. To establish whether this
difference reflected a real, reproducible signal rather than simulation
noise, we measured the run-to-run noise floor directly by repeating cue A
alone at five additional simulation seeds and comparing the resulting spread
to the existing cue-A-versus-cue-B difference. At the longer, lower-noise
setting (1,000 ms, 5 trials), the mean same-cue distance was 5.10 Hz and the
mean cue-A-to-cue-B distance was 79.44 Hz, a ratio of 15.6, against a
pre-specified acceptance threshold of 3.0; all eight of the previously
identified discriminating MBONs individually cleared a per-neuron version of
the same threshold. At a cheaper setting (100 ms, 1 trial), the same ratio
was 1.9 — above the threshold for a real signal but below the threshold for
reliable single-trial use, so we take single decisions to require averaging
over multiple trials or a longer simulated duration rather than the cheapest
setting. This noise-floor measurement used cue A only, so it assumes,
without directly testing, that cue B has comparable run-to-run noise.

**Graded rate encoding and an associated intensity bias.** Because every
diagnostic above compared only which Kenyon cells were driven, not how
strongly, we separately tested whether the circuit's output changes in an
orderly, monotonic way with input intensity, which our subsequent encoding
of continuous market features into firing rates requires. One pool of 100
Kenyon cells was driven at 30, 60, 90, 120, and 150 Hz (one run per rate,
1,000 ms, 5 trials, fixed seed). The primary readout score (defined below)
was strictly monotonic across all five rates, and the Euclidean distance
between the MBON vectors at the two endpoints (222.9 Hz) exceeded a
pre-specified threshold of 15.3 Hz (three times the measured noise floor) by
a wide margin; we designated 30–150 Hz as the validated range and set the
input encoder's rate bounds to match it. The direction of the monotonic
relationship, however, was decreasing under the primary readout: stronger
drive produced a more avoidance-leaning score, because both approach-like
and avoidance-like output-neuron populations increased with drive but the
avoidance-like population increased faster (168.0 Hz versus 101.2 Hz summed
type-mean activity at 150 Hz). Re-scoring the same five simulation outputs
under alternative sign conventions (below) showed that this direction is not
a fixed property of the circuit: two alternative readouts produced a rising
rather than falling score with increasing drive. Because our decision
procedure (below) compares two stimulus intensities that generally differ
whenever a market's price is not exactly 0.5, this intensity dependence
constitutes an innate, price-dependent bias in the decision procedure that
exists independently of any learning, and it is currently unresolved: two
candidate mitigations have been specified but neither has been implemented
against the full model, and any experiment presenting market data to the
circuit must address it before its results can be interpreted as measuring
learning rather than this bias.

## Readout

We convert mushroom-body output-neuron activity into a decision by
presenting each market twice per decision — once as a "YES" framing at the
market's quoted price and once as a "NO" framing at one minus that price —
scoring each framing, and selecting whichever framing scores higher, provided
the gap between the two scores clears a threshold fitted on training data;
otherwise the system abstains, which we treat as a valid action that incurs
no learning update. The primary scoring rule, which we refer to as CIRCUIT, is
derived from wiring rather than from behavioral measurements: for each output
neuron we sum its annotated direct synapses from PAM (reward-associated) and
PPL1 (punishment-associated) dopamine neurons, and assign the neuron an
avoidance-like sign if PAM supplies at least 80% of that annotated input, an
approach-like sign if PPL1 supplies at least 80%, and zero weight otherwise.
This 80% threshold was fixed before any learning result existed, on the
grounds that unambiguous compartments in the data show near-total dominance
by one dopamine family (for example 99.9% and 99.6% for two of the assigned
types), and we report 70% and 90% as preregistered sensitivity checks on the
threshold. Firing rates are aggregated by first averaging across the
individual neuron instances of each anatomical cell type (so that a type with
many instances does not receive disproportionate weight for anatomical
reasons alone) and then summing the signed type averages; an alternative
aggregation that sums over all instances is implemented but is not the
default. We additionally report two behaviorally grounded, preregistered
robustness readouts: STRICT, which uses only individually confirmed
activation-valence labels, and GROUP, which adds labels established only at
the level of co-activated neuron groups. CIRCUIT's wiring-derived signs
disagree with the behavioral literature for two output-neuron types in the γ3
compartment: MBON08 receives no direct annotated dopamine input under CIRCUIT
and is therefore assigned zero weight despite a group-level approach label,
and MBON09 is assigned an avoidance-like sign under CIRCUIT (99.6% of its
annotated dopamine input is PAM) despite a group-level approach label; we
report this disagreement rather than resolving it, and it accounts for the
largest single contribution to the intensity bias described above.
Accordingly, we also report a sensitivity variant, CIRCUIT-80 with MBON08 and
MBON09 excluded, so that any result found to depend on this specific,
contested pair of neuron types can be identified as such.

## Learning rule

The only connections permitted to change are those from Kenyon cells to
output neurons. Plasticity is compartment-matched: each dopamine-neuron type
can modify only the Kenyon-cell-to-output-neuron connections in the
mushroom-body compartment(s) it directly innervates, using a map inferred
from direct dopamine-neuron-to-output-neuron synapse counts in the v783
connectome (this compartment map is not independently verified at the
compartment level). When a teaching signal is applied, the rule weakens the
connections from Kenyon cells that were active during the associated
decision; a floor prevents any connection from being driven below a minimum
fraction of its original, connectome-derived strength, and a slow drift
continuously returns every connection toward that original value, together
preventing collapse of the circuit's responsiveness. Because the published
model contains no dopamine-dependent synaptic plasticity, and because every
modeled dopamine-neuron synapse in this connectome is annotated as fast and
excitatory — including onto Kenyon cells, which we consider biologically
implausible for a slow neuromodulatory signal — we do not stimulate dopamine
neurons within the simulator during learning. Instead, dopamine is
represented abstractly: a scalar teaching signal, carrying a sign (PAM- or
PPL1-family) and a clipped, normalized magnitude, is applied directly by our
learning rule to the compartment-matched connections, entirely outside the
spiking simulation. We do not claim that this abstraction reproduces the
biochemistry of dopaminergic modulation in the mushroom body, and we do not
simulate dopamine release or dopamine-neuron activity at any point during
learning. Reward type is a preregistered experimental variable with two
arms run on identical markets and seeds: a profit-based arm, in which the
teaching signal is the money the decision made or lost, and an
accuracy-based arm, in which the teaching signal is the improvement in Brier
score relative to the market's own quoted probability. The rationale for
including the accuracy-based arm is that profit is a noisy teacher — a
correct forecast can lose on a single outcome and an incorrect one can win —
and a purely profit-driven signal risks teaching a degenerate, uniformly
averse policy, a failure mode reported (though not independently verified by
us) for at least one earlier fly-connectome-and-markets project. Decisions on
which the system abstained receive no learning update of any kind, including
no drift.

## Controls

We evaluate the learned circuit against the following comparisons, run on
identical markets and seeds and given the same calibration procedure and
tuning budget:

- **Learning switched off**, an ablation of the learning rule with everything
  else unchanged, isolating whether learning contributes anything beyond the
  circuit's fixed, innate response.
- **A degree-preserving shuffled connectome**, generated by a directed
  double-edge-swap procedure that exchanges the targets of pairs of edges
  while holding fixed the neuron set, each neuron's in- and out-degree
  (counted by connectivity row), and the global joint distribution of
  synapse count and sign; it destroys specific pre/post partner
  identity, wiring motifs, and cell-type-specific connectivity within the
  shuffled scope. This isolates whether any effect depends on the fly's
  specific wiring or only on the network's coarse size and degree structure.
  The generation procedure and its pre-run correctness checks have been
  implemented and validated on synthetic test graphs; the real v783
  connectome has not yet been shuffled, and whether the shuffle is applied to
  the mushroom body alone or to the whole network is an open choice that has
  not yet been made.
- **A reduced mushroom-body model**, an independent, non-connectome
  circuit model of mushroom-body learning from Bennett, Philippides and
  Nowotny (2021), implementing the mixed-valence variant of their published
  plasticity rule. We verified the model's governing equations and
  parameters against the original publication and its released source code,
  and we ran a pre-specified protocol-fidelity check reproducing the
  qualitative result in the source paper's Figure 3d: that the model's
  reinforcement-prediction signal tracks an unbounded, stepped reinforcement
  schedule. This check compared the model's reinforcement prediction at
  nine block endpoints in a 180-trial schedule against the noiseless
  reinforcement value at each endpoint and required a root-mean-square error
  no greater than 0.15 reinforcement units; the reduced model passed this
  check. We emphasize that this tolerance is our own, invented for this
  check and never stated by the original authors — the source publication
  reports that its model tracks the schedule accurately but does not give a
  numerical tolerance against which to test a reimplementation. The check
  therefore establishes only that our NumPy reimplementation reproduces the
  qualitative behavior described in the source paper to within a threshold we
  chose ourselves; it is not a validated numerical match to the paper, nor an
  independent replication of the paper's original MATLAB analysis, nor any
  evaluation of the reduced model's performance on our synthetic or
  historical markets, which remains untested.
- **Logistic regression** on the same encoded features, as a baseline
  statistical model with no neural circuit.
- **The market's own quoted price**, used directly as the forecast — a
  demanding baseline, since prediction-market prices are typically difficult
  to beat.
- **Random** (coin-flip) decisions, as a floor.
- **Always predicting the historical base rate**, catching cases in which a
  single fixed guess is difficult to beat.

## Status at the time of this draft

Two infrastructure checks required before any learning experiment proceeds
have now been completed. First, a graded-rate encoding test (above)
established that the readout responds monotonically to input intensity over
30–150 Hz, at the cost of revealing the intensity bias described above.
Second, a fast, reusable-network simulation path intended to make repeated,
sequential decision-and-learning experiments computationally tractable has
been validated for equivalence against the original, slower simulation path:
across five independent seeds, the mean Euclidean distance between the two
paths' output-neuron rate vectors was 4.61 Hz, within the pre-specified 5.10
Hz noise-floor tolerance, and all eight previously identified discriminating
output neurons retained the same sign of their cue-A-versus-cue-B difference
under the fast path. With this equivalence test passed, the first
cue-reward association test — a pre-specified experiment asking whether the
learning rule causes the circuit's readout to prefer a rewarded cue over an
unrewarded one, with dedicated controls for whether learning is switched on,
reversible in direction, and specific to the taught cue — is now cleared to
run. It has not yet been run. The synthetic-market signal-requirement
experiment, which depends additionally on a choice between the two
unresolved intensity-bias mitigations described above, has likewise not yet
been run.

## References

- Shiu, P. K. et al. A Drosophila computational brain model reveals sensorimotor
  processing. *Nature* 634, 210–219 (2024). doi:10.1038/s41586-024-07763-9.
- Bennett, J. E. M., Philippides, A. & Nowotny, T. Learning with reinforcement
  prediction errors in a model of the Drosophila mushroom body. *Nature
  Communications* 12, 2569 (2021). doi:10.1038/s41467-021-22592-4.
- Aso, Y., Hattori, D., Yu, Y. et al. The neuronal architecture of the
  mushroom body provides a logic for associative learning. *eLife* 3, e04577
  (2014). doi:10.7554/eLife.04577.
- Aso, Y., Sitaraman, D., Ichinose, T. et al. Mushroom body output neurons
  encode valence and guide memory-based action selection in Drosophila.
  *eLife* 3, e04580 (2014). doi:10.7554/eLife.04580.
- Owald, D., Felsenberg, J., Talbot, C. B., Das, G., Perisse, E., Huetteroth,
  W. & Waddell, S. Activity of defined mushroom body output neurons underlies
  learned olfactory behavior in Drosophila. *Neuron* 86, 417–427 (2015).
  doi:10.1016/j.neuron.2015.03.025.
- Li, F., Lindsey, J. W., Marin, E. C. et al. The connectome of the adult
  Drosophila mushroom body provides insights into function. *eLife* 9,
  e62576 (2020). doi:10.7554/eLife.62576.
- Rubin, G. M. & Aso, Y. New genetic tools for mushroom body output neurons
  in Drosophila. *eLife* 13, RP90523 (2023). doi:10.7554/eLife.90523.
- Mohammad, F., Mai, Y., Ho, J. et al. Dopamine neurons that inform Drosophila
  olfactory memory have distinct, acute functions driving attraction and
  aversion. *PLOS Biology* 22, e3002843 (2024).
  doi:10.1371/journal.pbio.3002843.
