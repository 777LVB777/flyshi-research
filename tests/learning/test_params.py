from __future__ import annotations

import json
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.learning import params as P  # noqa: E402


def test_every_parameter_field_is_documented_exactly_once():
    documented = [(g, n) for g, n, _, _ in P.PARAMETER_TABLE]
    assert sorted(documented) == sorted(P.declared_fields())
    assert len(documented) == len(set(documented))


def test_statuses_are_known_and_only_readout_tables_are_preregistered():
    assert {s for _, _, s, _ in P.PARAMETER_TABLE} <= {P.PRE, P.PH, P.DEC}
    pre = {(g, n) for g, n, s, _ in P.PARAMETER_TABLE if s == P.PRE}
    assert pre == {("readout", "sign_table"), ("readout", "sensitivity_tables"),
                   ("readout", "robustness_tables")}
    decided = {(g, n) for g, n, s, _ in P.PARAMETER_TABLE if s == P.DEC}
    assert decided == {
        ("encoder", "pool_size"),
        ("encoder", "pool_seed"),
        ("encoder", "balance_pool_size"),
        ("encoder", "option_b_variant"),
        ("encoder", "min_rate_hz"),
        ("encoder", "max_rate_hz"),
        ("readout", "aggregation"),
        ("reward", "profit_scale"),
        ("reward", "brier_scale"),
        ("reward", "dead_zone"),
        ("plasticity", "learning_rate"),
        ("plasticity", "floor_fraction"),
        ("plasticity", "drift_rate"),
        ("plasticity", "drift_steps_per_resolution"),
        ("plasticity", "kc_active_threshold_hz"),
        ("plasticity", "kc_rate_ref_hz"),
    }


def test_readout_aggregation_default_is_type_mean_with_sum_as_named_variant():
    assert P.ReadoutParams().aggregation == "type_mean"
    assert P.AGGREGATIONS == ("type_mean", "instance_sum")
    assert P.ReadoutParams(aggregation="instance_sum").aggregation == "instance_sum"


def test_owner_decisions_of_2026_09_22_are_the_defaults():
    """docs/design/open-decisions.md, items 3 and 4."""
    r = P.RewardParams()
    assert (r.brier_scale, r.dead_zone) == (0.04, 0.0)
    assert P.PlasticityParams().drift_steps_per_resolution == 1
    # drift disabled is a preregistered sensitivity check, so it must be expressible
    assert P.PlasticityParams(drift_rate=0.0).drift_rate == 0.0


def test_owner_decisions_of_2026_09_30_lock_the_learning_demonstrated_values():
    """docs/design/open-decisions.md, item 5: carried forward unchanged from the
    first learning test's configuration (tag layer3-learning-demonstrated)."""
    assert P.RewardParams().profit_scale == 1.0
    pl = P.PlasticityParams()
    assert (pl.learning_rate, pl.floor_fraction, pl.drift_rate) == (0.1, 0.1, 0.01)
    # drift disabled remains a preregistered sensitivity check
    assert P.PlasticityParams(drift_rate=0.0).drift_rate == 0.0


def test_decided_values_equal_the_first_learning_test_configuration():
    """The locked defaults must match the saved config of the run that demonstrated
    learning, so they cannot drift from it silently."""
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[2] / "repro" / "mushroom_body"
                         / "results" / "first_learning_6fea97ac91" / "config.json").read_text())
    pl, r = P.PlasticityParams(), P.RewardParams()
    for name in ("learning_rate", "floor_fraction", "drift_rate"):
        assert getattr(pl, name) == config["plasticity"][name], name
    assert r.profit_scale == config["reward"]["profit_scale"]
    assert r.brier_scale == config["reward"]["brier_scale"]


def test_brier_baseline_is_not_a_tunable_parameter():
    """Decided: the baseline is the market price, passed per market."""
    assert not hasattr(P.RewardParams(), "brier_baseline_prob")
    assert "brier_baseline_prob" not in P.LearningParams().to_json()


def test_describe_flags_defaults_as_placeholders_and_lists_everything():
    text = P.describe()
    assert "PLACEHOLDER" in text and "never tune" in text
    for g, n, _, _ in P.PARAMETER_TABLE:
        assert f"{g}.{n}" in text


def test_preregistered_readout_defaults():
    r = P.ReadoutParams()
    assert r.sign_table == "circuit_80"
    assert r.sensitivity_tables == ("circuit_70", "circuit_90")
    assert r.robustness_tables == ("strict", "group")


def test_defaults_are_json_serialisable_and_stable():
    a, b = P.LearningParams().to_json(), P.LearningParams().to_json()
    assert a == b
    loaded = json.loads(a)
    assert set(loaded) == {"encoder", "readout", "reward", "plasticity"}
    assert loaded["encoder"]["features"][0]["name"] == "price"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: P.EncoderParams(pool_size=0),
        lambda: P.EncoderParams(min_rate_hz=200.0, max_rate_hz=100.0),
        lambda: P.FeatureSpec("x", 1.0, 1.0),
        lambda: P.ReadoutParams(margin_threshold=-1.0),
        lambda: P.RewardParams(profit_scale=0.0),
        lambda: P.ReadoutParams(aggregation="median"),
        lambda: P.RewardParams(dead_zone=1.0),
        lambda: P.PlasticityParams(learning_rate=1.5),
        lambda: P.PlasticityParams(floor_fraction=1.0),
        lambda: P.PlasticityParams(drift_rate=-0.1),
        lambda: P.PlasticityParams(kc_rate_ref_hz=0.5, kc_active_threshold_hz=1.0),
    ],
)
def test_invalid_parameters_rejected(factory):
    with pytest.raises(ValueError):
        factory()


def test_learning_package_never_imports_brian2():
    """Purity: importing every module must not pull in Brian2 or run a simulator."""
    code = (
        "import sys\n"
        "import flyshi_research.learning.params, flyshi_research.learning.encoder, "
        "flyshi_research.learning.readout, flyshi_research.learning.reward, "
        "flyshi_research.learning.plasticity\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('brian2', 'pandas', 'scipy')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_encoder_rate_bounds_are_the_accepted_left_only_mirrored_range():
    """Decided 2026-10-09: 30-150 Hz is the range under which the left-only,
    mirrored, unbalanced encoder was ACCEPTED (commit c084908)."""
    e = P.EncoderParams()
    assert (e.min_rate_hz, e.max_rate_hz) == (30.0, 150.0)  # min was 0 before 2026-09-21
    rows = {(g, n): (st, m) for g, n, st, m in P.PARAMETER_TABLE}
    for key in (("encoder", "min_rate_hz"), ("encoder", "max_rate_hz")):
        status, meaning = rows[key]
        assert status == P.DEC and "ACCEPTED" in meaning
        assert "pending" not in meaning


def test_owner_decisions_of_2026_10_09_encoder_and_eligibility():
    """Validated (ACCEPTED graded test) or in force in a passed test (first learning)."""
    e, pl = P.EncoderParams(), P.PlasticityParams()
    assert (e.pool_size, e.pool_seed) == (100, 20260401)
    assert (pl.kc_active_threshold_hz, pl.kc_rate_ref_hz) == (1.0, 150.0)
    assert pl.kc_rate_ref_hz == e.max_rate_hz
    # feature ranges stay placeholders: not decided on 2026-10-09
    assert [st for g, n, st, _ in P.PARAMETER_TABLE if (g, n) == ("encoder", "features")] == [P.PH]
