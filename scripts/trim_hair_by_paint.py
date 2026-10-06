"""Drop low hair-shell pieces the pictures painted as skin.

Where a picture shows neck or jaw, the hair shell has no business being: if a
shell triangle below the ears took skin colour from the paint, the pictures
say there is no hair there. Each triangle's colour (at its UV centroid) is
classed by the nearer of two references: the median painted skin of the head
and the median painted hair of the shell. Run after painting; render with the
trimmed shell and the same hair texture. Deterministic, CPU only.

Usage:
  python scripts/trim_hair_by_paint.py <template.npz> <conform.npz> <hair.npz> \
      <head_basecolor.png> <hair_basecolor.png> <hair_out.npz> [--margin 0.0]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from PIL import Image


def sample(tex, uv):
    h, w = tex.shape[:2]
    x = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    y = np.clip(((1.0 - uv[:, 1]) * h).astype(int), 0, h - 1)
    return tex[y, x]


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "hair", "head_tex", "hair_tex", "hair_out"):
        p.add_argument(name)
    p.add_argument("--margin", type=float, default=0.0,
                   help="metres above the ears' lowest point still considered")
    a = p.parse_args(argv)

    tz = np.load(a.template)
    z = np.load(a.conform)
    h = np.load(a.hair)
    ear_bottom = float(z["verts"][tz["vg__ears"], 2].min()) + a.margin
    head_tex = np.asarray(Image.open(a.head_tex).convert("RGB"), np.float64) / 255
    hair_tex = np.asarray(Image.open(a.hair_tex).convert("RGB"), np.float64) / 255

    hv, ht = h["verts"], h["tris"]
    uv = h["loop_uv"].reshape(len(ht), 3, 2)
    colour = sample(hair_tex, uv.mean(1))
    painted_skin = head_tex.reshape(-1, 3)
    painted_skin = painted_skin[painted_skin.sum(1) > 0.3]
    skin_ref = np.median(painted_skin, 0)
    hair_ref = np.median(colour, 0)
    skinlike = np.linalg.norm(colour - skin_ref, axis=1) < np.linalg.norm(colour - hair_ref, axis=1)
    low = (hv[ht, 2] < ear_bottom).all(1)
    drop = low & skinlike
    keep = ~drop
    np.savez_compressed(a.hair_out, verts=hv, tris=ht[keep], loop_uv=uv[keep].reshape(-1, 2))
    print(json.dumps({"ear_bottom_z": ear_bottom, "skin_ref": skin_ref.round(3).tolist(),
                      "hair_ref": hair_ref.round(3).tolist(), "triangles_in": int(len(ht)),
                      "triangles_dropped": int(drop.sum())}))


if __name__ == "__main__":
    main()
