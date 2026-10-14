"""Clean the acquired garment surface, transfer its paint and skinning, preserve the actor.

This is a versioned candidate, not an artistic acceptance. Voxel union removes
overlapping sheets; bounded smoothing and reduction prepare connected UV charts.
All non-garment meshes, their UVs/shapes/weights, and every bone are hash checked.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repack_character_outfit import chart_count, geometry_signature, sha


def apply_modifier(obj, name, kind, **settings):
    mod = obj.modifiers.new(name, kind)
    for key, value in settings.items():
        setattr(mod, key, value)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def tree(mesh):
    mesh.calc_loop_triangles()
    return BVHTree.FromPolygons([v.co for v in mesh.vertices],
                               [t.vertices for t in mesh.loop_triangles], all_triangles=True)


def transfer_image(source, target, image_path, dest, linear):
    mat = bpy.data.materials.new('SourcePaintTransfer')
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    image_node = nodes.new('ShaderNodeTexImage')
    image_node.image = bpy.data.images.load(str(image_path.resolve()), check_existing=False)
    image_node.image.colorspace_settings.name = 'Non-Color' if linear else 'sRGB'
    links.new(image_node.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs[0], output.inputs['Surface'])
    source.data.materials.clear()
    source.data.materials.append(mat)
    target_mat = bpy.data.materials.new('TargetPaintTransfer')
    target_mat.use_nodes = True
    result = bpy.data.images.new(dest.stem, width=4096, height=4096, alpha=False)
    result.colorspace_settings.name = 'Non-Color' if linear else 'sRGB'
    result.filepath_raw, result.file_format = str(dest.resolve()), 'PNG'
    active = target_mat.node_tree.nodes.new('ShaderNodeTexImage')
    active.image = result
    target_mat.node_tree.nodes.active = active
    target.data.materials.clear()
    target.data.materials.append(target_mat)
    for ob in bpy.context.scene.objects:
        ob.select_set(ob in (source, target))
    bpy.context.view_layer.objects.active = target
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.cycles.seed = 23
    # A wider ray does not excuse a displaced surface; the independent distance gate runs first.
    bpy.ops.object.bake(type='EMIT', margin=16, margin_type='EXTEND', use_clear=True,
                       use_selected_to_active=True, cage_extrusion=.012, max_ray_distance=.025)
    result.save()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--xatlas-dir', type=Path, required=True)
    parser.add_argument('--python', default='python')
    parser.add_argument('--voxel', type=float, default=.0025)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    assert sha(args.source) == args.source_sha256, 'Source hash changed'
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'outfit-paint').mkdir()
    (args.out / 'export').mkdir()
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    obj = bpy.data.objects['Character02_Outfit_And_Hands']
    assert obj.data.shape_keys is None, 'Garment shape keys need a separate transport gate'
    before = geometry_signature(obj)
    source = obj.copy()
    source.data = obj.data.copy()
    source.name = 'SOURCE_PreservedGarment'
    bpy.context.scene.collection.objects.link(source)
    original_material = obj.data.materials[0]
    for item in bpy.context.scene.objects:
        item.select_set(item == obj)
    bpy.context.view_layer.objects.active = obj
    # Work on the bind surface; reattach the exact armature after baking.
    armature = next(m.object for m in obj.modifiers if m.type == 'ARMATURE')
    obj.modifiers.clear()
    source.modifiers.clear()
    source.data.calc_loop_triangles()
    before_count = len(source.data.loop_triangles)
    apply_modifier(obj, 'ThinSheetSupport', 'SOLIDIFY', thickness=.003, offset=0)
    apply_modifier(obj, 'AcquiredSurfaceUnion', 'REMESH', mode='VOXEL', voxel_size=args.voxel,
                   use_smooth_shade=True)
    apply_modifier(obj, 'BoundedSurfaceFairing', 'SMOOTH', factor=.3, iterations=2)
    obj.data.calc_loop_triangles()
    ratio = min(1.0, 46000 / len(obj.data.loop_triangles))
    apply_modifier(obj, 'GarmentBudget', 'DECIMATE', ratio=ratio)
    apply_modifier(obj, 'StableTriangles', 'TRIANGULATE')
    obj.data.calc_loop_triangles()
    new_count = len(obj.data.loop_triangles)
    assert new_count <= 47161, 'Garment exceeded the existing budget'
    old_tree, new_tree = tree(source.data), tree(obj.data)
    forward = np.array([old_tree.find_nearest(v.co)[3] for v in obj.data.vertices])
    backward = np.array([new_tree.find_nearest(v.co)[3] for v in source.data.vertices])
    distances = {'new_to_source': np.quantile(forward, [.5, .95, .99, 1]).tolist(),
                 'source_to_new': np.quantile(backward, [.5, .95, .99, 1]).tolist()}
    (args.out / 'surface-distances.json').write_text(json.dumps(distances, indent=2))
    assert max(np.quantile(forward, .99), np.quantile(backward, .99)) < .008, distances
    assert max(forward.max(), backward.max()) < .025, distances
    obj.vertex_groups.clear()
    for group in source.vertex_groups:
        obj.vertex_groups.new(name=group.name)
    apply_modifier(obj, 'OriginalSkinning', 'DATA_TRANSFER', object=source, use_vert_data=True,
                   data_types_verts={'VGROUP_WEIGHTS'}, vert_mapping='POLYINTERP_NEAREST',
                   layers_vgroup_select_src='ALL', layers_vgroup_select_dst='NAME')
    unweighted = 0
    for vertex in obj.data.vertices:
        weights = sorted([(g.group, g.weight) for g in vertex.groups if g.weight > 1e-7],
                         key=lambda pair: pair[1], reverse=True)[:4]
        total = sum(w for _, w in weights)
        if total == 0:
            unweighted += 1
            continue
        for group in list(vertex.groups):
            obj.vertex_groups[group.group].remove([vertex.index])
        for group, weight in weights:
            obj.vertex_groups[group].add([vertex.index], weight / total, 'REPLACE')
    assert unweighted == 0, f'{unweighted} unweighted vertices'
    dump, packed = args.out / 'surface.npz', args.out / 'packed-uvs.npz'
    triangles = list(obj.data.loop_triangles)
    np.savez(dump, verts=np.array([v.co[:] for v in obj.data.vertices]),
             faces=np.array([t.vertices[:] for t in triangles]))
    helper = Path(__file__).resolve().parents[1] / 'repack_outfit_uvs.py'
    subprocess.run([args.python, str(helper), str(dump.resolve()), str(packed.resolve()),
                    '--xatlas-dir', str(args.xatlas_dir.resolve())], check=True)
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    uv = obj.data.uv_layers.new(name='UVMap')
    for tri, coords in zip(triangles, np.load(packed)['uv']):
        for loop, value in zip(tri.loops, coords):
            uv.data[loop].uv = value
    charts = chart_count(obj.data, uv)
    assert charts < 2000, f'{charts} charts remains excessive after surface repair'
    image_receipts = {}
    for name, linear in [('body_basecolor.png', False), ('garment_mask.png', True)]:
        input_path = args.build / 'outfit-paint' / name
        output_path = args.out / 'outfit-paint' / name
        image = transfer_image(source, obj, input_path, output_path, linear)
        image_receipts[name] = {'input_sha256': sha(input_path), 'output_sha256': sha(output_path)}
        if not linear:
            color_image = image
    obj.data.materials.clear()
    obj.data.materials.append(original_material)
    for node in original_material.node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image = color_image
    mod = obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = armature
    bpy.data.objects.remove(source, do_unlink=True)
    after = geometry_signature(obj)
    protected = {name: value for name, value in before.items() if name != obj.name}
    assert all(after[name] == value for name, value in protected.items()), 'Protected character data changed'
    area3, area2 = 0.0, 0.0
    for tri in obj.data.loop_triangles:
        area3 += tri.area
        coords = np.array([uv.data[i].uv[:] for i in tri.loops])
        a, b = coords[1] - coords[0], coords[2] - coords[0]
        area2 += abs(a[0] * b[1] - a[1] * b[0]) * .5
    stage = json.loads((args.build / 'outfit-paint/outfit-paint.json').read_text())
    metres_per_uv = math.sqrt(area3 / area2)
    factor = metres_per_uv / stage['metres_per_uv']
    stage['tiling'] = {key: value * factor for key, value in stage['tiling'].items()}
    stage['metres_per_uv'] = metres_per_uv
    stage['surface_transfer'] = {'source_sha256': args.source_sha256, 'charts': charts}
    (args.out / 'outfit-paint/outfit-paint.json').write_text(json.dumps(stage, indent=2))
    for name in ('leather_normal.png', 'weave_normal.png'):
        shutil.copy2(args.build / 'outfit-paint' / name, args.out / 'outfit-paint' / name)
    shutil.copytree(args.build / 'hands-paint', args.out / 'hands-paint')
    for path in (args.build / 'export').glob('hair-mesh-*.png'):
        shutil.copy2(path, args.out / 'export' / path.name)
    native = args.out / 'Character02_UE5_surface.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()))
    report = {'source': str(args.source), 'source_sha256': args.source_sha256, 'script_sha256': sha(__file__),
              'blender': bpy.app.version_string, 'command': sys.argv, 'seed': 23,
              'voxel_m': args.voxel, 'solidify_m': .003, 'triangles_before': before_count,
              'triangles_after': new_count, 'charts': charts, 'distance_quantiles_m': distances,
              'protected_character_unchanged': True, 'protected_signatures': protected,
              'images': image_receipts, 'native_sha256': sha(native),
              'production_ready': False, 'human_review': 'pending'}
    (args.out / 'surface-receipt.json').write_text(json.dumps(report, indent=2))
    print(f'Garment candidate served: {new_count} triangles, {charts} charts. The face retains its alibi, sir.')


if __name__ == '__main__':
    main()
