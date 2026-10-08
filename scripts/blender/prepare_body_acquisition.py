"""Prepare the preserved garment/wrist acquisition for source-view UV baking.

Two ways to reach the review count. The older one (``--triangles`` alone) is a
uniform collapse of the whole acquisition, and it spends where the scan was
dense rather than where the eye reads: the acquisition's preserved hands are two
thirds of its 1.33M triangles, so a uniform 120k left about 29k on the hands.

``--hand-triangles`` gives each region its own count. The hands (everything
beyond ``--hands-beyond-abs-x`` along the T-pose arms) are collapsed to their
count while the garment is held still, then the garment to ``--triangles`` while
the hands are held still. Both collapses rank edges by quadric error alone, which
already spends on folds, hems and the outline: an extra fold/hem/outline weight
measured no better at mild strength and worse at any strength that changed the
result (docs/DECISIONS.md, 2026-10-07). ``--measure-samples`` records how far the
reduction sits from the source in those regions.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

FREE_GROUP = "RAC_Decimate_Free"
# Blender's collapse adds edge length x (2 - w1 - w2) x factor to an edge's
# cost: weight 1 collapses by quadric error alone, weight 0 is held still.
HOLD_FACTOR = 1000.0


def mesh_arrays(ob):
    mesh = ob.data
    mesh.calc_loop_triangles()
    verts = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", verts)
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tris)
    return verts.reshape(-1, 3), tris.reshape(-1, 3)


def _spread(values, edges, count, iterations):
    """Average each normal with its neighbours', ``iterations`` times."""
    a, b = edges[:, 0], edges[:, 1]
    degree = np.bincount(a, minlength=count) + np.bincount(b, minlength=count) + 1.0
    out = values.copy()
    for _ in range(iterations):
        total = out.copy()
        for axis in range(3):
            total[:, axis] += (np.bincount(a, out[b, axis], minlength=count)
                               + np.bincount(b, out[a, axis], minlength=count))
        out = total / degree[:, None]
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    return out


def detail_regions(verts, tris, fold_degrees=25.0, outline_band=0.25):
    """Where the eye reads a garment: folds and hems, and the outline.

    Folds and hems turn at the scale of cloth: the angle between a lightly
    smoothed normal and one averaged over a few centimetres (scan noise turns at
    a smaller scale and is averaged out of both). Open boundaries are hems by
    definition. The outline is where the coarse normal lies across the
    front/back or side view direction.
    """
    count = len(verts)
    face_normals = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    normals = np.zeros((count, 3))
    for corner in range(3):
        for axis in range(3):
            normals[:, axis] += np.bincount(tris[:, corner], face_normals[:, axis], minlength=count)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    unique, uses = np.unique(edges, axis=0, return_counts=True)
    fine = _spread(normals, unique, count, 2)
    coarse = _spread(fine, unique, count, 40)
    turn = np.degrees(np.arccos(np.clip(np.sum(fine * coarse, axis=1), -1.0, 1.0)))
    fold = turn >= 0.5 * fold_degrees
    fold[unique[uses == 1].ravel()] = True
    across = np.minimum(np.abs(coarse[:, 1]), np.abs(coarse[:, 0]))
    outline = across <= 0.5 * outline_band
    return {"folds_and_hems": fold, "outline": outline}


def hold(ob, free):
    """Let the ``free`` vertices collapse by quadric error and hold the rest still."""
    group = ob.vertex_groups.get(FREE_GROUP) or ob.vertex_groups.new(name=FREE_GROUP)
    group.add(np.flatnonzero(free).tolist(), 1.0, "REPLACE")
    held = np.flatnonzero(~free).tolist()
    if held:
        group.add(held, 0.0, "REPLACE")


