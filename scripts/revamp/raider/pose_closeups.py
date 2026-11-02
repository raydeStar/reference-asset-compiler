"""Painted close-ups of the rigged Raider in test poses: shoulders with arms forward, bent elbows, bent knees,
a closed fist and a finger spread, so deformation is judged where it fails first, not from across the room.

  $B -b <rigged.blend> --python pose_closeups.py -- <out_dir>
"""
import bpy
import sys
import math
import os
from mathutils import Vector
out = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
pb = arm.pose.bones
def reset():
    for b in pb:
        b.rotation_mode = 'XYZ'
        b.rotation_euler = (0, 0, 0)
        b.location = (0, 0, 0)
def rot(name, x=0, y=0, z=0):
    if name in pb:
        pb[name].rotation_mode = 'XYZ'
        pb[name].rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
def world(name):
    bpy.context.view_layer.update()
    return arm.matrix_world @ pb[name].head
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = sc.render.resolution_y = 700
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.3, 0.32, 1)
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", 'SUN'))
sun.data.energy = 3
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
sc.view_settings.view_transform = 'Standard'
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
def shoot(name, target, size, d):
    d = Vector(d).normalized()
    cam.data.ortho_scale = size
    cam.location = target + d * 4
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f"{out}/{name}.png"
    bpy.ops.render.render(write_still=True)
FR, SIDE_L, Q = (0, -1, 0), (1, -0.15, 0), (0.7, -0.7, 0.1)
reset()
shoot("rest-torso", world("spine_03"), 0.9, FR)
# arms raised forward
reset()
rot("upperarm_l", 0, 0, -70)
rot("upperarm_r", 0, 0, 70)
shoot("arms-up-front", world("spine_04"), 0.9, FR)
shoot("arms-up-side", world("spine_04"), 0.9, SIDE_L)
# elbows bent
reset()
rot("lowerarm_l", 0, 0, -100)
rot("lowerarm_r", 0, 0, 100)
shoot("elbow-bent", world("lowerarm_l"), 0.45, Q)
# knee bent and hip raised
reset()
rot("thigh_l", -70, 0, 0)
rot("calf_l", 100, 0, 0)
shoot("knee-bent-side", world("calf_l"), 0.9, SIDE_L)
shoot("knee-bent-front", world("calf_l"), 0.9, FR)
# fist and spread on the left hand
reset()
for dg in ("index", "middle", "ring", "pinky"):
    for k in ("01", "02", "03"):
        rot(f"{dg}_{k}_l", 0, 0, -75)
for k in ("02", "03"):
    rot(f"thumb_{k}_l", 0, 0, -40)
shoot("fist-back", world("hand_l"), 0.28, (0.6, 0.5, 0.6))
shoot("fist-front", world("hand_l"), 0.28, (0.6, -0.8, 0.0))
reset()
for dg, a in (("index", 12), ("middle", 3), ("ring", -6), ("pinky", -15)):
    rot(f"{dg}_01_l", a, 0, 0)
shoot("spread", world("hand_l"), 0.28, (0.6, -0.8, 0.0))
reset()
print("POSES_DONE")
