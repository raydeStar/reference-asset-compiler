"""Optional real-Blender check: a generated body scan becomes the rebuild's body acquisition.

The fixture is a figure built the way a generator delivers one: a GLB, Y-up,
two metres tall and (nearly) centred, in several pieces under a scaled parent.
Its collar is tilted, lower in front and rising at the back above the cut, so
a single horizontal plane would either chop the collar or leave neck skin in
front. The stage must take the head and the neck column off above the cut and
keep the collar.
"""
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'scripts/blender/prepare_body_scan.py'
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')

HEIGHT = 1.8
CUT = 1.52              # floor space: metres above the feet
NECK = (0.0, 0.01, 0.055)  # centre x, y and radius
COLLAR_RADIUS, COLLAR_TILT_DEG, COLLAR_Z = 0.09, 25.0, 1.50
COLLAR_BACK_TOP = COLLAR_Z + COLLAR_RADIUS * math.sin(math.radians(COLLAR_TILT_DEG)) \
    + 0.015 * math.cos(math.radians(COLLAR_TILT_DEG))


def blender(*args):
    result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1', *map(str, args)],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope='module')
def scan(tmp_path_factory):
    folder = tmp_path_factory.mktemp('scan')
    source = folder / 'body.glb'
    script = folder / 'make.py'
    # Built at the final size in floor space, then shifted to centred space; the
    # parent empty scales it to two metres and nudges it 1 cm up, as a
    # generator's normalisation would, without applying either.
    script.write_text(f'''
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
LIFT = {HEIGHT / 2}

def tube(name, radius, z0, z1, rings, around, centre=(0.0, 0.0), cap=False):
    verts = [(centre[0] + radius * math.cos(2 * math.pi * k / around),
              centre[1] + radius * math.sin(2 * math.pi * k / around),
              z0 + (z1 - z0) * r / rings) for r in range(rings + 1) for k in range(around)]
    faces = []
    for r in range(rings):
        for k in range(around):
            a, b = r * around + k, r * around + (k + 1) % around
            faces += [(a, b, b + around), (a, b + around, a + around)]
    if cap:
        faces += [tuple(range(around))[::-1], tuple(rings * around + k for k in range(around))]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    return ob

root = bpy.data.objects.new('generator_root', None)
bpy.context.scene.collection.objects.link(root)
parts = [tube('torso_and_legs', 0.18, 0.0 - LIFT, 1.45 - LIFT, 60, 48, cap=True),
         tube('neck', {NECK[2]}, 1.40 - LIFT, 1.62 - LIFT, 44, 64, centre=({NECK[0]}, {NECK[1]}))]
arms = tube('arms', 0.045, -0.85, 0.85, 80, 24, cap=True)
arms.rotation_euler = (0.0, math.pi / 2, 0.0)
arms.location = (0.0, 0.0, 1.38 - LIFT)
collar = tube('collar', {COLLAR_RADIUS}, -0.015, 0.015, 6, 96)
collar.rotation_euler = (math.radians({COLLAR_TILT_DEG}), 0.0, 0.0)
collar.location = ({NECK[0]}, {NECK[1]}, {COLLAR_Z} - LIFT)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.115,
                                     location=({NECK[0]}, {NECK[1]}, 1.685 - LIFT))
head = bpy.context.active_object
for ob in parts + [arms, collar, head]:
    ob.parent = root
root.scale = (1 / 0.9,) * 3
root.location = (0.0, 0.0, 0.01)
bpy.ops.export_scene.gltf(filepath={str(source)!r}, export_format='GLB', export_yup=True)
''')
    blender('--python', script)
    return source


def dump(blend, folder):
    out = folder / 'dump.json'
    script = folder / 'dump.py'
    script.write_text(f'''
import bpy, json
objects = []
for ob in bpy.data.objects:
    item = {{'name': ob.name, 'type': ob.type}}
    if ob.type == 'MESH':
        ob.data.calc_loop_triangles()
        item['verts'] = [list(ob.matrix_world @ v.co) for v in ob.data.vertices]
        item['triangles'] = len(ob.data.loop_triangles)
    objects.append(item)
open({str(out)!r}, 'w').write(json.dumps(objects))
''')
    blender(blend, '--python', script)
    return json.loads(out.read_text())


def run_stage(scan, folder, *args):
    blend = folder / 'out' / 'body-acquisition.blend'
    log = blender('--python', STAGE, '--', scan, blend, '--height-m', HEIGHT, *args)
    receipt = json.loads((blend.parent / 'body-scan-receipt.json').read_text())
    objects = dump(blend, folder)
    return log, receipt, objects


