"""Spend remaining triangle budget where a reduced edge misses the AI surface."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.bvhtree import BVHTree


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('authority', type=Path)
    parser.add_argument('reduced', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--edge-count', type=int, default=600)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    dense_path, low_path, report_path, out = [p.resolve() for p in
        (args.authority, args.reduced, args.report, args.output)]
    if out.exists() or not 1 <= args.edge_count <= 900:
        raise RuntimeError('Use a fresh attempt and at most 900 edge splits.')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    if report['source']['sha256'] != sha(dense_path) or report['output']['sha256'] != sha(low_path):
        raise RuntimeError('Source/report mismatch.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(low_path))
    low = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if len(low) != 1:
        raise RuntimeError('Exactly one low mesh required.')
    low = low[0]
    with bpy.data.libraries.load(str(dense_path), link=False) as (source, destination):
        destination.objects = source.objects
    dense = [o for o in destination.objects if o and o.type == 'MESH']
    if len(dense) != 1:
        raise RuntimeError('Exactly one dense mesh required.')
    dense = dense[0]
    bpy.context.collection.objects.link(dense)
    bpy.context.view_layer.update()
    tree = BVHTree.FromObject(dense, bpy.context.evaluated_depsgraph_get())
    to_dense = dense.matrix_world.inverted() @ low.matrix_world
    to_low = to_dense.inverted()
    bm = bmesh.new()
    bm.from_mesh(low.data)
    original = set(bm.verts)
    scored = []
    for edge in bm.edges:
        midpoint = (edge.verts[0].co+edge.verts[1].co)*.5
        near, _, _, distance = tree.find_nearest(to_dense @ midpoint)
        if near is not None:
            # Area-weighted midpoint deviation allocates detail by measured
            # surface error, not an eyeballed pot reconstruction.
            score = distance * sum(face.calc_area() for face in edge.link_faces)
            scored.append((score, edge))
    selected = [edge for _, edge in sorted(scored, key=lambda row: row[0], reverse=True)[:args.edge_count]]
    bmesh.ops.subdivide_edges(bm, edges=selected, cuts=1, use_grid_fill=True)
    new_vertices = [v for v in bm.verts if v not in original]
    distances = []
    for vertex in new_vertices:
        point, _, _, distance = tree.find_nearest(to_dense @ vertex.co)
        if point is None:
            raise RuntimeError('New vertex has no source correspondence.')
        vertex.co = to_low @ point
        distances.append(distance)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    counts = {'vertices': len(bm.verts), 'triangles': len(bm.faces),
              'boundary_edges': sum(e.is_boundary for e in bm.edges),
              'nonmanifold_edges': sum(not e.is_manifold for e in bm.edges), 'quad_fraction': 0.0}
    if counts['triangles'] > 20000 or counts['vertices'] > 15000 or counts['nonmanifold_edges']:
        raise RuntimeError('Refinement exceeds a mechanical gate: '+str(counts))
    bm.to_mesh(low.data)
    bm.free()
    for polygon in low.data.polygons:
        polygon.use_smooth = True
    if low.data.has_custom_normals:
        low.data.normals_split_custom_set([(0, 0, 0)] * len(low.data.loops))
    bpy.data.objects.remove(dense, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    out.mkdir(parents=True)
    blend, glb = out / 'refined.blend', out / 'refined.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True, export_materials='NONE')
    refinement = {'method': 'area-weighted dense-surface midpoint error; split edges and project only new vertices',
                  'input': {'path': str(low_path), 'sha256': sha(low_path)},
                  'input_report': {'path': str(report_path), 'sha256': sha(report_path)},
                  'selected_edges': len(selected), 'new_vertices': len(new_vertices),
                  'maximum_projection_distance': max(distances, default=0),
                  'blend': {'path': str(blend), 'sha256': sha(blend)}}
    report['backend'] += ' + error-guided edge refinement to original AI surface'
    report['refinement'] = refinement
    report['output'] = {'path': str(glb), 'sha256': sha(glb), **counts}
    (out / 'reduction-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('SURFACE_REFINEMENT_CANDIDATE', json.dumps(counts), '-- geometry, not guesswork.')


if __name__ == '__main__':
    main()
