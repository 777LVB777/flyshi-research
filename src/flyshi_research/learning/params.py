"""Every tunable parameter of the learning system, in one place.

!! THE DEFAULTS BELOW ARE PLACEHOLDERS !!

Unless a parameter is marked "preregistered" or "decided" in ``PARAMETER_TABLE``,
its default is an unverified placeholder that exists so the code runs and the
tests have something to hold. ("decided" = a design choice made by the project on
stated grounds, recorded in docs/design/mb-learning-interface.md; it is not a
tuned value, but it is not a preregistered hypothesis either.)

Placeholders must be set (from documented reasoning or from TRAINING data only)
and frozen BEFORE the preregistered experiment. They must never be tuned on the
results of the experiment they are meant to be preregistered for.
``LearningParams.to_json()`` gives a canonical dump that can be hashed/committed
when the values are frozen.

Nothing here imports numpy or Brian2; this module is plain dataclasses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Tuple

# How MBON instances are combined into one CIRCUIT score (see readout.py).
AGG_TYPE_MEAN = "type_mean"  # DEFAULT: mean within each cell type, then one vote per type
AGG_INSTANCE_SUM = "instance_sum"  # named variant: plain sum over instances
AGGREGATIONS = (AGG_TYPE_MEAN, AGG_INSTANCE_SUM)

PLACEHOLDER_NOTICE = (
    "Defaults are PLACEHOLDERS, not tuned values. Set and freeze them before the "
    "preregistered experiment; never tune them on that experiment's results."
)


# --------------------------------------------------------------------------- #
# encoder
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeatureSpec:
    """One market feature and how it is turned into a Kenyon-cell firing rate.

    ``min_value``/``max_value`` are the feature's bounded range: values outside
    it are clipped (and the clipping is reported). The value is then mapped
    linearly onto ``[EncoderParams.min_rate_hz, EncoderParams.max_rate_hz]``.

    ``mirror_for_no``: under the NO framing of Option B this feature is
    reflected about its range midpoint (``v -> min + max - v``). For price on
    [0, 1] that is exactly ``p -> 1 - p``. DECIDED RULE: a feature is mirrored
    if it is evidence for or against YES (price, recent_change, signal), and is
    not mirrored if it means the same thing for both framings (time to
    resolution, liquidity). See docs/design/mb-learning-interface.md, 4a.

    ``required``: encoding raises if a required feature is missing. The synthetic
    signal feature is optional because real markets do not have it; its KC pool
    is still allocated so pools do not shift between synthetic and real runs.
    """

    name: str
    min_value: float
    max_value: float
    mirror_for_no: bool = False
    required: bool = True

    def __post_init__(self) -> None:
        if not self.max_value > self.min_value:
            raise ValueError(f"feature {self.name!r}: max_value must exceed min_value")


def _default_features() -> Tuple[FeatureSpec, ...]:
    return (
        FeatureSpec("price", 0.0, 1.0, mirror_for_no=True),
        # change in quoted probability over a lookback window (window: undecided)
        FeatureSpec("recent_change", -0.2, 0.2, mirror_for_no=True),
        # days; 0 = resolving now
        FeatureSpec("time_to_resolution", 0.0, 365.0),
        # expects an already-normalised liquidity in [0, 1] (normalisation: undecided)
        FeatureSpec("liquidity", 0.0, 1.0),
        # synthetic markets only; evidence toward YES, so mirrored under NO
        FeatureSpec("signal", 0.0, 1.0, mirror_for_no=True, required=False),
    )


@dataclass(frozen=True)
class EncoderParams:
    pool_size: int = 100  # KCs per feature; earlier cue experiments used 100
    pool_seed: int = 20260401  # arbitrary fixed seed; freeze before prereg
    # ---- RATE BOUNDS ------------------------------------------------------- #
    # A feature's min/max value is encoded at min_rate_hz / max_rate_hz. The
    # graded-rate test (docs/design/graded-encoding.md) will cover 30, 60, 90, 120
    # and 150 Hz ONLY, and it has NOT been run: 150 Hz is still the only KC-direct
    # rate ever simulated, and no graded rate has been shown to work (UNVERIFIED).
    # So, for now, the placeholders are the ends of the range that test will cover:
    # min_rate_hz is 30 (it was 0), so the encoder cannot emit a rate below anything
    # tested. Consequence: no feature pool is ever silent, even at a feature's
    # minimum value.
    #
    # RULE once the graded test has run: min_rate_hz and max_rate_hz must EQUAL the
    # validated range - all five rates (30-150 Hz) for ACCEPTED, the chosen
    # sub-range for USABLE RANGE; on FAIL the encoder must change instead.
    # graded_check.encoder_params_for(result) builds such params and
    # graded_check.require_encoder_matches(params, result) enforces the rule. The
    # values below are placeholders and must not be used for a learning experiment
    # before that check has been made.
    min_rate_hz: float = 30.0  # rate at a feature's min_value
    max_rate_hz: float = 150.0  # rate at a feature's max_value
    features: Tuple[FeatureSpec, ...] = field(default_factory=_default_features)

    def __post_init__(self) -> None:
        if self.pool_size < 1:
            raise ValueError("pool_size must be >= 1")
        if not 0.0 <= self.min_rate_hz < self.max_rate_hz:
            raise ValueError("need 0 <= min_rate_hz < max_rate_hz")
        names = [f.name for f in self.features]
        if len(set(names)) != len(names):
            raise ValueError("duplicate feature names")


# --------------------------------------------------------------------------- #
# readout
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReadoutParams:
    # Names understood by readout.load_sign_table: "circuit_<pct>", "strict", "group".
    sign_table: str = "circuit_80"  # PREREGISTERED primary readout
    sensitivity_tables: Tuple[str, ...] = ("circuit_70", "circuit_90")  # PREREGISTERED
    robustness_tables: Tuple[str, ...] = ("strict", "group")  # PREREGISTERED
    # How MBON instances are combined. DECIDED: "type_mean" = average the
    # instances within each cell type first, then apply the sign table, so each
    # type gets one vote whatever its instance count. "instance_sum" (plain sum
    # over instances) remains available as a named variant, not the default.
    aggregation: str = AGG_TYPE_MEAN
    # Abstain unless (score_chosen - score_other) > margin_threshold. 0.0 means
    # "abstain only on ties". Must be set from TRAINING data only (design doc 4b).
    # Units: Hz, summed over types (type_mean) or over instances (instance_sum) -
    # a threshold set under one aggregation is NOT valid under the other.
    margin_threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.aggregation not in AGGREGATIONS:
            raise ValueError(f"aggregation must be one of {AGGREGATIONS}, got {self.aggregation!r}")
        if not self.margin_threshold >= 0.0:
            raise ValueError("margin_threshold must be >= 0")


# --------------------------------------------------------------------------- #
# reward
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RewardParams:
    # Profit (net of fees/spread) is divided by this, then clipped to [-1, 1].
    # 1.0 means "profit measured in stake units; +/-1 stake saturates".
    profit_scale: float = 1.0
    # Brier improvement (over the MARKET PRICE, a DECIDED baseline: it is passed
    # per market to brier_improvement_reward, so it is not a parameter here) is
    # divided by this, then clipped to [-1, 1]. 0.25 is the largest possible
    # improvement over a 0.5 baseline; improvements over a market price are
    # typically much SMALLER, so with 0.25 the accuracy arm's dopamine signal
    # will be weak. Placeholder - set from training data (UNVERIFIED).
    brier_scale: float = 0.25
    # |normalised reward| <= dead_zone -> no dopamine stimulation at all.
    dead_zone: float = 0.0
    # Dopamine-neuron stimulation rate = |normalised reward| * this. No dopamine
    # stimulation has been simulated yet, so this number is unanchored.
    dopamine_max_rate_hz: float = 150.0

    def __post_init__(self) -> None:
        if not (self.profit_scale > 0 and self.brier_scale > 0):
            raise ValueError("profit_scale and brier_scale must be > 0")
        if not 0.0 <= self.dead_zone < 1.0:
            raise ValueError("dead_zone must be in [0, 1)")
        if not self.dopamine_max_rate_hz > 0:
            raise ValueError("dopamine_max_rate_hz must be > 0")


# --------------------------------------------------------------------------- #
# plasticity
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlasticityParams:
    # Fraction of the distance to the floor closed per unit (eligibility x
    # dopamine strength x compartment mask). Effective step is clipped to [0, 1].
    learning_rate: float = 0.1
    # Weight magnitude never falls below floor_fraction * |baseline weight|.
    floor_fraction: float = 0.1
    # Fraction of the distance back to the baseline weight closed per drift step.
    drift_rate: float = 0.01
    # Drift steps applied automatically after each resolved market. The unit of
    # "one drift step" (per resolution vs per trading day) is an OPEN choice.
    drift_steps_per_resolution: int = 1
    # KCs at or below this rate (Hz) at decision time are "not recently active".
    kc_active_threshold_hz: float = 1.0
    # KC rate (Hz) at which eligibility saturates at 1. Keep consistent with the
    # KC activity actually produced by the encoder's max rate.
    kc_rate_ref_hz: float = 150.0

    def __post_init__(self) -> None:
        for name in ("learning_rate", "floor_fraction", "drift_rate"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.floor_fraction >= 1.0:
            raise ValueError("floor_fraction must be < 1 (1 would freeze all weights)")
        if self.drift_steps_per_resolution < 0:
            raise ValueError("drift_steps_per_resolution must be >= 0")
        if self.kc_active_threshold_hz < 0:
            raise ValueError("kc_active_threshold_hz must be >= 0")
        if not self.kc_rate_ref_hz > self.kc_active_threshold_hz:
            raise ValueError("kc_rate_ref_hz must exceed kc_active_threshold_hz")


# --------------------------------------------------------------------------- #
# aggregate + documentation table
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LearningParams:
    encoder: EncoderParams = field(default_factory=EncoderParams)
    readout: ReadoutParams = field(default_factory=ReadoutParams)
    reward: RewardParams = field(default_factory=RewardParams)
    plasticity: PlasticityParams = field(default_factory=PlasticityParams)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        """Canonical JSON (sorted keys) suitable for hashing when params are frozen."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


