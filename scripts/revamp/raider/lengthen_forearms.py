"""Lengthen the Raider's forearms on the production mesh, written as a versioned derivative.

Mark: "a lot of missing forearm, making the character look like it has t-rex arms". Measured against the
reference at the same figure height (1.25 mm a pixel): shoulder to fingertip is 64 cm there and 58 cm here; the
reference shows a rolled sleeve ending about 8 cm past the elbow, about 6 cm of bare forearm and an 8.7 cm flared
gauntlet cuff. Here the sleeve ends 15 cm past the elbow and the hand-only acquisition's short glove cuff starts
2 to 3 cm inside it (the hand placement followed the whole-body acquisition's glove, whose forearm was already
short), so no forearm shows at all.

Per arm, along the forearm axis from the landmark elbow to the landmark wrist:
  1. the hand turns about its glove top to point along the sleeve's measured centreline and moves onto it, DELTA
     further out (shoulder to fingertip 58 -> 63 cm);
  2. the rolled cuff (the sleeve's last CUFF) lifts by SLEEVE_UP as one piece and the plain sleeve above it
     compresses over SLEEVE_SPAN, so the cuff keeps its shape;
  3. a skin tube runs from just inside the sleeve opening, following its slanted edge, to inside the glove,
     narrowing to the wrist; a dark lining spans the opening from the sleeve wall to the forearm;
  4. a flared leather gauntlet cuff, GAUNT long, rises from inside the glove over the skin.
Both are painted with the reference's own painting of those parts (strips along his forearm, copied into unused
hand-atlas space and wrapped so the front shows the front, mirrored for the left arm), matte there. One flat tone
per part, from a single texel, read as plastic.

  $B -b --factory-startup --python lengthen_forearms.py -- <production.glb> <landmarks.json> <out.glb> <reference.png> [delta_m]
"""
import bpy, bmesh, sys, json, math, os
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]; src, lm_p, out, ref_p = a[0], a[1], a[2], a[3]
DELTA = float(a[4]) if len(a) > 4 else 0.052
# the reference's own painting of the bare forearm and the gauntlet: strips along his right forearm in reference
# pixels (top centre, bottom centre, width), copied into unused space of the hand atlas (u0, v0, u1, v1)
REF_SKIN = ((205, 515), (197, 566), 44); PATCH_SKIN = (0.6875, 0.0, 0.75, 0.125)
REF_GAUNT = ((184, 595), (150, 652), 58); PATCH_GAUNT = (0.75, 0.0, 0.8125, 0.125)
PATCH_DARK = (0.8125, 0.0, 0.875, 0.125); DARK = (0.035, 0.045, 0.045)   # the shadowed inside of the sleeve
SLEEVE_UP, CUFF, SLEEVE_SPAN, CAP_IN, GAUNT, GLOVE_IN = 0.035, 0.035, 0.10, 0.01, 0.04, 0.035
SKIN_R = (0.055, 0.024)              # the forearm's largest radius at the sleeve, and at the wrist inside the glove
GAUNT_R = (0.034, 0.041)             # gauntlet at the glove, flared at its top
SEGS, RINGS = 24, 8
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
me_o = next(o for o in bpy.context.scene.objects if o.type == 'MESH'); me = me_o.data
me.transform(me_o.matrix_world); me_o.matrix_world.identity()
J = json.load(open(lm_p))["joints"]
P = np.array([v.co[:] for v in me.vertices]); nv = len(P)
mi = np.zeros(nv, int)
for p in me.polygons:
    for v in p.vertices: mi[v] = p.material_index
