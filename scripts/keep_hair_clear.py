"""Keep mesh hair outside the head's skin: push what is too close (or inside) out along the skin's normal.

Mesh hair placed by the face (transfer_mesh_hair.py --place-by-face) sits on
a skull the scan never had, so some of it ends up in or against the skin. Any
hair vertex closer than --clearance outside the skin moves out to --clearance
along the nearest skin vertex's normal (the head's body skin down to
SKIN_BELOW_EYES under the eyes, so the neck and shoulders count).

It runs on the reduced hair, after reduce_mesh_hair.py: pushed vertex by vertex
before the reduction, neighbouring blades land on one offset shell and the
quadric collapse stops early (character-02's face-placed hair stalled at 36,442
triangles of a 30,000 request; unpushed, it reached 29,999).

Usage:
  python scripts/keep_hair_clear.py <hair.npz> <head.npz> <out.npz> [--clearance 0.002]

head.npz is a conformed head (verts, loops, loop_starts, loop_totals, vg__body,
vg__helper-l-eye). Every other array in hair.npz is copied unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_scan_hair import vertex_normals  # noqa: E402

SKIN_BELOW_EYES = 0.25   # metres under the eyes the skin that hair is kept off reaches


def keep_clear(points, skin, normals, clearance):
    """Points closer than clearance outside the skin (or inside it) pushed out to clearance along the nearest skin
    vertex's normal: (points, moved)."""
    _, j = cKDTree(skin).query(points)
    depth = np.einsum("ij,ij->i", points - skin[j], normals[j])
    moved = depth < clearance
    out = points.copy()
    out[moved] += (clearance - depth[moved])[:, None] * normals[j[moved]]
    return out, moved


def head_skin(head):
    """The head's skin that hair is kept off, and its normals: (points, normals)."""
    verts = np.asarray(head["verts"], float)
    body = np.asarray(head["vg__body"])
    eye_z = verts[head["vg__helper-l-eye"]][:, 2].mean()
    skin = body[verts[body, 2] > eye_z - SKIN_BELOW_EYES]
    normals = vertex_normals(verts, head["loops"], head["loop_starts"], head["loop_totals"])
    return verts[skin], normals[skin]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hair")
    p.add_argument("head")
    p.add_argument("out")
    p.add_argument("--clearance", type=float, default=0.002, help="metres the hair keeps outside the skin")
    a = p.parse_args(argv)
    hair = dict(np.load(a.hair))
    skin, normals = head_skin(np.load(a.head))
    points = hair["verts"].astype(np.float64)
    out, moved = keep_clear(points, skin, normals, a.clearance)
    hair["verts"] = out.astype(np.float32)
    np.savez(a.out, **hair)
    push = np.linalg.norm(out - points, axis=1)[moved] * 1000
    print(json.dumps({"vertices": int(len(points)), "clearance_m": a.clearance, "pushed": int(moved.sum()),
                      "pushed_share": round(float(moved.mean()), 4),
                      "push_mm": dict(zip(("p50", "p95", "max"),
                                          (np.percentile(push, [50, 95, 100]).round(1).tolist() if len(push)
                                           else [0.0, 0.0, 0.0])))}))


if __name__ == "__main__":
    main()
