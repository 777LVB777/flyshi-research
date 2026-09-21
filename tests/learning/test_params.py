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
    assert {s for _, _, s, _ in P.PARAMETER_TABLE} <= {P.PRE, P.PH}
    pre = {(g, n) for g, n, s, _ in P.PARAMETER_TABLE if s == P.PRE}
    assert pre == {("readout", "sign_table"), ("readout", "sensitivity_tables"),
                   ("readout", "robustness_tables")}


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
        lambda: P.RewardParams(brier_baseline_prob=1.5),
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
