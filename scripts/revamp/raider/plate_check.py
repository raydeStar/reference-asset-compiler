"""Measure how the Raider's solid pieces hold up in Manny's frames: bend, and the surface pushing through them.

For every plate, knee pad, pouch, belt and buckle shell, in each dumped Manny frame (manny_pose.py):
  open   the shell's open edges: a solid piece is a closed shell, so anything but 0 is a hole a viewer shows
         (the v5 shells lost triangles in the production collapse and the glTF export);
  bend   RMS and largest distance (mm) of the posed shell from its best rigid fit to the bind shell (Kabsch);
         a solid piece reads 0.
  poke   body vertices the piece covers at bind (a ray out along the surface normal meets it within COVER) that end
         up through it once posed: the piece is now behind them, more than POKE in and within REACH along their bind
         normal turned with the piece (its best rigid fit; the posed vertex normal tilts with the cloth around it and
         can find the piece's far side). Vertices already behind it at bind are left out. Count and largest excursion
         (mm).
  strain the 95th percentile of edge stretch or squash in the uncovered surface within BAND of the piece.

  $B -b <rigged_manny.blend> --python plate_check.py -- <manny_refpose.json> <manny_anim_poses.json>
      <paint.obj> <face-parts.npy> <face-parts.json> <out.json>
"""
import json
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manny_pose import MannyPoser  # noqa: E402
from part_labels import face_labels, shell_label, shells  # noqa: E402

PIECES = {'plate', 'kneepad', 'pouch', 'belt', 'buckle', 'thigh_pouch'}
COVER, POKE, REACH, BAND = 0.03, 0.0005, 0.04, 0.06

argv = sys.argv[sys.argv.index('--') + 1:]
manny = json.loads(Path(argv[0]).read_text())
poses = json.loads(Path(argv[1]).read_text())['poses']
obj_path, parts_path, names_path, out = argv[2], argv[3], argv[4], Path(argv[5])
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = bpy.data.objects['raider']
poser = MannyPoser(rig, manny)
vl = bpy.context.view_layer


def posed():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    P = np.array([(body.matrix_world @ v.co)[:] for v in me.vertices])
    N = np.array([(body.matrix_world.to_3x3() @ v.normal).normalized()[:] for v in me.vertices])
    ev.to_mesh_clear()
    return P, N


def behind(tree, p, n):
    """How far in from p, against the outward direction n, the piece lies, or None."""
    hit = tree.ray_cast(Vector(p - n * 1e-4), Vector(-n), REACH)
    return hit[3] if hit[0] is not None else None


def kabsch(A, B):
    """The rotation of A's best rigid fit to B, and B's residuals from that fit."""
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, np.linalg.norm((A - ca) @ R.T + cb - B, axis=1)


me = body.data
labels = face_labels(me, obj_path, parts_path, names_path)
pieces, solid, open_edges = [], np.zeros(len(me.vertices), bool), []
for verts, polys in shells(me):
    label = shell_label(labels, polys)
    if label in PIECES:
        pieces.append((label, verts, [list(me.polygons[i].vertices) for i in polys]))
        uses = {}
        for i in polys:
            for k in me.polygons[i].edge_keys:
                uses[k] = uses.get(k, 0) + 1
        open_edges.append(sum(1 for c in uses.values() if c == 1))
        solid[verts] = True
poser.apply(None, vl)
rest, restN = posed()
edges = np.array([e.vertices[:] for e in me.edges])
under, bands = [], []
for label, verts, tris in pieces:
    tree = BVHTree.FromPolygons([tuple(p) for p in rest], tris)
    lo, hi = rest[verts].min(0) - BAND, rest[verts].max(0) + BAND
    cand = np.flatnonzero(~solid & np.all((rest >= lo) & (rest <= hi), 1))
    cov, free = [], []
    for i in cand:
        if tree.ray_cast(Vector(rest[i] + restN[i] * 1e-4), Vector(restN[i]), COVER)[0] is not None:
            if behind(tree, rest[i], restN[i]) is None:
                cov.append(i)
        elif tree.find_nearest(Vector(rest[i]), BAND)[0] is not None:
            free.append(i)
    under.append(np.array(cov, int))
    fs = np.zeros(len(rest), bool)
    fs[free] = True
    be = edges[fs[edges[:, 0]] & fs[edges[:, 1]]]
    bands.append(be[np.linalg.norm(rest[be[:, 0]] - rest[be[:, 1]], axis=1) > 0.002])
rows = []
wanted = [p for p in poses if p['anim'] in ('MM_Idle', 'MF_Unarmed_Jog_Fwd', 'MM_Attack_01', 'MM_Jump', 'MM_Dash')]
for pose in wanted:
    poser.apply(pose, vl)
    P, _ = posed()
    for (label, verts, tris), uv, be, op in zip(pieces, under, bands, open_edges):
        R, r = kabsch(rest[verts], P[verts])
        r *= 1000
        tree = BVHTree.FromPolygons([tuple(p) for p in P], tris)
        ex = np.array([d for d in (behind(tree, P[i], R @ restN[i]) for i in uv) if d is not None])
        L0 = np.linalg.norm(rest[be[:, 0]] - rest[be[:, 1]], axis=1)
        strain = np.abs(np.linalg.norm(P[be[:, 0]] - P[be[:, 1]], axis=1) / L0 - 1) if len(be) else np.zeros(1)
        poked = ex[ex > POKE] * 1000 if len(ex) else ex
        rows.append({'pose': f"{pose['anim']}@{pose['time']:.2f}", 'piece': label, 'verts': len(verts), 'open': op,
                     'centre': rest[verts].mean(0).round(3).tolist(),
                     'bend_rms_mm': round(float(np.sqrt((r ** 2).mean())), 2), 'bend_max_mm': round(float(r.max()), 2),
                     'covered': len(uv), 'poked': int(len(poked)),
                     'strain_p95': round(float(np.percentile(strain, 95)), 2),
                     'poke_max_mm': round(float(poked.max()), 1) if len(poked) else 0.0})
poser.apply(None, vl)
summary = {}
for r in rows:
    s = summary.setdefault(f"{r['piece']} {r['centre']}", {
        'verts': r['verts'], 'open': r['open'], 'covered': r['covered'], 'bend_rms_mm': 0, 'bend_max_mm': 0,
        'poked_worst': 0,
        'poke_max_mm': 0, 'strain_p95': 0})
    s['bend_rms_mm'] = max(s['bend_rms_mm'], r['bend_rms_mm'])
    s['bend_max_mm'] = max(s['bend_max_mm'], r['bend_max_mm'])
    s['poked_worst'] = max(s['poked_worst'], r['poked'])
    s['poke_max_mm'] = max(s['poke_max_mm'], r['poke_max_mm'])
    s['strain_p95'] = max(s['strain_p95'], r['strain_p95'])
out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=1))
for name, s in sorted(summary.items(), key=lambda kv: -kv[1]['verts']):
    print('PLATE', name, s)
