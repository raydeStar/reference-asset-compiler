"""A dark scalp cap under mesh hair, so the skin does not show between its locks.

Mesh hair (docs/CHARACTER_MESH_HAIR.md) is sculpted locks with gaps between
them, and through a gap the head's skin paint reads as bare scalp. The strand
groom puts a dark cap under its strands (grow_hair_groom.py); this makes the
same cap for a hair mesh, under the same keys (cap_verts, cap_tris,
cap_colour), which render_painted_head.py --scalp-cap draws.

The cap is the head's skin where hair grows and the hair lies over it:

- where hair grows: the template's scalp vertex group (--scalp-group);
- the hair lies over it: hair surface within --reach out along the skin's
  normal, in a column --probe-radius wide (so the cap ends near the hair's own
  edge). Coverage is then closed over the gaps between locks (--close passes
  over the skin's neighbours), since those gaps are what the cap is for;
- its edge stays inside the hair: --front-inset behind the face (skin outside
  the scalp that faces forward, -y in template space), so the forehead, not the
  cap, shows between fringe locks; --rim-inset from every other free edge.

The cap is that skin pushed --lift out along its normals, with only the
vertices its triangles use. Its colour is the hair's own: the median of its
paint, sampled at its triangles.

Usage:
  python scripts/mesh_hair_scalp_cap.py <template.npz> <head.npz> <hair-mesh.npz> <hair-basecolor.png> <out.npz>
      [--reach 0.03] [--probe-radius 0.006] [--front-inset 0.015] [--rim-inset 0.0] [--lift 0.0025] [--close 2]

head.npz is a conformed head (verts, loops, loop_starts, loop_totals,
keep_polys, vg__helper-*), in the template's vertex order; hair-mesh.npz is
build_mesh_hair.py's (verts, tris, loop_uv) in the same space.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree

FACE_FORWARD = -0.35   # skin whose normal's y is below this faces forward (the template faces -y)


def skin_triangles(head):
    """The head's own skin as triangles: kept polygons without helper vertices (eyes, teeth...), fanned."""
    helper = np.zeros(len(head["verts"]), bool)
    for name in head.files:
        if name.startswith("vg__helper-"):
            helper[head[name]] = True
    loops, starts, totals = head["loops"], head["loop_starts"], head["loop_totals"]
    tris = []
    for i in head["keep_polys"]:
        s, n = int(starts[i]), int(totals[i])
        poly = loops[s:s + n]
        if helper[poly].any():
            continue
        tris.extend((poly[0], poly[k], poly[k + 1]) for k in range(1, n - 1))
    return np.array(tris, np.int64).reshape(-1, 3)


def vertex_normals(verts, tris):
    fn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def hair_samples(verts, tris):
    """Points on the hair surface: its triangles' corners, edge midpoints and centres."""
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return np.concatenate([verts[np.unique(tris)], (a + b) / 2, (b + c) / 2, (c + a) / 2, (a + b + c) / 3])


def neighbour_matrix(tris, n):
    """Row-normalised vertex adjacency over the triangles' edges."""
    i = np.concatenate([tris[:, 0], tris[:, 1], tris[:, 2], tris[:, 1], tris[:, 2], tris[:, 0]])
    j = np.concatenate([tris[:, 1], tris[:, 2], tris[:, 0], tris[:, 0], tris[:, 1], tris[:, 2]])
    m = coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    m.data[:] = 1.0
    degree = np.asarray(m.sum(1)).ravel()
    return m, np.maximum(degree, 1)


