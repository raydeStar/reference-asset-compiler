# SPDX-License-Identifier: MIT
"""Read or write a garment's UV islands (Blender half of scripts/repack_outfit_coherent.py).

  blender -b <character.blend> -P scripts/blender/outfit_uv_islands.py -- dump <object> <out.npz>
  blender -b <character.blend> -P scripts/blender/outfit_uv_islands.py -- apply <object> <uv.npz> <out.blend> [<basecolor.png>]

dump writes every loop's UV with its face, each face's loop range, the UV island id of each face (faces
joined across an edge whose two loops share UVs), each loop's vertex, each vertex's 3D world position,
and each face's 3D centroid (m), area (m2) and unit normal. apply writes the repacked UVs back into
the object's active UV map, in the same loop order, optionally updates the packed body_basecolor image
in the blend so Cycles renders match the repacked UVs, and saves a new blend. Geometry, weights, shape keys
and every other object are untouched.
"""
from pathlib import Path
import sys

import bpy
import numpy as np


def _edge_faces(me):
    out = {}
    for p in me.polygons:
        vs = list(p.vertices)
        for k in range(len(vs)):
            a, b = vs[k], vs[(k + 1) % len(vs)]
            out.setdefault((min(a, b), max(a, b)), []).append((p.index, a, b))
    return out


args = sys.argv[sys.argv.index('--') + 1:]
mode, name = args[0], args[1]
obj = bpy.data.objects[name]
me = obj.data
uv = me.uv_layers.active.data
F = len(me.polygons)

if mode == 'dump':
    out = args[2]
    luv = np.array([uv[i].uv[:] for i in range(len(uv))])               # L x 2
    loop_face = np.empty(len(uv), int)
    for p in me.polygons:
        loop_face[p.loop_start:p.loop_start + p.loop_total] = p.index
    parent = list(range(F))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    # loops of each face, keyed by vertex, to compare the two sides of an edge
    face_vert_uv = [{me.loops[li].vertex_index: luv[li] for li in p.loop_indices} for p in me.polygons]
    for e_faces in _edge_faces(me).values():
        if len(e_faces) != 2:
            continue
        (f1, a, b), (f2, _, _) = e_faces
        if all(np.abs(face_vert_uv[f1][v] - face_vert_uv[f2][v]).max() < 1e-6 for v in (a, b)):
            ra, rb = find(f1), find(f2)
            if ra != rb:
                parent[ra] = rb
    roots = np.array([find(f) for f in range(F)])
    _, island = np.unique(roots, return_inverse=True)
    mw = np.array(obj.matrix_world)
    verts_w = np.array([(mw @ np.array([*v.co, 1.0]))[:3] for v in me.vertices])
    centre = np.array([(mw @ np.array([*p.center, 1.0]))[:3] for p in me.polygons])
    loop_start = np.array([p.loop_start for p in me.polygons])
    loop_total = np.array([p.loop_total for p in me.polygons])
    loop_vert = np.array([lp.vertex_index for lp in me.loops])
    area = np.array([p.area for p in me.polygons]) * float(np.linalg.det(mw[:3, :3]) ** (2 / 3))
    rot = np.array(obj.matrix_world.to_3x3().inverted().transposed())
    normal = np.array([rot @ np.array(p.normal[:]) for p in me.polygons])
    normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]
    extra = {}
    head_obj = next((o for o in bpy.data.objects if o.type == 'MESH' and o.name.endswith('_head')), None)
    if head_obj is not None and head_obj.data.uv_layers.active is not None:
        hmw = np.array(head_obj.matrix_world)
        huv_data = head_obj.data.uv_layers.active.data
        extra['head_centre'] = np.array([(hmw @ np.array([*p.center, 1.0]))[:3] for p in head_obj.data.polygons])
        extra['head_uv'] = np.array([np.mean([huv_data[li].uv[:] for li in p.loop_indices], axis=0)
                                     for p in head_obj.data.polygons])
    np.savez_compressed(out, loop_uv=luv, loop_face=loop_face, loop_start=loop_start, loop_total=loop_total,
                        loop_vert=loop_vert, verts=verts_w, island=island, centre=centre, area=area, normal=normal,
                        **extra)
    print('ISLANDS', int(island.max()) + 1, 'faces', F)
elif mode == 'apply':
    data = np.load(args[2])
    new = data['loop_uv']
    assert new.shape == (len(uv), 2), new.shape
    uv.foreach_set('uv', new.astype(np.float32).ravel())
    me.update()
    if len(args) >= 5 and Path(args[4]).is_file():
        tex_path = str(Path(args[4]).resolve())
        fresh_img = bpy.data.images.load(tex_path)
        target_img = bpy.data.images.get('body_basecolor.png')
        if target_img is not None:
            if target_img.packed_file:
                target_img.unpack(method='REMOVE')
            target_img.pixels = list(fresh_img.pixels[:])
            target_img.update()
            target_img.pack()
        bpy.data.images.remove(fresh_img)
        for mat in me.materials:
            if mat and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED' and 'Roughness' in node.inputs:
                        node.inputs['Roughness'].default_value = 0.85
    bpy.ops.wm.save_as_mainfile(filepath=args[3])
    print('APPLIED', args[3])
