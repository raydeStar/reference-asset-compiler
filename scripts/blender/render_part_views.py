"""Render a painted model from many angles, and record which face every pixel shows.

The part labeller (`label_parts.py`) finds a model's parts in pictures of it:
a detector draws boxes round "a red fin" or "a wooden seat" in each view, and
the votes are carried back onto the faces those pixels show. That needs the
two to agree exactly, so the face under each pixel is found by casting a ray
through it against the very mesh the render drew, not estimated afterwards.

24 views: eight round the model at 20 and at 55 degrees up, one from almost
straight above, four from a little below, and three more at 35 degrees. The
camera stands far enough back that the whole model is in frame from every side.

Writes into <out dir>:
- view-NN.png: the painted model (Workbench, the base colour texture, flat studio light);
- view-NN-faces.npy: int32, the face index under each pixel centre of an
  <id size> square grid, -1 where the ray hits nothing;
- views.json: each view's angles and camera, the field of view, the face count.

Face indices are the glTF file's own triangle order, which is the order every
other script in this pipeline reads the mesh in.

Usage:
  blender -b --factory-startup --python scripts/blender/render_part_views.py -- \\
      <painted.glb> <out dir> [--size 1024] [--id-size 768]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

TAG = "[PART-VIEWS]"
VIEWS = ([(azimuth, 20) for azimuth in range(0, 360, 45)]
         + [(azimuth, 55) for azimuth in range(0, 360, 45)]
         + [(0, 88), (90, -15), (270, -15), (0, -15), (180, -15), (45, 35), (135, 35), (225, 35)])


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--id-size", type=int, default=768)
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.source)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        print("{0} FAILED: the model should be one mesh, as a painted model is; it holds {1}".format(
            TAG, len(meshes)))
        return 1
    obj = meshes[0]
    # The ray tree reads the mesh in its own coordinates, and the importer
    # leaves glTF's axis turn on the object: applied, rays and render agree.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    middle, radius = (low + high) / 2, (high - low).length / 2

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "TEXTURE"
    shading.show_cavity = False
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("white")
    scene.world.color = (1, 1, 1)
    camera_data = bpy.data.cameras.new("camera")
    camera_data.lens, camera_data.sensor_width = 50, 36
    camera = bpy.data.objects.new("camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    fov = 2 * math.atan(18 / 50)
    distance = radius / math.sin(fov / 2) * 0.8
    half = math.tan(fov / 2)
    centres = (np.arange(args.id_size) + 0.5) / args.id_size

    records = []
    for number, (azimuth, elevation) in enumerate(VIEWS):
        started = time.time()
        direction = Vector((math.cos(math.radians(elevation)) * math.cos(math.radians(azimuth)),
                            math.cos(math.radians(elevation)) * math.sin(math.radians(azimuth)),
                            math.sin(math.radians(elevation))))
        camera.location = middle + direction * distance
        camera.rotation_euler = (middle - camera.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        scene.render.filepath = os.path.join(args.out, "view-{0:02d}.png".format(number))
        bpy.ops.render.render(write_still=True)
        frame = camera.matrix_world
        origin = frame.translation.copy()
        turn = frame.to_3x3()
        right, up, forward = turn @ Vector((1, 0, 0)), turn @ Vector((0, 1, 0)), turn @ Vector((0, 0, -1))
        faces = np.full((args.id_size, args.id_size), -1, dtype=np.int32)
        for row in range(args.id_size):
            y = (1 - 2 * centres[row]) * half
            for column in range(args.id_size):
                x = (2 * centres[column] - 1) * half
                hit = bvh.ray_cast(origin, (forward + right * x + up * y).normalized(), distance * 2)
                if hit[2] is not None:
                    faces[row, column] = hit[2]
        np.save(os.path.join(args.out, "view-{0:02d}-faces.npy".format(number)), faces)
        records.append({"view": number, "azimuth": azimuth, "elevation": elevation,
                        "location": [round(v, 5) for v in camera.location],
                        "faces_seen": int(len(np.unique(faces[faces >= 0]))),
                        "seconds": round(time.time() - started, 1)})
        print("{0} view {1}: azimuth {2}, elevation {3}, {4} faces seen".format(
            TAG, number, azimuth, elevation, records[-1]["faces_seen"]), flush=True)
    with open(os.path.join(args.out, "views.json"), "w", encoding="utf-8") as stream:
        json.dump({"schema": "reference-asset-compiler.part-views.v1", "source": args.source,
                   "size": args.size, "id_size": args.id_size, "fov": fov,
                   "faces": len(obj.data.polygons), "views": records}, stream, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
