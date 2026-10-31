# SPDX-License-Identifier: MIT
"""Measure runtime contact proofs: evaluated game poses plus traced sole gaps.

A proof is the JSON an engine probe writes (see docs/ANIMATION_CONTACT_TOOLS.md):
``frames`` rows carry ``case``, ``time``, ``speed_cm_s``, component-space ``bones``
as ``[x, y, z, qx, qy, qz, qw]`` and per-side ``soles`` gaps. Per-character speeds
and windows come from a criteria profile, never from this module.
"""
import numpy as np
from scipy.spatial.transform import Rotation

CRITERIA_SCHEMA = 'rac.runtime-contact-criteria.v1'
LEG_PREFIXES = ('thigh_', 'calf_', 'foot_', 'ball_')
LEG_TARGETS = ('ik_foot_l', 'ik_foot_r')
SUPPORT_WINDOW = {'angular_speed_max_deg_s': 18, 'ankle_vertical_speed_max_cm_s': 8,
                  'sole_gap_range_cm': [-.5, 2.5], 'minimum_window_s': .10, 'minimum_samples': 4,
                  'same_sampled_surface_vertex': True}


def criteria(profile=None, proof=None):
    """Resolve measurement criteria; derived defaults follow the declared walk speed."""
    profile = dict(profile or {})
    if profile.pop('schema', CRITERIA_SCHEMA) != CRITERIA_SCHEMA:
        raise ValueError('unsupported runtime-contact criteria')
    profile.pop('asset', None)
    profile.pop('note', None)
    speed = profile.get('walk_speed_cm_s')
    if speed is None and proof:
        speed = (proof.get('review_profile') or {}).get('walk_speed_cm_s')
    if speed is None:
        raise ValueError('declare walk_speed_cm_s in the criteria (or the proof review profile)')
    speed = float(speed)
    if not 10 <= speed <= 1000:
        raise ValueError('walk_speed_cm_s out of range')
    resolved = {'walk_speed_cm_s': speed, 'steady_speed_tolerance_cm_s': 1.,
                'steady_window_s': None,
                'support_speed_range_cm_s': [speed * .95, speed * 1.055],
                'walk_exit_speed_range_cm_s': [speed * .9, speed * 1.12],
                'idle_exit_speed_max_cm_s': 1.,
                'recovery_window_s': .6, 'settled_after_s': None}
    unknown = set(profile) - set(resolved)
    if unknown:
        raise ValueError(f'unknown criteria: {sorted(unknown)}')
    resolved.update(profile)
    return resolved


def _angle(a, b):
    return float(np.degrees((Rotation.from_quat(a).inv() * Rotation.from_quat(b)).magnitude()))


def _distance(a, b):
    return float(np.linalg.norm(np.array(a[:3]) - b[:3]))


def _leg_bone(name):
    return name.startswith(LEG_PREFIXES) or name in LEG_TARGETS


def _complete(proof):
    if proof.get('error') or not proof.get('frames'):
        raise ValueError('Runtime capture must be complete and error-free')


def _gaps(observations):
    return [o['gap_cm'] for o in observations if o['gap_cm'] is not None]


def _whole_case(rows):
    observations = [f['soles'][s] for f in rows for s in 'lr']
    gaps = _gaps(observations)
    return {'minimum_gap_cm': min(gaps), 'negative_foot_observations': sum(g < 0 for g in gaps),
            'traced_vertices': sum(o['traced_samples'] for o in observations),
            'valid_ground_hits': sum(o['valid_ground_samples'] for o in observations),
            'minimum_trace_coverage': min(o['valid_ground_samples'] / o['traced_samples'] for o in observations)}


