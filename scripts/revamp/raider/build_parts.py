"""Split the dense acquired mesh by part label, close each part's openings, reduce each part to its own
triangle budget, save dense and reduced part files, render label and shape views."""
import bpy
import bmesh
import sys
import json
import math
import numpy as np
from mathutils import Vector, Euler
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
src, labp, names, out = a[0], a[1], json.load(open(a[2])), a[3]
BUDGET = {"hair": 8000, "face": 4000, "beard": 3000, "skin": 1500, "glove": 12000, "jacket": 26000, "trousers": 14000,
          "boot": 10000, "boot_strap": 3000, "plate": 5000, "strap": 5000, "belt": 2000, "buckle": 600, "pouch": 6000,
          "thigh_pouch": 2000, "kneepad": 2500}
PAL = {"hair": (70,35,15), "face": (240,180,140), "beard": (180,120,60), "skin": (215,140,100), "jacket": (25,120,150),
       "plate": (215,215,230), "pouch": (230,205,80), "buckle": (255,240,120), "belt": (200,100,40), "strap": (205,90,40),
       "kneepad": (240,115,180), "glove": (140,50,155), "boot": (140,75,25), "boot_strap": (190,120,60),
       "trousers": (85,85,100), "thigh_pouch": (250,170,60)}
# Layers: base cloth/skin parts continue under the overlays that sit on them; overlays become thin closed shells.
BASE = ("face", "skin", "glove", "jacket", "trousers", "boot")
SHELL = {"hair": 0.010, "beard": 0.004, "strap": 0.005, "plate": 0.006, "belt": 0.006, "buckle": 0.004, "pouch": 0.006,
         "thigh_pouch": 0.006, "kneepad": 0.006, "boot_strap": 0.005}
SKIRT = 0.006
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
me = ob.data
me.transform(ob.matrix_world)
V = np.array([v.co[:] for v in me.vertices])
F = np.array([p.vertices[:] for p in me.polygons], np.int64)
L = np.load(labp)
bpy.data.objects.remove(ob)
nF = len(F)
ID = {n: i for i, n in enumerate(names)}
E = np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1)
key = E[:, 0] * len(V) + E[:, 1]
fid = np.repeat(np.arange(nF), 3)
o = np.argsort(key, kind="stable")
ks, fs = key[o], fid[o]
same = ks[1:] == ks[:-1]
pa, pb = fs[:-1][same], fs[1:][same]
rows = np.concatenate([pa, pb])
cols = np.concatenate([pb, pa])
o = np.argsort(rows, kind="stable")
cols = cols[o]
indptr = np.concatenate([[0], np.cumsum(np.bincount(rows, minlength=nF))])
# which base part lies under each overlay face: nearest base face across the overlay, in hops
base_ids = [ID[n] for n in BASE]
under = np.where(np.isin(L, base_ids), L, -1)
from collections import deque
q = deque(np.nonzero(under >= 0)[0])
while q:
    f = q.popleft()
    for g in cols[indptr[f]:indptr[f + 1]]:
        if under[g] < 0:
            under[g] = under[f]
            q.append(g)
under[(L == ID["hair"]) | (L == ID["beard"])] = ID["face"]
under[(L == ID["kneepad"]) | (L == ID["thigh_pouch"])] = ID["trousers"]
print("UNDER unresolved", int((under < 0).sum()))

def mesh_from(fsel, name):
    sub = F[fsel]
    uniq, inv = np.unique(sub, return_inverse=True)
    m = bpy.data.meshes.new(name)
    m.from_pydata(V[uniq].tolist(), [], inv.reshape(-1, 3).tolist())
    m.update()
    return m, uniq, inv.reshape(-1, 3)

def relax(P, tris, movable, iters):
    """Harmonic relax of movable vertices with the rest fixed: the cloth runs on under an overlay."""
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    deg = np.bincount(e[:, 0], minlength=len(P)).astype(float)
    for _ in range(iters):
        acc = np.zeros_like(P)
        np.add.at(acc, e[:, 0], P[e[:, 1]])
        avg = acc / np.maximum(deg, 1)[:, None]
        P[movable] = avg[movable]
    return P

