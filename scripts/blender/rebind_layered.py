"""Re-skin a layered character from nearest-bone weights, then make small rigid gear ride one bone.

rig_from_landmarks.py binds with heat weights on the mesh, or on a welded copy when heat fails. On a modular
character the welded copy joins gear to cloth: CH-03 Raider's belt pouches flew out like wings when his arms
rose (2026-11-01). Here instead:

1. Heat weighting fails on this mesh (as it did on a welded and a voxel-remeshed copy). Each vertex follows
   its nearest bones, but an arm or leg bone may only weigh the surface labelled as its own limb (labels
   spread along the welded surface from forearm, shin and chest seeds).
2. The weights are smoothed a little along the surface, welded across UV seams.
3. Each small loose piece (a pouch, buckle, plate, knee pad, hair shell) whose weight mostly belongs to one
   bone is set wholly to that bone, so it stays rigid instead of smearing between bones. Pieces larger than
   the size limit, or spread over many bones (hands, the head, straps), keep their copied weights.
4. Influences are capped at four and normalised; the FBX is re-exported like rig_from_landmarks.py's.

  blender -b <rigged.blend> --python rebind_layered.py -- <out.fbx> <out.blend> <report.json>
      [--falloff 8] [--smooth 2] [--rigid-size 0.42] [--rigid-share 0.6]
"""
import bpy, bmesh, sys, json
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
pos = [x for x in argv if not x.startswith("--")]
out_fbx, out_blend, out_rep = pos[:3]
def opt(name, default):
    return float(argv[argv.index(name) + 1]) if name in argv else default
RIGID_SIZE, RIGID_SHARE = opt("--rigid-size", 0.42), opt("--rigid-share", 0.6)

sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = max((o for o in sc.objects if o.type == 'MESH' and o.parent == arm), key=lambda o: len(o.data.vertices))
deform = [b.name for b in arm.data.bones if b.use_deform]

# 1-2. Limb-limited nearest-bone weights. Heat weighting fails on this kind of mesh ("failed to find
# solution", on the real mesh, a welded copy and a voxel-remeshed copy alike), and rig_from_landmarks.py then
# falls back to envelope weights. Tried and rejected on CH-03 Raider (2026-11-01):
#   * plain nearest-bone weights: in an A-pose the forearms hang beside the belt, so the pouches flew with them;
#   * weights spread along the surface: the long chest straps carried shoulder weight down onto the chest.
# Here each arm or leg bone may only weigh the surface labelled as its own limb; spine, neck, head and clavicles
# are free. Within that, each vertex follows its nearest bones.
me = body.data; nV = len(me.vertices)
co = np.array([(body.matrix_world @ v.co)[:] for v in me.vertices])
B = arm.data.bones
def seg_dist(pts, h, t):
    ab = t - h; L2 = max(float(ab @ ab), 1e-12); t_ = np.clip(((pts - h) @ ab) / L2, 0, 1)
    return np.linalg.norm(pts - (h + t_[:, None] * ab), axis=1)
def wpos(name, end="head"):
    b = B[name]; return np.array((arm.matrix_world @ (b.head_local if end == "head" else b.tail_local))[:])
D = np.empty((nV, len(deform)), np.float32)
for j, n in enumerate(deform): D[:, j] = seg_dist(co, wpos(n), wpos(n, "tail"))
# Limb regions by surface connectivity: a baggy sleeve and the jacket side 8 cm away are not separable by a
# radius (10 cm let the jacket side follow the forearm; 7 cm left parts of the sleeve behind), but the sleeve
# only meets the torso at the armpit. Labels spread along the welded surface from sure seeds (forearm, shin,
# chest centre); a loose piece (a strap, a pouch) takes its label vertex by vertex from the nearest labelled
# surface.
import heapq
from mathutils.kdtree import KDTree
_, canon0 = np.unique(np.round(co, 5), axis=0, return_inverse=True); canon0 = canon0.ravel(); nN = canon0.max() + 1
P = np.zeros((nN, 3)); P[canon0] = co
Ee = canon0[np.array([e.vertices[:] for e in me.edges], np.int64)]; Ee = Ee[Ee[:, 0] != Ee[:, 1]]
Ee = np.unique(np.sort(Ee, 1), axis=0); lens = np.linalg.norm(P[Ee[:, 0]] - P[Ee[:, 1]], axis=1)
src = np.concatenate([Ee[:, 0], Ee[:, 1]]); order_ = np.argsort(src, kind="stable")
nbr_to = np.concatenate([Ee[:, 1], Ee[:, 0]])[order_]; nbr_len = np.concatenate([lens, lens])[order_]
ptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=nN))])
REGIONS = ["torso", "arm_l", "arm_r", "leg_l", "leg_r"]
label = np.full(nN, -1); dist = np.full(nN, np.inf); heap = []
def seed(mask, r):
    for k in np.nonzero(mask & (dist > 0))[0]: label[k] = r; dist[k] = 0.0; heap.append((0.0, int(k)))
for side in ("l", "r"):
    seed(seg_dist(P, wpos("lowerarm_" + side), wpos("hand_" + side, "tail")) < 0.06, REGIONS.index("arm_" + side))
    seed(seg_dist(P, wpos("calf_" + side), wpos("foot_" + side)) < 0.09, REGIONS.index("leg_" + side))
