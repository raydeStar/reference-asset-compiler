"""Shoulder weight repair on the rigged Raider, written as a versioned derivative.

Mark found arms-out and arms-overhead weird. Measured cause: chest skin and cloth beside the armpit, 2 to 5 cm
on the body side of the shoulder joint, carried up to 0.8 upper-arm weight from the MakeHuman transfer, so
raising the arm lifted flaps of chest out sideways like wings (the brown flaps in the overhead pose).

  1. On the body side of each shoulder joint, the upper arm's share (with its twist bones) is capped: none
     beyond CAP_IN inboard of the joint, rising to full at the joint. The excess goes to the vertex's own torso
     weights (spine, clavicle) in proportion, or to spine_05 when it has none.
  2. Around each shoulder joint, weights are averaged with the nearest vertices in space (across shells, not
     along the surface), so layered cloth moves as one; the cap is applied again afterwards.

Tried and dropped (2026-11-01): moving the clavicle's share out to the upper arm (put still more arm weight on
the chest) and making the pauldron rigid at half clavicle, half upper arm (its inner layer poked through).

  $B -b <rigged.blend> --python fix_shoulders.py -- <out_blend> <out_fbx>
"""
import bpy, sys
import numpy as np
from mathutils.kdtree import KDTree
a = sys.argv[sys.argv.index("--") + 1:]; out_blend, out_fbx = a[0], a[1]
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE'); body = bpy.data.objects["raider"]
M = body.matrix_world; A = arm.matrix_world
names = [g.name for g in body.vertex_groups]; idx = {n: i for i, n in enumerate(names)}
nv = len(body.data.vertices)
W = np.zeros((nv, len(names)), np.float32)
for v in body.data.vertices:
    for g in v.groups: W[v.index, g.group] = g.weight
P = np.array([(M @ v.co)[:] for v in body.data.vertices])
def joint(s): return np.array((A @ arm.data.bones[f"upperarm_{s}"].head_local)[:])
CAP_IN, ZONE_UP, ZONE_DOWN, REACH, K, ITERS = 0.06, 0.08, 0.20, 0.15, 12, 2
TORSO = [i for i, n in enumerate(names) if n.startswith(("spine_", "clavicle_"))]
def cap():
    moved = 0
    for s in ("l", "r"):
        j = joint(s); sign = 1 if s == "l" else -1
        armg = [i for i, n in enumerate(names) if n.startswith(("upperarm", "lowerarm")) and n.endswith(f"_{s}")]
        side = [i for i in TORSO if not names[i].startswith("clavicle_") or names[i].endswith(f"_{s}")]
        inward = j[0] * sign - P[:, 0] * sign                        # metres on the body side of the joint
        near = (P[:, 2] < j[2] + ZONE_UP) & (P[:, 2] > j[2] - ZONE_DOWN) & (P[:, 0] * sign > 0)
        allow = np.clip(1 - inward / CAP_IN, 0, 1)
        have = W[:, armg].sum(1)
        over = np.where(near & (have > allow), have - allow, 0)
        k = np.nonzero(over > 1e-4)[0]
        if not len(k): continue
        W[np.ix_(k, armg)] *= (allow[k] / have[k])[:, None]
        tw = W[np.ix_(k, side)]; ts = tw.sum(1)
        share = np.where(ts[:, None] > 1e-4, tw / np.maximum(ts, 1e-4)[:, None], 0)
        share[ts <= 1e-4, side.index(idx["spine_05"])] = 1
        W[np.ix_(k, side)] += share * over[k][:, None]
        moved += len(k)
    return moved
print("CAP", cap(), "verts")
kd = KDTree(nv)
for i, p in enumerate(P): kd.insert(p, i)
kd.balance()
zone = np.zeros(nv, bool)
for s in ("l", "r"): zone |= np.linalg.norm(P - joint(s), axis=1) < REACH
zi = np.nonzero(zone)[0]
nbr = np.array([[i for _, i, _ in kd.find_n(P[k], K)] for k in zi])
for _ in range(ITERS): W[zi] = 0.5 * W[zi] + 0.5 * W[nbr].mean(1)
print("SMOOTHED", len(zi), "verts; CAP again", cap(), "verts")
for k in range(nv):   # at most 4 influences, normalised
    row = W[k]; keep = np.argsort(row)[-4:]; m = np.zeros_like(row); m[keep] = row[keep]
    W[k] = m / m.sum() if m.sum() > 0 else m
for g in body.vertex_groups: g.remove(range(nv))
for gi in range(len(names)):
    for k in np.nonzero(W[:, gi] > 1e-4)[0]: body.vertex_groups[gi].add([int(k)], float(W[k, gi]), 'REPLACE')
# 3. The face mesh's neck reaches 12 cm into the collar and flares out to the shoulders (to 0.28 m either side
# at chest height), weighted to the neck alone. Raising the arms lifts the jacket off that skin, which showed as
# skin-coloured flaps at the armpits. Below SKIRT_TOP it takes the weights of the nearest body vertex, blending
# into its own neck weights up to SKIRT_TOP + SKIRT_BLEND, so it stays under the jacket.
SKIRT_TOP, SKIRT_BLEND = 1.54, 0.04
face = bpy.data.objects.get("face")
if face:
    FM = face.matrix_world; F = np.array([(FM @ v.co)[:] for v in face.data.vertices])
    t = np.clip((F[:, 2] - SKIRT_TOP) / SKIRT_BLEND, 0, 1)              # 0 = body weights, 1 = own neck weights
    fk = np.nonzero(t < 1)[0]
    for n in names:
        if n not in face.vertex_groups: face.vertex_groups.new(name=n)
    fidx = {g.name: g.index for g in face.vertex_groups}
    FW = np.zeros((len(F), len(face.vertex_groups)), np.float32)
    for v in face.data.vertices:
        for g in v.groups: FW[v.index, g.group] = g.weight
    for k in fk:
        _, j, _ = kd.find(F[k]); new = np.zeros(FW.shape[1], np.float32)
        for gi in np.nonzero(W[j] > 1e-4)[0]: new[fidx[names[gi]]] = W[j, gi]
        FW[k] = t[k] * FW[k] + (1 - t[k]) * new
        row = FW[k]; keep = np.argsort(row)[-4:]; m = np.zeros_like(row); m[keep] = row[keep]; FW[k] = m / m.sum()
    for g in face.vertex_groups: g.remove([int(k) for k in fk])
    for gi in range(FW.shape[1]):
        for k in fk:
            if FW[k, gi] > 1e-4: face.vertex_groups[gi].add([int(k)], float(FW[k, gi]), 'REPLACE')
    print("FACE_SKIRT reweighted", len(fk), "verts")
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
for o in sc.objects: o.select_set(o.type in ('ARMATURE', 'MESH'))
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="COPY", embed_textures=True, use_mesh_modifiers=False)
print("SHOULDERS_OK")
