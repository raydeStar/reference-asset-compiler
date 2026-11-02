"""Replace the Raider's fused acquired gloves with the painted hand-only acquisition on both sides.

Unbiased slice bounding-box centres fit coaxial forearm axes on both the hand asset and the body arms
(avoiding vertex-density bias from the fingers and rolled cuff folds). The hand asset is cut high on its
uniform bare-skin band (preserving 100% of the sculpted rounded leather gauntlet top welt) and its bare
forearm section is smoothly morphed along the arm axis into the rolled sleeve cuff bore. Synthetic inward-
extruded boundary skirts on the body's forearm skin and old glove/fingertip scraps are removed, and the
rolled sleeve cuff's inner crease is cleanly tucked along a planar ring inside the forearm cylinder.

  $B -b raider-parts-v2.blend --python place_hands.py -- <assembled.glb> <hand.glb> <crop.png> <crop.lineage.json> \
     <ids.npy> <out.glb>
"""
import bpy, bmesh, sys, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
asm_p, hand_p = a[0], a[1]
out_p = a[-1]

low = bpy.data.collections["low"]
part_objs = [o for o in low.objects if o.type == 'MESH']
total_f = sum(len(o.data.polygons) for o in part_objs)
kd = KDTree(total_f)
f_part = []
idx = 0
for o in part_objs:
    for p in o.data.polygons:
        kd.insert(o.matrix_world @ p.center, idx)
        f_part.append(o.name)
        idx += 1
kd.balance()

for o in list(bpy.context.scene.objects):
    if o.type == 'MESH':
        o.hide_render = True

bpy.ops.import_scene.gltf(filepath=asm_p)
asm = [o for o in bpy.context.selected_objects if o.type == 'MESH']
body = next(o for o in asm if "body" in o.name)
head = next(o for o in asm if "head" in o.name)
body.name = "raider_body"
head.name = "raider_head"
body.data.transform(body.matrix_world); body.matrix_world = Matrix.Identity(4)
head.data.transform(head.matrix_world); head.matrix_world = Matrix.Identity(4)

bpy.ops.import_scene.gltf(filepath=hand_p)
hand = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]
hand.name = "raider_hand_r"
hand.data.transform(hand.matrix_world); hand.matrix_world = Matrix.Identity(4)

S = 0.195
hand.data.transform(Matrix.Scale(S, 4))

Vh = np.array([v.co[:] for v in hand.data.vertices])
axis_h = np.array([-0.54880033, -0.06742087, -0.83323024])
axis_h /= np.linalg.norm(axis_h)
c_ref_h = np.array([-0.00326051, 0.01692191, 0.05782961])

th_all = (Vh - c_ref_h) @ axis_h
sl_welt = np.abs(th_all - (-0.067)) < 0.003
ch = 0.5 * (Vh[sl_welt].min(0) + Vh[sl_welt].max(0))

# Cut hand at T_CUT_H = -0.105 (t_rel = -0.038, inside the 360-deg uniform bare-skin band above the leather gauntlet welt)
T_CUT_H = -0.105
hb = bmesh.new(); hb.from_mesh(hand.data)
bmesh.ops.remove_doubles(hb, verts=hb.verts[:], dist=1e-6)
plane_co = Vector((c_ref_h + axis_h * T_CUT_H).tolist())
plane_no = Vector((-axis_h).tolist())
bmesh.ops.bisect_plane(hb, geom=hb.verts[:] + hb.edges[:] + hb.faces[:], plane_co=plane_co, plane_no=plane_no, clear_outer=True)

hb.faces.ensure_lookup_table(); seen = set(); pieces = []
for f in hb.faces:
    if f.index in seen:
        continue
    stack = [f]; seen.add(f.index); piece = []
    while stack:
        g = stack.pop(); piece.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index); stack.append(h)
    pieces.append(piece)
pieces.sort(key=len, reverse=True)
hand_faces_cut = sum(len(p) for p in pieces[1:])
bmesh.ops.delete(hb, geom=[f for p in pieces[1:] for f in p], context='FACES')
bmesh.ops.triangulate(hb, faces=hb.faces)
hb.normal_update()
fold_verts = set()
for e in hb.edges:
    if len(e.link_faces) == 2 and e.calc_face_angle(0) > 1.0:
        for v in e.verts:
            fold_verts.add(v)
            for le in v.link_edges:
                fold_verts.add(le.other_vert(v))
for _ in range(4):
    updates = {}
    for v in fold_verts:
        if v.is_boundary:
            continue
        nbrs = [le.other_vert(v).co for le in v.link_edges]
        if nbrs:
            updates[v] = sum(nbrs, Vector((0.0, 0.0, 0.0))) / len(nbrs)
    for v, co_new in updates.items():
        v.co = 0.35 * v.co + 0.65 * co_new