def reduce(obj, target):
    tris = len(obj.data.polygons)
    if tris > target:
        mod = obj.modifiers.new("reduce", 'DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = target / tris
        mod.use_collapse_triangulate = True
        bake_mods(obj)

def bake_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    mats = list(old.materials)
    obj.data = m
    m.materials.clear()
    [m.materials.append(x) for x in mats]
    m.name = old.name

sc = bpy.context.scene
dense_col = bpy.data.collections.new("dense")
low_col = bpy.data.collections.new("low")
sc.collection.children.link(dense_col)
sc.collection.children.link(low_col)
report = {}
for i, n in enumerate(names):
    own = L == i
    if not own.any():
        continue
    mat = bpy.data.materials.new("PART_" + n)
    c = PAL[n]
    mat.diffuse_color = (c[0]/255, c[1]/255, c[2]/255, 1)
    dm, _, _ = mesh_from(own, n + "_dense")
    dm.materials.append(mat)
    dense_col.objects.link(bpy.data.objects.new(n + "_dense", dm))
    if n in BASE:
        sel = own | ((under == i) & ~own)
        lm, uniq, tris = mesh_from(sel, n)
        owned_v = np.zeros(len(uniq), bool)
        owned_v[tris[own[sel]].ravel()] = True
        P = V[uniq].copy()
        P = relax(P, tris, ~owned_v, 80)
        lm.vertices.foreach_set("co", P.ravel())
        bm = bmesh.new()
        bm.from_mesh(lm)
        bnd = [e for e in bm.edges if e.is_boundary]
        nb = len(bnd)
        # a short skirt folded inward on every open edge hides cracks between neighbouring parts
        bm.normal_update()
        nrm = {v: v.normal.copy() for e in bnd for v in e.verts}
        ext = bmesh.ops.extrude_edge_only(bm, edges=bnd)
        for v in [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]:
            src_v = next((e.other_vert(v) for e in v.link_edges if e.other_vert(v) in nrm), None)
            if src_v is not None:
                v.co = src_v.co - nrm[src_v] * SKIRT
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(lm)
        bm.free()
        lm.materials.append(mat)
        lo = bpy.data.objects.new(n, lm)
        low_col.objects.link(lo)
        reduce(lo, BUDGET[n])
        kind = "base"
    else:
        lm, _, _ = mesh_from(own, n)
        lm.materials.append(mat)
        lo = bpy.data.objects.new(n, lm)
        low_col.objects.link(lo)
        reduce(lo, BUDGET[n] // 2)
        sol = lo.modifiers.new("shell", 'SOLIDIFY')
        sol.thickness = SHELL[n]
        sol.offset = 0.6
        sol.use_rim = True
        sol.use_even_offset = True
        sol.use_quality_normals = True
        sol.nonmanifold_thickness_mode = 'CONSTRAINTS'
        bake_mods(lo)
        kind = "shell"
        nb = 0
    for p in lo.data.polygons:
        p.use_smooth = True
    try:
        lo.modifiers.new("smooth", 'SMOOTH_BY_ANGLE')
    except Exception:
        pass
    report[n] = {"kind": kind, "dense_tris": int(own.sum()), "open_edges": nb, "reduced_tris": len(lo.data.polygons)}
    print("PART", n, json.dumps(report[n]))
json.dump(report, open(out + "/parts-report.json", "w"), indent=2)
sc.collection.children.unlink(dense_col)  # keep dense in the file but out of the scene renders
bpy.ops.wm.save_as_mainfile(filepath=out + "/raider-parts-v2.blend")
sc.collection.children.link(dense_col)
dense_col.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=out + "/raider-parts-v2.blend")
print("SAVED total reduced", sum(r["reduced_tris"] for r in report.values()))

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.3, 0.3, 0.32)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
H = V[:, 2].ptp() if hasattr(V[:, 2], 'ptp') else np.ptp(V[:, 2])
ctr = Vector(((V[:, 0].min() + V[:, 0].max()) / 2, (V[:, 1].min() + V[:, 1].max()) / 2, (V[:, 2].min() + V[:, 2].max()) / 2))
front = Vector((0, -1, 0))
def shoot(prefix, views, size, centre, res):
    sc.render.resolution_x, sc.render.resolution_y = res
    cam.data.ortho_scale = size
    for nm, ang in views:
        d = front.copy()
        d.rotate(Euler((0, 0, math.radians(ang))))
        cam.location = centre + d * 8
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = f"{out}/{prefix}-{nm}.png"
        bpy.ops.render.render(write_still=True)
four = (("front", 0), ("three-quarter", 45), ("side", 90), ("back", 180))
head = Vector((ctr.x, -0.03, 0.85))
for mode in ("labels", "shape"):
    if mode == "labels":
        sh.light = 'STUDIO'
        sh.color_type = 'MATERIAL'
        sh.show_cavity = True
        sh.show_object_outline = True
    else:
        sh.light = 'MATCAP'
        sh.color_type = 'SINGLE'
        sh.single_color = (0.8, 0.8, 0.8)
        sh.show_object_outline = False
    shoot(mode, four, H * 1.08, ctr, (700, 1000))
    shoot(mode + "-head", (("front", 0), ("side", 90), ("back", 180)), 0.42, head, (600, 600))
    shoot(mode + "-waist", (("back", 180),), 0.6, Vector((0, 0, 0.2)), (600, 600))
print("BUILD_DONE")
