"""Skin a layered humanoid from a MakeHuman body's hand-made weights (MPFB 2, CC0 assets).

Studios skin clothing by copying weights from a properly weighted body underneath it. Rule-based weights
on CH-03 Raider (heat failed; envelope, nearest-bone, surface spread and limb-region weights were tried)
kept the gear on but bent the limbs as stiff segments with hard creases and stretching; Mark rejected
them (2026-11-01). Here:

1. A MakeHuman body is made with MPFB's `game_engine` rig and its artist weights (UE4 mannequin names).
2. Its skeleton is posed onto the target's Manny skeleton: the trunk stays as it is; every limb and finger
   bone (and the head) is moved onto the target joint, turned to the target bone's direction and stretched
   to its length, parents first. The
   posed body is baked to a proxy mesh that keeps the weights.
3. Every target vertex takes the weights of the nearest point on that body (polygon-interpolated), so a
   sleeve follows the arm under it and a belt pouch follows the hip under it.
4. Each MakeHuman bone's weight is shared among the Manny bones of the same region (spine_03 over
   spine_03..05, upperarm over upperarm and its twists, hand over hand and metacarpals ...) by the
   nearest of those bones, which keeps MakeHuman's smooth blends between regions.
4b. Inside the hands, the hand-and-finger share is redistributed over the target's measured finger bones
   (MakeHuman's closed fingers do not match spread ones).
5. Small rigid pieces ride one bone; four influences, normalised; FBX exported as rig_from_landmarks.py does.

  blender -b <rigged.blend> --python skin_from_makehuman.py -- <out.fbx> <out.blend> <report.json>
      [--rigid-size 0.42] [--rigid-share 0.6] [--debug-proxy <proxy.blend>]
Needs MPFB 2 enabled in the user's Blender (not --factory-startup).
"""
import bpy, sys, os, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:]
pos = [x for x in argv if not x.startswith("--") and (argv.index(x) == 0 or not argv[argv.index(x) - 1].startswith("--"))]
out_fbx, out_blend, out_rep = pos[:3]
def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default
RIGID_SIZE, RIGID_SHARE = opt("--rigid-size", 0.42), opt("--rigid-share", 0.6)
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

sc = bpy.context.scene
tarm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = max((o for o in sc.objects if o.type == 'MESH' and o.parent == tarm), key=lambda o: len(o.data.vertices))
TB = tarm.data.bones
def tw(name, end="head"):
    b = TB[name]; return tarm.matrix_world @ (b.head_local if end == "head" else b.tail_local)
H = max((body.matrix_world @ v.co).z for v in body.data.vertices) - min((body.matrix_world @ v.co).z for v in body.data.vertices)

