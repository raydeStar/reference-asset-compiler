"""Preview: project the reference picture front-on onto the head and shoulders (same mapping that placed the part
labels, silhouette IoU 0.86) and render the acquired head and the MakeHuman head side by side in EEVEE."""
import bpy
import sys
import os
import math
import numpy as np
from mathutils import Vector, Euler
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
out, ref_path, ids_path, tag = a[0], a[1], a[2], a[3]
sc = bpy.context.scene
ids = np.load(ids_path)
IH, IW = ids.shape
fg = ids != 255
ys, xs = np.nonzero(fg)
iy0, iy1, ix0, ix1 = ys.min(), ys.max(), xs.min(), xs.max()
dense = [o for o in bpy.data.objects if o.name.endswith("_dense")]
V = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in dense])
s = (iy1 - iy0) / np.ptp(V[:, 2])
ox = ix0 + (ix1 - ix0) / 2 - s * (V[:, 0].min() + V[:, 0].max()) / 2
oy = iy0 + s * V[:, 2].max()
print("PROJ", round(float(s), 2), round(float(ox), 2), round(float(oy), 2))
img = bpy.data.images.load(ref_path)
m = bpy.data.materials.new("REF_PROJ")
m.use_nodes = True
nt = m.node_tree
N = nt.nodes
Lk = nt.links
geo = N.new("ShaderNodeNewGeometry")
sep = N.new("ShaderNodeSeparateXYZ")
Lk.new(geo.outputs["Position"], sep.inputs[0])
def lin(src, mul, add):
    a_ = N.new("ShaderNodeMath")
    a_.operation = 'MULTIPLY_ADD'
    Lk.new(src, a_.inputs[0])
    a_.inputs[1].default_value = mul
    a_.inputs[2].default_value = add
    return a_.outputs[0]
u = lin(sep.outputs["X"], s / IW, ox / IW)
v = lin(sep.outputs["Z"], s / IH, 1 - oy / IH)
comb = N.new("ShaderNodeCombineXYZ")
Lk.new(u, comb.inputs[0])
Lk.new(v, comb.inputs[1])
tex = N.new("ShaderNodeTexImage")
tex.image = img
tex.extension = 'EXTEND'
Lk.new(comb.outputs[0], tex.inputs["Vector"])
bsdf = N["Principled BSDF"]
Lk.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.65
show = {"acq": ("face", "beard", "hair", "jacket", "strap", "plate"), "mh": ("head", "eye_l", "eye_r", "hair", "jacket", "strap", "plate")}
for o in sc.objects:
    if o.type == 'MESH' and o.name in set(show["acq"]) | set(show["mh"]):
        o.data.materials.clear()
        o.data.materials.append(m)
        for p in o.data.polygons:
            p.material_index = 0
sc.render.engine = 'BLENDER_EEVEE'
w = sc.world or bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.32, 0.32, 0.34, 1)
bg.inputs["Strength"].default_value = 1.0
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", 'SUN'))
sun.data.energy = 2.5
sc.collection.objects.link(sun)
sun.rotation_euler = Euler((math.radians(55), 0, math.radians(-25)))
sc.view_settings.view_transform = 'Standard'
cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
if cam.name not in sc.collection.objects:
    sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 0.3
sc.render.resolution_x = sc.render.resolution_y = 500
c = Vector((0, -0.05, 0.85))
for which, names in show.items():
    if which == "acq" and "face" not in bpy.data.objects:
        continue
    for o in sc.objects:
        if o.type == 'MESH':
            o.hide_render = o.name not in names
    for nm, ang in (("front", 0), ("three-quarter", 30), ("side", 80)):
        d = Vector((0, -1, 0))
        d.rotate(Euler((0, 0, math.radians(ang))))
        cam.location = c + d * 5
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out, f"{tag}-{which}-{nm}.png")
        bpy.ops.render.render(write_still=True)
print("PREVIEW_DONE")
