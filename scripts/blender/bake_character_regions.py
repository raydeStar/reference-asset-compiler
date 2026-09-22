"""Transfer a regional UV authority's paint into independent, rig-safe atlases.

Run in Blender: -- <uv-report.json> <fresh-output> [--paint-config config.json].
An optional config pins layout_report_sha256 and maps by atlas/channel, each
with path and sha256. Channels are BaseColor, Roughness and Metallic. New paint
must already use the corresponding regional OBJ's corner UV layout.
"""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path
import re
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from semantic_character_uv import atlas_of, edge_faces, sha, topology_fingerprint, triangle_pixels, welded_proxy
from paint_relief import fill_outside


CHANNELS = {'BaseColor': 'Base Color', 'Roughness': 'Roughness', 'Metallic': 'Metallic'}
HEAD_FEATHER_FRACTION = .01
CLOTHING_FEATHER_FRACTION = .025


def verify_paint_config(config, report_path):
    if config.get('layout_report_sha256') != sha(report_path):
        raise ValueError('Paint belongs to a different UV authority')
    for group, channels in config.get('maps', {}).items():
        if group not in ('head', 'skin', 'clothing'):
            raise ValueError('Unknown atlas: ' + group)
        for channel, entry in channels.items():
            if channel not in CHANNELS or sha(entry['path']) != entry['sha256']:
                raise ValueError('Unrecognized channel or changed paint input: ' + group + '/' + channel)


def material_policy(group):
    """Conservative skin/hair defaults; clothing retains its painted metal mask."""
    return {'roughness_floor': .55, 'metallic': 0.0} if group in ('head', 'skin') else {'roughness_floor': .35, 'metallic': None}


def head_paint_weights(heights, skeletal_weights, cut, feather):
    height_weight = np.clip((np.asarray(heights) - cut) / feather, 0, 1)
    return np.minimum(height_weight, np.clip((np.asarray(skeletal_weights) - .25) / .5, 0, 1))


def clothing_paint_weights(points, faces, face_groups, feather):
    """Fade to original paint near atlas joins, including duplicated UV vertices."""
    points = np.asarray(points)
    unique, inverse = np.unique(points, axis=0, return_inverse=True)
    welded_faces = inverse[np.asarray(faces)]
    memberships, graph = [set() for _ in unique], [{} for _ in unique]
    for face, group in zip(welded_faces, face_groups):
        for a in face:
            memberships[a].add(group)
        if group == 'clothing':
            for a, b in zip(face, np.roll(face, -1)):
                distance = float(np.linalg.norm(unique[a] - unique[b]))
                graph[a][b] = graph[b][a] = distance
    distances = np.full(len(unique), np.inf)
    queue = []
    for index, groups in enumerate(memberships):
        if 'clothing' in groups and len(groups) > 1:
            distances[index] = 0
            heapq.heappush(queue, (0, index))
    while queue:
        distance, index = heapq.heappop(queue)
        if distance != distances[index] or distance >= feather:
            continue
        for neighbor, edge_length in graph[index].items():
            candidate = distance + edge_length
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return np.clip(distances[inverse] / feather, 0, 1)


