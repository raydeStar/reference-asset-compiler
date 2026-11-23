"""Check an attached surface at named trouble spots in an exported GLB.

Coordinates are mesh-local glTF XYZ (metres for normalized RAC exports). The
operator chooses boxes that are meant to contain a single continuous surface.
Coincident UV vertices are joined for this rest-topology check only; neither
the file nor its normals, skin weights or textures are changed.
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


def inspect_mesh(path, config):
    doc, blob = read_glb(path.read_bytes())
    matches = [m for m in doc["meshes"] if m.get("name") == config["mesh"]]
    if len(matches) != 1:
        raise ValueError("Name exactly one mesh in this export")
    positions, faces, offset = [], [], 0
    for prim in matches[0]["primitives"]:
        if prim.get("mode", 4) != 4 or prim.get("extensions"):
            raise ValueError("This check requires ordinary, uncompressed triangles")
        p = accessor(doc, blob, prim["attributes"]["POSITION"])
        idx = (accessor(doc, blob, prim["indices"]).ravel()
               if "indices" in prim else np.arange(len(p)))
        positions.append(p)
        faces.append(idx.astype(np.int64).reshape(-1, 3) + offset)
        offset += len(p)
    p, inv = np.unique(np.concatenate(positions), axis=0, return_inverse=True)
    t = inv.ravel()[np.vstack(faces)]
    # An atlas seam duplicates vertices, not positions. A skirt adds real faces.
    edges, counts = np.unique(np.sort(t[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1),
                              axis=0, return_counts=True)
    graph = coo_matrix((np.ones(len(edges), dtype=bool), edges.T), shape=(len(p), len(p)))
    _, labels = connected_components(graph, directed=False)
    edge_centres, face_centres = p[edges].mean(1), p[t].mean(1)
    rows = {}
    for name, box in config["regions"].items():
        bounds = np.asarray(box, dtype=float)
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or not (bounds[0] < bounds[1]).all():
            raise ValueError(f"Invalid [min XYZ, max XYZ] for {name}")
        lo, hi = bounds
        region = ((face_centres >= lo) & (face_centres <= hi)).all(1)
        inside = ((edge_centres >= lo) & (edge_centres <= hi)).all(1)
        pieces = len(np.unique(labels[t[region, 0]]))
        open_edges = int(np.sum(inside & (counts == 1)))
        nonmanifold = int(np.sum(inside & (counts > 2)))
        rows[name] = {"faces": int(region.sum()), "components_entering_box": pieces,
                      "boundary_edges": open_edges, "nonmanifold_edges": nonmanifold,
                      "needs_inspection": pieces != 1 or open_edges != 0 or nonmanifold != 0}
    if not rows:
        raise ValueError("Name at least one region")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("glb", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
    rows = inspect_mesh(args.glb, cfg)
    pending = any(v["needs_inspection"] for v in rows.values())
    receipt = {"schema": "rac.fitted-surface-check.v1",
               "glb_sha256": hashlib.sha256(args.glb.read_bytes()).hexdigest(),
               "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
               "mesh": cfg["mesh"], "regions": rows, "needs_inspection": pending}
    with args.report.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    print("FITTED_SURFACE:", "inspect marked boxes" if pending else "continuous in all boxes",
          "- a tailor counts the layers before pressing the seams.")
    return int(pending)


if __name__ == "__main__":
    raise SystemExit(main())
