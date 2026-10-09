"""Reduce mesh hair to a game triangle count (quadric edge collapse).

Mesh hair, step four (docs/CHARACTER_MESH_HAIR.md). A generator's sculpted
hair runs to most of a million triangles; a hero's hair gets tens of
thousands. fast-simplification (MIT; the Fast-Quadric-Mesh-Simplification
algorithm) keeps the locks' blade shapes at 60k where Blender's collapse
decimator turned them into shards, because it does not stop at the open edges
every blade has. UVs do not survive: blender/bake_mesh_hair.py lays new ones
and bakes the full-resolution paint onto them.

The collapse lays some thin blades' two sides onto each other: the same three
vertices twice (about 10% of character-02's hair at 30-40k). Those copies are
dropped here, as Blender's mesh validation would drop them at the bake, so the
count reported is the count that ships. When it misses --triangles by more than
2% (the copies, or a hair whose many small pieces cannot collapse further) a
WARNING says so on stderr and in the printed JSON.

Usage:
  python scripts/reduce_mesh_hair.py <hair.npz> <out.npz> [--triangles 60000] [--aggression 7]
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

TOLERANCE = 0.02   # a count further than this from the request is reported


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


def unique_faces(tris):
    """The triangles without repeats of the same three vertices (in any order or winding), first ones kept."""
    _, first = np.unique(np.sort(tris, 1), axis=0, return_index=True)
    return tris[np.sort(first)]


def count_warning(requested, triangles, what="the reduced hair"):
    """A warning when a triangle count misses the request by more than TOLERANCE, else None."""
    if requested and abs(triangles - requested) > TOLERANCE * requested:
        return f"{what} has {triangles:,} triangles, not the {requested:,} requested"
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hair")
    p.add_argument("out")
    p.add_argument("--triangles", type=int, default=60000)
    p.add_argument("--aggression", type=int, default=7)
    a = p.parse_args(argv)
    z = np.load(a.hair)
    v, t = reduce(z["verts"], z["tris"], a.triangles, a.aggression)
    collapsed = len(t)
    t = unique_faces(np.asarray(t, np.int64))
    np.savez(a.out, verts=np.asarray(v, np.float32), tris=t)
    report = {"triangles_in": int(len(z["tris"])), "requested": a.triangles, "collapsed": int(collapsed),
              "duplicates_dropped": int(collapsed - len(t)), "triangles": int(len(t)), "vertices": int(len(v))}
    warning = count_warning(a.triangles, len(t)) if len(z["tris"]) > a.triangles else None
    if warning:
        report["warning"] = warning
        print("WARNING: " + warning, file=sys.stderr)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
