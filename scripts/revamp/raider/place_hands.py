"""Replace the Raider's fused acquired gloves with the painted hand-only acquisition, on both sides.

Placement is measured, not eyeballed: the hand crop's square in reference pixels (its lineage JSON) and
the hand's silhouette inside the crop give the mesh's x/z extent in reference pixels; the same
reference-to-body mapping that placed the part labels (scale, x and z offsets) turns that into body
units. Depth comes from the old glove. The left hand is the right hand mirrored, moved by the offset
between the old left glove and the mirrored old right glove. Hand faces painted as skin or sleeve are
cut, so only the leather glove and gauntlet remain; the body keeps its own forearm skin.

  $B -b raider-parts-v2.blend --python place_hands.py -- <assembled.glb> <hand.glb> <crop.png> <crop.lineage.json> \
     <ids.npy> <out.glb>
"""
import bpy, bmesh, sys, json, colorsys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]; asm_p, hand_p, crop_p, lin_p, ids_p, out_p = a
low = bpy.data.collections["low"]
parts = sorted([o for o in low.objects if o.type == 'MESH'], key=lambda o: o.name)
trees = {}
for o in parts:
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    trees[o.name] = BVHTree.FromPolygons([o.matrix_world @ v.co for v in me.vertices], [list(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
# reference-to-body mapping, recomputed exactly as the label projection did
ids = np.load(ids_p); IH, IW = ids.shape; ys, xs = np.nonzero(ids != 255)
iy0, iy1, ix0, ix1 = ys.min(), ys.max(), xs.min(), xs.max()
dense = [o for o in bpy.data.objects if o.name.endswith("_dense")]
DV = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in dense])
s_ref = (iy1 - iy0) / np.ptp(DV[:, 2]); ox = ix0 + (ix1 - ix0) / 2 - s_ref * (DV[:, 0].min() + DV[:, 0].max()) / 2
oy = iy0 + s_ref * DV[:, 2].max()
glove = bpy.data.objects["glove_dense"]; GV = np.array([(glove.matrix_world @ v.co)[:] for v in glove.data.vertices])
old = {sd: GV[np.sign(GV[:, 0]) == sg] for sd, sg in (("r", -1), ("l", 1))}
# the old glove's own dense surface catches fingertip scraps the part lookup assigned elsewhere
glove_tree = BVHTree.FromPolygons([glove.matrix_world @ v.co for v in glove.data.vertices], [list(p.vertices) for p in glove.data.polygons])
for o in list(bpy.context.scene.objects):
    if o.type == 'MESH': o.hide_render = True

bpy.ops.import_scene.gltf(filepath=asm_p)
asm = [o for o in bpy.context.selected_objects if o.type == 'MESH']
body = next(o for o in asm if o.name.startswith("raider_body")); body.name = "raider_body"
bm = bmesh.new(); bm.from_mesh(body.data); drop = []
for f in bm.faces:
    c = body.matrix_world @ f.calc_center_median(); best, name = 1e9, None
    for n, t in trees.items():
        h = t.find_nearest(c)
        if h[0] is not None and h[3] < best: best, name = h[3], n
    near_old = glove_tree.find_nearest(c)
    if name == "glove" or (near_old[0] is not None and near_old[3] < 0.012): drop.append(f)
bmesh.ops.delete(bm, geom=drop, context='FACES'); bm.to_mesh(body.data); bm.free()
print("BODY glove faces dropped", len(drop))

# the hand's silhouette in the crop, in reference pixels
lin = json.load(open(lin_p)); sq = lin["square"]; side = sq[2] - sq[0]
import struct
crop = bpy.data.images.load(crop_p); CW, CH = crop.size
P = np.array(crop.pixels[:], np.float32).reshape(CH, CW, -1)[::-1]  # top row first
fg = P[:, :, :3].min(2) < 0.92; rr, cc = np.nonzero(fg)
k = side / CW
fx0, fx1 = sq[0] + cc.min() * k, sq[0] + cc.max() * k; fz0, fz1 = sq[1] + rr.min() * k, sq[1] + rr.max() * k
bpy.ops.import_scene.gltf(filepath=hand_p); hand = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]
hand.data.transform(hand.matrix_world); hand.matrix_world = Matrix.Identity(4)
HV = np.array([v.co[:] for v in hand.data.vertices])
# body units: x = (px - ox) / s, z = (oy - py) / s ; mesh x grows with image x (front view, front is -y)
bx0, bx1 = (fx0 - ox) / s_ref, (fx1 - ox) / s_ref; bz1, bz0 = (oy - fz0) / s_ref, (oy - fz1) / s_ref
sx = (bx1 - bx0) / np.ptp(HV[:, 0]); sz = (bz1 - bz0) / np.ptp(HV[:, 2]); sc = float(0.5 * (sx + sz))
print("HAND scale x", round(float(sx), 4), "z", round(float(sz), 4), "used", round(sc, 4))
tx = float((bx0 + bx1) / 2 - sc * (HV[:, 0].min() + HV[:, 0].max()) / 2)
tz = float((bz0 + bz1) / 2 - sc * (HV[:, 2].min() + HV[:, 2].max()) / 2)
ty = float(np.median(old["r"][:, 1]) - sc * np.median(HV[:, 1]))
hand.data.transform(Matrix.Translation((tx, ty, tz)) @ Matrix.Scale(sc, 4))

