"""Game review step 2b: rebind the body by heat weights on a watertight stand-in, then copy them back.

blender -b <rigged.blend> --python game_review_bind.py -- <job.json> <out.blend>

The landmark rig binds with Blender's heat weights, which fail on a character built of layers: a hair shell, eyes
and mouth parts inside the head, an outfit over a body. Remora fell all the way back to envelope weights (capsules
around each bone): the shoulders, arms and torso folded wrongly in every clip. Here the body and outfit (not hair,
eyes or mouth, which ride the head in step 4) are voxel-remeshed into one closed surface, heat-weighted, and each
vertex of the real mesh takes the weights of the nearest point on that surface. Layers that lie together therefore
move together: an outfit cannot swing through the body under it.

Every other attribute of the mesh (shape keys, UVs, normals, materials) is untouched.
"""
import json
import sys
import time
from pathlib import Path

import bmesh
import bpy

args = sys.argv[sys.argv.index('--') + 1:]
job = json.loads(Path(args[0]).read_text(encoding='utf-8'))
out = Path(args[1])
sys.path.insert(0, str(Path(job['repo_root']) / 'src'))
from reference_asset_compiler.game_review import is_hair, material_kind  # noqa: E402

settings = {'voxel_m': 0.006, **job.get('bind', {})}
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = next(o for o in bpy.data.objects if o.type == 'MESH')
deform = {b.name for b in rig.data.bones if b.use_deform}
started = time.monotonic()

# the stand-in: body and outfit only, welded into one closed surface
proxy = body.copy()
proxy.data = body.data.copy()
proxy.name = 'RAC_BindProxy'
bpy.context.scene.collection.objects.link(proxy)
proxy.parent = None
proxy.matrix_world = body.matrix_world.copy()
proxy.modifiers.clear()
proxy.vertex_groups.clear()
if proxy.data.shape_keys:
    proxy.shape_key_clear()
