"""Calibrated orthographic renders of a rest-pose character, for 2-D keypoints.

blender -b <character.blend> --python render_ortho_views.py -- <out_dir> [resolution]

Writes front/left/back/top PNGs plus ortho.json (centre, ortho scale and
camera axes), so a pixel maps back to world metres exactly:
x = cx + (px - res/2) * scale / res, z = cz + (res/2 - py) * scale / res.
"""

import bpy
import json
import sys
import math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :]
out = argv[0]
res = int(argv[1]) if len(argv) > 1 else 2048
scene = bpy.context.scene
for ob in scene.objects:
    if ob.type == "ARMATURE":
        ob.data.pose_position = "REST"
meshes = [o for o in scene.objects if o.type in ("MESH", "CURVES") and o.visible_get()]
deps = bpy.context.evaluated_depsgraph_get()
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in meshes:
    if o.type != "MESH":
        continue
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        lo = Vector(map(min, lo, w))
        hi = Vector(map(max, hi, w))
center = (lo + hi) / 2
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = res
scene.render.resolution_y = res
scene.render.film_transparent = False
scene.world = scene.world or bpy.data.worlds.new("W")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.45, 0.45, 0.45, 1)
    bg.inputs[1].default_value = 1.0
cam_data = bpy.data.cameras.new("OrthoCam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("OrthoCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
span = max(hi.x - lo.x, hi.z - lo.z, hi.y - lo.y) * 1.08
cam_data.ortho_scale = span
cam_data.clip_end = 100
views = {
    "front": (Vector((center.x, lo.y - 5, center.z)), (math.radians(90), 0, 0)),
    "left": (Vector((hi.x + 5, center.y, center.z)), (math.radians(90), 0, math.radians(90))),
    "back": (Vector((center.x, hi.y + 5, center.z)), (math.radians(90), 0, math.radians(180))),
    "top": (Vector((center.x, center.y, hi.z + 5)), (0, 0, 0)),
}
meta = {"center": list(center), "ortho_scale": span, "res": res, "views": {}}
for name, (loc, rot) in views.items():
    cam.location = loc
    cam.rotation_euler = rot
    bpy.context.view_layer.update()
    scene.render.filepath = f"{out}/{name}.png"
    bpy.ops.render.render(write_still=True)
    m = cam.matrix_world
    meta["views"][name] = {
        "cam_loc": list(cam.location),
        "right": list(m.col[0].xyz),
        "up": list(m.col[1].xyz),
    }
json.dump(meta, open(f"{out}/ortho.json", "w"), indent=1)
print("ORTHO DONE", meta)