def collapse(ob, ratio):
    mod = ob.modifiers.new("review-reduction", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = min(1.0, ratio)
    mod.use_collapse_triangulate = True
    mod.vertex_group = FREE_GROUP
    mod.vertex_group_factor = HOLD_FACTOR
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.vertex_groups.remove(ob.vertex_groups[FREE_GROUP])


def hand_tris(verts, tris, beyond):
    return np.abs(verts[tris].mean(axis=1)[:, 0]) > beyond


def deviation(source_verts, ob, pick):
    """Distance from source vertices to the reduction's surface, in millimetres."""
    if not len(pick):
        return {"samples": 0}
    verts, tris = mesh_arrays(ob)
    tree = BVHTree.FromPolygons(verts.tolist(), tris.tolist())
    distance = np.array([tree.find_nearest(source_verts[i].tolist())[3] for i in pick]) * 1000.0
    return {"samples": int(len(pick)),
            "p50_mm": round(float(np.percentile(distance, 50)), 3),
            "p99_mm": round(float(np.percentile(distance, 99)), 3),
            "max_mm": round(float(distance.max()), 3)}


def split_reduction(body, args):
    source_verts, source_tris = mesh_arrays(body)
    source_hand = np.abs(source_verts[:, 0]) > args.hands_beyond_abs_x
    source_hand_tris = int(hand_tris(source_verts, source_tris, args.hands_beyond_abs_x).sum())
    total = len(source_tris)

    hold(body, source_hand)
    collapse(body, (total - (source_hand_tris - args.hand_triangles)) / total)
    verts, tris = mesh_arrays(body)
    hands_now = int(hand_tris(verts, tris, args.hands_beyond_abs_x).sum())
    hold(body, np.abs(verts[:, 0]) <= args.hands_beyond_abs_x)
    collapse(body, (hands_now + args.triangles) / len(tris))

    verts, tris = mesh_arrays(body)
    hands = int(hand_tris(verts, tris, args.hands_beyond_abs_x).sum())
    summary = {
        "method": "each region collapsed by quadric error to its own count while the other is held still",
        "hands_beyond_abs_x_m": args.hands_beyond_abs_x,
        "source_triangles": {"hands": source_hand_tris, "garment": total - source_hand_tris},
        "targets": {"hands": args.hand_triangles, "garment": args.triangles},
        "triangles": {"hands": hands, "garment": len(tris) - hands},
    }
    if args.measure_samples:
        rng = np.random.default_rng(0)
        regions = detail_regions(source_verts, source_tris)
        masks = {"garment": ~source_hand,
                 "garment_folds_and_hems": ~source_hand & regions["folds_and_hems"],
                 "garment_outline": ~source_hand & regions["outline"],
                 "hands": source_hand}
        summary["deviation_from_source"] = {}
        for name, mask in masks.items():
            pick = np.flatnonzero(mask)
            pick = rng.choice(pick, size=min(args.measure_samples, len(pick)), replace=False)
            summary["deviation_from_source"][name] = deviation(source_verts, body, pick)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("--triangles", type=int, default=120000,
                   help="The whole body's count, or the garment's when --hand-triangles is given")
    p.add_argument("--hand-triangles", type=int, help="Give the hands their own count")
    p.add_argument("--hands-beyond-abs-x", type=float, default=0.80,
                   help="Metres from the midline along the T-pose arms where the hands begin")
    p.add_argument("--body-object",
                   help="the outfit's object in the acquisition blend (default: its only mesh)")
    p.add_argument("--measure-samples", type=int, default=0,
                   help="Source vertices per region to measure the reduction against (0: skip)")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.source).resolve()))
    if a.body_object:
        body = bpy.data.objects[a.body_object]
    else:
        meshes = [ob for ob in bpy.data.objects if ob.type == "MESH"]
        if len(meshes) != 1:
            raise SystemExit(f"{len(meshes)} meshes in the acquisition; name the outfit with --body-object.")
        body = meshes[0]
    for ob in list(bpy.data.objects):
        if ob != body:
            bpy.data.objects.remove(ob, do_unlink=True)
    body.hide_render = False
    body.hide_set(False)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    before = len(body.data.polygons)
    split = None
    if a.hand_triangles:
        if body.matrix_world != body.matrix_world.Identity(4):
            raise SystemExit("The hand boundary is measured in object space; apply the transform first.")
        split = split_reduction(body, a)
    else:
        mod = body.modifiers.new("review-reduction", "DECIMATE")
        mod.ratio = min(1.0, a.triangles / before)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    body.data.materials.clear()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.151917, island_margin=0.005, area_weight=0.5)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = body.data
    mesh.calc_loop_triangles()
    verts = np.array([body.matrix_world @ v.co for v in mesh.vertices])
    tris = np.array([list(t.vertices) for t in mesh.loop_triangles])
    loops = np.array([list(t.loops) for t in mesh.loop_triangles])
    uv = np.array([list(u.uv) for u in mesh.uv_layers.active.data])
    np.savez_compressed(out / "body.npz", verts=verts, tris=tris, tris_uv=loops, uv=uv)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "body-uv.blend"))
    receipt = {"source": str(Path(a.source).resolve()),
               "source_sha256": hashlib.sha256(Path(a.source).read_bytes()).hexdigest(),
               "source_polygons": before, "triangles": len(tris), "vertices": len(verts),
               "uv_method": "Blender Smart Project", "topology_review_pending": True}
    if split is not None:
        receipt["reduction"] = split
    (out / "body-preparation.json").write_text(json.dumps(receipt, indent=2))
    print("The tailor has retained the coat and repaired cuffs, sir.", json.dumps(receipt))


if __name__ == "__main__":
    main()