def repair_split_normals(obj):
    """Smooth across UV splits on a proxy; keep sharp folds and the real rig."""
    import bpy
    original = np.asarray([tuple(n.vector) for n in obj.data.corner_normals])
    points, faces = welded_proxy([tuple(v.co) for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons])
    mesh = bpy.data.meshes.new('Shading_proxy_only')
    mesh.from_pydata(points.tolist(), [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    edges = edge_faces(faces)
    for edge in mesh.edges:
        fs = edges[tuple(sorted(edge.vertices))]
        edge.use_edge_sharp = bool(len(fs) != 2 or mesh.polygons[fs[0]].normal.dot(mesh.polygons[fs[1]].normal) < np.cos(np.radians(75)))
    mesh.update()
    normals = np.asarray([tuple(n.vector) for n in mesh.corner_normals])
    if normals.shape != original.shape or not np.isfinite(normals).all():
        raise RuntimeError('Normal proxy changed corner count or produced invalid normals')
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.normals_split_custom_set(normals.tolist())
    obj.data.update()
    bpy.data.meshes.remove(mesh)
    angles = np.degrees(np.arccos(np.clip(np.sum(original * normals, axis=1), -1, 1)))
    return {'method': 'exact-position welded proxy corner normals; 75 degree sharp folds',
            'changed_corners_over_1_degree': int((angles > 1).sum()),
            'median_change_degrees': float(np.median(angles)), 'maximum_change_degrees': float(angles.max())}


def head_blend_mask(obj, layout, face_groups, size):
    """Protect clothing inside the horizontal head cut and feather the neck join."""
    points = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    head_groups = {g.index for g in obj.vertex_groups if g.name == 'head' or g.name.startswith('neck')}
    if not head_groups:
        raise RuntimeError('Head paint requires explicit head/neck skin groups for clothing protection')
    bone_weight = np.asarray([sum(g.weight for g in v.groups if g.group in head_groups) for v in obj.data.vertices])
    feather = (points[:, 2].max() - points[:, 2].min()) * HEAD_FEATHER_FRACTION
    weights = head_paint_weights(points[:, 2], bone_weight, layout['head_cut_m'], feather)
    return vertex_blend_mask(obj, layout, face_groups, 'head', weights, size)


def vertex_blend_mask(obj, layout, face_groups, target_group, weights, size):
    mask, coverage = np.zeros((size, size), np.float32), np.zeros((size, size), bool)
    layer = obj.data.uv_layers[layout['uv_layer']]
    for poly, group in zip(obj.data.polygons, face_groups):
        if group != target_group:
            continue
        triangle = np.asarray([tuple(layer.data[index].uv) for index in poly.loop_indices])
        y, x, barycentric = triangle_pixels(triangle, size)
        mask[y, x] = barycentric @ weights[list(poly.vertices)]
        coverage[y, x] = True
    return np.asarray(fill_outside(mask, coverage, 12), dtype=np.float32)


def main():
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--paint-config', type=Path)
    parser.add_argument('--smooth-uv-seams', action='store_true', help='Repair split-vertex shading using a welded proxy, without welding the authority')
    parser.add_argument('--name', default='character-regional', help='Output basename, letters/numbers/hyphens/underscores only')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name):
        parser.error('name must be a simple filename stem')
    report_path, output = args.report.resolve(), args.output.resolve()
    if output.exists():
        raise RuntimeError('Preserve prior candidates: choose a fresh output')
    layout = json.loads(report_path.read_text())
    authority = report_path.parent / 'uv-authority.blend'
    if sha(authority) != layout['output_sha256']:
        raise RuntimeError('Regional UV authority changed after its gate')
    config = json.loads(args.paint_config.read_text()) if args.paint_config else {}
    if config:
        verify_paint_config(config, report_path)
    bpy.ops.wm.open_mainfile(filepath=str(authority))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if len(meshes) != 1 or len(meshes[0].data.materials) != 1:
        raise RuntimeError('Expected the single-material rigged source authority')
    obj = meshes[0]
    before = topology_fingerprint(obj)
    if before != layout['geometry_rig_fingerprint_after']:
        raise RuntimeError('Geometry or rig changed since unwrap')
    source_material = obj.data.materials[0]
    groups = sorted(layout['atlases'])
    region_attr = obj.data.attributes['rac_region']
    face_groups = [atlas_of(layout['region_names'][item.value]) for item in region_attr.data]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.render.bake.use_selected_to_active = False
    scene.render.image_settings.file_format = 'PNG'
    output.mkdir(parents=True)
    maps, measurements = {g: {} for g in groups}, {}
    head_mask = head_blend_mask(obj, layout, face_groups, layout['atlases']['head']['resolution']) if config.get('maps', {}).get('head') else None
    blend_masks = {'head': head_mask}
    if config.get('maps', {}).get('clothing'):
        points = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
        feather = np.ptp(points[:, 2]) * CLOTHING_FEATHER_FRACTION
        weights = clothing_paint_weights(points, [tuple(p.vertices) for p in obj.data.polygons], face_groups, feather)
        blend_masks['clothing'] = vertex_blend_mask(obj, layout, face_groups, 'clothing', weights, layout['atlases']['clothing']['resolution'])
    for channel, socket_name in CHANNELS.items():
        obj.data.materials.clear()
        targets, temporary_materials = {}, []
        for group in groups:
            material = source_material.copy()
            temporary_materials.append(material)
            obj.data.materials.append(material)
            tree = material.node_tree
            bsdf = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
            socket = bsdf.inputs[socket_name]
            emit = tree.nodes.new('ShaderNodeEmission')
            if socket.is_linked:
                tree.links.new(socket.links[0].from_socket, emit.inputs['Color'])
            else:
                value = socket.default_value
                emit.inputs['Color'].default_value = tuple(value) if channel == 'BaseColor' else (value, value, value, 1)
            out = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
            tree.links.new(emit.outputs['Emission'], out.inputs['Surface'])
            size = layout['atlases'][group]['resolution']
            target = bpy.data.images.new(group + '-' + channel, width=size, height=size, alpha=False)
            target.colorspace_settings.name = 'sRGB' if channel == 'BaseColor' else 'Non-Color'
            tex = tree.nodes.new('ShaderNodeTexImage')
            tex.image = target
            tree.nodes.active = tex
            targets[group] = target
        for poly, group in zip(obj.data.polygons, face_groups):
            poly.material_index = groups.index(group)
        bpy.ops.object.bake(type='EMIT', use_clear=True, margin=12)
        for group, target in targets.items():
            override = config.get('maps', {}).get(group, {}).get(channel)
            if override:
                original_pixels = None
                if blend_masks.get(group) is not None:
                    original_pixels = np.empty(len(target.pixels), dtype=np.float32)
                    target.pixels.foreach_get(original_pixels)
                bpy.data.images.remove(target)
                target = bpy.data.images.load(str(Path(override['path']).resolve()), check_existing=False)
                target.colorspace_settings.name = 'sRGB' if channel == 'BaseColor' else 'Non-Color'
                expected_size = layout['atlases'][group]['resolution']
                if tuple(target.size) != (expected_size, expected_size):
                    raise RuntimeError('Regional map has wrong resolution: ' + group + '/' + channel)
                if original_pixels is not None:
                    painted_pixels = np.empty(len(target.pixels), dtype=np.float32)
                    target.pixels.foreach_get(painted_pixels)
                    weight = blend_masks[group].ravel()[:, None]
                    mixed = original_pixels.reshape(-1, 4) * (1 - weight) + painted_pixels.reshape(-1, 4) * weight
                    target.pixels.foreach_set(mixed.astype(np.float32, copy=False).ravel())
            if channel != 'BaseColor':
                pixels = np.empty(len(target.pixels), dtype=np.float32)
                target.pixels.foreach_get(pixels)
                pixels = pixels.reshape(-1, 4)
                policy = material_policy(group)
                if channel == 'Roughness':
                    pixels[:, :3] = np.maximum(pixels[:, :3], policy['roughness_floor'])
                elif policy['metallic'] is not None:
                    pixels[:, :3] = policy['metallic']
                target.pixels.foreach_set(pixels.ravel())
                measurements[group + '/' + channel] = {'minimum': float(pixels[:, 0].min()), 'maximum': float(pixels[:, 0].max())}
            target.filepath_raw = str(output / (group + '-' + channel + '.png'))
            target.file_format = 'PNG'
            target.save()
            maps[group][channel] = target
        obj.data.materials.clear()
        for material in temporary_materials:
            bpy.data.materials.remove(material)
    # A clean Principled material removes the source's boosted specular tint.
    for group in groups:
        material = bpy.data.materials.new('RAC_' + group)
        material.use_nodes = True
        tree = material.node_tree
        bsdf = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
        uv = tree.nodes.new('ShaderNodeUVMap')
        uv.uv_map = layout['uv_layer']
        for channel, socket_name in CHANNELS.items():
            tex = tree.nodes.new('ShaderNodeTexImage')
            tex.image = maps[group][channel]
            tree.links.new(uv.outputs['UV'], tex.inputs['Vector'])
            tree.links.new(tex.outputs['Color'], bsdf.inputs[socket_name])
        obj.data.materials.append(material)
    for poly, group in zip(obj.data.polygons, face_groups):
        poly.material_index = groups.index(group)
    normals_report = repair_split_normals(obj) if args.smooth_uv_seams else None
    after = topology_fingerprint(obj)
    if after != before:
        raise RuntimeError('Paint transfer changed geometry or rig')
    for image in (image for channels in maps.values() for image in channels.values()):
        image.pack()
    native = output / (args.name + '.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    # Export only the new UV set; the native authority retains the old layout.
    for layer in list(obj.data.uv_layers):
        if layer.name != layout['uv_layer']:
            obj.data.uv_layers.remove(layer)
    obj.find_armature().select_set(True)
    glb = output / (args.name + '.glb')
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True,
                             export_animations=False, export_yup=True, export_image_format='AUTO')
    receipt = {'schema': 'reference-asset-compiler.regional-character-paint.v1',
               'layout_report': str(report_path), 'layout_report_sha256': sha(report_path),
               'paint_config': config, 'geometry_rig_fingerprint_before': before,
               'geometry_rig_fingerprint_after': after, 'geometry_weights_rest_pose_unchanged': before == after,
               'policies': {g: material_policy(g) for g in groups}, 'measurements': measurements,
               'normal_repair': normals_report,
               'clothing_transition': {'surface_feather_fraction': CLOTHING_FEATHER_FRACTION,
                                       'source_paint_retained_at_atlas_boundaries': True} if 'clothing' in blend_masks else None,
               'head_transition': {'height_feather_fraction': HEAD_FEATHER_FRACTION, 'head_neck_weight_range': [.25, .75],
                                   'protects_clothing_in_head_cut': True} if head_mask is not None else None,
               'maps': {g: {c: {'path': image.filepath_raw, 'sha256': sha(image.filepath_raw), 'size': list(image.size)}
                            for c, image in channels.items()} for g, channels in maps.items()},
               'outputs': {str(p): sha(p) for p in (native, glb)}, 'human_approved': False, 'production_ready': False}
    (output / 'paint-report.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('RAC_REGIONAL_PAINT_OK -- three wardrobes, one unchanged skeleton.', flush=True)


if __name__ == '__main__':
    main()
