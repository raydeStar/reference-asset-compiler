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


def test_a_stray_sheet_inside_the_cage_is_baked_from_a_closer_cage_not_black(tmp_path):
    # WK-04.1's stair: Pixal3D's dense mesh had a thin stray sheet a few
    # millimetres off the real surface. A ray starting on the 8 mm cage met the
    # sheet's back first and baked a normal pointing in, a black crescent. The
    # closer cage starts under the sheet and meets the real surface.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_plane_add(size=1.0)
bpy.ops.mesh.primitive_plane_add(size=0.4, location=(0, 0, 0.004), rotation=(math.pi, 0, 0))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'dense.blend')!r})
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_plane_add(size=1.0)
low = bpy.context.object
image = bpy.data.images.new('paint', 128, 128)
image.pixels = [0.6, 0.4, 0.2, 1.0] * (128 * 128)
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
    check = tmp_path / 'inward.py'
    check.write_text('''
import bpy, sys, numpy as np
image = bpy.data.images.load(sys.argv[sys.argv.index("--") + 1])
pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3] * 2 - 1
print("INWARD", int((pixels[:, 2] < 0.05).sum()))
''')

    def inward(maps):
        result = subprocess.run([BLENDER, '-b', '--factory-startup', '--python', str(check), '--',
                                 str(maps / 'dense_shape.png')], capture_output=True, text=True, timeout=90)
        return int(next(line for line in result.stdout.splitlines() if line.startswith('INWARD')).split()[1])

    # One cage: the sheet's 0.4 m square (about 2600 of 128x128 texels) faces
    # in. Those texels are left flat rather than black, and counted.
    run(ROOT / 'scripts/blender/bake_dense_shape.py', tmp_path / 'painted.glb', tmp_path / 'one.glb',
        tmp_path / 'one.json', '--dense', tmp_path / 'dense.blend', '--fallback-cages', 'none')
    one = json.loads((tmp_path / 'one.json').read_text())
    assert one['texels_flat'] > 2000
    assert inward(tmp_path / 'one-maps') == 0
    report = tmp_path / 'shaped.json'
    run(ROOT / 'scripts/blender/bake_dense_shape.py', tmp_path / 'painted.glb', tmp_path / 'shaped.glb', report,
        '--dense', tmp_path / 'dense.blend')
    receipt = json.loads(report.read_text())
    assert receipt['cages_m'] == [0.008, 0.003, 0.001]
    assert receipt['texels_by_cage']['0.003'] > 2000
    assert receipt['texels_flat_share'] < 0.01
    assert inward(tmp_path / 'shaped-maps') == 0


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


def test_a_game_mesh_is_mended_of_small_holes_specks_and_fins_but_not_a_large_opening(tmp_path):
    # PR-04.2's crate: Pixal3D's own game meshes came with missing triangles,
    # loose specks and fins on edges shared by three faces. The game mesh is
    # closed; a bowl's mouth, a large opening that may be meant, stays open;
    # and the dense mesh is left as it came.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, bmesh
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.5)
obj = bpy.context.object
bm = bmesh.new(); bm.from_mesh(obj.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[200], bm.faces[300]], context='FACES')
# a fin: a third face on one edge
bm.faces.ensure_lookup_table()
edge = bm.faces[100].edges[0]
tip = bm.verts.new((edge.verts[0].co + edge.verts[1].co) / 2 * 1.02)
bm.faces.new((edge.verts[0], edge.verts[1], tip))
# a speck: one tiny loose triangle
a = bm.verts.new((0.3, 0.3, 0.3)); b = bm.verts.new((0.3001, 0.3, 0.3)); c = bm.verts.new((0.3, 0.3001, 0.3))
bm.faces.new((a, b, c))
bm.to_mesh(obj.data); bm.free()
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'holed.glb')!r}, export_format='GLB')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.5)
obj = bpy.context.object
bm = bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > 0.25], context='FACES')
bm.to_mesh(obj.data); bm.free()
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'bowl.glb')!r}, export_format='GLB')
''')
    run(make)
    report = tmp_path / 'level.json'
    run(ROOT / 'scripts/blender/level_pair.py', '1.0', report, tmp_path / 'holed.glb', tmp_path / 'dense.blend',
        tmp_path / 'holed.glb', tmp_path / 'low.blend', tmp_path / 'bowl.glb', tmp_path / 'bowl.blend')
    dense, low, bowl = json.loads(report.read_text())['files']
    assert dense['holes_filled'] == 0 and dense['open_edges_after'] == dense['open_edges_before'] > 0
    assert low['open_edges_before'] > 0 and low['nonmanifold_edges_before'] > 0
    assert low['specks_dropped'] >= 1 and low['fins_dropped'] >= 1 and low['holes_filled'] >= 2
    assert low['open_edges_after'] == 0 and low['nonmanifold_edges_after'] == 0
    assert bowl['holes_filled'] == 0 and bowl['open_edges_after'] == bowl['open_edges_before'] >= 32


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


def test_a_size_given_as_a_height_sets_the_height(tmp_path):
    # Framewright gives a size as a landmark on a person, which is a height: a
    # long, low boat of knee height must come out knee high, not knee long.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0)
obj = bpy.context.object
obj.scale = (2.0, 0.7, 0.4)
obj.rotation_euler = (0.3, 0.2, 0.9)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'boat.glb')!r}, export_format='GLB')
''')
    run(make)
    report = tmp_path / 'level.json'
    run(ROOT / 'scripts/blender/level_pair.py', '0.5', report, tmp_path / 'boat.glb', tmp_path / 'boat.blend',
        '--height')
    levelled = json.loads(report.read_text())
    low, high = levelled['files'][0]['min_m'], levelled['files'][0]['max_m']
    assert levelled['size_is'] == 'height'
    assert abs((high[2] - low[2]) - 0.5) < 1e-3
    assert (high[0] - low[0]) > 1.5


