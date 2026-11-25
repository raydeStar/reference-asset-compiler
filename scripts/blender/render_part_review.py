"""Fixed views of a model with every face in its part's colour: the review of a part labelling.

A person looks at these before any part is painted: a fin labelled as hull
would be painted from the hull's picture. Front, three-quarter, side, back and
top, Workbench with cavity so the shapes read, on white.

Usage:
  blender -b --factory-startup --python scripts/blender/render_part_review.py -- \\
      <model.glb> <labels.npy> <colours.json> <out dir> [--size 900]

`labels.npy` holds one part index per face, in the glTF file's triangle order;
`colours.json` is a list of [r, g, b] (0..255), one per part index.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

TAG = "[PART-REVIEW]"
VIEWS = (("front", 90, 15), ("three-quarter", 45, 25), ("side", 0, 10), ("back", 270, 15), ("top", 0, 80))


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("labels")
    parser.add_argument("colours")
    parser.add_argument("out")
    parser.add_argument("--size", type=int, default=900)
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.source)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        print("{0} FAILED: expected one mesh, found {1}".format(TAG, len(meshes)))
        return 1
    obj = meshes[0]
    mesh = obj.data
    labels = np.load(args.labels)
    if len(labels) != len(mesh.polygons):
        print("{0} FAILED: {1} labels for {2} faces".format(TAG, len(labels), len(mesh.polygons)))
        return 1
    colours = np.asarray(json.load(open(args.colours, encoding="utf-8")), dtype=np.float32) / 255.0
    loop_face = np.empty(len(mesh.loops), dtype=np.int64)
    for polygon in mesh.polygons:
        loop_face[polygon.loop_start:polygon.loop_start + polygon.loop_total] = polygon.index
    rgba = np.ones((len(mesh.loops), 4), dtype=np.float32)
    rgba[:, :3] = colours[labels[loop_face]]
    attribute = mesh.color_attributes.new("parts", "FLOAT_COLOR", "CORNER")
    attribute.data.foreach_set("color", rgba.ravel())
    mesh.color_attributes.active_color = attribute

    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    middle, radius = (low + high) / 2, (high - low).length / 2
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    try:
        shading.color_type = "ATTRIBUTE"
    except TypeError:
        shading.color_type = "VERTEX"
    shading.show_cavity = True
    scene.render.resolution_x, scene.render.resolution_y = args.size, round(args.size * 0.7)
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("white")
    scene.world.color = (1, 1, 1)
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    camera.data.lens = 50
    scene.collection.objects.link(camera)
    scene.camera = camera
    turn = 90 if (high - low).y > (high - low).x else 0
    for name, yaw, pitch in VIEWS:
        yaw += turn
        direction = Vector((math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)),
                            -math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)),
                            math.sin(math.radians(pitch))))
        camera.location = middle + direction * radius * 2.9
        camera.rotation_euler = (middle - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(args.out, "parts-{0}.png".format(name))
        bpy.ops.render.render(write_still=True)
    print("{0} rendered {1} views into {2}".format(TAG, len(VIEWS), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
