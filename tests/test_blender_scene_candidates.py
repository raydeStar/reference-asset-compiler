"""Optional real-Blender regressions for bugs exposed by assembled scene assets."""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get('RAC_BLENDER')
pytestmark = pytest.mark.skipif(not BLENDER, reason='Set RAC_BLENDER for real Blender checks')


def run(script, *args):
    result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1',
                             '--python', str(script), '--', *map(str, args)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_group_cleanup_preserves_separate_substantive_objects_when_requested(tmp_path):
    script = tmp_path / 'groups.py'
    script.write_text(f'''
import bpy, sys, json
sys.path.insert(0, {str(ROOT / 'scripts/blender')!r})
from reduce_voxel_quadriflow import manifoldize_dominant_volume
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(location=(-2,0,0))
bpy.ops.mesh.primitive_cube_add(location=(2,0,0))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.join()
obj=bpy.context.object
report=manifoldize_dominant_volume(obj, preserve_components=True)
assert report['input_components']==2
assert report['discarded_faces']==0
assert len(obj.data.polygons)==12
assert report['remaining_boundary_edges']==0
default=manifoldize_dominant_volume(obj)
assert default['discarded_faces']==6
assert len(obj.data.polygons)==6
''')
    run(script)


def test_height_is_vertical_extent_not_a_wide_objects_longest_dimension(tmp_path):
    source = tmp_path / 'wide.glb'
    script = tmp_path / 'wide.py'
    script.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
bpy.context.object.scale=(3,1,.5)
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
bpy.ops.export_scene.gltf(filepath={str(source)!r},export_format='GLB')
''')
    run(script)
    report = tmp_path / 'staged.json'
    run(ROOT / 'scripts/blender/stage_generated_mesh.py', source, tmp_path / 'staged.blend',
        report, '--height-m', '2', '--size', 'test')
    scale = json.loads(report.read_text())['scale']
    assert scale['height_axis'] == 'world-Z'
    assert scale['dimensions_after_m'] == pytest.approx([12, 4, 2])


def test_rig_normalization_round_trips_height_weights_and_bind_pose(tmp_path):
    source = tmp_path / 'rig.blend'
    script = tmp_path / 'rig.py'
    script.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.object.armature_add()
arm=bpy.context.object
arm.name='Rig'
bpy.ops.mesh.primitive_cube_add(location=(0,0,2))
mesh=bpy.context.object
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
group=mesh.vertex_groups.new(name='Bone')
group.add(list(range(len(mesh.data.vertices))),1.0,'REPLACE')
mesh.parent=arm
modifier=mesh.modifiers.new('Skin','ARMATURE')
modifier.object=arm
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    run(script)
    output = tmp_path / 'placed.glb'
    run(ROOT / 'scripts/blender/normalize_browser_asset.py', source, output, tmp_path/'receipt.json', '0.5')
    check = tmp_path / 'check.py'
    check.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath={str(output)!r})
mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
assert len(arm.data.bones)==1
assert all(abs(sum(g.weight for g in v.groups)-1)<1e-5 for v in mesh.data.vertices)
graph=bpy.context.evaluated_depsgraph_get()
evaluated=mesh.evaluated_get(graph)
points=[evaluated.matrix_world@v.co for v in evaluated.data.vertices]
assert abs(min(v.z for v in points))<1e-5
assert abs(max(v.z for v in points)-.5)<1e-5
raw=[mesh.matrix_world@v.co for v in mesh.data.vertices]
assert abs(max(v.z for v in raw)-.5)<1e-5
arm.pose.bones[0].rotation_mode='XYZ'
arm.pose.bones[0].rotation_euler.x=.5
bpy.context.view_layer.update()
posed=mesh.evaluated_get(graph)
assert max((posed.matrix_world@v.co-before).length for v,before in zip(posed.data.vertices,points))>.02
''')
    run(check)
    # Importers create bone-display meshes. Those are widgets, not geometry to
    # measure or ship when normalizing an already rigged GLB a second time.
    second_report = tmp_path/'second.json'
    run(ROOT/'scripts/blender/normalize_browser_asset.py', output, tmp_path/'second.glb', second_report, '.7')
    receipt = json.loads(second_report.read_text())
    assert receipt['triangles'] == 12
    assert receipt['height_m'] == .7
    assert receipt['source_bounds_blender_m'][0][2] == pytest.approx(0, abs=1e-5)
    assert receipt['source_bounds_blender_m'][1][2] == pytest.approx(.5, abs=1e-5)


def test_floor_material_changes_only_selected_uvs_and_no_geometry(tmp_path):
    source = tmp_path/'room.blend'
    albedo = tmp_path/'tile.png'
    setup = tmp_path/'floor.py'
    setup.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,.1))
