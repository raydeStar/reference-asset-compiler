"""Mark which triangles of a scanned head are hair, against the template conformed to it.

The first step of mesh hair (docs/CHARACTER_MESH_HAIR.md). A generator that
sculpts stylised hair (Pixal3D does) delivers it fused to the head: one surface,
locks and skin together. After conform_head_template.py the conformed template
is the skin, so a scan triangle is hair when it stands outside that skin:

- over the scalp, by more than --scalp-offset (the hair's own thickness);
- anywhere, by more than --far (the fringe in front of the brow, locks over
  the ears and the nape);
- never the ears themselves (within --ear-keep of the template's ears), never
  an inside layer (behind the skin), never the neck (more than --below-eyes
  under the eyes).

Colour is not used here: the scan's texture tells skin from hair only near the
skin, which the cutting stage (blender/cut_scan_hair.py) checks.

Usage:
  python scripts/classify_scan_hair.py <template.npz> <conform.npz> <out.npz>
      [--scalp-offset 0.006] [--far 0.025] [--ear-keep 0.03] [--below-eyes 0.10]

Writes face_index (scan triangles that are hair, in conform.npz's acq_tris
order) and signed (each one's distance outside the skin, metres).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def vertex_normals(verts, loops, starts, totals):
    fan = [np.stack([np.full(n - 2, loops[s]), loops[s + 1:s + n - 1], loops[s + 2:s + n]], 1)
           for s, n in zip(starts, totals)]
    tris = np.concatenate(fan)
    fn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def classify(template, conform, scalp_offset=0.006, far=0.025, ear_keep=0.03, below_eyes=0.10):
    skin = conform["verts"]
    n = len(skin)

    def group(name):
        g = np.zeros(n, bool)
        if "vg__" + name in template.files:
            g[template["vg__" + name]] = True
        return g

    normals = vertex_normals(skin, conform["loops"], conform["loop_starts"], conform["loop_totals"])
    body = conform["vg__body"]
    eye_z = skin[conform["vg__helper-l-eye"]][:, 2].mean()
    head = body[skin[body, 2] > eye_z - 0.25]
    tree = cKDTree(skin[head])
    acq, tris = conform["acq_verts"].astype(np.float64), conform["acq_tris"]
    centres = acq[tris].mean(1)
    _, j = tree.query(centres)
    near = head[j]
    signed = np.einsum("ij,ij->i", centres - skin[near], normals[near])
    hair = ((signed > scalp_offset) & group("scalp")[near]) | (signed > far)
    hair &= ~(group("ears")[near] & (signed < ear_keep))
    hair &= signed > 0
    hair &= centres[:, 2] > eye_z - below_eyes
    return np.flatnonzero(hair), signed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("template")
    p.add_argument("conform")
    p.add_argument("out")
    p.add_argument("--scalp-offset", type=float, default=0.006)
    p.add_argument("--far", type=float, default=0.025)
    p.add_argument("--ear-keep", type=float, default=0.03)
    p.add_argument("--below-eyes", type=float, default=0.10)
    a = p.parse_args(argv)
    faces, signed = classify(np.load(a.template, allow_pickle=True), np.load(a.conform, allow_pickle=True),
                             a.scalp_offset, a.far, a.ear_keep, a.below_eyes)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, face_index=faces, signed=signed[faces].astype(np.float32))
    print(json.dumps({"hair_triangles": int(len(faces)), "scan_triangles": int(len(signed))}))


if __name__ == "__main__":
    main()