wrists = [np.array(J["hand_l"]), np.array(J["hand_r"])]
near = lambda k: sum(int((np.linalg.norm(P[mi == k] - w, axis=1) < 0.10).sum()) for w in wrists)
HAND = max(range(len(me.materials)), key=near); BODY = 0
print("LEN hand material", me.materials[HAND].name, "body material", me.materials[BODY].name)
def write_patches():
    mat = me.materials[HAND]
    texs = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
    base = next(n.image for n in texs if any(l.to_socket.name == 'Base Color' for l in n.outputs[0].links))
    mr = next((n.image for n in texs if n.image != base), None)
    ref = bpy.data.images.load(ref_p); RW, RH = ref.size
    R = np.empty(RW * RH * 4, np.float32); ref.pixels.foreach_get(R); R = R.reshape(RH, RW, 4)[::-1]   # rows top-down
    def sample(x, y):
        x0, y0 = int(x), int(y); fx, fy = x - x0, y - y0
        return (R[y0, x0] * (1 - fx) * (1 - fy) + R[y0, x0 + 1] * fx * (1 - fy) + R[y0 + 1, x0] * (1 - fx) * fy
                + R[y0 + 1, x0 + 1] * fx * fy)
    nodes = {n.image.name: n for n in texs}
    for img, is_mr in ((base, False), (mr, True)):
        if img is None: continue
        W_, H_ = img.size; X = np.empty(W_ * H_ * 4, np.float32); img.pixels.foreach_get(X); X = X.reshape(H_, W_, 4)
        for (A, B, wd), (u0, v0, u1, v1) in ((REF_SKIN, PATCH_SKIN), (REF_GAUNT, PATCH_GAUNT)):
            x0, x1, y0, y1 = int(u0 * W_), int(u1 * W_), int(v0 * H_), int(v1 * H_)
            if is_mr:
                X[y0:y1, x0:x1] = (1.0, 0.7, 0.0, 1.0); continue          # matte, not metal (G roughness, B metal)
            A_, B_ = np.array(A, float), np.array(B, float); d = B_ - A_; perp = np.array([d[1], -d[0]]) / np.linalg.norm(d)
            for yy in range(y0, y1):
                fy = (y1 - 1 - yy) / max(1, y1 - y0 - 1)                   # the strip's top at the patch's top
                for xx in range(x0, x1):
                    q = A_ + d * fy + perp * wd * ((xx - x0) / max(1, x1 - x0 - 1) - 0.5); X[yy, xx] = sample(*q)
        x0, x1, y0, y1 = int(PATCH_DARK[0] * W_), int(PATCH_DARK[2] * W_), int(PATCH_DARK[1] * H_), int(PATCH_DARK[3] * H_)
        X[y0:y1, x0:x1] = (1.0, 1.0, 0.0, 1.0) if is_mr else (*DARK, 1.0)
        img.pixels.foreach_set(X.ravel())
        path = os.path.join(os.path.dirname(out), os.path.splitext(os.path.basename(out))[0] + "-" + img.name + ".png")
        img.filepath_raw = path; img.file_format = 'PNG'; img.save()
        # the exporter embedded the imported original (packed) whatever the pixels said: load the saved file as a
        # fresh image and put it on the material
        new = bpy.data.images.load(path); new.colorspace_settings.name = img.colorspace_settings.name
        nodes[img.name].image = new
        print("LEN wrote patches into", img.name, "->", path)
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
uvb = bm.loops.layers.uv.active
geo = {}
for s, sign in (("l", 1), ("r", -1)):
    E, W = np.array(J[f"lowerarm_{s}"]), np.array(J[f"hand_{s}"]); L = np.linalg.norm(W - E); u = (W - E) / L
    t = (P - E) @ u; r = np.linalg.norm((P - E) - np.outer(t, u), axis=1)
    arm = (np.sign(P[:, 0]) == sign) & (r < 0.10) & (t > -0.05) & (t < L + 0.25)
    hand = arm & (mi == HAND); body = arm & (mi == BODY) & (t > 0.0)
    # the rolled cuff flares past 10 cm from the axis in places; it lifts whole (r < 12 cm)
    cuffwide = (np.sign(P[:, 0]) == sign) & (r < 0.12) & (mi == BODY) & (t > 0.0) & (t < L + 0.05)
    th0, tb1 = t[hand].min(), t[body].max()
    geo[s] = dict(E=E, u=u, L=L, t=t, hand=hand, body=body, cuffwide=cuffwide, th0=th0, tb1=tb1,
                  g_c=P[hand & (t < th0 + 0.04)].mean(0), K=np.array(J[f"middle_01_{s}"]))
    # the sleeve's own centreline: centres of two slices of its lower part, re-sliced square to the estimate a few
    # times (the landmark forearm runs about 12 degrees off it, and the hand-only acquisition's glove top sat 5 to
    # 6 cm off it, which showed as a kinked, off-centre forearm)
    d = u.copy()
    for _ in range(4):
        tt = (P - E) @ d; rr = np.linalg.norm((P - E) - np.outer(tt, d), axis=1)
        b2 = (np.sign(P[:, 0]) == sign) & (mi == BODY) & (rr < 0.07)
        tend = tt[b2 & (tt > 0) & (tt < L + 0.05)].max()
        c_lo = P[b2 & (tt > tend - 0.10) & (tt < tend - 0.06)].mean(0); c_hi = P[b2 & (tt > tend - 0.045) & (tt < tend - 0.005)].mean(0)
        d = (c_hi - c_lo) / np.linalg.norm(c_hi - c_lo)
    geo[s].update(d=d, c_hi=c_hi)
    # the sleeve opening's centre and radius from its last 5 cm (a thinner slab caught one side of the tilted
    # cuff and put the forearm against the sleeve's edge), moved along the arm to the opening
    slab = body & (t > tb1 - 0.05) & (r < 0.08); sc_ = P[slab].mean(0); tm = float(t[slab].mean())
    d_ = P[slab] - sc_; rad = np.linalg.norm(d_ - np.outer(d_ @ u, u), axis=1)
    geo[s].update(s_c=sc_ + (tb1 - tm) * u, s_r=float(np.percentile(rad, 75)))
