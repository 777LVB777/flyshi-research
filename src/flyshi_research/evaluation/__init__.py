"""Pure-numpy evaluation metrics, calibration, and conventional baselines.

Nothing in this package imports Brian2 or runs a brain simulation.  The public
types used for observations and decisions come from :mod:`flyshi_research.simulator`.
"""

from .calibration import CalibratedPredictions, PlattScaler, fit_and_apply_calibration

__all__ = [
    "CalibratedPredictions",
    "PlattScaler",
    "fit_and_apply_calibration",
]
