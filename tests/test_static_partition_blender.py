"""Real GLB round-trip proof for modular extraction, including source binding."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')


def invoke(script, *args):
    return subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1',
                           '--python', str(script), '--', *map(str, args)],
                          capture_output=True, text=True, timeout=90)


def test_partition_round_trips_positions_uvs_and_rejects_changed_source(tmp_path):
    source = tmp_path / 'source.blend'
    setup = tmp_path / 'setup.py'
    setup.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
for name,x in [('left',-2),('right',2)]:
    data=bpy.data.meshes.new(name)
    data.from_pydata([(0,0,0),(1,0,0),(0,0,1)],[],[(0,1,2)])
    uv=data.uv_layers.new(name='UVMap')
    for loop,value in zip(uv.data,[(.1,.2),(.8,.3),(.2,.9)]):loop.uv=value
    material=bpy.data.materials.new(name)
    material.diffuse_color=(.2,.3,.4,1)
    data.materials.append(material)
    obj=bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location=(x,.3,1)
    obj.scale=(1.2,1.4,1.5)
    obj.rotation_euler.z=.2
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    result = invoke(setup)
    assert result.returncode == 0, result.stdout + result.stderr
    recipe = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'parts': [{'name': 'left', 'bounds': [[-5, -5, -5], [0, 5, 5]]}],
              'remainder': 'right'}
    recipe_file = tmp_path / 'recipe.json'
    recipe_file.write_text(json.dumps(recipe))
    script = ROOT / 'scripts/blender/partition_static_asset.py'
    output = tmp_path / 'modules'
    result = invoke(script, source, recipe_file, output)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((output / 'partition.json').read_text())
    assert receipt['all_source_polygons_accounted_for_once']
    assert receipt['source_polygons'] == 2
    assert [part['triangles'] for part in receipt['parts']] == [1, 1]
    assert sorted(i for part in receipt['parts'] for i in part['source_polygon_ids']) == [0, 1]
    check = tmp_path / 'check.py'
    check.write_text(f'''
import bpy,json
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath={str(source)!r})
expected={{o.name:[(o.matrix_world@o.data.vertices[l.vertex_index].co, o.data.uv_layers[0].data[l.index].uv.copy()) for l in o.data.loops] for o in bpy.context.scene.objects if o.type=='MESH'}}
receipt=json.loads(open({str(output / 'partition.json')!r}).read())
for part in receipt['parts']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath={str(output)!r}+'/'+part['file'])
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    assert len(meshes)==1
    obj=meshes[0];p=part['position_gltf_m'];pivot=Vector((p[0],-p[2],p[1]))
    assert len(obj.data.materials)==1
    assert len(obj.data.uv_layers)==1
    for loop in obj.data.loops:
        world=obj.matrix_world@obj.data.vertices[loop.vertex_index].co+pivot
        point,uv=min(expected[part['name']],key=lambda pair:(world-pair[0]).length)
        assert (world-point).length<1e-5
        assert (obj.data.uv_layers[0].data[loop.index].uv-uv).length<1e-6
''')
    result = invoke(check)
    assert result.returncode == 0, result.stdout + result.stderr
    # A wrong source must fail before publishing any partial module directory.
    recipe['source_sha256'] = '0' * 64
    recipe_file.write_text(json.dumps(recipe))
    refused = tmp_path / 'refused'
    result = invoke(script, source, recipe_file, refused)
    assert result.returncode != 0
    assert 'Source hash differs' in result.stdout + result.stderr
    assert not refused.exists()
