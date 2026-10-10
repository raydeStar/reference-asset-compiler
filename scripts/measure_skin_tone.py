"""Measure a face's skin tone in a picture: the cheeks, found by the face detector.

For matching a character's in-game skin to its reference: run it on the
reference painting and on an in-game face shot, then compare. Brightness
depends on each picture's light, so the comparison that carries over is hue
(degrees) and colourfulness (chroma / L*); both are printed, with L*.

The cheek samples sit on the line from each nose wing (landmarks 31, 35) to
the jaw below the ear (2, 14), a third of the way out, in a disc a twelfth of
the face's width; the brighter cheek is the lit one (`lit`).

Usage:
  python scripts/measure_skin_tone.py <picture> --landmarks dw.json [--out tone.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def srgb_to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def tone(lab):
    L, a, b = np.median(lab, axis=0)
    chroma = float(np.hypot(a, b))
    return {"L": round(float(L), 1), "a": round(float(a), 1), "b": round(float(b), 1),
            "hue_deg": round(float(np.degrees(np.arctan2(b, a))), 1), "chroma": round(chroma, 1),
            "colourfulness": round(chroma / max(float(L), 1.0), 3)}


def cheeks(image, pts):
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0
    lab = srgb_to_lab(rgb)
    width = np.linalg.norm(pts[16] - pts[0])
    radius = max(2.0, width / 12)
    yy, xx = np.indices(lab.shape[:2])
    out = {}
    for side, (nose, jaw) in {"right": (31, 2), "left": (35, 14)}.items():
        centre = pts[nose] + (pts[jaw] - pts[nose]) / 3
        disc = (xx - centre[0]) ** 2 + (yy - centre[1]) ** 2 < radius ** 2
        out[side] = tone(lab[disc])
    out["lit"] = max(out["right"], out["left"], key=lambda t: t["L"])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("picture")
    p.add_argument("--landmarks", required=True, help="detect_face_landmarks_dwpose.py JSON of the picture")
    p.add_argument("--out")
    a = p.parse_args(argv)
    d = json.loads(Path(a.landmarks).read_text(encoding="utf-8"))
    pts = np.asarray(d["landmarks_68"], float)
    result = {"picture": a.picture, **cheeks(Image.open(a.picture), pts)}
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
