# SPDX-License-Identifier: MIT
"""CPU-only evidence: source motion, rest calibration and Character02 leg weights."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def bend(world, side):
    a, b, c = [world[f'{n}_{side}'][:3, 3] for n in ('thigh', 'calf', 'foot')]
    u, v = b-a, c-b
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v)/(np.linalg.norm(u)*np.linalg.norm(v)), -1, 1))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--anim-tools', type=Path, required=True)
    p.add_argument('--game-tools', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    data = json.loads(args.packet.read_text())
    assert hashlib.sha256(args.source.read_bytes()).hexdigest() == data['provenance']['character_blend_sha256']
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.anim_tools))
    import clip_retarget as cr
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    rig = cr.TargetRig(next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE'))
    target = {n: rig.rest[i] for i, n in enumerate(rig.names)}
    weights = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        candidates, opposite, unnormalized = [], [], []
        names = {g.index: g.name for g in obj.vertex_groups}
        for v in obj.data.vertices:
            xyz = obj.matrix_world @ v.co
            influence = {names[g.group]: g.weight for g in v.groups}
            legs = {side: sum(w for n, w in influence.items() if n.startswith(('thigh_', 'calf_', 'foot_', 'ball_')) and n.endswith('_'+side)) for side in 'lr'}
            if sum(legs.values()) < .5 or xyz.z > .88:
                continue
            candidates.append(v.index)
            if abs(sum(influence.values())-1) > .001:
                unnormalized.append(v.index)
            if abs(xyz.x) > .06 and xyz.z < .80 and legs['r' if xyz.x > 0 else 'l'] > .05:
                opposite.append({'vertex': v.index, 'point': list(xyz), 'leg_weights': legs})
        if candidates:
            weights.append({'mesh': obj.name, 'leg_vertices': len(candidates),
                'unnormalized': unnormalized, 'opposite_leg_influences': opposite})
    library_path = Path(data['provenance']['libraries']['ual1']['path'])
    library = cr.UalLibrary(library_path)
    reference = library.reference()
    profile = json.loads(Path(data['provenance']['profile'][0]).read_text())
    retarget = cr.Retarget(rig, library, profile['bone_map'])
    old_reference = retarget.world('A_TPose', 0)
    poses = []
    for f in range(41):
        t = library.length('Walk_Loop') * f / 40
        source = library.world('Walk_Loop', t)
        transferred = retarget.world('Walk_Loop', t)
        transferred = {n: transferred[i] for i, n in enumerate(rig.names)}
        poses.append({'frame': f, 'time': t,
            'source_bend': {s: bend(source, s) for s in 'lr'},
            'retarget_bend': {s: bend(transferred, s) for s in 'lr'},
            'source_positions_m': {n: m[:3, 3].tolist() for n, m in source.items() if n.startswith(('pelvis','thigh_', 'calf_', 'foot_', 'ball_'))},
            'target_positions_m': {n: m[:3, 3].tolist() for n, m in transferred.items() if n.startswith(('pelvis','thigh_', 'calf_', 'foot_', 'ball_'))}})
    # Controlled counterfactual: align each actual leg segment to its mapped
    # source segment, instead of a signed, hard-coded lateral rotation.
    for side in 'lr':
        for parent, child in [('thigh', 'calf'), ('calf', 'foot'), ('foot', 'ball')]:
            a, b = f'{parent}_{side}', f'{child}_{side}'
            direction = target[b][:3, 3] - target[a][:3, 3]
            source_direction = retarget.A @ (reference[b][:3, 3] - reference[a][:3, 3])
            swing = cr._rot_between(direction, source_direction)
            retarget.tgt_ref[rig.index[a]] = swing @ target[a][:3, :3]
            if parent == 'foot':
                retarget.tgt_ref[rig.index[b]] = swing @ target[b][:3, :3]
    new_reference = retarget.world('A_TPose', 0)
    candidate = copy.deepcopy(data)
    clip = candidate['clips']['MF_Unarmed_Walk_Fwd']
    axes = Matrix.Diagonal((1., -1., 1., 1.))
    def matrix(values):
        x, y, z, qx, qy, qz, qw = values
        m = Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
        m.translation = Vector((x/100, y/100, z/100))
        return np.array(axes @ m @ axes)
    leg_names = {f'thigh_{s}' for s in 'lr'}
    for side in 'lr':
        leg_names.update(b.name for b in rig.obj.data.bones[f'thigh_{side}'].children_recursive)
    worlds = []
    for f in range(clip['frames']):
        w = np.empty_like(rig.rest)
        for i, parent in enumerate(rig.parents):
            w[i] = (w[parent] if parent >= 0 else rig.mw) @ matrix(clip['tracks'][rig.names[i]][f])
        calibrated = retarget.world('Walk_Loop', f/clip['fps'])
        for name in leg_names:
            w[rig.index[name]] = calibrated[rig.index[name]]
        worlds.append(w)
        poses[f]['calibrated_bend'] = {s: bend({n: calibrated[i] for i, n in enumerate(rig.names)}, s) for s in 'lr'}
    sys.path.insert(0, str(args.game_tools))
    from CheckLocomotionFooting import boot_data
    from CheckLocomotionClearance import deform
    boots = boot_data(rig.obj)
    inverse_rest = np.linalg.inv(rig.rest)
    low = min(float(deform(mesh, w @ inverse_rest)[ids[side], 2].min())
              for w in worlds for _, mesh, ids in boots for side in 'lr' if ids[side])
    lift = .002-low
    assert abs(lift) < .12, 'Calibration needs a separate proportion/contact investigation'
    for f, w in enumerate(worlds):
        w[:, 2, 3] += lift
        for source, destination in cr.IK_PINS:
            w[rig.index[destination]] = w[rig.index[source]].copy()
        local = rig.world_to_local(w)
        for n in leg_names | {'pelvis', 'ik_foot_l', 'ik_foot_r'}:
            clip['tracks'][n][f] = [float(v) for v in cr.ue_from_matrix(local[rig.index[n]])]
    clip.setdefault('layers', {})['diagnostic_leg_calibration'] = {'installed': False,
        'constant_ground_lift_cm': lift*100, 'runtime_speed_and_contacts_require_revalidation': True}
    (args.out/'diagnostic-candidate.json').write_text(json.dumps(candidate, separators=(',', ':')))
    report = {'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'packet_sha256': hashlib.sha256(args.packet.read_bytes()).hexdigest(),
        'library_sha256': hashlib.sha256(library_path.read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'blender': bpy.app.version_string, 'source_reference_bend': {s: bend(reference, s) for s in 'lr'},
        'target_rest_bend': {s: bend(target, s) for s in 'lr'}, 'retarget_scale': retarget.scale,
        'source_reference_positions': {n: m[:3, 3].tolist() for n, m in reference.items() if n.startswith(('pelvis','thigh_', 'calf_', 'foot_', 'ball_'))},
        'target_rest_positions': {n: m[:3, 3].tolist() for n, m in target.items() if n.startswith(('pelvis','thigh_', 'calf_', 'foot_', 'ball_'))},
        'weight_screen': weights, 'poses': poses,
        'reference_ankle_width_cm': {'existing': float((old_reference[rig.index['foot_l'],0,3]-old_reference[rig.index['foot_r'],0,3])*100),
                                   'calibrated': float((new_reference[rig.index['foot_l'],0,3]-new_reference[rig.index['foot_r'],0,3])*100)},
        'diagnostic_candidate_ground_lift_cm': lift*100,
        'scope': 'Rest calibration, source/retarget joint motion and broad weight leakage screen; not exhaustive deformation acceptance.'}
    (args.out/'diagnosis.json').write_text(json.dumps(report, indent=2))
    print('WALK_DIAGNOSIS_COMPLETE -- the knees have provided their alibis.')


if __name__ == '__main__':
    main()