bm.verts.ensure_lookup_table()
report = {"delta_m": DELTA, "sleeve_up_m": SLEEVE_UP, "gauntlet_m": GAUNT, "sides": {}}
def tube(a0, a1, rtop, r1, ax, mat, patch, out_sign, ease=1.0, toff=None, lining=None):
    """Rings from a0 to a1 about ax. rtop: the first ring's radius per segment (or one number); later rings narrow
    to r1 (ease > 1 narrows fast after the first ring). UVs wrap the patch: rows run from a0 to a1, columns go
    from the outer to the inner side (front and back mirror); out_sign says which x side is outer."""
    side_ax = np.cross(ax, [0, 1, 0]); side_ax /= np.linalg.norm(side_ax); up_ax = np.cross(side_ax, ax)
    rt = np.full(SEGS, rtop) if np.isscalar(rtop) else np.asarray(rtop)
    dirs = [math.cos(2 * math.pi * j / SEGS) * side_ax + math.sin(2 * math.pi * j / SEGS) * up_ax for j in range(SEGS)]
    to = np.zeros(SEGS) if toff is None else np.asarray(toff)
    rings = [[bm.verts.new(Vector(a0 + (a1 - a0) * (k / RINGS) + to[j] * (1 - k / RINGS) * ax
                                  + (r1 + (rt[j] - r1) * (1 - k / RINGS) ** ease) * dirs[j]))
              for j in range(SEGS)] for k in range(RINGS + 1)]
    lin = []
    if lining is not None:      # a dark ring across the opening, from the first ring out to the sleeve wall
        outer = [bm.verts.new(Vector(a0 + to[j] * ax + lining[j] * dirs[j])) for j in range(SEGS)]
        du0, dv0, du1, dv1 = PATCH_DARK; cuv = Vector(((du0 + du1) / 2, (dv0 + dv1) / 2))
        for j in range(SEGS):
            jj = (j + 1) % SEGS
            f = bm.faces.new([outer[j], outer[jj], rings[0][jj], rings[0][j]]); f.material_index = mat; f.smooth = True
            for lp in f.loops: lp[uvb].uv = cuv
            lin.append(f)
    u0, v0, u1, v1 = patch; m = 0.004
    def uv(j, k):
        c = 0.5 - 0.5 * out_sign * float(dirs[j][0])                   # 0 on the outer side, 1 on the inner
        return Vector((u0 + m + (u1 - u0 - 2 * m) * c, v1 - m - (v1 - v0 - 2 * m) * k / RINGS))
    faces = []
    for k in range(RINGS):
        for j in range(SEGS):
            jj = (j + 1) % SEGS
            f = bm.faces.new([rings[k][j], rings[k][jj], rings[k + 1][jj], rings[k + 1][j]])
            f.material_index = mat; f.smooth = True; faces.append(f)
            for lp, (a_, b_) in zip(f.loops, ((j, k), (jj, k), (jj, k + 1), (j, k + 1))): lp[uvb].uv = uv(a_, b_)
    bm.normal_update()
    c0 = np.array(faces[0].calc_center_median()[:]); radial = (c0 - a0) - ((c0 - a0) @ ax) * ax
    if np.dot(np.array(faces[0].normal[:]), radial) < 0:
        for f in faces: f.normal_flip()
        bm.normal_update()
    if lin:                     # the lining faces out of the sleeve, towards the hand
        bm.normal_update()
        if np.dot(np.array(lin[0].normal[:]), ax) < 0:
            for f in lin: f.normal_flip()
        bm.normal_update()
    return len(faces) + len(lin)
