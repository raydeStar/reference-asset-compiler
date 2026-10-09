"""Carry mesh hair from the head it was cut from to another head conformed from the same template.

Mesh hair, step three (docs/CHARACTER_MESH_HAIR.md). Both heads are the same
template with the same vertex order, conformed to different scans. Each hair
vertex moves with the skin under it: the inverse-distance-squared weighted
displacement of its --k nearest head vertices (skull, face and upper neck)
between the two heads. Hair cut from one scan then sits on the skull of a head
built from another (or on another character's).

Usage:
  python scripts/transfer_mesh_hair.py <hair.npz> <from-head.npz> <to-head.npz> <out.npz> [--k 12]

The heads are conform_head_template.py or finish_template_head.py NPZs (verts,
vg__body, vg__helper-l-eye). Every other array in hair.npz is copied unchanged.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from scipy.spatial import cKDTree


def transfer(points, src, dst, body, eye, k=12):
    """Displace points by the skin's motion from src to dst (same template vertex order)."""
    eye_z = src[eye][:, 2].mean()
    head = body[src[body, 2] > eye_z - 0.12]
    dist, j = cKDTree(src[head]).query(points, k=k)
    w = 1.0 / np.maximum(dist, 1e-4) ** 2
    w /= w.sum(1, keepdims=True)
    return points + np.einsum("nk,nkc->nc", w, dst[head][j] - src[head][j])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hair")
    p.add_argument("from_head")
    p.add_argument("to_head")
    p.add_argument("out")
    p.add_argument("--k", type=int, default=12)
    a = p.parse_args(argv)
    hair = dict(np.load(a.hair))
    src, dst = np.load(a.from_head, allow_pickle=True), np.load(a.to_head, allow_pickle=True)
    if src["verts"].shape != dst["verts"].shape:
        raise SystemExit("the two heads are not the same template (vertex counts differ)")
    moved = transfer(hair["verts"].astype(np.float64), src["verts"], dst["verts"], src["vg__body"],
                     src["vg__helper-l-eye"], a.k)
    shift = np.linalg.norm(moved - hair["verts"], axis=1) * 1000
    hair["verts"] = moved.astype(np.float32)
    np.savez(a.out, **hair)
    print(json.dumps({"vertices": int(len(moved)),
                      "moved_mm": dict(zip(("p50", "p95", "max"), np.percentile(shift, [50, 95, 100]).round(1).tolist()))}))


if __name__ == "__main__":
    main()
