"""Pins the design-doc statements that record decisions and results (2026-09-21), so they
cannot silently regress. Whitespace-normalised: independent of line wrapping."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def doc(name: str) -> str:
    return " ".join((REPO / "docs" / "design" / name).read_text().split())


DESIGN = doc("mb-learning-interface.md")
GRADED = doc("graded-encoding.md")


def section(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a:text.index(end, a)]


def test_reward_is_described_as_an_abstract_teaching_signal_not_stimulation():
    s4c = section(DESIGN, "### 4c. REWARD", "### 4d.")
    for needle in ("represent dopamine **abstractly**", "Why not stimulate the dopamine neurons",
                   "biological grounding is the compartment map",
                   "We do not simulate dopamine release or dopamine neuron activity during learning",
                   "never given to the network"):
        assert needle in s4c, needle
    assert "teaching signal" in s4c.split("###")[1][:200]  # the heading itself


def test_no_text_says_reward_is_delivered_by_stimulating_dopamine_neurons():
    banned = [
        r"we teach the circuit by directly stimulating",
        r"We stimulate PAM \(reward\) or PPL1",
        r"stimulate reward or punishment dopamine neurons",
        r"we stimulate .reward. neurons",
        r"Directly stimulating dopamine neurons",
        r"barely activated these dopamine neurons",
    ]
    for pattern in banned:
        assert not re.search(pattern, DESIGN, re.IGNORECASE), pattern


def test_section_10_says_we_do_not_simulate_dopamine_release_or_activity():
    s10 = section(DESIGN, "## 10. What we will NOT claim", "## 11.")
    assert "We do not simulate dopamine release or dopamine-neuron activity during learning" in s10
    assert "compartment map" in s10 and "unverified" in s10


def test_graded_result_is_recorded_in_both_documents():
    results = GRADED[GRADED.index("## Results"):]
    for needle in ("Verdict: ACCEPTED", "222.88 Hz", "15.30 Hz", "−9.6", "−66.8",
                   "Strictly monotonic across all five rates: yes, and decreasing",
                   "0.00 Hz", "Validated range: 30–150 Hz"):
        assert needle in results, needle
    assert "the verdict is ACCEPTED" in DESIGN and "222.9 Hz against a threshold of 15.3 Hz" in DESIGN
    assert "no criterion in this document was changed after the run" in GRADED


def test_intensity_bias_is_documented_with_both_options_undecided_and_the_sign_caveat():
    p4 = section(DESIGN, "4. **An intensity bias", "**The separation score, defined precisely")
    for needle in ("30 + 0.8 × 120 = 126 Hz", "54 Hz", "innately prefers NO whenever YES is the expensive side",
                   "(a) Total-drive balancing", "(b) Innate-score subtraction",
                   "*Costs:*", "*Could hide:*", "**Not decided.**",
                   "STRICT (0.0 → +53.2) and GROUP (+10.8 → +77.6) rise",
                   "the direction depends on the readout",
                   "first learning test", "is unaffected", "constant 150 Hz",
                   "Any market experiment must address this bias first"):
        assert needle in p4, needle
    assert p4.count("*Costs:*") == 2 and p4.count("*Could hide:*") == 2  # each option states both
    assert "The intensity bias must be addressed before any market experiment" in DESIGN
    assert "four real problems" in DESIGN


def test_first_learning_spec_records_both_pre_run_decisions():
    spec = doc("first-learning-test.md")
    assert "no dopamine release or dopamine-neuron activity is simulated" in spec
    assert "control (c) demoted" in spec and "reported diagnostic" in spec
    assert "Control (c) alone can never produce this verdict" in spec
    assert "The intensity bias found by the graded-rate test does not affect this test" in spec


def test_gamma3_variant_is_preregistered_in_both_documents_with_its_rationale():
    readout = doc("readout-and-plasticity-options.md")
    g3 = section(readout, "### γ3 sensitivity variant", "### Multi-compartment types")
    spec = doc("first-learning-test.md")
    s5b = section(spec, "## 5b. Readout sensitivity variants", "## 6.")
    for text in (g3, s5b):
        for needle in ("MBON08 and MBON09", "largest", "intensity bias", "contradicts",
                       "readout only", "circuit_80_no_gamma3", "before any"):
            assert needle.lower() in text.lower(), needle
    assert "**None of them can change the primary verdict.**" in s5b
    assert "readout sensitivity variants preregistered" in spec  # revision history


def test_parallel_split_is_in_the_spec_and_changes_no_criterion():
    spec = doc("first-learning-test.md")
    s10 = section(spec, "## 10. Parallel execution", "## Revision history")
    for needle in ("35 independent **jobs**", "**strictly sequential**", "byte-identical",
                   "Control (a) tests it directly", "not measured on the server"):
        assert needle in s10, needle
    assert "split into parallel jobs" in spec and "No criterion, seed, parameter or run count changed" in spec


CLOUD = REPO / "docs" / "cloud"
SETUP = REPO / "scripts" / "cloud" / "setup.sh"


def test_server_guide_covers_every_required_step_and_separates_roles():
    g = " ".join((CLOUD / "server-setup.md").read_text().split())
    for needle in ("## Who does what", "You must do these personally", "An AI agent can do these",
                   "ssh-keygen -t ed25519", "Add SSH Key", "ssh flyshi", "ufw allow OpenSSH",
                   "ufw --force enable", "PasswordAuthentication no", "setup.sh", "tmux new -s fly",
                   "Ctrl-b", "tmux attach -t fly", "rsync", "git", "## Step 12 — DELETE the server",
                   "Powering the server off does NOT stop billing", "Never give an AI agent"):
        assert needle in g, needle


def test_cost_estimate_matches_the_launcher_schedule():
    c = " ".join((CLOUD / "cost-estimate.md").read_text().split())
    for needle in ("| **CCX33** | 5 | 52 | **26 min** | **8.7 h** |",
                   "| **CCX43** | 11 | 46 | **23 min** | **7.7 h** |",
                   "| 1 | 260 | 2.2 h | 43.3 h |", "42 runs back to back",
                   "unverified", "Nothing here has been measured on a server"):
        assert needle in c, needle


def test_setup_script_pins_match_the_reproduction_records():
    s = SETUP.read_text()
    shiu = (REPO / "docs" / "reproduction" / "shiu2024.md").read_text()
    mb = (REPO / "docs" / "reproduction" / "mushroom_body_check.md").read_text()
    lock = (REPO / "repro" / "shiu2024" / "requirements-lock.txt").read_text().split()
    up = re.search(r'UPSTREAM_COMMIT="([0-9a-f]{40})"', s).group(1)
    ann = re.search(r'ANNOT_COMMIT="([0-9a-f]{40})"', s).group(1)
    assert up == "91bdd1e7dcf193f3e7ca5a8933497fcef63b7960" and up in shiu
    assert ann in mb and 'ANNOT_TAG="v3.1.0"' in s
    assert "cython==0.29.33" in lock and "setuptools==67.8.0" in lock
    assert "-r \"$LOCK\"" in s and "--no-deps -e ." in s  # the package cannot move a pin
    assert s.startswith("#!/usr/bin/env bash") and "set -Eeuo pipefail" in s
    assert "trap " in s and "SETUP FAILED" in s
    for needle in ("pytest tests/ -q", "fast_runner.py --self-test", 'prefs.codegen.target = "cython"'):
        assert needle in s, needle


def test_setup_script_parses():
    import subprocess
    subprocess.run(["bash", "-n", str(SETUP)], check=True)
