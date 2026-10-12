# SPDX-License-Identifier: MIT
"""Render top-down and elevated angle views of Character02 to verify coat sleeves and shoulders."""

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
    out_dir = r"C:\work\character-02\top_views_v22"
    if "--out-dir" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out-dir") + 1]
    os.makedirs(out_dir, exist_ok=True)

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 48
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024

    cam = bpy.data.objects.get("TopReviewCam")
    if not cam:
        cam_data = bpy.data.cameras.new("TopReviewCam")
        cam = bpy.data.objects.new("TopReviewCam", cam_data)
        scene.collection.objects.link(cam)
    scene.camera = cam

    # Ensure lighting from above so top surfaces are well-lit
    top_light = bpy.data.objects.get("Top_Inspect_Light")
    if not top_light:
        t_data = bpy.data.lights.new("Top_Inspect_Light", type='AREA')
        t_data.energy = 350.0
        t_data.size = 2.5
        t_data.color = (1.0, 0.98, 0.95)
        top_light = bpy.data.objects.new("Top_Inspect_Light", t_data)
        scene.collection.objects.link(top_light)
    top_light.location = (0.0, 0.0, 3.5)

    views = [
        {
            "name": "01_Top_Down_Full_Wingspan",
            "cam_pos": Vector((0.0, -0.05, 3.6)),
            "target": Vector((0.0, 0.0, 1.42)),
            "lens": 42.0,
            "direct_down": True,
        },
        {
            "name": "02_Top_Front_Elevated_Angle",
            "cam_pos": Vector((0.0, -2.4, 2.7)),
            "target": Vector((0.0, 0.0, 1.35)),
            "lens": 48.0,
            "direct_down": False,
        },
        {
            "name": "03_Top_Left_Sleeve_Zoom",
            "cam_pos": Vector((0.55, -0.6, 2.3)),
            "target": Vector((0.55, 0.0, 1.40)),
            "lens": 55.0,
            "direct_down": False,
        },
        {
            "name": "04_Top_Right_Sleeve_Zoom",
            "cam_pos": Vector((-0.55, -0.6, 2.3)),
            "target": Vector((-0.55, 0.0, 1.40)),
            "lens": 55.0,
            "direct_down": False,
        },
    ]

    for v in views:
        t0 = time.time()
        cam.location = v["cam_pos"]
        cam.data.lens = v["lens"]
        if v.get("direct_down"):
            # Looking straight down along -Z, character head towards top (+Y)
            cam.rotation_euler = (0.0, 0.0, 0.0)
        else:
            point_camera_at(cam, v["target"])
        bpy.context.view_layer.update()

        out_path = os.path.join(out_dir, f"{v['name']}.png")
        scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {v['name']} in {round(time.time() - t0, 2)}s -> {out_path}")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