# cut the forearm off with one plane where the painted skin begins (a per-face colour cut shredded the
# gauntlet: its highlights read as skin), then drop loose scraps
img = None
for m in hand.data.materials:
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and any(l.to_socket.name == "Base Color" for l in n.outputs[0].links): img = n.image
IWd, IHd = img.size; TX = np.array(img.pixels[:], np.float32).reshape(IHd, IWd, -1)
def pca_axis(P):
    c = P.mean(0); w, v = np.linalg.eigh(np.cov((P - c).T)); return c, v[:, -1], v[:, -2]
hb = bmesh.new(); hb.from_mesh(hand.data)
# the painter splits vertices along UV seams; weld them (UVs live on loops and survive) so pieces are real
bmesh.ops.remove_doubles(hb, verts=hb.verts[:], dist=1e-6)
hb.faces.ensure_lookup_table(); uvl = hb.loops.layers.uv.active
FC = np.array([f.calc_center_median()[:] for f in hb.faces]); skin = np.zeros(len(FC), bool)
for i, f in enumerate(hb.faces):
    u = sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    r, g, b = TX[min(IHd - 1, int(u.y * IHd)), min(IWd - 1, int(u.x * IWd)), :3] ** (1 / 2.2)
    hh, ss, vv = colorsys.rgb_to_hsv(float(r), float(g), float(b)); hh *= 360
    skin[i] = (12 <= hh <= 40 and ss > 0.3 and vv > 0.5) or (150 <= hh <= 240 and ss > 0.12)
c0, ax, _ = pca_axis(FC)
if (FC[skin] - c0).dot(ax).mean() < 0: ax = -ax          # axis runs from the fingers toward the elbow
t = (FC - c0) @ ax; T = float(np.percentile(t[skin], 8))
print("HAND axis t range", round(float(t.min()), 3), round(float(t.max()), 3), "skin faces", int(skin.sum()), "of", len(t))
plane_co = Vector((c0 + ax * T).tolist()); plane_no = Vector(ax.tolist())
bmesh.ops.bisect_plane(hb, geom=hb.verts[:] + hb.edges[:] + hb.faces[:], plane_co=plane_co, plane_no=plane_no, clear_outer=True)
# keep the largest connected piece
hb.faces.ensure_lookup_table(); seen = set(); pieces = []
for f in hb.faces:
    if f.index in seen: continue
    stack = [f]; seen.add(f.index); piece = []
    while stack:
        g = stack.pop(); piece.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen: seen.add(h.index); stack.append(h)
    pieces.append(piece)
pieces.sort(key=len, reverse=True)
bmesh.ops.delete(hb, geom=[f for p in pieces[1:] for f in p], context='FACES')
hb.to_mesh(hand.data); hb.free()
print("HAND plane cut at", round(T, 4), "pieces dropped", len(pieces) - 1, "kept faces", len(hand.data.polygons))
hand.name = "raider_hand_r"

