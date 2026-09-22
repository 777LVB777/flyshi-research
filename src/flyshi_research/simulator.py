"""A deterministic, offline-only synthetic binary prediction-market simulator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log
from random import Random
from statistics import fmean
from typing import Protocol

EPSILON = 1e-15


@dataclass(frozen=True)
class Market:
    """Internal resolved state for one synthetic YES/NO contract."""

    latent_probability: float
    quote: float
    outcome: int
    signal: float = 0.5
    recent_change: float = 0.0
    time_to_resolution: float = 30.0
    liquidity: float = 0.5
    sequence: int = 0


@dataclass(frozen=True)
class MarketObservation:
    """The complete Phase 0 information set made available to an agent."""

    quote: float
    signal: float = 0.5
    recent_change: float = 0.0
    time_to_resolution: float = 30.0
    liquidity: float = 0.5


class Action(str, Enum):
    """A single-contract paper-trading action."""

    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class Decision:
    """A forecast and a separately selected action for one observation."""

    forecast_probability: float
    action: Action


@dataclass(frozen=True)
class SimulationMetrics:
    """Aggregate probabilistic forecast and one-contract paper P/L metrics."""

    brier_score: float
    log_loss: float
    simulated_pnl: float


class Agent(Protocol):
    """An agent that forecasts from only the exposed market observation."""

    def decide(self, observation: MarketObservation) -> Decision:
        """Return a probability forecast and a separate trading action."""


class RandomAgent:
    """Seeded random forecast and quote-independent random trading baseline."""

    def __init__(self, seed: int) -> None:
        self._forecast_rng = Random(seed)
        self._action_rng = Random(seed ^ 0x9E3779B9)

    def decide(self, observation: MarketObservation) -> Decision:
        """Draw forecast and YES/NO action independently of the quote."""
        del observation
        forecast_probability = self._forecast_rng.random()
        action = Action.YES if self._action_rng.random() < 0.5 else Action.NO
        return Decision(forecast_probability, action)


class PublicQuoteAbstainingAgent:
    """Public-information calibration reference that never takes a position."""

    def decide(self, observation: MarketObservation) -> Decision:
        return Decision(observation.quote, Action.ABSTAIN)


class QuoteThresholdRandomForecastAgent:
    """Legacy quote-dependent stochastic policy retained only for diagnostics."""

    def __init__(self, seed: int) -> None:
        self._rng = Random(seed)

    def decide(self, observation: MarketObservation) -> Decision:
        forecast_probability = self._rng.random()
        action = Action.YES if forecast_probability >= observation.quote else Action.NO
        return Decision(forecast_probability, action)


def generate_markets(count: int, seed: int, quote_noise: float = 0.15) -> list[Market]:
    """Generate seeded markets with latent probabilities and noisy quotes."""
    if count <= 0:
        raise ValueError("count must be positive")
    if not 0 <= quote_noise <= 0.9:
        raise ValueError("quote_noise must be between 0 and 0.9")

    rng = Random(seed)
    markets: list[Market] = []
    for _ in range(count):
        latent_probability = rng.uniform(0.1, 0.9)
        quote = min(0.99, max(0.01, latent_probability + rng.uniform(-quote_noise, quote_noise)))
        outcome = int(rng.random() < latent_probability)
        markets.append(Market(latent_probability, quote, outcome))
    return markets


def generate_signal_markets(
    count: int,
    seed: int,
    signal_strength: float,
    price_deviation: float = 0.20,
) -> list[Market]:
    """Generate a chronological synthetic market sequence with controlled signal.

    The hidden true probability is uniform on ``[0.1, 0.9]``.  The public market
    price is that probability plus independent uniform error in
    ``[-price_deviation, +price_deviation]``, clipped to ``[0.01, 0.99]``.

    The synthetic signal mixes an independent distractor probability with the
    hidden true probability::

        signal = (1 - strength) * distractor + strength * true_probability

    Thus strength 0 contains no population-level information about truth and
    strength 1 reveals the true probability exactly.  Using the same ``seed`` at
    different strengths keeps true probabilities, prices, outcomes and the
    distractor draws identical; only their mixture changes.  This is an
    engineered calibration environment, not a model of a real market.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    if not 0.0 <= signal_strength <= 1.0:
        raise ValueError("signal_strength must be in [0, 1]")
    if not 0.0 <= price_deviation <= 0.9:
        raise ValueError("price_deviation must be in [0, 0.9]")
    rng = Random(seed)
    markets: list[Market] = []
    previous_quote = 0.5
    for sequence in range(count):
        true_probability = rng.uniform(0.1, 0.9)
        price = min(0.99, max(0.01, true_probability + rng.uniform(-price_deviation, price_deviation)))
        outcome = int(rng.random() < true_probability)
        distractor = rng.uniform(0.05, 0.95)
        signal = (1.0 - signal_strength) * distractor + signal_strength * true_probability
        recent_change = min(0.2, max(-0.2, price - previous_quote))
        previous_quote = price
        markets.append(
            Market(
                latent_probability=true_probability,
                quote=price,
                outcome=outcome,
                signal=signal,
                recent_change=recent_change,
                time_to_resolution=rng.uniform(1.0, 365.0),
                liquidity=rng.random(),
                sequence=sequence,
            )
        )
    return markets


def observe_market(market: Market) -> MarketObservation:
    """Drop hidden probability and outcome while retaining public features."""
    return MarketObservation(
        quote=market.quote,
        signal=market.signal,
        recent_change=market.recent_change,
        time_to_resolution=market.time_to_resolution,
        liquidity=market.liquidity,
    )


def run_simulation(markets: list[Market], agent: Agent) -> SimulationMetrics:
    """Score forecasts and settle one simulated contract per resolved market.

    Forecast metrics use only ``forecast_probability``. P/L uses only ``action``:
    YES costs ``quote`` and settles at ``outcome``; NO costs ``1 - quote`` and
    settles at ``1 - outcome``; ABSTAIN earns zero. This deliberately omits all
    real-market mechanics and must not be interpreted as evidence of tradability.
    """
    if not markets:
        raise ValueError("markets must not be empty")

    brier_scores: list[float] = []
    log_losses: list[float] = []
    pnl = 0.0
    for market in markets:
        observation = observe_market(market)
        decision = agent.decide(observation)
        prediction = decision.forecast_probability
        if not isfinite(prediction) or not 0.0 <= prediction <= 1.0:
            raise ValueError("agent predictions must be finite probabilities in [0, 1]")
        if not isinstance(decision.action, Action):
            raise ValueError("agent actions must be an Action value")

        brier_scores.append((prediction - market.outcome) ** 2)
        realized_outcome_probability = prediction if market.outcome else 1.0 - prediction
        log_losses.append(-log(max(EPSILON, realized_outcome_probability)))
        if decision.action is Action.YES:
            pnl += market.outcome - market.quote
        elif decision.action is Action.NO:
            pnl += market.quote - market.outcome

    return SimulationMetrics(fmean(brier_scores), fmean(log_losses), pnl)


def main() -> None:
    """Run the Phase 0 random baseline with fixed, documented seeds."""
    markets = generate_markets(count=100, seed=20260916)
    metrics = run_simulation(markets, RandomAgent(seed=7))
    print(f"Brier score: {metrics.brier_score:.6f}")
    print(f"Log loss: {metrics.log_loss:.6f}")
    print(f"Simulated P/L: {metrics.simulated_pnl:.6f}")


if __name__ == "__main__":
    main()
