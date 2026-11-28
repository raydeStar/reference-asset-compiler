"""Coherent UV charts for one Raider part, cut the way a pattern is cut (used by body_paint_prep.py --part-uv).

Smart UV Project chopped the noisy acquired surface wherever it creased: about 10k islands with saw-toothed
borders, and every border is a seam where the painter's views disagree. Here a part is cut only where it must be:
  1. at folds sharper than FOLD degrees on a shell (its rim against its faces, a pouch's box corners) and CLOTH
     degrees on a cloth part, where only a skirt folding back under its edge qualifies: at 75 degrees the wrinkles
     of the acquired jacket cut it into ragged patches;
  2. a chart that is still a tube or ring (two or more open loops) gets just enough cuts to lie flat: the cheapest
     edge path joining its loops, where an edge costs its length times one plus how far its faces turn to the front
     and to the top, so the cuts run down the back and the undersides (the jacket's back seam and under-arm seams,
     the trousers' inner legs, the back of a belt);
  3. each chart unwraps with minimum stretch. A chart that still folds over itself is projected by angle instead,
     and counted in the report.
"""
import heapq
import math
from collections import defaultdict

import bmesh
import bpy
import numpy as np

FOLD, CLOTH = 75.0, 130.0
FRONT, TOP = 3.0, 1.5


def _charts(bm, seam):
    """Faces joined across edges that are not seams."""
    comp = {}
    for f in bm.faces:
        if f in comp:
            continue
        k = len(set(comp.values()))
        stack = [f]
        comp[f] = k
        while stack:
            g = stack.pop()
            for e in g.edges:
                if seam[e.index]:
                    continue
                for h in e.link_faces:
                    if h not in comp:
                        comp[h] = k
                        stack.append(h)
    return comp


def _loops(edges):
    """Edge sets joined at shared vertices."""
    adj = defaultdict(list)
    for e in edges:
        a, b = e.verts
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for v in adj:
        if v in seen:
            continue
        stack, group = [v], set()
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            group.add(u)
            stack.extend(adj[u])
        loops.append(group)
    return loops


def _cost(e):
    n = sum((f.normal for f in e.link_faces), e.link_faces[0].normal * 0)
    if n.length > 0:
        n.normalize()
    return e.calc_length() * (1 + FRONT * max(0.0, -n.y) + TOP * max(0.0, n.z))


def _join_loops(bm, faces, seam):
    """Cut a chart with several open loops along the cheapest paths between them, until one loop remains."""
    inside = set(faces)
    edges = {e for f in faces for e in f.edges}
    border = [e for e in edges if seam[e.index] or e.is_boundary or any(g not in inside for g in e.link_faces)]
    loops = _loops(border)
    cuts = 0
    while len(loops) > 1:
        src, rest = loops[0], set().union(*loops[1:])
        dist = {v: 0.0 for v in src}
        prev = {}
        heap = [(0.0, v.index, v) for v in src]
        heapq.heapify(heap)
        hit = None
        while heap:
            d, _, v = heapq.heappop(heap)
            if d > dist.get(v, math.inf):
                continue
            if v in rest:
                hit = v
                break
            for e in v.link_edges:
                if e not in edges or seam[e.index]:
                    continue
                u = e.other_vert(v)
                nd = d + _cost(e)
                if nd < dist.get(u, math.inf):
                    dist[u], prev[u] = nd, e
                    heapq.heappush(heap, (nd, u.index, u))
        if hit is None:
            break
        v = hit
        while v in prev:
            e = prev[v]
            seam[e.index] = True
            cuts += 1
            v = e.other_vert(v)
        merged = [lp for lp in loops[1:] if hit in lp]
        loops = [src.union(*merged)] + [lp for lp in loops[1:] if hit not in lp]
    return cuts


def unwrap(obj, fold=FOLD):
    """Seam and unwrap one part object in place, cutting at folds sharper than `fold` degrees; returns a report."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    bm.normal_update()
    limit = math.cos(math.radians(fold))
    seam = [len(e.link_faces) == 2 and e.link_faces[0].normal.dot(e.link_faces[1].normal) < limit for e in bm.edges]
    comp = _charts(bm, seam)
    by_chart = defaultdict(list)
    for f, k in comp.items():
        by_chart[k].append(f)
    cuts = sum(_join_loops(bm, fs, seam) for fs in by_chart.values())
    for e in bm.edges:
        e.seam = seam[e.index]
    bm.to_mesh(me)
    bm.free()
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', fill_holes=True, margin=0.0, iterations=40, no_flip=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    flipped = _project_flipped(obj)
    return {'charts': len(by_chart), 'path_cuts': cuts, 'reprojected_faces': flipped}


def _project_flipped(obj):
    """Project by angle the charts whose unwrap turned faces over (a flip shows as a negative UV area)."""
    me = obj.data
    uv = me.uv_layers.active.data
    bad = []
    for p in me.polygons:
        q = np.array([uv[i].uv[:] for i in p.loop_indices])
        a = 0.5 * sum((q[i, 0] - q[0, 0]) * (q[i + 1, 1] - q[0, 1]) - (q[i, 1] - q[0, 1]) * (q[i + 1, 0] - q[0, 0])
                      for i in range(1, len(q) - 1))
        if a <= 0:
            bad.append(p.index)
    if not bad:
        return 0
    for p in me.polygons:
        p.select = p.index in set(bad)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return len(bad)


def islands(me):
    """UV islands: faces joined across edges whose two corners carry the same UVs."""
    uv = me.uv_layers.active.data
    parent = list(range(len(me.polygons)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for p in me.polygons:
        li = list(p.loop_indices)
        for j in range(len(li)):
            a, b = li[j], li[(j + 1) % len(li)]
            va, vb = me.loops[a].vertex_index, me.loops[b].vertex_index
            key = tuple(sorted(((va, tuple(np.round(uv[a].uv, 6))), (vb, tuple(np.round(uv[b].uv, 6))))))
            if key in seen:
                parent[find(p.index)] = find(seen[key])
            else:
                seen[key] = p.index
    return len({find(i) for i in range(len(parent))})
