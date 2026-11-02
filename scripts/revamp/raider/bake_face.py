"""Bake the painted head's colour onto the wrapped MakeHuman face (its own UVs): skin and eyeballs get their own
images; teeth and tongue a plain material. Cycles, selected-to-active, short rays: the wrapped skin lies within
about a millimetre of the painted surface.

  $B -b <face-wrap.blend> --python bake_face.py -- <out_dir> [skin_px] [eye_px]
"""
import bpy, sys, os
import numpy as np
a = sys.argv[sys.argv.index("--") + 1:]; out = a[0]; SK = int(a[1]) if len(a) > 1 else 2048; EY = int(a[2]) if len(a) > 2 else 512
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
face = bpy.data.objects["face"]; scan = next(o for o in sc.objects if o.name.startswith("raider_head"))
me = face.data; gi = {g.name: g.index for g in face.vertex_groups}
def in_group(v, names):
    ids = {gi[n] for n in names if n in gi}; return any(g.group in ids and g.weight > 0.5 for g in v.groups)
cls = ["eye" if in_group(v, ["helper-l-eye", "helper-r-eye"]) else "mouth" if in_group(v, ["helper-upper-teeth", "helper-lower-teeth", "helper-tongue"]) else "skin" for v in me.vertices]
def material(name, img=None, colour=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]
    if img is not None:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; nt.links.new(t.outputs[0], bsdf.inputs["Base Color"]); nt.nodes.active = t
    if colour: bsdf.inputs["Base Color"].default_value = colour
    bsdf.inputs["Roughness"].default_value = 0.6
    return m
# His painted eyes rest with heavy upper lids over the top of the iris; MakeHuman's rest wider. A quarter of its
# own blink is folded into the rest shape (and every expression shape) before baking, so the lid paint lands
# where the lid now sits.
REST_LID = float(os.environ.get("RAC_FACE_REST_LID", "0.25"))
kbs = me.shape_keys.key_blocks; basis = kbs[0]
B0 = np.zeros(len(me.vertices) * 3); basis.data.foreach_get("co", B0)
delta = np.zeros_like(B0)
for nm in ("eye-left-closure", "eye-right-closure"):
    K = np.zeros_like(B0); kbs[nm].data.foreach_get("co", K); delta += REST_LID * (K - B0)
for kb_ in kbs:
    K = np.zeros_like(B0); kb_.data.foreach_get("co", K); kb_.data.foreach_set("co", K + delta)
me.vertices.foreach_set("co", (B0 + delta)); me.update()
skin_img = bpy.data.images.new("face_skin", SK, SK); eye_img = bpy.data.images.new("face_eyes", EY, EY)
me.materials.clear()
for m in (material("FACE_skin", skin_img), material("FACE_eyes", eye_img), material("FACE_mouth", colour=(0.55, 0.25, 0.25, 1))):
    me.materials.append(m)
idx = {"skin": 0, "eye": 1, "mouth": 2}
for p in me.polygons:
    cs = [cls[i] for i in p.vertices]; p.material_index = idx["eye"] if "eye" in cs else idx["mouth"] if "mouth" in cs else 0
    p.use_smooth = True
# mouth material needs an image node too or the bake errors; give it a throwaway one
tmp = bpy.data.images.new("tmp_mouth", 8, 8); mm = me.materials[2].node_tree
tn = mm.nodes.new("ShaderNodeTexImage"); tn.image = tmp; mm.nodes.active = tn
# Bake the paint itself: route the acquired head's base colour to emission and bake EMIT. A DIFFUSE colour
# bake multiplies by (1 - metallic), and the painter left the skin slightly metallic, so the face came out dark.
for m in scan.data.materials:
    nt = m.node_tree; src_tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and any(l.to_socket.name == "Base Color" for l in n.outputs[0].links)), None)
    em = nt.nodes.new("ShaderNodeEmission"); outn = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    nt.links.new(src_tex.outputs[0], em.inputs[0]); nt.links.new(em.outputs[0], outn.inputs[0])
