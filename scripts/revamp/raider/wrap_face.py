"""Wrap MakeHuman's head (eyelids, eyeballs, split mouth, teeth, tongue, 34 expression shapes) onto the painted
head-only acquisition, so the face can blink and speak while keeping the acquired shape.

1. 478 MediaPipe landmarks found on straight-on renders of both faces (face_front.py, face_landmarks.py)
   are traced back onto each surface.
2. A similarity transform, then a thin-plate warp through every landmark pair, moves MakeHuman onto the
   painted head: eye contours on eye contours, lips on lips, jaw on jaw.
3. The skin is snapped onto the painted surface, except the eye openings and the inner lips, which must
   stay open to blink and talk. Every expression shape moves with the skin.
4. MakeHuman is cut below the painted neck; its helper eyes become real eyeballs seated behind the lids.

  $B -b <mh-front.blend> --python wrap_face.py -- <assembled.glb> <face_dir> <out.blend>
(face_dir holds scan-/mh- landmarks .json and the -front.json cameras; needs MPFB)
"""
import bpy
import bmesh
import sys
import os
import json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
asm_p, fdir, out_p = a
from bl_ext.user_default.mpfb.services.targetservice import TargetService
MPFB = os.path.dirname(sys.modules["bl_ext.user_default.mpfb"].__file__)
sc = bpy.context.scene
mh = next(o for o in sc.objects if o.type == 'MESH' and o.name.startswith("Human"))
for m in list(mh.modifiers):
    mh.modifiers.remove(m)
units = os.path.join(MPFB, "data", "targets", "expression", "units", "caucasian")
for fn in sorted(os.listdir(units)):
    TargetService.load_target(mh, os.path.join(units, fn), weight=0.0, name=fn.replace(".target.gz", ""))
me = mh.data
keys = me.shape_keys.key_blocks
bpy.ops.import_scene.gltf(filepath=asm_p)
scan = next(o for o in sc.objects if o.type == 'MESH' and o.name.startswith("raider_head"))
for o in list(sc.objects):
    if o.type == 'MESH' and o not in (mh, scan):
        bpy.data.objects.remove(o)