hb.to_mesh(hand.data); hb.free()

# Weld body seams and measure unbiased slice-bbox arm axes from non-boundary outer forearm vertices
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()

Vb = np.array([v.co[:] for v in bm.verts])
is_bnd_v = np.array([v.is_boundary for v in bm.verts], dtype=bool)

arm_axes = {}
for side, sg in (('r', -1), ('l', 1)):
    arm_v = set()
    for f in bm.faces:
        fc = f.calc_center_median()
        if sg * fc.x > 0.25 and fc.z > 0.05:
            _, fi, _ = kd.find(fc)
            if f_part[fi] in ('skin', 'glove'):
                for v in f.verts:
                    if not v.is_boundary:
                        arm_v.add(v.index)
    arm_mask = np.zeros(len(Vb), bool); arm_mask[list(arm_v)] = True
    ax = np.array([sg * 0.43263932, -0.30733883, -0.84756478]); ax /= np.linalg.norm(ax)
    cref = np.array([sg * 0.46579623, -0.01634728, 0.1502606])
    for _ in range(6):
        tb = (Vb - cref) @ ax
        centers = []
        for t0 in np.linspace(-0.08, 0.08, 17):
            sl = arm_mask & (np.abs(tb - t0) < 0.006)
            if sl.sum() > 10:
                pts = Vb[sl]
                centers.append(0.5 * (pts.min(0) + pts.max(0)))
        centers = np.array(centers)
        cref = centers.mean(0)
        _, _, vh = np.linalg.svd(centers - cref, full_matrices=False)
        ax = vh[0]
        if ax[2] > 0:
            ax = -ax
    tb = (Vb - cref) @ ax
    sl_join = arm_mask & (np.abs(tb - (-0.032)) < 0.005)
    c_join = 0.5 * (Vb[sl_join].min(0) + Vb[sl_join].max(0))
    arm_axes[side] = (ax, cref, c_join, arm_mask)

left = hand.copy(); left.data = hand.data.copy(); left.name = "raider_hand_l"
bpy.context.scene.collection.objects.link(left)