floor=bpy.context.object
floor.name='Floor'
floor.scale=(3,3,.2)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,2))
post=bpy.context.object
post.name='Post'
post.scale=(.2,.2,4)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
image=bpy.data.images.new('Fixture',width=2,height=2)
image.filepath_raw={str(albedo)!r}
image.file_format='PNG'
image.save()
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    run(setup)
    output = tmp_path/'floor-textured.glb'
    report = tmp_path/'floor-report.json'
    run(ROOT/'scripts/blender/texture_planar_floor.py', source, output, report, albedo)
    receipt = json.loads(report.read_text())
    assert receipt['selected_faces'] == 1
    assert receipt['total_faces'] == 12
    check = tmp_path/'compare.py'
    check.write_text(f'''
import bpy
def snapshot(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    return {{o.name: ([tuple(v.co) for v in o.data.vertices], [tuple(l.uv) for l in o.data.uv_layers.active.data]) for o in bpy.context.scene.objects if o.type=='MESH'}}
before=snapshot({str(source)!r})
after=snapshot({str(output.with_suffix('.blend'))!r})
assert before['Post']==after['Post']
assert before['Floor'][0]==after['Floor'][0]
assert before['Floor'][1]!=after['Floor'][1]
''')
    run(check)


@pytest.mark.parametrize('include_down,expected_faces', [(False, 3), (True, 6)])
def test_horizontal_material_preserves_geometry_and_vertical_uvs(tmp_path, include_down, expected_faces):
    source, albedo = tmp_path/'shelves.blend', tmp_path/'oak.png'
    setup = tmp_path/'shelves.py'
    setup.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
for height in (0, 1, 2):
    bpy.ops.mesh.primitive_cube_add(size=1,location=(.3,.2,height))
    o=bpy.context.object
    o.scale=(3,.5,.1)
    o.data.materials.append(bpy.data.materials.new('Original'))
image=bpy.data.images.new('Fixture',width=2,height=2)
image.filepath_raw={str(albedo)!r}
image.file_format='PNG'
image.save()
bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})
''')
    run(setup)
    output, report = tmp_path/'repaired.glb', tmp_path/'repair.json'
    script = ROOT/'scripts/blender/texture_horizontal_surfaces.py'
    flags = ['--include-down'] if include_down else []
    run(script, source, output, report, albedo, *flags)
    receipt = json.loads(report.read_text())
    assert receipt['selected_faces'] == expected_faces
    assert receipt['untouched_faces'] == 18-expected_faces
    check = tmp_path/'check-horizontal.py'
    check.write_text(f'''
import bpy
def snapshot(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    return {{o.name: {{'matrix':[tuple(row) for row in o.matrix_world],
        'vertices':[tuple(v.co) for v in o.data.vertices],
        'faces':[tuple(p.vertices) for p in o.data.polygons],
        'uvs':[[tuple(o.data.uv_layers.active.data[n].uv) for n in p.loop_indices] for p in o.data.polygons],
        'materials':[o.data.materials[p.material_index].name for p in o.data.polygons],
        'centres':[p.center.z for p in o.data.polygons]}} for o in bpy.context.scene.objects if o.type=='MESH'}}
before=snapshot({str(source)!r})
after=snapshot({str(output.with_suffix('.blend'))!r})
for name,old in before.items():
    new=after[name]
    for field in ('matrix','vertices','faces'):assert old[field]==new[field]
    for n,z in enumerate(old['centres']):
        selected=z>.49 or ({include_down!r} and z<-.49)
        if selected:
            assert old['uvs'][n]!=new['uvs'][n]
            assert new['materials'][n]=='Reference horizontal surface'
        else:
            assert old['uvs'][n]==new['uvs'][n]
            assert old['materials'][n]==new['materials'][n]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath={str(output)!r})
assert sum(len(p.vertices)-2 for o in bpy.context.scene.objects if o.type=='MESH' for p in o.data.polygons)==36
''')
    run(check)
    retained = output.read_bytes()
    refused = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1',
                              '--python', str(script), '--', str(source), str(output), str(report), str(albedo)],
                             capture_output=True, text=True, timeout=90)
    assert refused.returncode != 0
    assert 'Preserve the existing candidate' in refused.stdout + refused.stderr
    assert output.read_bytes() == retained


def test_seam_cut_mesh_is_welded_before_tiny_pieces_are_removed(tmp_path):
    # Pixal3D writes its mesh cut along every texture seam. Counted as it came,
    # each island was a "tiny piece" and the cleanup deleted 11% of a hull.
    script = tmp_path / 'seams.py'
    script.write_text(f'''
