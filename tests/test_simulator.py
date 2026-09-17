from __future__ import annotations

from math import isfinite, log

import pytest

from flyshi_research.simulator import (
    EPSILON,
    Action,
    Decision,
    Market,
    MarketObservation,
    PublicQuoteAbstainingAgent,
    RandomAgent,
    generate_markets,
    run_simulation,
)


class SequenceAgent:
    def __init__(self, decisions: list[Decision]) -> None:
        self._decisions = iter(decisions)

    def decide(self, observation: MarketObservation) -> Decision:
        return next(self._decisions)


def test_market_generation_is_reproducible_for_a_fixed_seed() -> None:
    assert generate_markets(4, seed=123) == generate_markets(4, seed=123)
    assert generate_markets(4, seed=123) != generate_markets(4, seed=124)


def test_random_agent_and_metrics_are_reproducible_for_fixed_seeds() -> None:
    markets = generate_markets(10, seed=123)
    first = run_simulation(markets, RandomAgent(seed=456))
    assert first == run_simulation(markets, RandomAgent(seed=456))
    assert first != run_simulation(markets, RandomAgent(seed=457))


def test_random_trader_actions_do_not_depend_on_quote() -> None:
    low_quote_decision = RandomAgent(seed=456).decide(MarketObservation(quote=0.01))
    high_quote_decision = RandomAgent(seed=456).decide(MarketObservation(quote=0.99))
    assert low_quote_decision == high_quote_decision
    assert low_quote_decision.action in {Action.YES, Action.NO}


def test_public_quote_baseline_forecasts_quote_and_abstains() -> None:
    decision = PublicQuoteAbstainingAgent().decide(MarketObservation(quote=0.42))
    assert decision == Decision(0.42, Action.ABSTAIN)


def test_abstention_has_zero_pnl() -> None:
    markets = [Market(0.5, quote=0.1, outcome=1), Market(0.5, quote=0.9, outcome=0)]
    assert run_simulation(markets, PublicQuoteAbstainingAgent()).simulated_pnl == 0.0


def test_forecast_metrics_and_pnl_use_separate_decision_fields() -> None:
    market = Market(0.5, quote=0.4, outcome=1)
    yes = run_simulation([market], SequenceAgent([Decision(0.25, Action.YES)]))
    abstain = run_simulation([market], SequenceAgent([Decision(0.25, Action.ABSTAIN)]))
    assert yes.brier_score == abstain.brier_score == pytest.approx((0.25 - 1.0) ** 2)
    assert yes.log_loss == abstain.log_loss == pytest.approx(-log(0.25))
    assert yes.simulated_pnl == pytest.approx(1.0 - 0.4)
    assert abstain.simulated_pnl == 0.0


def test_pnl_matches_hand_calculated_yes_and_no_settlement() -> None:
    markets = [Market(0.5, quote=0.4, outcome=1), Market(0.5, quote=0.3, outcome=0)]
    agent = SequenceAgent([Decision(0.7, Action.YES), Decision(0.2, Action.NO)])
    assert run_simulation(markets, agent).simulated_pnl == pytest.approx((1.0 - 0.4) + (0.3 - 0.0))


def test_endpoint_probabilities_have_finite_log_loss() -> None:
    markets = [Market(0.5, quote=0.5, outcome=1), Market(0.5, quote=0.5, outcome=0)]
    decisions = [Decision(0.0, Action.ABSTAIN), Decision(1.0, Action.ABSTAIN)]
    metrics = run_simulation(markets, SequenceAgent(decisions))
    assert metrics.brier_score == pytest.approx(1.0)
    assert metrics.log_loss == pytest.approx(-log(EPSILON))
    assert isfinite(metrics.log_loss)


def test_agents_receive_only_quote_not_hidden_probability_or_outcome() -> None:
    observed: list[MarketObservation] = []

    class InspectingAgent:
        def decide(self, observation: MarketObservation) -> Decision:
            observed.append(observation)
            assert not hasattr(observation, "latent_probability")
            assert not hasattr(observation, "outcome")
            return Decision(observation.quote, Action.ABSTAIN)

    run_simulation([Market(0.73, quote=0.42, outcome=1)], InspectingAgent())
    assert observed == [MarketObservation(quote=0.42)]


def test_invalid_empty_or_zero_market_runs_are_rejected() -> None:
    with pytest.raises(ValueError, match="count must be positive"):
        generate_markets(0, seed=1)
    with pytest.raises(ValueError, match="markets must not be empty"):
        run_simulation([], RandomAgent(seed=1))


@pytest.mark.parametrize("prediction", [-0.01, 1.01, float("nan"), float("inf")])
def test_invalid_agent_probabilities_are_rejected(prediction: float) -> None:
    with pytest.raises(ValueError, match="finite probabilities"):
        run_simulation([Market(0.5, quote=0.5, outcome=1)], SequenceAgent([Decision(prediction, Action.YES)]))
