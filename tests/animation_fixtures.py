"""Shared animation-workflow fixtures: a bent two-link leg packet and its bound recipe."""
import json

from reference_asset_compiler.animation_workflow import SCHEMA, binding


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


def write_recipe(tmp_path):
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
