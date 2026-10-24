"""Authored turns and cycles on a synthetic biped: exact yaw, planted feet, clean seams."""
import copy
import math

import numpy as np
import pytest

from reference_asset_compiler import animation_authoring as aa

# A small biped facing +Y with its left side on +X (the UE mannequin convention).
BONES = [('pelvis', None, [0, -3, 95]), ('spine_01', 'pelvis', [0, 0, 12]), ('spine_03', 'spine_01', [0, 0, 20]),
         ('neck_01', 'spine_03', [0, 0, 20]), ('head', 'neck_01', [0, 0, 10]),
         ('thigh_l', 'pelvis', [10, 0, -6]), ('calf_l', 'thigh_l', [0, 2, -42]), ('foot_l', 'calf_l', [0, -2, -42]),
         ('ball_l', 'foot_l', [0, 14, -7]),
         ('thigh_r', 'pelvis', [-10, 0, -6]), ('calf_r', 'thigh_r', [0, 2, -42]), ('foot_r', 'calf_r', [0, -2, -42]),
         ('ball_r', 'foot_r', [0, 14, -7]),
         ('ik_foot_root', None, [0, 0, 0]), ('ik_foot_l', 'ik_foot_root', [10, -3, 5]), ('ik_foot_r', 'ik_foot_root', [-10, -3, 5])]


def rig():
    names = [b[0] for b in BONES]
    skeleton = {'bones': names, 'parents': [names.index(p) if p else -1 for _, p, _ in BONES],
                'units': 'cm', 'up_axis': 'Z', 'rotation': 'xyzw', 'armature_transform': [0, 0, 0, 0, 0, 0, 1]}
    idle = {'fps': 30, 'frames': 2, 'length': 1 / 30, 'loop': True, 'root_motion': False, 'speed_cm_s': None,
            'tracks': {n: [[*off, 0, 0, 0, 1]] * 2 for n, _, off in BONES}, 'layers': {'hands': 'relaxed'}}
    return {'bones': names, 'clips': {'MM_Idle': idle}, 'provenance': {}}, skeleton


def turn_spec(degrees, **extra):
    spec = {'name': 'turn', 'degrees': degrees, 'duration_s': 1.0, 'fps': 30, 'lift_cm': 5,
            'steps': [['lead', .12, .47], ['trail', .47, .84]], 'yaw_window': [.1, .86]}
    spec.update(extra)
    return spec


def test_facing_follows_the_feet():
    packet, skeleton = rig()
    forward, left = aa.facing(skeleton, packet['clips']['MM_Idle'])
    np.testing.assert_allclose(forward, [0, 1, 0], atol=1e-9)
    np.testing.assert_allclose(left, [1, 0, 0], atol=1e-9)


@pytest.mark.parametrize('degrees', [90, -90, 180, -180])
def test_turn_root_carries_exact_yaw_and_feet_stay_planted(degrees):
    packet, skeleton = rig()
    spec = turn_spec(degrees)
    if abs(degrees) == 180:
        spec.update(duration_s=1.3, steps=[['lead', .06, .28], ['trail', .28, .5], ['lead', .5, .72], ['trail', .72, .92]],
                    yaw_window=[.05, .9])
    clip = aa.turn_in_place(packet, skeleton, spec)
    m = aa.measure_clip(clip, skeleton, stand=packet['clips']['MM_Idle'])
    # Facing +Y with left on +X, a left turn is a negative rotation about +Z.
    assert m['root']['yaw_deg'] == pytest.approx(-degrees, abs=1e-9)
    assert m['root']['translation_cm'] == 0
    for side in 'lr':
        assert m['support'][side]['foot_slide_cm_s']['max'] < 1e-6
        assert len(m['support'][side]['intervals_s']) >= 2
    assert m['stand_match']['start_cm'] < 1e-6 and m['stand_match']['end_cm'] < 1e-6
    assert m['feet_minimum_gap_cm'] >= 3
    assert clip['root_motion'] and not clip['loop'] and len(clip['tracks']['root']) == clip['frames']


def test_turn_rejects_a_foot_that_never_steps_and_overlapping_steps():
    packet, skeleton = rig()
    with pytest.raises(ValueError, match='move both feet'):
        aa.turn_in_place(packet, skeleton, turn_spec(90, steps=[['lead', .1, .9]]))
    with pytest.raises(ValueError, match='both feet airborne'):
        aa.turn_in_place(packet, skeleton, turn_spec(90, steps=[['lead', .1, .6], ['trail', .4, .9]]))


def test_segment_gap():
    assert aa._segment_gap(np.array([0., 0]), np.array([5., 0]), np.array([0., 10]), np.array([5., 10])) == pytest.approx(5)
    # Feet crossing in an X touch even though every endpoint is 5 cm from the other foot.
    assert aa._segment_gap(np.array([0., 0]), np.array([-5., 5]), np.array([0., 10]), np.array([5., 5])) == 0


