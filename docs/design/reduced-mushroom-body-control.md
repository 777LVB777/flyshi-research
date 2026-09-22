# Reduced mushroom-body control: Bennett, Philippides & Nowotny (2021)

**Status:** source-verified implementation specification written 2026-09-21
before running the new reproduction test. The pre-stated reproduction test then
passed on 2026-09-21. No Brian2 or connectome simulation is involved; the model
is pure NumPy.

## Sources and selected model

The primary source is Bennett, Philippides & Nowotny, “Learning with
reinforcement prediction errors in a model of the Drosophila mushroom body,”
*Nature Communications* 12, 2569 (2021),
[doi:10.1038/s41467-021-22592-4](https://www.nature.com/articles/s41467-021-22592-4).
The paper links its [archived author code](https://github.com/BrainsOnBoard/paper_RPEs_in_drosophila_mb),
which was also inspected.

The paper contains several related circuits: VS, VSλ, two VSu circuits, and the
mixed-valence (MV) circuit. This control implements the **MV model using the
paper's Eq. 8 plasticity rule**, expressed as the discrete update in Methods
Eq. 22. The paper states that this is the MV rule used thereafter, and Fig. 3d–g
shows its unbounded reinforcement-prediction learning. The VS/VSλ/VSu variants
are not implemented.

## Source equations and parameters

- Units use rectified linear responses from Eq. 9.
- Approach and avoidance MBON rates follow Eq. 10. Their difference is the
  reinforcement prediction.
- Binary decisions use the Eq. 11 softmax. The author code sets temperature
  `T=0.2`, hence `beta=5`.
- Mixed-valence DAN rates follow Eq. 14 with MBON feedback weight `w_M=1`.
- Learning follows Eq. 22: active KC→approach weights change with the difference
  between approach and avoidance DAN rates, and KC→avoidance weights change in
  the opposite direction. The author implementation rectifies updated weights
  at zero.
- The Methods assign each paper cue to 10 KCs firing at 1 Hz, so total KC
  activity is 10 Hz. The author implementation normalizes each cue to that same
  total.
- KC→MBON weights are independently initialized as `0.1 * Uniform(0,1)`, as
  stated in Methods and implemented by the authors.
- The Fig. 3d–g author script uses `gamma=1` for fixed KC→DAN weights and passes
  `0.5 * 2.5e-2 = 0.0125` as the MV learning rate. These are this control's
  defaults. They are exact figure settings, not claimed biological constants.

Implementation: `src/flyshi_research/controls/reduced_mushroom_body.py`.

## Flyshi interface

The core sequence is:

1. `decide(yes_cue, no_cue)` accepts two non-negative KC firing-rate vectors,
   each summing to the paper's 10 Hz, and returns Flyshi's ordinary `Decision`
   containing a YES probability and a sampled YES/NO action.
2. `reward(value)` supplies the signed reinforcement for the selected cue and
   applies one Eq. 14/Eq. 22 update.
3. `freeze()` disables queuing and plasticity for the chronological held-out
   split.

`BennettMarketAgent` accepts the same `MarketObservation` type as other Phase 0
agents. It reuses Flyshi's existing `KCEncoder` and its Option-B YES/NO
framings. `run_market_sequence` uses the same chronological split and calls the
shared Platt calibration function fitted only on training forecasts/outcomes.
The reinforcement callback is invoked only for training rows, so the model
cannot receive test outcomes during fitting.

## Differences from the paper

- The paper represents odors or other sensory cues with cue-specific KC
  populations. Flyshi represents market price, recent change, time to
  resolution, liquidity, and the synthetic signal with its existing seeded
  feature pools.
- The adapter rescales each encoded market framing to total KC activity of
  10 Hz. This preserves the encoder's relative feature rates and matches the
  paper's total activity, but it is a **Flyshi adaptation not tested in the
  paper**. It also gives YES and NO equal total drive.
- The paper's bandit chooses among sensory cues and receives their reinforcement.
  Flyshi's two cues are YES and NO framings; profit or accuracy reward is passed
  as signed reinforcement. The paper did not study prediction markets, Brier
  rewards, fees, spreads, or probability calibration.
- The paper's experimental protocols deliver reinforcement immediately after a
  choice. This adapter likewise targets the synthetic task, where outcomes are
  immediately available during training; delayed real-market resolution is not
  implemented here.
- The paper uses MATLAB's seeded random stream. This implementation uses NumPy's
  seeded generator, so individual initial weights, noisy reinforcements, and
  sampled choices are not expected to match the MATLAB trace exactly.
- Only the MV Eq. 8/Eq. 22 model is implemented. Results do not stand in for the
  paper's VS, VSλ, VSu, intervention, conditioning, or blocking models.

## Pre-stated published-result reproduction

The unit test reproduces the qualitative result in **Fig. 3d** that the MV
model's reinforcement prediction tracks an unbounded stepped reinforcement
schedule.

Protocol, fixed before executing the test:

- 20 KCs and two non-overlapping cues of 10 KCs at 1 Hz each;
- 180 trials, cue 1 forced on every trial as in the authors' `choose1=true`;
- the Fig. 3 schedule from Methods: blocks of 20 trials at
  `0, +1, +2, +1, 0, -1, -2, -1, 0`;
- Gaussian reinforcement noise with standard deviation 0.1, the paper's default;
- 10 independently seeded NumPy runs;
- source settings `gamma=1`, `beta=5`, learning rate `0.0125`, initial weights
  in `[0,0.1]`, and a zero weight floor;
- compare the mean pre-update reinforcement prediction at the final trial of
  each 20-trial block with that block's noiseless reinforcement.

**Pass criterion:** root-mean-square error across those nine endpoints must be
at most **0.15 reinforcement units**. The paper reports accurate tracking but
does not state this numerical tolerance; 0.15 is an **unverified, pre-stated
reproduction tolerance**, not a value attributed to the paper. The test does
not claim pixel-level reproduction of Fig. 3d because MATLAB and NumPy random
streams differ.

## Limits

The equations, listed parameter values, schedule, and author implementation
details above were verified from the open paper and linked source code. The
qualitative NumPy reproduction passed its pre-stated tolerance. The market
adaptation, exact equivalence of NumPy and MATLAB trajectories, and performance
on Flyshi synthetic markets remain **unverified**.

## Test result

The six reduced-model unit tests passed on 2026-09-21, including the Fig. 3d
endpoint-RMSE gate above. This verifies the NumPy implementation against its
hand-computed one-step values and the stated qualitative learning-curve target;
it is not an independent replication of the paper's full MATLAB analysis.
