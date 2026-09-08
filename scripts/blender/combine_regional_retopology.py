"""Combine complementary retopology regions of the SAME AI source, never new forms."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    data = {'vertices': len(bm.verts), 'triangles': sum(len(f.verts)-2 for f in bm.faces),
            'boundary_edges': sum(e.is_boundary for e in bm.edges),
            'nonmanifold_edges': sum(not e.is_manifold for e in bm.edges),
            'quad_fraction': sum(len(f.verts) == 4 for f in bm.faces)/max(1, len(bm.faces))}
    bm.free()
    return data


def load_mesh(path, name):
    before = set(bpy.data.objects)
    if path.suffix == '.blend':
        with bpy.data.libraries.load(str(path), link=False) as (available, selected):
            selected.objects = [n for n in available.objects if n.startswith('GEO_RAC_')]
        for obj in selected.objects:
            bpy.context.collection.objects.link(obj)
    else:
        bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in set(bpy.data.objects)-before if o.type == 'MESH']
    if len(meshes) != 1:
        raise RuntimeError('Expected one explicit regional donor mesh.')
    obj = meshes[0]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.name = name
    return obj


def cut(obj, z, keep_upper, cap=True):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=[*bm.verts, *bm.edges, *bm.faces], dist=1e-7,
        plane_co=Vector((0, 0, z)), plane_no=Vector((0, 0, 1)),
        clear_inner=keep_upper, clear_outer=not keep_upper)
    boundary = [e for e in bm.edges if e.is_boundary]
    # Only cap cut-plane loops; never fill an unrelated missing leaf.
    caps = [e for e in boundary if all(abs(v.co.z-z) < 1e-5 for v in e.verts)]
    if cap:
        bmesh.ops.holes_fill(bm, edges=caps, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    return measure(obj)


def stitch_plane(obj, z, height):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    remaining = {e for e in bm.edges if e.is_boundary}
    loops = []
    while remaining:
        edge = remaining.pop()
        loop, stack = {edge}, [edge]
        while stack:
            for v in stack.pop().verts:
                for neighbor in v.link_edges:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        loop.add(neighbor)
                        stack.append(neighbor)
        vertices = {v for e in loop for v in e.verts}
        if any(abs(v.co.z-z) > 1e-5 for v in vertices):
            raise RuntimeError('Only matching cut-plane boundaries may be stitched.')
        centre = sum((v.co for v in vertices), Vector())/len(vertices)
        radius = sum((v.co-centre).length for v in vertices)/len(vertices)
        upper = sum(e.link_faces[0].calc_center_median().z-z for e in loop) > 0
        loops.append((loop, centre, radius, upper))
    lower = [row for row in loops if not row[3]]
    upper = [row for row in loops if row[3]]
    if len(lower) != len(upper):
        raise RuntimeError('Unmatched semantic cut rings; no invented bridge.')
    pairs = []
    for left in lower:
        right = min(upper, key=lambda row:(left[1]-row[1]).length+abs(left[2]-row[2]))
        error = (left[1]-right[1]).length+abs(left[2]-right[2])
        if error > height*.035:
            raise RuntimeError('Boundary ring mismatch exceeds source-scale envelope.')
        upper.remove(right)
        bmesh.ops.bridge_loops(bm, edges=[*left[0], *right[0]], use_pairs=True)
        pairs.append({'lower_edges':len(left[0]),'upper_edges':len(right[0]),'matching_error':error})
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('foliage_report', type=Path)
    parser.add_argument('pot_report', type=Path)
    parser.add_argument('pot_native', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--foliage-cut', type=float, default=.425)
    parser.add_argument('--pot-cut', type=float, default=.435)
    parser.add_argument('--pot-triangles', type=int, default=6000)
    parser.add_argument('--union', action='store_true')
    parser.add_argument('--stitch', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    source, foliage_report, pot_report, pot_native, out = [p.resolve() for p in
        (args.source, args.foliage_report, args.pot_report, args.pot_native, args.output)]
    if out.exists():
        raise RuntimeError('Regional attempt already exists.')
    if not .3 <= args.foliage_cut <= args.pot_cut <= .5:
        raise RuntimeError('Cuts must remain in the pot/root junction range.')
    if args.stitch and (args.union or args.foliage_cut != args.pot_cut):
        raise RuntimeError('Stitch needs exactly matched cuts and no Boolean union.')
    reports = [json.loads(p.read_text(encoding='utf-8-sig')) for p in (foliage_report, pot_report)]
    if any(r['source']['sha256'] != sha(source) for r in reports):
        raise RuntimeError('Regional donors must come from the exact same dense AI authority.')
    for report in reports:
        if sha(Path(report['output']['path'])) != report['output']['sha256']:
            raise RuntimeError('Donor mesh changed.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    foliage = load_mesh(Path(reports[0]['output']['path']), 'GEO_RAC_Foliage')
    pot = load_mesh(pot_native, 'GEO_RAC_Pot')
    zs = [v.co.z for v in foliage.data.vertices]
    lo, height = min(zs), max(zs)-min(zs)
    # Overlap is a hidden stem-root junction, not a visible shape substitute.
    foliage_cut = lo+height*args.foliage_cut
    pot_cut = lo+height*args.pot_cut
    foliage_stats = cut(foliage, foliage_cut, True, not args.stitch)
    pot_stats = cut(pot, pot_cut, False, not args.stitch)
    if pot_stats['nonmanifold_edges'] and not args.stitch:
        raise RuntimeError('Quad pot has unrelated open edges; do not hide them with caps.')
    if not 3000 <= args.pot_triangles <= 7000:
        raise RuntimeError('Pot allocation must be 3000..7000 triangles.')
    if pot_stats['triangles'] > args.pot_triangles:
        bpy.ops.object.select_all(action='DESELECT')
        pot.select_set(True)
        bpy.context.view_layer.objects.active = pot
        modifier = pot.modifiers.new('RegionalPotBudget', 'DECIMATE')
        modifier.ratio = args.pot_triangles/pot_stats['triangles']
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        pot_stats = measure(pot)
    target = (19000 if args.stitch else 19500)-pot_stats['triangles']
    if target < 12000:
        raise RuntimeError('Pot consumes too much of the shared runtime budget.')
    if foliage_stats['triangles'] > target:
        bpy.ops.object.select_all(action='DESELECT')
        foliage.select_set(True)
        bpy.context.view_layer.objects.active = foliage
        modifier = foliage.modifiers.new('RegionalFoliageBudget', 'DECIMATE')
        modifier.ratio = target/foliage_stats['triangles']
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    if args.union:
        bpy.ops.object.select_all(action='DESELECT')
        pot.select_set(True)
        bpy.context.view_layer.objects.active = pot
        modifier = pot.modifiers.new('RemoveOverlappingInternalCaps', 'BOOLEAN')
        modifier.operation = 'UNION'
        modifier.solver = 'EXACT'
        modifier.object = foliage
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(foliage, do_unlink=True)
        foliage = pot
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (pot, foliage):
        obj.select_set(True)
        obj.data.materials.clear()
    bpy.context.view_layer.objects.active = pot
    if foliage != pot:
        bpy.ops.object.join()
    result = bpy.context.object
    result.name = 'GEO_RAC_RegionalPlant'
    stitch_pairs = stitch_plane(result, pot_cut, height) if args.stitch else []
    for p in result.data.polygons:
        p.use_smooth = True
    stats = measure(result)
    if stats['triangles'] > 20000 or stats['vertices'] > 15000 or stats['nonmanifold_edges']:
        raise RuntimeError('Regional topology failed: '+str(stats))
    out.mkdir(parents=True)
    native, transport = out/'regional.blend', out/'regional.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    bpy.ops.export_scene.gltf(filepath=str(transport), export_format='GLB', use_selection=True, export_materials='NONE')
    record = {'schema':'reference-asset-compiler.production-retopology-candidate.v1',
        'status':'mechanical_pass', 'source':{'path':str(source),'sha256':sha(source)},
        'backend':'regional same-source AutoRemesher pot and voxel/QEM foliage',
        'parents':[{'path':str(p),'sha256':sha(p)} for p in (foliage_report,pot_report,pot_native)],
        'settings':{'foliage_cut_normalized_height':args.foliage_cut,'pot_cut_normalized_height':args.pot_cut,
                    'foliage_cut_z':foliage_cut,'pot_cut_z':pot_cut,'foliage_target_triangles':target,
                    'pot_maximum_triangles':args.pot_triangles, 'exact_union':args.union,
                    'stitch_pairs':stitch_pairs},
        'regions':{'pot_after_cut':pot_stats,'foliage_before_final_reduction':foliage_stats},
        'output':{'path':str(native),'sha256':sha(native),**stats},
        'transport':{'path':str(transport),'sha256':sha(transport)},
        'failures':[], 'production_grade':False,'requires_fixed_view_review':True}
    (out/'reduction-report.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('REGIONAL_RETOPO_CANDIDATE',json.dumps(stats),'-- two derivations, one artistic authority.')


if __name__ == '__main__':
    main()