mats = [m.name for m in proxy.data.materials]
rigid = {i for i, name in enumerate(mats) if material_kind(name, job) == 'rigid'}
bm = bmesh.new()
bm.from_mesh(proxy.data)
doomed = [f for f in bm.faces if f.material_index in rigid]
dropped = len(doomed)
bmesh.ops.delete(bm, geom=doomed, context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(proxy.data)
bm.free()
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = proxy
proxy.select_set(True)
remesh = proxy.modifiers.new('Remesh', 'REMESH')
remesh.mode = 'VOXEL'
remesh.voxel_size = settings['voxel_m']
remesh.adaptivity = 0.0
bpy.ops.object.modifier_apply(modifier=remesh.name)
faces_after_remesh = len(proxy.data.polygons)      # no decimation: its slivers make the heat solve singular
# Keep the outer surface only. The remesh of an outfit over a body also closes hollow pockets between the layers;
# their walls see no bone, which leaves the heat equations without a solution for every bone at once.
bm = bmesh.new()
bm.from_mesh(proxy.data)
bm.verts.ensure_lookup_table()
seen, parts = set(), []
for start in bm.verts:
    if start.index in seen:
        continue
    stack, part = [start], []
    seen.add(start.index)
    while stack:
        v = stack.pop()
        part.append(v)
        for e in v.link_edges:
            w = e.other_vert(v)
            if w.index not in seen:
                seen.add(w.index)
                stack.append(w)
    parts.append(part)
parts.sort(key=len, reverse=True)
inner = [v for part in parts[1:] for v in part]
bmesh.ops.delete(bm, geom=inner, context='VERTS')
bm.to_mesh(proxy.data)
bm.free()
components = {'kept_vertices': len(parts[0]), 'dropped_parts': len(parts) - 1, 'dropped_vertices': len(inner)}

# heat weights on the stand-in, solved at 10x as Remora's accepted run was (weights do not depend on scale; the
# scale alone did not cure the 0% failure, dropping the inner pockets above did)
SCALE = settings.get('heat_scale', 10.0)
rig_scale = rig.scale.copy()
for o in (rig, proxy):
    o.scale = o.scale * SCALE
    o.location = o.location * SCALE
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
proxy.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
rig.scale = rig_scale
rig.location = rig.location / SCALE
bpy.context.view_layer.update()
weighted = sum(1 for v in proxy.data.vertices if any(g.weight > 1e-5 for g in v.groups))
coverage = weighted / max(1, len(proxy.data.vertices))
report = {'voxel_m': settings['voxel_m'], 'rigid_faces_dropped': dropped, 'proxy_faces_after_remesh': faces_after_remesh,
          'proxy_components': components,
          'proxy_vertices': len(proxy.data.vertices), 'proxy_heat_coverage': round(coverage, 5)}
assert coverage > 0.98, f'heat weights failed on the stand-in too: {report}'

# copy back: every vertex takes the nearest stand-in surface point's weights
for group in list(body.vertex_groups):
    body.vertex_groups.remove(group)
for group in proxy.vertex_groups:
    body.vertex_groups.new(name=group.name)
armature = next((m for m in body.modifiers if m.type == 'ARMATURE'), None)
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
transfer = body.modifiers.new('TransferWeights', 'DATA_TRANSFER')
transfer.object = proxy
transfer.use_vert_data = True
transfer.data_types_verts = {'VGROUP_WEIGHTS'}
transfer.vert_mapping = 'POLYINTERP_NEAREST'
transfer.layers_vgroup_select_src = 'ALL'
transfer.layers_vgroup_select_dst = 'NAME'
transfer.mix_mode = 'REPLACE'
transfer.mix_factor = 1.0
if armature:      # the transfer must be applied before (under) the armature
    bpy.ops.object.modifier_move_to_index(modifier=transfer.name, index=0)
bpy.ops.object.modifier_apply(modifier=transfer.name)
bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
bpy.data.objects.remove(proxy, do_unlink=True)
unweighted = sum(1 for v in body.data.vertices if not any(g.weight > 1e-5 for g in v.groups))
assert unweighted == 0, f'{unweighted} vertices took no weight'


def shoulder_release(ramp_m):
    """Heat on the stand-in leaves the top of the upper arm mostly on the collarbone (Remora: 63% in the first fifth
    of the upper arm, 21% in the second), so a raised arm leaves the deltoid behind: a lump at the shoulder, a sagging
    armpit, a stretched thin upper arm. Past the shoulder joint along the arm, collarbone and upper-spine weight moves
    to the upper arm, faded in continuously (along the arm over ramp_m, by how much of the vertex is already arm, and
    by distance from the arm's axis): a hard selection edge tore the tunic's armhole."""
    groups = {g.name: g for g in body.vertex_groups}
    heads = {b.name: rig.matrix_world @ b.head_local for b in rig.data.bones}
    moved, touched = 0.0, 0
    for s in 'lr':
        if f'upperarm_{s}' not in groups or f'lowerarm_{s}' not in heads:
            continue
        sh, el = heads[f'upperarm_{s}'], heads[f'lowerarm_{s}']
        axis = (el - sh).normalized()
        length = (el - sh).length
        arm_names = {n for n in groups if n.startswith((f'upperarm_{s}', f'lowerarm_{s}'))}
        donors = [n for n in (f'clavicle_{s}', 'spine_05', 'spine_04', 'spine_03') if n in groups]
        upper = groups[f'upperarm_{s}']
        for v in body.data.vertices:
            p = body.matrix_world @ v.co
            d = (p - sh).dot(axis)
            if d <= 0 or d > length:
                continue
            radial = ((p - sh) - axis * d).length
            if radial > 0.10:
                continue
            ws = {body.vertex_groups[g.group].name: g.weight for g in v.groups}
            arm_w = sum(w for n, w in ws.items() if n in arm_names)
            f = (min(1.0, d / ramp_m) * max(0.0, min(1.0, (arm_w - 0.05) / 0.30))
                 * max(0.0, min(1.0, (0.10 - radial) / 0.03)))
            if f <= 0:
                continue
            take = 0.0
            for n in donors:
                w = ws.get(n, 0.0)
                if w > 0:
                    groups[n].add([v.index], w * (1 - f), 'REPLACE')
                    take += w * f
            if take > 0:
                upper.add([v.index], ws.get(f'upperarm_{s}', 0.0) + take, 'REPLACE')
                moved += take
                touched += 1
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    return {'ramp_cm': round(ramp_m * 100, 2), 'vertices': touched, 'weight_moved': round(moved, 2)}


if settings.get('shoulder_release_cm', 0) > 0:
    report['shoulder_release'] = shoulder_release(settings['shoulder_release_cm'] / 100)


def hip_release(ramp_m, take):
    """Heat on the stand-in gives the buttock to the thigh (Remora: 69-98% thigh from 8 cm above the hip joint down,
    6-23% pelvis), so it rides the leg: in a run it balloons into a faceted lump when the knee lifts and creases when
    the leg goes back. On the back of the hip, `take` of the thigh's weight moves to the pelvis at and above the hip
    joint, fading to none ramp_m below it along the thigh and fading out toward the front of the hip. A short ramp
    (9 cm) only moved the crease down; 16-22 cm bends smoothly. The fade toward the front starts 7 cm ahead of the
    hip joint (V20 began 3 cm ahead and left the outer hip bulging when the leg lifted)."""
    def smooth(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    groups = {g.name: g for g in body.vertex_groups}
    heads = {b.name: rig.matrix_world @ b.head_local for b in rig.data.bones}
    if 'pelvis' not in groups or 'ball_l' not in heads:
        return {'skipped': 'no pelvis group or foot bones'}
    back = heads['foot_l'] - heads['ball_l']      # from the toes toward the heel: her back
    back.z = 0
    back.normalize()
    moved, touched = 0.0, 0
    for s in 'lr':
        if f'thigh_{s}' not in heads or f'calf_{s}' not in heads:
            continue
        hip, knee = heads[f'thigh_{s}'], heads[f'calf_{s}']
        axis = (knee - hip).normalized()
        donors = [n for n in groups if n == f'thigh_{s}' or (n.startswith('thigh_twist') and n.endswith(f'_{s}'))]
        for v in body.data.vertices:
            p = body.matrix_world @ v.co
            d = (p - hip).dot(axis)
            if d > ramp_m:
                continue
            f = take * (1.0 if d <= 0 else 1.0 - smooth(d / ramp_m)) * smooth(((p - hip).dot(back) + 0.07) / 0.12)
            if f <= 0:
                continue
            ws = {body.vertex_groups[g.group].name: g.weight for g in v.groups}
            got = 0.0
            for n in donors:
                w = ws.get(n, 0.0)
                if w > 0:
                    groups[n].add([v.index], w * (1 - f), 'REPLACE')
                    got += w * f
            if got > 0:
                groups['pelvis'].add([v.index], ws.get('pelvis', 0.0) + got, 'REPLACE')
                moved += got
                touched += 1
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    return {'ramp_cm': round(ramp_m * 100, 2), 'take': take, 'vertices': touched, 'weight_moved': round(moved, 2)}


if settings.get('hip_release_cm', 0) > 0:
    report['hip_release'] = hip_release(settings['hip_release_cm'] / 100, settings.get('hip_release_take', 0.65))


def armhole_hold(band_m):
    """A sleeveless outfit modelled in one surface with the body gets the arm's weights around its armhole, so the
    armhole lifts and wings out with a raised arm and the outfit's flank tents up after it (Remora hanging from a
    ledge: the tunic's shoulders stood out like caps, 2026-11-10). The outfit there belongs to the torso.

    The arm's own surface is told from the outfit by colour: what has the tint and brightness of the free upper arm
    (the base colour between 45% and 85% of the way to the elbow) and is joined to it through more of the same. On a
    bare arm that is the skin, up to the armhole's edge; on a sleeved arm it is the sleeve and all it joins, and
    nothing is held. Everything else gives its arm weights back to its other bones: all of them around the shoulder,
    and anywhere else it stands more than 6-9 cm off the arm's bones (a bracer or a glove wraps them and keeps its
    weights; a hand past a bracer is all arm and keeps them too). The arm's own surface is held where it lies against
    the held outfit and let go over band_m, measured straight through space: the armpit's skin stretches as skin does
    and nothing tears at the armhole's edge. (Measured along the surface instead, the groove under the armhole's rim
    used the band up and the edge tore; a hard edge with no band tore everywhere.)"""
    import numpy as np
    from mathutils import Vector
    from mathutils.kdtree import KDTree

    def smooth(x):
        x = np.clip(x, 0.0, 1.0)
        return x * x * (3 - 2 * x)

    def base_image(material):
        tree = material.node_tree if material else None
        if not tree:
            return None
        shader = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        stack = [link.from_node for link in shader.inputs['Base Color'].links] if shader else []
        seen = set()
        while stack:
            node = stack.pop()
            if node.name in seen:
                continue
            seen.add(node.name)
            if node.type == 'TEX_IMAGE' and node.image:
                return node.image
            stack += [link.from_node for socket in node.inputs for link in socket.links]
        return next((n.image for n in tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)

    def pixels(image, size=512):      # box-blurred, so a weave or a stitch line does not decide a vertex
        w, h = image.size
        flat = np.empty(w * h * 4, np.float32)
        image.pixels.foreach_get(flat)
        rgb = flat.reshape(h, w, 4)[:, :, :3]
        fy, fx = max(1, h // size), max(1, w // size)
        return rgb[:h // fy * fy, :w // fx * fx].reshape(h // fy, fy, w // fx, fx, 3).mean(axis=(1, 3))

    def to_segment(points, a, b):
        ab = b - a
        u = np.clip(((points - a) @ ab) / float(ab @ ab), 0.0, 1.0)
        return np.linalg.norm(points - (a + np.outer(u, ab)), axis=1)

    me = body.data
    if not me.uv_layers.active:
        return {'skipped': 'the mesh has no UVs to read its colour by'}
    n_loops, n_verts = len(me.loops), len(me.vertices)
    loop_vert = np.empty(n_loops, np.int32)
    me.loops.foreach_get('vertex_index', loop_vert)
    uv = np.empty(n_loops * 2, np.float32)
    me.uv_layers.active.data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)
    loop_mat = np.empty(n_loops, np.int32)
    for p in me.polygons:
        loop_mat[p.loop_start:p.loop_start + p.loop_total] = p.material_index
    colour, count = np.zeros((n_verts, 3)), np.zeros(n_verts)
    for mi, material in enumerate(me.materials):
        image = base_image(material)
        pick = np.nonzero(loop_mat == mi)[0]
        if image is None or not len(pick) or not image.size[0]:
            continue
        tex = pixels(image)
        h, w = tex.shape[:2]
        x = np.clip((uv[pick, 0] % 1.0 * w).astype(int), 0, w - 1)
        y = np.clip((uv[pick, 1] % 1.0 * h).astype(int), 0, h - 1)
        np.add.at(colour, loop_vert[pick], tex[y, x])
        np.add.at(count, loop_vert[pick], 1)
    if not count.any():
        return {'skipped': 'no material has a base colour image'}
    colour /= np.maximum(count, 1)[:, None]
    world = np.asarray(body.matrix_world)
    co = np.empty(n_verts * 3)
    me.vertices.foreach_get('co', co)
    P = co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
    # the mesh is split along its UV seams: vertices at one position are one point
    key, point = {}, np.empty(n_verts, np.int64)
    for i, p in enumerate(np.round(P / 2e-5).astype(np.int64)):
        point[i] = key.setdefault((p[0], p[1], p[2]), len(key))
    edges = np.empty(len(me.edges) * 2, np.int32)
    me.edges.foreach_get('vertices', edges)
    links = [[] for _ in range(len(key))]
    for a, b in point[edges].reshape(-1, 2):
        if a != b:
            links[a].append(b)
            links[b].append(a)
    c = np.maximum(colour, 1e-3)
    luma = c @ np.array([0.2126, 0.7152, 0.0722])
    feature = np.stack([np.log(c[:, 0] / c[:, 1]), np.log(c[:, 1] / c[:, 2]), np.log(luma)], axis=1)      # tint, tint, brightness
    floor = np.array([0.05, 0.05, 0.30])
    names = [g.name for g in body.vertex_groups]
    heads = {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}
    result = {'band_cm': round(band_m * 100, 2)}
    for s in 'lr':
        if any(f'{b}_{s}' not in heads for b in ('upperarm', 'lowerarm', 'hand')) or f'clavicle_{s}' not in names:
            continue
        S, E, H = heads[f'upperarm_{s}'], heads[f'lowerarm_{s}'], heads[f'hand_{s}']
        tip = heads.get(f'middle_03_{s}', H)
        L = float(np.linalg.norm(E - S))
        axis = (E - S) / L
        rel = P - S
        t = rel @ axis
        dist = np.linalg.norm(rel, axis=1)
        rho = np.linalg.norm(rel - np.outer(t, axis), axis=1)
        arm_chain = {i for i, n in enumerate(names) if n.endswith('_' + s)
                     and n.split('_')[0] in ('upperarm', 'lowerarm', 'hand', 'thumb', 'index', 'middle', 'ring', 'pinky')}
        arm_weight = np.array([sum(g.weight for g in v.groups if g.group in arm_chain) for v in me.vertices])
        free = (t > 0.45 * L) & (t < 0.85 * L) & (rho < 0.08) & (count > 0)
        if free.sum() < 20:
            result[s] = {'skipped': 'too little of the upper arm to read its colour'}
            continue
        mu = np.median(feature[free], axis=0)
        spread = np.maximum(np.percentile(np.abs(feature[free] - mu), 90, axis=0), floor)
        alike = (np.sqrt((((feature - mu) / spread) ** 2).sum(axis=1) / 3) < 1.6) & (count > 0)
        alike_point = np.zeros(len(key), bool)
        np.logical_or.at(alike_point, point, alike)
        reached = np.zeros(len(key), bool)
        stack = list(set(point[free & alike].tolist()))
        reached[stack] = True
        while stack:
            k = stack.pop()
            for j in links[k]:
                if alike_point[j] and not reached[j]:
                    reached[j] = True
                    stack.append(j)
        # a speck on the arm that failed the colour test (a shadow, a painted crease) is still the arm
        near_point = np.zeros(len(key), bool)
        np.logical_or.at(near_point, point, dist < 0.30)
        seen, absorbed = reached.copy(), 0
        for seed in np.nonzero(near_point & ~reached)[0]:
            if seen[seed]:
                continue
            seen[seed] = True
            stack, members, touches, enclosed = [seed], [seed], False, True
            while stack:
                k = stack.pop()
                for j in links[k]:
                    if reached[j]:
                        touches = True
                    elif not near_point[j]:
                        enclosed = False
                    elif not seen[j]:
                        seen[j] = True
                        stack.append(j)
                        members.append(j)
            if touches and enclosed and len(members) <= 80:
                reached[members] = True
                absorbed += len(members)
        own = reached[point]
        off_arm = np.minimum(np.minimum(to_segment(P, S, E), to_segment(P, E, H)), to_segment(P, H, tip))
        if (own & (off_arm > 0.12)).sum() > 0.2 * max(1, own.sum()):
            result[s] = {'skipped': 'the upper arm looks like the outfit around it (a sleeve): nothing to hold'}
            continue
        around = (1.0 - smooth((t / L - 0.35) / 0.25)) * (1.0 - smooth((dist - 0.18) / 0.06))
        hold = np.maximum(around, smooth((off_arm - 0.06) / 0.03) * (arm_weight < 0.98))
        hold[own | (arm_weight < 1e-4) | ((t > L) & (arm_weight >= 0.98))] = 0.0
        edge = np.nonzero((hold > 0.5) & (around > 0.5))[0]
        if len(edge):
            tree = KDTree(len(edge))
            for n, i in enumerate(edge):
                tree.insert(Vector(P[i]), n)
            tree.balance()
            for i in np.nonzero(own & (dist < 0.30) & (arm_weight > 1e-4))[0]:
                hold[i] = (1.0 - smooth(tree.find(Vector(P[i]))[2] / band_m)) * around[i]
        clavicle = body.vertex_groups[f'clavicle_{s}']
        moved, touched, skin = 0.0, 0, 0
        for i in np.nonzero(hold > 1e-3)[0]:
            ws = {g.group: g.weight for g in me.vertices[i].groups}
            taken = sum(w for gi, w in ws.items() if gi in arm_chain) * hold[i]
            if taken <= 1e-4:
                continue
            rest = sum(w for gi, w in ws.items() if gi not in arm_chain)
            for gi, w in ws.items():
                if gi in arm_chain:
                    body.vertex_groups[gi].add([int(i)], w * (1.0 - hold[i]), 'REPLACE')
                elif rest > 1e-4:
                    body.vertex_groups[gi].add([int(i)], w + taken * w / rest, 'REPLACE')
            if rest <= 1e-4:
                clavicle.add([int(i)], taken, 'ADD')
            moved += taken
            touched += 1
            skin += bool(own[i])
        result[s] = {'arm_surface_vertices': int((own & (dist < 0.30)).sum()), 'specks_absorbed': absorbed,
                     'held_vertices': touched, 'of_them_arm_surface': skin, 'weight_moved': round(float(moved), 1)}
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    return result


if settings.get('armhole_hold_cm', 0) > 0:
    report['armhole_hold'] = armhole_hold(settings['armhole_hold_cm'] / 100)


def layer_follow(gap_m, passes=3):
    """Garment layers a few millimetres apart get slightly different weights from the stand-in (each samples its own
    nearest point), and any leg lift pushes the under layer through the upper one (Remora: trouser triangles through
    the tunic's front panel in every run frame; 11,700 outfit vertices sit under another outfit layer at a median 4 mm).
    An outfit vertex whose outward normal meets a covering outfit surface within gap_m takes that surface's weights at
    the point it meets, so the two move as one. The cover is another connected piece, or the same piece wrapped over
    itself and facing the same way (a crossover front); the search passes through the vertex's own back faces (a
    flap's lining) and stops at skin. Covered vertices keep up to eight influences: a blend of three cover vertices
    is often five or six bones, and trimming it to four put the marks straight back (V21). The reverse direction (the
    cover rides the layer beneath) left them too: a flap has far fewer vertices than what it covers. Skin, hair and
    rigid head parts are left alone; mesh data other than weights is not touched (the bmesh is read only)."""
    from mathutils.bvhtree import BVHTree
    from mathutils.interpolate import poly_3d_calc
    garment = {i for i, m in enumerate(body.data.materials)
               if m and material_kind(m.name, job) is None and not is_hair(m.name, job)}
    unit = body.matrix_world.to_scale().x or 1.0
    step, reach = 0.0008 / unit, gap_m / unit
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    part, parts = {}, 0
    for v in bm.verts:
        if v.index in part:
            continue
        stack = [v]
        part[v.index] = parts
        while stack:
            a = stack.pop()
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in part:
                    part[b.index] = parts
                    stack.append(b)
        parts += 1
    tree = BVHTree.FromBMesh(bm)
    worn = {v.index for f in bm.faces if f.material_index in garment for v in f.verts}

    def cover(v):
        origin, left = v.co + v.normal * step, reach
        for _ in range(8):
            hit, normal, index, dist = tree.ray_cast(origin, v.normal, left)
            if hit is None:
                return None
            f = bm.faces[index]
            if f.material_index not in garment:
                return None
            facing = normal.dot(v.normal)
            if (part[f.verts[0].index] != part[v.index] and facing > 0.2) or facing > 0.5:
                return f, hit
            origin, left = hit + v.normal * step, left - dist - step
            if left <= 0:
                return None
        return None

    changed = 0
    for _ in range(passes):
        snap = [{g.group: g.weight for g in v.groups} for v in body.data.vertices]
        changed = 0
        for v in bm.verts:
            if v.index not in worn:
                continue
            found = cover(v)
            if not found:
                continue
            f, hit = found
            mixed = {}
            for c, w in zip(f.verts, poly_3d_calc([c.co for c in f.verts], hit)):
                for gi, gw in snap[c.index].items():
                    mixed[gi] = mixed.get(gi, 0.0) + gw * w
            for g in body.vertex_groups:
                if mixed.get(g.index, 0.0) > 1e-4:
                    g.add([v.index], mixed[g.index], 'REPLACE')
                elif g.index in snap[v.index]:
                    g.remove([v.index])
            changed += 1
    bm.free()
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=8)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    most = max(sum(1 for g in v.groups if g.weight > 0) for v in body.data.vertices)
    return {'gap_mm': round(gap_m * 1000, 1), 'passes': passes, 'vertices': changed, 'connected_parts': parts,
            'influence_cap': 8, 'most_influences': most}


if settings.get('layer_follow_mm', 0) > 0:
    report['layer_follow'] = layer_follow(settings['layer_follow_mm'] / 1000)
per_bone = {g.name: 0 for g in body.vertex_groups}
names = {g.index: g.name for g in body.vertex_groups}
for v in body.data.vertices:
    for g in v.groups:
        if g.weight > 0.05:
            per_bone[names[g.group]] += 1
report.update({'method': 'heat on voxel stand-in, nearest-surface transfer', 'influence_cap': 4,
               'deform_bones_without_vertices': sorted(b for b in deform if per_bone.get(b, 0) == 0),
               'seconds': round(time.monotonic() - started, 1)})
out.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out.resolve()))
Path(str(out) + '.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print('GAME_REVIEW_BIND', json.dumps(report))
