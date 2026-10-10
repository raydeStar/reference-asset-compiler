"""measure_skin_tone.py reads the cheeks where the landmarks put them, and reports hue and colourfulness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_skin_tone  # noqa: E402


def face(tmp_path, left_rgb, right_rgb):
    img = np.zeros((200, 200, 3), np.uint8)
    img[:, :100] = right_rgb       # the character's right cheek is on the picture's left
    img[:, 100:] = left_rgb
    path = tmp_path / "face.png"
    Image.fromarray(img).save(path)
    pts = np.zeros((68, 2))
    pts[0], pts[16] = (20, 100), (180, 100)     # face width 160
    pts[31], pts[2] = (90, 120), (30, 120)      # right nose wing, right jaw
    pts[35], pts[14] = (110, 120), (170, 120)   # left
    (tmp_path / "dw.json").write_text(json.dumps({"landmarks_68": pts.tolist()}), encoding="utf-8")
    return path


def test_lit_cheek_hue_and_colourfulness(tmp_path):
    tan, shade = (190, 130, 80), (95, 65, 40)
    path = face(tmp_path, left_rgb=shade, right_rgb=tan)
    pts = np.asarray(json.loads((tmp_path / "dw.json").read_text())["landmarks_68"], float)
    out = measure_skin_tone.cheeks(Image.open(path), pts)
    assert out["lit"] == out["right"]                      # the brighter cheek
    lab = measure_skin_tone.srgb_to_lab(np.array([[tan]]) / 255.0)[0, 0]
    assert abs(out["right"]["L"] - lab[0]) < 0.5
    assert 40 < out["right"]["hue_deg"] < 75                # an orange-tan hue
    assert abs(out["right"]["colourfulness"] - np.hypot(lab[1], lab[2]) / lab[0]) < 0.02