scan.data.transform(scan.matrix_world)
scan.matrix_world = Matrix.Identity(4)
SV = np.array([v.co[:] for v in scan.data.vertices])
sbm = bmesh.new()
sbm.from_mesh(scan.data)
sbvh = BVHTree.FromBMesh(sbm)   # exact surface, for landmarks
# The skin snaps onto a lightly smoothed copy: the acquired beard and moustache are hard steps and the lips a
# slit, and snapping onto them folded the skin into flaps around the mouth. The baked paint carries that detail.
smb = bmesh.new()
smb.from_mesh(scan.data)
bmesh.ops.remove_doubles(smb, verts=smb.verts[:], dist=1e-6)
for _ in range(int(os.environ.get("RAC_WRAP_SMOOTH", "12"))):
    bmesh.ops.smooth_vert(smb, verts=smb.verts[:], factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
snap_bvh = BVHTree.FromBMesh(smb)

gi = {g.name: g.index for g in mh.vertex_groups}
def members(name, w=0.5):
    idx = gi[name]
    return np.array([v.index for v in me.vertices if any(g.group == idx and g.weight > w for g in v.groups)], int)
body = members("body")
eyes_l, eyes_r = members("helper-l-eye"), members("helper-r-eye")
teeth = np.concatenate([members("helper-upper-teeth"), members("helper-lower-teeth")])
tongue = members("helper-tongue")
MV = np.array([v.co[:] for v in me.vertices])
keep_for_rays = np.zeros(len(MV), bool)
keep_for_rays[body] = True
keep_for_rays[eyes_l] = True
keep_for_rays[eyes_r] = True
tris = []
for p in me.polygons:
    vs = list(p.vertices)
    if all(keep_for_rays[i] for i in vs):
        tris += [[vs[0], vs[k], vs[k + 1]] for k in range(1, len(vs) - 1)]
mbvh = BVHTree.FromPolygons([Vector(v) for v in MV], tris)

def trace(lm_file, cam_file, bvh):
    L = np.array(json.load(open(lm_file))["mediapipe_478_xy"])
    cam = json.load(open(cam_file))
    c, s, R = Vector(cam["centre"]), cam["ortho_scale"], cam["resolution"]
    pts = []
    for x, y in L:
        o = Vector((c.x + (x / R - 0.5) * s, -5.0, c.z + (0.5 - y / R) * s))
        hit = bvh.ray_cast(o, Vector((0, 1, 0)))
        pts.append(hit[0][:] if hit[0] is not None else (np.nan,) * 3)
    return np.array(pts)
S = trace(f"{fdir}/scan-landmarks.json", f"{fdir}/scan-front.json", sbvh)
M = trace(f"{fdir}/mh-landmarks.json", f"{fdir}/mh-front.json", mbvh)
# Inner-lip landmarks are dropped: on MakeHuman they land inside its mouth, on the painted head on the
# surface of closed lips, and forcing those pairs together folded the skin into flaps at the mouth corners.
INNER_LIPS = {78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 191, 80, 81, 82, 13, 312, 311, 310, 415}
ok = ~np.isnan(S).any(1) & ~np.isnan(M).any(1) & np.array([i not in INNER_LIPS for i in range(len(S))])
S, M = S[ok], M[ok]
print("LANDMARKS paired", int(ok.sum()), "of 478")

# similarity (Umeyama) MakeHuman -> scan
mu_m, mu_s = M.mean(0), S.mean(0)
Mc, Sc = M - mu_m, S - mu_s
U, Dg, Vt = np.linalg.svd(Sc.T @ Mc / len(M))
Dm = np.eye(3)
Dm[2, 2] = np.sign(np.linalg.det(U @ Vt))
Rm = U @ Dm @ Vt
scale = float(np.trace(np.diag(Dg) @ Dm) / (Mc ** 2).sum(1).mean())
t = mu_s - scale * Rm @ mu_m
T = Matrix.Identity(4)
for i in range(3):
    for j in range(3):
        T[i][j] = scale * Rm[i, j]
    T[i][3] = t[i]
me.transform(T, shape_keys=True)
me.update()
M = (scale * (Rm @ M.T)).T + t
print("SIMILARITY scale", round(scale, 4), "landmark rms after", round(float(np.sqrt(((M - S) ** 2).sum(1).mean())), 4))

# thin-plate warp through every landmark pair, applied to every vertex and every expression shape
def tps(src, dst, lam=float(os.environ.get("RAC_WRAP_TPS_LAMBDA", "1e-6"))):
    n = len(src)
    K = np.linalg.norm(src[:, None] - src[None], axis=2)
    P = np.c_[np.ones(n), src]
    A = np.zeros((n + 4, n + 4))
    A[:n, :n] = K + lam * np.eye(n)
    A[:n, n:] = P
    A[n:, :n] = P.T
    # lam > 0 lets the warp bend smoothly instead of passing exactly through every pair (no fold-overs)
    b = np.zeros((n + 4, 3))
    b[:n] = dst - src
    coef = np.linalg.solve(A, b)
    def f(x):
        return np.linalg.norm(x[:, None] - src[None], axis=2) @ coef[:n] + np.c_[np.ones(len(x)), x] @ coef[n:]
    return f
warp = tps(M, S)
MV = np.array([v.co[:] for v in me.vertices])
disp = warp(MV)
# The warp is only trusted near the landmarks: with every landmark on the front of the face, its linear part
# extrapolated behind the ears and flattened the back of the head. Away from the face the snap below shapes
# the head instead.
neck_z = float(S[:, 2].min() - 0.06)
kdl = KDTree(len(M))
for k_, p_ in enumerate(M):
    kdl.insert(Vector(p_), k_)
kdl.balance()
dl = np.array([kdl.find(Vector(p_))[2] for p_ in MV])
fade = (np.exp(-(dl / 0.04) ** 2) * np.clip((MV[:, 2] - (neck_z - 0.10)) / 0.10, 0, 1))[:, None]
disp *= fade
for kb in keys:
    co = np.zeros(len(MV) * 3)
    kb.data.foreach_get("co", co)
    kb.data.foreach_set("co", (co.reshape(-1, 3) + disp).ravel())
me.vertices.foreach_set("co", (MV + disp).ravel())
me.update()
MV = MV + disp
Mw = M + warp(M)
print("WARP landmark rms", round(float(np.sqrt(((Mw - S) ** 2).sum(1).mean())), 5))

# Snap the skin onto the painted surface. A vertex is pulled only where its surface faces the same way as the
# painted surface under it: outer lips and skin snap, while the inner lips and eyelid rims, which curl inward,
# stay open. (Shielding the whole lip region left a plate standing over the mouth.) Two passes, smoothed.
eye_c = [MV[eyes_l].mean(0), MV[eyes_r].mean(0)]
eye_r = float(np.linalg.norm(MV[eyes_l] - eye_c[0], axis=1).mean())
lipw = np.zeros(len(MV))
lidx = gi.get("lips")
for v in me.vertices:
    for g in v.groups:
        if g.group == lidx:
            lipw[v.index] = g.weight
def ramp(d, a0, a1):
    return np.clip((d - a0) / (a1 - a0), 0, 1)
is_body = np.zeros(len(MV), bool)
is_body[body] = True
ptris = np.array([[p.vertices[0], p.vertices[k], p.vertices[k + 1]] for p in me.polygons for k in range(1, len(p.vertices) - 1)])
e = np.concatenate([ptris[:, [0, 1]], ptris[:, [1, 2]], ptris[:, [2, 0]]])
e = np.concatenate([e, e[:, ::-1]])
deg = np.bincount(e[:, 0], minlength=len(MV)).astype(float)
off = np.zeros_like(MV)
pulled_any = None
for it in range(0 if os.environ.get("RAC_WRAP_NOSNAP") else 2):
    me.update()
    NV = np.array([v.normal[:] for v in me.vertices])
    d_eye = np.min([np.linalg.norm(MV - c, axis=1) for c in eye_c], axis=0)
    w = ramp(d_eye, eye_r * 1.2, eye_r * 1.7)
    region = is_body & (MV[:, 2] > neck_z)
    step = np.zeros_like(MV)
    for i in np.nonzero(region & (w > 0))[0]:
        # project along the vertex's own normal (both ways): nearest-point snapping sent neighbours to
        # different sides of the beard and moustache steps and folded the skin around the mouth
        # from the vertex itself, outward and inward, taking the closer surface: starting the ray behind the
        # vertex let it stop on hidden inner surfaces of the acquired head, which folded the skin
        nv = Vector(NV[i])
        o = Vector(MV[i])
        hits = [h for h in (snap_bvh.ray_cast(o, nv, 0.04), snap_bvh.ray_cast(o, -nv, 0.04)) if h[0] is not None]
        if not hits:
            continue
        loc, nrm, _, dd = min(hits, key=lambda h: h[3])
        if nv.dot(nrm) < 0.3:
            continue
        step[i] = (np.array(loc) - MV[i]) * w[i]
    pulled = np.abs(step).sum(1) > 0
    pulled_any = pulled if it == 0 else (pulled_any | pulled)
    for _ in range(2):
        acc = np.zeros_like(step)
        np.add.at(acc, e[:, 0], step[e[:, 1]])
        step = 0.5 * step + 0.5 * acc / np.maximum(deg, 1)[:, None]
    step[~is_body] = 0
    MV = MV + step
    off += step
    me.vertices.foreach_set("co", MV.ravel())
if os.environ.get("RAC_WRAP_NOSNAP"):
    pulled_any = np.zeros(len(MV), bool)
    pulled_any[body[:1]] = True
pulled_final = pulled_any.copy()
# Everything inside the face that was not snapped (the mouth cavity, inner lips, eyelid rims) moves with the
# nearest snapped skin in space, weighted by distance, the way the teeth and eyes do. Two graph-based fills were
# tried and rejected: one peeled the lower face away, one tore the area around the mouth open.
base = MV - off
src_i = np.nonzero(pulled_any)[0]
kdp = KDTree(len(src_i))
for k_, i in enumerate(src_i):
    kdp.insert(Vector(base[i]), k_)
kdp.balance()
inner = is_body & ~pulled_any & (base[:, 2] > neck_z - 0.05)
for i in np.nonzero(inner)[0]:
    near = kdp.find_n(Vector(base[i]), 8)
    ww = np.array([1 / (d + 1e-4) ** 2 for _, _, d in near])
    off[i] = (off[src_i[[k for _, k, _ in near]]] * ww[:, None]).sum(0) / ww.sum()
MV = base + off
me.vertices.foreach_set("co", MV.ravel())
off_body = off.copy()
# helpers (eyes, teeth, tongue) ride with the nearest skin
kd = KDTree(len(body))
for k_, i in enumerate(body):
    kd.insert(MV[i] - off_body[i], k_)
kd.balance()
for i in np.nonzero(~is_body)[0]:
    near = kd.find_n(Vector(MV[i] - off_body[i]), 8)
    ww = np.array([1 / (d + 1e-4) for _, _, d in near])
    off[i] = (off[body[[k for _, k, _ in near]]] * ww[:, None]).sum(0) / ww.sum()
# Teeth and tongue move as one solid piece by the lips' average offset: following the nearest lip skin
# dragged the tongue forward with lips pulled onto his fuller painted lips, and it filled the open mouth.
lip_v = np.nonzero(lipw > 0.5)[0]
if len(lip_v):
    mouth_shift = off[lip_v].mean(0)
    for arr in (teeth, tongue):
        off[arr] = mouth_shift
MV = MV - off_body + off           # helpers get their share; body already moved
# MakeHuman's teeth arch came out wider than his mouth (7.9 cm against 6.8 cm lips) and poked through the
# corners: teeth and tongue are scaled to 75% of the lip width (at 85% their corners still showed as white wedges) about their centre and seated just behind the lips
mouth_parts = np.concatenate([teeth, tongue])
if len(lip_v):
    lw, tw2 = np.ptp(MV[lip_v][:, 0]), np.ptp(MV[teeth][:, 0])
    k_ = min(1.0, 0.75 * lw / tw2)
    mc = MV[mouth_parts].mean(0)
    fix = (mc + (MV[mouth_parts] - mc) * k_) - MV[mouth_parts]
    front_gap = (MV[lip_v][:, 1].min() + 0.004) - (MV[mouth_parts] + fix)[:, 1].min()
    fix[:, 1] += max(0.0, front_gap)
    off[mouth_parts] += fix
    MV[mouth_parts] += fix
    # MakeHuman's tongue sat high under the upper lip and stayed put when the jaw dropped, filling the open
    # mouth: seat it low behind the lower teeth
    lower_t = members("helper-lower-teeth")
    th_ = np.ptp(MV[teeth][:, 2])
    tongue_fix = np.array([0.0, 0.006, -0.45 * th_])
    off[tongue] += tongue_fix
    MV[tongue] += tongue_fix
    print("MOUTH teeth scaled", round(float(k_), 3), "to fit lips", round(float(lw), 4))
B0_ = np.zeros(len(MV) * 3)
keys[0].data.foreach_get("co", B0_)
B0_ = B0_.reshape(-1, 3)
lower_t = members("helper-lower-teeth")
for kb in keys:
    co = np.zeros(len(MV) * 3)
    kb.data.foreach_get("co", co)
    co = co.reshape(-1, 3)
    # every shape moves the tongue with the lower teeth (MakeHuman's shapes leave the tongue behind)
    if kb is not keys[0] and len(lower_t) and len(tongue):
        co[tongue] = B0_[tongue] + (co[lower_t] - B0_[lower_t]).mean(0)
    kb.data.foreach_set("co", (co + off).ravel())
me.vertices.foreach_set("co", MV.ravel())
me.update()
res = [sbvh.find_nearest(Vector(MV[i]))[3] for i in np.nonzero(is_body & (MV[:, 2] > neck_z) & pulled_final)[0]] or [0.0]
print("SNAP residual mean", round(float(np.mean(res)), 5), "p95", round(float(np.percentile(res, 95)), 5))

# MakeHuman's own CC0 system assets replace the helper eyes, teeth and tongue. MPFB fits each
# asset to the face's (already wrapped) helper geometry; each expression shape is refitted and stored on the asset
# as a matching shape, so the mouth parts and lashes move with speech and blinks. Painted brows stay painted.
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.clothesservice import ClothesService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
from bl_ext.user_default.mpfb.entities.clothes.mhclo import Mhclo
UD = LocationService.get_user_data()
ASSETS = {"eyes": ("eyes/high-poly/high-poly.mhclo", "Eyes"), "teeth": ("teeth/teeth_base/teeth_base.mhclo", "Teeth"),
          "tongue": ("tongue/tongue01/tongue01.mhclo", "Tongue")}   # eyelashes dropped: Mark found the cards weird
assets = {}
for k in keys[1:]:
    k.value = 0.0
for name, (rel, atype) in ASSETS.items():
    path = os.path.join(UD, rel)
    if not os.path.exists(path):
        print("ASSET missing", path)
        continue
    obj = HumanService.add_mhclo_asset(path, mh, asset_type=atype, subdiv_levels=0, material_type="MAKESKIN", set_up_rigging=False,
                                       interpolate_weights=False, import_subrig=False, import_weights=False)
    for m_ in list(obj.modifiers):
        obj.modifiers.remove(m_)
    mc = Mhclo()
    mc.load(path)
    mc.clothes = obj
    ClothesService.fit_clothes_to_human(obj, mh, mc, set_parent=False)
    base_co = np.zeros(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", base_co)
    per_key = {}
    for kb_ in keys[1:]:
        for k in keys[1:]:
            k.value = 0.0
        kb_.value = 1.0
        ClothesService.fit_clothes_to_human(obj, mh, mc, set_parent=False)
        c_ = np.zeros_like(base_co)
        obj.data.vertices.foreach_get("co", c_)
        if np.abs(c_ - base_co).max() > 1e-6:
            per_key[kb_.name] = c_
    for k in keys[1:]:
        k.value = 0.0
    obj.data.vertices.foreach_set("co", base_co)
    obj.data.update()
    if per_key:
        obj.shape_key_add(name="Basis", from_mix=False)
        for kn, c_ in per_key.items():
            sk = obj.shape_key_add(name=kn, from_mix=False)
            sk.data.foreach_set("co", c_)
    obj.parent = None
    obj.name = name
    obj.data.name = name
    assets[name] = obj
    print("ASSET", name, "verts", len(obj.data.vertices), "shapes", len(per_key))
# eyes: the pack's grey iris, the nearest to his painted grey-blue. Only the texture is swapped: MakeHuman's eye
# material uses the texture's alpha for the clear cornea (an opaque replacement turned the eyes black).
if "eyes" in assets:
    eimg = bpy.data.images.load(os.path.join(UD, "eyes", "materials", "grey_eye.png"))
    for m_ in assets["eyes"].data.materials:
        for n_ in (m_.node_tree.nodes if m_ else []):
            if n_.type == 'TEX_IMAGE':
                n_.image = eimg

# which vertices the last snap pass pulled, kept as a vertex group for review
mh.vertex_groups.new(name="review_snapped").add([int(i) for i in np.nonzero(pulled_final)[0]], 1.0, 'REPLACE')
# cut below the painted neck, keep eyes, teeth, tongue
# the neck reaches well down into the collar: removing the old head also took the neck skin showing in the
# open V at the front and at the nape, and a face cut at the jaw left holes there
NECK_DROP = float(os.environ.get("RAC_FACE_NECK_DROP", "0.12"))
keep = np.zeros(len(MV), bool)
keep[body[MV[body, 2] > neck_z - NECK_DROP]] = True
# helper eyes, teeth and tongue are replaced by the CC0 assets above
for arr in (() if assets else (eyes_l, eyes_r, teeth, tongue)):
    keep[arr] = True
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(~keep)[0]], context='VERTS')
bm.to_mesh(me)
bm.free()
mh.name = "face"
me.name = "face"
json.dump({"landmarks_paired": int(ok.sum()), "similarity_scale": scale, "neck_z": neck_z, "eye_radius": eye_r,
           "snap_residual_mean": float(np.mean(res)), "snap_residual_p95": float(np.percentile(res, 95))},
          open(out_p[:-6] + ".json", "w"), indent=2)
bpy.ops.wm.save_as_mainfile(filepath=out_p)
print("WRAP_OK", len(me.vertices))
