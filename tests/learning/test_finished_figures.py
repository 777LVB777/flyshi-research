"""Paper figures from finished results: SVG output, pre-stated thresholds drawn, values
taken from the records, and never a read of a synthetic-sweep or Phase 2 file."""

from __future__ import annotations

import builtins
import importlib.util
import io
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("numpy")

REPO = Path(__file__).resolve().parents[2]
FIG_DIR = REPO / "repro" / "figures"


def _load():
    sys.path.insert(0, str(FIG_DIR))
    spec = importlib.util.spec_from_file_location("make_finished_figures_test", FIG_DIR / "make_finished_figures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MF = _load()
RESULTS = REPO / "repro" / "mushroom_body" / "results"


def test_every_figure_is_well_formed_svg_with_labelled_axes_and_its_sources(tmp_path):
    manifest = MF.make(tmp_path, png=False)
    assert set(manifest["figures"]) == set(MF.FIGURES) and len(manifest["figures"]) == 6
    for name, entry in manifest["figures"].items():
        text = (tmp_path / entry["svg"]).read_text()
        ET.fromstring(text)  # well-formed XML
        assert "(Hz" in text or "fraction" in text, name  # units on an axis
        assert "pre-stated" in text, name  # the pre-stated threshold is drawn and labelled
        assert entry["png"] is None and entry["sources"]
        for src, digest in entry["sources"].items():
            assert (REPO / src).exists() and len(digest) == 64
    assert json.loads((tmp_path / "MANIFEST.json").read_text()) == manifest


def test_figures_show_the_recorded_numbers(tmp_path):
    MF.make(tmp_path, png=False)
    fig1 = (tmp_path / "fig1_first_learning.svg").read_text()
    assert "LEARNING DEMONSTRATED" in fig1 and "3σ = 6.54 Hz" in fig1 and "3σ_B = 4.85 Hz" in fig1
    fig2 = (tmp_path / "fig2_first_learning_ignition_recheck.svg").read_text()
    assert "154.49 Hz, 159.25 Hz" in fig2
    graded = json.loads((RESULTS / "graded_left_mirrored_verdict.json").read_text())
    fig4 = (tmp_path / "fig4_graded_encoding.svg").read_text()
    assert graded["verdict"] in fig4 and f"{graded['endpoint_threshold_hz']:.1f} Hz" in fig4
    fig3 = (tmp_path / "fig3_population_scaling_ignition.svg").read_text()
    assert "left-only runs 1/24" in fig3 and "1% ignition label" in fig3
    fig6 = (tmp_path / "fig6_low_drive_followup.svg").read_text()
    assert "3/100" in fig6 and "below 25 kHz" in fig6


def test_no_synthetic_sweep_or_phase2_file_is_ever_read(tmp_path, monkeypatch):
    opened = []
    real_open, real_io_open = builtins.open, io.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def spy_io(file, *a, **k):
        opened.append(str(file))
        return real_io_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy_io)
    MF.make(tmp_path, png=False)
    results_reads = [p for p in opened if "/results/" in p]
    assert results_reads and not [p for p in opened if MF.FORBIDDEN.search(p)]
    allowed_roots = (str(MF.FIRST_LEARNING), str(MF.RECHECK), str(MF.LEFT_SCALING), str(MF.POP_SCALING),
                     str(MF.GRADED), str(MF.POOL_ID), str(MF.LOW_DRIVE))
    assert all(p.startswith(allowed_roots) for p in results_reads), \
        [p for p in results_reads if not p.startswith(allowed_roots)]
    for bad in ("repro/mushroom_body/results/synthetic_market_a325e6b206/parts/x.json",
                "data/polymarket/phase2_abc/verdict.json"):
        with pytest.raises(PermissionError):
            MF.read_json(REPO / bad)


@pytest.mark.skipif(shutil.which("qlmanage") is None or shutil.which("sips") is None,
                    reason="PNG rendering uses macOS qlmanage and sips")
def test_png_has_the_figure_aspect(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(MF, "FIGURES", {"fig4_graded_encoding": MF.FIGURES["fig4_graded_encoding"]})
    manifest = MF.make(tmp_path, png=True)
    png = tmp_path / manifest["figures"]["fig4_graded_encoding"]["png"]
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(png)], capture_output=True, text=True).stdout
    w = int(out.split("pixelWidth:")[1].split()[0])
    h = int(out.split("pixelHeight:")[1].split()[0])
    assert w == 1800 and h == round(1800 * 520 / 1100)
