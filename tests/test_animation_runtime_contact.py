"""Runtime contact measurement takes per-character limits from data, not code."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler import animation_runtime_contact as rc

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = [0, 0, 0, 1]


def sole(gap, vertex=3, x=0.):
    return {'gap_cm': gap, 'point': [x, 0, gap], 'vertex': vertex, 'traced_samples': 4, 'valid_ground_samples': 4}


def frame(case, t, speed, step=0, gap=.5, foot_z=10., pelvis=(0, 0, 90), **extra):
    bones = {'pelvis': [*pelvis, *IDENTITY]}
    for side, y in (('l', 10), ('r', -10)):
        bones[f'thigh_{side}'] = [0, y, 90, *IDENTITY]
        bones[f'calf_{side}'] = [5, y, 50, *IDENTITY]
        bones[f'foot_{side}'] = [0, y, foot_z, *IDENTITY]
    row = {'case': case, 'time': t, 'step': step, 'input': .2 if speed else 0, 'speed_cm_s': speed,
           'falling': False, 'delta_s': 1 / 60, 'heading': 0, 'pawn': [t * speed, 0, 0, *IDENTITY],
           'bones': bones, 'soles': {'l': sole(gap), 'r': sole(gap)}, 'plant_curves': {'l': 1, 'r': 1}}
    row.update(extra)
    return row


def walk_proof(speed=120.):
    rows = [frame('walk', i / 60, 0 if i < 30 else speed, step=0 if i < 30 else 1) for i in range(120)]
    return {'error': None, 'frames': rows, 'plan': [('walk', [(.5, 0, 0), (1.45, .24, 0)])]}


def test_criteria_derive_from_walk_speed_and_reject_unknown_fields():
    limits = rc.criteria({'walk_speed_cm_s': 100})
    assert limits['support_speed_range_cm_s'] == [95, 105.5]
    assert limits['walk_exit_speed_range_cm_s'] == pytest.approx([90, 112])
    with pytest.raises(ValueError, match='unknown criteria'):
        rc.criteria({'walk_speed_cm_s': 100, 'walk_sped': 1})
    with pytest.raises(ValueError, match='declare walk_speed_cm_s'):
        rc.criteria({})
    assert rc.criteria(None, {'review_profile': {'walk_speed_cm_s': 105}})['walk_speed_cm_s'] == 105


def test_every_shipped_criteria_profile_resolves():
    for path in (ROOT / 'profiles/animation/runtime-contact').glob('*.json'):
        assert rc.criteria(json.loads(path.read_text()))['walk_speed_cm_s'] > 0


def test_walk_uses_the_declared_speed_for_steady_and_support_windows():
    proof = walk_proof(120)
    measured = rc.analyze_locomotion(proof, rc.criteria({'walk_speed_cm_s': 120}))['cases']['walk']
    assert measured['steady_walk_samples'] == 90
    assert {w['side'] for w in measured['near_flat_support_windows']} == {'l', 'r'}
    assert measured['transition_windows'][0]['input_change_s'] == pytest.approx(.5)
    elsewhere = rc.analyze_locomotion(proof, rc.criteria({'walk_speed_cm_s': 89}))['cases']['walk']
    assert elsewhere['steady_walk_samples'] == 0 and not elsewhere['near_flat_support_windows']


def test_turn_exit_state_and_early_end():
    proof = walk_proof(120)
    proof['frames'] = [dict(f, case='left_walk') for f in proof['frames']]
    proof['plan'] = [('left_walk', [(.5, 0, 0), (1.45, .24, 90)])]
    case = rc.measure_turns(proof, rc.criteria({'walk_speed_cm_s': 120}))['cases']['left_walk']
    assert case['exit_state_passed'] and case['whole_case']['minimum_gap_cm'] == .5
    proof['plan'] = [('left_walk', [(.5, 0, 0), (5., .24, 90)])]
    with pytest.raises(ValueError, match='ended early'):
        rc.measure_turns(proof, rc.criteria({'walk_speed_cm_s': 120}))


def combat_proof(lift=0.):
    rows = []
    for i in range(240):
        t = i / 60
        active = 1 <= t < 2
        rows.append(frame('combo_idle', t, 0, gap=-.2 if active else .4, foot_z=10 + (lift if active else 0),
                          combo_active=active, combo_playing=active, any_montage=t < 2.3, attacking=active,
                          section='Attack01' if active else 'None', montage_position=t if t < 2.3 else 0))
    return {'error': None, 'frames': rows, 'cases': [('combo_idle', 1, False)],
            'sole_measurement': 'all sampled vertices'}


def test_recovery_phases_follow_the_declared_window():
    measured = rc.analyze_recovery(combat_proof(), rc.criteria({'walk_speed_cm_s': 90, 'recovery_window_s': .5}))
    case = measured['cases']['combo_idle']
    assert case['phases']['active_attack']['negative_gap_observations'] == 120
    assert case['phases']['recovery']['samples'] == 30
    assert case['montage_gone_s'] == pytest.approx(2.3)
    assert '0.5 seconds' in measured['scope']


def test_combat_comparison_allows_lift_but_not_horizontal_change():
    before, after = combat_proof(), combat_proof(lift=1.5)
    result = rc.compare_combat(before, after)
    assert result['performance_preserved_except_vertical_leg_contact']
    assert result['maxima']['active_foot_lift_cm'] == pytest.approx(1.5)
    after['frames'][90]['bones']['pelvis'][0] += 1
    assert not rc.compare_combat(before, after)['performance_preserved_except_vertical_leg_contact']
    assert not rc.compare_recovery(before, after)['active_strikes_preserved']


def test_paired_captures_must_match_frame_for_frame():
    before = combat_proof()
    after = combat_proof()
    after['frames'].pop()
    with pytest.raises(ValueError, match='identical fixed-step'):
        rc.compare_turns(before, after)


def test_cli_writes_once(tmp_path):
    proof = tmp_path / 'proof.json'
    proof.write_text(json.dumps(walk_proof(120)))
    criteria = tmp_path / 'criteria.json'
    criteria.write_text(json.dumps({'schema': rc.CRITERIA_SCHEMA, 'walk_speed_cm_s': 120}))
    out = tmp_path / 'walk.json'
    command = [sys.executable, str(ROOT / 'scripts/anim/analyze_runtime_contact.py'), 'walk', str(proof), str(out),
               '--criteria', str(criteria)]
    subprocess.run(command, check=True, capture_output=True)
    assert json.loads(out.read_text())['criteria_profile']['sha256']
    assert subprocess.run(command, capture_output=True).returncode != 0
