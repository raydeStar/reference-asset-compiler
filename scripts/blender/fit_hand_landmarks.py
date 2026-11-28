"""Fit the finger and metacarpal joints of derived humanoid landmarks to the hands of the mesh.

blender -b --factory-startup --python fit_hand_landmarks.py -- <mesh.glb> <humanoid-landmarks.json> <out.json> <overlay_dir>

derive_humanoid_landmarks.py measures the arm but places the hand by template: Manny's finger layout turned by the
smallest rotation onto the forearm and scaled by forearm length. Nothing sets which way the palm faces or how long
and wide the hand is, so on Remora every finger joint sat 2-18 mm outside the hand and the rebound right thumb rode
the index metacarpal. Here each hand is measured:

1. The hand is grown over the mesh's own edges from the arm centreline's far end, never crossing the wrist plane, so
   a thigh the hand rests against is not taken with it.
2. Its frame: the principal axis toward the fingertips; across the knuckles the wider of the other two, signed to
   point forward (-Y), the index side for a hanging A-pose hand and a palm-down T-pose hand alike; the palm normal
   from the two. Manny's hand gets the same frame from its own joints (middle knuckle, index-to-pinky knuckle line),
   so the turn between them is a proper rotation.
3. Manny's layout is scaled to the hand's length and knuckle width and centred on the hand's cross-section at the
   knuckles, then refined (Nelder-Mead, three starting rolls) so its joints and bone midpoints lie a little inside the
   hand. The refinement is bounded (35 degrees, 15 mm, scale 1/1.2-1.2) and the middle finger must reach 90% of the
   hand's length: unbounded, the cheapest "fit" folded every joint into the palm. The same refinement also starts
   from the joints as they came in, and the lower-cost result is kept (`refined_from`): with the wrist measured on the
   mesh (derive's --arm-joints measured) the incoming hand is already close, and the resized one starts too wide where
   the thumb lies beside the knuckles (on Remora it was refused; from the incoming joints all 24 ended inside).
4. Each joint's distance outside the hand surface is measured before and after; a fit that does not bring more joints
   inside is refused, and the input landmarks are left as they were.

Only the finger and metacarpal joints move; the wrist, forearm and everything else are kept. The output is a new
landmarks file (review_status stays pending: a person still looks at the overlays).
"""
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DIGITS = ('thumb', 'index', 'middle', 'ring', 'pinky')
args = sys.argv[sys.argv.index('--') + 1:]
mesh_path, land_path, out_path, overlay_dir = (Path(a).resolve() for a in args[:4])
land = json.loads(land_path.read_text(encoding='utf-8'))
joints = {k: np.array(v, float) for k, v in land['joints'].items()}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(mesh_path))
body = max((o for o in bpy.context.scene.objects if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
bm = bmesh.new()
bm.from_mesh(body.data)
bm.transform(body.matrix_world)
# glTF import splits vertices at every UV seam and hard edge; weld (this copy only) so the hand is one surface
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.verts.ensure_lookup_table()
co = np.array([v.co[:] for v in bm.verts])
H = float(land['height_m'])


def hand_names(side):
    return [n for n in joints if n.endswith('_' + side) and any(n.startswith(d + '_') for d in DIGITS)]


def grow_hand(side):
    """Vertices connected to the arm's far end without crossing the wrist plane."""
    wrist, elbow = joints['hand_' + side], joints['lowerarm_' + side]
    fore = (wrist - elbow) / np.linalg.norm(wrist - elbow)
    end = joints.get('hand_end_' + side, wrist + fore * 0.1 * H)
    beyond = (co - wrist) @ fore > -0.002
    near = np.linalg.norm(co - end, axis=1)
    near[~beyond] = np.inf
    start = int(np.argmin(near))
    seen = {start}
    stack = [bm.verts[start]]
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            w = e.other_vert(v)
            if w.index not in seen and beyond[w.index] and np.linalg.norm(co[w.index] - wrist) < 0.16 * H:
                seen.add(w.index)
                stack.append(w)
    return np.array(sorted(seen)), fore


def frame(length, across):
    """Right-handed frame: fingers, thumbward (orthogonalised), palm normal."""
    a = length / np.linalg.norm(length)
    b = across - (across @ a) * a
    b /= np.linalg.norm(b)
    return np.stack([a, b, np.cross(a, b)])      # rows


def signed_mm(points, tree):
    """Signed distance to the hand surface in mm by the nearest point's normal: > 0 outside, < 0 inside."""
    out = []
    for p in points:
        loc, normal, _, dist = tree.find_nearest(Vector(p))
        out.append(dist * 1000 * (1 if loc is None or (Vector(p) - loc).dot(normal) > 0 else -1))
    return np.array(out)


def outside_mm(points, tree, _=None):
    return np.maximum(signed_mm(points, tree), 0.0)


def chains(side, names):
    """Each digit's joints in order, for sampling bone midpoints."""
    out = []
    for d in DIGITS:
        chain = [n for n in (f'{d}_metacarpal_{side}', f'{d}_01_{side}', f'{d}_02_{side}', f'{d}_03_{side}') if n in names]
        out.append(chain)
    return out


def rotation(v):
    """Rotation matrix from a rotation vector (radians)."""
    angle = float(np.linalg.norm(v))
    if angle < 1e-12:
        return np.eye(3)
    k = v / angle
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K


def nelder_mead(f, x0, step, iterations=1500):
    n = len(x0)
    simplex = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[i] * step[i] for i in range(n)]
    values = [f(x) for x in simplex]
    for _ in range(iterations):
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if abs(values[-1] - values[0]) < 1e-6:
            break
        centre = np.mean(simplex[:-1], axis=0)
        worst = simplex[-1]
        xr = centre + (centre - worst)
        fr = f(xr)
        if fr < values[0]:
            xe = centre + 2 * (centre - worst)
            fe = f(xe)
            simplex[-1], values[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = xr, fr
        else:
            xc = centre + 0.5 * (worst - centre)
            fc = f(xc)
            if fc < values[-1]:
                simplex[-1], values[-1] = xc, fc
            else:
                simplex = [simplex[0] + 0.5 * (s - simplex[0]) for s in simplex]
                values = [f(s) for s in simplex]
    best = int(np.argmin(values))
    return simplex[best], values[best]


report = {'schema': 'reference-asset-compiler.hand-landmark-fit.v1', 'source_mesh': str(mesh_path),
          'source_mesh_sha256': hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
          'landmarks_in': str(land_path), 'landmarks_in_sha256': hashlib.sha256(land_path.read_bytes()).hexdigest(),
          'hands': {}}
fitted = {k: v.copy() for k, v in joints.items()}
for side in ('l', 'r'):
    idx, fore = grow_hand(side)
    pts = co[idx]
    wrist = joints['hand_' + side]
    names = hand_names(side)
    # the hand's own surface, for inside/outside
    keep = set(idx.tolist())
    faces = [[v.index for v in f.verts] for f in bm.faces if all(v.index in keep for v in f.verts)]
    tree = BVHTree.FromPolygons([tuple(p) for p in co], faces)
    centred = pts - pts.mean(0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    length = vt[0] if vt[0] @ fore > 0 else -vt[0]
    spread = [float(np.ptp(centred @ v)) for v in vt[1:]]
    across = vt[1] if spread[0] >= spread[1] else vt[2]
    across = across if across[1] < 0 else -across            # thumb forward (-Y)
    F_mesh = frame(length, across)
    # Manny's (already placed) layout in its own frame
    T = {n: joints[n] for n in names}
    # across = the knuckle line toward the index (the thumb side); Manny's thumb leans toward the palm, so it is
    # not the across axis
    F_tmpl = frame(T['middle_01_' + side] - wrist, T['index_01_' + side] - T['pinky_01_' + side])
    local = {n: F_tmpl @ (T[n] - wrist) for n in names}
    tip = local['middle_03_' + side] + (local['middle_03_' + side] - local['middle_02_' + side])
    tmpl_len = float(tip[0])
    knuckles = np.array([local[f'{d}_01_{side}'] for d in ('index', 'middle', 'ring', 'pinky')])
    tmpl_width = float(np.ptp(knuckles[:, 1]))
    rel = (pts - wrist) @ F_mesh.T
    mesh_len = float(rel[:, 0].max())
    knuckle_at = float(np.mean(knuckles[:, 0])) * mesh_len / tmpl_len
    band = rel[np.abs(rel[:, 0] - knuckle_at) < 0.012 * H / 1.7]
    mesh_width = float(np.ptp(band[:, 1])) * 0.80        # knuckle joints sit inside the hand's edges
    mesh_thick = float(np.ptp(band[:, 2]))
    scale = np.array([mesh_len / tmpl_len, mesh_width / max(tmpl_width, 1e-6), 1.0])
    scale[2] = scale[1]      # finger curl and thumb offset across the palm follow the hand's size
    placed = {n: local[n] * scale for n in names}
    # centre the knuckle row on the hand's cross-section there
    row = np.array([placed[f'{d}_01_{side}'] for d in ('index', 'middle', 'ring', 'pinky')])
    shift = np.array([0.0, band[:, 1].mean() - row[:, 1].mean(), band[:, 2].mean() - row[:, 2].mean()])
    order = list(names)
    L0 = np.array([placed[n] + shift for n in order])
    links = [(order.index(a), order.index(b)) for c in chains(side, names) for a, b in zip(c, c[1:])]

    def place(x):
        """x: rotation vector (3, in the hand frame), shift (3, m), log scale along the fingers and across."""
        s = np.exp([x[6], x[7], x[7]])
        pivot = L0.mean(0)
        local_pts = (rotation(x[:3]) @ ((L0 - pivot) * s).T).T + pivot + x[3:6]
        return wrist + local_pts @ F_mesh

    tip_index = (order.index(f'middle_03_{side}'), order.index(f'middle_02_{side}'))

    def cost(x):
        """Joints inside the hand, but still a hand: bounded turn, shift and scale, and the middle finger reaching
        the far end (without this the cheapest fit folds every joint into the palm)."""
        world = place(x)
        samples = np.vstack([world, [(world[a] + world[b]) / 2 for a, b in links]])
        d = signed_mm(samples, tree)
        depth = 0.25 * min(mesh_thick, 0.02) * 1000      # aim a little inside, not grazing the skin
        inside = float(np.sum(np.maximum(d + depth, 0) ** 2))
        m3, m2 = world[tip_index[0]], world[tip_index[1]]
        reach = float((m3 + 0.8 * (m3 - m2) - wrist) @ F_mesh[0])
        short = max(0.0, 0.9 * mesh_len - reach) * 1000
        bounds = (np.maximum(np.abs(x[:3]) - np.radians(35), 0) ** 2).sum() * 1e5
        bounds += (np.maximum(np.abs(x[3:6]) - 0.015, 0) ** 2).sum() * 1e8
        bounds += (np.maximum(np.abs(x[6:]) - np.log(1.2), 0) ** 2).sum() * 1e6
        return inside + 4 * short ** 2 + bounds

    # Two layouts to refine from: Manny's hand resized to the measured hand (above), and the joints as they came in.
    # With the wrist on the mesh's own wrist (derive's --arm-joints measured) the incoming hand is already close, and
    # the resized one starts too wide wherever the thumb lies beside the knuckles; the lower cost wins.
    layouts = {'resized': L0, 'as_placed': np.array([F_mesh @ (T[n] - wrist) for n in order])}
    best, best_cost, best_layout = None, np.inf, 'resized'
    for label, layout in layouts.items():
        L0 = layout
        for roll in (0.0, -0.35, 0.35):      # restarts about the finger axis
            x, value = nelder_mead(cost, [roll, 0, 0, 0, 0, 0, 0, 0], [0.15, 0.15, 0.15, 0.01, 0.01, 0.01, 0.1, 0.1])
            if value < best_cost:
                best, best_cost, best_layout = x, value, label
    L0 = layouts[best_layout]
    fitted_pts = place(best)
    new = {n: fitted_pts[i] for i, n in enumerate(order)}
    before = outside_mm([joints[n] for n in names], tree)
    after = outside_mm([new[n] for n in names], tree)
    accepted = int((after == 0).sum()) > int((before == 0).sum()) and after.mean() < before.mean()
    if accepted:
        fitted.update(new)
    report['hands'][side] = {
        'hand_vertices': int(len(idx)), 'hand_length_m': round(mesh_len, 4), 'knuckle_width_m': round(mesh_width, 4),
        'thickness_m': round(mesh_thick, 4), 'scale_len_width_thick': [round(float(s), 3) for s in scale],
        'joints': len(names), 'inside_before': int((before == 0).sum()), 'inside_after': int((after == 0).sum()),
        'mean_outside_mm_before': round(float(before.mean()), 2), 'mean_outside_mm_after': round(float(after.mean()), 2),
        'max_outside_mm_before': round(float(before.max()), 2), 'max_outside_mm_after': round(float(after.max()), 2),
        'accepted': bool(accepted), 'refined_from': best_layout, 'refine': {'rotation_deg': [round(float(np.degrees(v)), 1) for v in best[:3]],
                                               'shift_mm': [round(float(v) * 1000, 1) for v in best[3:6]],
                                               'scale_len_across': [round(float(np.exp(v)), 3) for v in best[6:]]},
        'outside_after_mm': {n: round(float(d), 1) for n, d in zip(names, after) if d > 0},
    }

out = dict(land)
out['joints'] = {k: [float(x) for x in v] for k, v in fitted.items()}
out['method'] = land['method'] + ' Hands refitted to the mesh by fit_hand_landmarks.py (frame, size and centre).'
out['hand_fit'] = report['hands']
out['review_status'] = 'derived_pending_overlay_review'
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(out, indent=1), encoding='utf-8')
report['landmarks_out'] = str(out_path)

# overlays: each hand from the palm and from the thumb side, joints before (red) and after (green)
overlay_dir.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.show_xray = True
scene.display.shading.xray_alpha = 0.25
scene.display.shading.color_type = 'OBJECT'
scene.display.shading.light = 'FLAT'
scene.render.resolution_x = scene.render.resolution_y = 640
scene.world = bpy.data.worlds.new('w')
body.color = (0.8, 0.7, 0.6, 1)


def dots(points, colour, name):
    mesh = bpy.data.meshes.new(name)
    bmd = bmesh.new()
    for p in points:
        bmesh.ops.create_icosphere(bmd, subdivisions=1, radius=0.0045, matrix=__import__('mathutils').Matrix.Translation(p))
    bmd.to_mesh(mesh)
    bmd.free()
    o = bpy.data.objects.new(name, mesh)
    o.color = colour
    scene.collection.objects.link(o)
    return o


cam_data = bpy.data.cameras.new('c')
cam_data.type = 'ORTHO'
cam = bpy.data.objects.new('c', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
shots = []
for side in ('l', 'r'):
    names = hand_names(side)
    a = dots([joints[n] for n in names], (1, 0.15, 0.1, 1), 'before_' + side)
    b = dots([fitted[n] for n in names], (0.1, 1, 0.3, 1), 'after_' + side)
    centre = np.mean([fitted[n] for n in names], axis=0)
    cam_data.ortho_scale = 0.16 * H / 1.7
    for view, direction in (('front', np.array([0, -1, 0])), ('side', np.array([1 if side == 'l' else -1, 0, 0]))):
        cam.location = Vector(centre + direction * 0.6)
        cam.rotation_euler = (Vector(centre) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        path = overlay_dir / f'hand-{side}-{view}.png'
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        shots.append(path.name)
    for o in (a, b):
        bpy.data.objects.remove(o)
report['overlays'] = shots
(out_path.parent / 'hand-fit.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print('HAND_FIT', json.dumps({s: {k: v for k, v in h.items() if k != 'outside_after_mm'} for s, h in report['hands'].items()}))
