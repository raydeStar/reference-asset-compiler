"""Render one orthographic view of a conformed head and record its camera.

Landmark binding needs a picture of the template whose pixel-to-world mapping
is known exactly: a face detector reads the picture, and each landmark is
traced back to the template vertex under it. The JSON written beside the PNG
holds that mapping (centre, orthographic scale, resolution, view axes).

Usage:
  blender -b --factory-startup --python scripts/blender/render_mesh_view.py \
      -- <conform.npz> <out.png> <camera.json> [--rest] [--view front]
      [--resolution 1024] [--expression name=weight ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_conform_review import VIEWS, build_head, camera  # noqa: E402


def build_arrays(z):
    me = bpy.data.meshes.new("mesh")
    v, t = z["verts"].astype(np.float64), z["tris"].astype(np.int64)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.ravel())
    me.loops.add(t.size)
    me.loops.foreach_set("vertex_index", t.ravel())
    me.polygons.add(len(t))
    me.polygons.foreach_set("loop_start", np.arange(0, t.size, 3))
    me.polygons.foreach_set("loop_total", np.full(len(t), 3))
    me.update()
    me.shade_smooth()
    ob = bpy.data.objects.new("mesh", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("conform")
    p.add_argument("out")
    p.add_argument("camera_json")
    p.add_argument("--rest", action="store_true")
    p.add_argument("--view", default="front", choices=sorted(VIEWS))
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--expression", nargs="*", default=[])
    p.add_argument("--arrays", action="store_true", help="the input is a plain verts/tris mesh")
    a = p.parse_args(argv)

    z = np.load(a.conform)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "VERTEX"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = a.resolution
    if a.arrays:
        head = build_arrays(z)
        scene.display.shading.color_type = "SINGLE"
    else:
        head = build_head(z, z["rest"] if a.rest else None)
    for item in a.expression:
        name, w = item.split("=")
        head.data.shape_keys.key_blocks[name].value = float(w)
    pts = np.array([v.co for v in head.data.vertices])
    lo, hi = pts.min(0), pts.max(0)
    centre = (lo + hi) / 2
    size = float((hi - lo)[[0, 2]].max()) * 1.1
    camera(centre, VIEWS[a.view], size)
    scene.render.filepath = a.out
    bpy.ops.render.render(write_still=True)
    cam = scene.camera
    m = np.array(cam.matrix_world)
    Path(a.camera_json).write_text(json.dumps({
        "view": a.view, "resolution": a.resolution, "ortho_scale": size,
        "centre": centre.tolist(), "right": m[:3, 0].tolist(), "up": m[:3, 1].tolist(),
        "forward": (-m[:3, 2]).tolist(), "rest": a.rest,
    }, indent=1), encoding="utf-8")
    print("view", a.view, "->", a.out)


if __name__ == "__main__":
    main()
