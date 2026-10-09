"""reproject_face_paint.py's picture-derived zones: brow window, forehead colour, open-mouth guard."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from reproject_face_paint import FIXED_BROW_WINDOW, brow_window, mouth_open_ratio, skin_or_probe  # noqa: E402

# Ennix's front picture's landmarks (work/ennix-character-v1, 1254 px): the brows the fixed window was set on.
ENNIX_BROWS = {17: (422.9, 461.0), 18: (461.0, 439.2), 19: (504.5, 433.8), 20: (548.1, 441.9), 21: (586.2, 450.1),
               22: (673.3, 452.8), 23: (711.4, 444.7), 24: (752.2, 439.2), 25: (793.0, 447.4), 26: (828.4, 469.2)}


def face(brows=None, inner_gap=0.0, width=180.0):
    """68 points: brows where given, a mouth of this width with this gap between the inner lips."""
    lm = np.zeros((68, 2))
    for i, xy in (brows or {}).items():
        lm[i] = xy
    cx, cy = 640.0, 900.0
    lm[48], lm[54] = (cx - width / 2, cy), (cx + width / 2, cy)
    for top, bottom, dx in ((61, 67, -20.0), (62, 66, 0.0), (63, 65, 20.0)):
        lm[top], lm[bottom] = (cx + dx, cy - inner_gap / 2), (cx + dx, cy + inner_gap / 2)
    return lm


def test_the_landmark_window_lands_on_the_fixed_one_for_the_picture_it_was_set_on():
    lm = face({i: xy for i, xy in ENNIX_BROWS.items()})
    window = brow_window(lm)
    assert window["centre_px"] == pytest.approx(FIXED_BROW_WINDOW["centre_px"], abs=1.0)
    assert window["half_px"] == pytest.approx(FIXED_BROW_WINDOW["half_px"], abs=1.0)
    assert window["other_brow_dy_px"] == pytest.approx(FIXED_BROW_WINDOW["other_brow_dy_px"], abs=0.5)
    assert brow_window(lm, "fixed") == FIXED_BROW_WINDOW


def test_the_window_follows_brows_that_sit_elsewhere():
    lower = {i: (x + 3.0, y + 128.0) for i, (x, y) in ENNIX_BROWS.items()}   # a face lower in its picture
    window = brow_window(face(lower))
    assert window["centre_px"][1] == pytest.approx(FIXED_BROW_WINDOW["centre_px"][1] + 128.0, abs=1.0)
    wider = {i: (640 + (x - 640) * 1.2, y) for i, (x, y) in ENNIX_BROWS.items()}
    assert brow_window(face(wider))["half_px"][0] == pytest.approx(82.0 * 1.2, abs=1.5)


@pytest.mark.parametrize("gap, opened", [(0.0, False), (2.0, False), (14.7, True)])
def test_an_open_mouth_is_told_from_a_closed_one(gap, opened):
    # character-02's grinning painting: 14.7 px between the inner lips of a 186 px mouth (0.079); Ennix's: 0.
    ratio = mouth_open_ratio(face(inner_gap=gap, width=186.0))
    assert (ratio > 0.03) is opened


def test_a_fringe_over_the_forehead_takes_skin_from_the_probes():
    skin = [np.array([0.78, 0.52, 0.36]), np.array([0.74, 0.49, 0.33]), np.array([0.80, 0.55, 0.38])]
    hair = np.array([0.09, 0.06, 0.05])
    colour, swapped = skin_or_probe(hair, skin)
    assert swapped and colour == pytest.approx(np.median(skin, axis=0))
    forehead = np.array([0.82, 0.56, 0.40])
    colour, swapped = skin_or_probe(forehead, skin)
    assert not swapped and colour == pytest.approx(forehead)


def test_ennix_brows_are_his_pictures():
    # Keeps ENNIX_BROWS honest when the frozen bundle is present (it is git-ignored).
    path = ROOT / "work/ennix-character-v1/rebuild-inputs/front-landmarks.json"
    if not path.is_file():
        pytest.skip("Ennix's frozen inputs are not in this checkout")
    lm = np.array(json.loads(path.read_text())["landmarks_68"])
    for i, xy in ENNIX_BROWS.items():
        assert lm[i] == pytest.approx(xy, abs=0.1)
