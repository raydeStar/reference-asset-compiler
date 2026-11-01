"""Project the reference part map onto the dense acquired mesh, grow labels along creases, split into part objects."""
import bpy, bmesh, sys, json, math, heapq
import numpy as np
sys.stdout.reconfigure(line_buffering=True)
from mathutils import Vector
from mathutils.bvhtree import BVHTree

a = sys.argv[sys.argv.index("--") + 1:]
src, ids_path, names_path, out = a[0], a[1], a[2], a[3]
ids = np.load(ids_path); names = json.load(open(names_path)); IH, IW = ids.shape
fg = ids != 255

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
bm = bmesh.new(); bm.from_mesh(ob.data); bm.transform(ob.matrix_world)
bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
V = np.array([v.co[:] for v in bm.verts]); nF = len(bm.faces)
print("DENSE", len(V), nF)

ys, xs = np.nonzero(fg); iy0, iy1, ix0, ix1 = ys.min(), ys.max(), xs.min(), xs.max()
bvh = BVHTree.FromBMesh(bm)

def project(front_sign):
    """front_sign=-1: camera on -Y looking +Y. Image x grows with Blender x (mirrored for +Y camera)."""
    xv = V[:, 0] * (-front_sign); zv = V[:, 2]
    s = (iy1 - iy0) / (zv.max() - zv.min())
    ox = ix0 + (ix1 - ix0) / 2 - s * (xv.min() + xv.max()) / 2
    oy = iy0 + s * zv.max()
    return s, ox, oy, xv

def silhouette_iou(front_sign):
    s, ox, oy, xv = project(front_sign)
    grid = np.zeros((IH, IW), bool)
    px = np.clip((xv * s + ox).astype(int), 0, IW - 1); py = np.clip((oy - V[:, 2] * s).astype(int), 0, IH - 1)
    grid[py, px] = True
    import scipy.ndimage as nd  # may be missing; fall back to dilation by shifts
    return grid

def raycast(front_sign, stride=1):
    s, ox, oy, xv = project(front_sign)
    votes = {}
    hits = 0; hitmask = np.zeros((IH, IW), bool)
    for py in range(iy0, iy1 + 1, stride):
        z = (oy - py) / s
        for px in range(ix0, ix1 + 1, stride):
            x = (px - ox) / s * (-front_sign)
            origin = Vector((x, front_sign * 10.0, z)); d = Vector((0, -front_sign, 0))
            loc, nrm, fi, dist = bvh.ray_cast(origin, d)
            if fi is None: continue
            hitmask[py, px] = True
            if not fg[py, px]: continue
            hits += 1
            votes.setdefault(fi, []).append(int(ids[py, px]))
    inter = (hitmask & fg).sum(); union = (hitmask | fg).sum()
    return votes, inter / union

# front is where the boot toes point: the lowest band reaches further forward than the ankles
zmin_, H_ = V[:, 2].min(), V[:, 2].max() - V[:, 2].min()
sole = V[V[:, 2] < zmin_ + 0.03 * H_]; ankle = V[(V[:, 2] > zmin_ + 0.08 * H_) & (V[:, 2] < zmin_ + 0.12 * H_)]
toe_shift = (sole[:, 1].min() + sole[:, 1].max()) / 2 - (ankle[:, 1].min() + ankle[:, 1].max()) / 2
sign = -1 if toe_shift < 0 else 1
print("ORIENT toe_shift", round(float(toe_shift), 4), "front_sign", sign)
votes, iou = raycast(sign, stride=1)
print("PROJECTED faces", len(votes), "IoU", round(float(iou), 3))

# rolled sleeves are jacket cloth; keep them one part so they cannot race around the arms
if "sleeve_roll" in names:
    sr, jk = names.index("sleeve_roll"), names.index("jacket")
    for fi in votes: votes[fi] = [jk if v == sr else v for v in votes[fi]]
