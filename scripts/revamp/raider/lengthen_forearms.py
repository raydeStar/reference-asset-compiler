"""Lengthen the Raider's forearms on the production mesh, written as a versioned derivative.

Mark: "a lot of missing forearm, making the character look like it has t-rex arms". Measured against the
reference at the same figure height (1.25 mm a pixel): shoulder to fingertip is 64 cm there and 58 cm here; the
reference shows a rolled sleeve ending about 8 cm past the elbow, about 6 cm of bare forearm and an 8.7 cm flared
gauntlet cuff. Here the sleeve ends 15 cm past the elbow and the hand-only acquisition's short glove cuff starts
2 to 3 cm inside it (the hand placement followed the whole-body acquisition's glove, whose forearm was already
short), so no forearm shows at all.

Per arm, along the forearm axis from the landmark elbow to the landmark wrist:
  1. the hand moves out by DELTA as one piece (shoulder to fingertip 58 -> 63 cm);
  2. the rolled cuff (the sleeve's last CUFF) lifts by SLEEVE_UP as one piece and the plain sleeve above it
     compresses over SLEEVE_SPAN, so the cuff keeps its shape;
  3. a skin tube joins the inside of the sleeve opening to the inside of the glove, painted from the arm's own
     skin texels in the body atlas (one tone: jittered texels read as a patchwork);
  4. a flared leather gauntlet cuff, GAUNT long, rises from inside the glove over the skin, painted from the
     glove's own cuff texels.

  $B -b --factory-startup --python lengthen_forearms.py -- <production.glb> <landmarks.json> <out.glb> [delta_m]
"""
import bpy, bmesh, sys, json, colorsys, math, os
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]; src, lm_p, out = a[0], a[1], a[2]
DELTA = float(a[3]) if len(a) > 3 else 0.052
SLEEVE_UP, CUFF, SLEEVE_SPAN, TUBE_IN, GAUNT, GLOVE_IN = 0.035, 0.035, 0.10, 0.025, 0.04, 0.035
SKIN_R = (0.055, 0.024)              # fills the sleeve opening (an open gap showed the sleeve's inside), narrowing to
                                     # the reference's 6 cm wrist; capped at 85% of the opening
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
def pixels(mat):
    img = next(n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
    w, h = img.size; px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); return px.reshape(h, w, 4)
PX = {BODY: pixels(me.materials[BODY]), HAND: pixels(me.materials[HAND])}
def texel(k, uv):
    h, w = PX[k].shape[:2]; return PX[k][min(h - 1, max(0, int(uv[1] % 1 * h))), min(w - 1, max(0, int(uv[0] % 1 * w))), :3]
def is_skin(c):   # the display-space skin rule attach_face uses (hue 8-38, s > 0.3, v > 0.55)
    h, s, v = colorsys.rgb_to_hsv(*[float(x) for x in c]); return 8 <= h * 360 <= 38 and s > 0.3 and v > 0.55
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
uvb = bm.loops.layers.uv.active
geo, skin_uv, leather_uv = {}, [], {}
for s, sign in (("l", 1), ("r", -1)):
    E, W = np.array(J[f"lowerarm_{s}"]), np.array(J[f"hand_{s}"]); L = np.linalg.norm(W - E); u = (W - E) / L
    t = (P - E) @ u; r = np.linalg.norm((P - E) - np.outer(t, u), axis=1)
    arm = (np.sign(P[:, 0]) == sign) & (r < 0.10) & (t > -0.05) & (t < L + 0.25)
    hand = arm & (mi == HAND); body = arm & (mi == BODY) & (t > 0.0)
    # the rolled cuff flares past 10 cm from the axis in places; it lifts whole (r < 12 cm)
    cuffwide = (np.sign(P[:, 0]) == sign) & (r < 0.12) & (mi == BODY) & (t > 0.0) & (t < L + 0.05)
    th0, tb1 = t[hand].min(), t[body].max()
    geo[s] = dict(E=E, u=u, L=L, t=t, hand=hand, body=body, cuffwide=cuffwide, th0=th0, tb1=tb1,
                  g_c=P[hand & (t < th0 + 0.04)].mean(0))
    # the sleeve opening's centre and radius from its last 5 cm (a thinner slab caught one side of the tilted
    # cuff and put the forearm against the sleeve's edge), moved along the arm to the opening
    slab = body & (t > tb1 - 0.05) & (r < 0.08); sc_ = P[slab].mean(0); tm = float(t[slab].mean())
    d_ = P[slab] - sc_; rad = np.linalg.norm(d_ - np.outer(d_ @ u, u), axis=1)
    geo[s].update(s_c=sc_ + (tb1 - tm) * u, s_r=float(np.percentile(rad, 75)))
    leather_uv[s] = []
    for f in bm.faces:
        c = np.array(f.calc_center_median()[:])
        if np.sign(c[0]) != sign: continue
        tc = (c - E) @ u
        if f.material_index == BODY and abs(tc - tb1) < 0.03:
            skin_uv += [(lp[uvb].uv.x, lp[uvb].uv.y) for lp in f.loops if is_skin(texel(BODY, lp[uvb].uv))]
        elif f.material_index == HAND and tc < th0 + 0.015:
            leather_uv[s] += [(lp[uvb].uv.x, lp[uvb].uv.y) for lp in f.loops]
