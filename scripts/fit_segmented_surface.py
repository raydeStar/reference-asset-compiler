"""Build one fitted mesh from face labels on one acquired, indexed surface.

The NPZ is a geometry intermediate in mesh-local coordinates. Reproject the
original labels, paint and rig after choosing the final topology. Never give
this helper independently extruded shells and expect it to reconstruct the
missing surface underneath.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from compress_textures import read_glb
from surface_atlas import accessor


def fit_surface(positions, faces, selected, *, largest=False, triangles=None):
    """Retain shared acquisition indices at semantic boundaries; never inset or extrude."""
    selected = np.asarray(selected)
    if selected.dtype != bool or selected.shape != (len(faces),) or not selected.any():
        raise ValueError("Expected a nonempty face selection aligned to the acquired triangles")
    if triangles is not None and triangles < 4:
        raise ValueError("Choose a plausible fitted surface budget before UVs and paint")
    source_vertices, inverse = np.unique(faces[selected], return_inverse=True)
    t = inverse.reshape(-1, 3)
    pairs = t[:, [0, 1, 2, 0]]
    graph = coo_matrix((np.ones(3 * len(t), dtype=bool),
                        (pairs[:, :3].ravel(), pairs[:, 1:].ravel())),
                       shape=(len(source_vertices), len(source_vertices)))
    _, ids = connected_components(graph, directed=False)
    sizes = np.bincount(ids)
    if largest:
        t = t[ids[t[:, 0]] == sizes.argmax()]
    used, local = np.unique(t, return_inverse=True)
    p = positions[source_vertices[used]]
    t = local.reshape(-1, 3).astype(np.int32)
    before = len(t)
    if triangles is not None and before > triangles:
        import fast_simplification

        p, t = fast_simplification.simplify(p.astype(float), t, target_count=triangles, agg=5)
    info = {"selected_faces": int(selected.sum()), "selected_components": len(sizes),
            "discarded_island_faces": int(selected.sum()) - before, "output_faces": len(t)}
    return p, t, info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Uncut GLB with one indexed triangle primitive")
    ap.add_argument("labels", type=Path, help="One integer label per source triangle (.npy)")
    ap.add_argument("names", type=Path, help="JSON array mapping label indices to names")
    ap.add_argument("output", type=Path, help="New .npz with positions, faces and receipt")
    ap.add_argument("--include", required=True, nargs="+", help="Labels to keep on the same surface")
    ap.add_argument("--largest-component", action="store_true", help="Explicitly drop smaller islands")
    ap.add_argument("--triangles", type=int, help="Fitted region budget decided before paint")
    a = ap.parse_args()
    doc, blob = read_glb(a.source.read_bytes())
    prims = [pr for m in doc["meshes"] for pr in m["primitives"]]
    if (len(prims) != 1 or "indices" not in prims[0] or prims[0].get("mode", 4) != 4
            or prims[0].get("extensions")):
        raise ValueError("Provide one uncompressed, indexed, pre-cut acquisition")
    pr = prims[0]
    pts = accessor(doc, blob, pr["attributes"]["POSITION"])
    faces = accessor(doc, blob, pr["indices"]).reshape(-1, 3)
    names = json.loads(a.names.read_text(encoding="utf-8-sig"))
    labels = np.load(a.labels, allow_pickle=False)
    if (not isinstance(names, list) or len(set(names)) != len(names)
            or labels.shape != (len(faces),) or not np.issubdtype(labels.dtype, np.integer)
            or np.any((labels < 0) | (labels >= len(names)))):
        raise ValueError("Labels must index the supplied name list in this mesh's face order")
    selected = np.isin(labels, [names.index(name) for name in a.include])
    p, t, info = fit_surface(pts, faces, selected, largest=a.largest_component, triangles=a.triangles)
    info.update(selected_labels=a.include, largest_component=a.largest_component,
                triangle_budget=a.triangles, input_hashes={
                    k: hashlib.sha256(path.read_bytes()).hexdigest()
                    for k, path in [("source", a.source), ("labels", a.labels), ("names", a.names)]})
    with a.output.open("xb") as f:
        np.savez_compressed(f, positions=p, triangles=t, receipt=json.dumps(info))
    print("FITTED_SURFACE:", info, "- one coat does not need a wall at every stitch.")


if __name__ == "__main__":
    main()
