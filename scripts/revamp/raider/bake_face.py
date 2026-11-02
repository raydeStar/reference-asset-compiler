"""Bake the painted head's colour onto the wrapped MakeHuman face (its own UVs): skin and eyeballs get their own
images; teeth and tongue a plain material. Cycles, selected-to-active, short rays: the wrapped skin lies within
about a millimetre of the painted surface.

  $B -b <face-wrap.blend> --python bake_face.py -- <out_dir> [skin_px] [eye_px]
"""
import bpy
import sys
import os
import numpy as np
import json
a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
SK = int(a[1]) if len(a) > 1 else 2048
EY = int(a[2]) if len(a) > 2 else 512
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
face = bpy.data.objects["face"]
scan = next(o for o in sc.objects if o.name.startswith("raider_head"))
me = face.data
gi = {g.name: g.index for g in face.vertex_groups}
def in_group(v, names):
    ids = {gi[n] for n in names if n in gi}
    return any(g.group in ids and g.weight > 0.5 for g in v.groups)
cls = ["eye" if in_group(v, ["helper-l-eye", "helper-r-eye"]) else "teeth" if in_group(v, ["helper-upper-teeth", "helper-lower-teeth"])
       else "tongue" if in_group(v, ["helper-tongue"]) else "skin" for v in me.vertices]
# The inside of the mouth took the lip paint. Skin that the wrap did not project onto the painted surface and
# that sits behind the lips, near the teeth, is the mouth cavity: it gets a dark material.
co_ = np.array([v.co[:] for v in me.vertices])
teeth_obj = bpy.data.objects.get("teeth")   # MakeHuman's CC0 teeth asset, when the wrap added it
TCO = np.array([v.co[:] for v in teeth_obj.data.vertices]) if teeth_obj else co_[[i for i, c in enumerate(cls) if c == "teeth"]]
tc = TCO.mean(0)
tw_ = float(np.ptp(TCO[:, 0]))
snapped = np.array([in_group(v, ["review_snapped"]) for v in me.vertices])
# ... and that lies inside the head, behind the painted surface: without that test, unprojected skin under the
# jaw was painted as mouth and showed as dark patches on the chin
from mathutils import Vector as _V
from mathutils.bvhtree import BVHTree as _BVH
import bmesh as _bm
_sb = _bm.new()
_sb.from_mesh(scan.data)
_sbvh = _BVH.FromBMesh(_sb)
for i, c in enumerate(cls):
    if c == "skin" and not snapped[i] and np.linalg.norm(co_[i] - tc) < 0.75 * tw_ and co_[i][1] > tc[1] - 0.25 * tw_:
        loc, nrm, _, dd = _sbvh.find_nearest(_V(co_[i]))
        if loc is not None and (_V(co_[i]) - loc).dot(nrm) < -0.003:
            cls[i] = "cavity"