def cycle(packet, skeleton, period_frames, stride_cm):
    """A crude in-place run: each foot sweeps back on the ground for 40% of the cycle, then swings."""
    names = skeleton['bones']
    clip = {'fps': 30, 'frames': period_frames + 1, 'loop': True, 'root_motion': False,
            'length': period_frames / 30, 'tracks': copy.deepcopy(packet['clips']['MM_Idle']['tracks'])}
    for n in names:
        clip['tracks'][n] = [clip['tracks'][n][0]] * (period_frames + 1)
    pelvis = []
    for f in range(period_frames + 1):
        phase = f / period_frames
        p = list(clip['tracks']['pelvis'][0])
        p[2] -= 6 + 2 * math.cos(4 * math.pi * phase)
        pelvis.append(p)
    clip['tracks']['pelvis'] = pelvis
    world = aa.world_matrices(clip, skeleton)
    for side, offset in (('l', 0.), ('r', .5)):
        for f in range(period_frames + 1):
            phase = (f / period_frames - offset - .1) % 1
            foot = world[f, names.index('foot_' + side)].copy()
            if phase < .4:
                y, z = stride_cm / 2 - stride_cm * phase / .4, 0.
            else:
                u = (phase - .4) / .6
                y, z = -stride_cm / 2 + stride_cm * (1 - math.cos(math.pi * u)) / 2, 15 * math.sin(math.pi * u)
            target = foot[:3, 3] + np.array([0, y, z + 5])
            thigh_rot, calf_rot, _ = aa._two_bone(world[f], [names.index(f'{b}_{side}') for b in ('thigh', 'calf', 'foot')],
                                                   target, np.array([0, 1., 0]))
            w = world[f]
            for bone, rot in ((f'thigh_{side}', thigh_rot), (f'calf_{side}', calf_rot)):
                m = w[names.index(bone)].copy()
                m[:3, :3] = rot
                aa._apply_world(w, {i: [j for j, p in enumerate(skeleton['parents']) if p == i] for i in range(len(names))},
                                names.index(bone), m)
            m = w[names.index('foot_' + side)].copy()
            m[:3, 3] = target
            aa._apply_world(w, {i: [j for j, p in enumerate(skeleton['parents']) if p == i] for i in range(len(names))},
                            names.index('foot_' + side), m)
    aa._store(clip, skeleton, world)
    for track in clip['tracks'].values():
        track[-1] = track[0]
    clip['contacts_s'] = {'l': .1 * clip['length'], 'r': .6 * clip['length']}
    clip['speed_cm_s'] = stride_cm / (.4 * clip['length'])
    return clip


def test_cycle_blend_plants_the_ball_at_the_declared_speed_with_a_clean_seam():
    packet, skeleton = rig()
    packet['clips']['slow'] = cycle(packet, skeleton, 24, 40)
    packet['clips']['fast'] = cycle(packet, skeleton, 18, 50)
    clip = aa.blend_cycle(packet, skeleton, {'name': 'run', 'sources': ['slow', 'fast'], 'speed_cm_s': 200,
                                             'upper_weight': .5, 'phase_origin': .05, 'stance_threshold_cm': 1.5})
    forward, _ = aa.facing(skeleton, packet['clips']['MM_Idle'])
    m = aa.measure_clip(clip, skeleton, forward)
    for side in 'lr':
        assert m['support'][side]['ball_slide_cm_s']['max'] < 1e-3
        assert m['support'][side]['foot_slide_cm_s']['max'] < 1e-3
    assert m['loop_seam']['max_position_cm'] == 0
    assert clip['speed_cm_s'] == 200 and set(clip['contacts_s']) == {'l', 'r'}
    assert 0 <= clip['layers']['authoring']['lower_weight'] <= 1


def test_cycle_blend_needs_looped_in_place_sources():
    packet, skeleton = rig()
    with pytest.raises(ValueError, match='looped in-place'):
        aa.blend_cycle(packet, skeleton, {'sources': ['MM_Idle', 'MM_Idle'], 'speed_cm_s': 100, 'upper_weight': .5})


def test_author_packet_keeps_existing_clips_and_refuses_overwrites():
    packet, skeleton = rig()
    result, measurements = aa.author_packet(packet, skeleton, {'turns': [dict(turn_spec(90), name='MM_Turn')]})
    assert result['clips']['MM_Idle'] == packet['clips']['MM_Idle'] and 'MM_Turn' in measurements
    with pytest.raises(ValueError, match='already exists'):
        aa.author_packet(packet, skeleton, {'turns': [dict(turn_spec(90), name='MM_Idle')]})
