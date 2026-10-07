"""Optional real-Blender check: the strict rig gate takes a character's tier as its ceiling."""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')

PROFILE = {
    'profile_id': 'tier_fixture', 'root_bone': 'Bone', 'required_bones': ['Bone'],
    'expected_parents': {}, 'optional_bones': [], 'allow_unlisted_bones': False,
    'max_influences': 4, 'tri_budget': 10, 'tri_budget_waiver': None,
}


def blender(*args):
    return subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1', *map(str, args)],
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def skinned_cube(tmp_path):
    """Twelve triangles on one bone: over a flat ceiling of 10, inside any tier."""
    source = tmp_path / 'cube.blend'
    script = tmp_path / 'make.py'
    script.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.object.armature_add()
arm = bpy.context.object
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 1))
cube = bpy.context.object
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
group = cube.vertex_groups.new(name='Bone')
group.add(list(range(len(cube.data.vertices))), 1.0, 'REPLACE')
cube.modifiers.new('Skin', 'ARMATURE').object = arm
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    result = blender('--python', script)
    assert result.returncode == 0, result.stdout + result.stderr
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps(PROFILE))
    return source, profile


def gate(source, profile, report, *extra):
    return blender('--python', ROOT / 'scripts/blender/gate_rig.py', '--', source, profile, report, *extra)


def test_the_flat_ceiling_applies_without_a_tier(skinned_cube, tmp_path):
    source, profile = skinned_cube
    report = tmp_path / 'flat.json'

    result = gate(source, profile, report)

    assert result.returncode == 1, result.stdout + result.stderr
    verdict = json.loads(report.read_text())
    assert verdict['total_tris'] == 12
    assert verdict['tri_budget'] == 10
    assert verdict['tri_budget_rule']['source'] == 'skeleton_profile'
    assert any('exceeds profile budget 10' in failure for failure in verdict['failures'])


def test_a_tier_replaces_the_flat_ceiling(skinned_cube, tmp_path):
    source, profile = skinned_cube
    report = tmp_path / 'npc.json'

    result = gate(source, profile, report, '--tier', 'npc')

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = json.loads(report.read_text())
    assert verdict['ok']
    assert verdict['tri_budget'] == 20_000
    assert verdict['tri_budget_rule']['character_tier']['id'] == 'npc'
    assert '(the npc tier allows 20,000)' in result.stdout


def test_an_unknown_tier_stops_the_gate(skinned_cube, tmp_path):
    source, profile = skinned_cube
    report = tmp_path / 'unknown.json'

    result = gate(source, profile, report, '--tier', 'wizard')

    assert result.returncode != 0
    assert not report.exists()
    assert 'Unknown character tier' in result.stdout + result.stderr
