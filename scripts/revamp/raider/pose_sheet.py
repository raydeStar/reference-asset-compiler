"""Full-body deformation sheet for the rigged Raider: everyday and extreme poses, painted (EEVEE) and clay
(matcap), front and three-quarter, so stretching and bad bends cannot hide behind paint or a single angle.

  $B -b <rigged.blend> --python pose_sheet.py -- <out_dir>
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
mesh = next(o for o in sc.objects if o.type == 'MESH' and o.parent == arm)
def reset():
    for b in pb:
        b.rotation_mode = 'XYZ'
        b.rotation_euler = (0, 0, 0)
        b.location = (0, 0, 0)
def rot(name, x=0, y=0, z=0):
    if name in pb:
        pb[name].rotation_mode = 'XYZ'
        pb[name].rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
POSES = {
    "rest": {},
    "arms-forward": {"upperarm_l": (0, 0, -70), "upperarm_r": (0, 0, 70)},
    "arms-overhead": {"upperarm_l": (0, 0, -130), "upperarm_r": (0, 0, 130), "clavicle_l": (0, 0, -15), "clavicle_r": (0, 0, 15)},
    # a reach as people make it: the collarbones lift about 30 degrees with the arms (the test pose above keeps
    # its 15 so earlier sheets stay comparable; at 15 the head reads sunk between the shoulders)
    "arms-overhead-natural": {"upperarm_l": (0, 0, -112), "upperarm_r": (0, 0, 112), "clavicle_l": (0, 0, -30), "clavicle_r": (0, 0, 30)},
    "elbows-bent": {"lowerarm_l": (0, 0, -110), "lowerarm_r": (0, 0, 110), "upperarm_l": (0, 0, -30), "upperarm_r": (0, 0, 30)},
    "squat": {"thigh_l": (-95, 0, 0), "thigh_r": (-95, 0, 0), "calf_l": (110, 0, 0), "calf_r": (110, 0, 0), "foot_l": (-15, 0, 0), "foot_r": (-15, 0, 0), "spine_01": (20, 0, 0)},
    "lunge": {"thigh_l": (-80, 0, 0), "calf_l": (80, 0, 0), "thigh_r": (30, 0, 0), "calf_r": (40, 0, 0)},
    "twist-look": {"spine_02": (0, 15, 0), "spine_04": (0, 15, 0), "neck_01": (0, 20, 0), "head": (10, 20, 0)},
    "fists": {**{f"{d}_{k}_{s}": (0, 0, -80 if s == "l" else 80) for d in ("index", "middle", "ring", "pinky") for k in ("01", "02", "03") for s in ("l", "r")},
              **{f"thumb_{k}_{s}": (0, 0, -35 if s == "l" else 35) for k in ("02", "03") for s in ("l", "r")}},
}
sc.render.resolution_x, sc.render.resolution_y = 520, 700
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
mats = list(mesh.data.materials)
for name, pose in POSES.items():
    reset()
    for b, r in pose.items():
        rot(b, *r)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    zs = [(mesh.matrix_world @ v.co).z for v in ev.data.vertices]
    zmin, zmax = min(zs), max(zs)
    c = Vector((0, 0, (zmin + zmax) / 2))
    cam.data.ortho_scale = max(1.0, (zmax - zmin) * 1.12, 1.6)
    for mode in ("paint", "clay"):
        if mode == "paint":
            sc.render.engine = 'BLENDER_EEVEE'
        else:
            sc.render.engine = 'BLENDER_WORKBENCH'
            sh = sc.display.shading
            sh.light = 'MATCAP'
            sh.color_type = 'SINGLE'
            sh.single_color = (0.8, 0.8, 0.8)
            sh.show_cavity = True
        for view, d in (("front", Vector((0, -1, 0))), ("34", Vector((0.7, -0.7, 0)).normalized())):
            cam.location = c + d * 6
            cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = f"{out}/{name}-{mode}-{view}.png"
            bpy.ops.render.render(write_still=True)
reset()
print("SHEET_POSES", list(POSES))
