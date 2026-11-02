"""Painted renders of the acquired head and the wrapped, baked MakeHuman face under one light, front, three-quarter
and side, then the face's expression shapes (rest, mouth open, smile, "oo", blink, brows up, "ee" and "ff").

  $B -b <face-baked.blend> --python face_renders.py -- <out_prefix>
"""
import bpy
import sys
import math
import numpy as np
from mathutils import Vector, Euler
out = sys.argv[sys.argv.index("--") + 1:][0]
sc = bpy.context.scene
face = bpy.data.objects["face"]
scan = next(o for o in sc.objects if o.name.startswith("raider_head"))
for m in scan.data.materials:
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    outn = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    if bsdf:
        nt.links.new(bsdf.outputs[0], outn.inputs[0])
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.35, 0.37, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", 'SUN'))
sun.data.energy = 2.5
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
V = np.array([(scan.matrix_world @ v.co)[:] for v in scan.data.vertices])
top = V[:, 2].max()
zr = np.ptp(V[:, 2])
c = Vector(((V[:, 0].min() + V[:, 0].max()) / 2, 0, top - 0.36 * zr))
sc.render.resolution_x = sc.render.resolution_y = 600
def shoot(path, ang, size, centre):
    cam.data.ortho_scale = size
    d = Vector((0, -1, 0))
    d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = centre + d * 5
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
hair = bpy.data.objects.get("hair")
eye_l = bpy.data.objects.get("eye_l")
eye_r = bpy.data.objects.get("eye_r")
for who, objs in (("scan", (scan,)), ("face", (face, hair, eye_l, eye_r))):
    for o in sc.objects:
        if o.type == 'MESH':
            o.hide_render = o not in objs
    for nm, ang in (("front", 0), ("34", 35), ("side", 90)):
        shoot(f"{out}-{who}-{nm}.png", ang, 0.36, c)
for o in sc.objects:
    if o.type == 'MESH':
        o.hide_render = o not in (face, hair, eye_l, eye_r)
kb = face.data.shape_keys.key_blocks
EXPR = {"rest": {}, "open": {"mouth-open": 1.0}, "smile": {"mouth-corner-puller": 1.0, "eye-left-slit": 0.3, "eye-right-slit": 0.3},
        "oo": {"mouth-pursing": 1.0, "mouth-protusion": 0.6}, "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0},
        "brows": {"eyebrows-left-inner-up": 1.0, "eyebrows-right-inner-up": 1.0},
        "ee": {"mouth-retraction": 1.0, "mouth-open": 0.25}, "ff": {"mouth-depression-retraction": 0.6, "mouth-elevation": 0.5}}
fc = Vector((c.x, c.y, c.z - 0.02))
for nm, ws in EXPR.items():
    for k in kb[1:]:
        k.value = ws.get(k.name, 0.0)
    shoot(f"{out}-expr-{nm}.png", 20, 0.25, fc)
for k in kb[1:]:
    k.value = 0.0
print("FACE_RENDERS_OK")