for s, g in geo.items():
    E, u, t, th0, tb1 = g["E"], g["u"], g["t"], g["th0"], g["tb1"]
    bm.verts.ensure_lookup_table()
    # 1. the hand turns about its glove top to point along the sleeve, and moves onto the sleeve's centreline,
    # DELTA further out than it was
    d, c_hi, gc = g["d"], g["c_hi"], g["g_c"]
    # the sleeve points 12-16 degrees towards the camera; the hand takes its side-to-side line from the sleeve but
    # its forward tilt from the landmark arm, so the forearm hangs in the front plane as in the reference (following
    # the sleeve fully foreshortened it in the front view)
    dh = np.array([d[0], u[1], d[2]]); dh /= np.linalg.norm(dh)
    hd = (g["K"] - gc) / np.linalg.norm(g["K"] - gc)
    Rm = Vector(hd).rotation_difference(Vector(dh)).to_matrix()
    gc_new = c_hi + dh * (float((gc - c_hi) @ dh) + DELTA)
    g["turn_deg"] = math.degrees(Vector(hd).angle(Vector(dh))); g["shift_cm"] = float(np.linalg.norm((gc - c_hi) - ((gc - c_hi) @ d) * d)) * 100
    for i in np.nonzero(g["hand"])[0]: bm.verts[i].co = Rm @ (bm.verts[i].co - Vector(gc)) + Vector(gc_new)
    for i in np.nonzero(g["cuffwide"] & (t > tb1 - CUFF - SLEEVE_SPAN))[0]:
        k = min(1.0, (t[i] - (tb1 - CUFF - SLEEVE_SPAN)) / SLEEVE_SPAN); bm.verts[i].co -= Vector(SLEEVE_UP * k * d)
    # centres: the sleeve opening and the glove opening (after the moves), the tube running between them
    s_end = g["s_c"] - SLEEVE_UP * d; g_end = gc_new
    ax = (g_end - s_end) / np.linalg.norm(g_end - s_end)
    s_r = g["s_r"]
    # the opening's outline: per direction about the tube axis, where the lifted cuff ends along the axis (the
    # opening is cut on a slant) and the sleeve's inner (25th percentile) radius CAP_IN inside that edge. A dark
    # lining spans the opening there, from the wall to the forearm (78% of the wall): a round tube pushed into the
    # opening poked out of one side and showed the hollow sleeve on the other, and squeezing its top ring to fit
    # crumpled it
    side_ax = np.cross(ax, [0, 1, 0]); side_ax /= np.linalg.norm(side_ax); up_ax = np.cross(side_ax, ax)
    q = P[g["cuffwide"] & (t > tb1 - 0.05)] - SLEEVE_UP * d - s_end
    qa = q @ ax; qp = q - np.outer(qa, ax)
    ang = np.arctan2(qp @ up_ax, qp @ side_ax); rr = np.linalg.norm(qp, axis=1)
    wall, tedge = [], []
    for j in range(SEGS):
        dd = np.abs((ang - 2 * math.pi * j / SEGS + math.pi) % (2 * math.pi) - math.pi); inb = dd < math.pi / SEGS * 1.5
        if inb.sum() < 3: wall.append(s_r); tedge.append(0.0); continue
        te = float(qa[inb].max()); at = inb & (np.abs(qa - (te - CAP_IN)) < 0.01)
        wall.append(np.percentile(rr[at], 25) if at.sum() >= 3 else s_r); tedge.append(te)
    sm = lambda x: (np.roll(x, 1) + 2 * x + np.roll(x, -1)) / 4
    wall = np.array(wall); tedge = np.array(tedge); med = float(np.median(tedge)); tedge = np.clip(tedge, med - 0.02, med + 0.02)
    for _ in range(3): wall, tedge = sm(wall), sm(tedge)
    wall = np.clip(0.97 * wall, 0.03, 0.065); rtop = np.clip(0.78 * wall, 0.028, SKIN_R[0])
    out_sign = sign             # the outer side of each arm is away from the body: +x for the left, -x for the right
    nf = tube(s_end, g_end + GLOVE_IN * ax, rtop, SKIN_R[1], ax, HAND, PATCH_SKIN, out_sign, ease=2.0, toff=tedge - CAP_IN,
              lining=wall)
    # the gauntlet runs from its top (towards the sleeve) down into the glove, the strip's way round
    ng = tube(g_end - GAUNT * ax, g_end + GLOVE_IN * ax, GAUNT_R[1], GAUNT_R[0], ax, HAND, PATCH_GAUNT, out_sign)
    report["sides"][s] = {"hand_turned_deg": round(g["turn_deg"], 1), "hand_onto_sleeve_line_cm": round(g["shift_cm"], 1),
                          "forearm_before_m": round(float(g["L"]), 4), "forearm_after_m": round(float(g["L"] + DELTA), 4),
                          "glove_started_inside_sleeve_m": round(float(tb1 - th0), 4),
                          "sleeve_to_glove_now_m": round(float(np.linalg.norm(g_end - s_end)), 4),
                          "bare_forearm_now_m": round(float(np.linalg.norm(g_end - s_end) - GAUNT), 4),
                          "sleeve_opening_r_m": round(s_r, 4), "top_ring_r_m": [round(float(rtop.min()), 4), round(float(rtop.max()), 4)], "cuff_slant_m": round(float(np.ptp(tedge)), 4), "skin_faces": nf, "gauntlet_faces": ng}
    print(f"LEN {s}:", report["sides"][s])
bm.to_mesh(me); bm.free()
write_patches()
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"derived_from": src, "forearms": report, "faces": len(me.polygons), "verts": len(me.vertices)})
json.dump(side, open(out + ".json", "w"), indent=2)
print("LENGTHEN_OK", len(me.polygons), "faces")