import bpy, bmesh, sys
sys.path.insert(0, {str(ROOT / 'scripts/blender')!r})
from reduce_voxel_quadriflow import remove_tiny_components, weld_coincident
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.1)
obj = bpy.context.object
faces = len(obj.data.polygons)
bm = bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.split_edges(bm, edges=list(bm.edges))
bm.to_mesh(obj.data); bm.free()
assert len(obj.data.vertices) == len(obj.data.loops)  # every face its own piece
weld = weld_coincident(obj)
assert weld['merged_vertices'] > 0
assert remove_tiny_components(obj, 24)['faces'] == 0
assert len(obj.data.polygons) == faces
''')
    run(script)


def test_a_dense_shape_is_baked_onto_a_painted_mesh_and_lands_in_its_normal_map(tmp_path):
    # A bumpy dense sphere and a smooth painted one in the same place: the bake
    # must give the smooth one a normal map that tilts where the bumps are.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=0.5)
dense = bpy.context.object
for v in dense.data.vertices:
    bump = 1.0 + 0.03 * math.sin(14 * v.co.x) * math.sin(14 * v.co.y)
    v.co *= bump
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'dense.blend')!r})
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5)
low = bpy.context.object
bpy.ops.object.shade_smooth()
image = bpy.data.images.new('paint', 256, 256)
image.pixels = [0.6, 0.4, 0.2, 1.0] * (256 * 256)
image.filepath_raw = {str(tmp_path / 'paint.png')!r}
image.file_format = 'PNG'
image.save()
material = bpy.data.materials.new('paint'); material.use_nodes = True
texture = material.node_tree.nodes.new('ShaderNodeTexImage'); texture.image = image
material.node_tree.links.new(texture.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
low.data.materials.append(material)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'painted.glb')!r}, export_format='GLB')
''')
    run(make)
    report = tmp_path / 'shape.json'
    run(ROOT / 'scripts/blender/bake_dense_shape.py', tmp_path / 'painted.glb', tmp_path / 'shaped.glb', report,
        '--dense', tmp_path / 'dense.blend', '--cage', '0.04', '--max-ray', '0.1')
    receipt = json.loads(report.read_text())
    assert receipt['size'] == [256, 256]
    assert receipt['centre_offset_m'] < 0.01
    assert 'alone' in receipt['normal']
    assert receipt['tilt_degrees_p50_p90'][1] > 3.0
    assert (tmp_path / 'shaped.glb').stat().st_size > 0


def test_a_dense_mesh_in_another_place_is_refused(tmp_path):
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0))
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'dense.blend')!r})
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
image = bpy.data.images.new('paint', 64, 64)
material = bpy.data.materials.new('paint'); material.use_nodes = True
texture = material.node_tree.nodes.new('ShaderNodeTexImage'); texture.image = image
material.node_tree.links.new(texture.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.context.object.data.materials.append(material)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'painted.glb')!r}, export_format='GLB')
''')
    run(make)
    result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python-exit-code', '1', '--python',
                             str(ROOT / 'scripts/blender/bake_dense_shape.py'), '--', str(tmp_path / 'painted.glb'),
                             str(tmp_path / 'o.glb'), str(tmp_path / 'o.json'), '--dense', str(tmp_path / 'dense.blend')],
                            capture_output=True, text=True, timeout=90)
    assert 'not the same model in the same place' in result.stdout
    assert not (tmp_path / 'o.glb').exists()


def test_a_dense_mesh_and_its_simplified_copy_are_levelled_by_one_transform(tmp_path):
    # A tilted boat-like box and a coarser copy of it: both must come out with
    # the same length along X, on the floor, and matching each other closely.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0)
obj = bpy.context.object
obj.scale = (2.0, 0.7, 0.4)
obj.rotation_euler = (0.3, 0.2, 0.9)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'dense.glb')!r}, export_format='GLB')
mod = obj.modifiers.new('fewer', 'DECIMATE'); mod.ratio = 0.2
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'low.glb')!r}, export_format='GLB')
''')
    run(make)
    report = tmp_path / 'level.json'
    run(ROOT / 'scripts/blender/level_pair.py', '2.2', report, tmp_path / 'dense.glb', tmp_path / 'dense.blend',
        tmp_path / 'low.glb', tmp_path / 'low.blend')
    files = json.loads(report.read_text())['files']
    dense, low = files[0], files[1]
    assert abs((dense['max_m'][0] - dense['min_m'][0]) - 2.2) < 1e-3
    assert abs(dense['min_m'][2]) < 1e-4
    for axis in range(3):
        assert abs(dense['min_m'][axis] - low['min_m'][axis]) < 0.03
        assert abs(dense['max_m'][axis] - low['max_m'][axis]) < 0.03
    assert low['triangles'] < dense['triangles']


def test_a_tall_piece_stands_up_when_its_longest_axis_is_up(tmp_path):
    # A lantern-like column: two metres tall, tilted the way Pixal3D keeps the
    # picture's camera. Levelled with the default it would lie down; with
    # --up longest it stands, two metres tall, on the floor.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0)
obj = bpy.context.object
obj.scale = (0.25, 0.35, 1.0)
obj.rotation_euler = (0.35, 0.1, 0.6)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'tall.glb')!r}, export_format='GLB')
''')
    run(make)
    for up, standing in (('shortest', False), ('longest', True)):
        report = tmp_path / 'level-{0}.json'.format(up)
        run(ROOT / 'scripts/blender/level_pair.py', '2.0', report, tmp_path / 'tall.glb',
            tmp_path / 'tall-{0}.blend'.format(up), '--up', up)
        levelled = json.loads(report.read_text())
        size = [hi - lo for lo, hi in zip(levelled['files'][0]['min_m'], levelled['files'][0]['max_m'])]
        assert levelled['up'] == up
        assert abs(max(size) - 2.0) < 1e-3
        assert abs(levelled['files'][0]['min_m'][2]) < 1e-4
        assert (size[2] == max(size)) is standing
