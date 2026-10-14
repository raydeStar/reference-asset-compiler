"""Repack a face-island garment atlas without altering the acquired character.

xatlas proposes connected charts; a Blender emission bake transports the
existing paint and garment mask through the old UVs. No new artwork,
geometry, inference or proprietary tooling is involved. Keep each output in a
fresh directory; the original tailor's work deserves a proper paper trail.
"""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry_signature(outfit):
    """Protect positions, topology, shapes, skinning, transforms and bone frames."""
    result = {}
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type not in {'MESH', 'ARMATURE'}:
            continue
        data = {'matrix': [list(row) for row in obj.matrix_world]}
        if obj.type == 'ARMATURE':
            data['bones'] = [(b.name, b.parent.name if b.parent else None,
                              [list(row) for row in b.matrix_local]) for b in obj.data.bones]
        else:
            data['vertices'] = [list(v.co) for v in obj.data.vertices]
            data['polygons'] = [list(p.vertices) for p in obj.data.polygons]
            data['groups'] = [g.name for g in obj.vertex_groups]
            data['weights'] = [[(g.group, g.weight) for g in v.groups] for v in obj.data.vertices]
            data['shapes'] = {k.name: [list(v.co) for v in k.data]
                              for k in obj.data.shape_keys.key_blocks} if obj.data.shape_keys else {}
            if obj != outfit:
                data['uvs'] = [[list(v.uv) for v in layer.data] for layer in obj.data.uv_layers]
        result[obj.name] = hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()
    return result


