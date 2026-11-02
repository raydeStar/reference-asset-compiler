"""Fit the MakeHuman (MPFB, CC0 assets) head to the Raider's acquired head: similarity alignment on eye, mouth
and nose landmarks, then a smooth low-frequency offset field so MakeHuman keeps its eyelids, lips, nostrils and
expression targets while taking the acquired head's proportions. Saves raider-head-v1.blend and renders."""
import bpy
import bmesh
import sys
import os
import json
import math
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
MPFB = os.path.dirname(sys.modules["bl_ext.user_default.mpfb"].__file__)
# acquired-head landmarks measured on the dense mesh (front view, z up, front is -y)
AI = {"eye_z": 0.865, "mouth_z": 0.785, "neck_cut": 0.69}
HAIR_INSET = 0.012

sc = bpy.context.scene
def objs(names):
    return [bpy.data.objects[n] for n in names if n in bpy.data.objects]
# target surface: acquired face and beard as they are, the hair pushed in to where the scalp would be
bm = bmesh.new()
for o in objs(["face_dense", "beard_dense", "hair_dense"]):
    t = bmesh.new()
    t.from_mesh(o.data)
    t.normal_update()
    if o.name == "hair_dense":
        for v in t.verts:
            v.co -= v.normal * HAIR_INSET
    tmp = bpy.data.meshes.new("tmp")
    t.to_mesh(tmp)
    t.free()
    bm.from_mesh(tmp)
    bpy.data.meshes.remove(tmp)
bm.normal_update()
bvh = BVHTree.FromBMesh(bm)
TV = np.array([v.co[:] for v in bm.verts])
fr = TV[(TV[:, 2] > 0.80) & (TV[:, 2] < 0.85) & (np.abs(TV[:, 0]) < 0.02)]
AI["nose_y"] = float(fr[:, 1].min())
AI["width"] = float(np.ptp(TV[(TV[:, 2] > 0.84) & (TV[:, 2] < 0.87), 0]))
print("AI landmarks", json.dumps({k: round(v, 4) for k, v in AI.items()}))

