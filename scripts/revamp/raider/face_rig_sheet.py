"""Renders for the face-rig gate on the assembled, rigged Raider: four full views at rest, head close-ups of the
speech and expression shapes on the body, and head turns and nods that exercise the neck blend.

  $B -b <rigged-with-face.blend> --python face_rig_sheet.py -- <out_dir>
"""
import bpy
import sys
import math
import os
from mathutils import Vector, Euler
out = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
pb = arm.pose.bones
face = bpy.data.objects["face"]
kb = face.data.shape_keys.key_blocks
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.32, 0.34, 1)
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", 'SUN'))
sun.data.energy = 2.6
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
def shoot(path, ang, size, centre, res=(600, 600)):
    sc.render.resolution_x, sc.render.resolution_y = res
    cam.data.ortho_scale = size
    d = Vector((0, -1, 0))
    d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = centre + d * 6
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
def reset():
    for b in pb:
        b.rotation_mode = 'XYZ'
        b.rotation_euler = (0, 0, 0)
    for k in kb[1:]:
        k.value = 0.0
reset()
for nm, ang in (("front", 0), ("three-quarter", 45), ("side", 90), ("back", 180)):
    shoot(f"{out}/body-{nm}.png", ang, 2.0, Vector((0, 0, 0.91)), (560, 800))
head_c = arm.matrix_world @ arm.data.bones["head"].head_local + Vector((0, 0, 0.07))
EXPR = {"rest": {}, "ah": {"mouth-open": 0.8}, "ee": {"mouth-retraction": 1.0, "mouth-open": 0.25},
        "oo": {"mouth-pursing": 1.0, "mouth-protusion": 0.6}, "ff": {"mouth-depression-retraction": 0.6, "mouth-elevation": 0.5},
        "mbp": {"mouth-compression": 1.0}, "smile": {"mouth-corner-puller": 1.0, "eye-left-slit": 0.3, "eye-right-slit": 0.3},
        "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0}, "brows": {"eyebrows-left-inner-up": 1.0, "eyebrows-right-inner-up": 1.0},
        "frown": {"eyebrows-left-down": 1.0, "eyebrows-right-down": 1.0, "mouth-depression": 0.6}}
for nm, ws in EXPR.items():
    reset()
    for k in kb[1:]:
        k.value = ws.get(k.name, 0.0)
    shoot(f"{out}/expr-{nm}.png", 25, 0.32, head_c)
for nm, rots in (("turn-left", {"neck_01": (0, 0, 20), "neck_02": (0, 0, 15), "head": (0, 0, 15)}),
                 ("turn-right", {"neck_01": (0, 0, -20), "neck_02": (0, 0, -15), "head": (0, 0, -15)}),
                 ("nod-down", {"neck_01": (15, 0, 0), "head": (20, 0, 0)}), ("look-up", {"neck_01": (-10, 0, 0), "head": (-20, 0, 0)})):
    reset()
    for b, r in rots.items():
        pb[b].rotation_mode = 'XYZ'
        pb[b].rotation_euler = tuple(math.radians(x) for x in r)
    bpy.context.view_layer.update()
    shoot(f"{out}/neck-{nm}.png", 25, 0.5, head_c - Vector((0, 0, 0.06)))
reset()
print("FACE_RIG_SHEET_OK")