# 1. MakeHuman body with the game_engine rig and weights
macro = {"gender": 1.0, "age": 0.5, "muscle": 0.7, "weight": 0.55, "proportions": 0.5, "height": 0.6, "cupsize": 0.5,
         "firmness": 0.5, "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}
mh = HumanService.create_human(macro_detail_dict=macro)
TargetService.bake_targets(mh)
for m in list(mh.modifiers):
    if m.type == 'MASK': mh.modifiers.remove(m)
marm = HumanService.add_builtin_rig(mh, "game_engine", import_weights=True)
# real-world scale matching the target's height, feet on the floor
mzs = [(mh.matrix_world @ v.co).z for v in mh.data.vertices if any(g.group == mh.vertex_groups["body"].index for g in v.groups)]
k = H / (max(mzs) - min(mzs))
# scale the rig object only: MPFB parents the body to it, so the body follows (no transform apply, which
# would scale the parented body a second time)
marm.scale = (k, k, k)
bpy.context.view_layer.update()
print("MH scaled", round(k, 4), "bones", len(marm.data.bones))

# 2. pose the MakeHuman skeleton onto the target joints (direction and length), parents first
MB = marm.pose.bones
for b in marm.data.bones: b.inherit_scale = 'NONE'
pelvis_off = tw("pelvis") - marm.matrix_world @ marm.data.bones["pelvis"].head_local
def joint_err(tag):
    bpy.context.view_layer.update()
    e = {n: round(float((marm.matrix_world @ MB[n].head - tw(n)).length), 3) for n in ("pelvis", "spine_01", "neck_01", "head", "upperarm_l", "lowerarm_l", "hand_l", "thigh_l", "calf_l", "foot_l")}
    print(tag, e)
marm.location = marm.location + pelvis_off
bpy.context.view_layer.update()
joint_err("PRE")
def depth(b):
    d = 0
    while b.parent: b = b.parent; d += 1
    return d
shared = sorted([b for b in marm.data.bones if b.name in TB and b.name != "Root"], key=depth)
# The trunk is left as it is: MakeHuman's pelvis and spine bones point differently by convention, and turning
# them swung the hips and shoulders 15-44 cm off. Limb and finger bones (and the head) are first moved so their
# start sits on the target joint, then turned onto the target bone and stretched to its length, parents first.
TRUNK = {"pelvis", "spine_01", "spine_02", "spine_03", "neck_01"}
posed = []
for b in shared:
    if b.name in TRUNK: continue
    pb = MB[b.name]
    bpy.context.view_layer.update()
    h = marm.matrix_world @ pb.head
    th = tw(b.name)
    Mw = marm.matrix_world @ pb.matrix
    Mw = Matrix.Translation(th - h) @ Mw
    pb.matrix = marm.matrix_world.inverted() @ Mw
    bpy.context.view_layer.update()
    h = marm.matrix_world @ pb.head; t = marm.matrix_world @ pb.tail; cur = t - h
    want = tw(b.name, "tail") - th
    if cur.length < 1e-6 or want.length < 1e-6: continue
    rot = cur.normalized().rotation_difference(want.normalized()).to_matrix().to_4x4()
    Mw = marm.matrix_world @ pb.matrix
    pb.matrix = marm.matrix_world.inverted() @ (Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ Mw)
    bpy.context.view_layer.update()
    pb.scale = (pb.scale[0], pb.scale[1] * (want.length / cur.length), pb.scale[2])
    posed.append(b.name)
joint_err("POST")
bpy.context.view_layer.update()
err = {n: round(float((marm.matrix_world @ MB[n].head - tw(n)).length), 4) for n in posed}
print("POSE joint error mean", round(float(np.mean(list(err.values()))), 4), "max", max(err.items(), key=lambda kv: kv[1]))

# bake the posed body (body vertices only) into a proxy that keeps the weights
dg = bpy.context.evaluated_depsgraph_get(); ev = mh.evaluated_get(dg)
pm = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
proxy = bpy.data.objects.new("TMP_mh_proxy", pm); sc.collection.objects.link(proxy); proxy.matrix_world = mh.matrix_world.copy()
for vg in mh.vertex_groups: proxy.vertex_groups.new(name=vg.name)
for v in mh.data.vertices:
    for g in v.groups: proxy.vertex_groups[g.group].add([v.index], g.weight, 'REPLACE')
import bmesh
bm = bmesh.new(); bm.from_mesh(pm); bm.verts.ensure_lookup_table(); dl = bm.verts.layers.deform.active
body_gi = proxy.vertex_groups["body"].index
bmesh.ops.delete(bm, geom=[v for v in bm.verts if body_gi not in v[dl] or v[dl][body_gi] < 0.5], context='VERTS')
bm.to_mesh(pm); bm.free()
mh_bones = [b.name for b in marm.data.bones if b.use_deform]
for vg in list(proxy.vertex_groups):
    if vg.name not in mh_bones: proxy.vertex_groups.remove(vg)
print("PROXY verts", len(pm.vertices))
if "--debug-proxy" in argv:
    bpy.ops.wm.save_as_mainfile(filepath=opt("--debug-proxy", ""), copy=True)

# 3. copy MakeHuman weights onto the target by nearest body surface
for vg in list(body.vertex_groups): body.vertex_groups.remove(vg)
for n in mh_bones: body.vertex_groups.new(name="MH_" + n)
for vg in proxy.vertex_groups: vg.name = "MH_" + vg.name
dt = body.modifiers.new("mh_weights", 'DATA_TRANSFER'); dt.object = proxy; dt.use_vert_data = True
dt.data_types_verts = {'VGROUP_WEIGHTS'}; dt.vert_mapping = 'POLYINTERP_NEAREST'
dt.layers_vgroup_select_src = 'ALL'; dt.layers_vgroup_select_dst = 'NAME'
for o in sc.objects: o.select_set(False)
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.modifier_move_to_index(modifier=dt.name, index=0); bpy.ops.object.modifier_apply(modifier=dt.name)

# 4. MakeHuman bone weights shared among the Manny bones of the same region by nearest of them
me = body.data; nV = len(me.vertices)
co = np.array([(body.matrix_world @ v.co)[:] for v in me.vertices])
deform = [b.name for b in TB if b.use_deform]
def family(n):
    if n == "spine_03": return ["spine_03", "spine_04", "spine_05"]
    if n == "neck_01": return ["neck_01", "neck_02"]
    for limb in ("upperarm", "lowerarm", "thigh", "calf"):
        for s in ("_l", "_r"):
            if n == limb + s: return [x for x in deform if x == n or x.startswith(limb + "_twist") and x.endswith(s)]
    for s in ("_l", "_r"):
        if n == "hand" + s: return ["hand" + s] + [x for x in deform if "metacarpal" in x and x.endswith(s)]
    return [n] if n in deform else []
def seg_dist(pts, h, t):
    h = np.array(h[:]); t = np.array(t[:]); ab = t - h; L2 = max(float(ab @ ab), 1e-12)
    t_ = np.clip(((pts - h) @ ab) / L2, 0, 1); return np.linalg.norm(pts - (h + t_[:, None] * ab), axis=1)
W = np.zeros((nV, len(deform)), np.float32); di = {n: i for i, n in enumerate(deform)}
src = {vg.index: vg.name[3:] for vg in body.vertex_groups}
MW = np.zeros((nV, len(src)), np.float32)
for v in me.vertices:
    for g in v.groups: MW[v.index, g.group] = g.weight
unmapped = []
for gidx, n in src.items():
    col = MW[:, gidx]
    if not col.any(): continue
    fam = family(n)
    if not fam: unmapped.append(n); continue
    if len(fam) == 1: W[:, di[fam[0]]] += col; continue
    Dm = np.stack([seg_dist(co, tw(f), tw(f, "tail")) for f in fam], 1) + 1e-3
    share = (1 / Dm ** 4); share /= share.sum(1, keepdims=True)
    for i, f in enumerate(fam): W[:, di[f]] += col * share[:, i]
print("MAP unmapped MakeHuman bones", unmapped)
for vg in list(body.vertex_groups): body.vertex_groups.remove(vg)
for n in deform: body.vertex_groups.new(name=n)
G = {vg.index: vg.name for vg in body.vertex_groups}

# 4b. Inside the hands, MakeHuman's straight, closed fingers do not match a hand with spread fingers: a vertex
# on one finger picked up weight from the neighbouring MakeHuman finger and a fist tore into spikes. There the
# hand-and-finger share of each vertex is redistributed over the target's own (measured) hand bones by
# distance, then smoothed along the welded surface.
_, canon_h = np.unique(np.round(co, 5), axis=0, return_inverse=True); canon_h = canon_h.ravel()
Eh = canon_h[np.array([e.vertices[:] for e in me.edges], np.int64)]; Eh = Eh[Eh[:, 0] != Eh[:, 1]]
for side in ("_l", "_r"):
    hb = [n for n in deform if n.endswith(side) and (n.startswith(("hand", "thumb", "index", "middle", "ring", "pinky")))]
    hj = [di[n] for n in hb]
    T = W[:, hj].sum(1); sel = T > 0.05
    if not sel.any(): continue
    Dm = np.stack([seg_dist(co[sel], tw(n), tw(n, "tail")) for n in hb], 1) + 2e-3
    near_ = np.argsort(Dm, 1)[:, :3]; r_ = np.arange(sel.sum())[:, None]
    dn = Dm[r_, near_] / Dm[r_, near_[:, :1]]
    Sh = np.zeros_like(Dm); Sh[r_, near_] = 1.0 / dn ** 6; Sh /= Sh.sum(1, keepdims=True)
    full = np.zeros((nV, len(hb)), np.float32); full[sel] = Sh
    for _ in range(2):
        acc = np.zeros((canon_h.max() + 1, len(hb)), np.float32); np.add.at(acc, canon_h, full)
        cnt = np.bincount(canon_h, minlength=canon_h.max() + 1)[:, None]; Wv = acc / np.maximum(cnt, 1)
        nb = np.zeros_like(Wv); deg = np.zeros(len(Wv), np.float32)
        np.add.at(nb, Eh[:, 0], Wv[Eh[:, 1]]); np.add.at(nb, Eh[:, 1], Wv[Eh[:, 0]])
        np.add.at(deg, Eh[:, 0], 1); np.add.at(deg, Eh[:, 1], 1)
        Wv = 0.5 * Wv + 0.5 * nb / np.maximum(deg, 1)[:, None]; full = Wv[canon_h]
    full[sel] /= np.maximum(full[sel].sum(1, keepdims=True), 1e-9)
    W[np.ix_(sel, hj)] = full[sel] * T[sel, None]
print("HANDS redistributed over measured finger bones")

# 5. rigid small pieces, then cap and normalise
_, canon = np.unique(np.round(co, 5), axis=0, return_inverse=True); canon = canon.ravel()
E = canon[np.array([e.vertices[:] for e in me.edges], np.int64)]
parent = np.arange(canon.max() + 1)
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
for u, w in E:
    ru, rw = find(u), find(w)
    if ru != rw: parent[ru] = rw
comp = np.array([find(c) for c in canon]); rigid = []
for r in np.unique(comp):
    idx = np.nonzero(comp == r)[0]; size = float(np.linalg.norm(co[idx].max(0) - co[idx].min(0)))
    if size > RIGID_SIZE or len(idx) < 8: continue
    tot = W[idx].sum(0); top = int(tot.argmax()); share = float(tot[top] / max(tot.sum(), 1e-9))
    if share < RIGID_SHARE: continue
    W[idx] = 0; W[idx, top] = 1.0; rigid.append({"verts": int(len(idx)), "size_m": round(size, 3), "bone": deform[top], "share": round(share, 3)})
rows = np.arange(nV)[:, None]; keep = np.argsort(-W, axis=1)[:, :4]
Wc = np.zeros_like(W); Wc[rows, keep] = W[rows, keep]; s = Wc.sum(1, keepdims=True)
unweighted = int((s[:, 0] <= 0).sum()); Wc = np.where(s > 0, Wc / np.maximum(s, 1e-9), 0)
for vg in body.vertex_groups:
    col = Wc[:, vg.index]; nz = np.nonzero(col > 1e-4)[0]
    for w in np.unique(np.round(col[nz], 4)):
        vg.add([int(i) for i in nz[np.round(col[nz], 4) == w]], float(w), 'REPLACE')
print("WEIGHTS unweighted", unweighted, "rigid pieces", len(rigid))
for o in (proxy, mh, marm): bpy.data.objects.remove(o)
os.makedirs(os.path.dirname(out_blend), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
for o in sc.objects: o.select_set(o in (tarm, body))
bpy.context.view_layer.objects.active = tarm
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="RELATIVE", embed_textures=False)
json.dump({"method": "makehuman_body_transfer", "makehuman_rig": "game_engine", "makehuman_macro": macro, "scale": k,
           "pose_joint_error_m": err, "unmapped_makehuman_bones": unmapped, "rigid_pieces": rigid,
           "unweighted_verts": unweighted}, open(out_rep, "w"), indent=2)
print("MH_SKIN_OK")
