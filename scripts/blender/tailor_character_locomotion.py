"""Test local pose corrections against exported UE tracks and the acquired garment.

Retains the T-pose, skin weights, meshes, UVs and facial morphs. Outputs animation
tracks only, with explicit triangle collision evidence. A passing pose is not a
claim about gameplay, interpolated blending or cloth simulation.
"""
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix_from_ue(value):
    x, y, z, qx, qy, qz, qw = value
    axes = Matrix.Diagonal((1., -1., 1., 1.))
    m = Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
    m.translation = Vector((x / 100, y / 100, z / 100))
    return np.array(axes @ m @ axes)


def ue_from_matrix(matrix):
    axes = Matrix.Diagonal((1., -1., 1., 1.))
    m = axes @ Matrix(matrix.tolist()) @ axes
    q = m.to_quaternion()
    return [*(m.translation * 100), q.x, q.y, q.z, q.w]


def prepare_mesh(obj, bone_indices, face_filter=None):
    rest = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
    indices = np.zeros((len(rest), 4), dtype=np.int32)
    weights = np.zeros((len(rest), 4))
    for v in obj.data.vertices:
        groups = sorted(v.groups, key=lambda g: -g.weight)[:4]
        for col, g in enumerate(groups):
            indices[v.index, col] = bone_indices[obj.vertex_groups[g.group].name]
            weights[v.index, col] = g.weight
    faces = [p.vertices[:] for p in obj.data.polygons if face_filter is None or face_filter(p, rest)]
    return rest, indices, weights, faces


