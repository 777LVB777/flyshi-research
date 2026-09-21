# Flyshi Research

## Hypothesis

A published, partial Drosophila neural model may provide useful inductive biases for an uncertainty-aware decision-making agent in **synthetic** binary prediction-market simulations. Phase 0 establishes the measurement framework; it makes no claim that a simplified neural model is a complete fruit-fly brain emulation.

## Scope and limitations

This repository is research infrastructure, not financial software. The only environment currently implemented is a deterministic synthetic simulator and a random baseline. It uses paper-trading-style simulated P/L solely as an experimental metric. There are no live markets, exchange integrations, wallets, credentials, or real-money trading paths.

Simulation results cannot establish biological fidelity, market profitability, or real-world safety. Any later neural-model work must be evaluated against strong non-neural baselines and held-out environments.

## Model terminology

These terms are not interchangeable. A **whole-brain emulation** would claim to model an entire brain at an appropriate functional or biological scope; this project makes no such claim. A **connectome-derived model** uses connectivity data, but may omit cell dynamics, sensory context, and learning. A **neural-circuit model** represents a defined circuit and task, without representing the whole organism. A **biologically inspired algorithm** borrows design ideas from biology without claiming biological equivalence. Candidate work must be labelled using the narrowest accurate term.

## Phase 0 simulator semantics

For each market, a seeded generator draws a hidden latent probability uniformly from 0.1 to 0.9, draws a quote by adding uniform noise in [-0.15, 0.15] and clipping it to [0.01, 0.99], then draws a binary outcome from that latent probability. The agent observes **only** the quote. It never receives the hidden probability or outcome.

An agent returns a `Decision`: a probability forecast in [0, 1] and a separate action of YES, NO, or ABSTAIN. Brier score is the mean squared forecast error. Log loss is the mean negative Bernoulli log likelihood; the probability assigned to the realized outcome is floored at `1e-15` only for its logarithm. YES buys one contract for `quote`, settling at `outcome`; NO costs `1 - quote`, settling at `1 - outcome`; ABSTAIN has zero P/L. Thus per-market P/L is `outcome - quote` for YES, `quote - outcome` for NO, and zero for ABSTAIN.

Forecasting performance and trading-policy performance are different measurements: Brier/log loss use only the forecast field, while P/L uses only the action field. `RandomAgent` samples YES/NO with equal probability from a random draw independent of the quote; its expected P/L is zero conditional on any quote and outcome. `PublicQuoteAbstainingAgent` forecasts the public quote and never trades, so it is a calibration reference rather than an edge claim. `QuoteThresholdRandomForecastAgent` retains the earlier quote-dependent threshold behavior only for simulator diagnostics and is not a pure random-trading baseline.

A single simulated P/L run is not evidence of profitability. Any apparent behavior of a policy must be supported by repeated seeded simulations or an analytical expectation under the stated generator.

## Roadmap

1. **Phase 0 (current):** reproducible synthetic binary markets, random baseline, scoring, documentation, and tests.
2. **Phase 1:** specify candidate published Drosophila models, reproduce a bounded behavioral task, and add conventional forecasting baselines.
3. **Phase 2:** adapt only justified model components to synthetic decision tasks; run ablations, calibration, and robustness experiments.
4. **Phase 3:** independent replication, ethics review, and paper-trading protocol review before considering any broader simulation work.

## Quick start

Requires Python 3.10+ (the core package is tested on 3.10 and 3.11).

```bash
python3 -m pip install -e ".[dev]"
python3 -m flyshi_research.simulator
python3 -m pytest
```

The simulator prints mean Brier score, log loss, and simulated P/L for a seeded random agent. Results are reproducible for a given configuration and seed.

## License

MIT is suggested as a simple, permissive starting point. A starter `LICENSE` is included; confirm the choice with contributors or institutional counsel before publishing.

## Repository layout

- `src/flyshi_research/`: small simulator and baseline implementation
- `tests/`: deterministic behavioral tests
- `docs/research-plan.md`: experimental design and validity guardrails
- `docs/ethics.md`: ethics-collaborator review template