# the gauntlet's top sits this far up the arm past the old glove's top, covering the forearm skin's ragged
# lower edge (the old glove/skin label boundary); the reference's gauntlet runs that far up anyway
WRIST_OVERLAP = 0.035
def align_to_glove(obj, oldP, mirror):
    """Rotate the hand's axis onto the old glove's axis and put its cut ring at the old glove's wrist."""
    if mirror:
        obj.data.transform(Matrix.Scale(-1, 4, (1, 0, 0))); obj.data.flip_normals()
    P = np.array([v.co[:] for v in obj.data.vertices]); cn, an, _ = pca_axis(P)
    tn = (P - cn) @ an
    if np.percentile(tn, 99) - tn.max() == 0: pass
    # the cut ring is the hand's elbow end: orient the axis toward it
    ring_side = np.sign(((P - cn) @ an)[np.argsort((P - cn) @ an)[-50:]].mean())
    bm2 = bmesh.new(); bm2.from_mesh(obj.data); ring = np.array([v.co[:] for e in bm2.edges if e.is_boundary for v in e.verts]); bm2.free()
    top_new = ring.mean(0)
    if (top_new - cn) @ an < 0: an = -an
    co, ao, _ = pca_axis(oldP)
    if (oldP.mean(0) * 0 + np.array([0, 0, 1])) @ ao < 0: ao = -ao  # the old glove's axis points up the arm
    to = (oldP - co) @ ao; top_old = oldP[to > np.percentile(to, 92)].mean(0)
    R = Vector(an.tolist()).rotation_difference(Vector(ao.tolist())).to_matrix().to_4x4()
    M = Matrix.Translation(Vector(top_old.tolist()) + Vector(ao.tolist()) * WRIST_OVERLAP) @ R @ Matrix.Translation(-Vector(top_new.tolist()))
    obj.data.transform(M)
    bm3 = bmesh.new(); bm3.from_mesh(obj.data); ringw = np.array([v.co[:] for e in bm3.edges if e.is_boundary for v in e.verts]); bm3.free()
    rc = ringw.mean(0); rr = float(np.linalg.norm((ringw - rc) - np.outer((ringw - rc) @ ao, ao), axis=1).mean())
    openings.append((rc, ao, rr))
    return float(np.degrees(np.arccos(np.clip(an @ ao, -1, 1))))
openings = []
left = hand.copy(); left.data = hand.data.copy(); left.name = "raider_hand_l"; bpy.context.scene.collection.objects.link(left)
rot_r = align_to_glove(hand, old["r"], False); rot_l = align_to_glove(left, old["l"], True)
print("ALIGN rotation r", round(rot_r, 1), "l", round(rot_l, 1))
cut = []; off = np.zeros(3)
# final tidy: body faces inside or against the new gloves (the forearm-skin fringe under the gauntlet) go,
# then small loose bits near the hands (old glove slivers)
ht = []
for o in (hand, left):
    ht.append(BVHTree.FromPolygons([v.co.copy() for v in o.data.vertices], [list(p.vertices) for p in o.data.polygons]))
centres = [np.array([v.co[:] for v in o.data.vertices]).mean(0) for o in (hand, left)]
bm = bmesh.new(); bm.from_mesh(body.data); bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6); bm.faces.ensure_lookup_table()
inside = []
for f in bm.faces:
    c = body.matrix_world @ f.calc_center_median(); cv = np.array(c[:])
    # the forearm skin's jagged edge and skirt reach past the gauntlet's narrow top: clear everything below the
    # gauntlet opening within a generous radius (the glove covers it)
    tube = False
    for rc, ao_, rr in openings:
        tt = (cv - rc) @ ao_; rad = np.linalg.norm((cv - rc) - tt * ao_)
        if -0.25 < tt < 0.004 and rad < 2.5 * rr: tube = True
    if tube: inside.append(f); continue
    if min(np.linalg.norm(cv - k) for k in centres) > 0.25: continue
    for t in ht:
        loc, nrm, _, d = t.find_nearest(c)
        if loc is not None and (d < 0.006 or (c - loc).dot(nrm) < 0 and d < 0.05): inside.append(f); break
bmesh.ops.delete(bm, geom=inside, context='FACES'); bm.faces.ensure_lookup_table()
seen = set(); loose = []
for f in bm.faces:
    if f.index in seen: continue
    stack = [f]; seen.add(f.index); piece = []
    while stack:
        g = stack.pop(); piece.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen: seen.add(h.index); stack.append(h)
    pc = np.array((body.matrix_world @ piece[0].calc_center_median())[:])
    if len(piece) < 80 and min(np.linalg.norm(pc - k) for k in centres) < 0.45: loose += piece
bmesh.ops.delete(bm, geom=loose, context='FACES'); bm.to_mesh(body.data); bm.free()
print("TIDY inside", len(inside), "loose", len(loose))
keep = [o for o in asm] + [hand, left]
for o in bpy.context.scene.objects: o.select_set(o in keep)
bpy.ops.export_scene.gltf(filepath=out_p, export_format='GLB', use_selection=True)
json.dump({"scale": sc, "scale_x": float(sx), "scale_z": float(sz), "translate": [tx, ty, tz], "rotation_deg": [rot_r, rot_l], "cut_plane_t": T,
           "body_glove_faces_dropped": len(drop), "hand_faces_cut": len(cut)}, open(out_p + ".json", "w"), indent=2)
print("HANDS_OK")