def chart_count(mesh, layer):
    """Count UV-connected face components using geometric edges and loop UVs."""
    parents = list(range(len(mesh.polygons)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    edges = {}
    for poly in mesh.polygons:
        loops = list(poly.loop_indices)
        for a, b in zip(loops, loops[1:] + loops[:1]):
            va, vb = mesh.loops[a].vertex_index, mesh.loops[b].vertex_index
            ua = tuple(round(x, 6) for x in layer.data[a].uv)
            ub = tuple(round(x, 6) for x in layer.data[b].uv)
            key = (va, vb, ua, ub) if va < vb else (vb, va, ub, ua)
            if key in edges:
                parents[root(poly.index)] = root(edges[key])
            else:
                edges[key] = poly.index
    return len({root(i) for i in range(len(parents))})


def bake(mesh_obj, old_uv, new_uv, source, dest, size, linear=False):
    mat = bpy.data.materials.new('OutfitAtlasTransfer')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = old_uv.name
    source_node = nodes.new('ShaderNodeTexImage')
    source_node.image = bpy.data.images.load(str(source.resolve()), check_existing=False)
    source_node.image.colorspace_settings.name = 'Non-Color' if linear else 'sRGB'
    source_node.interpolation = 'Linear'
    mat.node_tree.links.new(uv.outputs['UV'], source_node.inputs['Vector'])
    mat.node_tree.links.new(source_node.outputs['Color'], emission.inputs['Color'])
    mat.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    target = bpy.data.images.new(dest.stem, width=size, height=size, alpha=False)
    target.colorspace_settings.name = 'Non-Color' if linear else 'sRGB'
    target.filepath_raw = str(dest.resolve())
    target.file_format = 'PNG'
    target_node = nodes.new('ShaderNodeTexImage')
    target_node.image = target
    nodes.active = target_node
    mesh_obj.data.materials[0] = mat
    mesh_obj.data.uv_layers.active = new_uv
    new_uv.active_render = True
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.context.scene.cycles.device = 'CPU'
    bpy.context.scene.cycles.samples = 1
    bpy.context.scene.cycles.seed = 23
    bpy.ops.object.bake(type='EMIT', margin=16, margin_type='EXTEND', use_clear=True,
                       use_selected_to_active=False, uv_layer=new_uv.name)
    target.save()
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--object', default='Character02_Outfit_And_Hands')
    parser.add_argument('--size', type=int, default=4096)
    parser.add_argument('--atlas-python', default='python')
    parser.add_argument('--xatlas-dir', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if sha(args.source) != args.source_sha256:
        raise ValueError('Source changed; the butler refuses to tailor the wrong gentleman.')
    args.out.mkdir(parents=True, exist_ok=False)
    for folder in ('outfit-paint', 'export'):
        (args.out / folder).mkdir()
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    obj = bpy.data.objects[args.object]
    before = geometry_signature(obj)
    old = obj.data.uv_layers.active
    old.name = 'SourceFaceAtlas'
    before_charts = chart_count(obj.data, old)
    original_material = obj.data.materials[0]
    new = obj.data.uv_layers.new(name='OutfitAtlas')
    old = obj.data.uv_layers['SourceFaceAtlas']
    obj.data.uv_layers.active = new
    for item in bpy.context.scene.objects:
        item.select_set(item == obj)
    bpy.context.view_layer.objects.active = obj
    obj.data.calc_loop_triangles()
    triangles = list(obj.data.loop_triangles)
    dump = args.out / 'source-geometry.npz'
    np.savez(dump, verts=np.array([v.co[:] for v in obj.data.vertices]),
             faces=np.array([t.vertices[:] for t in triangles]))
    helper = Path(__file__).resolve().parents[1] / 'repack_outfit_uvs.py'
    packed = args.out / 'packed-uvs.npz'
    command = [args.atlas_python, str(helper), str(dump.resolve()), str(packed.resolve()),
               '--xatlas-dir', str(args.xatlas_dir.resolve())]
    subprocess.run(command, check=True)
    packed_uvs = np.load(packed)['uv']
    for tri, coords in zip(triangles, packed_uvs):
        for loop, uv in zip(tri.loops, coords):
            new.data[loop].uv = uv
    after_charts = chart_count(obj.data, new)
    if after_charts >= before_charts // 4:
        raise ValueError(f'Chart count remains excessive: {after_charts}/{before_charts}')
    inputs = {'source': {'path': str(args.source.resolve()), 'sha256': sha(args.source)}}
    outputs = {}
    for name, linear in [('body_basecolor.png', False), ('garment_mask.png', True)]:
        source = args.build / 'outfit-paint' / name
        dest = args.out / 'outfit-paint' / name
        image = bake(obj, old, new, source, dest, args.size, linear)
        outputs[name] = {'path': str(dest.resolve()), 'sha256': sha(dest)}
        inputs[name] = {'path': str(source.resolve()), 'sha256': sha(source)}
        if not linear:
            color_image = image
    obj.data.materials[0] = original_material
    for node in original_material.node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image = color_image
    # Export UV0 must be the rebaked atlas; archive the old one in the source file.
    obj.data.uv_layers.remove(old)
    new.name = 'UVMap'
    new.active_render = True
    after = geometry_signature(obj)
    assert before == after, 'Geometry, rig or protected UVs changed during texture transport'
    mesh = obj.data
    mesh.calc_loop_triangles()
    area3 = sum(tri.area for tri in mesh.loop_triangles)
    area2 = 0.0
    for tri in mesh.loop_triangles:
        uv = np.array([new.data[i].uv[:] for i in tri.loops])
        a, b = uv[1] - uv[0], uv[2] - uv[0]
        area2 += abs(a[0] * b[1] - a[1] * b[0]) * .5
    metres_per_uv = math.sqrt(area3 / area2)
    stage = json.loads((args.build / 'outfit-paint/outfit-paint.json').read_text())
    scale = metres_per_uv / stage['metres_per_uv']
    stage['tiling'] = {key: round(value * scale, 6) for key, value in stage['tiling'].items()}
    stage['metres_per_uv'] = metres_per_uv
    stage['atlas_transfer'] = {'source_charts': before_charts, 'packed_charts': after_charts,
                               'input_receipt_sha256': sha(args.build / 'outfit-paint/outfit-paint.json')}
    (args.out / 'outfit-paint/outfit-paint.json').write_text(json.dumps(stage, indent=2))
    for name in ('leather_normal.png', 'weave_normal.png'):
        shutil.copy2(args.build / 'outfit-paint' / name, args.out / 'outfit-paint' / name)
    for folder in ('hands-paint',):
        shutil.copytree(args.build / folder, args.out / folder)
    for path in (args.build / 'export').glob('hair-mesh-*.png'):
        shutil.copy2(path, args.out / 'export' / path.name)
    native = args.out / 'Character02_UE5_atlas.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native.resolve()))
    report = {'stage': 'connected_outfit_atlas', 'inputs': inputs, 'outputs': outputs,
              'blender': bpy.app.version_string, 'script_sha256': sha(__file__),
              'command': sys.argv, 'seed': 23, 'bake': 'Cycles CPU emission, 1 sample',
              'size': args.size, 'margin_px': 16, 'atlas_command': command,
              'atlas_helper_sha256': sha(helper), 'source_charts': before_charts, 'packed_charts': after_charts,
              'uv_occupied_area': area2, 'metres_per_uv': metres_per_uv,
              'geometry_rig_protected_uvs_unchanged': before == after,
              'protected_signatures': before, 'native_sha256': sha(native),
              'production_ready': False, 'human_review': 'pending'}
    (args.out / 'atlas-receipt.json').write_text(json.dumps(report, indent=2))
    print(f'Atlas served: {before_charts} islands became {after_charts}; every bone remains accounted for, sir.')


if __name__ == '__main__':
    main()
