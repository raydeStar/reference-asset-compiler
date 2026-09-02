"""Heal a generated mesh into something a quad remesher will accept.

The meshes in this project looked catastrophically broken -- field-scout-male
reads as 1,915 disconnected components with 25,591 non-manifold edges -- and
that reading is wrong. Exporters split a vertex wherever the UV or normal is
discontinuous, and re-importing without welding turns every seam into a
separate island. Welding at 0.1 mm takes the same mesh to 9 components and 320
non-manifold edges: the geometry was always nearly clean.

So the order matters. Weld first, then judge, then repair:

  1. Weld by distance      undo the export's vertex splitting
  2. Drop tiny shells      stray fragments that contribute no silhouette
  3. Fill holes            close the small boundary loops that remain
  4. Consistent normals    QuadriFlow refuses inconsistent winding

Reports the numbers at every step so a refusal downstream is explainable
rather than mysterious.

Usage:
  blender -b --factory-startup --python scripts/blender/heal_mesh.py \
      -- <in.fbx|glb> <out.blend> <report.json> \
         [--weld 0.0001] [--min-shell-frac 0.001] [--hole-sides 64]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def measure(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen = set()
    shells = []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack, size = [vert], 0
        seen.add(vert.index)
        while stack:
            current = stack.pop()
            size += 1
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        shells.append(size)
    shells.sort(reverse=True)
    result = {
        "verts": len(bm.verts),
        "faces": len(bm.faces),
        "components": len(shells),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
        "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
        "largest_shells": shells[:6],
    }
    bm.free()
    result["quadriflow_viable"] = (
        result["non_manifold_edges"] == 0 and result["boundary_edges"] == 0)
    return result


def edit(action):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    action()
    bpy.ops.object.mode_set(mode="OBJECT")


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out_blend, report_path = Path(argv[0]), Path(argv[1]), Path(argv[2])
    weld = arg(argv, "--weld", 0.0001, float)
    min_shell_frac = arg(argv, "--min-shell-frac", 0.001, float)
    hole_sides = arg(argv, "--hole-sides", 64, int)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix = src.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    else:
        bpy.ops.wm.open_mainfile(filepath=str(src))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[HEAL] FAILED: no mesh")
        return 1
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)

    report = {"source": str(src), "steps": {}}
    report["steps"]["imported"] = measure(obj)
    print("[HEAL] imported: {0} comps, {1} non-manifold".format(
        report["steps"]["imported"]["components"],
        report["steps"]["imported"]["non_manifold_edges"]))

    edit(lambda: bpy.ops.mesh.remove_doubles(threshold=weld))
    report["steps"]["welded"] = measure(obj)
    print("[HEAL] welded @{0}: {1} comps, {2} non-manifold".format(
        weld, report["steps"]["welded"]["components"],
        report["steps"]["welded"]["non_manifold_edges"]))

    # Drop shells too small to matter. Eyes and teeth are legitimately separate
    # and are preserved by the fraction test; stray specks are not.
    total_verts = report["steps"]["welded"]["verts"]
    threshold = max(int(total_verts * min_shell_frac), 8)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen, drop = set(), []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack, group = [vert], []
        seen.add(vert.index)
        while stack:
            current = stack.pop()
            group.append(current.index)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        if len(group) < threshold:
            drop.extend(group)
    bm.free()

    if drop:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        for index in drop:
            obj.data.vertices[index].select = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.delete(type="VERT")
        bpy.ops.object.mode_set(mode="OBJECT")
    report["dropped_small_shell_verts"] = len(drop)
    report["steps"]["shells_pruned"] = measure(obj)
    print("[HEAL] pruned {0} stray verts: {1} comps, {2} non-manifold".format(
        len(drop), report["steps"]["shells_pruned"]["components"],
        report["steps"]["shells_pruned"]["non_manifold_edges"]))

    edit(lambda: bpy.ops.mesh.fill_holes(sides=hole_sides))
    edit(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    report["steps"]["holes_filled"] = measure(obj)
    print("[HEAL] holes filled: {0} comps, {1} non-manifold, {2} boundary".format(
        report["steps"]["holes_filled"]["components"],
        report["steps"]["holes_filled"]["non_manifold_edges"],
        report["steps"]["holes_filled"]["boundary_edges"]))

    report["ok"] = True
    report["quadriflow_viable"] = report["steps"]["holes_filled"]["quadriflow_viable"]
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[HEAL] {0} -> {1}  quadriflow_viable={2}".format(
        src.name, out_blend.name, report["quadriflow_viable"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