def _glb_json(path):
    import struct
    data = Path(path).read_bytes()
    length = struct.unpack('<I', data[12:16])[0]
    return json.loads(data[20:20 + length])


def _painted_sphere(tmp_path, with_normal_map):
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, math, random
random.seed(3)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.5)
obj = bpy.context.object
for v in obj.data.vertices:
    v.co *= 1.0 + 0.04 * math.sin(9 * v.co.x) * math.sin(9 * v.co.z)
bpy.ops.object.shade_smooth()
image = bpy.data.images.new('paint', 256, 256)
image.pixels = [c for _ in range(256 * 256) for c in (random.random() * 0.5 + 0.2, 0.4, 0.3, 1.0)]
image.filepath_raw = {str(tmp_path / 'paint.png')!r}
image.file_format = 'PNG'
image.save()
material = bpy.data.materials.new('paint'); material.use_nodes = True
tree = material.node_tree
texture = tree.nodes.new('ShaderNodeTexImage'); texture.image = image
tree.links.new(texture.outputs['Color'], tree.nodes['Principled BSDF'].inputs['Base Color'])
if {with_normal_map!r}:
    bump = bpy.data.images.new('nrm', 64, 64)
    bump.pixels = [0.5, 0.5, 1.0, 1.0] * (64 * 64)
    bump.filepath_raw = {str(tmp_path / 'nrm.png')!r}
    bump.file_format = 'PNG'
    bump.save()
    node = tree.nodes.new('ShaderNodeTexImage'); node.image = bump
    node.image.colorspace_settings.name = 'Non-Color'
    normal = tree.nodes.new('ShaderNodeNormalMap')
    tree.links.new(node.outputs['Color'], normal.inputs['Color'])
    tree.links.new(normal.outputs['Normal'], tree.nodes['Principled BSDF'].inputs['Normal'])
obj.data.materials.append(material)
bpy.ops.export_scene.gltf(filepath={str(tmp_path / 'painted.glb')!r}, export_format='GLB')
''')
    run(make)
    return tmp_path / 'painted.glb'


def test_a_normal_mapped_model_reaches_the_browser_with_its_tangents(tmp_path):
    # The normal map was baked against Blender's tangents; a viewer given none
    # estimates its own per triangle, and Unreal computes its own. Shipping
    # Blender's keeps every viewer on the same frame.
    painted = _painted_sphere(tmp_path, with_normal_map=True)
    report = tmp_path / 'payload.json'
    run(ROOT / 'scripts/blender/export_browser_payload.py', painted, tmp_path / 'payload.glb', report)
    assert json.loads(report.read_text())['tangents_exported'] is True
    attributes = _glb_json(tmp_path / 'payload.glb')['meshes'][0]['primitives'][0]['attributes']
    assert 'TANGENT' in attributes


def test_detail_baked_without_occlusion_leaves_the_occlusion_slot_empty(tmp_path):
    # Pixal3D's layered game meshes bake occlusion that darkens visible
    # triangles in every viewer that reads the slot; --no-occlusion leaves it out.
    painted = _painted_sphere(tmp_path, with_normal_map=False)
    report = tmp_path / 'detail.json'
    run(ROOT / 'scripts/blender/bake_derived_maps.py', painted, tmp_path / 'detail.glb', report,
        '--resolution', '512', '--samples', '8', '--no-occlusion')
    assert 'left_out' in json.loads(report.read_text())['occlusion']
    assert 'occlusionTexture' not in _glb_json(tmp_path / 'detail.glb')['materials'][0]
    assert (tmp_path / 'detail-maps' / 'curvature.png').is_file()
    assert not (tmp_path / 'detail-maps' / 'occlusion.png').exists()


def test_a_surface_that_passes_over_itself_is_unwrapped_without_sharing_a_texel(tmp_path):
    # A helical ramp: every face looks up and all are joined, so Smart Project
    # makes one island of it and projects it flat, and after one turn it lands
    # on itself. The WK-04.1 stair's folded treads did the same: 8.9 % of their
    # texels were shared, and a hidden face's occlusion showed on a visible one.
    make = tmp_path / 'make.py'
    make.write_text(f'''
import bpy, bmesh, math
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new('ramp'); obj = bpy.data.objects.new('ramp', mesh)
bpy.context.scene.collection.objects.link(obj)
bm = bmesh.new(); rows = []
for i in range(73):
    t = i / 72 * 2.5 * math.pi
    rows.append([bm.verts.new((r * math.cos(t), r * math.sin(t), 0.05 * t / (2 * math.pi))) for r in (0.5, 0.75, 1.0)])
for a, b in zip(rows, rows[1:]):
    for j in range(2):
        bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
bm.to_mesh(mesh); bm.free()
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'ramp.blend')!r})
''')
    run(make)
    report = tmp_path / 'uv.json'
    run(ROOT / 'scripts/blender/prepare_texture_uv_transport.py', tmp_path / 'ramp.blend', tmp_path / 'uv.blend',
        tmp_path / 'uv.obj', report)
    receipt = json.loads(report.read_text())
    overlap = receipt['settings']['overlap']
    assert receipt['status'] == 'passed'
    assert overlap['faces_before'] > 20 and overlap['texel_share_before'] > 0.05
    assert overlap['texel_share_after_repack'] <= 0.001