def analyze_locomotion(proof, limits):
    """Walk poses, knee bend, sole gaps, near-flat support windows and pelvis steps per case."""
    _complete(proof)
    speed, tolerance = limits['walk_speed_cm_s'], limits['steady_speed_tolerance_cm_s']
    window = limits['steady_window_s']
    low, high = limits['support_speed_range_cm_s']
    gap_low, gap_high = SUPPORT_WINDOW['sole_gap_range_cm']
    cases = {}
    for name in dict.fromkeys(f['case'] for f in proof['frames']):
        rows = [f for f in proof['frames'] if f['case'] == name]
        steady = [f for f in rows if f['input'] > 0 and abs(f['speed_cm_s'] - speed) < tolerance
                  and (window is None or window[0] < f['time'] < window[1])]
        summary = {'samples': len(rows), 'falling_samples': sum(f['falling'] for f in rows),
                   'max_speed_cm_s': max(f['speed_cm_s'] for f in rows), 'steady_walk_samples': len(steady)}
        summary['knee_bend_deg'] = {}
        for side in 'lr':
            values = []
            for f in steady:
                a, b, c = [np.array(f['bones'][n + '_' + side][:3]) for n in ['thigh', 'calf', 'foot']]
                u, v = b - a, c - b
                values.append(float(np.degrees(np.arccos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1)))))
            summary['knee_bend_deg'][side] = {'min': min(values), 'max': max(values)} if values else None
        summary['sole_gap_cm'] = {s: {
            'min': min(f['soles'][s]['gap_cm'] for f in rows if f['soles'][s]['gap_cm'] is not None),
            'max': max(f['soles'][s]['gap_cm'] for f in rows if f['soles'][s]['gap_cm'] is not None),
            'below_minus_05cm_samples': sum(f['soles'][s]['gap_cm'] is not None and f['soles'][s]['gap_cm'] < -.5
                                            for f in rows)} for s in 'lr'}
        # Infer only near-flat support windows. Changing heel/toe pivots are excluded;
        # thresholds and coverage are reported, so a short window cannot impersonate a whole gait.
        windows = []
        for side in 'lr':
            current = []

            def close():
                if (len(current) >= SUPPORT_WINDOW['minimum_samples']
                        and current[-1]['time'] - current[0]['time'] >= SUPPORT_WINDOW['minimum_window_s']):
                    xyz = np.array([f['soles'][side]['point'][:2] for f in current])
                    found = {'side': side, 'start_s': current[0]['time'], 'end_s': current[-1]['time'],
                             'samples': len(current),
                             'max_displacement_cm': float(np.max(np.linalg.norm(xyz - xyz[0], axis=1)))}
                    if all('plant_curves' in f for f in current):
                        values = [f['plant_curves'][side] for f in current]
                        found['plant_curve_range'] = [min(values), max(values)]
                        found['entire_window_declared_flat_support'] = min(values) >= .9
                    windows.append(found)
                current.clear()
            for a, b in zip(rows, rows[1:]):
                dt = b['time'] - a['time']
                angular = _angle(a['bones']['foot_' + side][3:], b['bones']['foot_' + side][3:]) / dt
                vertical = abs(b['bones']['foot_' + side][2] - a['bones']['foot_' + side][2]) / dt
                gaps = [f['soles'][side]['gap_cm'] for f in (a, b)]
                good = (a['input'] > 0 and low < a['speed_cm_s'] < high and low < b['speed_cm_s'] < high
                        and all(g is not None and gap_low <= g <= gap_high for g in gaps)
                        and angular < SUPPORT_WINDOW['angular_speed_max_deg_s']
                        and vertical < SUPPORT_WINDOW['ankle_vertical_speed_max_cm_s']
                        and a['soles'][side]['vertex'] == b['soles'][side]['vertex'])
                if good:
                    if not current:
                        current.append(a)
                    current.append(b)
                else:
                    close()
            close()
        summary['near_flat_support_windows'] = windows
        changes = [rows[i]['time'] for i in range(1, len(rows)) if rows[i]['step'] != rows[i - 1]['step']]
        transition = []
        for moment in changes:
            pairs = [(a, b) for a, b in zip(rows, rows[1:]) if abs(b['time'] - moment) < .25]
            movement = [_distance(b['bones']['pelvis'], a['bones']['pelvis']) for a, b in pairs]
            transition.append({'input_change_s': moment, 'max_pelvis_step_cm': max(movement, default=0),
                               'observed_max_dt_s': max((b['time'] - a['time'] for a, b in pairs), default=0)})
        summary['transition_windows'] = transition
        cases[name] = summary
    return {'cases': cases, 'criteria': limits, 'support_window_definition': SUPPORT_WINDOW,
            'scope': 'Sampled evaluated game poses and collision at this map location. Flat-support windows are inferred subsets, not continuous or all-terrain proof.'}