sc.render.engine = 'CYCLES'; sc.cycles.samples = 1; sc.cycles.device = 'CPU'
bk = sc.render.bake; bk.use_selected_to_active = True; bk.cage_extrusion = 0.01; bk.max_ray_distance = 0.03
bk.use_pass_direct = False; bk.use_pass_indirect = False; bk.use_pass_color = True; bk.margin = 8
for o in sc.objects: o.select_set(o in (scan, face))
bpy.context.view_layer.objects.active = face
for o in sc.objects:
    if o.type == 'MESH': o.hide_render = False
print('BAKE_START', flush=True)
bpy.ops.object.bake(type='EMIT')
# The eyeballs sit deeper behind the lids than the skin does behind the paint: with short rays they found
# nothing and came out milky. Bake them again on their own with a longer reach, the skin image untouched.
for m in me.materials: m.node_tree.nodes.active = next(n for n in m.node_tree.nodes if n.type == 'TEX_IMAGE')
sk_nodes = [n for n in me.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE']; keep_sk = skin_img.pixels[:]
bk.cage_extrusion = 0.04; bk.max_ray_distance = 0.08
bpy.ops.object.bake(type='EMIT')
skin_img.pixels[:] = keep_sk
print('BAKE_DONE', flush=True)
skin_img.filepath_raw = os.path.join(out, "face_skin.png"); skin_img.file_format = 'PNG'; skin_img.save()
eye_img.filepath_raw = os.path.join(out, "face_eyes.png"); eye_img.file_format = 'PNG'; eye_img.save()
skin_img.pack(); eye_img.pack()
bpy.data.images.remove(tmp); mm.nodes.remove(tn)
# The acquired hair keeps its volume: faces of the painted head that are painted dark and sit above the brows
# become their own mesh over MakeHuman's smooth scalp (it rides the head bone). Its own paint is kept.
import bmesh, numpy as np, colorsys
tex = next(n for n in scan.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE').image
TW, TH = tex.size; PX = np.array(tex.pixels[:], np.float32).reshape(TH, TW, -1)
gi_l = {g.name: g.index for g in face.vertex_groups}
brow_z = max(v.co.z for v in face.data.vertices if any(g.group in (gi_l["helper-l-eye"], gi_l["helper-r-eye"]) for g in v.groups))
hb = bmesh.new(); hb.from_mesh(scan.data); uvl = hb.loops.layers.uv.active; drop = []
for f in hb.faces:
    c = f.calc_center_median(); uv = sum((l[uvl].uv for l in f.loops), __import__("mathutils").Vector((0, 0))) / len(f.loops)
    r, g, b = PX[min(TH - 1, int(uv.y * TH)), min(TW - 1, int(uv.x * TW)), :3] ** (1 / 2.2)
    h_, s_, v_ = colorsys.rgb_to_hsv(float(r), float(g), float(b))
    if not (c.z > brow_z + 0.01 and v_ < 0.33): drop.append(f)
bmesh.ops.delete(hb, geom=drop, context='FACES')
for f in list(hb.faces):           # loose specks
    if all(len(e.link_faces) < 2 for e in f.edges): hb.faces.remove(f)
hm = bpy.data.meshes.new("hair"); hb.to_mesh(hm); hb.free()
for m in scan.data.materials: hm.materials.append(m)
hair = bpy.data.objects.new("hair", hm); sc.collection.objects.link(hair)
print("HAIR faces", len(hm.polygons))
# Eyes: baking the paint onto MakeHuman's eyeballs left them milky (its eye openings and the painted eyes do
# not line up exactly). Real eyeballs replace them: white spheres with an iris and pupil on the front, seated
# where MakeHuman's eyes sit behind the wrapped lids; the iris colour is sampled from the painted iris right in
# front of each eye.
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sbm2 = bmesh.new(); sbm2.from_mesh(scan.data); sbv = BVHTree.FromBMesh(sbm2); suv = sbm2.loops.layers.uv.active
co_f = np.array([v.co[:] for v in face.data.vertices])
# MediaPipe's iris centres (468, 473) on the painted head say where each iris is painted
import json as _json
fdir = os.path.dirname(os.path.abspath(out))
L2 = np.array(_json.load(open(os.path.join(fdir, "scan-landmarks.json")))["mediapipe_478_xy"])
cam = _json.load(open(os.path.join(fdir, "scan-front.json"))); cc, cs, cr = Vector(cam["centre"]), cam["ortho_scale"], cam["resolution"]
def iris_hit(k):
    x, y = L2[k]; o = Vector((cc.x + (x / cr - 0.5) * cs, -5.0, cc.z + (0.5 - y / cr) * cs))
    return sbv.ray_cast(o, Vector((0, 1, 0)))
eyes = {}
for side, gname, lm in (("l", "helper-l-eye", 473), ("r", "helper-r-eye", 468)):
    idx = [v.index for v in face.data.vertices if any(g.group == gi_l[gname] and g.weight > 0.5 for g in v.groups)]
    P = co_f[idx]; c = P.mean(0); r = float(np.linalg.norm(P - c, axis=1).mean())
    hit = iris_hit(lm)
    if hit[0] is None or (Vector(c) - hit[0]).length > 0.06:     # landmark side convention guard: use the nearer iris
        alt = iris_hit(468 if lm == 473 else 473)
        if alt[0] is not None and (alt[0] is not None and (hit[0] is None or (Vector(c) - alt[0]).length < (Vector(c) - hit[0]).length)): hit = alt
    sbm2.faces.ensure_lookup_table(); f = sbm2.faces[hit[2]]
    uv = sum((l[suv].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    iris = tuple(float(x) for x in PX[min(TH - 1, int(uv.y * TH)), min(TW - 1, int(uv.x * TW)), :3])
    R = r * 0.85
    fwd = (Vector(hit[0]) - Vector(c)).normalized()
    centre = Vector(hit[0]) - fwd * (R + 0.0015)      # the eye's front sits just behind the painted iris
    eyes[side] = (np.array(centre[:]), R, idx, iris, fwd)
fb = bmesh.new(); fb.from_mesh(face.data); fb.verts.ensure_lookup_table()
bmesh.ops.delete(fb, geom=[fb.verts[i] for e_ in eyes.values() for i in e_[2]], context='VERTS'); fb.to_mesh(face.data); fb.free()
iris_avg = tuple(float(x) for x in np.mean([e_[3] for e_ in eyes.values()], axis=0))
for side, (c, r, _, iris, fwd) in eyes.items():
    iris = iris_avg
    em_ = bpy.data.meshes.new(f"eye_{side}"); b = bmesh.new()
    bmesh.ops.create_uvsphere(b, u_segments=48, v_segments=24, radius=r)
    mats = [bpy.data.materials.new(f"EYE_{side}_{k}") for k in ("sclera", "iris", "pupil")]
    for m_, col in zip(mats, ((0.72, 0.68, 0.64, 1), (*iris, 1), (0.02, 0.02, 0.02, 1))):
        m_.use_nodes = True; bs = m_.node_tree.nodes["Principled BSDF"]; bs.inputs["Base Color"].default_value = col; bs.inputs["Roughness"].default_value = 0.2
        em_.materials.append(m_)
    for f in b.faces:
        f.smooth = True; d = f.calc_center_median().normalized(); facing = d.dot(fwd)
        f.material_index = 2 if facing > 0.975 else 1 if facing > 0.88 else 0
    b.to_mesh(em_); b.free()
    eo = bpy.data.objects.new(f"eye_{side}", em_); eo.location = Vector(c); sc.collection.objects.link(eo)
    print("EYE", side, "radius", round(r, 4), "iris", tuple(round(x, 3) for x in iris))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "face-baked.blend"))
print("BAKE_OK", {k: cls.count(k) for k in ("skin", "eye", "mouth")})