def material(name, img=None, colour=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if img is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        nt.links.new(t.outputs[0], bsdf.inputs["Base Color"])
        nt.nodes.active = t
    if colour:
        bsdf.inputs["Base Color"].default_value = colour
    bsdf.inputs["Roughness"].default_value = 0.6
    if name == "FACE_mouth_cavity":   # matte and unlit-looking: the inside of a mouth is in shadow
        bsdf.inputs["Roughness"].default_value = 1.0
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.0
    return m
# His painted eyes rest with heavy upper lids over the top of the iris; MakeHuman's rest wider. A quarter of its
# own blink is folded into the rest shape (and every expression shape) before baking, so the lid paint lands
# where the lid now sits.
REST_LID = float(os.environ.get("RAC_FACE_REST_LID", "0.25"))
kbs = me.shape_keys.key_blocks
basis = kbs[0]
B0 = np.zeros(len(me.vertices) * 3)
basis.data.foreach_get("co", B0)
delta = np.zeros_like(B0)
for nm in ("eye-left-closure", "eye-right-closure"):
    K = np.zeros_like(B0)
    kbs[nm].data.foreach_get("co", K)
    delta += REST_LID * (K - B0)
for kb_ in kbs:
    K = np.zeros_like(B0)
    kb_.data.foreach_get("co", K)
    kb_.data.foreach_set("co", K + delta)
me.vertices.foreach_set("co", (B0 + delta))
me.update()
skin_img = bpy.data.images.new("face_skin", SK, SK)
eye_img = bpy.data.images.new("face_eyes", EY, EY)
me.materials.clear()
for m in (material("FACE_skin", skin_img), material("FACE_eyes", eye_img), material("FACE_mouth_cavity", colour=(0.025, 0.01, 0.01, 1)),
          material("FACE_teeth", colour=(0.36, 0.33, 0.28, 1)), material("FACE_tongue", colour=(0.32, 0.11, 0.11, 1))):
    me.materials.append(m)
idx = {"skin": 0, "eye": 1, "cavity": 2, "teeth": 3, "tongue": 4}
for p in me.polygons:
    cs = [cls[i] for i in p.vertices]
    p.material_index = next((idx[k] for k in ("eye", "teeth", "tongue") if k in cs), idx["cavity"] if cs.count("cavity") >= 2 else 0)
    p.use_smooth = True
# plain materials need an image node too or the bake errors; give them a throwaway one
tmp = bpy.data.images.new("tmp_mouth", 8, 8)
tmp_nodes = []
for m_ in me.materials[2:]:
    tn = m_.node_tree.nodes.new("ShaderNodeTexImage")
    tn.image = tmp
    m_.node_tree.nodes.active = tn
    tmp_nodes.append((m_, tn))
# Bake the paint itself: route the acquired head's base colour to emission and bake EMIT. A DIFFUSE colour
# bake multiplies by (1 - metallic), and the painter left the skin slightly metallic, so the face came out dark.
for m in scan.data.materials:
    nt = m.node_tree
    src_tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links)), None)
    em = nt.nodes.new("ShaderNodeEmission")
    outn = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    nt.links.new(src_tex.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], outn.inputs[0])
sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
sc.cycles.device = 'CPU'
bk = sc.render.bake
bk.use_selected_to_active = True
bk.cage_extrusion = 0.01
bk.max_ray_distance = 0.03
bk.use_pass_direct = False
bk.use_pass_indirect = False
bk.use_pass_color = True
bk.margin = 8
for o in sc.objects:
    o.select_set(o in (scan, face))
bpy.context.view_layer.objects.active = face
for o in sc.objects:
    if o.type == 'MESH':
        o.hide_render = False
print('BAKE_START', flush=True)
bpy.ops.object.bake(type='EMIT')
# The eyeballs sit deeper behind the lids than the skin does behind the paint: with short rays they found
# nothing and came out milky. Bake them again on their own with a longer reach, the skin image untouched.
for m in me.materials:
    m.node_tree.nodes.active = next(n for n in m.node_tree.nodes if n.type == 'TEX_IMAGE')
