"""The optional engine adapter must bind samples and keep reach compensation opt-in."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setitem(sys.modules, 'unreal', types.ModuleType('unreal'))
    path = Path(__file__).resolve().parents[1] / 'scripts/ue5/configure_rac_contact.py'
    spec = importlib.util.spec_from_file_location('contact_profile_test_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile(tmp_path, **changes):
    probe = {'source_sha256': 'measured-mesh', 'sides': {
        s: [{'influences': [{'bone': 'foot_' + s, 'weight': 1, 'point_cm': [0, 0, 0]}]}]
        for s in 'lr'}}
    probe_path = tmp_path / 'probe.json'
    probe_path.write_text(json.dumps(probe))
    value = {'schema': 'rac.unreal-contact-profile.v1', 'sample_source_sha256': 'measured-mesh',
             'probe': {'path': probe_path.name, 'sha256': hashlib.sha256(probe_path.read_bytes()).hexdigest()},
             'chains': {s: [n + s for n in ['thigh_', 'calf_', 'foot_', 'ik_foot_']] for s in 'lr'},
             'clearance_cm': .4, 'max_correction_cm': 12, 'combat_max_correction_cm': 3,
             'release_time_s': .06, **changes}
    path = tmp_path / 'profile.json'
    path.write_text(json.dumps(value))
    return path


def test_pelvis_compensation_is_opt_in(adapter, tmp_path):
    spec, _ = adapter.read_spec(profile(tmp_path))
    assert spec['maximum_pelvis_drop_cm'] == 0
    assert spec['maximum_plant_offset_cm'] == 15


@pytest.mark.parametrize('field,value', [('maximum_pelvis_drop_cm', 8.01),
                                      ('maximum_plant_offset_cm', 50.01),
                                      ('maximum_plant_offset_cm', -1),
                                      ('max_correction_cm', float('nan'))])
def test_reach_limits_are_finite_and_bounded(adapter, tmp_path, field, value):
    with pytest.raises(ValueError, match='out of range'):
        adapter.read_spec(profile(tmp_path, **{field: value}))


def test_samples_from_another_mesh_are_rejected(adapter, tmp_path):
    with pytest.raises(ValueError, match='another declared source mesh'):
        adapter.read_spec(profile(tmp_path, sample_source_sha256='different-mesh'))


def test_defaults_reproduce_the_original_constants(adapter, tmp_path):
    spec, _ = adapter.read_spec(profile(tmp_path))
    assert (spec['action_slot'], spec['pelvis_bone'], spec['maximum_lock_speed_cm_s']) == ('DefaultSlot', 'pelvis', 180)
    assert (spec['lock_acquire_weight'], spec['lock_release_weight']) == (.65, .5)
    assert spec['terrain'] == {'channel': 'ECC_VISIBILITY', 'trace_up_cm': 45, 'trace_down_cm': 180,
                               'minimum_ground_normal_z': .5, 'inner_grid_spacing_cm': 7.5,
                               'maximum_predicted_travel_cm': 15}


def test_every_runtime_constant_is_data(adapter, tmp_path):
    spec, _ = adapter.read_spec(profile(tmp_path, action_slot='UpperBody', pelvis_bone='hips',
        maximum_lock_speed_cm_s=240, lock_acquire_weight=.8, lock_release_weight=.4,
        terrain={'channel': 'ECC_WORLD_STATIC', 'trace_down_cm': 90}))
    assert spec['action_slot'] == 'UpperBody' and spec['pelvis_bone'] == 'hips'
    assert spec['terrain']['channel'] == 'ECC_WORLD_STATIC' and spec['terrain']['trace_down_cm'] == 90
    assert spec['terrain']['trace_up_cm'] == 45


@pytest.mark.parametrize('changes,message', [
    ({'lock_acquire_weight': .4, 'lock_release_weight': .6}, 'must not exceed'),
    ({'maximum_lock_speed_cm_s': True}, 'out of range'),
    ({'terrain': {'trace_down_cm': -1}}, 'out of range'),
    ({'terrain': {'traceDown': 10}}, 'unknown terrain field'),
    ({'action_slot': ''}, 'must be names')])
def test_invalid_runtime_fields_fail(adapter, tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        adapter.read_spec(profile(tmp_path, **changes))
