"""Skin sweep: a tear must count, a legitimate outline must not."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.cli import main
from reference_asset_compiler.skin_integrity import RENDER_SCHEMA, analyse, measure_frame


def figure(size=64):
    """A grey torso with two legs that reach the bottom edge, on transparency."""
    rgba = np.zeros((size, size, 4), np.float32)
    rgba[8:40, 20:44] = (.6, .6, .6, 1)
    rgba[40:64, 20:30] = rgba[40:64, 34:44] = (.6, .6, .6, 1)
    return rgba


def test_clean_figure_has_no_findings_and_gap_between_legs_is_outside():
    measured, _ = measure_frame(figure(), split_width_px=4)
    assert measured["split_px"] == measured["opening_px"] == measured["backface_px"] == 0
    assert measured["blobs"] == []


def test_thin_tear_is_a_split_and_a_wide_hole_is_an_opening():
    rgba = figure()
    rgba[20:30, 31:33, 3] = 0           # 2 px wide slit through the torso
    rgba[12:18, 22:28, 3] = 0           # 6 px square hole
    measured, masks = measure_frame(rgba, split_width_px=4)
    assert measured["split_px"] == 20 and measured["opening_px"] == 36
    assert masks["split"][25, 31] and masks["opening"][15, 25]
    split = next(b for b in measured["blobs"] if b["kind"] == "split")
    assert split["bbox_xywh"] == [31, 20, 2, 10] and split["max_width_px"] <= 4


def test_exposed_back_faces_are_counted_inside_the_figure_only():
    rgba = figure()
    rgba[30:34, 24:28] = (1, 0, 1, 1)
    rgba[0:2, 0:2] = (1, 0, 1, 0)       # magenta in the transparent background does not count
    measured, _ = measure_frame(rgba, split_width_px=4)
    assert measured["backface_px"] == 16 and measured["split_px"] == 0


@pytest.mark.parametrize("bad", [np.zeros((8, 8, 3)), np.full((8, 8, 4), np.nan)])
def test_invalid_images_fail_closed(bad):
    with pytest.raises(ValueError, match="RGBA"):
        measure_frame(bad, split_width_px=4)


def write_renders(root, rgba_by_view):
    root.mkdir(parents=True)
    frames = []
    for view, rgba in rgba_by_view.items():
        name = "Walk/s00-{0}.png".format(view)
        (root / "Walk").mkdir(exist_ok=True)
        Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(root / name)
        frames.append({"clip": "Walk", "sample": 0, "time_s": 0.0, "view": view, "image": name})
    (root / "sweep.json").write_text(json.dumps({
        "schema": RENDER_SCHEMA, "asset": "animated.glb", "asset_sha256": "0" * 64, "resolution": 64,
        "pixels_per_metre": 200.0, "views": {"front": 0, "side": 90}, "backface_rgb": [1, 0, 1],
        "frames": frames}), encoding="utf-8")
    return root


def test_report_gates_only_against_a_baseline(tmp_path):
    clean = write_renders(tmp_path / "clean", {"front": figure(), "side": figure()})
    torn = figure()
    torn[20:30, 31:33, 3] = 0
    candidate = write_renders(tmp_path / "torn", {"front": torn, "side": figure()})

    first = analyse(clean, tmp_path / "baseline")
    assert first["checks_passed"] is None and first["frames"] == 2
    report = json.loads((tmp_path / "baseline" / "report.json").read_text())
    assert not report["human_approved"] and report["limitations"]
    assert (tmp_path / "baseline" / report["frames"][0]["overlay"]).is_file()

    baseline = tmp_path / "baseline" / "report.json"
    # 20 split pixels pass a 32 px tolerance and fail a 4 px one.
    assert analyse(candidate, tmp_path / "loose", baseline, tolerance_px=32)["checks_passed"] is True
    strict = analyse(candidate, tmp_path / "strict", baseline, tolerance_px=4)
    assert strict["checks_passed"] is False and strict["regressions"] == 1


def test_cli_exit_code_and_fresh_output(tmp_path):
    clean = write_renders(tmp_path / "clean", {"front": figure()})
    torn = figure()
    torn[20:30, 31:33, 3] = 0
    candidate = write_renders(tmp_path / "torn", {"front": torn})
    assert main(["animation", "skin-sweep", str(clean), "--output", str(tmp_path / "a")]) == 0
    baseline = str(tmp_path / "a" / "report.json")
    assert main(["animation", "skin-sweep", str(candidate), "--output", str(tmp_path / "b"),
                 "--baseline", baseline, "--tolerance-px", "4"]) == 1
    with pytest.raises(ValueError, match="fresh"):
        analyse(clean, tmp_path / "a")


def test_baseline_with_different_settings_or_missing_frames_is_refused(tmp_path):
    clean = write_renders(tmp_path / "clean", {"front": figure()})
    analyse(clean, tmp_path / "a")
    with pytest.raises(ValueError, match="settings"):
        analyse(clean, tmp_path / "b", tmp_path / "a" / "report.json", split_width_m=0.05)
    wider = write_renders(tmp_path / "wider", {"front": figure(), "back": figure()})
    result = analyse(wider, tmp_path / "c", tmp_path / "a" / "report.json")
    assert result["checks_passed"] is False and result["unmatched"] == 1