sk_nodes = [n for n in me.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE']
keep_sk = skin_img.pixels[:]
bk.cage_extrusion = 0.04
bk.max_ray_distance = 0.08
bpy.ops.object.bake(type='EMIT')
skin_img.pixels[:] = keep_sk
print('BAKE_DONE', flush=True)
skin_img.filepath_raw = os.path.join(out, "face_skin.png")
skin_img.file_format = 'PNG'
skin_img.save()
eye_img.filepath_raw = os.path.join(out, "face_eyes.png")
eye_img.file_format = 'PNG'
eye_img.save()
# for the neck repaint: each skin triangle's UVs and height (fix_neck_paint.py)
uvl_ = me.uv_layers.active.data
tri = []
for p in me.polygons:
    if p.material_index != 0:
        continue
    li = list(p.loop_indices)
    z = float(np.mean([me.vertices[me.loops[j].vertex_index].co.z for j in li]))
    for k in range(1, len(li) - 1):
        tri.append([*uvl_[li[0]].uv, *uvl_[li[k]].uv, *uvl_[li[k + 1]].uv, z])
scan_zmin = min(v.co.z for v in scan.data.vertices)
# the chin, from MediaPipe landmark 152 on the straight-on render (orthographic: image row gives height)
fd_ = os.path.dirname(os.path.abspath(out))
L_ = json.load(open(os.path.join(fd_, "scan-landmarks.json")))["mediapipe_478_xy"]
cam_ = json.load(open(os.path.join(fd_, "scan-front.json")))
chin_z = cam_["centre"][2] + (0.5 - L_[152][1] / cam_["resolution"]) * cam_["ortho_scale"]
np.save(os.path.join(out, "skin-tris.npy"), np.array(tri, np.float32))
open(os.path.join(out, "neck.json"), "w").write(json.dumps({"scan_min_z": scan_zmin, "chin_z": chin_z}))
skin_img.pack()
eye_img.pack()
for m_, tn in tmp_nodes:
    m_.node_tree.nodes.remove(tn)
bpy.data.images.remove(tmp)
# The acquired hair keeps its volume: faces of the painted head that are painted dark and sit above the brows
# become their own mesh over MakeHuman's smooth scalp (it rides the head bone). Its own paint is kept.
import bmesh
import numpy as np
import colorsys
tex = next(n for n in scan.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE').image
TW, TH = tex.size
PX = np.array(tex.pixels[:], np.float32).reshape(TH, TW, -1)
gi_l = {g.name: g.index for g in face.vertex_groups}
_eyes_obj = bpy.data.objects.get("eyes")   # the CC0 eye asset when present, else MakeHuman's helper eyes
brow_z = (max((_eyes_obj.matrix_world @ v.co).z for v in _eyes_obj.data.vertices) if _eyes_obj else
          max(v.co.z for v in face.data.vertices if any(g.group in (gi_l["helper-l-eye"], gi_l["helper-r-eye"]) for g in v.groups)))
hb = bmesh.new()
hb.from_mesh(scan.data)
uvl = hb.loops.layers.uv.active
drop = []
for f in hb.faces:
    c = f.calc_center_median()
    uv = sum((lp[uvl].uv for lp in f.loops), __import__("mathutils").Vector((0, 0))) / len(f.loops)
    r, g, b = PX[min(TH - 1, int(uv.y * TH)), min(TW - 1, int(uv.x * TW)), :3] ** (1 / 2.2)
    h_, s_, v_ = colorsys.rgb_to_hsv(float(r), float(g), float(b))
    if not (c.z > brow_z + 0.01 and v_ < 0.33):
        drop.append(f)
bmesh.ops.delete(hb, geom=drop, context='FACES')
# loose bits float around the head: keep only pieces of real size (welded across UV seams first)
bmesh.ops.remove_doubles(hb, verts=hb.verts[:], dist=1e-6)
hb.faces.ensure_lookup_table()
seen = set()
small = []
for f in hb.faces:
    if f.index in seen:
        continue
    stack = [f]
    seen.add(f.index)
    grp = []
    while stack:
        g = stack.pop()
        grp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index)
                    stack.append(h)
    if len(grp) < 60:
        small += grp
bmesh.ops.delete(hb, geom=small, context='FACES')
print("HAIR loose faces removed", len(small))
hm = bpy.data.meshes.new("hair")
hb.to_mesh(hm)
hb.free()
for m in scan.data.materials:
    hm.materials.append(m)
hair = bpy.data.objects.new("hair", hm)
sc.collection.objects.link(hair)
print("HAIR faces", len(hm.polygons))
# Eyes: baking the paint onto MakeHuman's eyeballs left them milky (its eye openings and the painted eyes do
# not line up exactly). Real eyeballs replace them: white spheres with an iris and pupil on the front, seated
# where MakeHuman's eyes sit behind the wrapped lids; the iris colour is sampled from the painted iris right in
# front of each eye.
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sbm2 = bmesh.new()
sbm2.from_mesh(scan.data)
sbv = BVHTree.FromBMesh(sbm2)
suv = sbm2.loops.layers.uv.active
co_f = np.array([v.co[:] for v in face.data.vertices])
HAVE_ASSET_EYES = bpy.data.objects.get("eyes") is not None
# MediaPipe's iris centres (468, 473) on the painted head say where each iris is painted
import json as _json
fdir = os.path.dirname(os.path.abspath(out))
L2 = np.array(_json.load(open(os.path.join(fdir, "scan-landmarks.json")))["mediapipe_478_xy"])
cam = _json.load(open(os.path.join(fdir, "scan-front.json")))
cc, cs, cr = Vector(cam["centre"]), cam["ortho_scale"], cam["resolution"]
def iris_hit(k):
    x, y = L2[k]
    o = Vector((cc.x + (x / cr - 0.5) * cs, -5.0, cc.z + (0.5 - y / cr) * cs))
    return sbv.ray_cast(o, Vector((0, 1, 0)))
eyes = {}
for side, gname, lm in (() if HAVE_ASSET_EYES else (("l", "helper-l-eye", 473), ("r", "helper-r-eye", 468))):
    idx = [v.index for v in face.data.vertices if any(g.group == gi_l[gname] and g.weight > 0.5 for g in v.groups)]
    P = co_f[idx]
    c = P.mean(0)
    r = float(np.linalg.norm(P - c, axis=1).mean())
    hit = iris_hit(lm)
    if hit[0] is None or (Vector(c) - hit[0]).length > 0.06:     # landmark side convention guard: use the nearer iris
        alt = iris_hit(468 if lm == 473 else 473)
        if alt[0] is not None and (alt[0] is not None and (hit[0] is None or (Vector(c) - alt[0]).length < (Vector(c) - hit[0]).length)):
            hit = alt
    sbm2.faces.ensure_lookup_table()
    f = sbm2.faces[hit[2]]
    uv = sum((lp[suv].uv for lp in f.loops), Vector((0, 0))) / len(f.loops)
    iris = tuple(float(x) for x in PX[min(TH - 1, int(uv.y * TH)), min(TW - 1, int(uv.x * TW)), :3])
    R = r * 0.85
    fwd = (Vector(hit[0]) - Vector(c)).normalized()
    centre = Vector(hit[0]) - fwd * (R + 0.003)       # the eye's front sits just behind the painted iris, in the lid's shadow
    eyes[side] = (np.array(centre[:]), R, idx, iris, fwd)
fb = bmesh.new()
fb.from_mesh(face.data)
fb.verts.ensure_lookup_table()
bmesh.ops.delete(fb, geom=[fb.verts[i] for e_ in eyes.values() for i in e_[2]], context='VERTS')
fb.to_mesh(face.data)
fb.free()
iris_avg = tuple(float(x) for x in np.mean([e_[3] for e_ in eyes.values()], axis=0)) if eyes else (0.4, 0.4, 0.4)
for side, (c, r, _, iris, fwd) in eyes.items():
    iris = iris_avg
    em_ = bpy.data.meshes.new(f"eye_{side}")
    b = bmesh.new()
    bmesh.ops.create_uvsphere(b, u_segments=48, v_segments=24, radius=r)
    mats = [bpy.data.materials.new(f"EYE_{side}_{k}") for k in ("sclera", "iris", "pupil", "limbus")]
    limbus = tuple(x * 0.45 for x in iris)
    for m_, col in zip(mats, ((0.6, 0.55, 0.5, 1), (*iris, 1), (0.02, 0.02, 0.02, 1), (*limbus, 1))):
        m_.use_nodes = True
        bs = m_.node_tree.nodes["Principled BSDF"]
        bs.inputs["Base Color"].default_value = col
        bs.inputs["Roughness"].default_value = 0.12
        em_.materials.append(m_)
    for f in b.faces:
        f.smooth = True
        d = f.calc_center_median().normalized()
        facing = d.dot(fwd)
        f.material_index = 2 if facing > 0.975 else 1 if facing > 0.9 else 3 if facing > 0.875 else 0
    b.to_mesh(em_)
    b.free()
    eo = bpy.data.objects.new(f"eye_{side}", em_)
    eo.location = Vector(c)
    sc.collection.objects.link(eo)
    print("EYE", side, "radius", round(r, 4), "iris", tuple(round(x, 3) for x in iris))
# The back of the mouth is open (MakeHuman's mouth bag does not survive the wrap whole), so an open mouth
# showed straight through. A dark backing sits behind the teeth.
tco = TCO
if len(tco):
    c_ = tco.mean(0)
    wdt = np.ptp(tco[:, 0])
    hgt = np.ptp(tco[:, 2]) * 1.6
    bk_ = bmesh.new()
    bmesh.ops.create_grid(bk_, x_segments=2, y_segments=2, size=0.5)
    for v in bk_.verts:
        v.co = Vector((c_[0] + v.co.x * wdt * 1.1, tco[:, 1].max() + 0.004, c_[2] + v.co.y * hgt))
    bmesh.ops.recalc_face_normals(bk_, faces=bk_.faces)
    mb_ = bpy.data.meshes.new("mouth_back")
    bk_.to_mesh(mb_)
    bk_.free()
    mb_.materials.append(me.materials[2])
    mob = bpy.data.objects.new("mouth_back", mb_)
    sc.collection.objects.link(mob)
    mob.vertex_groups.new(name="head")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "face-baked.blend"))
print("BAKE_OK", {k: cls.count(k) for k in ("skin", "eye", "cavity", "teeth", "tongue")})