macro = {"gender": 1.0, "age": 0.5, "muscle": 0.7, "weight": 0.5, "proportions": 0.5, "height": 0.5, "cupsize": 0.5,
         "firmness": 0.5, "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}
h = HumanService.create_human(macro_detail_dict=macro)
TargetService.bake_targets(h)
for m in list(h.modifiers):
    h.modifiers.remove(m)
units = os.path.join(MPFB, "data", "targets", "expression", "units", "caucasian")
for fn in sorted(os.listdir(units)):
    TargetService.load_target(h, os.path.join(units, fn), weight=0.0, name=fn.replace(".target.gz", ""))
me = h.data
keys = me.shape_keys.key_blocks
print("MH", len(me.vertices), "expression keys", len(keys) - 1)
gi = {g.name: g.index for g in h.vertex_groups}
def members(name):
    idx = gi[name]
    return np.array([v.index for v in me.vertices if any(g.group == idx and g.weight > 0.5 for g in v.groups)], int)
body = members("body")
eyes = np.concatenate([members("helper-l-eye"), members("helper-r-eye")])
teeth = np.concatenate([members("helper-upper-teeth"), members("helper-lower-teeth")])
tongue = members("helper-tongue")
lashes = np.concatenate([members(n) for n in gi if "eyelashes" in n])
MV = np.array([v.co[:] for v in me.vertices])
mh_eye_z = MV[eyes, 2].mean()
mh_mouth_z = MV[teeth, 2].mean()
hb = body[MV[body, 2] > mh_eye_z - 0.12]
nz = hb[(MV[hb, 2] < mh_eye_z - 0.02) & (MV[hb, 2] > mh_mouth_z) & (np.abs(MV[hb, 0]) < 0.01)]
mh_nose_y = MV[nz, 1].min()
mh_width = np.ptp(MV[hb][(MV[hb, 2] > mh_eye_z - 0.01) & (MV[hb, 2] < mh_eye_z + 0.015), 0])
s_v = (AI["eye_z"] - AI["mouth_z"]) / (mh_eye_z - mh_mouth_z)
s_w = AI["width"] / mh_width
s = 0.5 * (s_v + s_w)
print("SCALE vertical", round(s_v, 4), "width", round(s_w, 4), "used", round(s, 4))
M = Matrix.Translation((0, AI["nose_y"] - s * mh_nose_y, AI["eye_z"] - s * mh_eye_z)) @ Matrix.Scale(s, 4)
me.transform(M, shape_keys=True)
me.update()

def laplace_smooth(field, tris, fixed, iters):
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    deg = np.bincount(e[:, 0], minlength=len(field)).astype(float)
    for _ in range(iters):
        acc = np.zeros_like(field)
        np.add.at(acc, e[:, 0], field[e[:, 1]])
        nf = acc / np.maximum(deg, 1)[:, None]
        field = np.where(fixed[:, None], field, nf)
    return field
tris = []
for p in me.polygons:
    vs = list(p.vertices)
    tris += [[vs[0], vs[k], vs[k + 1]] for k in range(1, len(vs) - 1)]
tris = np.array(tris)
is_body = np.zeros(len(me.vertices), bool)
is_body[body] = True
MV0 = np.array([v.co[:] for v in me.vertices])
total = np.zeros_like(MV0)
for it in range(3):
    MV = MV0 + total
    off = np.zeros_like(MV)
    trust = np.zeros(len(MV), bool)
    region = is_body & (MV[:, 2] > AI["neck_cut"] + 0.03)
    for i in np.nonzero(region)[0]:
        loc, nrm, _, d = bvh.find_nearest(Vector(MV[i]))
        if loc is not None and d < 0.05:
            off[i] = np.array(loc) - MV[i]
            trust[i] = True
    # keep the field low-frequency: averaged over the surface, pinned to zero well below the collar
    pin = is_body & (MV[:, 2] < AI["neck_cut"] - 0.02)
    field = laplace_smooth(np.where(trust[:, None], off, 0.0), tris, pin, 40 if it < 2 else 25)
    total += field * (1.0 if it < 2 else 0.8)
    print("FIT pass", it, "mean |offset| before", round(float(np.linalg.norm(off[trust], axis=1).mean()), 4))
# helpers ride with the nearest skin
kd = KDTree(len(body))
for k, i in enumerate(body):
    kd.insert(MV0[i], k)
kd.balance()
for i in np.nonzero(~is_body)[0]:
    near = kd.find_n(Vector(MV0[i]), 8)
    w = np.array([1 / (d + 1e-4) for _, _, d in near])
    total[i] = (total[body[[k for _, k, _ in near]]] * w[:, None]).sum(0) / w.sum()
for kb in keys:
    co = np.zeros(len(me.vertices) * 3)
    kb.data.foreach_get("co", co)
    kb.data.foreach_set("co", (co.reshape(-1, 3) + total).ravel())
me.vertices.foreach_set("co", (MV0 + total).ravel())
me.update()
FV = MV0 + total
res = []
for i in np.nonzero(is_body & (FV[:, 2] > 0.75))[0]:
    loc, _, _, d = bvh.find_nearest(Vector(FV[i]))
    if loc is not None:
        res.append(d)
print("RESIDUAL mean", round(float(np.mean(res)), 4), "p95", round(float(np.percentile(res, 95)), 4))
h.name = "mh_full_fitted"
me.name = "mh_full_fitted"

# the head part: skin above the cut plus eyes, teeth, tongue, lashes
head = h.copy()
head.data = me.copy()
head.name = "head"
head.data.name = "head"
sc.collection.objects.link(head)
keep = np.zeros(len(me.vertices), bool)
keep[body[FV[body, 2] > AI["neck_cut"]]] = True
for arr in (eyes, teeth, tongue):
    keep[arr] = True
hb_ = bmesh.new()
hb_.from_mesh(head.data)
hb_.verts.ensure_lookup_table()
bmesh.ops.delete(hb_, geom=[hb_.verts[i] for i in np.nonzero(~keep)[0]], context='VERTS')
hb_.to_mesh(head.data)
hb_.free()
for g in list(head.vertex_groups):
    if g.name.startswith(("helper-skirt", "helper-tights", "helper-hair", "helper-genital", "joint-")):
        head.vertex_groups.remove(g)
h.hide_render = True
# the short beard is painted on the head, so it moves with every mouth shape: mark it as a mask from the acquired
# beard, below the nose and off the lips; the acquired beard shell is retired
bbv = bpy.data.objects["beard_dense"]
bt = bmesh.new()
bt.from_mesh(bbv.data)
bbvh = BVHTree.FromBMesh(bt)
nose_base = AI["mouth_z"] + 0.45 * (AI["eye_z"] - AI["mouth_z"])
hgi0 = {g.name: g.index for g in head.vertex_groups}
beard_vg = head.vertex_groups.new(name="beard_mask")
bidx = []
for v in head.data.vertices:
    if v.co.z > nose_base or any(g.group == hgi0["lips"] and g.weight > 0.3 for g in v.groups):
        continue
    if not any(g.group == hgi0["body"] for g in v.groups):
        continue
    loc, _, _, d = bbvh.find_nearest(v.co)
    if loc is not None and d < 0.012:
        bidx.append(v.index)
beard_vg.add(bidx, 1.0, 'REPLACE')
print("BEARD_MASK verts", len(bidx))
if "beard" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["beard"])
def mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    return m
hm = head.data
hm.materials.clear()
for m_ in (mat("HEAD_skin", (0.86, 0.62, 0.50)), mat("HEAD_eye", (0.95, 0.95, 0.95)), mat("HEAD_teeth", (0.92, 0.9, 0.82)), mat("HEAD_beard_mask", (0.45, 0.28, 0.17))):
    hm.materials.append(m_)