def root_shade(texture, loop_uv):
    """The hair's typical paint (linear RGB): the median colour at its triangles' centres in UV (a corner sits on
    its island's edge, in the bake's margin), skipping black texels, which are bake misses rather than paint."""
    image = np.asarray(Image.open(texture).convert("RGB"), np.float64) / 255.0
    h, w = image.shape[:2]
    uv = loop_uv.reshape(-1, 3, 2).mean(1)
    x = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1)
    y = np.clip(((1.0 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
    srgb = image[y, x]
    srgb = srgb[srgb.max(1) > 2 / 255] if (srgb.max(1) > 2 / 255).any() else srgb
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return np.median(linear, 0)


def scalp_cap(template, head, hair, texture, reach=0.03, front_inset=0.015, rim_inset=0.0, lift=0.0025,
              close=2, scalp_group="scalp", probe_radius=0.006):
    """(cap_verts, cap_tris, cap_colour, report) for a hair mesh over a conformed head."""
    key = "vg__" + scalp_group
    if key not in template.files:
        raise ValueError(f"the template has no {scalp_group!r} vertex group to say where hair grows")
    verts = np.asarray(head["verts"], np.float64)
    tris = skin_triangles(head)
    normals = vertex_normals(verts, tris)
    used = np.unique(tris)
    scalp = np.zeros(len(verts), bool)
    scalp[template[key]] = True
    scalp &= np.isin(np.arange(len(verts)), used)

    # Hair over the skin: a hair point in a column of balls (probe_radius) out along the normal to reach,
    # so only hair outside the skin, over this spot, counts.
    tree = cKDTree(hair_samples(np.asarray(hair["verts"], np.float64), np.asarray(hair["tris"], np.int64)))
    covered = np.zeros(len(verts), bool)
    ids = np.flatnonzero(scalp)
    for t in np.arange(probe_radius, reach + 1e-9, probe_radius):
        hits = tree.query_ball_point(verts[ids] + normals[ids] * t, probe_radius, return_length=True)
        covered[ids[hits > 0]] = True
    # Close the gaps between locks: a scalp vertex most of whose neighbours are covered is covered.
    adjacency, degree = neighbour_matrix(tris, len(verts))
    raw = int(covered.sum())
    for _ in range(close):
        share = np.asarray(adjacency @ covered.astype(float)).ravel() / degree
        covered |= scalp & (share > 0.5)

    tri_c = verts[tris].mean(1)
    under = covered[tris].all(1)
    # The face: skin outside the scalp that faces forward. The cap ends front_inset behind it.
    face = ~scalp & (normals[:, 1] < FACE_FORWARD)
    face[~np.isin(np.arange(len(verts)), used)] = False
    behind = np.ones(len(tris), bool)
    if front_inset > 0 and face.any():
        behind = cKDTree(verts[face]).query(tri_c)[0] > front_inset
    keep = under & behind
    rim_dropped = 0
    if rim_inset > 0 and keep.any():
        edges = np.sort(np.concatenate([tris[keep][:, [0, 1]], tris[keep][:, [1, 2]], tris[keep][:, [2, 0]]]), 1)
        unique, count = np.unique(edges, axis=0, return_counts=True)
        rim = np.unique(unique[count == 1])
        inside = cKDTree(verts[rim]).query(tri_c)[0] > rim_inset
        rim_dropped = int((keep & ~inside).sum())
        keep &= inside
    cap = tris[keep]
    used_cap = np.unique(cap)
    remap = -np.ones(len(verts), np.int64)
    remap[used_cap] = np.arange(len(used_cap))
    cap_verts = verts[used_cap] + normals[used_cap] * lift
    colour = root_shade(texture, np.asarray(hair["loop_uv"], np.float64))
    report = {"cap_triangles": int(len(cap)), "cap_vertices": int(len(used_cap)),
              "scalp_triangles": int(scalp[tris].all(1).sum()), "under_hair_triangles": int(under.sum()),
              "covered_vertices": {"probe": raw, "closed": int(covered.sum())},
              "front_dropped": int((under & ~behind).sum()), "rim_dropped": rim_dropped,
              "cap_colour": np.round(colour, 5).tolist(),
              "options": {"reach_m": reach, "probe_radius_m": probe_radius, "front_inset_m": front_inset,
                          "rim_inset_m": rim_inset, "lift_m": lift, "close": close, "scalp_group": scalp_group}}
    return cap_verts.astype(np.float32), remap[cap].astype(np.int32), colour.astype(np.float32), report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("template", "head", "hair", "texture", "out"):
        p.add_argument(name)
    p.add_argument("--reach", type=float, default=0.03, help="metres out from the skin within which hair covers it")
    p.add_argument("--probe-radius", type=float, default=0.006,
                   help="metres: the width of the column searched for hair over each scalp vertex")
    p.add_argument("--front-inset", type=float, default=0.015,
                   help="metres the cap stays behind the face (forward-facing skin outside the scalp)")
    p.add_argument("--rim-inset", type=float, default=0.0, help="metres the cap stays inside its other free edges")
    p.add_argument("--lift", type=float, default=0.0025, help="metres the cap stands off the skin")
    p.add_argument("--close", type=int, default=2, help="passes that close coverage over gaps between locks")
    p.add_argument("--scalp-group", default="scalp", help="the template's vertex group where hair grows")
    a = p.parse_args(argv)
    try:
        cap_verts, cap_tris, colour, report = scalp_cap(
            np.load(a.template), np.load(a.head), np.load(a.hair), a.texture, a.reach, a.front_inset, a.rim_inset,
            a.lift, a.close, a.scalp_group, a.probe_radius)
    except ValueError as error:
        p.error(str(error))
    if not len(cap_tris):
        p.error("no scalp lies under the hair: is the hair mesh in the head's template space?")
    np.savez_compressed(a.out, cap_verts=cap_verts, cap_tris=cap_tris, cap_colour=colour)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