cyl_profiles = {}
rot_degs = {}
for side, obj, sg in (('r', hand, -1), ('l', left, 1)):
    ax_b, cref_b, c_join, arm_mask = arm_axes[side]
    if side == 'l':
        obj.data.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
        obj.data.flip_normals()
        ax_h_side = np.array([-axis_h[0], axis_h[1], axis_h[2]])
        ch_side = np.array([-ch[0], ch[1], ch[2]])
    else:
        ax_h_side = axis_h.copy()
        ch_side = ch.copy()
    R = Vector(ax_h_side.tolist()).rotation_difference(Vector(ax_b.tolist())).to_matrix().to_4x4()
    M = Matrix.Translation(Vector(c_join.tolist())) @ R @ Matrix.Translation(-Vector(ch_side.tolist()))
    obj.data.transform(M)
    rot_degs[side] = float(np.degrees(np.arccos(np.clip(ax_h_side @ ax_b, -1.0, 1.0))))

    u = np.cross(ax_b, [0, 1, 0]); u /= np.linalg.norm(u)
    v_ort = np.cross(ax_b, u); v_ort /= np.linalg.norm(v_ort)

    # Measure sleeve inner bore radius profile r_top(theta) from all non-boundary outer forearm vertices in -0.115 < tb < -0.104
    tb_b = (Vb - cref_b) @ ax_b
    c_sl_all = c_join + np.outer(tb_b - (-0.032), ax_b)
    rel_b = (Vb - c_sl_all) - np.outer((Vb - c_sl_all) @ ax_b, ax_b)
    rad_b = np.hypot(rel_b @ u, rel_b @ v_ort)
    ang_b = np.arctan2(rel_b @ v_ort, rel_b @ u)
    sl_b_top = arm_mask & (~is_bnd_v) & (tb_b > -0.115) & (tb_b < -0.104)
    ang_b_top = ang_b[sl_b_top]; rad_b_top = rad_b[sl_b_top]

    # Measure hand's smooth wrist skin radius profile r_bot(theta) right above the leather gauntlet welt (t_rel in [-0.008, -0.003])
    Vh_now = np.array([v.co[:] for v in obj.data.vertices])
    t_rel_all = (Vh_now - c_join) @ ax_b
    sl_h_bot = (t_rel_all >= -0.008) & (t_rel_all <= -0.003)
    pts_h_bot = (Vh_now[sl_h_bot] - c_join) - np.outer(t_rel_all[sl_h_bot], ax_b)
    ang_h_bot = np.arctan2(pts_h_bot @ v_ort, pts_h_bot @ u)
    rad_h_bot = np.hypot(pts_h_bot @ u, pts_h_bot @ v_ort)

    ang_grid = np.linspace(-math.pi, math.pi, 72, endpoint=False)
    r_bot_grid = np.zeros_like(ang_grid)
    r_top_grid = np.zeros_like(ang_grid)
    for idx_a, th_a in enumerate(ang_grid):
        d_bot = np.abs(np.arctan2(np.sin(ang_h_bot - th_a), np.cos(ang_h_bot - th_a)))
        m_bot = d_bot < 0.35
        r_bot_grid[idx_a] = float(np.median(rad_h_bot[m_bot])) if m_bot.any() else 0.0485
        d_top = np.abs(np.arctan2(np.sin(ang_b_top - th_a), np.cos(ang_b_top - th_a)))
        m_top = d_top < 0.35
        r_top_grid[idx_a] = float(np.median(rad_b_top[m_top])) if m_top.any() else 0.0620
    for _ in range(3):
        r_bot_grid = 0.2 * (np.roll(r_bot_grid, -2) + np.roll(r_bot_grid, -1) + r_bot_grid + np.roll(r_bot_grid, 1) + np.roll(r_bot_grid, 2))
        r_top_grid = 0.2 * (np.roll(r_top_grid, -2) + np.roll(r_top_grid, -1) + r_top_grid + np.roll(r_top_grid, 1) + np.roll(r_top_grid, 2))

    def eval_polar(theta, grid):
        pos = ((theta + math.pi) / (2.0 * math.pi)) * len(grid)
        i0 = int(math.floor(pos)) % len(grid)
        i1 = (i0 + 1) % len(grid)
        frac = pos - math.floor(pos)
        return (1.0 - frac) * grid[i0] + frac * grid[i1]

    def make_eval_cyl(c_join_, ax_b_, r_bot_g, r_top_g):
        def eval_cyl(t_new, theta):
            s_len = np.clip((-0.0025 - t_new) / (-0.0025 - (-0.084)), 0.0, 1.0)
            r_b = eval_polar(theta, r_bot_g)
            r_t = eval_polar(theta, r_top_g)
            r_c = (1.0 - s_len) * r_b + s_len * r_t
            c_sl = c_join_ + t_new * ax_b_
            return c_sl, r_c
        return eval_cyl

    eval_cyl_fn = make_eval_cyl(c_join, ax_b, r_bot_grid.copy(), r_top_grid.copy())
    cyl_profiles[side] = (u, v_ort, eval_cyl_fn)

    for v in obj.data.vertices:
        p = np.array(v.co[:])
        t_rel = (p - c_join) @ ax_b
        if t_rel < -0.0025:
            # Stretch from t_rel in [-0.0025, -0.038] to t_new in [-0.0025, -0.090] (reaching tb = -0.122 inside the rolled sleeve cuff)
            s = np.clip((-0.0025 - t_rel) / (-0.0025 - (-0.038)), 0.0, 1.0)
            t_new = -0.0025 - s * 0.0875
            rel_p = (p - c_join) - t_rel * ax_b
            r_orig = np.linalg.norm(rel_p)
            theta = math.atan2(rel_p @ v_ort, rel_p @ u)
            c_sl, r_cyl = eval_cyl_fn(t_new, theta)
            if t_new < -0.086:
                tuck_top = np.clip((-0.086 - t_new) / 0.004, 0.0, 1.0)
                r_cyl -= 0.0020 * tuck_top
            w = np.clip((-0.0025 - t_rel) / 0.0040, 0.0, 1.0)
            w_sm = w * w * (3.0 - 2.0 * w)
            r_final = (1.0 - w_sm) * r_orig + w_sm * r_cyl
            dir_radial = math.cos(theta) * u + math.sin(theta) * v_ort
            v.co = Vector((c_sl + dir_radial * r_final).tolist())

# Identify synthetic inward-extruded skirt vertices on skin (v.is_boundary in tb > -0.123 and r < 0.064)
skirt_verts = set()
for v in bm.verts:
    if v.is_boundary and abs(v.co.x) > 0.28 and v.co.z > 0.05:
        co = np.array(v.co[:])
        side = 'r' if co[0] < 0 else 'l'
        ax_b, cref_b, c_join, _ = arm_axes[side]
        tb = (co - cref_b) @ ax_b
        c_sl = c_join + (tb - (-0.032)) * ax_b
        rel = (co - c_sl) - ((co - c_sl) @ ax_b) * ax_b
        r = np.linalg.norm(rel)
        if tb > -0.123 and r < 0.064:
            skirt_verts.add(v.index)