hgi = {g.name: g.index for g in head.vertex_groups}
def vin(v, names):
    ids = [hgi[n] for n in names if n in hgi]
    return any(g.group in ids and g.weight > 0.5 for g in v.groups)
lash_names = [n for n in hgi if "eyelashes" in n]
vcls = [1 if vin(v, ["helper-l-eye", "helper-r-eye"]) else 2 if vin(v, ["helper-upper-teeth", "helper-lower-teeth", "helper-tongue"])
        else 3 if vin(v, ["beard_mask"]) else 0 for v in hm.vertices]
for p in hm.polygons:
    cl = [vcls[i] for i in p.vertices]
    p.material_index = 3 if all(c == 3 for c in cl) else max(c for c in cl if c != 3) if any(c != 3 for c in cl) else 0
    p.use_smooth = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "raider-head-v1.blend"))
json.dump({"scale": s, "scale_vertical": s_v, "scale_width": s_w, "residual_mean": float(np.mean(res)),
           "residual_p95": float(np.percentile(res, 95)), "expression_keys": [k.name for k in keys][1:],
           "head_verts": len(hm.vertices), "head_tris": sum(len(p.vertices) - 2 for p in hm.polygons)},
          open(os.path.join(out, "head-fit.json"), "w"), indent=2)
print("SAVED head", len(hm.vertices))

# renders: acquired head vs fitted MakeHuman head, then expressions
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'MATERIAL'
sh.show_cavity = True
cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
if cam.name not in sc.collection.objects:
    sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 0.36
sc.render.resolution_x = sc.render.resolution_y = 600
centre = Vector((0, -0.03, 0.84))
front = Vector((0, -1, 0))
def shoot(path, ang, size=0.36, c=centre):
    cam.data.ortho_scale = size
    d = front.copy()
    d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = c + d * 5
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
meshes = [o for o in sc.objects if o.type == 'MESH']
def only(names):
    for o in meshes:
        o.hide_render = o.name not in names
ctx = ("hair", "jacket", "strap", "plate")
only(("face", "beard") + ctx)
for nm, ang in (("front", 0), ("three-quarter", 35), ("side", 90)):
    shoot(os.path.join(out, f"head-acq-{nm}.png"), ang)
only(("head",) + ctx)
for nm, ang in (("front", 0), ("three-quarter", 35), ("side", 90)):
    shoot(os.path.join(out, f"head-mh-{nm}.png"), ang)
only(("head",) + ctx)
hk = head.data.shape_keys.key_blocks
EXPR = {"rest": {}, "open": {"mouth-open": 1.0}, "smile": {"mouth-corner-puller": 1.0, "eye-left-slit": 0.3, "eye-right-slit": 0.3},
        "oo": {"mouth-pursing": 1.0, "mouth-protusion": 0.6}, "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0},
        "brows": {"eyebrows-left-inner-up": 1.0, "eyebrows-right-inner-up": 1.0}}
for nm, ws in EXPR.items():
    for kb in hk[1:]:
        kb.value = ws.get(kb.name, 0.0)
    shoot(os.path.join(out, f"head-expr-{nm}.png"), 20, 0.26, Vector((0, -0.05, 0.83)))
for kb in hk[1:]:
    kb.value = 0.0
print("HEAD_DONE")