# edge-on faces pick up neighbouring pixels; only faces turned toward the camera take the picture's label
toward = Vector((0, sign, 0))
votes = {fi: vs for fi, vs in votes.items() if bm.faces[fi].normal.dot(toward) > 0.35}
label = np.full(nF, -1, np.int32)
for fi, vs in votes.items():
    label[fi] = np.bincount(vs).argmax()

# crease-aware multi-source growth over face adjacency
fn = [f.normal.copy() for f in bm.faces]; fc = [f.calc_center_median() for f in bm.faces]
dist = np.full(nF, np.inf); heap = []
for fi in np.nonzero(label >= 0)[0]:
    dist[fi] = 0; heap.append((0.0, int(fi)))
heapq.heapify(heap)
while heap:
    d, f = heapq.heappop(heap)
    if d > dist[f]: continue
    for e in bm.faces[f].edges:
        for g in e.link_faces:
            gi = g.index
            if gi == f: continue
            # concave crease: neighbours' normals turn toward each other
            cosang = max(-1.0, min(1.0, fn[f].dot(fn[gi])))
            ang = math.acos(cosang)
            concave = (fc[gi] - fc[f]).dot(fn[f]) > 0
            step = (fc[gi] - fc[f]).length * (1.0 + (25.0 * ang if concave else 2.0 * ang))
            nd_ = d + step
            if nd_ < dist[gi]:
                dist[gi] = nd_; label[gi] = label[f]; heapq.heappush(heap, (nd_, gi))
print("UNLABELLED_AFTER_GROW", int((label < 0).sum()))

# faces the growth never reached (disconnected shells) take the nearest labelled face's part
from mathutils.kdtree import KDTree
lab_idx = np.nonzero(label >= 0)[0]
kd = KDTree(len(lab_idx))
for k, fi in enumerate(lab_idx): kd.insert(fc[fi], k)
kd.balance()
for fi in np.nonzero(label < 0)[0]:
    _, k, _ = kd.find(fc[fi]); label[fi] = label[lab_idx[k]]

# hidden faces: equipment may only reach a short way round; otherwise the body/cloth part
# seen at the same screen position on the front (equipment removed) is the prior
body = np.load(a[4]); s_, ox_, oy_, _ = project(sign)
reach = {"strap": 0.25, "belt": 0.6, "boot_strap": 0.12, "plate": 0.05, "pouch": 0.6, "buckle": 0.02,
         "kneepad": 0.05, "thigh_pouch": 0.06}
equip_ids = {names.index(n): r for n, r in reach.items() if n in names}
face_ids = {names.index(n) for n in ("face", "beard") if n in names}; hair_id = names.index("hair")
front = Vector((0, sign, 0)); projected = set(votes)
changed = 0
for fi in range(nF):
    if fi in projected: continue
    l = int(label[fi])
    if l in equip_ids and dist[fi] <= equip_ids[l]: continue
    c = fc[fi]; xv = c.x * (-sign)
    px = int(round(xv * s_ + ox_)); py = int(round(oy_ - c.z * s_))
    if 0 <= py < IH and 0 <= px < IW and body[py, px] != 255:
        nl = int(body[py, px])
        if nl in face_ids and (fn[fi].dot(front) < -0.15 or fn[fi].z > 0.55):
            nl = hair_id
        if nl != l: label[fi] = nl; changed += 1
print("PRIOR_RELABELLED", changed)

# above the chin nothing is cloth: hidden head faces are hair when they face back or up, else skin
fr = ids == names.index("beard"); chin_row = np.nonzero(fr.any(1))[0].max()
chin_z = (oy_ - chin_row) / s_
jk = names.index("jacket"); head_fixed = 0
skin_face = names.index("face")
for fi in range(nF):
    if fi in projected or fc[fi].z < chin_z + 0.01: continue
    # the jacket collar stands up behind the neck: keep cloth there
    if label[fi] == jk and fc[fi].z < chin_z + 0.05 and fn[fi].dot(front) < 0.2: continue
    if label[fi] not in face_ids and label[fi] != hair_id:
        label[fi] = hair_id if (fn[fi].dot(front) < -0.1 or fn[fi].z > 0.5) else skin_face; head_fixed += 1