def test_head_and_neck_column_go_and_the_tilted_collar_stays(scan, tmp_path):
    log, receipt, objects = run_stage(scan, tmp_path, '--cut-z-m', CUT, '--object-name', 'Scan_Body')

    assert [(o['name'], o['type']) for o in objects] == [('Scan_Body', 'MESH')]
    body = objects[0]
    verts = np.array(body['verts'])
    lift = receipt['body_lift_m']
    assert 'body_lift_m: 0.9' in log
    assert receipt['object'] == 'Scan_Body'
    assert receipt['imported_meshes_joined'] == 5

    # Real size, uniformly: two metres became 1.8, the T-pose arms span 1.7 m.
    assert receipt['scale']['factor'] == pytest.approx(0.9, abs=1e-6)
    assert verts[:, 0].min() == pytest.approx(-0.85, abs=1e-4)
    assert verts[:, 0].max() == pytest.approx(0.85, abs=1e-4)
    # Centred on z=0 as delivered: the 9 mm the parent added is taken back out,
    # x/y are left alone, and the feet sit half the height below the origin.
    assert receipt['centre']['shift_applied_m'] == pytest.approx([0.0, 0.0, -0.009], abs=1e-6)
    assert lift == pytest.approx(-verts[:, 2].min(), abs=1e-6)
    assert lift == pytest.approx(HEIGHT / 2, abs=1e-5)
    assert receipt['cut_z_m']['floor'] == pytest.approx(CUT)
    assert receipt['cut_z_m']['centred'] == pytest.approx(CUT - lift, abs=1e-6)
    assert receipt['cut_z_m']['source'] == 'argument --cut-z-m'

    # Without a profile the neck column is measured, seen all round past the
    # collar, and the cut goes a margin outside it.
    neck = receipt['neck_column']
    assert neck['source'] == 'measured'
    assert neck['measured']['plausible'] is True
    assert neck['measured']['centred_on'].startswith("the neck's own centre")
    assert neck['centre_xy_m'] == pytest.approx(NECK[:2], abs=0.001)
    assert neck['radii_xy_m'] == pytest.approx([NECK[2]] * 2, abs=0.001)
    assert neck['margin_m'] == pytest.approx(0.015)

    floor = verts[:, 2] + lift
    radius = np.hypot(verts[:, 0] - NECK[0], verts[:, 1] - NECK[1])
    # Nothing of the neck or head stays above the cut inside the neck column.
    assert not np.any((floor > CUT + 1e-6) & (radius < NECK[2] + 0.01))
    # Nothing of the head anywhere: the highest point left is the collar's back.
    assert floor.max() == pytest.approx(COLLAR_BACK_TOP, abs=0.002)
    # The collar's back, outside the column and above the cut, is kept ...
    back = (verts[:, 1] > NECK[1] + 0.05) & (floor > CUT + 0.02) & (radius > NECK[2] + 0.015)
    assert back.sum() > 20
    # ... and so are its front, below the cut, and the neck's stub inside the collar.
    assert np.any((verts[:, 1] < NECK[1] - 0.05) & (floor < COLLAR_Z) & (radius > 0.08) & (radius < 0.1))
    assert np.any((floor > 1.45) & (floor <= CUT) & (np.abs(radius - NECK[2]) < 0.001))

    removed = receipt['faces_removed']
    assert removed['neck_column'] > 0 and removed['above_head_level'] > 0 and removed['floating_above_cut'] > 0
    assert receipt['triangles']['after'] == body['triangles']
    assert receipt['triangles']['before'] > receipt['triangles']['after']
    assert receipt['top_floor_z_m'] == pytest.approx(COLLAR_BACK_TOP, abs=0.002)


def test_the_profile_supplies_the_cut_and_the_name(scan, tmp_path):
    profile = tmp_path / 'tester.json'
    profile.write_text(json.dumps({
        'name': 'Tester', 'asset_prefix': 'Tester',
        'oral_anatomy': {'neck_m': [1.6, 1.45]},
        'neck_overlap': {'ellipse_m': [0.07, 0.07], 'above_z_m': CUT, 'rim_above_z_m': 1.5, 'rim_abs_x_m': 0.2},
    }))
    log, receipt, objects = run_stage(scan, tmp_path, '--profile', profile)

    assert [o['name'] for o in objects] == ['Tester_Garment_And_Wrists_Preserved']
    assert 'neck_overlap.above_z_m' in receipt['cut_z_m']['source']
    assert 'neck_overlap.above_z_m' in log
    assert receipt['cut_z_m']['floor'] == pytest.approx(CUT)
    assert receipt['head_neck_gap'] is None
    # The profile's ellipse is the column, on the axis, as the assembly cuts it;
    # the measurement is kept beside it as a cross-check.
    neck = receipt['neck_column']
    assert 'neck_overlap.ellipse_m' in neck['source']
    assert neck['centre_xy_m'] == [0.0, 0.0]
    assert neck['cut_radii_xy_m'] == pytest.approx([0.07, 0.07])
    assert neck['measured']['radii_xy_m'] == pytest.approx([NECK[2]] * 2, abs=0.001)
    verts = np.array(objects[0]['verts'])
    floor = verts[:, 2] + receipt['body_lift_m']
    assert not np.any((floor > CUT + 1e-6) & (np.hypot(verts[:, 0], verts[:, 1]) < 0.07))
    assert floor.max() == pytest.approx(COLLAR_BACK_TOP, abs=0.002)


def test_a_profile_whose_head_neck_stops_above_the_cut_is_reported(scan, tmp_path):
    profile = tmp_path / 'short-neck.json'
    profile.write_text(json.dumps({
        'asset_prefix': 'Short', 'inputs': {'body_object': 'Short_Body'},
        'oral_anatomy': {'neck_m': [1.6, 1.55]},
        'neck_overlap': {'ellipse_m': [0.07, 0.07], 'above_z_m': CUT},
    }))
    log, receipt, objects = run_stage(scan, tmp_path, '--profile', profile)

    assert [o['name'] for o in objects] == ['Short_Body']
    assert 'WARNING' in log and '1.55' in receipt['head_neck_gap']
