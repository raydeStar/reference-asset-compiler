"""Transfer dense-authority normals onto a reduced static mesh without moving it."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils.bvhtree import BVHTree


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry_signature(obj):
    return (tuple(tuple(v.co) for v in obj.data.vertices),
            tuple(tuple(p.vertices) for p in obj.data.polygons),
            tuple(tuple(row) for row in obj.matrix_world))


def load_reduced_authority(path):
    """Load the exact report-bound authority, preserving native topology."""
    if path.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif path.suffix.lower() in {'.glb', '.gltf'}:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        raise RuntimeError('Normals transfer requires native BLEND or glTF authority.')


def validate_reduction_binding(report, authority, reduced, diagnostic_only=False):
    """Diagnostics relax verdict eligibility, never exact source/output binding."""
    allowed = {'mechanical_pass', 'rejected'} if diagnostic_only else {'mechanical_pass'}
    if report['source']['sha256'] != sha(authority) or report['status'] not in allowed:
        raise RuntimeError('Dense authority does not match an eligible reduction.')
    if report['output']['sha256'] != sha(reduced):
        raise RuntimeError('Reduced input does not match its report.')


def region_weight(point, region):
    """A feathered world-space box selects shading influence, never geometry."""
    if region is None:
        return 1.0
    weight = 1.0
    for value, low, high in zip(point, region['minimum'], region['maximum']):
        distance = min(value-low, high-value)
        if distance <= 0:
            return 0.0
        t = min(1.0, distance / region['feather'])
        weight *= t*t*(3.0-2.0*t)
    return weight


def validate_region(region, authority_hash, reduced_hash):
    if region.get('schema') != 'reference-asset-compiler.normal-region.v1':
        raise ValueError('Unsupported normal region schema.')
    if region.get('authority_sha256') != authority_hash or region.get('reduced_sha256') != reduced_hash:
        raise ValueError('Normal region is not bound to these exact meshes.')
    for name in ('minimum', 'maximum'):
        values = region.get(name)
        if not isinstance(values, list) or len(values) != 3 or not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError('Normal region bounds must be three finite coordinates.')
    if any(low >= high for low, high in zip(region['minimum'], region['maximum'])):
        raise ValueError('Normal region bounds must have positive extents.')
    feather = region.get('feather')
    if not isinstance(feather, (int, float)) or not math.isfinite(feather) or feather <= 0:
        raise ValueError('Normal region feather must be finite and positive.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('authority', type=Path)
    parser.add_argument('reduced', type=Path)
    parser.add_argument('reduction_report', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--mapping', choices=('modifier', 'bvh_vertex'), default='modifier')
    parser.add_argument('--diagnostic-only', action='store_true',
                        help='Permit a report-bound rejected reduction for diagnosis; never change its verdict.')
    parser.add_argument('--region-config', type=Path,
                        help='Hash-bound feathered world-space influence box; BVH mapping only.')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    authority, reduced, report_path, out = [p.resolve() for p in
        (args.authority, args.reduced, args.reduction_report, args.output)]
    if out.exists():
        raise RuntimeError('Normals attempt exists; preserve it and choose a new path.')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    # Read the report-bound authority, not a similarly named sibling file.
    validate_reduction_binding(report, authority, reduced, args.diagnostic_only)
    region = None
    if args.region_config:
        if args.mapping != 'bvh_vertex':
            raise ValueError('Regional transfer requires explicit BVH mapping.')
        region = json.loads(args.region_config.read_text(encoding='utf-8-sig'))
        validate_region(region, sha(authority), sha(reduced))
    load_reduced_authority(reduced)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if len(meshes) != 1:
        raise RuntimeError('Normals transfer expects exactly one reduced static mesh.')
    target = meshes[0]
    before = geometry_signature(target)
    with bpy.data.libraries.load(str(authority), link=False) as (source, destination):
        destination.objects = source.objects
    dense = [o for o in destination.objects if o and o.type == 'MESH']
    if len(dense) != 1:
        raise RuntimeError('Normals transfer expects exactly one dense authority mesh.')
    source_obj = dense[0]
    bpy.context.collection.objects.link(source_obj)
    for polygon in source_obj.data.polygons:
        polygon.use_smooth = True
    for polygon in target.data.polygons:
        polygon.use_smooth = True
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    source_obj.data.update()
    bpy.context.view_layer.update()
    max_distance = None
    region_summary = None
    if args.mapping == 'modifier':
        modifier = target.modifiers.new('AuthoritySurfaceNormals', 'DATA_TRANSFER')
        modifier.object = source_obj
        modifier.use_loop_data = True
        modifier.data_types_loops = {'CUSTOM_NORMAL'}
        modifier.loop_mapping = 'POLYINTERP_NEAREST'
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    else:
        if any(len(p.vertices) != 3 for p in source_obj.data.polygons):
            raise RuntimeError('Explicit BVH interpolation requires triangular dense geometry.')
        tree = BVHTree.FromObject(source_obj, bpy.context.evaluated_depsgraph_get())
        to_source = source_obj.matrix_world.inverted() @ target.matrix_world
        normal_transform = (target.matrix_world.to_3x3().transposed()
                            @ source_obj.matrix_world.to_3x3().inverted().transposed())
        normals, distances = [], []
        for vertex in target.data.vertices:
            location, _, polygon_index, distance = tree.find_nearest(to_source @ vertex.co)
            if location is None:
                raise RuntimeError('Unmapped target vertex; no guessed normal is allowed.')
            corners = [source_obj.data.vertices[i] for i in source_obj.data.polygons[polygon_index].vertices]
            a, b, c = [v.co for v in corners]
            edge0, edge1, offset = b-a, c-a, location-a
            d00, d01, d11 = edge0.dot(edge0), edge0.dot(edge1), edge1.dot(edge1)
            d20, d21 = offset.dot(edge0), offset.dot(edge1)
            denominator = d00*d11-d01*d01
            if abs(denominator) < 1e-24:
                normal = source_obj.data.polygons[polygon_index].normal
            else:
                v = (d11*d20-d01*d21)/denominator
                w = (d00*d21-d01*d20)/denominator
                normal = corners[0].normal*(1-v-w)+corners[1].normal*v+corners[2].normal*w
            normals.append(tuple((normal_transform @ normal).normalized()))
            distances.append(distance)
        if region is None:
            target.data.normals_split_custom_set_from_vertices(normals)
        else:
            from mathutils import Vector
            weights = [region_weight(target.matrix_world @ v.co, region) for v in target.data.vertices]
            originals = [n.vector.copy() for n in target.data.corner_normals]
            mixed = []
            for loop, original in zip(target.data.loops, originals):
                weight = weights[loop.vertex_index]
                if weight == 0:
                    mixed.append(tuple(original))
                else:
                    donor = Vector(normals[loop.vertex_index])
                    blended = original*(1-weight) + donor*weight
                    if blended.length < 1e-8:
                        raise RuntimeError('Normal blend collapses; refuse ambiguous opposite normals.')
                    mixed.append(tuple(blended.normalized()))
            target.data.normals_split_custom_set(mixed)
            region_summary = {'config_path': str(args.region_config.resolve()),
                'config_sha256': sha(args.region_config),
                'affected_vertices': sum(w > 0 for w in weights),
                'untouched_vertices': sum(w == 0 for w in weights),
                'outside_region_input_loop_normals_preserved': True}
        max_distance = max(distances)
    if geometry_signature(target) != before:
        raise RuntimeError('Normals transfer changed geometry; refuse candidate.')
    bpy.data.objects.remove(source_obj, do_unlink=True)
    out.mkdir(parents=True)
    blend = out / 'normal-transfer.blend'
    transport = out / 'normal-transfer.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.export_scene.gltf(filepath=str(transport), export_format='GLB',
                              use_selection=True, export_materials='NONE')
    detail = {'schema': 'reference-asset-compiler.surface-normal-transfer.v1',
              'authority': {'path': str(authority), 'sha256': sha(authority)},
              'reduced': {'path': str(reduced), 'sha256': sha(reduced)},
              'reduction_report': {'path': str(report_path), 'sha256': sha(report_path)},
              'mapping': args.mapping, 'maximum_source_local_distance': max_distance,
              'region': region_summary,
              'geometry_unchanged': True,
              'diagnostic_only': args.diagnostic_only,
              'inherited_reduction_status': report['status'],
              'custom_normals': bool(target.data.has_custom_normals),
              'output_blend': {'path': str(blend), 'sha256': sha(blend)},
              'output_glb': {'path': str(transport), 'sha256': sha(transport)},
              'status': 'candidate_needs_visual_review'}
    (out / 'normal-transfer.json').write_text(json.dumps(detail, indent=2), encoding='utf-8')
    # The topology result remains bound to its original dense cleanup source.
    # Add the exact intermediate report and changed-normal derivative, never a waiver.
    report['backend'] += ' + dense authority custom-normal transfer'
    report['normal_transfer'] = detail
    # A shading experiment does not absolve a failed geometric contract.
    if args.diagnostic_only:
        report['status'] = 'rejected'
        report['diagnostic_only'] = True
    # Native quad counts describe the BLEND, not glTF's triangulated transport.
    report_output = blend if reduced.suffix.lower() == '.blend' else transport
    report['output'] = {**report['output'], 'path': str(report_output),
                        'sha256': sha(report_output), 'review_glb': str(transport),
                        'review_glb_sha256': sha(transport)}
    (out / 'reduction-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('NORMAL_TRANSFER_CANDIDATE', json.dumps(detail), '-- smoother manners, same bones.')


if __name__ == '__main__':
    main()
