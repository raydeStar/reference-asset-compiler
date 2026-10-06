"""Smooth a hair shell into readable locks: no shards, no crumbs.

A hair shell taken from an image-to-3D acquisition carries the acquisition's
noise: knife-edge shards, pits and crumbs of loose triangles. Painted, they
read as broken glass rather than hair. Taubin smoothing (alternating shrink
and inflate steps) removes that noise without shrinking the volume, and small
disconnected pieces are dropped. UVs ride along unchanged. Deterministic, CPU.

Usage:
  python scripts/smooth_hair_shell.py <hair_in.npz> <hair_out.npz> \
      [--iterations 12] [--lam 0.5] [--mu -0.53] [--min-piece 200]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.csgraph import connected_components


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("hair_in")
    p.add_argument("hair_out")
    p.add_argument("--iterations", type=int, default=12)
    p.add_argument("--lam", type=float, default=0.5)
    p.add_argument("--mu", type=float, default=-0.53)
    p.add_argument("--min-piece", type=int, default=200,
                   help="drop connected pieces with fewer triangles than this")
    a = p.parse_args(argv)

    h = np.load(a.hair_in)
    v = h["verts"].astype(np.float64)
    t = h["tris"]
    uv = h["loop_uv"].reshape(len(t), 3, 2)
    n = len(v)

    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    adj = coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])),
                     shape=(n, n)).tocsr()
    adj.data[:] = 1.0
    deg = np.asarray(adj.sum(1)).ravel()
    avg = diags(1.0 / np.maximum(deg, 1)) @ adj      # neighbour mean
    for _ in range(a.iterations):
        v = v + a.lam * (avg @ v - v)
        v = v + a.mu * (avg @ v - v)

    # Pieces: connected through shared vertices.
    pieces, label = connected_components(adj, directed=False)
    tri_label = label[t[:, 0]]
    sizes = np.bincount(tri_label, minlength=pieces)
    keep = sizes[tri_label] >= a.min_piece
    moved = np.linalg.norm(v - h["verts"], axis=1)
    np.savez_compressed(a.hair_out, verts=v.astype(np.float32), tris=t[keep],
                        loop_uv=uv[keep].reshape(-1, 2))
    print(json.dumps({"iterations": a.iterations, "moved_mm": {"median": float(np.median(moved) * 1000),
                                                              "max": float(moved.max() * 1000)},
                      "pieces": int(pieces), "triangles_in": int(len(t)),
                      "triangles_dropped": int((~keep).sum())}))


if __name__ == "__main__":
    main()
