"""Bake the full-resolution hair's paint and surface onto the reduced game hair (Cycles, CPU).

Mesh hair, step five (docs/CHARACTER_MESH_HAIR.md). The reduced mesh gets new
UVs (Smart UV Project), then a selected-to-active bake from the full-resolution
cut: its base colour, and a tangent-space normal map that keeps the blades'
fine relief. The cage reaches --cage metres out from the reduced surface: the
reduction moves thin blades by up to about a centimetre, and rays that miss
leave black texels (4 mm missed most of character-02's).

Usage:
  blender -b --factory-startup --python scripts/blender/bake_mesh_hair.py -- \
      <high.npz> <high-basecolor.png> <low.npz> <out_dir> [--size 2048] [--cage 0.015]

high.npz carries verts, tris and loop_uv; low.npz verts and tris. Writes
<out_dir>/hair-mesh.npz (verts, tris, loop_uv), hair-mesh-basecolor.png,
hair-mesh-normal.png and hair-mesh.json.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def mesh_object(name, verts, tris, loop_uv=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, np.float64).ravel())
    me.loops.add(tris.size)
    me.loops.foreach_set("vertex_index", tris.ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", np.arange(0, tris.size, 3))
    me.polygons.foreach_set("loop_total", np.full(len(tris), 3))
    me.update()
    if loop_uv is not None:
        uv = me.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", np.asarray(loop_uv, np.float32).ravel())
    me.validate()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    for name in ("high", "high_png", "low", "out"):
        p.add_argument(name)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--cage", type=float, default=0.015)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    h, lo = np.load(a.high), np.load(a.low)
    high = mesh_object("high", h["verts"], h["tris"].astype(np.int64), h["loop_uv"])
    mat = bpy.data.materials.new("high")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(a.high_png).resolve()))
    mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    high.data.materials.append(mat)

    low = mesh_object("low", lo["verts"], lo["tris"].astype(np.int64))
    for ob in scene.objects:
        ob.select_set(ob == low)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    lmat = bpy.data.materials.new("low")
    lmat.use_nodes = True
    low.data.materials.append(lmat)
    target = lmat.node_tree.nodes.new("ShaderNodeTexImage")
    lmat.node_tree.nodes.active = target

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 4
    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.cage_extrusion = a.cage
    bake.max_ray_distance = a.cage * 4
    bake.margin = 8
    bake.use_pass_direct = False
    bake.use_pass_indirect = False
    bake.use_pass_color = True
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    for kind, name, space in (("DIFFUSE", "hair-mesh-basecolor", "sRGB"), ("NORMAL", "hair-mesh-normal", "Non-Color")):
        img = bpy.data.images.new(name, a.size, a.size, alpha=False)
        img.colorspace_settings.name = space
        target.image = img
        bpy.ops.object.bake(type=kind)
        img.filepath_raw = str(out / f"{name}.png")
        img.file_format = "PNG"
        img.save()

    me = low.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    tris = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", tris)
    verts = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", verts)
    np.savez(out / "hair-mesh.npz", verts=verts.reshape(-1, 3), tris=tris.reshape(-1, 3), loop_uv=uv.reshape(-1, 2))
    receipt = {"stage": "bake_mesh_hair", "triangles": len(me.polygons), "texture_size": a.size, "cage_m": a.cage,
               "high_triangles": int(len(h["tris"]))}
    (out / "hair-mesh.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("BAKE_MESH_HAIR " + json.dumps(receipt))


if __name__ == "__main__":
    main()
