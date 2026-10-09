"""clean_line_art.py takes ink off skin and leaves the features, the hair and the outline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clean_line_art  # noqa: E402

SKIN = (70, 120, 190)        # BGR: a warm tan
BACKDROP = (215, 225, 232)   # BGR: a light cream backdrop
INK = (20, 20, 25)


def picture(tmp_path):
    img = np.full((200, 200, 3), BACKDROP, np.uint8)
    cv2.rectangle(img, (40, 40), (160, 190), SKIN, -1)           # the face
    cv2.line(img, (60, 150), (140, 150), INK, 2)                 # a jaw contour on the skin
    cv2.rectangle(img, (70, 80), (90, 86), INK, -1)              # an eye (a landmark feature)
    cv2.line(img, (40, 40), (40, 190), INK, 2)                   # the outline against the backdrop
    cv2.rectangle(img, (40, 40), (160, 60), (20, 25, 40), -1)    # hair
    path = tmp_path / "in.png"
    cv2.imwrite(str(path), img)
    eye = [[70 + 4 * i, 83] for i in range(6)]
    marks = [[0, 0]] * 36 + eye + [[0, 0]] * 26
    (tmp_path / "dw.json").write_text(json.dumps({"landmarks_68": marks}), encoding="utf-8")
    return path


def test_ink_on_skin_goes_and_the_rest_stays(tmp_path):
    src = picture(tmp_path)
    out = tmp_path / "out.png"
    clean_line_art.main([str(src), str(out), "--landmarks", str(tmp_path / "dw.json"), "--keep-margin-px", "4"])
    img = cv2.imread(str(out)).astype(int)
    assert np.abs(img[150, 100] - SKIN).max() < 25            # the jaw contour is skin now
    assert img[83, 80].max() < 60                               # the eye keeps its ink
    assert img[100, 40].max() < 60                              # the outline is the painter's to mask
    assert img[50, 100].max() < 60                              # the hair is untouched
