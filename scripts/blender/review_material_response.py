"""Render paired studio views with a moving key; run with background Blender, after the sweep."""

import argparse
import hashlib
import html
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def render(source, directory, framing, size, samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
    scene = bpy.context.scene
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("There is no mesh to light.")
    for obj in scene.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
    if framing is None:
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector([min(v[i] for v in corners) for i in range(3)])
        hi = Vector([max(v[i] for v in corners) for i in range(3)])
        framing = ((lo + hi) / 2, (hi - lo).length)
    center, span = framing
    if not math.isfinite(span) or span <= 0:
        raise ValueError("Cannot frame a zero-sized asset.")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.seed = 231
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("Neutral studio")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.25, 0.25, 0.25, 1)
    bg.inputs[1].default_value = 0.65
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    cam = bpy.data.objects.new("Studio camera", bpy.data.cameras.new("Studio camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span * 1.07
    cam.data.clip_start, cam.data.clip_end = span * 0.005, span * 12

    def aim(obj, offset):
        obj.location = center + Vector(offset) * span
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()

    def card(name, power, w, h, offset):
        lamp = bpy.data.lights.new(name, "AREA")
        lamp.shape = "RECTANGLE"
        lamp.energy = power * span**2
        lamp.size, lamp.size_y = w * span, h * span
        obj = bpy.data.objects.new(name, lamp)
        scene.collection.objects.link(obj)
        aim(obj, offset)
        return obj

    key = card("Traveling softbox", 91, 0.34, 1.15, (-0.9, -1.3, 1.0))
    card("Broad fill", 68, 1.4, 1.3, (1.1, -0.7, 0.9))
    card("Edge card", 70, 0.37, 0.95, (-0.7, 1.1, 0.9))
    views = ["front", "quarter", "back", "light-left", "light-center", "light-right"]
    for i, name in enumerate(views):
        direction = [(0, -1, 0.08), (-0.64, -1, 0.16), (0.3, 1, 0.12)][i if i < 3 else 1]
        aim(cam, Vector(direction).normalized() * 3)
        if i >= 3:
            az = math.radians((-95, -45, 15)[i - 3])
            aim(key, (1.55 * math.sin(az), -1.55 * math.cos(az), 0.70))
        scene.render.filepath = str((directory / (name + ".png")).resolve())
        bpy.ops.render.render(write_still=True)
    return framing, views


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--size", type=int, default=600)
    parser.add_argument("--samples", type=int, default=24)
    args = parser.parse_args(argv)
    if not 128 <= args.size <= 2048 or not 2 <= args.samples <= 256:
        parser.error("Use 128–2048 pixels and 2–256 samples.")
    if args.output.exists():
        parser.error("Choose a new review directory to retain earlier evidence.")
    framing = None
    for tag in ("before", "after"):
        path = args.output / tag
        path.mkdir(parents=True)
        framing, views = render(getattr(args, tag), path, framing, args.size, args.samples)
    options = "".join(f"<option>{html.escape(v)}</option>" for v in views)
    page = """<!doctype html><html lang=en><meta charset=utf-8><title>Material response review</title>
<style>body{background:#192126;color:#e8eceb;font:17px system-ui;max-width:1240px;margin:3vw auto;padding:12px}select{font:inherit}section{display:flex;gap:1vw}figure{width:50%;margin:16px 0}img{width:100%}</style>
<h1>Material response review</h1><p>Compare the same camera and illumination. The three light positions share one camera.</p>
<label>View <select id=v>OPTIONS</select></label><section><figure><figcaption>Before</figcaption><img id=a src="before/front.png" alt="Before sweep"></figure>
<figure><figcaption>After</figcaption><img id=b src="after/front.png" alt="After sweep"></figure></section>
<script>v.onchange=()=>{a.src='before/'+v.value+'.png';b.src='after/'+v.value+'.png'}</script></html>"""
    (args.output / "Review.html").write_text(page.replace("OPTIONS", options), encoding="utf8")
    receipt = {
        tag + "_sha256": hashlib.sha256(getattr(args, tag).read_bytes()).hexdigest()
        for tag in ("before", "after")
    }
    receipt.update(
        views=views,
        center=list(framing[0]),
        span=framing[1],
        samples=args.samples,
        resolution=args.size,
        blender=bpy.app.version_string,
        visual_approval="pending",
    )
    (args.output / "review.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    print("MATERIAL_REVIEW_OK -- the lighting has agreed to testify.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1 :])
