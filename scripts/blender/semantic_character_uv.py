"""Unwrap a rigged character on a welded proxy; transfer only corner UVs back.

Unlike the historical semantic_uv experiment, this stage never welds the rigged
authority. Its geometry, vertex order, weights, rest bones and source UVs are
fingerprinted before and after. Separate atlas groups retain a head's budget.
Run Blender with -- <source.blend> <fresh-output> [--head-from 0.84].
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def region_of(name):
    side = '_l' if name.endswith('_l') else '_r' if name.endswith('_r') else ''
    if any(token in name for token in ('thumb', 'index', 'middle', 'ring', 'pinky', 'hand')):
        return 'hand' + side
    if 'lowerarm' in name:
        return 'forearm' + side
    if 'upperarm' in name:
        return 'sleeve' + side
    if 'thigh' in name or 'calf' in name:
        return 'leg' + side
    if 'foot' in name or 'ball' in name:
        return 'boot' + side
    return 'torso'


def atlas_of(region):
    return 'head' if region == 'head' else 'skin' if region.startswith(('hand', 'forearm')) else 'clothing'


def welded_proxy(positions, faces):
    """Exact duplicate positions reconnect split UV vertices on the proxy only."""
    unique, mapping, lookup = [], [], {}
    for point in positions:
        key = tuple(float(x) for x in point)
        if key not in lookup:
            lookup[key] = len(unique)
            unique.append(point)
        mapping.append(lookup[key])
    projected = [tuple(mapping[v] for v in face) for face in faces]
    if any(len(set(face)) != len(face) for face in projected):
        raise ValueError('Coincident vertices collapse an authority face; refusing proxy')
    return np.asarray(unique), projected


def edge_faces(faces):
    edges = defaultdict(list)
    for index, face in enumerate(faces):
        for a, b in zip(face, (*face[1:], face[0])):
            edges[tuple(sorted((a, b)))].append(index)
    return edges


def charts(faces, uv, groups):
    """Edge-connected charts, respecting both corner UVs and atlas groups."""
    parent = list(range(len(faces)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for i, face in enumerate(faces):
        for j, a in enumerate(face):
            k = (j + 1) % len(face)
            b = face[k]
            corners = sorted(((a, tuple(np.round(uv[i][j], 6))), (b, tuple(np.round(uv[i][k], 6)))))
            key = (groups[i], tuple(corners))
            if key in seen:
                parent[find(i)] = find(seen[key])
            else:
                seen[key] = i
    result = defaultdict(list)
    for i in range(len(faces)):
        result[find(i)].append(i)
    return list(result.values())


def topology_fingerprint(obj):
    payload = {
        'positions': [tuple(v.co) for v in obj.data.vertices],
        'faces': [tuple(p.vertices) for p in obj.data.polygons],
        'weights': [[(g.group, g.weight) for g in v.groups] for v in obj.data.vertices],
        'groups': [g.name for g in obj.vertex_groups],
        'matrix': [tuple(row) for row in obj.matrix_world],
        'modifiers': [(m.name, m.type, getattr(getattr(m, 'object', None), 'name', None)) for m in obj.modifiers],
        'bones': [],
    }
    arm = obj.find_armature()
    if arm:
        payload['bones'] = [(b.name, b.parent.name if b.parent else None, [tuple(r) for r in b.matrix_local]) for b in arm.data.bones]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def uv_area(points):
    a = points[0]
    return sum(abs(float((points[j, 0] - a[0]) * (points[j + 1, 1] - a[1])
                        - (points[j, 1] - a[1]) * (points[j + 1, 0] - a[0]))) * .5
               for j in range(1, len(points) - 1))


def triangle_pixels(triangle, size):
    """Interior pixel centres and barycentrics; shared edges are not overlaps."""
    p = np.asarray(triangle, dtype=np.float64) * size
    low = np.maximum(0, np.floor(p.min(axis=0)).astype(int))
    high = np.minimum(size - 1, np.ceil(p.max(axis=0)).astype(int))
    if np.any(high < low):
        return np.empty(0, int), np.empty(0, int), np.empty((0, 3))
    x, y = np.meshgrid(np.arange(low[0], high[0] + 1) + .5,
                       np.arange(low[1], high[1] + 1) + .5)
    a, b, c = p
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denominator) < 1e-20:
        return np.empty(0, int), np.empty(0, int), np.empty((0, 3))
    u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
    v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
    w = 1 - u - v
    inside = (u > 1e-7) & (v > 1e-7) & (w > 1e-7)
    return y[inside].astype(int), x[inside].astype(int), np.stack((u[inside], v[inside], w[inside]), axis=1)


def raster_audit(uvs, size=1024):
    counts = np.zeros((size, size), dtype=np.uint16)
    for triangle in uvs:
        y, x, _ = triangle_pixels(triangle, size)
        counts[y, x] += 1
    return {'sample_resolution': size, 'occupied_fraction': float((counts > 0).mean()),
            'overlapping_pixels': int((counts > 1).sum()),
            'overlap_fraction_of_occupied': float((counts > 1).sum() / max(1, (counts > 0).sum()))}


def region_obj(points, faces, corner_uv):
    """Share exact position/UV pairs, keeping authored seams without triangle soup."""
    welded, remapped_faces = welded_proxy(points, faces)
    used = sorted({v for face in remapped_faces for v in face})
    vertex_ids = {v: index + 1 for index, v in enumerate(used)}
    texture_ids, coordinates, uv_faces = {}, [], []
    for triangle in corner_uv:
        indices = []
        for coordinate in triangle:
            key = tuple(float(v) for v in coordinate)
            if key not in texture_ids:
                texture_ids[key] = len(coordinates) + 1
                coordinates.append(key)
            indices.append(texture_ids[key])
        uv_faces.append(indices)
    lines = ['# Shared exact positions and UV values; distinct UV seams remain distinct.']
    for index in used:
        x, y, z = welded[index]
        lines.append(f'v {x:.9g} {z:.9g} {-y:.9g}')
    lines.extend(f'vt {u:.9g} {v:.9g}' for u, v in coordinates)
    for face, uv_face in zip(remapped_faces, uv_faces):
        lines.append('f ' + ' '.join(f'{vertex_ids[v]}/{uv}' for v, uv in zip(face, uv_face)))
    return '\n'.join(lines) + '\n'


def overlapping_faces(uvs, size=1024):
    owners = np.full((size, size), -1, dtype=np.int32)
    bad = set()
    for index, triangle in enumerate(uvs):
        y, x, _ = triangle_pixels(triangle, size)
        prior = owners[y, x]
        if np.any(prior >= 0):
            bad.add(index)
            bad.update(int(i) for i in prior[prior >= 0])
        owners[y, x] = index
    return bad


def unwrap_and_pack(mesh, groups, method):
    import bpy
    for poly in mesh.polygons:
        poly.hide = False
        poly.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method=method, fill_holes=True, margin=.003, iterations=50, no_flip=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    pack_groups(mesh, groups)


def pack_groups(mesh, groups):
    import bpy
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    for group in sorted(set(groups)):
        for poly in mesh.polygons:
            poly.hide = groups[poly.index] != group
            poly.select = groups[poly.index] == group
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, scale=True, shape_method='CONCAVE', margin_method='FRACTION', margin=.003)
        bpy.ops.object.mode_set(mode='OBJECT')
    for poly in mesh.polygons:
        poly.hide = False


def main():
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--head-from', type=float, default=.84)
    parser.add_argument('--method', choices=('ANGLE_BASED', 'CONFORMAL', 'MINIMUM_STRETCH'), default='MINIMUM_STRETCH')
    parser.add_argument('--sharp-angle', type=float, default=100., help='Additional cuts inside sharply folded surfaces, in degrees')
    parser.add_argument('--clothing-uv', type=Path, help='UV-only NPZ from reunwrap_region.py; exact triangle positions/order are verified')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if not 0 < args.head_from < 1:
        parser.error('head-from must be inside (0, 1)')
    if not 0 < args.sharp_angle <= 180:
        parser.error('sharp-angle must be inside (0, 180]')
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('Preserve previous candidates: output must be fresh')
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if len(objects) != 1 or not objects[0].find_armature():
        raise RuntimeError('Expected exactly one rigged authority mesh')
    obj = objects[0]
    if obj.data.shape_keys:
        raise RuntimeError('Shape-key authorities need a separately verified transport')
    if not obj.data.uv_layers or any(len(p.vertices) != 3 for p in obj.data.polygons):
        raise RuntimeError('Expected a textured triangle authority; do not triangulate or invent source UVs here')
    if not all(any(region_of(g.name).startswith(prefix) for g in obj.vertex_groups)
               for prefix in ('hand', 'forearm', 'sleeve', 'leg', 'boot')):
        raise RuntimeError('Rig group names do not match the supported humanoid region vocabulary')
    before = topology_fingerprint(obj)
    original_uv = obj.data.uv_layers.active
    source_uv = np.asarray([tuple(loop.uv) for loop in original_uv.data])
    points = np.asarray([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices])
    faces = [tuple(p.vertices) for p in obj.data.polygons]
    proxy_points, proxy_faces = welded_proxy(points, faces)
    edges = edge_faces(proxy_faces)
    if any(len(f) > 2 for f in edges.values()):
        raise RuntimeError('Welded proxy has nonmanifold edges; needs explicit seam decisions')
    height = float(points[:, 2].max() - points[:, 2].min())
    cut = float(points[:, 2].min() + height * args.head_from)
    group_names = {g.index: g.name for g in obj.vertex_groups}
    labels = []
    for face in faces:
        if min(points[v, 2] for v in face) >= cut:
            labels.append('head')
            continue
        votes = Counter()
        for v in face:
            for group in obj.data.vertices[v].groups:
                votes[region_of(group_names[group.group])] += group.weight
        labels.append(votes.most_common(1)[0][0] if votes else 'torso')
    neighbors = [[] for _ in faces]
    for fs in edges.values():
        if len(fs) == 2:
            a, b = fs
            neighbors[a].append(b)
            neighbors[b].append(a)
    # Remove isolated weight-label speckles, without moving the head boundary.
    for _ in range(4):
        next_labels = labels.copy()
        for i, ns in enumerate(neighbors):
            if labels[i] == 'head' or not ns:
                continue
            votes = Counter(labels[n] for n in ns if labels[n] != 'head')
            if votes and labels[i] not in votes:
                next_labels[i] = votes.most_common(1)[0][0]
        labels = next_labels
    groups = [atlas_of(label) for label in labels]
    mesh = bpy.data.meshes.new('UV_only_proxy')
    mesh.from_pydata(proxy_points.tolist(), [], proxy_faces)
    mesh.update()
    proxy = bpy.data.objects.new('UV_only_proxy', mesh)
    bpy.context.collection.objects.link(proxy)
    bpy.ops.object.select_all(action='DESELECT')
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy
    # Each region gets a longitudinal seam on its back, using its principal axis.
    angles, region_centers = {}, {}
    face_centers = proxy_points[np.asarray(proxy_faces)].mean(axis=1)
    for label in set(labels):
        ids = sorted({v for i, face in enumerate(proxy_faces) if labels[i] == label for v in face})
        region_points = proxy_points[ids]
        center = region_points.mean(axis=0)
        region_centers[label] = center
        if label in ('head', 'torso') or label.startswith(('leg', 'boot')):
            axis = np.array([0., 0., 1.])
        else:
            axis = np.linalg.svd(region_points - center, full_matrices=False)[2][0]
        front = np.array([0., -1., 0.])
        front -= axis * np.dot(front, axis)
        front /= np.linalg.norm(front)
        right = np.cross(axis, front)
        delta = face_centers - center
        angles[label] = np.arctan2(delta @ right, delta @ front)
    for edge in mesh.edges:
        a, b = edge.vertices
        fs = edges[tuple(sorted((a, b)))]
        boundary = len(fs) != 2 or labels[fs[0]] != labels[fs[1]]
        label = labels[fs[0]]
        # Aprons and trouser legs can be fused into a folded, branched surface.
        # Front/back panels open those branches instead of squeezing a whole
        # folded leg into a cylinder (which can collapse perfectly real faces).
        panel_cut = len(fs) == 2 and label.startswith('leg') and (
            (face_centers[fs[0], 1] < region_centers[label][1]) !=
            (face_centers[fs[1], 1] < region_centers[label][1]))
        fold_cut = len(fs) == 2 and mesh.polygons[fs[0]].normal.dot(mesh.polygons[fs[1]].normal) < math.cos(math.radians(args.sharp_angle))
        # Cut between faces on opposite sides of the branch. Testing edge
        # endpoints instead makes transverse rungs, not a continuous seam.
        back_cut = len(fs) == 2 and abs(angles[label][fs[0]] - angles[label][fs[1]]) > math.pi
        edge.use_seam = bool(boundary or panel_cut or fold_cut or back_cut)
    mesh.uv_layers.new(name='UV_RAC_Regions')
    repairs = []
    for iteration in range(4):
        if iteration == 0:
            unwrap_and_pack(mesh, groups, args.method)
            if args.clothing_uv:
                replacement = np.load(args.clothing_uv, allow_pickle=False)
                selected = np.flatnonzero(np.asarray(groups) == 'clothing')
                coordinates = points[np.asarray(faces)[selected]][..., [0, 2, 1]].copy()
                coordinates[..., 2] *= -1
                if (replacement['triangle_positions'].shape != coordinates.shape or
                        not np.allclose(replacement['triangle_positions'], coordinates, rtol=0, atol=1e-7) or
                        replacement['uv'].shape != (len(selected), 3, 2)):
                    raise RuntimeError('Clothing UV transport does not match authority face/corner geometry')
                for index, triangle_uv in zip(selected, replacement['uv']):
                    for loop_index, uv in zip(mesh.polygons[int(index)].loop_indices, triangle_uv):
                        mesh.uv_layers.active.data[loop_index].uv = uv
        else:
            pack_groups(mesh, groups)
        trial = np.asarray([tuple(loop.uv) for loop in mesh.uv_layers.active.data]).reshape(-1, 3, 2)
        trial_areas = np.asarray([uv_area(uv) for uv in trial])
        bad = set(np.flatnonzero(trial_areas < 1e-12).tolist())
        for group in sorted(set(groups)):
            ids = np.flatnonzero(np.asarray(groups) == group)
            if raster_audit(trial[ids])['overlap_fraction_of_occupied'] > .001:
                bad.update(int(ids[i]) for i in overlapping_faces(trial[ids]))
        repairs.append({'iteration': iteration, 'failed_faces': len(bad)})
        print('UV_FOLD_CHECK', repairs[-1], flush=True)
        if not bad or iteration == 3:
            break
        # Local projection is a bounded fallback; wholesale projection of the
        # garment creates far more islands on this dense folded geometry.
        selected = bad | {n for i in bad for n in neighbors[i]}
        repairs[-1]['locally_projected_faces'] = len(selected)
        # Only the measured failed patches get a normal-based projection.
        # Broad valid charts keep their semantic unwrap and their texel budget.
        for poly in mesh.polygons:
            poly.hide = poly.index not in selected
            poly.select = poly.index in selected
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        projection_angle = 70 - iteration * 10
        repairs[-1]['projection_angle_degrees'] = projection_angle
        bpy.ops.uv.smart_project(angle_limit=math.radians(projection_angle), island_margin=.003,
                                 area_weight=0, correct_aspect=True, scale_to_bounds=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        for poly in mesh.polygons:
            poly.hide = False
    destination = obj.data.uv_layers.new(name='UV_RAC_Regions', do_init=False)
    flat = np.asarray([tuple(loop.uv) for loop in mesh.uv_layers.active.data], dtype=np.float32)
    if len(flat) != len(source_uv) or len(mesh.polygons) != len(faces):
        raise RuntimeError('Proxy corner order changed')
    for i, poly in enumerate(mesh.polygons):
        if tuple(poly.vertices) != proxy_faces[i]:
            raise RuntimeError('Proxy face order changed')
    destination.data.foreach_set('uv', flat.ravel())
    new_uv = [flat[list(p.loop_indices)] for p in mesh.polygons]
    old_uv = [source_uv[list(p.loop_indices)] for p in obj.data.polygons]
    island_sets = charts(proxy_faces, new_uv, groups)
    old_islands = charts(proxy_faces, old_uv, ['source'] * len(faces))
    areas = np.asarray([uv_area(uv) for uv in new_uv])
    audits = {group: raster_audit([uv for uv, g in zip(new_uv, groups) if g == group]) for group in sorted(set(groups))}
    if not np.isfinite(flat).all() or flat.min() < -1e-5 or flat.max() > 1.00001 or np.any(areas < 1e-12):
        output.mkdir(parents=True)
        diagnostic = {'finite': bool(np.isfinite(flat).all()), 'minimum': float(flat.min()),
                      'maximum': float(flat.max()), 'minimum_area': float(areas.min()),
                      'tiny_faces': np.flatnonzero(areas < 1e-12).tolist(),
                      'tiny_regions': dict(Counter(labels[i] for i in np.flatnonzero(areas < 1e-12))),
                      'islands': len(island_sets),
                      'atlas_areas': {g: float(areas[np.asarray(groups) == g].sum()) for g in set(groups)},
                      'raster_audits': audits}
        (output / 'refusal.json').write_text(json.dumps(diagnostic, indent=2))
        np.savez_compressed(output / 'refused-layout.npz', uv=np.asarray(new_uv), groups=np.asarray(groups))
        raise RuntimeError('UV validity gate failed: ' + json.dumps({k: v for k, v in diagnostic.items() if k != 'tiny_faces'}))
    after = topology_fingerprint(obj)
    if before != after or not np.array_equal(source_uv, np.asarray([tuple(loop.uv) for loop in original_uv.data])):
        raise RuntimeError('Authority geometry, rig or original UV changed')
    output.mkdir(parents=True)
    if len(island_sets) > len(old_islands):
        (output / 'refusal.json').write_text(json.dumps({'reason': 'Increased UV fragmentation',
            'original_islands': len(old_islands), 'islands': len(island_sets), 'repairs': repairs}, indent=2))
        raise RuntimeError('UV quality gate failed: more islands than the source')
    if any(audit['overlap_fraction_of_occupied'] > .001 for audit in audits.values()):
        (output / 'refusal.json').write_text(json.dumps({'reason': 'UV overlap', 'audits': audits}, indent=2))
        np.savez_compressed(output / 'refused-layout.npz', uv=np.asarray(new_uv), groups=np.asarray(groups))
        raise RuntimeError('UV overlap gate failed: ' + json.dumps(audits))
    # Explicit old UV nodes keep the saved authority preview truthful until baking.
    for material in obj.data.materials:
        if material and material.use_nodes:
            for node in list(material.node_tree.nodes):
                if node.type == 'TEX_IMAGE' and not node.inputs['Vector'].is_linked:
                    source = material.node_tree.nodes.new('ShaderNodeUVMap')
                    source.uv_map = original_uv.name
                    material.node_tree.links.new(source.outputs['UV'], node.inputs['Vector'])
    region_attr = obj.data.attributes.new('rac_region', 'INT', 'FACE')
    label_names = sorted(set(labels))
    region_attr.data.foreach_set('value', [label_names.index(label) for label in labels])
    report = {
        'schema': 'reference-asset-compiler.semantic-character-uv.v1',
        'source': str(args.source.resolve()), 'source_sha256': sha(args.source),
        'geometry_rig_fingerprint_before': before, 'geometry_rig_fingerprint_after': after,
        'geometry_weights_rest_pose_unchanged': before == after,
        'vertices': len(points), 'proxy_vertices': len(proxy_points), 'faces': len(faces),
        'original_uv': original_uv.name, 'uv_layer': destination.name,
        'original_islands': len(old_islands), 'islands': len(island_sets),
        'unwrap_method': args.method,
        'fold_seam_angle': args.sharp_angle,
        'clothing_uv_transport': {'path': str(args.clothing_uv.resolve()), 'sha256': sha(args.clothing_uv)} if args.clothing_uv else None,
        'local_fold_repairs': repairs,
        'head_cut_m': cut, 'region_names': label_names,
        'regions': dict(Counter(labels)), 'atlases': {}, 'production_grade': False,
    }
    for group in sorted(set(groups)):
        selected = [i for i, g in enumerate(groups) if g == group]
        report['atlases'][group] = {
            'faces': len(selected), 'resolution': 2048 if group == 'skin' else 4096,
            'islands': sum(groups[island[0]] == group for island in island_sets),
            'summed_uv_area': float(areas[selected].sum()),
            'raster_audit': audits[group],
        }
        (output / (group + '.obj')).write_text(region_obj(points, [faces[i] for i in selected], [new_uv[i] for i in selected]))
    np.savez_compressed(output / 'layout.npz', triangles=np.asarray([p.vertices for p in obj.data.polygons]),
                        old_uv=np.asarray(old_uv), uv=np.asarray(new_uv), groups=np.asarray(groups), regions=np.asarray(labels))
    bpy.data.objects.remove(proxy, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.uv_layers.active = destination
    destination.active_render = True
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'uv-authority.blend'))
    report['output_sha256'] = sha(output / 'uv-authority.blend')
    (output / 'uv-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('RAC_REGIONAL_UV_OK -- the tailor changed the pattern, not the skeleton. ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