def measure_turns(proof, limits):
    """Locomotion analysis plus exit state, whole-case contact and exit foot steps per planned turn."""
    result = analyze_locomotion(proof, limits)
    plans = dict(proof['plan'])
    walk_low, walk_high = limits['walk_exit_speed_range_cm_s']
    for name, case in result['cases'].items():
        rows = [f for f in proof['frames'] if f['case'] == name]
        if rows[-1]['time'] < sum(s[0] for s in plans[name]) - 1e-4:
            raise ValueError(f'case ended early: {name}')
        end_speed = rows[-1]['speed_cm_s']
        case['end_speed_cm_s'] = end_speed
        case['exit_state_passed'] = (walk_low < end_speed < walk_high if name.endswith('_walk')
                                     else end_speed < limits['idle_exit_speed_max_cm_s'])
        case['whole_case'] = _whole_case(rows)
        exit_start = sum(s[0] for s in plans[name][:-1])
        case['exit_start_s'] = exit_start
        case['exit_minimum_gap_cm'] = min(f['soles'][s]['gap_cm'] for f in rows for s in 'lr'
                                          if f['time'] >= exit_start and f['soles'][s]['gap_cm'] is not None)
        # Component-space foot jumps complement the unchanged pelvis/path checks.
        case['exit_maximum_foot_step_cm'] = {s: max(_distance(b['bones']['foot_' + s], a['bones']['foot_' + s])
            for a, b in zip(rows, rows[1:]) if exit_start - .2 <= b['time'] <= exit_start + .6) for s in 'lr'}
    result['scope'] = 'All retained sole vertices independently traced on tested terrain; finite samples and ray misses do not establish continuous contact.'
    return result


def analyze_recovery(proof, limits):
    """Attack recovery phases: active strike, montage blend-out, recovery window and settled tail."""
    _complete(proof)
    window, settled = limits['recovery_window_s'], limits['settled_after_s']
    cases = {}
    for name, swings, walking in proof['cases']:
        rows = [r for r in proof['frames'] if r['case'] == name]
        attacking = [r for r in rows if r['combo_active']]
        if not attacking:
            raise ValueError(f'no active attack frames: {name}')
        end = attacking[-1]['time']
        groups = {'active_attack': attacking,
                  'blend_out': [r for r in rows if r['any_montage'] and not r['combo_active']],
                  'recovery': [r for r in rows if end < r['time'] <= end + window],
                  'settled': [r for r in rows if r['time'] >= (end + window if settled is None else settled)]}
        phases = {}
        for phase, frames in groups.items():
            gaps = [r['soles'][s]['gap_cm'] for r in frames for s in 'lr' if r['soles'][s]['gap_cm'] is not None]
            phases[phase] = {'samples': len(frames), 'minimum_gap_cm': min(gaps) if gaps else None,
                             'negative_gap_observations': sum(g < 0 for g in gaps),
                             'below_minus_05cm_observations': sum(g < -.5 for g in gaps)}
        pairs = [(a, b) for a, b in zip(rows, rows[1:]) if end - .1 <= b['time'] <= end + window]
        # Component-space changes exclude intended pawn travel, but include authored pose motion.
        changes = {bone: max(_distance(b['bones'][bone], a['bones'][bone]) for a, b in pairs)
                   for bone in ['pelvis', 'foot_l', 'foot_r']}
        cases[name] = {'expected_swings': swings, 'resume_walking': walking, 'samples': len(rows),
            'sections': sorted({r['section'] for r in rows if r['section'] not in ('None', '')}),
            'last_active_s': end,
            'montage_gone_s': next(r['time'] for r in rows if r['time'] > end and not r['any_montage']),
            'end_speed_cm_s': rows[-1]['speed_cm_s'], 'phases': phases,
            'maximum_recovery_component_step_cm': changes,
            'observed_delta_s_range': [min(r['delta_s'] for r in rows), max(r['delta_s'] for r in rows)]}
    return {'cases': cases, 'criteria': limits,
            'scope': f'Sampled boot vertices, actual map collision and finite frame coverage. Recovery is the {window} seconds after the final active attack frame. Not continuous collision, performance or human acceptance proof.'}


