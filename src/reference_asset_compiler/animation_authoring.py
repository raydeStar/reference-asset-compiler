# SPDX-License-Identifier: MIT
"""Author locomotion clips on an existing packet's rig: a phase-synchronised cycle
blend with planted stances, and turn-in-place clips whose root carries the yaw.

Everything works in the packet's UE-local component space (cm, Z up, xyzw) and
returns ordinary packet clips plus measurements. Per-character choices (source
clips, speeds, timing, lift) come from a profile; nothing here names a character.
"""
import copy
import math

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from reference_asset_compiler.animation_motion import (
    matrices, sample_clip, solve_contact, transforms, world_matrices,
)


def _smooth(x):
    x = np.clip(x, 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


def _rig(skeleton):
    names, parents = skeleton['bones'], skeleton['parents']
    ix = {n: i for i, n in enumerate(names)}
    children = {i: [] for i in range(len(names))}
    for i, p in enumerate(parents):
        if p >= 0:
            children[p].append(i)
    return names, parents, ix, children


def _family(children, root):
    out, stack = [], [root]
    while stack:
        i = stack.pop()
        out.append(i)
        stack.extend(children[i])
    return out


def _store(clip, skeleton, worlds, root_track=None):
    """Rebuild local tracks from component-space worlds under the clip's root."""
    names, parents = skeleton['bones'], skeleton['parents']
    basis = matrices(skeleton.get('armature_transform', [0, 0, 0, 0, 0, 0, 1]))
    if root_track is not None:
        root = basis @ matrices(root_track)
    elif 'root' in clip['tracks'] and 'root' not in names:
        root = basis @ matrices(clip['tracks']['root'])
    else:
        root = np.broadcast_to(basis, worlds.shape[:1] + (4, 4))
    local = worlds.copy()
    for i, p in enumerate(parents):
        local[:, i] = np.linalg.inv(worlds[:, p] if p >= 0 else root) @ worlds[:, i]
    values = transforms(local)
    for i, n in enumerate(names):
        clip['tracks'][n] = values[:, i].tolist()
    if root_track is not None:
        clip['tracks']['root'] = np.asarray(root_track).tolist()


def facing(skeleton, clip, side_pair=('l', 'r')):
    """Forward and left unit vectors (component XY) from a standing pose's feet."""
    _, _, ix, _ = _rig(skeleton)
    w = world_matrices(clip, skeleton)[0]
    left = w[ix['foot_' + side_pair[0]], :3, 3] - w[ix['foot_' + side_pair[1]], :3, 3]
    forward = sum(w[ix['ball_' + s], :3, 3] - w[ix['foot_' + s], :3, 3] for s in side_pair)
    left[2] = forward[2] = 0
    return forward / np.linalg.norm(forward), left / np.linalg.norm(left)


# --------------------------------------------------------------------------- cycles

def _sample_cycle(clip, phase, contact_s):
    length = (clip['frames'] - 1) / clip['fps']
    return sample_clip(clip, (contact_s + phase * length) % length)


def _blend_tracks(a, b, weights):
    out = {}
    for bone in a:
        w = weights.get(bone, 0.)
        ta, tb = np.asarray(a[bone]), np.asarray(b[bone])
        xyz = (1 - w) * ta[:, :3] + w * tb[:, :3]
        qa, qb = ta[:, 3:].copy(), tb[:, 3:]
        qa[np.sum(qa * qb, axis=1) < 0] *= -1
        q = np.array([Slerp([0, 1], Rotation.from_quat([x, y]))([w]).as_quat()[0] for x, y in zip(qa, qb)])
        out[bone] = np.concatenate((xyz, q), axis=1).tolist()
    return out


def stance_intervals(clip, skeleton, forward, threshold_cm=1.5, sides='lr'):
    """Support intervals from the ball of the foot: low and moving backward."""
    _, _, ix, _ = _rig(skeleton)
    w = world_matrices(clip, skeleton)
    fps, n = clip['fps'], clip['frames']
    result = {}
    for s in sides:
        ball = w[:, ix['ball_' + s], :3, 3]
        back = -(np.gradient(ball, axis=0) * fps) @ forward
        low = ball[:, 2] <= ball[:, 2].min() + threshold_cm
        support = low & (back > 0)
        frames = np.flatnonzero(support)
        if len(frames) < 2:
            raise ValueError(f'no support found for {s}')
        runs = np.split(frames, np.flatnonzero(np.diff(frames) > 1) + 1)
        run = max(runs, key=len)
        if run[0] == 0 or run[-1] == n - 1:
            raise ValueError(f'{s} support wraps the cycle seam; move the phase origin')
        result[s] = [run[0] / fps, run[-1] / fps]
    return result


def _stance_speed(clip, skeleton, forward, intervals):
    _, _, ix, _ = _rig(skeleton)
    w = world_matrices(clip, skeleton)
    fps = clip['fps']
    speeds = []
    for s, (a, b) in intervals.items():
        f0, f1 = round(a * fps), round(b * fps)
        ball = w[f0:f1 + 1, ix['ball_' + s], :3, 3]
        speeds.append(-((ball[-1] - ball[0]) @ forward) / ((f1 - f0) / fps))
    return float(np.mean(speeds))


def _hold_rotation(clip, skeleton, bone, rotation, first, last, ramp):
    """Blend a bone's world rotation to a fixed one over frames [first, last], full weight inside the ramps."""
    names, parents = skeleton['bones'], skeleton['parents']
    world = world_matrices(clip, skeleton)
    track = np.asarray(clip['tracks'][names[bone]], dtype=float)
    held = Rotation.from_matrix(rotation)
    for f in range(max(first, 0), min(last, clip['frames'] - 1) + 1):
        weight = min(1., (f - first) / ramp, (last - f) / ramp) if ramp else 1.
        if weight <= 0:
            continue
        current = Rotation.from_matrix(world[f, bone, :3, :3])
        target = Slerp([0, 1], Rotation.concatenate([current, held]))([weight])[0]
        parent = Rotation.from_matrix(world[f, parents[bone], :3, :3])
        track[f, 3:] = (parent.inv() * target).as_quat()
    clip['tracks'][names[bone]] = track.tolist()


def blend_cycle(packet, skeleton, spec):
    """Phase-synchronised blend of two looped cycles, retimed and planted at a target speed.

    spec: name, sources [slow, fast], speed_cm_s, fps, upper_weight, optional
    lower_weight (else solved so the unplanted stance already moves near the
    target speed), phase_origin (cycle fraction before the left touchdown),
    stance_threshold_cm, plant_blend_frames.
    """
    names, parents, ix, children = _rig(skeleton)
    slow, fast = (packet['clips'][n] for n in spec['sources'])
    for c in (slow, fast):
        if not c.get('loop') or not c.get('contacts_s') or c.get('root_motion'):
            raise ValueError('cycle blend needs looped in-place sources with contacts_s')
    lower = set()
    for root in ('thigh_l', 'thigh_r'):
        lower.update(names[i] for i in _family(children, ix[root]))
    lower.update(n for n in names if n.startswith('ik_foot'))
    lower.add('pelvis')
    fps = spec.get('fps', slow['fps'])
    forward, _ = facing(skeleton, packet['clips'][spec.get('stand_clip', 'MM_Idle')])
    lengths = [(c['frames'] - 1) / c['fps'] for c in (slow, fast)]
    origin = spec.get('phase_origin', .25)

    def build(w_lower):
        length = (1 - w_lower) * lengths[0] + w_lower * lengths[1]
        frames = int(round(length * fps)) + 1
        phase = np.arange(frames) / (frames - 1)
        a = _sample_cycle(slow, (phase - origin) % 1, slow['contacts_s']['l'])
        b = _sample_cycle(fast, (phase - origin) % 1, fast['contacts_s']['l'])
        weights = {n: (w_lower if n in lower else spec['upper_weight']) for n in a}
        clip = {'fps': fps, 'frames': frames, 'length': (frames - 1) / fps, 'loop': True,
                'root_motion': False, 'tracks': _blend_tracks(a, b, weights)}
        for bone, track in clip['tracks'].items():
            track[-1] = track[0]
        return clip

    w_lower = spec.get('lower_weight')
    if w_lower is None:
        trials = []
        for w in np.linspace(0, 1, 41):
            c = build(w)
            sp = _stance_speed(c, skeleton, forward, stance_intervals(c, skeleton, forward, spec.get('stance_threshold_cm', 1.5)))
            trials.append((abs(sp - spec['speed_cm_s']), w, sp))
        _, w_lower, natural = min(trials)
    clip = build(float(w_lower))
    intervals = stance_intervals(clip, skeleton, forward, spec.get('stance_threshold_cm', 1.5))
    natural = _stance_speed(clip, skeleton, forward, intervals)
    speed = float(spec['speed_cm_s'])
    actor = forward * speed
    world = world_matrices(clip, skeleton)
    ramp = spec.get('plant_blend_frames', 1) / fps
    effector = spec.get('plant_effector', 'ball')
    for s, (a, b) in intervals.items():
        mid = round((a + b) / 2 * fps)
        foot = world[mid, ix['foot_' + s]]
        offset = foot[:3, :3].T @ (world[mid, ix[f'{effector}_{s}'], :3, 3] - foot[:3, 3])
        # The fixed ground point that best fits the blended stance at the planted speed.
        span = np.arange(round(a * fps), round(b * fps) + 1)
        if spec.get('hold_foot_rotation', True):
            # Flat support: the foot keeps its mid-stance orientation, so ankle and ball both stay put;
            # heel/toe roll returns in the ramp frames either side.
            _hold_rotation(clip, skeleton, ix['foot_' + s], world[mid, ix['foot_' + s], :3, :3],
                           span[0] - spec.get('plant_blend_frames', 1), span[-1] + spec.get('plant_blend_frames', 1),
                           spec.get('plant_blend_frames', 1))
            world = world_matrices(clip, skeleton)
        point = np.mean([world[f, ix[f'{effector}_{s}'], :3, 3] + actor * (f / fps) for f in span], axis=0) - actor * (mid / fps)
        # Full weight over the measured support; the ramp sits in the frames either side.
        solve_contact(clip, skeleton, {'chain': [f'thigh_{s}', f'calf_{s}', f'foot_{s}'],
                                       'interval_s': [a - ramp, b + ramp], 'offset_cm': offset.tolist(),
                                       'target_cm': (point + actor * (mid / fps)).tolist(),
                                       'actor_velocity_cm_s': actor.tolist(), 'blend_s': ramp,
                                       'sync_effectors': [f'ik_foot_{s}']})
    for track in clip['tracks'].values():
        track[-1] = track[0]
    clip.update(speed_cm_s=speed, contacts_s={s: round(v[0], 6) for s, v in intervals.items()},
                support_intervals={'space': 'cycle_seconds', 'duration_s': clip['length'],
                                   'feet': {s: {'touchdown_s': v[0], 'support_duration_s': v[1] - v[0]}
                                            for s, v in intervals.items()}},
                source=' + '.join(f"{packet['clips'][n].get('source', n)}" for n in spec['sources']),
                also_as=list(spec.get('also_as', [])), timing=None, trace_bone=None, transition=None,
                layers={'authoring': {'kind': 'phase-synchronised cycle blend', 'sources': spec['sources'],
                                      'planted_point': effector,
                                      'lower_weight': float(w_lower), 'upper_weight': spec['upper_weight'],
                                      'unplanted_stance_speed_cm_s': natural, 'planted_speed_cm_s': speed},
                        **{k: v for k, v in (slow.get('layers') or {}).items() if k in ('hands', 'twist_bones', 'footing')}})
    return clip


# ---------------------------------------------------------------- turn in place

def _two_bone(world, chain, wanted, pole):
    a, b, c = chain
    p, joint, tip = world[[a, b, c], :3, 3]
    l1, l2 = np.linalg.norm(joint - p), np.linalg.norm(tip - joint)
    distance = np.linalg.norm(wanted - p)
    if distance >= l1 + l2 - 1e-6:
        raise ValueError('turn-in-place foot target out of reach; lower the pelvis or shorten the step')
    direction = (wanted - p) / distance
    pole = pole - direction * np.dot(pole, direction)
    pole /= np.linalg.norm(pole)
    along = (l1 * l1 - l2 * l2 + distance * distance) / (2 * distance)
    knee = p + direction * along + pole * math.sqrt(max(0, l1 * l1 - along * along))

    def aim(rot, old, new):
        u, v = old / np.linalg.norm(old), new / np.linalg.norm(new)
        axis = np.cross(u, v)
        s = np.linalg.norm(axis)
        if s < 1e-12:
            return rot
        return Rotation.from_rotvec(axis / s * math.atan2(s, np.dot(u, v))).as_matrix() @ rot
    return aim(world[a, :3, :3], joint - p, knee - p), aim(world[b, :3, :3], tip - joint, wanted - knee), knee


def _segment_gap(a0, b0, a1, b1):
    """Shortest distance between 2D segments a0-a1 (one foot) and b0-b1 (the other foot)."""
    def point(p, q0, q1):
        d = q1 - q0
        t = np.clip(np.dot(p - q0, d) / max(np.dot(d, d), 1e-12), 0, 1)
        return np.linalg.norm(p - (q0 + t * d))
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if side(a0, a1, b0) * side(a0, a1, b1) < 0 and side(b0, b1, a0) * side(b0, b1, a1) < 0:
        return 0.
    return min(point(a0, b0, b1), point(a1, b0, b1), point(b0, a0, a1), point(b1, a0, a1))


def _apply_world(world, children, bone, new_world):
    """Replace a bone's world transform and carry its descendants rigidly."""
    delta = new_world @ np.linalg.inv(world[bone])
    for i in _family(children, bone):
        world[i] = delta @ world[i]


def turn_in_place(packet, skeleton, spec):
    """Idle-to-idle turn: the root carries the yaw, the feet step and stay planted between steps.

    spec: name, degrees (positive = toward the character's left), duration_s,
    fps, steps ([[side or 'lead'/'trail', start_fraction, end_fraction], ...]),
    yaw_window ([start, end] fractions), lift_cm, pelvis_dip_cm,
    pelvis_shift_cm, look_ahead_deg, stand_clip.
    """
    names, parents, ix, children = _rig(skeleton)
    stand = packet['clips'][spec.get('stand_clip', 'MM_Idle')]
    fps = spec.get('fps', stand['fps'])
    frames = int(round(spec['duration_s'] * fps)) + 1
    times = np.arange(frames) / fps
    forward, left = facing(skeleton, stand)
    to_left = -1. if np.cross(forward, left)[2] < 0 else 1.
    yaw_total = math.radians(spec['degrees']) * to_left
    lead = 'l' if spec['degrees'] > 0 else 'r'
    trail = 'r' if lead == 'l' else 'l'
    base_clip = {'fps': fps, 'frames': 1, 'tracks': {n: [stand['tracks'][n][0]] for n in names}}
    base = world_matrices(base_clip, skeleton)[0]
    y0, y1 = spec.get('yaw_window', [.1, .85])
    yaw = yaw_total * _smooth((times / times[-1] - y0) / (y1 - y0))
    # One single-axis angle per frame must be shaped (frames, 1): SciPy 1.17 reads
    # a flat (frames,) array as one rotation with `frames` axes and refuses it.
    turn = Rotation.from_euler('z', yaw[:, None])
    rz = turn.as_matrix()
    pole_local = {}
    for s in 'lr':
        thigh, calf, foot = (base[ix[f'{n}_{s}'], :3, 3] for n in ('thigh', 'calf', 'foot'))
        mid = (thigh + foot) / 2
        pole_local[s] = base[ix['foot_' + s], :3, :3].T @ ((calf - mid) / np.linalg.norm(calf - mid))
    worlds = np.repeat(base[None], frames, axis=0)
    root_track = np.zeros((frames, 7))
    root_track[:, 3:] = turn.as_quat()
    lift, dip, shift = spec.get('lift_cm', 6.), spec.get('pelvis_dip_cm', 1.5), spec.get('pelvis_shift_cm', 2.5)
    look = math.radians(spec.get('look_ahead_deg', 20.))
    spine = [(b, w) for b, w in (('spine_01', .25), ('spine_03', .25), ('neck_01', .2), ('head', .3)) if b in ix]
    ball_local = {s: np.linalg.inv(base[ix['foot_' + s]]) @ base[ix['ball_' + s]] for s in 'lr'}

    def footprint(m, s):
        return m[:2, 3], (m @ ball_local[s])[:2, 3]

    def plan(steps, between):
        """World foot schedule: planted feet stay put; a step carries the midfoot from its spot to its
        standing spot under the yaw at landing (the full turn on the foot's last step), bowing away
        from the planted foot as far as needed to keep the footprints apart."""
        feet = {s: np.repeat(base[ix['foot_' + s]][None], frames, axis=0) for s in 'lr'}
        planted = {s: np.ones(frames, bool) for s in 'lr'}
        last_end = {s: max(b for x, _, b in steps if x == s) for s in 'lr'}
        current = {s: base[ix['foot_' + s]].copy() for s in 'lr'}
        for s, a, b in sorted(steps, key=lambda x: x[1]):
            other = 'r' if s == 'l' else 'l'
            mid_local = ball_local[s][:3, 3] / 2
            land_yaw = yaw_total if b == last_end[s] else yaw_total * between
            land = np.eye(4)
            land[:3, :3] = Rotation.from_euler('z', land_yaw).as_matrix()
            target, start = land @ base[ix['foot_' + s]], current[s]
            m0, m1 = start[:3, :3] @ mid_local + start[:3, 3], target[:3, :3] @ mid_local + target[:3, 3]
            rot0 = Rotation.from_matrix(start[:3, :3])
            spin = Rotation.from_matrix(target[:3, :3] @ start[:3, :3].T).as_rotvec()
            stance = current[other]
            stance_mid = (stance[:3, :3] @ (ball_local[other][:3, 3] / 2) + stance[:3, 3])[:2]
            chord = (m0 + m1)[:2] / 2
            away = chord - stance_mid
            away /= max(np.linalg.norm(away), 1e-9)
            span = [f for f in range(frames) if times[f] > a]

            def pose(f, bow):
                u = min(1., (times[f] - a) / (b - a))
                e = float(_smooth(u))
                m = np.eye(4)
                m[:3, :3] = (Rotation.from_rotvec(spin * e) * rot0).as_matrix()
                point = m0 + (m1 - m0) * e
                point[:2] += away * bow * math.sin(math.pi * u)
                point[2] += lift * math.sin(math.pi * u) ** 2
                m[:3, 3] = point - m[:3, :3] @ mid_local
                return m, u

            def gap(bow):
                return min(_segment_gap(*footprint(pose(f, bow)[0], s), *footprint(stance, other)) if s == 'l' else
                           _segment_gap(*footprint(stance, other), *footprint(pose(f, bow)[0], s))
                           for f in span if times[f] < b)
            bow = max(np.linspace(0, spec.get('maximum_bow_cm', 15.), 16), key=lambda v: (min(gap(v), 8.), -v))
            for f in span:
                m, u = pose(f, bow)
                feet[s][f] = m
                if u < 1:
                    planted[s][f] = False
            current[s] = target
        if any((~planted['l']) & (~planted['r'])):
            raise ValueError('both feet airborne at once; separate the step windows')
        clearance = min(_segment_gap(*(feet[s][f][:2, 3] for s in 'lr'),
                                     *((feet[s][f] @ ball_local[s])[:2, 3] for s in 'lr')) for f in range(frames))
        return feet, planted, clearance

    first = spec.get('first_step', 'auto')
    options = [(lead, trail), (trail, lead)] if first == 'auto' else [(lead, trail) if first == 'lead' else (trail, lead)]
    # A foot that steps twice lands first at an intermediate share of the turn; search it with the order.
    shares = spec.get('intermediate_share', [.3, .4, .5, .6, .7])
    shares = shares if isinstance(shares, list) else [shares]
    candidates = []
    for one, two in options:
        steps = [((one if x == 'lead' else two if x == 'trail' else x), a * times[-1], b * times[-1])
                 for x, a, b in spec['steps']]
        if {x for x, _, _ in steps} != {'l', 'r'}:
            raise ValueError('a turn on the spot must move both feet')
        twice = len(steps) > len({x for x, _, _ in steps})
        for share in (shares if twice else [None]):
            candidates.append((*plan(steps, share), steps, share))
    feet, planted, clearance, steps, between = max(candidates, key=lambda c: c[2])
    if clearance < spec.get('minimum_foot_clearance_cm', 3.):
        raise ValueError(f'feet pass within {clearance:.1f} cm; adjust the steps')
    # The upper body follows the same yaw curve a little earlier (head and chest lead the turn).
    lead_yaw = yaw_total * _smooth((times / times[-1] - y0 + spec.get('look_ahead_fraction', .12)) / (y1 - y0))
    lead_yaw = np.clip(lead_yaw - yaw, -abs(look), abs(look)) * _smooth(times / (.15 * times[-1]))
    # The hips stay over the support: the feet's centroid plus the idle pelvis offset under the root yaw.
    idle_centre = (base[ix['foot_l'], :3, 3] + base[ix['foot_r'], :3, 3]) / 2
    hips = np.zeros((frames, 3))
    for f in range(frames):
        centre = (feet['l'][f][:3, 3] + feet['r'][f][:3, 3]) / 2
        hips[f] = centre + rz[f] @ (base[ix['pelvis'], :3, 3] - idle_centre) - rz[f] @ base[ix['pelvis'], :3, 3]
        hips[f, 2] = 0
    # Knees bend as needed: lower the pelvis just enough that both feet stay within reach.
    reach = spec.get('reach_fraction', .97)
    lengths = {s: np.linalg.norm(base[ix[f'calf_{s}'], :3, 3] - base[ix[f'thigh_{s}'], :3, 3])
               + np.linalg.norm(base[ix[f'foot_{s}'], :3, 3] - base[ix[f'calf_{s}'], :3, 3]) for s in 'lr'}
    need = np.zeros(frames)
    for f in range(frames):
        for s in 'lr':
            hip = rz[f] @ base[ix[f'thigh_{s}'], :3, 3] + hips[f]
            goal = feet[s][f][:3, 3]
            flat = np.linalg.norm((hip - goal)[:2])
            allowed = math.sqrt(max(0., (reach * lengths[s]) ** 2 - flat * flat))
            need[f] = max(need[f], hip[2] - goal[2] - allowed + shift)
    need = np.maximum(need - need[0], 0) * _smooth(np.minimum(times, times[-1] - times) / (.12 * times[-1]))
    window = max(1, int(round(.15 * fps)))
    padded = np.pad(need, window, mode='edge')
    need = np.array([padded[i:i + 2 * window + 1].max() for i in range(frames)])
    kernel = np.hanning(2 * window + 3)[1:-1]
    need = np.convolve(np.pad(need, window, mode='edge'), kernel / kernel.sum(), mode='valid')
    need *= _smooth(np.minimum(times, times[-1] - times) / (.1 * times[-1]))
    if need.max() > spec.get('max_pelvis_drop_cm', 8.):
        raise ValueError(f'turn needs {need.max():.1f} cm of pelvis drop; shorten the steps or the duration')
    for f in range(frames):
        w = worlds[f]
        r = np.eye(4)
        r[:3, :3] = rz[f]
        w[:] = r @ w
        pelvis = w[ix['pelvis']].copy()
        pelvis[:3, 3] += hips[f]
        pelvis[2, 3] -= need[f]
        for s, a, b in steps:
            if a < times[f] < b:
                u = math.sin(math.pi * (times[f] - a) / (b - a))
                other = 'r' if s == 'l' else 'l'
                toward = feet[other][f][:3, 3] - pelvis[:3, 3]
                toward[2] = 0
                toward /= max(np.linalg.norm(toward), 1e-9)
                pelvis[:3, 3] += toward * shift * u + np.array([0, 0, -dip * u])
                break
        _apply_world(w, children, ix['pelvis'], pelvis)
        for bone, share in spine:
            m = w[ix[bone]].copy()
            m[:3, :3] = Rotation.from_euler('z', lead_yaw[f] * share).as_matrix() @ m[:3, :3]
            _apply_world(w, children, ix[bone], m)
        for s in 'lr':
            chain = [ix[f'thigh_{s}'], ix[f'calf_{s}'], ix[f'foot_{s}']]
            target = feet[s][f]
            thigh_rot, calf_rot, _ = _two_bone(w, chain, target[:3, 3], target[:3, :3] @ pole_local[s])
            m = w[chain[0]].copy()
            m[:3, :3] = thigh_rot
            _apply_world(w, children, chain[0], m)
            m = w[chain[1]].copy()
            m[:3, :3] = calf_rot
            _apply_world(w, children, chain[1], m)
            _apply_world(w, children, chain[2], target.copy())
            if f'ik_foot_{s}' in ix:
                w[ix[f'ik_foot_{s}']] = target.copy()
    clip = {'fps': fps, 'frames': frames, 'length': times[-1], 'loop': False, 'root_motion': True, 'tracks': {}}
    _store(clip, skeleton, worlds, root_track)
    support = {}
    for s in 'lr':
        runs, start = [], None
        for f in range(frames):
            if planted[s][f] and start is None:
                start = f
            if (not planted[s][f] or f == frames - 1) and start is not None:
                end = f if planted[s][f] else f - 1
                runs.append([start / fps, end / fps])
                start = None
        support[s] = runs
    clip['reach_pelvis_drop_cm'] = float(need.max())
    clip.update(speed_cm_s=None, contacts_s=None, also_as=list(spec.get('also_as', [])), timing=None,
                trace_bone=None, transition=None,
                source=f"{stand.get('source', 'stand')} + procedural turn",
                support_intervals={'space': 'clip_seconds', 'duration_s': times[-1], 'feet': support},
                turn={'degrees': spec['degrees'], 'root_yaw_deg': math.degrees(yaw_total), 'first_foot': steps[0][0],
                      'foot_clearance_cm': clearance, 'intermediate_share': between,
                      'steps': [[s, a, b] for s, a, b in steps]},
                layers={k: v for k, v in (stand.get('layers') or {}).items() if k in ('hands', 'twist_bones')})
    return clip


# ------------------------------------------------------------------ measurement

def _root_world(clip, skeleton):
    basis = matrices(skeleton.get('armature_transform', [0, 0, 0, 0, 0, 0, 1]))
    if 'root' in clip['tracks']:
        return basis @ matrices(clip['tracks']['root'])
    return np.broadcast_to(basis, (clip['frames'], 4, 4))


def measure_clip(clip, skeleton, forward=None, stand=None):
    """Foot slide during declared support, loop seam, root yaw and start/end match to a standing pose."""
    names, _, ix, _ = _rig(skeleton)
    w = world_matrices(clip, skeleton)
    fps, frames = clip['fps'], clip['frames']
    times = np.arange(frames) / fps
    world = w.copy()
    if clip.get('speed_cm_s') and not clip.get('root_motion'):
        world[:, :, :3, 3] += (times[:, None, None] * forward * clip['speed_cm_s'])[:, :, :]
    result = {'frames': frames, 'fps': fps, 'length_s': (frames - 1) / fps, 'support': {}}
    intervals = clip.get('support_intervals') or {}
    for s in 'lr':
        info = (intervals.get('feet') or {}).get(s)
        if info is None:
            continue
        if intervals['space'] == 'cycle_seconds':
            runs = [[info['touchdown_s'], info['touchdown_s'] + info['support_duration_s']]]
        else:
            runs = info
        foot_speeds, ball_speeds = [], []
        for a, b in runs:
            f0, f1 = int(round(a * fps)), int(round(b * fps))
            if f1 <= f0:
                continue
            for bone, out in (('foot_', foot_speeds), ('ball_', ball_speeds)):
                p = world[f0:f1 + 1, ix[bone + s], :3, 3]
                out.extend((np.linalg.norm(np.diff(p, axis=0), axis=1) * fps).tolist())
        result['support'][s] = {'intervals_s': [[round(a, 4), round(b, 4)] for a, b in runs],
                                'foot_slide_cm_s': {'max': max(foot_speeds, default=0.), 'mean': float(np.mean(foot_speeds)) if foot_speeds else 0.},
                                'ball_slide_cm_s': {'max': max(ball_speeds, default=0.), 'mean': float(np.mean(ball_speeds)) if ball_speeds else 0.}}
    if clip.get('loop'):
        p = w[:, :, :3, 3]
        q = Rotation.from_matrix(w[:, :, :3, :3].reshape(-1, 3, 3)).as_quat().reshape(frames, -1, 4)
        dq = np.abs(np.sum(q[0] * q[-1], axis=1)).clip(0, 1)
        seam = np.linalg.norm((p[1] - p[0]) - (p[-1] - p[-2]), axis=1) * fps * fps
        interior = np.linalg.norm(p[2:] - 2 * p[1:-1] + p[:-2], axis=2) * fps * fps
        result['loop_seam'] = {'max_position_cm': float(np.linalg.norm(p[0] - p[-1], axis=1).max()),
                               'max_rotation_deg': float(np.degrees(2 * np.arccos(dq)).max()),
                               'seam_acceleration_cm_s2': float(seam.max()),
                               'max_interior_acceleration_cm_s2': float(interior.max()),
                               'seam_to_cycle_acceleration_ratio': float(np.max(seam / np.maximum(interior.max(axis=0), 1.)))}
    feet = w[:, [ix['foot_l'], ix['foot_r']]][:, :, :3, 3]
    balls = w[:, [ix['ball_l'], ix['ball_r']]][:, :, :3, 3]
    gap = np.array([_segment_gap(feet[f, 0, :2], feet[f, 1, :2], balls[f, 0, :2], balls[f, 1, :2]) for f in range(frames)])
    knee = {}
    for s in 'lr':
        a, b, c = (w[:, ix[f'{n}_{s}'], :3, 3] for n in ('thigh', 'calf', 'foot'))
        u, v = b - a, c - b
        cos = np.sum(u * v, axis=1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1))
        knee[s] = [float(np.degrees(np.arccos(np.clip(cos, -1, 1))).min()), float(np.degrees(np.arccos(np.clip(cos, -1, 1))).max())]
    result['feet_minimum_gap_cm'] = float(gap.min())
    result['knee_bend_deg'] = knee
    if clip.get('turn'):
        root = _root_world(clip, skeleton)
        yaw = math.degrees(Rotation.from_matrix(root[-1][:3, :3] @ root[0][:3, :3].T).as_rotvec()[2])
        result['root'] = {'yaw_deg': yaw, 'yaw_error_deg': yaw - clip['turn']['root_yaw_deg'],
                          'translation_cm': float(np.abs(np.asarray(clip['tracks']['root'])[:, :3]).max())}
    if stand is not None:
        ref = world_matrices({'fps': fps, 'frames': 1, 'tracks': {n: [stand['tracks'][n][0]] for n in names}}, skeleton)[0]
        out = {}
        for label, f in (('start', 0), ('end', frames - 1)):
            root = _root_world(clip, skeleton)[f]
            local = np.linalg.inv(root) @ w[f]
            out[label + '_cm'] = float(np.linalg.norm(local[:, :3, 3] - ref[:, :3, 3], axis=1).max())
        result['stand_match'] = out
    return result


def author_packet(packet, skeleton, profile):
    """Copy every existing clip and add the profile's cycles and turns, with measurements."""
    result = copy.deepcopy(packet)
    measurements = {}
    stand = packet['clips'][profile.get('stand_clip', 'MM_Idle')]
    forward, _ = facing(skeleton, stand)
    for spec in profile.get('cycles', []):
        if spec['name'] in result['clips']:
            raise ValueError(f"{spec['name']} already exists in the packet")
        clip = blend_cycle(packet, skeleton, spec)
        result['clips'][spec['name']] = clip
        measurements[spec['name']] = measure_clip(clip, skeleton, forward)
    for spec in profile.get('turns', []):
        if spec['name'] in result['clips']:
            raise ValueError(f"{spec['name']} already exists in the packet")
        clip = turn_in_place(packet, skeleton, spec)
        result['clips'][spec['name']] = clip
        measurements[spec['name']] = measure_clip(clip, skeleton, forward, stand)
    return result, measurements
