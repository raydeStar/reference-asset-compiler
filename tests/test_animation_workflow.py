"""Adversarial contracts and physical examples for the animation workflow."""
import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler.animation_motion import (
    derive_packet, measure_packet, validate_packet, world_matrices,
)
from reference_asset_compiler.animation_workflow import (
    SCHEMA, binding, compare, derive, load_recipe, measure, package, record_review, review_summary,
)
from reference_asset_compiler.cli import main


def packet_fixture():
    # A bent two-link leg, length sqrt(2) per segment, ending at (0,0,0).
    names = ['pelvis', 'thigh', 'calf', 'foot']
    xyz = [[0, 0, 2], [0, 0, 0], [1, 0, -1], [-1, 0, -1]]
    clip = {'fps': 10, 'frames': 11, 'length': 1., 'loop': True, 'root_motion': False,
            'contacts_s': {'l': .2, 'r': .7},
            'tracks': {n: [[*p, 0, 0, 0, 1] for _ in range(11)] for n, p in zip(names, xyz)}}
    packet = {'bones': names, 'clips': {'idle': clip}, 'provenance': {}}
    skeleton = {'bones': names, 'parents': [-1, 0, 1, 2], 'units': 'cm', 'up_axis': 'Z', 'rotation': 'xyzw'}
    return packet, skeleton


@pytest.fixture
def recipe(tmp_path):
    packet, skeleton = packet_fixture()
    character = tmp_path / 'authority.blend'
    character.write_bytes(b'unchanged native authority')
    packet['provenance']['character_blend_sha256'] = binding(character)['sha256']
    skeleton['source_sha256'] = binding(character)['sha256']
    (tmp_path / 'clips.json').write_text(json.dumps(packet))
    (tmp_path / 'skeleton.json').write_text(json.dumps(skeleton))
    (tmp_path / 'license.txt').write_text('CC0-1.0 fixture motion; MIT fixture code')
    data = {'schema': SCHEMA, 'packet': binding(tmp_path/'clips.json'), 'character': binding(character),
            'pose_intent': 'A supported held stance',
            'coordinates': {'units': 'cm', 'up': 'Z', 'rotation': 'xyzw', 'space': 'UE-local'},
            'provider': {'kind': 'licensed-library', 'dependencies_complete': True, 'components': [
                {'name': 'motion', 'role': 'motion', 'license': 'CC0-1.0',
                 'artifact': binding(tmp_path/'clips.json'), 'license_evidence': binding(tmp_path/'license.txt')},
                {'name': 'adapter', 'role': 'code', 'license': 'MIT',
                 'artifact': binding(tmp_path/'license.txt'), 'license_evidence': binding(tmp_path/'license.txt')}]},
            'mapping': [], 'skeleton': binding(tmp_path/'skeleton.json'), 'operations': [],
            'benchmark': {'idle': {'contacts': [{'bone': 'foot', 'interval_s': [0, 1], 'floor_z_cm': 0}]}}}
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps(data))
    return path


def test_sign_equivalent_quaternions_have_no_loop_jump():
    packet, rig = packet_fixture()
    for track in packet['clips']['idle']['tracks'].values():
        track[-1][3:] = [0, 0, 0, -1]
    metrics = measure_packet(packet, rig, {'idle': {}})
    assert metrics['clips']['idle']['loop_angle_gap_deg'] == pytest.approx(0)


def test_world_contact_compensates_actor_motion_and_offsets():
    packet, rig = packet_fixture()
    for i, k in enumerate(packet['clips']['idle']['tracks']['pelvis']):
        k[0] -= i / 10
    case = {'idle': {'contacts': [{'bone': 'foot', 'interval_s': [0, 1],
                                  'actor_velocity_cm_s': [1, 0, 0], 'offset_cm': [0, 0, .5], 'floor_z_cm': 0}]}}
    report = measure_packet(packet, rig, case)['clips']['idle']['contacts'][0]
    assert report['drift_cm'] < 1e-12
    assert report['penetration_cm'] == 0
    case['idle']['contacts'][0]['actor_velocity_cm_s'] = [0, 0, 0]
    assert measure_packet(packet, rig, case)['clips']['idle']['contacts'][0]['drift_cm'] == pytest.approx(1)


