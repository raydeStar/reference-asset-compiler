"""Render an exported GLB's clips for the skin-integrity sweep.

blender -b --factory-startup --python-exit-code 1 --python scripts/blender/render_skin_sweep.py \
    -- animated.glb work/<case>/sweep-renders --clips MM_Idle,MF_Unarmed_Walk_Fwd

Each clip is sampled at evenly spaced times and rendered from the four fixed
views with an orthographic camera, a transparent background and back faces in
flat magenta. The bind pose is rendered first as clip `__bind__`. Measure the
output with `rac animation skin-sweep`; this script makes no judgement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector

SCHEMA = "reference-asset-compiler.skin-sweep-renders.v1"
VIEWS = {"front": 0, "three_quarter": 45, "side": 90, "back": 180}
BACKFACE_RGB = [1.0, 0.0, 1.0]
FRAMING = 1.3  # orthographic width as a multiple of bind height


def evaluated_bounds(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        points = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", points)
        evaluated.to_mesh_clear()
        if not len(points):
            continue
        world = np.asarray(evaluated.matrix_world)
        points = points.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
        lo, hi = np.minimum(lo, points.min(0)), np.maximum(hi, points.max(0))
    if not np.isfinite(lo).all():
        raise ValueError("Evaluated meshes have no finite vertices.")
    return lo, hi


def label_material():
    material = bpy.data.materials.new("SkinSweepLabels")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    front = nodes.new("ShaderNodeBsdfDiffuse")
    front.inputs["Color"].default_value = (.6, .6, .62, 1)
    back = nodes.new("ShaderNodeEmission")
    back.inputs["Color"].default_value = (*BACKFACE_RGB, 1)
    geometry, mix, out = nodes.new("ShaderNodeNewGeometry"), nodes.new("ShaderNodeMixShader"), nodes.new("ShaderNodeOutputMaterial")
    links.new(geometry.outputs["Backfacing"], mix.inputs["Fac"])
    links.new(front.outputs[0], mix.inputs[1])
    links.new(back.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(material, "use_backface_culling"):
        material.use_backface_culling = False
    return material


def setup_render(resolution):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("SkinSweepWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = .35
    scene.world = world
    sun = bpy.data.objects.new("SkinSweepSun", bpy.data.lights.new("SkinSweepSun", type="SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    # EEVEE needs a GPU even in the background: RAC_RENDER_DEVICE=CPU renders with Cycles on the CPU.
    if os.environ.get("RAC_RENDER_DEVICE", "").upper() == "CPU":
        scene.render.engine = "CYCLES"
        # Denoising would smear the magenta label into its neighbours.
        scene.cycles.device, scene.cycles.samples, scene.cycles.use_denoising = "CPU", 4, False
    else:
        scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")
                                   if e in engines or e == "CYCLES")
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_layers[0].material_override = label_material()
    camera = bpy.data.objects.new("SkinSweepCamera", bpy.data.cameras.new("SkinSweepCamera"))
    camera.data.type = "ORTHO"
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def aim(camera, centre, height, azimuth):
    angle = math.radians(azimuth)
    camera.data.ortho_scale = height * FRAMING
    camera.data.clip_end = height * 20
    camera.location = Vector(centre) + Vector((math.sin(angle), -math.cos(angle), 0)) * height * 5
    camera.rotation_euler = (Vector(centre) - camera.location).to_track_quat("-Z", "Y").to_euler()


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--clips", help="Comma-separated clip names; default is every imported clip")
    parser.add_argument("--samples", type=int, default=8, help="Evenly spaced times per clip, endpoints included")
    parser.add_argument("--resolution", type=int, default=900)
    parser.add_argument("--exclude-mesh", action="append", default=[],
                        help="Hide meshes whose name contains this text, e.g. hair cards")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("Choose a fresh output directory; earlier renders are evidence.")
    if not 2 <= args.samples <= 200 or not 64 <= args.resolution <= 4096:
        raise ValueError("Samples must be 2-200 and resolution 64-4096.")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.asset.resolve()))
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(rigs) != 1 or not rigs[0].animation_data:
        raise ValueError("Expected one animated armature.")
    rig = rigs[0]
    meshes, hidden, unbound = [], [], []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if any(text in obj.name for text in args.exclude_mesh):
            obj.hide_render = True
            hidden.append(obj.name)
        elif obj.parent == rig or any(m.type == "ARMATURE" and m.object == rig for m in obj.modifiers):
            meshes.append(obj)
        else:
            # Still rendered as delivered, but a stray helper must not set the framing.
            unbound.append(obj.name)
    if not meshes:
        raise ValueError("No rig-bound meshes left to render.")
    # Imported glTF clips live in NLA strips; match by track or original action name.
    strips = {}
    for track in rig.animation_data.nla_tracks:
        for strip in track.strips:
            for name in {track.name, strip.action.name if strip.action else track.name}:
                strips.setdefault(name, []).append((track, strip))
    wanted = args.clips.split(",") if args.clips else sorted({t.name for t in rig.animation_data.nla_tracks})
    for name in wanted:
        if len(strips.get(name, [])) != 1:
            raise ValueError(f"Expected exactly one imported clip named {name!r}.")
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    rig.animation_data.action = None
    for track in rig.animation_data.nla_tracks:
        track.mute, track.is_solo = True, False
    for bone in rig.pose.bones:
        bone.location, bone.scale = (0, 0, 0), (1, 1, 1)
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = (1, 0, 0, 0)
    bpy.context.view_layer.update()
    lo, hi = evaluated_bounds(meshes)
    height = float(hi[2] - lo[2])
    if not height > 0:
        raise ValueError("Bind pose has no height.")
    camera = setup_render(args.resolution)
    frames = []

    def render(clip, sample, time_s):
        centre = (np.add(*evaluated_bounds(meshes)) / 2).tolist()
        for view, azimuth in VIEWS.items():
            aim(camera, centre, height, azimuth)
            image = f"{clip}/s{sample:02d}-{view}.png"
            scene.render.filepath = str(args.output / image)
            bpy.ops.render.render(write_still=True)
            frames.append({"clip": clip, "sample": sample, "time_s": round(time_s, 6), "view": view,
                           "image": image, "centre": [round(c, 5) for c in centre]})

    render("__bind__", 0, 0.0)
    for name in wanted:
        chosen, strip = strips[name][0]
        for track in rig.animation_data.nla_tracks:
            track.mute = track != chosen
        start, end = strip.frame_start, strip.frame_end
        if end <= start:
            raise ValueError(f"Clip {name!r} has no duration.")
        for sample in range(args.samples):
            frame = start + (end - start) * sample / (args.samples - 1)
            scene.frame_set(math.floor(frame), subframe=frame % 1)
            bpy.context.view_layer.update()
            render(name, sample, (frame - start) / fps)
        print(f"SKIN_SWEEP rendered {name}")
    manifest = {"schema": SCHEMA, "asset": str(args.asset.resolve()),
                "asset_sha256": hashlib.sha256(args.asset.read_bytes()).hexdigest(),
                "blender": bpy.app.version_string, "engine": scene.render.engine,
                "resolution": args.resolution, "pixels_per_metre": args.resolution / (height * FRAMING),
                "bind_height_m": height, "views": VIEWS, "backface_rgb": BACKFACE_RGB,
                "samples_per_clip": args.samples, "clips": wanted, "hidden_meshes": sorted(hidden),
                "unbound_meshes": sorted(unbound),
                "frames": frames}
    (args.output / "sweep.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"SKIN_SWEEP {len(frames)} renders -> {args.output}; measure with `rac animation skin-sweep`.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
