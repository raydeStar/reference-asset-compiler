# SPDX-License-Identifier: MIT
"""Relax an idle's arms and hands, then carry the change into its entry/exit handoffs.

Profile-driven (profiles/animation/repair/<name>.json); immutable input, versioned
output. Runs on CPU. Preserve the accepted body, rest transforms, timing and root tracks.
This is an authored candidate, not a declaration of artistic acceptance.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from reference_asset_compiler.animation_motion import (
    _aim, matrices, solve_contact, transforms, validate_packet, world_matrices,
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_profile(path):
    profile = json.loads(Path(path).read_text())
    if profile.get('schema') != 'rac.idle-handoff-relaxation.v1':
        raise ValueError('unsupported idle handoff profile')
    for key in ('idle_clip', 'pelvis_motion_scale', 'idle_arm_directions', 'arm_motion_follow',
                'thumb_adduction_degrees', 'handoffs'):
        if key not in profile:
            raise ValueError(f'profile missing {key}')
    for bone in ('upperarm', 'lowerarm'):
        xy = profile['idle_arm_directions'][bone]
        if len(xy) != 2 or sum(a * a for a in xy) >= 1:
            raise ValueError(f'{bone} direction needs the x/y of a unit downward vector')
    for name, spec in profile['handoffs'].items():
        if spec.get('blend_to_idle') not in (None, 'start', 'end'):
            raise ValueError(f'{name}: blend_to_idle is start, end or absent')
    return profile


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def repair(packet, skeleton, profile):
    result = copy.deepcopy(packet)
    idle_name = profile['idle_clip']
    arms = profile['idle_arm_directions']
    handoff = profile['handoffs']
    names, parents = skeleton['bones'], skeleton['parents']
    ix = {name: i for i, name in enumerate(names)}
    families = {}
    for root in range(len(names)):
        family = {root}
        for i, parent in enumerate(parents):
            if parent in family:
                family.add(i)
        families[root] = sorted(family)

    def rotate(world, bone, rotation):
        root = ix[bone]
        pivot = world[root, :3, 3].copy()
        for i in families[root]:
            world[i, :3, 3] = pivot + rotation @ (world[i, :3, 3] - pivot)
            world[i, :3, :3] = rotation @ world[i, :3, :3]

    def store(clip, worlds):
        basis = matrices(skeleton['armature_transform'])
        root = basis @ matrices(clip['tracks']['root']) if 'root' in clip['tracks'] else basis
        local = worlds.copy()
        for i, parent in enumerate(parents):
            local[:, i] = np.linalg.inv(worlds[:, parent] if parent >= 0 else root) @ worlds[:, i]
        values = transforms(local)
        for i, name in enumerate(names):
            clip['tracks'][name] = values[:, i].tolist()

    def pins(world):
        for source, target in [('foot_l', 'ik_foot_l'), ('foot_r', 'ik_foot_r'),
                               ('hand_l', 'ik_hand_l'), ('hand_r', 'ik_hand_r'), ('hand_r', 'ik_hand_gun')]:
            if target in ix:
                world[ix[target]] = world[ix[source]].copy()

    def relax_thumbs(world, amount=45):
        for side in 'lr':
            a = world[ix[f'thumb_02_{side}'], :3, 3] - world[ix[f'thumb_01_{side}'], :3, 3]
            b = world[ix[f'index_02_{side}'], :3, 3] - world[ix[f'index_01_{side}'], :3, 3]
            a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
            axis = np.cross(a, b)
            angle = min(np.radians(amount), np.arccos(np.clip(np.dot(a, b), -1, 1)))
            if np.linalg.norm(axis) > 1e-8:
                rotate(world, f'thumb_01_{side}', Rotation.from_rotvec(axis / np.linalg.norm(axis) * angle).as_matrix())

    idle = result['clips'][idle_name]
    original = world_matrices(idle, skeleton)
    pelvis = np.array(idle['tracks']['pelvis'])
    pelvis[:, :3] = pelvis[0, :3] + profile['pelvis_motion_scale'] * (pelvis[:, :3] - pelvis[0, :3])
    idle['tracks']['pelvis'] = pelvis.tolist()
    duration = (idle['frames'] - 1) / idle['fps']
    for side in 'lr':
        solve_contact(idle, skeleton, {'chain': [f'thigh_{side}', f'calf_{side}', f'foot_{side}'],
            'interval_s': [0, duration], 'blend_s': 0,
            'target_cm': original[0, ix[f'foot_{side}'], :3, 3].tolist(),
            'sync_effectors': [f'ik_foot_{side}']})
    worlds = world_matrices(idle, skeleton)
    for world in worlds:
        for side, sign in [('l', 1), ('r', -1)]:
            for bone, child, xy in [('upperarm', 'lowerarm', arms['upperarm']), ('lowerarm', 'hand', arms['lowerarm'])]:
                source_direction = original[0, ix[f'{child}_{side}'], :3, 3] - original[0, ix[f'{bone}_{side}'], :3, 3]
                direction = world[ix[f'{child}_{side}'], :3, 3] - world[ix[f'{bone}_{side}'], :3, 3]
                target = np.array([sign * xy[0], xy[1], -np.sqrt(1 - sum(a*a for a in xy))])
                target += profile['arm_motion_follow'] * (direction / np.linalg.norm(direction) - source_direction / np.linalg.norm(source_direction))
                rotate(world, f'{bone}_{side}', _aim(np.eye(3), direction, target))
        relax_thumbs(world, profile['thumb_adduction_degrees'])
        pins(world)
    store(idle, worlds)

    # Keep the entrance/exit handoffs: the butler does not teleport his elbows.
    modified = [idle_name]
    for name, spec in handoff.items():
        clip = result['clips'][name]
        worlds = world_matrices(clip, skeleton)
        for f, world in enumerate(worlds):
            ramp = spec.get('fade_out_after')
            weight = 1 - smooth((f/(len(worlds)-1) - ramp)/spec.get('fade_out_length', 1 - ramp)) if ramp is not None else 1
            across = world[ix['upperarm_l'], :3, 3] - world[ix['upperarm_r'], :3, 3]
            across /= np.linalg.norm(across)
            for side, sign in [('l', 1), ('r', -1)]:
                for bone, degrees in [('upperarm', spec['upperarm_degrees']), ('lowerarm', spec['lowerarm_degrees'])]:
                    reach = world[ix[f'hand_{side}'], :3, 3] - world[ix[f'{bone}_{side}'], :3, 3]
                    axis = np.cross(reach, across * sign)
                    axis /= np.linalg.norm(axis)
                    rotate(world, f'{bone}_{side}', Rotation.from_rotvec(axis * np.radians(degrees * weight)).as_matrix())
            relax_thumbs(world, profile['thumb_adduction_degrees'] * weight)
            pins(world)
        store(clip, worlds)
        # Change arm families only in handoff windows; retain authored hips and feet.
        for f in range(clip['frames']):
            frames = spec.get('blend_frames', 6)
            if spec.get('blend_to_idle') == 'start':
                weight = 1 - smooth(f / frames)
            elif spec.get('blend_to_idle') == 'end':
                weight = smooth((f - (clip['frames'] - frames - 1)) / frames)
            else:
                weight = 0
            if not weight:
                continue
            for side in 'lr':
                for i in families[ix[f'upperarm_{side}']]:
                    bone = names[i]
                    a, b = np.array(clip['tracks'][bone][f]), np.array(idle['tracks'][bone][0])
                    q = Slerp([0, 1], Rotation.from_quat([a[3:], b[3:]]))([weight]).as_quat()[0]
                    clip['tracks'][bone][f] = [*((1-weight)*a[:3] + weight*b[:3]), *q]
        worlds = world_matrices(clip, skeleton)
        for world in worlds:
            pins(world)
        store(clip, worlds)
        modified.append(name)
    validate_packet(result)
    for name, clip in packet['clips'].items():
        assert {k: v for k, v in clip.items() if k != 'tracks'} == {k: v for k, v in result['clips'][name].items() if k != 'tracks'}
        assert clip['tracks'].get('root') == result['clips'][name]['tracks'].get('root')
    return result, modified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--skeleton', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding='utf-8-sig'))
    skeleton = json.loads(args.skeleton.read_text())
    validate_packet(packet)
    assert packet['bones'] == skeleton['bones']
    assert packet['provenance']['character_blend_sha256'] == skeleton['source_sha256']
    profile = load_profile(args.profile)
    missing = ({profile['idle_clip']} | set(profile['handoffs'])) - set(packet['clips'])
    if missing:
        raise ValueError(f'profile names clips absent from the packet: {sorted(missing)}')
    result, modified = repair(packet, skeleton, profile)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'clips.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    (args.out/'derivation.json').write_text(json.dumps({'source': str(args.packet.resolve()),
        'source_sha256': digest(args.packet), 'skeleton_sha256': digest(args.skeleton),
        'script_sha256': digest(Path(__file__)), 'profile_sha256': digest(args.profile), 'packet_sha256': digest(args.out/'clips.json'),
        'modified_clips': modified, 'timing_root_and_events_preserved': True,
        'human_approved': False, 'production_ready': False}, indent=2), encoding='utf-8')
    print('CANDIDATE_AUTHORED -- the elbows have been asked to mind the tailoring.')


if __name__ == '__main__':
    main()