def test_ik_moves_effector_without_stretching_or_mutating_authority():
    packet, rig = packet_fixture()
    original = copy.deepcopy(packet)
    operation = {'op': 'solve_contact', 'clip': 'idle', 'chain': ['thigh', 'calf', 'foot'],
                 'interval_s': [0, 1], 'target_cm': [.4, 0, .2], 'blend_s': 0}
    candidate = derive_packet(packet, [operation], rig)
    w = world_matrices(candidate['clips']['idle'], rig)
    assert np.max(abs(w[:, 3, :3, 3] - [.4, 0, .2])) < 1e-8
    for a, b in ((1, 2), (2, 3)):
        assert np.linalg.norm(w[:, a, :3, 3] - w[:, b, :3, 3], axis=1) == pytest.approx(np.sqrt(2))
    assert packet == original


def test_unreachable_contact_fails_without_stretching():
    packet, rig = packet_fixture()
    with pytest.raises(ValueError, match='unreachable'):
        derive_packet(packet, [{'op': 'solve_contact', 'clip': 'idle', 'chain': ['thigh', 'calf', 'foot'],
                                'interval_s': [0, 1], 'target_cm': [100, 0, 0], 'blend_s': 0}], rig)


def test_retime_maps_markers_speed_and_duration_together():
    packet, _ = packet_fixture()
    packet['clips']['idle']['speed_cm_s'] = 100
    candidate = derive_packet(packet, [{'op': 'retime', 'clip': 'idle', 'duration_factor': 2}])
    c = candidate['clips']['idle']
    assert c['frames'] == 21 and c['length'] == 2
    assert c['contacts_s'] == {'l': .4, 'r': 1.4}
    assert c['speed_cm_s'] == 50


@pytest.mark.parametrize('field,value', [('events', [{'time': .5}]), ('transition', {'to': 'walk'}), ('root_motion', True)])
def test_retime_cannot_silently_break_gameplay_contract(field, value):
    packet, _ = packet_fixture()
    packet['clips']['idle'][field] = value
    with pytest.raises(ValueError, match='retime refuses'):
        derive_packet(packet, [{'op': 'retime', 'clip': 'idle', 'duration_factor': 2}])


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_motion_is_rejected(bad):
    packet, _ = packet_fixture()
    packet['clips']['idle']['tracks']['foot'][3][0] = bad
    with pytest.raises(ValueError, match='finite'):
        validate_packet(packet)


def test_missing_bone_and_nonunit_rotation_are_rejected():
    packet, _ = packet_fixture()
    packet['clips']['idle']['tracks']['foot'][3][6] = 0
    with pytest.raises(ValueError, match='non-unit'):
        validate_packet(packet)
    del packet['clips']['idle']['tracks']['foot']
    with pytest.raises(ValueError, match='track set'):
        validate_packet(packet)


def test_stale_license_evidence_blocks_work(recipe):
    (recipe.parent/'license.txt').write_text('changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_recipe(recipe)


@pytest.mark.parametrize('license_id', ['CC-BY-NC-4.0', 'unknown', 'Llama-3', 'AnimoFlow-Community'])
def test_restricted_components_are_not_admitted(recipe, license_id):
    data = json.loads(recipe.read_text())
    data['provider']['components'][0]['license'] = license_id
    recipe.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='strict-open'):
        load_recipe(recipe)


def test_generator_requires_separate_weights_data_inventory(recipe):
    data = json.loads(recipe.read_text())
    data['provider']['kind'] = 'generator'
    recipe.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='incomplete'):
        load_recipe(recipe)


def test_derivative_is_immutable_and_source_survives(recipe):
    source = (recipe.parent/'clips.json').read_bytes()
    result = derive(recipe, recipe.parent/'candidate')
    assert result['human_approved'] is False
    assert (recipe.parent/'clips.json').read_bytes() == source
    with pytest.raises(FileExistsError):
        derive(recipe, recipe.parent/'candidate')


def test_bad_operation_never_publishes_candidate(recipe):
    data = json.loads(recipe.read_text())
    data['operations'] = [{'op': 'execute_python', 'clip': 'idle', 'code': 'anything'}]
    recipe.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unsupported'):
        derive(recipe, recipe.parent/'candidate')
    assert not (recipe.parent/'candidate').exists()


