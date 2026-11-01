"""Put the painted head-only acquisition on the painted body: drop the body's own face, beard and hair faces,
align the head by a similarity on nose tip, ear width and nose-to-crown height, cut its bust away where the
body's collar and straps already are, and export one GLB for fixed-view renders.

Run in the parts blend (it holds the reduced parts used to tell which body face is which):
  $B -b raider-parts-v2.blend --python place_head.py -- <body.glb> <head.glb> <out.glb>
"""
import bpy, bmesh, sys, json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]; body_p, head_p, out_p = a
HEAD_PARTS = {"face", "beard", "hair"}
low = bpy.data.collections["low"]
parts = sorted([o for o in low.objects if o.type == 'MESH'], key=lambda o: o.name)
trees = {}
for o in parts:
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    trees[o.name] = BVHTree.FromPolygons([o.matrix_world @ v.co for v in me.vertices], [list(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
# old acquired-head landmarks, from the dense face/hair the body was cut from
fd = bpy.data.objects["face_dense"]; FV = np.array([(fd.matrix_world @ v.co)[:] for v in fd.data.vertices])
hd = bpy.data.objects["hair_dense"]; HV = np.array([(hd.matrix_world @ v.co)[:] for v in hd.data.vertices])
band = FV[(np.abs(FV[:, 0]) < 0.02) & (FV[:, 2] > 0.78) & (FV[:, 2] < 0.86)]; nose_old = band[band[:, 1].argmin()]
top_old = max(FV[:, 2].max(), HV[:, 2].max())
ear_old = np.ptp(FV[(FV[:, 2] > nose_old[2]) & (FV[:, 2] < nose_old[2] + 0.06), 0])
for o in list(bpy.context.scene.objects):
    if o.type == 'MESH': o.hide_render = True

bpy.ops.import_scene.gltf(filepath=body_p); body = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]; body.name = "raider_body"
bm = bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table(); drop = []
for f in bm.faces:
    c = body.matrix_world @ f.calc_center_median(); best, name = 1e9, None
    for n, t in trees.items():
        h = t.find_nearest(c)
        if h[0] is not None and h[3] < best: best, name = h[3], n
    if name in HEAD_PARTS: drop.append(f)
bmesh.ops.delete(bm, geom=drop, context='FACES'); bm.to_mesh(body.data); bm.free()
print("BODY head faces dropped", len(drop))

bpy.ops.import_scene.gltf(filepath=head_p); head = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]; head.name = "raider_head"
head.data.transform(head.matrix_world); head.matrix_world = Matrix.Identity(4)
HV2 = np.array([v.co[:] for v in head.data.vertices]); top_new = HV2[:, 2].max()
upper = HV2[HV2[:, 2] > np.percentile(HV2[:, 2], 40)]
cand = upper[np.abs(upper[:, 0]) < 0.05]; nose_new = cand[cand[:, 1].argmin()]
ear_new = np.ptp(HV2[(HV2[:, 2] > nose_new[2]) & (HV2[:, 2] < nose_new[2] + 0.06 * (top_new - nose_new[2]) / (top_old - nose_old[2]) * 1.0) & (HV2[:, 1] > nose_new[1] + 0.05), 0])
s_v = (top_old - nose_old[2]) / (top_new - nose_new[2]); s_w = ear_old / ear_new; s = float(0.5 * (s_v + s_w))
print("SCALE vertical", round(s_v, 4), "ears", round(s_w, 4), "used", round(s, 4))
M = Matrix.Translation(Vector(nose_old.tolist()) - s * Vector(nose_new.tolist())) @ Matrix.Scale(s, 4)
head.data.transform(M)
# cut the bust by the head's own paint: below the jaw, faces painted as the teal jacket go, and so do leather
# brown faces below the beard; skin and beard stay. Geometric cuts were tried and rejected: a distance cut left a
# ragged neck, and an outside-the-cloth test misread the collar's inner face, which faces the neck.
import colorsys
img = None
for m in head.data.materials:
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and any(l.to_socket.name == "Base Color" for l in n.outputs[0].links): img = n.image
IW, IH = img.size; PX = np.array(img.pixels[:], np.float32).reshape(IH, IW, -1)
hb = bmesh.new(); hb.from_mesh(head.data); hb.faces.ensure_lookup_table(); uvl = hb.loops.layers.uv.active; cut = []
jaw_z = nose_old[2] - 0.06; beard_z = nose_old[2] - 0.11
for f in hb.faces:
    c = f.calc_center_median()
    if c.z > jaw_z: continue
    if c.z < 0.62 or abs(c.x) > 0.15: cut.append(f); continue
    u = sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    r, g, b = PX[min(IH - 1, int(u.y * IH)), min(IW - 1, int(u.x * IW)), :3] ** (1 / 2.2)
    hh, ss, vv = colorsys.rgb_to_hsv(float(r), float(g), float(b)); hh *= 360
    teal = 150 <= hh <= 240 or (ss < 0.25 and vv < 0.35)
    leather = 10 <= hh <= 45 and ss > 0.35 and vv < 0.55 and c.z < beard_z
    if teal or leather: cut.append(f)
bmesh.ops.delete(hb, geom=cut, context='FACES'); hb.to_mesh(head.data); hb.free()
print("HEAD bust faces cut", len(cut), "kept", len(head.data.polygons))
for o in bpy.context.scene.objects: o.select_set(o in (body, head))
bpy.ops.export_scene.gltf(filepath=out_p, export_format='GLB', use_selection=True)
json.dump({"scale": s, "scale_vertical": s_v, "scale_ears": s_w, "nose_old": nose_old.tolist(), "body_faces_dropped": len(drop),
           "head_faces_cut": len(cut)}, open(out_p + ".json", "w"), indent=2)
print("PLACE_OK")
