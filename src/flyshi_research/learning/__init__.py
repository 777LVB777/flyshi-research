"""Pure-logic components of the mushroom-body learning interface.

numpy is the only dependency; nothing here imports Brian2 or runs a simulation.
Runs under Python >= 3.10 (the brain-model venv). Design record:
docs/design/mb-learning-interface.md and docs/design/readout-and-plasticity-options.md.

Every tunable default lives in :mod:`flyshi_research.learning.params` and is a
PLACEHOLDER until frozen before the preregistered experiment.
"""
