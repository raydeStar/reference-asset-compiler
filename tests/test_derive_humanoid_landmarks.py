"""Optional real-Blender check: derive_humanoid_landmarks.py without its overlays.

A one-shot build of a new character derives its rig landmarks from the proxy it
has just exported. The overlays render with EEVEE, which needs a GPU, so a CPU
build passes --no-overlays. The fixture is a capsule humanoid in T-pose
(torso, head, legs, arms), 1.8 m tall, standing on z=0.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')


def blender(*args):
    result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1', *map(str, args)],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope='module')
def humanoid(tmp_path_factory):
    folder = tmp_path_factory.mktemp('humanoid')
    mesh = folder / 'humanoid.fbx'
    script = folder / 'make.py'
    script.write_text(f'''
import bpy, math
import numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
verts, faces = [], []

def tube(start, end, radius, step=0.01, around=12):
    """Closed-ring tube from start to end, a ring every `step` metres."""
    start, end = np.array(start, float), np.array(end, float)
    axis = (end - start) / np.linalg.norm(end - start)
    u = np.cross(axis, [0, 1, 0] if abs(axis[1]) < 0.9 else [1, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    rings = int(np.linalg.norm(end - start) / step) + 1
    base = len(verts)
    for r in range(rings):
        centre = start + (end - start) * r / (rings - 1)
        for k in range(around):
            a = 2 * math.pi * k / around
            verts.append(tuple(centre + radius * (math.cos(a) * u + math.sin(a) * v)))
    for r in range(rings - 1):
        for k in range(around):
            a, b = base + r * around + k, base + r * around + (k + 1) % around
            faces.append((a, b, b + around, a + around))

tube((0, 0, 0.80), (0, 0, 1.50), 0.15)          # torso
tube((0, 0, 1.50), (0, 0, 1.80), 0.09)          # neck and head
for x in (0.10, -0.10):
    tube((x, 0, 0.0), (x, 0, 0.85), 0.06)       # legs
    tube((x, -0.02, 0.03), (x, -0.20, 0.03), 0.03)  # feet on the floor, toes to -y (front)
for sign in (1, -1):
    tube((sign * 0.16, 0, 1.42), (sign * 0.85, 0, 1.42), 0.04)  # T-pose arms
data = bpy.data.meshes.new('Humanoid')
data.from_pydata(verts, [], faces)
ob = bpy.data.objects.new('Humanoid', data)
bpy.context.scene.collection.objects.link(ob)
bpy.ops.export_scene.fbx(filepath={str(mesh)!r}, use_selection=False, add_leaf_bones=False)
''')
    blender('--python', script)
    return mesh


SKELETON = ROOT / 'profiles/skeletons/ue5_manny.json'


@pytest.fixture(scope='module')
def derived(humanoid, tmp_path_factory):
    out = tmp_path_factory.mktemp('derive') / 'derived'
    log = blender('--python', ROOT / 'scripts/blender/derive_humanoid_landmarks.py', '--', humanoid, out,
                  '--profile', SKELETON, '--no-overlays')
    return out, log


def test_no_overlays_writes_the_landmarks_and_renders_nothing(humanoid, derived):
    out, log = derived
    assert 'overlays=skipped' in log
    assert sorted(p.name for p in out.iterdir()) == ['humanoid-landmarks.json']
    landmarks = json.loads((out / 'humanoid-landmarks.json').read_text(encoding='utf-8'))
    assert 'overlay_sha256' not in landmarks
    assert landmarks['skeleton_profile'] == 'ue5_manny'
    assert landmarks['payload_fbx'] == str(humanoid.resolve())
    assert landmarks['review_status'] == 'derived_pending_overlay_review'
    profile = json.loads(SKELETON.read_text(encoding='utf-8-sig'))
    assert set(profile['required_bones']) <= set(landmarks['bones'])
    assert landmarks['height_m'] == pytest.approx(1.8, abs=0.01)
    # Measured, not template: the legs stand at x = +-0.10 m and the hands reach out along the arms.
    assert landmarks['joints']['calf_l'][0] == pytest.approx(0.10, abs=0.01)
    assert landmarks['joints']['calf_r'][0] == pytest.approx(-0.10, abs=0.01)
    assert landmarks['joints']['hand_l'][0] > 0.6 and landmarks['joints']['hand_r'][0] < -0.6


def test_rig_from_landmarks_takes_the_derived_landmarks(humanoid, derived, tmp_path):
    """The rebuild runner's next stage, on the derived JSON as the runner passes it."""
    out, _ = derived
    blender('--python', ROOT / 'scripts/blender/rig_from_landmarks.py', '--', humanoid,
            out / 'humanoid-landmarks.json', SKELETON, tmp_path / 'rigged.fbx', tmp_path / 'rig-report.json')
    report = json.loads((tmp_path / 'rig-report.json').read_text(encoding='utf-8'))
    landmarks = json.loads((out / 'humanoid-landmarks.json').read_text(encoding='utf-8'))
    assert set(report['bones']) == set(landmarks['bones']) - {'root'}  # root is the armature object
    assert report['geometry_unchanged'] and (tmp_path / 'rigged.fbx').is_file()