PRE = "preregistered"
PH = "placeholder"
DEC = "decided"

# (group, field, status, meaning). test_params.py asserts every dataclass field
# above appears here, so a new parameter cannot be added undocumented.
PARAMETER_TABLE: Tuple[Tuple[str, str, str, str], ...] = (
    ("encoder", "pool_size", PH, "KCs per feature pool (100 matches the earlier cue experiments)"),
    ("encoder", "pool_seed", PH, "seed for pool assignment; arbitrary, freeze before prereg"),
    ("encoder", "min_rate_hz", PH, "KC rate at a feature's min value; 30 Hz = lowest rate the graded test covers; after that test must EQUAL the validated range's low end"),
    ("encoder", "max_rate_hz", PH, "KC rate at a feature's max value; 150 Hz = highest rate the graded test covers; after that test must EQUAL the validated range's high end"),
    ("encoder", "features", PH, "per-feature value range (placeholder) and required flag; NO-framing mirroring flags are DECIDED (see FeatureSpec)"),
    ("readout", "sign_table", PRE, "primary readout: CIRCUIT with 80% dominant-family rule"),
    ("readout", "sensitivity_tables", PRE, "CIRCUIT 70% and 90% sensitivity checks"),
    ("readout", "robustness_tables", PRE, "STRICT and GROUP robustness checks"),
    ("readout", "aggregation", DEC, "type_mean (default): average instances within each type, one vote per type; instance_sum = named variant"),
    ("readout", "margin_threshold", PH, "abstain unless score margin > this (Hz, aggregation-specific); set from TRAINING data only"),
    ("reward", "profit_scale", PH, "profit divisor before clipping to [-1, 1]"),
    ("reward", "brier_scale", PH, "Brier-improvement-over-market divisor before clipping to [-1, 1] (likely too large for market baseline)"),
    ("reward", "dead_zone", PH, "|reward| at or below this gives no dopamine stimulation"),
    ("reward", "dopamine_max_rate_hz", PH, "PAM/PPL1 stimulation rate at |reward| = 1 (unanchored)"),
    ("plasticity", "learning_rate", PH, "fraction of distance to floor closed per unit gate"),
    ("plasticity", "floor_fraction", PH, "min weight magnitude as a fraction of the connectome weight"),
    ("plasticity", "drift_rate", PH, "fraction of distance back to connectome weight closed per drift step"),
    ("plasticity", "drift_steps_per_resolution", PH, "drift steps applied after each resolved market"),
    ("plasticity", "kc_active_threshold_hz", PH, "KC rate at/below which a KC is not 'recently active'"),
    ("plasticity", "kc_rate_ref_hz", PH, "KC rate at which eligibility saturates at 1"),
)


def declared_fields() -> List[Tuple[str, str]]:
    """(group, field) for every parameter dataclass field; used by tests."""
    out: List[Tuple[str, str]] = []
    for group in fields(LearningParams):
        for f in fields(getattr(LearningParams(), group.name)):
            out.append((group.name, f.name))
    return out


def describe(params: LearningParams = None) -> str:
    """Human-readable table of every parameter, its value, status and meaning."""
    p = params or LearningParams()
    lines = [PLACEHOLDER_NOTICE, ""]
    lines.append(f"{'parameter':<44} {'status':<13} value  --  meaning")
    for group, name, status, meaning in PARAMETER_TABLE:
        value = getattr(getattr(p, group), name)
        if name == "features":
            value = ", ".join(
                f"{f.name}[{f.min_value:g},{f.max_value:g}]"
                f"{'~' if f.mirror_for_no else ''}{'' if f.required else '?'}"
                for f in value
            )
        lines.append(f"{group + '.' + name:<44} {status:<13} {value}  --  {meaning}")
    return "\n".join(lines)