def test_metrics_compare_hash_bound_same_conditions(recipe):
    a, b, result = [recipe.parent/n for n in ('a.json', 'b.json', 'comparison.json')]
    measure(recipe, a)
    derive(recipe, recipe.parent/'candidate')
    measure(recipe, b, recipe.parent/'candidate/clips.json')
    report = compare(a, b, result)
    assert report['winner'] is None
    assert report['deltas_candidate_minus_baseline']['idle']['loop_position_gap_cm'] == 0
    (recipe.parent/'candidate/clips.json').write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        compare(a, b, recipe.parent/'invalid.json')


def test_review_rate_does_not_treat_pending_as_accepted(recipe):
    target = recipe.parent/'review.json'
    record_review(recipe.parent/'clips.json', 'pending', '', 'Awaiting owner', [], 3, target)
    summary = review_summary([target])
    assert summary['acceptance_rate'] is None
    assert summary['minutes_per_accepted_clip'] is None
    assert summary['pending'] == 1
    with pytest.raises(ValueError, match='one review'):
        review_summary([target, target])


def test_agent_cannot_record_human_acceptance(recipe):
    with pytest.raises(ValueError, match='human reviewer'):
        record_review(recipe.parent/'clips.json', 'accepted', 'codex', 'Looks fine', [recipe], 0,
                      recipe.parent/'review.json')


def test_package_includes_licenses_and_does_not_promote(recipe):
    output = recipe.parent/'package'
    result = package(recipe, [recipe.parent/'clips.json'], output)
    assert (output/'license-0.txt').is_file()
    assert result['production_ready'] is False


def test_cli_rejects_stale_recipe_without_writing(recipe, capsys):
    (recipe.parent/'authority.blend').write_bytes(b'changed')
    assert main(['animation', 'preflight', str(recipe)]) == 2
    assert 'hash mismatch' in capsys.readouterr().err


def test_root_track_cannot_evade_retime_guard():
    packet, _ = packet_fixture()
    packet['clips']['idle']['tracks']['root'] = [[i, 0, 0, 0, 0, 0, 1] for i in range(11)]
    with pytest.raises(ValueError, match='retime refuses'):
        derive_packet(packet, [{'op': 'retime', 'clip': 'idle', 'duration_factor': 2}])


def test_duration_nan_cannot_evade_validation():
    packet, _ = packet_fixture()
    packet['clips']['idle']['length'] = float('nan')
    with pytest.raises(ValueError, match='duration'):
        validate_packet(packet)


def test_review_tracks_usable_clips_and_failed_cleanup(recipe):
    source = recipe.parent / 'clips.json'
    packet = json.loads(source.read_text())
    packet['clips']['walk'] = copy.deepcopy(packet['clips']['idle'])
    source.write_text(json.dumps(packet))
    a, b = recipe.parent / 'accepted.json', recipe.parent / 'rejected.json'
    record_review(source, 'accepted', 'Test human', 'Explicit fixture review', [recipe], 3, a, ['idle'])
    record_review(source, 'rejected', 'Test human', 'Explicit fixture rejection', [recipe], 2, b, ['walk'])
    summary = review_summary([a, b])
    assert summary['acceptance_rate'] == .5
    assert summary['minutes_per_accepted_clip'] == 5
    assert summary['accepted_clips'] == 1


def test_package_refuses_reserved_name_before_writing(recipe):
    with pytest.raises(ValueError, match='reserved'):
        package(recipe, [recipe], recipe.parent / 'invalid-package')
    assert not (recipe.parent / 'invalid-package').exists()


def test_contact_solver_keeps_existing_ik_target_with_foot():
    packet, rig = packet_fixture()
    packet['bones'].append('ik_foot')
    rig['parents'].append(0)
    packet['clips']['idle']['tracks']['ik_foot'] = [[0, 0, -2, 0, 0, 0, 1] for _ in range(11)]
    op = {'op': 'solve_contact', 'clip': 'idle', 'chain': ['thigh', 'calf', 'foot'],
          'interval_s': [0, 1], 'target_cm': [.4, 0, .2], 'blend_s': 0}
    with pytest.raises(ValueError, match='sync_effectors'):
        derive_packet(packet, [op], rig)
    candidate = derive_packet(packet, [dict(op, sync_effectors=['ik_foot'])], rig)
    world = world_matrices(candidate['clips']['idle'], rig)
    assert np.max(abs(world[:, 4] - world[:, 3])) < 1e-8
