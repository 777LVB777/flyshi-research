# Research plan

## Research questions

1. Can a clearly scoped component from a published Drosophila neural model improve calibrated binary-outcome decisions in synthetic markets?
2. If it does, does the effect remain after matching model capacity, tuning budget, observations, and decision latency to conventional agents?
3. Which architectural or dynamical features account for any improvement?

This project does not assume that any candidate model emulates an entire fruit fly brain. The biological interpretation of a result is limited to the published model's stated scope and evidence.

## Phase 0 environment

Each synthetic market has a hidden latent Bernoulli probability, a bounded noisy market quote, and a resolved binary outcome. The agent observes only the quote and returns a decision containing a forecast probability and an independent action field. It cannot access the latent probability or outcome. YES costs `quote` and settles at `outcome`; NO costs `1 - quote` and settles at `1 - outcome`; ABSTAIN has zero P/L. This is a toy evaluation environment, not a model of market microstructure, liquidity, selection effects, or participants.

All experiments use recorded configuration, source revision, Python version, and explicit random seeds. The simulator separates market-generation and agent seeds so baseline sampling cannot alter the generated dataset.

## Experimental controls

- Pre-register hypotheses, primary metric, tuning budget, and stopping rule.
- Freeze train/validation/test seed sets before model selection; do not tune on the test seeds.
- Give every agent identical observations, action opportunities, contract size, costs (when added), and compute/latency budget.
- Report mean and uncertainty intervals across many independent seed sets, not a cherry-picked run.
- Version published-model code, data transformations, and all configurations.

## Baselines

Phase 0 includes a quote-independent random trader and a public-quote abstaining calibration reference. The legacy quote-threshold random-forecast behavior is diagnostic only, not a random-trading baseline. Later work must add:

- constant base-rate and market-quote forecasters;
- logistic regression and a capacity-matched MLP/recurrent baseline;
- an oracle upper bound using the synthetic latent probability (labelled as unavailable to deployable agents);
- simple decision rules matched to the candidate model's input history.

## Ablations

For every neural adaptation, remove or replace one feature at a time: recurrent state, biologically motivated connectivity, input encoding, plasticity or learning rule, and readout/decision rule. Match parameter count and tune each ablation with the same budget. Test shuffled connectivity and random-initialized variants to distinguish structure from capacity.

## Metrics

- **Brier score:** mean squared error of the decision's forecast probability; lower is better.
- **Log loss:** negative Bernoulli log likelihood of the decision's forecast probability, clipped only for numerical stability; lower is better.
- **Simulated P/L:** YES settlement minus YES cost (`outcome - quote`) or NO settlement minus NO cost (`quote - outcome`) for one contract per market; report separately from forecast quality and never as evidence of tradability.
- Forecast scores do not establish that the decision policy has an edge, and P/L does not establish that forecasts are calibrated. Report both fields and action frequencies separately.
- Calibration curve/ECE, accuracy, drawdown, turnover, and sensitivity to costs should be added before interpreting decision performance.

## Threats to validity

- Synthetic distributions can favor the generator's assumptions and will not represent real markets.
- Repeated seed selection, hyperparameter search, and baseline under-tuning can create false improvements.
- A biological label may overstate what a reduced published model represents.
- P/L without realistic liquidity, costs, adversarial adaptation, or selection bias is not economic evidence.
- Code, dependency, and floating-point differences can weaken reproducibility; record environments and use tolerance-based checks where needed.
- A whole-brain emulation, connectome-derived model, neural-circuit model, and biologically inspired algorithm make different claims. Name the narrowest category supported by the source evidence; none is implied by Phase 0.

## Exit criteria for Phase 0

The simulator, baseline, metrics, documentation, and deterministic tests must be reviewable and reproducible. No connection to real-money systems is within scope for this phase.
