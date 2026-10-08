"""Optional real-Blender check: the Ennix body stage gives hands and garment their own counts.

A uniform collapse spends where the scan was dense. Ennix's preserved hands are
two thirds of the acquisition, so a uniform 120k left about 29k on the hands and
91k on the coat. The fixture is a tube with the same shape of problem: dense
ends beyond |x| 0.8 m and a sparse middle.
"""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')


def blender(*args):
    result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1', *map(str, args)],
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope='module')
def acquisition(tmp_path_factory):
    folder = tmp_path_factory.mktemp('acquisition')
    source = folder / 'body.blend'
    script = folder / 'make.py'
    script.write_text(f'''
import bpy, math
import numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
xs = np.concatenate([np.linspace(-1.0, -0.8, 101), np.linspace(-0.78, 0.78, 79), np.linspace(0.8, 1.0, 101)])
around = 64
rings = [[(x, 0.05 * math.cos(2 * math.pi * k / around), 0.05 * math.sin(2 * math.pi * k / around))
          for k in range(around)] for x in xs]
verts = [v for ring in rings for v in ring]
faces = []
for r in range(len(xs) - 1):
    for k in range(around):
        a, b = r * around + k, r * around + (k + 1) % around
        faces += [(a, b, b + around), (a, b + around, a + around)]
mesh = bpy.data.meshes.new('body')
mesh.from_pydata(verts, [], faces)
ob = bpy.data.objects.new('Ennix_Garment_And_Wrists_Preserved', mesh)
bpy.context.scene.collection.objects.link(ob)
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    blender('--python', script)
    return source


def test_hands_and_garment_each_reach_their_own_count(acquisition, tmp_path):
    blender('--python', ROOT / 'scripts/blender/prepare_body_acquisition.py', '--', acquisition, tmp_path,
            '--triangles', 4000, '--hand-triangles', 2000, '--measure-samples', 500)

    receipt = json.loads((tmp_path / 'body-preparation.json').read_text())
    reduction = receipt['reduction']
    # The source is the other way round: about 25,600 on the ends, 10,000 between.
    assert reduction['source_triangles']['hands'] > 2 * reduction['source_triangles']['garment']
    assert reduction['triangles']['hands'] == pytest.approx(2000, rel=0.1)
    assert reduction['triangles']['garment'] == pytest.approx(4000, rel=0.1)
    assert receipt['triangles'] == sum(reduction['triangles'].values())
    measured = reduction['deviation_from_source']
    assert set(measured) == {'garment', 'garment_folds_and_hems', 'garment_outline', 'hands'}
    # A plain tube has no folds; an empty region is recorded, not invented.
    assert measured['garment_folds_and_hems'] == {'samples': 0}
    for region in ('garment', 'garment_outline', 'hands'):
        assert measured[region]['samples'] == 500
        assert measured[region]['p99_mm'] < 2.0
    assert (tmp_path / 'body.npz').is_file()


def test_a_single_count_is_still_one_uniform_collapse(acquisition, tmp_path):
    blender('--python', ROOT / 'scripts/blender/prepare_body_acquisition.py', '--', acquisition, tmp_path,
            '--triangles', 6000)

    receipt = json.loads((tmp_path / 'body-preparation.json').read_text())
    assert 'reduction' not in receipt
    assert receipt['triangles'] == pytest.approx(6000, rel=0.05)
