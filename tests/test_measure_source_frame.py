"""Measuring a profile's source_camera block from alpha-cut pictures.

Synthetic figures with a known box stand in for the guidance pictures: a soft
alpha edge, a stray speck, a side figure drawn a little lower than the front.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_source_frame as msf  # noqa: E402

W, H = 200, 300


def picture(rows, cols, size=(W, H), speck=False, soft=True):
    """Alpha (H, W) in 0..1: an opaque rectangle over rows r0..r1 and cols c0..c1 (inclusive)."""
    w, h = size
    alpha = np.zeros((h, w))
    (r0, r1), (c0, c1) = rows, cols
    if soft:
        # A one-pixel ring at 100/255: outside the figure at the default threshold.
        alpha[r0 - 1:r1 + 2, c0 - 1:c1 + 2] = 100 / 255
    alpha[r0:r1 + 1, c0:c1 + 1] = 1.0
    if speck:
        alpha[5:7, 5:7] = 1.0
    return alpha


def save(path, alpha):
    rgba = np.zeros(alpha.shape + (4,), np.uint8)
    rgba[..., :3] = 128
    rgba[..., 3] = np.round(alpha * 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(path)
    return str(path)


# Front: rows 40..239 (200 px tall), cols 60..119; side: rows 42..241, cols 130..169.
FRONT = dict(rows=(40, 239), cols=(60, 119))
SIDE = dict(rows=(42, 241), cols=(130, 169))


def test_block_from_known_boxes():
    block, measurement, warnings = msf.measure_frame(
        picture(**FRONT, speck=True), picture(**SIDE), height_m=1.6)
    assert block == {
        "image_px": [W, H],
        "px_per_m": 125.0,                  # 200 rows / 1.6 m
        "front_origin_px": [90.0, 140.0],   # box [60, 40, 120, 240]
        "side_origin_px": [150.0, 140.0],   # the side's own x, the front's y
    }
    assert measurement["front"]["box_px"] == [60, 40, 120, 240]
    assert measurement["front"]["specks_dropped"] == 1
    assert measurement["side"]["centre_px"] == [150.0, 142.0]
    assert measurement["side"]["height_vs_front"] == 1.0
    assert warnings == []


def test_origins_land_on_half_pixels_and_scale_rounds_to_two_decimals():
    block, _, _ = msf.measure_frame(picture((40, 236), (61, 119)), picture(**SIDE), height_m=1.8)
    assert block["px_per_m"] == round(197 / 1.8, 2)
    assert block["front_origin_px"] == [90.5, 138.5]


def test_threshold_and_speck_options():
    alpha = picture(**FRONT, speck=True)
    mask, _ = msf.figure_mask(alpha, threshold=0.3)
    assert msf.figure_box(mask) == [59, 39, 121, 241]   # the soft ring counts now
    mask, dropped = msf.figure_mask(alpha, speck_fraction=0)
    assert dropped == 0 and msf.figure_box(mask) == [5, 5, 120, 240]


def test_side_scale_mismatch_is_a_warning():
    _, measurement, warnings = msf.measure_frame(picture(**FRONT), picture((40, 249), (130, 169)), 1.6)
    assert measurement["side"]["size_px"][1] == 210
    assert len(warnings) == 1 and "+5.0%" in warnings[0]


def test_size_mismatch_is_refused(tmp_path, capsys):
    with pytest.raises(msf.FrameError, match="must share one frame"):
        msf.measure_frame(picture(**FRONT), picture(**SIDE, size=(W + 1, H)), 1.6)
    front = save(tmp_path / "front.png", picture(**FRONT))
    side = save(tmp_path / "side.png", picture(**SIDE, size=(W, H + 4)))
    assert msf.main(["--front", front, "--side", side, "--height-m", "1.6"]) == 2
    assert "200 x 304 px but the front is 200 x 300 px" in capsys.readouterr().err


def test_picture_without_alpha_cut_is_refused():
    with pytest.raises(msf.FrameError, match="alpha-cut"):
        msf.measure_frame(np.ones((H, W)), picture(**SIDE), 1.6)


PROFILE = """{
  "name": "Test",
  "_name": "A comment key.",
  "inputs": {
    "body_object": "Body"
  },
  "source_camera": {
    "_comment": "Measured by hand.",
    "image_px": [1, 1],
    "px_per_m": 1.0,
    "front_origin_px": [0.5, 0.5],
    "side_origin_px": [0.5, 0.5]
  },
  "body_lift_m": 0.8,
  "body_paint": {
    "side_band_abs_x_m": [0.33, 0.45],
    "_side_band_abs_x_m": "Comment."
  }
}
"""


def test_write_merges_the_block_into_the_profile(tmp_path, capsys):
    front = save(tmp_path / "front.png", picture(**FRONT, speck=True))
    side = save(tmp_path / "side.png", picture(**SIDE))
    profile = tmp_path / "profile.json"
    profile.write_text(PROFILE, encoding="utf-8", newline="\n")
    args = ["--front", front, "--side", side, "--height-m", "1.6", "--profile", str(profile)]

    assert msf.main(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["source_camera"]["front_origin_px"] == [90.0, 140.0]
    assert printed["profile_source_camera"]["px_per_m"] == 1.0
    assert profile.read_text(encoding="utf-8") == PROFILE       # untouched without --write

    assert msf.main(args + ["--write"]) == 0
    text = profile.read_bytes().decode("utf-8")
    written = json.loads(text)
    before = json.loads(PROFILE)
    assert list(written) == list(before)
    assert {k: v for k, v in written.items() if k != "source_camera"} == \
           {k: v for k, v in before.items() if k != "source_camera"}
    assert written["source_camera"] == {
        "_comment": "Measured by hand.",
        "image_px": [W, H],
        "px_per_m": 125.0,
        "front_origin_px": [90.0, 140.0],
        "side_origin_px": [150.0, 140.0],
    }
    # Same layout: only the measured lines change.
    changed = [new for old, new in zip(PROFILE.splitlines(), text.splitlines()) if old != new]
    assert len(changed) == 4 and all("_px" in line or "px_per_m" in line for line in changed)
    assert text.endswith("}\n") and "\r" not in text


def test_write_needs_a_profile(tmp_path):
    front = save(tmp_path / "front.png", picture(**FRONT))
    with pytest.raises(SystemExit):
        msf.main(["--front", front, "--side", front, "--height-m", "1.6", "--write"])