# Delete old glove faces, fingertip scraps mislabelled trousers, synthetic skin skirt faces, and bare skin faces below tb = -0.105
drop_faces = []
for f in bm.faces:
    fc = np.array(f.calc_center_median()[:])
    if abs(fc[0]) > 0.25 and fc[2] > -0.20:
        side = 'r' if fc[0] < 0 else 'l'
        ax_b, cref_b, c_join, _ = arm_axes[side]
        tb = (fc - cref_b) @ ax_b
        _, fi, _ = kd.find(f.calc_center_median())
        pn = f_part[fi]
        if pn == 'glove' or (pn == 'trousers' and abs(fc[0]) > 0.36 and tb > -0.06):
            drop_faces.append(f)
        elif pn == 'skin':
            if tb > -0.105 or any(v.index in skirt_verts for v in f.verts):
                drop_faces.append(f)

body_faces_dropped = len(drop_faces)
bmesh.ops.delete(bm, geom=drop_faces, context='FACES')

# Remove any small disconnected fragments near the arms
bm.faces.ensure_lookup_table(); seen = set(); comps = []
for f in bm.faces:
    if f.index in seen:
        continue
    stack = [f]; seen.add(f.index); comp = []
    while stack:
        g = stack.pop(); comp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index); stack.append(h)
    comps.append(comp)
for comp in comps:
    if len(comp) < 250:
        pts = np.array([f.calc_center_median()[:] for f in comp])
        if abs(pts[:, 0].mean()) > 0.28 and pts[:, 2].mean() > 0.0:
            bmesh.ops.delete(bm, geom=comp, context='FACES')

# Insert planar edge loops on arm skin faces at tb = -0.1180, -0.1165, and bisect+clear_outer at tb = -0.1145
for side, sg in (('r', -1), ('l', 1)):
    ax_b, cref_b, c_join, _ = arm_axes[side]
    for tb_cut, clear_out in ((-0.1180, False), (-0.1165, False), (-0.1145, True)):
        bm.faces.ensure_lookup_table()
        skin_faces = []
        for f in bm.faces:
            fc = f.calc_center_median()
            if sg * fc.x > 0.25 and fc.z > 0.05:
                tb = (np.array(fc[:]) - cref_b) @ ax_b
                if -0.125 < tb < -0.100:
                    _, fi, _ = kd.find(fc)
                    if f_part[fi] == 'skin':
                        skin_faces.append(f)
        geom_sub = list({v for f in skin_faces for v in f.verts}) + list({e for f in skin_faces for e in f.edges}) + skin_faces
        p_co = Vector((cref_b + tb_cut * ax_b).tolist())
        p_no = Vector(ax_b.tolist())
        bmesh.ops.bisect_plane(bm, geom=geom_sub, plane_co=p_co, plane_no=p_no, clear_outer=clear_out)

bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.verts.ensure_lookup_table()
for v in bm.verts:
    co = np.array(v.co[:])
    if abs(co[0]) > 0.28 and co[2] > 0.05:
        side = 'r' if co[0] < 0 else 'l'
        ax_b, cref_b, c_join, _ = arm_axes[side]
        tb = (co - cref_b) @ ax_b
        if -0.1180 < tb <= -0.1135:
            t_new = tb - (-0.032)
            c_sl = c_join + t_new * ax_b
            rel_p = (co - c_sl) - ((co - c_sl) @ ax_b) * ax_b
            r = np.linalg.norm(rel_p)
            u, v_ort, eval_cyl_fn = cyl_profiles[side]
            theta = math.atan2(rel_p @ v_ort, rel_p @ u)
            _, r_cyl = eval_cyl_fn(t_new, theta)
            if r < r_cyl + 0.006:
                w = float(np.clip((tb - (-0.1180)) / 0.0020, 0.0, 1.0))
                r_targ = min(r, r_cyl - 0.0015)
                r_new = (1.0 - w) * r + w * r_targ
                dir_rad = math.cos(theta) * u + math.sin(theta) * v_ort
                v.co = Vector((c_sl + dir_rad * r_new).tolist())

bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(body.data); bm.free()
for p in body.data.polygons:
    p.use_smooth = True
for o in (hand, left):
    bm_h = bmesh.new(); bm_h.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm_h, faces=bm_h.faces[:])
    bm_h.to_mesh(o.data); bm_h.free()
    for p in o.data.polygons:
        p.use_smooth = True

keep = [body, head, hand, left]
for o in bpy.context.scene.objects:
    o.select_set(o in keep)
bpy.ops.export_scene.gltf(filepath=out_p, export_format='GLB', use_selection=True)
json.dump({
    "scale": S,
    "rotation_deg": [round(rot_degs['r'], 2), round(rot_degs['l'], 2)],
    "cut_plane_t": T_CUT_H,
    "body_glove_faces_dropped": body_faces_dropped,
    "hand_faces_cut": hand_faces_cut,
    "kept_hand_faces": len(hand.data.polygons),
    "body_faces": len(body.data.polygons),
}, open(out_p + ".json", "w"), indent=2)
print("HANDS_OK")
