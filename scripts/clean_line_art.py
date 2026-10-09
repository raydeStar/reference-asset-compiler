"""Take comic ink off the skin of a guidance picture before it is painted onto a head.

Stylised guidance (comic, cel, Arcane-like) draws a dark contour along the jaw,
hatching on the neck and outlines round the ear. Projected onto a head, those
strokes land beside the surface they outlined: a black line under the chin, a
smudge at the jaw corner. This finds thin dark strokes on skin with a
morphological black-hat (the dark detail a closing of the picture fills in),
keeps the features that are dark by nature (eyes, brows, nostrils, the lip
line: the landmark outlines, grown by a margin) and inpaints the rest from the
skin around it. Hair is left alone: a stroke counts only where the closed
picture around it is skin-coloured, and the outline against the background is
left to the painter's own foreground mask.

Usage:
  python scripts/clean_line_art.py <in.png> <out.png> [--landmarks dw.json]
      [--stroke-px 9] [--min-depth 28] [--keep-margin-px 18] [--mask out-mask.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

# 68-point groups whose surroundings keep their ink: brows, eyes, nostrils, mouth.
KEEP_GROUPS = (range(17, 22), range(22, 27), range(36, 42), range(42, 48), range(31, 36), range(48, 60))


def skin_like(bgr):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    hue = np.degrees(np.arctan2(b, a))
    return (L > 25) & (np.hypot(a, b) > 14) & (hue > 20) & (hue < 85)


def keep_mask(shape, landmarks, margin):
    keep = np.zeros(shape, np.uint8)
    if landmarks is None:
        return keep.astype(bool)
    d = json.loads(Path(landmarks).read_text(encoding="utf-8"))
    pts = np.array(d.get("landmarks_68") or d.get("landmarks_106"), float)
    if len(pts) != 68:
        raise SystemExit("clean_line_art.py keeps features from the 68-point layout")
    for g in KEEP_GROUPS:
        hull = cv2.convexHull(pts[list(g)].astype(np.int32))
        cv2.fillConvexPoly(keep, hull, 1)
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1,) * 2))
    return keep.astype(bool)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--landmarks", help="detect_face_landmarks_dwpose.py JSON of this picture (features to keep)")
    p.add_argument("--stroke-px", type=int, default=9, help="widest stroke removed (closing kernel)")
    p.add_argument("--min-depth", type=float, default=28.0, help="how much darker than its surroundings (0-255)")
    p.add_argument("--keep-margin-px", type=int, default=18)
    p.add_argument("--mask", help="write the removed strokes here")
    a = p.parse_args(argv)

    src = cv2.imread(a.image, cv2.IMREAD_UNCHANGED)
    alpha = src[..., 3] if src.ndim == 3 and src.shape[2] == 4 else None
    bgr = src[..., :3].copy()
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (a.stroke_px,) * 2)
    depth = cv2.morphologyEx(grey, cv2.MORPH_BLACKHAT, kernel).astype(np.float32)
    around = cv2.morphologyEx(bgr, cv2.MORPH_CLOSE, kernel)
    stroke = (depth > a.min_depth) & skin_like(around) & ~keep_mask(grey.shape, a.landmarks, a.keep_margin_px)
    # A plain backdrop (the corners' colour) is not skin, however warm: strokes beside it are outlines.
    corners = np.concatenate([bgr[:16, :16], bgr[:16, -16:], bgr[-16:, :16], bgr[-16:, -16:]]).reshape(-1, 3)
    backdrop = np.linalg.norm(bgr.astype(np.float32) - np.median(corners, 0), axis=2) < 24
    stroke &= ~cv2.dilate(backdrop.astype(np.uint8), kernel).astype(bool)
    if alpha is not None:
        stroke &= alpha > 0
    stroke = cv2.dilate(stroke.astype(np.uint8), np.ones((3, 3), np.uint8))
    out = cv2.inpaint(bgr, stroke, 5, cv2.INPAINT_TELEA)
    if alpha is not None:
        out = np.dstack([out, alpha])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(a.out, out)
    if a.mask:
        cv2.imwrite(a.mask, stroke * 255)
    print(json.dumps({"image": a.image, "out": a.out, "stroke_pixels": int(stroke.sum()),
                      "share": round(float(stroke.mean()), 4)}))


if __name__ == "__main__":
    main()
