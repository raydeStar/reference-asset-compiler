"""Painted close-ups of Ennix's outfit from an assembly, for before/after reviews.

Opens a rebuild's ``assembly/Ennix_Character_Review.blend`` -- painted outfit,
painted head, groom, the assembly's own lights and exposure -- and renders fixed
perspective close-ups of the jacket, scarf, sash, sleeves, hands, trousers and
boots. Two builds rendered with this script differ only in what they were built
from. ``--wire`` draws the outfit's triangle edges over its paint, so a review
can see where the triangles went without a grey clay pass.

Usage:
  blender -b --factory-startup --python scripts/blender/render_outfit_review.py -- \
      <assembly.blend> <out_dir> [--resolution 1024] [--samples 64] [--wire] [--device GPU|CPU]
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

OUTFIT = "Ennix_Outfit_And_Hands"
# name: (camera location, target, frame width in metres, what to look at)
VIEWS = {
    "jacket-front": ((-0.18, -1.08, 1.36), (0.0, 0.0, 1.30), 0.78, "jacket, lapels, scarf and vest"),
    "jacket-back": ((0.12, 1.08, 1.36), (0.0, 0.0, 1.30), 0.78, "jacket back, seams and collar"),
    "sash-and-belt": ((0.70, -0.98, 0.92), (0.14, -0.04, 0.82), 0.74, "belt, sash folds and torn hem"),
    "sleeve-and-hand": ((0.88, -0.70, 1.30), (0.80, 0.0, 1.38), 0.56, "rolled sleeve, forearm, wrist and hand"),
    "trousers-and-boots": ((-0.40, -1.20, 0.46), (0.0, 0.0, 0.40), 1.00, "trouser folds, boot straps and buckles"),
    "outline-back-three-quarter": ((1.30, 1.30, 1.15), (0.0, 0.0, 1.00), 1.30, "the outline against the background"),
}


def configure(scene, a):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    if a.device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type != "CPU"
    scene.cycles.device = a.device
    scene.render.resolution_x = scene.render.resolution_y = a.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False


def draw_wire(outfit):
    """Mix a one-pixel dark line into the outfit's paint at every triangle edge."""
    for material in outfit.data.materials:
        nodes, links = material.node_tree.nodes, material.node_tree.links
        texture = next(node for node in nodes if node.type == "TEX_IMAGE")
        bsdf = nodes["Principled BSDF"]
        wire = nodes.new("ShaderNodeWireframe")
        wire.use_pixel_size = True
        wire.inputs["Size"].default_value = 1.0
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["B"].default_value = (0.02, 0.02, 0.025, 1.0)
        links.new(wire.outputs["Fac"], mix.inputs["Factor"])
        links.new(texture.outputs["Color"], mix.inputs["A"])
        links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        links.new(mix.outputs["Result"], bsdf.inputs["Emission Color"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("assembly")
    p.add_argument("out")
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--views", nargs="+", default=list(VIEWS), choices=list(VIEWS))
    p.add_argument("--wire", action="store_true", help="draw the outfit's triangle edges over its paint")
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.assembly).resolve()))
    scene = bpy.context.scene
    configure(scene, a)
    outfit = bpy.data.objects[OUTFIT]
    outfit.data.calc_loop_triangles()
    if a.wire:
        draw_wire(outfit)
    camera = bpy.data.objects.new("Outfit_Review_Camera", bpy.data.cameras.new("Outfit_Review_Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.lens, camera.data.sensor_width, camera.data.sensor_fit = 50.0, 36.0, "HORIZONTAL"
    rendered = {}
    for name in a.views:
        location, target, width, what = VIEWS[name]
        eye, look = Vector(location), Vector(target)
        # Keep each view's frame width whatever the distance: width = distance x 36/50.
        direction = (eye - look).normalized()
        eye = look + direction * (width * camera.data.lens / camera.data.sensor_width)
        camera.location = eye
        camera.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()
        path = out / ("{0}{1}.png".format(name, "-wire" if a.wire else ""))
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered[name] = {"file": path.name, "what": what, "frame_width_m": width,
                          "camera": [round(v, 4) for v in eye], "target": list(target)}
    record = {"assembly": str(Path(a.assembly).resolve()), "outfit_triangles": len(outfit.data.loop_triangles),
              "resolution": a.resolution, "samples": a.samples, "device": a.device, "wire": a.wire,
              "views": rendered}
    (out / ("renders{0}.json".format("-wire" if a.wire else ""))).write_text(json.dumps(record, indent=2))
    print("RAC_OUTFIT_REVIEW_OK", json.dumps({k: v["file"] for k, v in rendered.items()}))


if __name__ == "__main__":
    main()
