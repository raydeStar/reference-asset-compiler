"""Render a conformed template head beside its acquisition, in several expressions.

Review evidence for template-conforming retopology: the same orthographic
cameras on the acquisition (the shape authority) and the conformed template,
then the template driven through its carried-across expression units, and a
wireframe pass that shows the edge loops a face rig depends on.

Usage:
  blender -b --factory-startup --python scripts/blender/render_conform_review.py \
      -- <conform.npz> <out_dir> [--resolution 768]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

POSES = {
    "neutral": {},
    "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0},
    "smile": {"mouth-corner-puller": 1.0, "eye-left-slit": 0.35, "eye-right-slit": 0.35},
    "jaw-open": {"mouth-open": 1.0},
    "brows-up": {"eyebrows-left-up": 1.0, "eyebrows-right-up": 1.0,
                 "eye-left-opened-up": 0.5, "eye-right-opened-up": 0.5},
    "angry": {"eyebrows-left-down": 1.0, "eyebrows-right-down": 1.0,
              "mouth-compression": 0.6, "nose-left-elevation": 0.4, "nose-right-elevation": 0.4},
    "oh": {"mouth-pursing": 0.8, "mouth-protusion": 0.5, "mouth-open": 0.35},
}
VIEWS = {"front": (0.0, -1.0, 0.0), "three-quarter": (0.62, -0.78, 0.0), "side": (1.0, 0.0, 0.0)}


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("conform")
    p.add_argument("out_dir")
    p.add_argument("--resolution", type=int, default=768)
    p.add_argument("--extra", nargs="*", default=[],
                   help="meshes rendered with the head (a hair shell), in its space")
    p.add_argument("--poses", nargs="*", default=None, help="subset of POSES to render")
    return p.parse_args(argv)


def build_head(z, coords=None):
    keep = z["keep_polys"]
    starts, totals, loops = z["loop_starts"], z["loop_totals"], z["loops"]
    polys = [loops[starts[i]:starts[i] + totals[i]] for i in keep]
    used = np.unique(np.concatenate(polys))
    remap = -np.ones(len(z["verts"]), np.int64)
    remap[used] = np.arange(len(used))
    me = bpy.data.meshes.new("conformed_head")
    base = z["verts"] if coords is None else coords
    me.from_pydata(base[used].tolist(), [], [remap[p].tolist() for p in polys])
    me.update()
    ob = bpy.data.objects.new("conformed_head", me)
    bpy.context.scene.collection.objects.link(ob)
    for poly in me.polygons:
        poly.use_smooth = True
    # Review colours: skin, eyeballs white with a dark iris facing forward.
    colour = np.tile([0.8, 0.78, 0.75, 1.0], (len(used), 1))
    for side in ("l", "r"):
        key = "vg__helper-{}-eye".format(side)
        if key not in z.files:
            continue
        idx = remap[z[key]]
        idx = idx[idx >= 0]
        pts = base[used][idx]
        centre = pts.mean(0)
        direction = pts - centre
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)
        forward = direction[:, 1] < -0.93
        colour[idx] = [0.95, 0.95, 0.95, 1.0]
        colour[idx[forward]] = [0.12, 0.08, 0.05, 1.0]
    attr = me.color_attributes.new("review", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", colour.ravel())
    me.color_attributes.active_color = attr
    me.color_attributes.render_color_index = me.color_attributes.active_color_index
    ob.shape_key_add(name="Basis")
    for k in z.files:
        if k.startswith("ex__"):
            sk = ob.shape_key_add(name=k[4:])
            co = (base[used] + z[k][used]).astype(np.float64)
            sk.data.foreach_set("co", co.ravel())
            sk.value = 0.0   # a new key starts at full strength in Blender 5.x
    return ob


def build_acquisition(z, offset):
    me = bpy.data.meshes.new("acquisition")
    v = z["acq_verts"].astype(np.float64) + np.array(offset)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.ravel())
    t = z["acq_tris"]
    me.loops.add(t.size)
    me.loops.foreach_set("vertex_index", t.ravel())
    me.polygons.add(len(t))
    me.polygons.foreach_set("loop_start", np.arange(0, t.size, 3))
    me.polygons.foreach_set("loop_total", np.full(len(t), 3))
    me.update()
    me.shade_smooth()
    ob = bpy.data.objects.new("acquisition", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def camera(centre, direction, ortho_scale):
    cam = bpy.data.objects.get("review_cam")
    if cam is None:
        cam = bpy.data.objects.new("review_cam", bpy.data.cameras.new("review_cam"))
        bpy.context.scene.collection.objects.link(cam)
        bpy.context.scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho_scale
    d = Vector(direction).normalized()
    cam.location = Vector(centre) + d * 2.0
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def render(path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    a = _args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(a.conform)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.8, 0.78, 0.75)
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = a.resolution
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w") if not scene.world else scene.world
    scene.world = world

    head = build_head(z)
    extras = []
    for path in a.extra:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        for ob in set(bpy.data.objects) - before:
            if ob.type == "MESH":
                attr = ob.data.color_attributes.new("review", "FLOAT_COLOR", "POINT")
                attr.data.foreach_set("color", np.tile([0.36, 0.22, 0.14, 1.0], len(ob.data.vertices)))
                ob.data.color_attributes.active_color = attr
                extras.append(ob)
    pts = np.array([v.co for v in head.data.vertices])
    lo, hi = pts.min(0), pts.max(0)
    centre = (lo + hi) / 2
    size = float((hi - lo)[[0, 2]].max()) * 1.15

    # Acquisition beside the template: same cameras, its own object.
    acq = build_acquisition(z, (0.0, 0.0, 0.0))
    for name, d in VIEWS.items():
        head.hide_render = True
        for ob in extras:
            ob.hide_render = True
        acq.hide_render = False
        camera(centre, d, size)
        render(out / "acquisition-{}.png".format(name))
    acq.hide_render = True
    head.hide_render = False
    for ob in extras:
        ob.hide_render = False

    keys = head.data.shape_keys.key_blocks
    scene.display.shading.color_type = "VERTEX"
    for pose, mix in POSES.items():
        if a.poses and pose not in a.poses:
            continue
        for k in keys[1:]:
            k.value = mix.get(k.name, 0.0)
        for name, d in VIEWS.items():
            if pose != "neutral" and name == "side":
                continue
            camera(centre, d, size)
            render(out / "{}-{}.png".format(pose, name))

    # Topology: the same neutral views with a wire cage over the surface.
    for k in keys[1:]:
        k.value = 0.0
    wire = head.copy()
    wire.data = head.data.copy()
    scene.collection.objects.link(wire)
    mod = wire.modifiers.new("wire", "WIREFRAME")
    mod.thickness = 0.0006
    mod.use_replace = True
    wire.color = (0.05, 0.05, 0.07, 1.0)
    head.color = (0.8, 0.78, 0.75, 1.0)
    scene.display.shading.color_type = "OBJECT"
    for name in ("front", "three-quarter"):
        camera(centre, VIEWS[name], size)
        render(out / "wire-{}.png".format(name))
    print("rendered review to", out)


if __name__ == "__main__":
    main()
