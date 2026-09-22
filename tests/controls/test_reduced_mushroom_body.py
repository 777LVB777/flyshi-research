from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.controls.reduced_mushroom_body import (  # noqa: E402
    PAPER_MV_LEARNING_RATE,
    BennettMarketAgent,
    BennettMixedValenceMB,
    normalized_stimulus_vector,
    run_market_sequence,
)
from flyshi_research.learning.encoder import KCEncoder  # noqa: E402
from flyshi_research.simulator import (  # noqa: E402
    Action,
    MarketObservation,
    generate_signal_markets,
)


def paper_cues() -> tuple[np.ndarray, np.ndarray]:
    yes = np.r_[np.ones(10), np.zeros(10)]
    no = np.r_[np.zeros(10), np.ones(10)]
    return yes, no


def test_source_equations_have_a_hand_computed_one_step_answer() -> None:
    model = BennettMixedValenceMB(20, seed=1)
    approach = np.full(20, 0.06)
    avoidance = np.full(20, 0.04)
    model.set_weights(approach, avoidance)
    yes, no = paper_cues()

    response = model.response(yes)
    assert response.approach_rate == pytest.approx(0.6)
    assert response.avoidance_rate == pytest.approx(0.4)
    assert response.reinforcement_prediction == pytest.approx(0.2)

    decision = model.decide(yes, no, forced_action=Action.YES)
    assert decision.forecast_probability == pytest.approx(0.5)
    step = model.reward(1.0)
    assert step.approach_dan_rate == pytest.approx(10.8)
    assert step.avoidance_dan_rate == pytest.approx(9.2)
    assert step.dan_difference == pytest.approx(1.6)
    expected_delta = PAPER_MV_LEARNING_RATE * 1.6
    assert np.allclose(model.approach_weights[:10], 0.06 + expected_delta)
    assert np.allclose(model.avoidance_weights[:10], 0.04 - expected_delta)
    assert np.array_equal(model.approach_weights[10:], approach[10:])


def test_seed_repeats_initial_weights_and_sampled_decisions() -> None:
    yes, no = paper_cues()
    first = BennettMixedValenceMB(20, seed=42)
    repeat = BennettMixedValenceMB(20, seed=42)
    assert np.array_equal(first.approach_weights, repeat.approach_weights)
    assert np.array_equal(first.avoidance_weights, repeat.avoidance_weights)
    for _ in range(8):
        a = first.decide(yes, no)
        b = repeat.decide(yes, no)
        assert a == b
        first.reward(0.25)
        repeat.reward(0.25)


def test_weight_floor_and_train_then_freeze_contract() -> None:
    yes, no = paper_cues()
    model = BennettMixedValenceMB(20, seed=3)
    model.set_weights(np.zeros(20), np.full(20, 0.01))
    model.decide(yes, no, forced_action=Action.YES)
    model.reward(-10.0)
    assert np.all(model.approach_weights >= 0.0)
    model.freeze()
    before = (model.approach_weights, model.avoidance_weights)
    model.decide(yes, no)
    with pytest.raises(RuntimeError, match="frozen"):
        model.reward(1.0)
    assert np.array_equal(model.approach_weights, before[0])
    assert np.array_equal(model.avoidance_weights, before[1])


def test_market_adapter_reuses_encoder_and_normalises_both_framings() -> None:
    kc_ids = np.arange(1000, 1900, dtype=np.int64)
    encoder = KCEncoder(kc_ids)
    observation = MarketObservation(
        quote=0.72,
        signal=0.61,
        recent_change=0.08,
        time_to_resolution=20.0,
        liquidity=0.45,
    )
    pair = encoder.option_b_stimuli(BennettMarketAgent._features(observation))
    yes = normalized_stimulus_vector(pair.yes, kc_ids)
    no = normalized_stimulus_vector(pair.no, kc_ids)
    assert np.sum(yes) == pytest.approx(10.0)
    assert np.sum(no) == pytest.approx(10.0)

    agent = BennettMarketAgent(kc_ids, seed=5, encoder=encoder)
    decision = agent.decide(observation)
    assert 0.0 <= decision.forecast_probability <= 1.0
    assert decision.action in (Action.YES, Action.NO)
    agent.reward(0.5)


def test_identical_synthetic_markets_use_chronological_split_and_shared_calibration() -> None:
    markets = generate_signal_markets(12, seed=91, signal_strength=0.4)
    agent = BennettMarketAgent(np.arange(900, dtype=np.int64), seed=7)
    seen_sequences = []

    def reinforcement(market, decision):
        seen_sequences.append(market.sequence)
        return (market.outcome - market.quote) if decision.action is Action.YES else (
            market.quote - market.outcome
        )

    result = run_market_sequence(markets, agent, train_count=8, reinforcement=reinforcement)
    assert seen_sequences == list(range(8))
    assert [row["sequence"] for row in result["train"]] == list(range(8))
    assert [row["sequence"] for row in result["test"]] == list(range(8, 12))
    assert all("calibrated_probability" in row for row in result["test"])
    assert agent.model.learning_enabled is False


def test_reproduces_fig3d_step_schedule_tracking_with_prestated_tolerance() -> None:
    """Qualitative Fig. 3d reproduction; endpoint RMSE tolerance is documented."""
    yes, no = paper_cues()
    block_values = np.asarray([0.0, 1.0, 2.0, 1.0, 0.0, -1.0, -2.0, -1.0, 0.0])
    schedule = np.repeat(block_values, 20)
    predictions = np.empty((10, schedule.size), dtype=float)
    for run in range(10):
        model = BennettMixedValenceMB(20, seed=100 + run)
        noise = np.random.default_rng(1000 + run)
        for trial, mean_reinforcement in enumerate(schedule):
            model.decide(yes, no, forced_action=Action.YES)
            predictions[run, trial] = model.response(yes).reinforcement_prediction
            model.reward(mean_reinforcement + noise.normal(0.0, 0.1))
    block_end_mean = np.mean(predictions[:, 19::20], axis=0)
    rmse = float(np.sqrt(np.mean((block_end_mean - block_values) ** 2)))
    assert rmse <= 0.15, (rmse, block_end_mean)
