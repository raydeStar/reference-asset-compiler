"""Export the MakeHuman (hm08) template a humanoid is conformed onto.

A generated character mesh has the right silhouette and the wrong anatomy for
a rig: no eyeballs, lids fused into a groove, fingers as slabs, a surface of
marching-cube triangles. The template supplies what an acquisition cannot --
quad topology with joint loops, open lids, eyeballs, teeth, separate fingers,
facial expression shapes and a skeleton placed from its own vertices -- and the
conform stage moves it onto the acquired shape. The template never supplies
the visible identity; the acquisition and the approved image do.

This runs MPFB (the MakeHuman add-on, CC0 assets) in Blender and writes one
NPZ: the macro-shaped base mesh with its helpers, every vertex group, the
expression units as per-vertex deltas, and the chosen rig's joints and
weights. Nothing is saved into a .blend; the NPZ is the whole hand-off.

Usage:
  blender -b --python scripts/blender/export_human_template.py -- \
      <out.npz> <report.json> [--gender 1.0] [--age 0.5] [--muscle 0.6]
      [--weight 0.5] [--height 0.55] [--proportions 0.6]
      [--race caucasian] [--rig game_engine]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("report")
    for name, default in (("gender", 1.0), ("age", 0.5), ("muscle", 0.6),
                          ("weight", 0.5), ("height", 0.55),
                          ("proportions", 0.6)):
        p.add_argument("--" + name, type=float, default=default)
    p.add_argument("--race", default="caucasian",
                   choices=("caucasian", "african", "asian"))
    p.add_argument("--rig", default="game_engine")
    return p.parse_args(argv)


def _mpfb():
    # MPFB is a Blender extension; its package path is bl_ext.<repo>.mpfb.
    import importlib
    for repo in ("user_default", "blender_org"):
        try:
            return importlib.import_module("bl_ext." + repo + ".mpfb")
        except ImportError:
            continue
    raise SystemExit("MPFB extension is not installed or not enabled")


def surface_exposure(body, coords, rays=48):
    """Fraction of the hemisphere above each body vertex that sees open sky.

    The inside of the mouth, the eye sockets behind the lids, the nostrils and
    the ear canals face space the acquisition never captured; a closest-point
    fit drags them onto the outer surface and folds them. Exposure says which
    template surface an acquisition can vouch for at all.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    body_idx = {v.index for v in body.data.vertices
                for g in v.groups if body.vertex_groups[g.group].name == "body" and g.weight > 0.5}
    polys = [list(p.vertices) for p in body.data.polygons
             if all(i in body_idx for i in p.vertices)]
    tree = BVHTree.FromPolygons([Vector(c) for c in coords], polys, all_triangles=False)
    normals = np.zeros_like(coords)
    for p in polys:
        a, b, c = coords[p[0]], coords[p[1]], coords[p[2]]
        fn = np.cross(b - a, c - a)
        for i in p:
            normals[i] += fn
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    rng = np.random.default_rng(7)
    dirs = rng.normal(size=(rays, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    out = np.zeros(len(coords), np.float32)
    for i in body_idx:
        n = normals[i]
        hemi = np.where((dirs @ n)[:, None] < 0, -dirs, dirs)
        origin = Vector(coords[i] + n * 2e-4)
        free = 0
        for d in hemi:
            if tree.ray_cast(origin, Vector(d), 1.0)[0] is None:
                free += 1
        out[i] = free / rays
    return out


def main():
    a = _args()
    mpfb = _mpfb()
    from importlib import import_module
    HumanService = import_module(mpfb.__name__ + ".services.humanservice").HumanService
    TargetService = import_module(mpfb.__name__ + ".services.targetservice").TargetService
    LocationService = import_module(mpfb.__name__ + ".services.locationservice").LocationService

    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)

    race = {"caucasian": 0.0, "african": 0.0, "asian": 0.0}
    race[a.race] = 1.0
    macro = {"gender": a.gender, "age": a.age, "muscle": a.muscle,
             "weight": a.weight, "proportions": a.proportions,
             "height": a.height, "cupsize": 0.5, "firmness": 0.5, "race": race}
    body = HumanService.create_human(mask_helpers=False, detailed_helpers=True,
                                     extra_vertex_groups=True,
                                     feet_on_ground=True, macro_detail_dict=macro)
    n = len(body.data.vertices)

    def mixed_coords():
        deps = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(deps)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        return co.reshape(-1, 3) @ np.array(body.matrix_world)[:3, :3].T \
            + np.array(body.matrix_world)[:3, 3]

    base = mixed_coords()

    # Expression units: load each at weight 0, read its delta against Basis.
    units_dir = Path(LocationService.get_mpfb_data("targets")) / "expression" / "units" / a.race
    expr = {}
    for path in sorted(units_dir.glob("*.target.gz")):
        name = path.name[: -len(".target.gz")]
        TargetService.load_target(body, str(path), weight=0.0, name="ex-" + name)
        sk = body.data.shape_keys.key_blocks["ex-" + name]
        ref = sk.relative_key
        a_co = np.empty(n * 3)
        sk.data.foreach_get("co", a_co)
        b_co = np.empty(n * 3)
        ref.data.foreach_get("co", b_co)
        d = (a_co - b_co).reshape(-1, 3) @ np.array(body.matrix_world)[:3, :3].T
        expr[name] = d.astype(np.float32)

    # Polygons as a flat index list plus offsets: hm08 is quads, helpers mix.
    loops = np.empty(len(body.data.loops), dtype=np.int64)
    body.data.loops.foreach_get("vertex_index", loops)
    starts = np.empty(len(body.data.polygons), dtype=np.int64)
    body.data.polygons.foreach_get("loop_start", starts)
    totals = np.empty(len(body.data.polygons), dtype=np.int64)
    body.data.polygons.foreach_get("loop_total", totals)

    exposure = surface_exposure(body, base)

    # MakeHuman's own UV layout, per loop: the face, lids and lips have their
    # regions in it, so paint baked onto the template lands where a skin
    # material expects it.
    uv = np.zeros(len(body.data.loops) * 2)
    if body.data.uv_layers:
        body.data.uv_layers[0].data.foreach_get("uv", uv)

    groups = {}
    names = {vg.index: vg.name for vg in body.vertex_groups}
    for v in body.data.vertices:
        for g in v.groups:
            if g.weight > 0.5:
                groups.setdefault(names[g.group], []).append(v.index)

    # The rig: MPFB places every joint from the template's own vertices, so a
    # conformed template carries an anatomically placed skeleton with it.
    rig = HumanService.add_builtin_rig(body, a.rig, import_weights=True)
    bones = []
    for b in rig.data.bones:
        bones.append({"name": b.name,
                      "parent": b.parent.name if b.parent else None,
                      "head": list(rig.matrix_world @ b.head_local),
                      "tail": list(rig.matrix_world @ b.tail_local),
                      "roll_z": list(rig.matrix_world.to_3x3() @ b.z_axis)})
    bone_names = [b["name"] for b in bones]
    weights = np.zeros((n, len(bone_names)), dtype=np.float32)
    column = {vg.index: bone_names.index(vg.name)
              for vg in body.vertex_groups if vg.name in bone_names}
    for v in body.data.vertices:
        for g in v.groups:
            j = column.get(g.group)
            if j is not None and g.weight > 0.0:
                weights[v.index, j] = g.weight

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"verts": base.astype(np.float64), "loops": loops,
              "loop_starts": starts, "loop_totals": totals,
              "weights": weights, "bone_names": np.array(bone_names),
              "exposure": exposure, "loop_uv": uv.reshape(-1, 2).astype(np.float32)}
    for k, idx in groups.items():
        arrays["vg__" + k] = np.array(sorted(idx), dtype=np.int64)
    for k, d in expr.items():
        arrays["ex__" + k] = d
    np.savez_compressed(out, **arrays)

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    report = {
        "schema": "reference-asset-compiler.human-template.v1",
        "template": "MakeHuman hm08 base mesh via MPFB " + ".".join(
            str(x) for x in getattr(mpfb, "bl_info", {}).get("version", ())),
        "asset_license": "CC0 (MakeHuman base mesh, targets and rigs)",
        "macro": macro, "rig": a.rig,
        "vertices": n, "polygons": int(len(starts)),
        "groups": {k: len(v) for k, v in sorted(groups.items())},
        "expression_units": sorted(expr),
        "bones": bones,
        "npz": str(out), "npz_sha256": digest,
    }
    Path(a.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("template", n, "verts", len(starts), "polys", len(expr), "units",
          len(bones), "bones ->", out)


main()