def measure_combat(proof, limits):
    """Recovery analysis plus whole-case and per-strike sole contact."""
    result = analyze_recovery(proof, limits)
    result['sole_measurement'] = proof['sole_measurement']
    for name, case in result['cases'].items():
        rows = [f for f in proof['frames'] if f['case'] == name]
        case['whole_case'] = _whole_case(rows)
        case['strikes'] = {}
        for section in case['sections']:
            frames = [f for f in rows if f['combo_active'] and f['section'] == section]
            gaps = [f['soles'][s]['gap_cm'] for f in frames for s in 'lr' if f['soles'][s]['gap_cm'] is not None]
            case['strikes'][section] = {'frames': len(frames), 'minimum_gap_cm': min(gaps),
                'negative_foot_observations': sum(g < 0 for g in gaps),
                'minimum_trace_coverage': min(f['soles'][s]['valid_ground_samples'] / f['soles'][s]['traced_samples']
                                              for f in frames for s in 'lr')}
    return result


def _paired(before, after):
    if before.get('error') is not None or after.get('error') is not None:
        raise ValueError('both captures must be error-free')
    old = {(f['case'], round(f['time'], 6)): f for f in before['frames']}
    if len(old) != len(after['frames']):
        raise ValueError('paired captures need identical fixed-step frames')
    return old


def compare_turns(before, after):
    """Paired locomotion runs: only leg chains may change; state, path and the rest of the body may not."""
    old = _paired(before, after)
    maximum = {'unaffected_position_cm': 0., 'unaffected_rotation_deg': 0., 'pawn_position_cm': 0., 'foot_rotation_deg': 0.}
    mismatches = []
    for f in after['frames']:
        b = old[(f['case'], round(f['time'], 6))]
        for key in ('step', 'input', 'heading', 'falling', 'combo_active', 'cycle_start', 'transition_time'):
            if abs(float(f[key]) - float(b[key])) > 1e-5:
                mismatches.append({'case': f['case'], 'time': f['time'], 'field': key})
        maximum['pawn_position_cm'] = max(maximum['pawn_position_cm'], _distance(f['pawn'], b['pawn']))
        for bone, pose in f['bones'].items():
            other = b['bones'][bone]
            angle = _angle(other[3:], pose[3:])
            if bone in ('foot_l', 'foot_r'):
                maximum['foot_rotation_deg'] = max(maximum['foot_rotation_deg'], angle)
            if _leg_bone(bone):
                continue
            maximum['unaffected_position_cm'] = max(maximum['unaffected_position_cm'], _distance(pose, other))
            maximum['unaffected_rotation_deg'] = max(maximum['unaffected_rotation_deg'], angle)
    return {'frames_compared': len(old), 'maxima': maximum, 'state_mismatches': mismatches,
            'unaffected_performance_preserved': not mismatches and all(v < .001 for v in maximum.values())}


