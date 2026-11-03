"""Skin the Raider's shoulders for arms that drop from the bind A-pose: a broad clavicle-to-upper-arm blend over the
deltoid, so the shoulder cap and its plate turn about half as far as the arm.

The landmark rig gave the upper arm the whole shoulder cap and plate at full weight, so lowering the arms 35-40
degrees to an idle swung the plate outward and folded the deltoid into the chest's side. Here, per side, the share a
vertex already gives the arm chain (clavicle + upper arm + its twist bones) is kept and only re-split along the arm:
upper arm share = smoothstep(T0, T1) of the distance past the shoulder joint along the upper arm.

  $B -b <rigged_manny.blend> --python shoulder_skin.py -- <out.blend>
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

out = Path(sys.argv[sys.argv.index('--') + 1])
T0, T1 = -0.05, 0.11          # metres along the upper arm from the shoulder joint: all clavicle .. all upper arm
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = bpy.data.objects['raider']
me = body.data
bones = rig.data.bones
P = np.array([v.co[:] for v in me.vertices])
nv = len(P)


def weights(group):
    vg = body.vertex_groups.get(group) or body.vertex_groups.new(name=group)
    w = np.zeros(nv)
    for v in me.vertices:
        for g in v.groups:
            if g.group == vg.index:
                w[v.index] = g.weight
    return w


def write(group, w):
    vg = body.vertex_groups[group]
    vg.remove(list(range(nv)))
    for i in np.nonzero(w > 1e-4)[0]:
        vg.add([int(i)], float(w[i]), 'REPLACE')


report = {}
for s in 'lr':
    names = [f'upperarm_{s}', f'upperarm_twist_01_{s}', f'upperarm_twist_02_{s}']
    cl = weights(f'clavicle_{s}')
    arm = {n: weights(n) for n in names}
    arm_sum = sum(arm.values())
    chain = cl + arm_sum
    split = {n: np.divide(arm[n], arm_sum, out=np.full(nv, 1.0 / 3), where=arm_sum > 1e-6) for n in names}
    S = np.array(bones[f'upperarm_{s}'].head_local)
    E = np.array(bones[f'lowerarm_{s}'].head_local)
    axis = (E - S) / np.linalg.norm(E - S)
    t = (P - S) @ axis
    x = np.clip((t - T0) / (T1 - T0), 0, 1)
    share = x * x * (3 - 2 * x)                     # smoothstep: upper arm's share of the chain
    touched = chain > 1e-4
    # Purely a function of position: the body is layered (plates and straps are thin shells over continuous cloth),
    # and layers only stay together if every layer at a point gets the same weights. A rigid-plate rule and mesh
    # smoothing gave the plate and the cloth under it different weights and the cloth poked through (rejected s1).
    new_cl = np.where(touched, chain * (1 - share), cl)
    new_arm = np.where(touched, chain * share, arm_sum)
    for n in names:
        arm[n] = new_arm * split[n]
    write(f'clavicle_{s}', new_cl)
    for n in names:
        write(n, arm[n])
    report[s] = {'chain_vertices': int(touched.sum()),
                 'clavicle_share_mean': round(float((new_cl[touched] / chain[touched]).mean()), 3)}
print('SHOULDER_SKIN', report)
bpy.ops.wm.save_as_mainfile(filepath=str(out))
Path(str(out) + '.json').write_text(json.dumps({'T0': T0, 'T1': T1, **report}, indent=2))
print('SHOULDER_SKIN_OK', out)