print("HEAD_FIXED", head_fixed, "chin_z", round(float(chin_z), 3))

# small-island cleanup: repeated majority vote on faces whose neighbours mostly disagree
for _ in range(4):
    new = label.copy()
    for face in bm.faces:
        nb = []
        for edge in face.edges:
            for other in edge.link_faces:
                if other.index != face.index: nb.append(other.index)
        if not nb: continue
        vals, cnt = np.unique(label[nb], return_counts=True)
        if cnt.max() >= 3 and vals[cnt.argmax()] != label[face.index]: new[face.index] = vals[cnt.argmax()]
    label = new

counts = {names[i]: int((label == i).sum()) for i in range(len(names))}
print("FACE_COUNTS", json.dumps(counts))
np.save(out + "/face-labels.npy", label)
json.dump({"front_sign": int(sign), "silhouette_iou": float(iou), "projected_faces": len(votes), "counts": counts, "names": names},
          open(out + "/projection.json", "w"), indent=2)

# split into one object per part, coloured
pal = {"hair": (70,35,15), "face": (240,180,140), "beard": (120,70,40), "skin": (215,140,100), "sleeve_roll": (40,150,170),
       "jacket": (25,120,150), "plate": (215,215,230), "pouch": (230,205,80), "buckle": (255,240,120), "belt": (200,100,40),
       "strap": (205,90,40), "kneepad": (240,115,180), "glove": (140,50,155), "boot": (140,75,25), "boot_strap": (190,120,60),
       "trousers": (85,85,100), "thigh_pouch": (250,170,60)}
F = np.array([[v.index for v in f.verts] for f in bm.faces], np.int64)
bpy.data.objects.remove(ob)
for i, n in enumerate(names):
    sub = F[label == i]
    if not len(sub): continue
    uniq, inv = np.unique(sub, return_inverse=True)
    pm = bpy.data.meshes.new(n); pm.from_pydata(V[uniq].tolist(), [], inv.reshape(-1, 3).tolist()); pm.update()
    m = bpy.data.materials.new("PART_" + n); c = pal[n]; m.diffuse_color = (c[0]/255, c[1]/255, c[2]/255, 1); pm.materials.append(m)
    po = bpy.data.objects.new(n, pm); bpy.context.scene.collection.objects.link(po)
bpy.ops.wm.save_as_mainfile(filepath=out + "/raider-parts-dense.blend")
print("SAVED_PARTS", len([o for o in bpy.context.scene.objects if o.type == 'MESH']))

# four-view render, flat part colours
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_cavity = True; sc.display.shading.show_object_outline = True
sc.render.resolution_x, sc.render.resolution_y = 700, 1000
sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.3, 0.3, 0.32)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; H = V[:, 2].max() - V[:, 2].min(); cam.data.ortho_scale = H * 1.08
ctr = Vector(((V[:, 0].min() + V[:, 0].max()) / 2, (V[:, 1].min() + V[:, 1].max()) / 2, (V[:, 2].min() + V[:, 2].max()) / 2))
front = Vector((0, sign, 0))
from mathutils import Euler
for nm, ang in (("front", 0), ("three-quarter", 45), ("side", 90), ("back", 180)):
    d = front.copy(); d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = ctr + d * 8; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f"{out}/parts-{nm}.png"; bpy.ops.render.render(write_still=True)
print("PROJECT_DONE")
# head close-ups
hz = V[:, 2].max() - 0.07 * H
cam.data.ortho_scale = H * 0.2
for nm, ang in (("head-front", 0), ("head-side", 90), ("head-back", 180)):
    d = front.copy(); d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = Vector((ctr.x, ctr.y, hz)) + d * 8; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.resolution_x, sc.render.resolution_y = 600, 600
    sc.render.filepath = f"{out}/parts-{nm}.png"; bpy.ops.render.render(write_still=True)
print("HEAD_DONE")
