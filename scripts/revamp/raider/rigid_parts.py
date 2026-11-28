"""Make the Raider's plates, knee pads, pouches, belt and buckles move as solid pieces.

Each of these overlays is its own closed shell on the production mesh (build_parts.py), but its weights came from
the body under it vertex by vertex, so a plate bent and creased like the cloth below (the shoulder plate by up to
96 mm in Manny's attack, plate_check.py). Each such shell now takes one weight set for all of its vertices: the
area-weighted mean of its own weights with twist bones folded into their limb bone (they only split the roll along
it), influences under MIN dropped, at most KEEP kept. One weight set is one transform for the whole shell, so it can
no longer bend; a set over two bones can only squash it evenly a little at large angles.

A shell over a ball joint (shoulder plate: clavicle and upper arm; drop-leg pouch: pelvis and thigh) is strapped to
the limb, so it rides the limb by at least LIMB. A shell whose mean straddles a hinge (elbow, knee) is left as it
was: there a single transform would cut into the bend.

The surface under each solid piece (jacket, straps, the arm under the shoulder plate) is pulled to the piece's
weights so it moves with the piece instead of pushing through it: fully where the piece covers it (a ray along the
surface normal meets the piece within COVER) or lies within LOCK of it, fading out linearly over FADE. Only surface
on the piece's own body regions (torso, each arm, each leg) is pulled, in proportion to its weight there (smoothstep
over GATE), so an arm hanging beside a belt pouch keeps the arm's weights. Where two pieces' fades meet (the chest
plate's lower edge and the belt pouches, 5 mm apart over a strap) the surface blends both pieces' weights by their
pulls, a covering piece's pull counting OVER times; taking only the nearer piece split neighbouring vertices between
them and tore the strap, and an even blend left the cloth under a pouch lagging behind it.

  $B -b <rigged_manny.blend> --python rigid_parts.py -- <paint.obj> <face-parts.npy> <face-parts.json> <out.blend>
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
from part_labels import face_labels, shell_label, shells  # noqa: E402

RIGID = {'plate', 'kneepad', 'pouch', 'belt', 'buckle', 'thigh_pouch'}
MIN, KEEP, LIMIT = 0.08, 4, 8       # piece weights: floor, count; influences per vertex after blending
COVER, LOCK, FADE = 0.03, 0.025, 0.07   # metres: covered depth, full lock from the surface, then a linear fade
GATE = (0.3, 0.7)                   # a vertex's weight on the piece's body regions: not pulled .. fully pulled
OVER = 10
LIMB = 0.7
BALL = (('clavicle_', 'upperarm_'), ('pelvis', 'thigh_'))
HINGES = (('upperarm', ('lowerarm', 'hand')), ('thigh', ('calf', 'foot', 'ball')))

argv = sys.argv[sys.argv.index('--') + 1:]
obj_path, parts_path, names_path, out = argv[0], argv[1], argv[2], Path(argv[3])
body = bpy.data.objects['raider']
me = body.data
groups = [g.name for g in body.vertex_groups]
gid = {g: i for i, g in enumerate(groups)}
nv, ng = len(me.vertices), len(groups)
W = np.zeros((nv, ng))
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
mw = body.matrix_world
P = np.array([(mw @ v.co)[:] for v in me.vertices])
N = np.array([(mw.to_3x3() @ v.normal).normalized()[:] for v in me.vertices])
area = np.zeros(nv)
for p in me.polygons:
    area[list(p.vertices)] += p.area / len(p.vertices)
# twist bone -> the limb bone it splits (upperarm_twist_01_r -> upperarm_r)
fold = np.arange(ng)
for i, g in enumerate(groups):
    if '_twist_' in g:
        base = g.split('_twist_')[0] + '_' + g.rsplit('_', 1)[1]
        fold[i] = gid.get(base, i)



def region(bone):
    side = bone.rsplit('_', 1)[-1]
    if bone.startswith(('upperarm', 'lowerarm', 'hand', 'thumb', 'index', 'middle', 'ring', 'pinky')):
        return 'arm_' + side
    if bone.startswith(('thigh', 'calf', 'foot', 'ball')):
        return 'leg_' + side
    return 'torso'


regions = np.array([region(g) for g in groups])


def share(w, prefixes):
    return sum(w[i] for i, g in enumerate(groups) if g.startswith(prefixes))


def piece_weights(mean):
    w = np.zeros(ng)
    np.add.at(w, fold, mean)
    top = [i for i in np.argsort(-w)[:KEEP] if w[i] >= MIN]
    w = np.where(np.isin(np.arange(ng), top), w, 0)
    w /= w.sum()
    for torso, limb in BALL:
        lb = [i for i in top if groups[i].startswith(limb)]
        others = [i for i in top if i not in lb]
        if lb and any(groups[i].startswith(torso) for i in others) and w[lb].sum() < LIMB:
            w[lb] *= LIMB / w[lb].sum()
            w[others] *= (1 - LIMB) / w[others].sum()
    return w


labels = face_labels(me, obj_path, parts_path, names_path)
pieces, report = [], []
for verts, polys in shells(me):
    label = shell_label(labels, polys)
    if label not in RIGID:
        continue
    mean = (W[verts] * area[verts, None]).sum(0) / area[verts].sum()
    entry = {'label': label, 'verts': len(verts), 'centre': P[verts].mean(0).round(3).tolist(),
             'mean': {groups[i]: round(float(mean[i]), 3) for i in np.argsort(-mean)[:6] if mean[i] > 0.01}}
    if any(share(mean, up) >= 0.15 and share(mean, low) >= 0.15 for up, low in HINGES):
        report.append({**entry, 'kept': 'straddles a hinge'})
        continue
    w = piece_weights(mean)
    pieces.append((verts, polys, w))
    report.append({**entry, 'rigid': {groups[i]: round(float(w[i]), 3) for i in np.flatnonzero(w)}})

new = W.copy()
in_piece = np.zeros(nv, bool)
for verts, _, w in pieces:
    new[verts] = w
    in_piece[verts] = True
# the surface under each piece; where pieces' pulls meet, their weights blend by pull
keep = np.ones(nv)                  # product of (1 - pull) over the pieces
pull = np.zeros(nv)
target = np.zeros((nv, ng))
reach = LOCK + FADE
for verts, polys, w in pieces:
    tree = BVHTree.FromPolygons([tuple(p) for p in P], [list(me.polygons[i].vertices) for i in polys])
    lo, hi = P[verts].min(0) - reach, P[verts].max(0) + reach
    own = W[:, np.isin(regions, regions[w > 0])].sum(1)
    for i in np.flatnonzero(~in_piece & np.all((P >= lo) & (P <= hi), 1)):
        hit = tree.find_nearest(Vector(P[i]), reach)
        if hit[0] is None:
            continue
        covered = tree.ray_cast(Vector(P[i] + N[i] * 1e-4), Vector(N[i]), COVER)[0] is not None
        a = 1.0 if covered else min(1.0, (reach - hit[3]) / FADE)
        g = np.clip((own[i] - GATE[0]) / (GATE[1] - GATE[0]), 0, 1)
        a *= g * g * (3 - 2 * g)
        keep[i] *= 1 - a
        pull[i] += a * (OVER if covered else 1)
        target[i] += a * (OVER if covered else 1) * w
alpha = 1 - keep
moved = pull > 0
target[moved] /= pull[moved, None]
new[moved] = (1 - alpha[moved, None]) * W[moved] + alpha[moved, None] * target[moved]
# keep the strongest LIMIT influences and renormalize
for i in np.flatnonzero(moved):
    row = new[i]
    row[np.argsort(-row)[LIMIT:]] = 0
    new[i] = row / row.sum()

changed = np.flatnonzero(np.abs(new - W).max(1) > 1e-6)
for gi, name in enumerate(groups):
    vg = body.vertex_groups[name]
    vg.remove(changed.tolist())
    for i in changed[new[changed, gi] > 0]:
        vg.add([int(i)], float(new[i, gi]), 'REPLACE')
bpy.ops.wm.save_as_mainfile(filepath=str(out))
summary = {'pieces_rigid': len(pieces), 'vertices_rigid': int(in_piece.sum()),
           'surface_locked': int((alpha >= 1).sum()), 'surface_faded': int(((alpha > 0) & (alpha < 1)).sum()),
           'vertices_changed': int(len(changed)), 'pieces': report}
Path(str(out) + '.json').write_text(json.dumps(summary, indent=1))
print('RIGID_PARTS', {k: v for k, v in summary.items() if k != 'pieces'}, out)
