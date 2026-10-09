"""Measure original/reference face ratios and transport the template's lower face.

Pure NumPy, deterministic, with every expression transported through the same
smooth deformation. Original UVs/topology and the crown are preserved.

--mouth-corner-lift is the character's: how far to raise each mouth corner to
restore a source's lifted corners (rebuild_character.py passes it from
profiles/characters/<name>.json; default none).

Per-character (Ennix-tuned): the deformation's zones are heights and depths on
the first character's conformed head (lower face above z 1.50 m, the mouth
corner at 1.625 m). See docs/CHARACTER_REBUILD.md, "Still tuned to the first
character".
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def landmarks(path):
    return np.array(json.loads(Path(path).read_text())["landmarks_68"])


def normalized(points):
    left, right = points[36:42].mean(0), points[42:48].mean(0)
    mid = (left + right) / 2
    horizontal = (right - left) / np.linalg.norm(right - left)
    rotation = np.array([horizontal, [-horizontal[1], horizontal[0]]])
    return (points - mid) @ rotation.T / np.linalg.norm(right - left)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("receipt")
    p.add_argument("original_landmarks")
    p.add_argument("out")
    p.add_argument("--mouth-corner-lift", type=float, nargs=2, default=(0.0, 0.0), metavar=("RIGHT_MM", "LEFT_MM"),
                   help="raise the mouth corner on the character's right (x < 0) and left (x > 0) by these "
                        "millimetres, for a source whose corners sit higher than the conformed head's (default: 0 0)")
    a = p.parse_args()
    right_lift, left_lift = (mm / 1000 for mm in a.mouth_corner_lift)
    z = dict(np.load(a.source))
    rec = json.loads(Path(a.receipt).read_text())
    before = normalized(landmarks(rec["picture"]["landmarks"]))
    target = normalized(landmarks(a.original_landmarks))
    ratio = float(target[8, 1] / before[8, 1])
    v = z["verts"]
    eyes = [z["vg__helper-l-eye"], z["vg__helper-r-eye"]]
    eye_z = float(np.mean([v[g, 2].mean() for g in eyes]))
    # Smooth only the lower facial height. The skull, scalp and ears keep
    # their shape; the neck follows so a shorter chin cannot leave a seam.
    # Per-character (Ennix-tuned): the zone heights and widths below.
    def deform(pos):
        out = pos.copy()
        below = np.maximum(eye_z - pos[:, 2], 0)
        front = np.clip((-pos[:, 1] - 0.04) / 0.055, 0, 1)
        front = front * front * (3 - 2 * front)
        extent = np.clip((pos[:, 2] - 1.50) / 0.07, 0, 1)
        extent = extent * extent * (3 - 2 * extent)
        out[:, 2] += below * (1 - ratio) * front * extent
        if right_lift or left_lift:
            # Restore the source's subtle lifted corner, not a permanent broad grin.
            x, y, height = pos.T
            mouth = np.exp(-((height - 1.625) / 0.014) ** 2 - ((np.abs(x) - 0.030) / 0.014) ** 2)
            mouth *= np.clip((-y - 0.08) / 0.045, 0, 1)
            out[:, 2] += mouth * np.where(x < 0, right_lift, left_lift)
        return out

    new = deform(v)
    for group in eyes:
        new[group] = v[group] + (new[group] - v[group]).mean(0)
    for key in list(z):
        if key.startswith("ex__"):
            z[key] = deform(v + z[key]) - deform(v)
    z["texture_verts"] = v.copy()
    z["verts"] = new
    dest = Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest, **z)
    report = {"source_sha256": hashlib.sha256(Path(a.source).read_bytes()).hexdigest(),
              "original_lower_face_ratio": ratio,
              "max_change_mm": float(np.linalg.norm(new - v, axis=1).max() * 1000),
              "expressions_transported": len([k for k in z if k.startswith("ex__")]),
              "topology_and_uv_unchanged": True}
    dest.with_suffix(".proportions.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