def compare_combat(before, after):
    """Paired combat runs: active feet may rise but keep horizontal travel and orientation."""
    old = _paired(before, after)
    maxima = dict(unaffected_position_cm=0., unaffected_rotation_deg=0., pawn_position_cm=0.,
                  active_foot_xy_cm=0., active_foot_rotation_deg=0., active_foot_lift_cm=0.,
                  active_foot_lowering_cm=0., montage_time_s=0.)
    changes, per_case, count, previous = [], {}, 0, None
    for f in after['frames']:
        b = old[(f['case'], round(f['time'], 6))]
        for key in ['section', 'combo_active', 'combo_playing', 'any_montage', 'attacking', 'falling', 'input']:
            if f[key] != b[key]:
                changes.append({'case': f['case'], 'time': f['time'], 'field': key})
        maxima['pawn_position_cm'] = max(maxima['pawn_position_cm'], _distance(f['pawn'], b['pawn']))
        maxima['montage_time_s'] = max(maxima['montage_time_s'], abs(f['montage_position'] - b['montage_position']))
        for bone, pose in f['bones'].items():
            if _leg_bone(bone):
                continue
            other = b['bones'][bone]
            maxima['unaffected_position_cm'] = max(maxima['unaffected_position_cm'], _distance(pose, other))
            maxima['unaffected_rotation_deg'] = max(maxima['unaffected_rotation_deg'], _angle(other[3:], pose[3:]))
        if f['combo_active'] and previous and previous['case'] == f['case'] and previous['combo_active']:
            count += 1
            per_case[f['case']] = per_case.get(f['case'], 0) + 1
            for side in 'lr':
                a, z = f['bones']['foot_' + side], b['bones']['foot_' + side]
                maxima['active_foot_xy_cm'] = max(maxima['active_foot_xy_cm'], float(np.linalg.norm(np.array(a[:2]) - z[:2])))
                maxima['active_foot_rotation_deg'] = max(maxima['active_foot_rotation_deg'], _angle(z[3:], a[3:]))
                maxima['active_foot_lift_cm'] = max(maxima['active_foot_lift_cm'], a[2] - z[2])
                maxima['active_foot_lowering_cm'] = min(maxima['active_foot_lowering_cm'], a[2] - z[2])
        previous = f
    passed = (not changes and maxima['pawn_position_cm'] < .001 and maxima['montage_time_s'] < 1e-6
              and maxima['unaffected_position_cm'] < .001 and maxima['unaffected_rotation_deg'] < .001
              and maxima['active_foot_xy_cm'] < .001 and maxima['active_foot_rotation_deg'] < .001
              and maxima['active_foot_lowering_cm'] > -.001)
    return {'maxima': maxima, 'state_mismatches': changes, 'active_frames_compared': count,
            'per_case_frames': per_case, 'performance_preserved_except_vertical_leg_contact': passed,
            'scope': 'Paired fixed-step game poses. Upper body, pelvis, coat, hand targets, path and timing are preserved; active feet may rise but must retain horizontal trajectory and orientation. Input-onset frames are excluded from active-foot comparison.'}


def compare_recovery(before, after):
    """Paired recovery runs: active strikes must be untouched (input-onset frames excluded)."""
    index = _paired(before, after)
    maximum_position = maximum_angle = maximum_pawn = 0.
    checked, state_mismatches, previous = 0, [], None
    for row in after['frames']:
        old = index[(row['case'], round(row['time'], 6))]
        for key in ['combo_active', 'combo_playing', 'any_montage', 'section', 'attacking']:
            if old[key] != row[key]:
                state_mismatches.append({'case': row['case'], 'time': row['time'], 'field': key})
        maximum_pawn = max(maximum_pawn, _distance(row['pawn'], old['pawn']))
        # Input is submitted after pose evaluation; skip the first frame that activates a montage.
        if row['combo_active'] and previous and previous['case'] == row['case'] and previous['combo_active']:
            for name, pose in row['bones'].items():
                other = old['bones'][name]
                maximum_position = max(maximum_position, _distance(pose, other))
                maximum_angle = max(maximum_angle, _angle(other[3:], pose[3:]))
            checked += 1
        previous = row
    return {'active_pose_frames_compared': checked, 'active_pose_max_position_difference_cm': maximum_position,
        'active_pose_max_rotation_difference_deg': maximum_angle, 'maximum_pawn_path_difference_cm': maximum_pawn,
        'montage_state_mismatches': state_mismatches,
        'active_strikes_preserved': maximum_position < .01 and maximum_angle < .01 and not state_mismatches,
        'scope': 'Paired game runs at identical simulation rate. Active-strike comparison excludes input-onset frames; no timing, movement-path or combat-state change is intended.'}
