# SPDX-License-Identifier: MIT
"""Render clean front and 3/4 review views of Character02 for asset review."""

import bpy
import math
import os
import sys
import time
from mathutils import Vector

def point_camera_at(cam, target_pos):
    direction = target_pos - cam.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam.rotation_euler = rot_quat.to_euler()

def main():
    out_dir = r"C:\work\character-02\review_views_v22"
    if "--out-dir" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out-dir") + 1]
    os.makedirs(out_dir, exist_ok=True)

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 48
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024

    cam = bpy.data.objects.get("ReviewCam")
    if not cam:
        cam_data = bpy.data.cameras.new("ReviewCam")
        cam = bpy.data.objects.new("ReviewCam", cam_data)
        scene.collection.objects.link(cam)
    scene.camera = cam

    views = [
        {
            "name": "01_Front_FullBody",
            "cam_pos": Vector((0.0, -4.6, 0.88)),
            "target": Vector((0.0, 0.0, 0.88)),
            "lens": 50.0,
        },
        {
            "name": "02_ThreeQuarter_Left_FullBody",
            "cam_pos": Vector((-2.6, -3.8, 0.92)),
            "target": Vector((0.0, 0.0, 0.88)),
            "lens": 50.0,
        },
        {
            "name": "03_ThreeQuarter_Right_FullBody",
            "cam_pos": Vector((2.6, -3.8, 0.92)),
            "target": Vector((0.0, 0.0, 0.88)),
            "lens": 50.0,
        },
        {
            "name": "04_Front_UpperBody",
            "cam_pos": Vector((0.0, -2.1, 1.38)),
            "target": Vector((0.0, 0.0, 1.38)),
            "lens": 60.0,
        },
        {
            "name": "05_ThreeQuarter_UpperBody",
            "cam_pos": Vector((-1.3, -1.8, 1.42)),
            "target": Vector((0.0, 0.0, 1.38)),
            "lens": 60.0,
        },
    ]

    for v in views:
        t0 = time.time()
        cam.location = v["cam_pos"]
        cam.data.lens = v["lens"]
        point_camera_at(cam, v["target"])
        bpy.context.view_layer.update()

        out_path = os.path.join(out_dir, f"{v['name']}.png")
        scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {v['name']} in {round(time.time() - t0, 2)}s -> {out_path}")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
