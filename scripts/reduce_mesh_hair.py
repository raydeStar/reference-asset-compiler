"""Reduce mesh hair to a game triangle count (quadric edge collapse).

Mesh hair, step four (docs/CHARACTER_MESH_HAIR.md). A generator's sculpted
hair runs to most of a million triangles; a hero's hair gets tens of
thousands. fast-simplification (MIT; the Fast-Quadric-Mesh-Simplification
algorithm) keeps the locks' blade shapes at 60k where Blender's collapse
decimator turned them into shards, because it does not stop at the open edges
every blade has. UVs do not survive: blender/bake_mesh_hair.py lays new ones
and bakes the full-resolution paint onto them.

Usage:
  python scripts/reduce_mesh_hair.py <hair.npz> <out.npz> [--triangles 60000] [--aggression 7]
"""

from __future__ import annotations

import argparse
import json

import numpy as np


def reduce(verts, tris, triangles, aggression=7):
    try:
        import fast_simplification
    except ImportError as error:  # an optional dependency: pip install fast-simplification
        raise SystemExit("reduce_mesh_hair.py needs fast-simplification (MIT): "
                         "pip install fast-simplification") from error
    if len(tris) <= triangles:
        return verts, tris
    return fast_simplification.simplify(verts.astype(np.float32), tris.astype(np.int64),
                                        target_reduction=1 - triangles / len(tris), agg=aggression)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hair")
    p.add_argument("out")
    p.add_argument("--triangles", type=int, default=60000)
    p.add_argument("--aggression", type=int, default=7)
    a = p.parse_args(argv)
    z = np.load(a.hair)
    v, t = reduce(z["verts"], z["tris"], a.triangles, a.aggression)
    np.savez(a.out, verts=np.asarray(v, np.float32), tris=np.asarray(t, np.int64))
    print(json.dumps({"triangles_in": int(len(z["tris"])), "triangles": int(len(t)), "vertices": int(len(v))}))


if __name__ == "__main__":
    main()
