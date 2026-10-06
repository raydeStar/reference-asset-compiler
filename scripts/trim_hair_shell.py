"""Remove hair-shell pieces that wrap the neck instead of hanging as hair.

A hair shell built from an acquisition's hair region picks up thin skins of
"hair" wherever the acquisition's hair touched the neck or jaw. Painted, they
take the skin colour the pictures show there and read as torn flesh. Hair that
hangs low (a nape, long locks) stands off the skin; these pieces lie on it.

Rule: drop every triangle whose three corners are below the ears' lowest point
and within HUG metres of the head's skin; along the jaw (in front of the ears'
back edge, where no hair hangs) within SIDE_HUG metres. The nape keeps its hair.
Deterministic, CPU only.

Usage:
  python scripts/trim_hair_shell.py <template.npz> <conform.npz> <hair_in.npz> <hair_out.npz> \
      [--hug 0.010]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from scipy.spatial import cKDTree


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "hair_in", "hair_out"):
        p.add_argument(name)
    p.add_argument("--hug", type=float, default=0.010)
    p.add_argument("--side-hug", type=float, default=0.025)
    a = p.parse_args(argv)

    tz = np.load(a.template)
    z = np.load(a.conform)
    h = np.load(a.hair_in)
    verts = z["verts"]
    body = np.zeros(len(verts), bool)
    body[z["vg__body"]] = True
    kept = np.zeros_like(body)
    for i in z["keep_polys"]:
        s, n = int(z["loop_starts"][i]), int(z["loop_totals"][i])
        kept[z["loops"][s:s + n]] = True
    skin = verts[kept & body]
    ear_bottom = float(verts[tz["vg__ears"], 2].min())
    ear_back = float(verts[tz["vg__ears"], 1].max())      # +y is towards the nape

    hv, ht = h["verts"], h["tris"]
    dist, _ = cKDTree(skin).query(hv)
    low = hv[:, 2] < ear_bottom
    low_hug = low & ((dist < a.hug) | ((hv[:, 1] < ear_back) & (dist < a.side_hug)))
    drop = low_hug[ht].all(1)
    keep = ~drop
    uv = h["loop_uv"].reshape(len(ht), 3, 2)[keep].reshape(-1, 2)
    np.savez_compressed(a.hair_out, verts=hv, tris=ht[keep], loop_uv=uv)
    print(json.dumps({"ear_bottom_z": ear_bottom, "ear_back_y": ear_back, "hug_m": a.hug,
                      "side_hug_m": a.side_hug,
                      "triangles_in": int(len(ht)), "triangles_dropped": int(drop.sum())}))


if __name__ == "__main__":
    main()
