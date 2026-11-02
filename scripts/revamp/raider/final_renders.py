"""Final beauty renders of the rigged Raider for judging: four full views (perspective, softer studio light) and face
close-ups from the front, three-quarter and side.

  $B -b <rigged.blend> --python final_renders.py -- <out_dir>
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
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
bg = w.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.42, 0.43, 0.46, 1)
bg.inputs["Strength"].default_value = 0.9
def light(name, energy, rot):
    lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN'))
    lamp.data.energy = energy
    lamp.data.angle = math.radians(8)
    sc.collection.objects.link(lamp)
    lamp.rotation_euler = tuple(math.radians(a) for a in rot)
light("key", 2.6, (55, 0, -35))
light("fill", 0.7, (65, 0, 60))
light("rim", 1.6, (110, 0, 170))
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 85
def shoot(path, ang, target, dist, res):
    sc.render.resolution_x, sc.render.resolution_y = res
    d = Vector((0, -1, 0))
    d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = target + d * dist + Vector((0, 0, 0.05))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
body_c = Vector((0, 0, 0.92))
for nm, ang in (("front", 0), ("three-quarter", 40), ("side", 90), ("back", 180)):
    shoot(f"{out}/full-{nm}.png", ang, body_c, 7.2, (900, 1400))
head = arm.matrix_world @ arm.data.bones["head"].head_local + Vector((0, 0, 0.07))
for nm, ang in (("front", 0), ("three-quarter", 35), ("side", 80)):
    shoot(f"{out}/face-{nm}.png", ang, head, 1.5, (900, 900))
print("FINAL_RENDERS_OK")