def deform(mesh, transforms):
    rest, indices, weights, _ = mesh
    xforms = transforms[indices]
    points = np.einsum('nvij,nj->nvi', xforms[:, :, :3, :3], rest) + xforms[:, :, :3, 3]
    return np.einsum('nv,nvi->ni', weights, points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--dump', type=Path, required=True)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--candidate', default='elbow')
    parser.add_argument('--recipe', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, args.out / Path(__file__).name)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    bones = list(rig.data.bones)
    names = [b.name for b in bones]
    index = {name: i for i, name in enumerate(names)}
    parents = [index[b.parent.name] if b.parent else -1 for b in bones]
    assert all(p < i for i, p in enumerate(parents)), 'Parent-first bone ordering required.'
    rest = np.array([b.matrix_local for b in bones])
    inverse_rest = np.linalg.inv(rest)
    local_rest = np.array([inverse_rest[p] @ rest[i] if p >= 0 else rest[i] for i, p in enumerate(parents)])
    trial = json.loads(args.recipe.read_text()) if args.recipe else next(t for t in json.loads(args.trial.read_text()) if t['name'] == args.candidate)
    if args.recipe:
        assert sha(args.source) == trial['source_blend_sha256'], 'Source rig changed; remeasure before tailoring.'
    corrections = {index[n]: np.array(m) for n, m in trial['corrections_local'].items()}
    # Eliminate float noise from the recorded translations on rotation-only corrections.
    for i, m in corrections.items():
        if not names[i].startswith('clavicle_'):
            m[:3, 3] = 0
    outfit = bpy.data.objects['Character02_Outfit_And_Hands']
    upper_arm_groups = {g.index for g in outfit.vertex_groups if g.name.startswith(('upperarm', 'lowerarm', 'hand_'))}
    torso_vertices = {v.index for v in outfit.data.vertices
                      if abs(v.co.x) < .33 and (v.co.z < 1.28 or
                         sum(g.weight for g in v.groups if g.group in upper_arm_groups) < .5)}
    def torso_face(p, co):
        return all(i in torso_vertices for i in p.vertices)
    coat = prepare_mesh(outfit, index, torso_face)
    hands = {}
    for side in ['l', 'r']:
        hands[side] = prepare_mesh(bpy.data.objects['Character02_hand_' + side], index,
                                  lambda p, co: bool((np.abs(co[list(p.vertices), 0]) > .69).all()))
    def world_pose(local):
        world = np.empty_like(local)
        for i, parent in enumerate(parents):
            world[i] = world[parent] @ local[i] if parent >= 0 else local[i]
        return world
    def collision(world):
        transforms = world @ inverse_rest
        points = deform(coat, transforms)
        bvh = BVHTree.FromPolygons(points.tolist(), coat[3])
        results = {}
        for side, mesh in hands.items():
            hp = deform(mesh, transforms)
            hbvh = BVHTree.FromPolygons(hp.tolist(), mesh[3])
            pairs = bvh.overlap(hbvh)
            results[side] = len(pairs)
        return results
    def separate_arm(local, side, degrees):
        """Rotate the arm away from the chest while preserving its elbow bend."""
        if degrees <= 0:
            return local.copy()
        result = local.copy()
        world = world_pose(local)
        shoulder = index['upperarm_' + side]
        hand = index['hand_' + side]
        across = world[index['upperarm_l'], :3, 3] - world[index['upperarm_r'], :3, 3]
        across /= np.linalg.norm(across)
        outward = across if side == 'l' else -across
        reach = world[hand, :3, 3] - world[shoulder, :3, 3]
        axis = np.cross(reach, outward)
        if np.linalg.norm(axis) < 1e-8:
            return result
        axis /= np.linalg.norm(axis)
        rotation = np.array(Matrix.Rotation(math.radians(degrees), 3, Vector(axis)))
        desired = world[shoulder].copy()
        desired[:3, :3] = rotation @ desired[:3, :3]
        result[shoulder] = np.linalg.inv(world[parents[shoulder]]) @ desired
        return result
    manifest = json.loads((args.dump / 'manifest.json').read_text())
    if args.recipe:
        assert sha(args.dump / 'manifest.json') == trial['baseline_manifest_sha256'], 'Animation baseline changed; do not apply a second pose offset.'
        assert sha(args.dump / 'mesh-reference.json') == trial['mesh_reference_sha256'], 'Mesh reference changed.'
    # Skeleton assets retain legacy retarget data across mesh reimports. Skinning
    # uses the current mesh's bind pose, recorded from a fresh mesh component.
    reference = json.loads((args.dump / 'mesh-reference.json').read_text())
    ref_error = max(float(np.max(np.abs(matrix_from_ue(reference[n]) - local_rest[i])))
                    for i, n in enumerate(names) if n in reference)
    report = {'source_sha256': sha(args.source), 'manifest_sha256': sha(args.dump / 'manifest.json'),
              'script_sha256': sha(__file__), 'trial_sha256': sha(args.trial), 'candidate': args.candidate,
              'reference_matrix_max_error': ref_error, 'animations': [], 'blender': bpy.app.version_string,
              'geometry_changed': False, 'runtime_verified': False, 'production_ready': False}
    report['collision_region'] = 'Coat/skirt and torso through collar; upper sleeve triangles excluded by arm influence >= 0.5. Palm/fingers beyond rest |x|=0.69m; cuff overlap excluded.'
    assert ref_error < 1e-3, f'UE/Blender reference mismatch {ref_error}; the skeleton has changed, sir.'
    sampled = {}
    for entry in manifest['animations']:
        source = args.dump / entry['file']
        assert sha(source) == entry['sha256']
        clip = json.loads(source.read_text())
        result = {'name': clip['name'], 'before': [], 'after': []}
        changed_names = [names[i] for i in corrections] + ['ik_hand_gun', 'ik_hand_l', 'ik_hand_r']
        payload = {'name': clip['name'], 'path': clip['path'], 'length': clip['length'], 'fps': clip['fps'],
                   'source_sha256': entry['sha256'], 'tracks': {n: [] for n in changed_names}}
        locals_corrected = []
        required = np.zeros((len(clip['frames']), 2))
        for fi, frame in enumerate(clip['frames']):
            local = np.array([matrix_from_ue(frame[n]) if n in frame else local_rest[i] for i, n in enumerate(names)])
            base = world_pose(local)
            before = collision(base)
            for i, correction in corrections.items():
                local[i] = local[i] @ correction
            corrected = world_pose(local)
            after = collision(corrected)
            result['before'].append(before)
            locals_corrected.append(local.copy())
            for si, side in enumerate(['l', 'r']):
                if not after[side]:
                    continue
                for degrees in range(1, 21):
                    moved = separate_arm(local, side, degrees)
                    if collision(world_pose(moved))[side] == 0:
                        required[fi, si] = min(degrees + 2, 22)
                        break
                else:
                    raise RuntimeError(f'{clip["name"]} frame {fi} {side}: bounded arm separation failed.')
        # Smoothly enter and leave each correction. A short plateau retains the
        # measured clearance; smoothstep shoulders avoid a one-frame elbow pop.
        amounts = np.zeros_like(required)
        looping = 'Idle' in clip['name'] or 'Unarmed' in clip['name']
        for fi, si in zip(*np.nonzero(required)):
            distance = np.abs(np.arange(len(required)) - fi).astype(float)
            if looping:
                distance = np.minimum(distance, len(required) - 1 - distance)
            fraction = np.clip((distance - 3) / 7, 0, 1)
            envelope = 1 - fraction * fraction * (3 - 2 * fraction)
            amounts[:, si] = np.maximum(amounts[:, si], required[fi, si] * envelope)
        result['adaptive_separation_degrees'] = amounts.tolist()
        for fi, base_local in enumerate(locals_corrected):
            local = base_local.copy()
            for si, side in enumerate(['l', 'r']):
                local = separate_arm(local, side, float(amounts[fi, si]))
            corrected = world_pose(local)
            after = collision(corrected)
            # Keep IK markers on their actual hands after the FK posture correction.
            for source_bone, ik_bone in [('hand_r', 'ik_hand_gun'), ('hand_l', 'ik_hand_l'), ('hand_r', 'ik_hand_r')]:
                i, source_i = index[ik_bone], index[source_bone]
                parent = parents[i]
                local[i] = np.linalg.inv(corrected[parent]) @ corrected[source_i] if parent >= 0 else corrected[source_i]
                corrected = world_pose(local)
            if 'Idle' in clip['name'] or 'Unarmed' in clip['name']:
                if fi in {round((len(clip['frames']) - 1) * x / 8) for x in range(8)}:
                    sampled.setdefault(clip['name'], []).append(local.copy())
            result['after'].append(after)
            for n in changed_names:
                payload['tracks'][n].append(ue_from_matrix(local[index[n]]))
        result['frames'] = len(clip['frames'])
        result['before_collision_frames'] = sum(any(v for v in row.values()) for row in result['before'])
        result['after_collision_frames'] = sum(any(v for v in row.values()) for row in result['after'])
        print(f"{clip['name']}: coat-contact frames {result['before_collision_frames']} -> {result['after_collision_frames']} / {result['frames']}", flush=True)
        path = args.out / entry['file']
        path.write_text(json.dumps(payload, separators=(',', ':')))
        result['output_sha256'] = sha(path)
        report['animations'].append(result)
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))
    def blend_pose(a, b, alpha):
        mixed = np.empty_like(a)
        for i in range(len(names)):
            am, bm = Matrix(a[i].tolist()), Matrix(b[i].tolist())
            m = am.to_quaternion().slerp(bm.to_quaternion(), alpha).to_matrix().to_4x4()
            m.translation = am.translation.lerp(bm.translation, alpha)
            mixed[i] = np.array(m)
        return mixed
    idle = sampled['Character02_MM_Idle']
    blend_results = []
    for name, poses in sampled.items():
        if 'Unarmed' not in name:
            continue
        for i, pose in enumerate(poses):
            for alpha in [.25, .5, .75]:
                counts = collision(world_pose(blend_pose(idle[i % len(idle)], pose, alpha)))
                blend_results.append({'to': name, 'phase': i, 'alpha': alpha, 'counts': counts})
    directions = ['Fwd', 'Fwd_Right', 'Right', 'Bwd_Right', 'Bwd', 'Bwd_Left', 'Left', 'Fwd_Left']
    pairs = []
    for gait in ['Walk', 'Jog']:
        for i, direction in enumerate(directions):
            pairs.append((f'Character02_MF_Unarmed_{gait}_{direction}', f'Character02_MF_Unarmed_{gait}_{directions[(i + 1) % 8]}'))
    pairs += [(f'Character02_MF_Unarmed_Walk_{d}', f'Character02_MF_Unarmed_Jog_{d}') for d in directions]
    for left, right in pairs:
        for i, (a, b) in enumerate(zip(sampled[left], sampled[right])):
            for alpha in [.25, .5, .75]:
                counts = collision(world_pose(blend_pose(a, b, alpha)))
                blend_results.append({'from': left, 'to': right, 'phase': i, 'alpha': alpha, 'counts': counts})
    report['idle_locomotion_blends'] = blend_results
    report['blend_collision_samples'] = sum(any(r['counts'].values()) for r in blend_results)
    report['collision_frame_total'] = sum(r['after_collision_frames'] for r in report['animations'])
    report['passed'] = report['collision_frame_total'] == 0 and report['blend_collision_samples'] == 0
    (args.out / 'report.json').write_text(json.dumps(report, indent=2))
    print(f"Blend contacts: {report['blend_collision_samples']}/{len(blend_results)}; passed={report['passed']}", flush=True)
    print('POSTURE_BAKE_MEASURED: every frame has faced the tailor, sir.')


if __name__ == '__main__':
    main()