seed(seg_dist(P, wpos("spine_02"), wpos("spine_05", "tail")) < 0.16, 0)
heapq.heapify(heap)
while heap:
    d, k = heapq.heappop(heap)
    if d > dist[k]: continue
    for q in range(ptr[k], ptr[k + 1]):
        m_, nd = int(nbr_to[q]), d + float(nbr_len[q])
        if nd < dist[m_]: dist[m_] = nd; label[m_] = label[k]; heapq.heappush(heap, (nd, m_))
reached = label >= 0; ridx = np.nonzero(reached)[0]
kd = KDTree(len(ridx))
for k_, i in enumerate(ridx): kd.insert(P[i], k_)
kd.balance()
for i in np.nonzero(~reached)[0]: label[i] = label[ridx[kd.find(P[i])[1]]]
vlabel = label[canon0]
limb_masked = {r: int((vlabel == i).sum()) for i, r in enumerate(REGIONS)}
for j, n in enumerate(deform):
    base, side = (n[:-2], n[-1]) if n[-2:] in ("_l", "_r") else (n, None)
    if side and base.startswith(("upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky")):
        D[vlabel != REGIONS.index("arm_" + side), j] = np.inf
    elif side and base.startswith(("thigh", "calf", "foot", "ball")):
        D[vlabel != REGIONS.index("leg_" + side), j] = np.inf
FALLOFF = opt("--falloff", 8.0)
rows = np.arange(nV)[:, None]; near = np.argsort(D, axis=1)[:, :4]
dn = D[rows, near].astype(np.float64) + 1e-3; dn = dn / dn[:, :1]
Wm = np.zeros_like(D); Wm[rows, near] = np.where(np.isfinite(dn), 1.0 / np.minimum(dn, 50.0) ** FALLOFF, 0)
Wm /= Wm.sum(1, keepdims=True)
print("LIMBS", limb_masked)
_, canon = np.unique(np.round(co, 5), axis=0, return_inverse=True); canon = canon.ravel()
E = np.array([e.vertices[:] for e in me.edges], np.int64)
for _ in range(int(opt("--smooth", 2))):
    acc = np.zeros((canon.max() + 1, Wm.shape[1]), np.float32); np.add.at(acc, canon, Wm)
    cnt = np.bincount(canon, minlength=canon.max() + 1)[:, None]; Wv = acc / np.maximum(cnt, 1)
    nb = np.zeros_like(Wv); deg = np.zeros(len(Wv), np.float32)
    ce = canon[E]; ce = ce[ce[:, 0] != ce[:, 1]]
    np.add.at(nb, ce[:, 0], Wv[ce[:, 1]]); np.add.at(nb, ce[:, 1], Wv[ce[:, 0]])
    np.add.at(deg, ce[:, 0], 1); np.add.at(deg, ce[:, 1], 1)
    Wv = 0.5 * Wv + 0.5 * nb / np.maximum(deg, 1)[:, None]
    Wm = Wv[canon]
_, canon = np.unique(np.round(co, 5), axis=0, return_inverse=True); canon = canon.ravel()
for vg in list(body.vertex_groups): body.vertex_groups.remove(vg)
for name in deform: body.vertex_groups.new(name=name)
G = {vg.index: vg.name for vg in body.vertex_groups}
print("LIMB weights falloff", FALLOFF)

# 3. rigid small pieces (connectivity welded across UV seams)
E = canon[E]
parent = np.arange(canon.max() + 1)
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
for u, w in E:
    ru, rw = find(u), find(w)
    if ru != rw: parent[ru] = rw
comp = np.array([find(c) for c in canon])
rigid = []
for r in np.unique(comp):
    idx = np.nonzero(comp == r)[0]
    size = float(np.linalg.norm(co[idx].max(0) - co[idx].min(0)))
    if size > RIGID_SIZE or len(idx) < 8: continue
    tot = Wm[idx].sum(0); top = int(tot.argmax()); share = float(tot[top] / max(tot.sum(), 1e-9))
    if share < RIGID_SHARE: continue
    Wm[idx] = 0; Wm[idx, top] = 1.0
    rigid.append({"verts": int(len(idx)), "size_m": round(size, 3), "bone": G[top], "share": round(share, 3)})
print("RIGID pieces", len(rigid))

# 4. cap at four influences, normalise, write back
order = np.argsort(-Wm, axis=1); keep = order[:, :4]
capped = np.zeros_like(Wm); rows = np.arange(nV)[:, None]; capped[rows, keep] = Wm[rows, keep]
s = capped.sum(1, keepdims=True); unweighted = int((s[:, 0] <= 0).sum()); capped = np.where(s > 0, capped / np.maximum(s, 1e-9), 0)
for vg in body.vertex_groups:
    col = capped[:, vg.index]; nz = np.nonzero(col > 1e-4)[0]
    vg.remove(list(range(nV)))
    for w in np.unique(np.round(col[nz], 4)):
        vg.add([int(i) for i in nz[np.round(col[nz], 4) == w]], float(w), 'REPLACE')
print("WEIGHTS unweighted", unweighted)
import os; os.makedirs(os.path.dirname(out_blend), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
for o in sc.objects: o.select_set(o in (arm, body))
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="RELATIVE", embed_textures=False)
json.dump({"method": "region_limited_nearest_bone", "regions": limb_masked, "falloff": FALLOFF, "rigid_size_m": RIGID_SIZE, "rigid_share": RIGID_SHARE, "rigid_pieces": rigid,
           "unweighted_verts": unweighted, "deform_bones": len(deform)}, open(out_rep, "w"), indent=2)
print("REBIND_OK")
