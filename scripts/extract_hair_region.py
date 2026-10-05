"""Split an acquired head into hair and skin against its conformed template.

After conforming, the template is the skin. Whatever of the acquisition stands
off that skin by more than a few millimetres is hair (or headwear): strands
over the scalp, bangs over the forehead, locks over the ears and neck. This
writes those triangles as their own mesh, the input to the hair-shell stage.

Usage:
  python scripts/extract_hair_region.py <conform.npz> <hair.npz> [--offset 0.004]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402


def surface_samples(verts, tris, per_tri=12, seed=3):
    """Dense points on a surface, so distance-to-skin is not distance-to-vertex."""
    rng = np.random.default_rng(seed)
    u = rng.random((len(tris), per_tri, 2))
    flip = u.sum(2) > 1
    u[flip] = 1 - u[flip]
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    pts = a[:, None] + u[..., :1] * (b - a)[:, None] + u[..., 1:] * (c - a)[:, None]
    return np.concatenate([pts.reshape(-1, 3), verts[np.unique(tris)]])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("conform")
    p.add_argument("out")
    p.add_argument("--offset", type=float, default=0.004)
    p.add_argument("--cap-reach", type=float, default=0.02,
                   help="scalp within this of a strand is capped")
    p.add_argument("--cap-lift", type=float, default=0.003)
    a = p.parse_args()
    z = np.load(a.conform)
    fitted = z["verts"]
    tris = tc.fan_triangles(z["loops"], z["loop_starts"], z["loop_totals"])
    body = np.zeros(len(fitted), bool)
    body[z["vg__body"]] = True
    keep = np.zeros(len(fitted), bool)
    for i in z["keep_polys"]:
        s, n = z["loop_starts"][i], z["loop_totals"][i]
        keep[z["loops"][s:s + n]] = True
    skin_tris = tris[(body & keep)[tris].all(1)]
    skin = cKDTree(surface_samples(fitted, skin_tris))

    av, at = z["acq_verts"].astype(np.float64), z["acq_tris"]
    d, _ = skin.query(av, workers=-1)
    off = d > a.offset
    # Stand-off that is not hair: where the picture moved the lips and chin
    # away from the acquisition, and the acquisition's cut collar below the
    # template's head. Hair grows above the mouth at the front and down to
    # the jaw at the back.
    teeth = np.concatenate([z[k] for k in ("vg__helper-upper-teeth", "vg__helper-lower-teeth")])
    mouth = fitted[teeth].mean(0)
    eyes = fitted[np.concatenate([z["vg__helper-l-eye"], z["vg__helper-r-eye"]])].mean(0)
    skin_v = fitted[np.unique(skin_tris)]
    chin_col = skin_v[(np.abs(skin_v[:, 0]) < 0.01) & (skin_v[:, 1] < mouth[1] + 0.02)]
    chin_z = chin_col[:, 2].min()
    ear_y = eyes[1] + 0.08
    front_low = (av[:, 2] < mouth[2] + 0.005) & (av[:, 1] < ear_y)
    collar = av[:, 2] < chin_z - 0.03
    off &= ~front_low & ~collar
    hair_tris = at[off[at].all(1)]
    used = np.unique(hair_tris)
    remap = -np.ones(len(av), np.int64)
    remap[used] = np.arange(len(used))

    # The cap: scalp the strands cover, lifted a little, so the shell is a
    # mass over the head rather than strands over a bald scalp. The visible
    # forehead and face are never capped.
    hair_tree = cKDTree(av[used])
    nrm = tc.vertex_normals(fitted, tris)
    sv = np.unique(skin_tris)
    near, _ = hair_tree.query(fitted[sv], workers=-1)
    face_front = (nrm[sv, 1] < -0.55) & (fitted[sv, 2] < eyes[2] + 0.07)
    cap_v = sv[(near < a.cap_reach) & ~face_front & (fitted[sv, 2] > eyes[2] - 0.04)]
    cap = fitted[cap_v] + nrm[cap_v] * a.cap_lift
    np.savez_compressed(a.out, verts=av[used], tris=remap[hair_tris], cap_points=cap)
    print("hair", len(used), "verts", len(hair_tris), "tris of", len(at),
          "| skin-side", int((~off).sum()), "verts | cap", len(cap), "points")


if __name__ == "__main__":
    main()