# one real texel each, the one whose colour is nearest the samples' median colour (the median of UV coordinates
# from different islands lands between them, on whatever is painted there)
def typical(k, uvs):
    if not uvs: return None
    C = np.array([texel(k, Vector(uv)) for uv in uvs]); m = np.median(C, 0)
    return np.array(uvs[int(np.argmin(np.linalg.norm(C - m, axis=1)))])
skin_uc = typical(BODY, skin_uv)
print("LEN skin texels", len(skin_uv), "at", None if skin_uc is None else skin_uc.round(4).tolist())
bm.verts.ensure_lookup_table()
report = {"delta_m": DELTA, "sleeve_up_m": SLEEVE_UP, "gauntlet_m": GAUNT, "sides": {}}
def tube(a0, a1, r0, r1, u, mat, uc, ease=1.0):
    # ease > 1 narrows fast after the first ring (a forearm out of a sleeve), 1 is a straight taper
    side_ax = np.cross(u, [0, 1, 0]); side_ax /= np.linalg.norm(side_ax); up_ax = np.cross(side_ax, u)
    rings = [[bm.verts.new(Vector(a0 + (a1 - a0) * (k / RINGS) + (r1 + (r0 - r1) * (1 - k / RINGS) ** ease)
                                  * (math.cos(2 * math.pi * j / SEGS) * side_ax + math.sin(2 * math.pi * j / SEGS) * up_ax)))
              for j in range(SEGS)] for k in range(RINGS + 1)]
    faces = []
    for k in range(RINGS):
        for j in range(SEGS):
            f = bm.faces.new([rings[k][j], rings[k][(j + 1) % SEGS], rings[k + 1][(j + 1) % SEGS], rings[k + 1][j]])
            f.material_index = mat; f.smooth = True; faces.append(f)
            if uc is not None:
                for lp in f.loops: lp[uvb].uv = Vector(uc)
    bm.normal_update()
    c0 = np.array(faces[0].calc_center_median()[:]); radial = (c0 - a0) - ((c0 - a0) @ u) * u
    if np.dot(np.array(faces[0].normal[:]), radial) < 0:
        for f in faces: f.normal_flip()
        bm.normal_update()
    return len(faces)
for s, g in geo.items():
    E, u, t, th0, tb1 = g["E"], g["u"], g["t"], g["th0"], g["tb1"]
    bm.verts.ensure_lookup_table()
    for i in np.nonzero(g["hand"])[0]: bm.verts[i].co += Vector(DELTA * u)
    for i in np.nonzero(g["cuffwide"] & (t > tb1 - CUFF - SLEEVE_SPAN))[0]:
        k = min(1.0, (t[i] - (tb1 - CUFF - SLEEVE_SPAN)) / SLEEVE_SPAN); bm.verts[i].co -= Vector(SLEEVE_UP * k * u)
    # centres: the sleeve opening and the glove opening (after the moves), the tube running between them
    s_end = g["s_c"] - SLEEVE_UP * u; g_end = g["g_c"] + DELTA * u
    ax = (g_end - s_end) / np.linalg.norm(g_end - s_end)
    s_r = g["s_r"]
    nf = tube(s_end - TUBE_IN * ax, g_end + GLOVE_IN * ax, min(SKIN_R[0], 0.9 * s_r), SKIN_R[1], ax, BODY, skin_uc, ease=2.0)
    luc = typical(HAND, leather_uv["r"] + leather_uv["l"])
    ng = tube(g_end + GLOVE_IN * ax, g_end - GAUNT * ax, GAUNT_R[0], GAUNT_R[1], ax, HAND, luc)
    report["sides"][s] = {"forearm_before_m": round(float(g["L"]), 4), "forearm_after_m": round(float(g["L"] + DELTA), 4),
                          "glove_started_inside_sleeve_m": round(float(tb1 - th0), 4),
                          "sleeve_to_glove_now_m": round(float(np.linalg.norm(g_end - s_end)), 4),
                          "bare_forearm_now_m": round(float(np.linalg.norm(g_end - s_end) - GAUNT), 4),
                          "sleeve_opening_r_m": round(s_r, 4), "skin_faces": nf, "gauntlet_faces": ng, "leather_texels": len(leather_uv[s])}
    print(f"LEN {s}:", report["sides"][s])
bm.to_mesh(me); bm.free()
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"derived_from": src, "forearms": report, "faces": len(me.polygons), "verts": len(me.vertices)})
json.dump(side, open(out + ".json", "w"), indent=2)
print("LENGTHEN_OK", len(me.polygons), "faces")
