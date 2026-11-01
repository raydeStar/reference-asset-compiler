"""Replace MakeHuman's crude helper eyes with separate eyeballs (they ride eye bones later), then render the
modeling-gate views of the whole modular Raider: part colours and plain shape, four sides, plus head close-ups."""
import bpy, bmesh, sys, os, math, json
import numpy as np
from mathutils import Vector, Matrix, Euler
sys.stdout.reconfigure(line_buffering=True)
out = sys.argv[sys.argv.index("--") + 1:][0]
sc = bpy.context.scene
head = bpy.data.objects["head"]; me = head.data
gi = {g.name: g.index for g in head.vertex_groups}
CO = np.array([v.co[:] for v in me.vertices])
eye_info = {}
already = "eye_l" in bpy.data.objects
for side, gname in (("l", "helper-l-eye"), ("r", "helper-r-eye")):
    if already: break
    idx = [v.index for v in me.vertices if any(g.group == gi[gname] and g.weight > 0.5 for g in v.groups)]
    P = CO[idx]; c = P.mean(0); r = float(np.linalg.norm(P - c, axis=1).mean())
    eye_info[side] = (c, r, idx)
if not already:
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for s in eye_info.values() for i in s[2]], context='VERTS')
    bm.to_mesh(me); bm.free()
white = bpy.data.materials.get("HEAD_eye")
iris = bpy.data.materials.new("EYE_iris"); iris.diffuse_color = (0.25, 0.3, 0.35, 1)
for side, (c, r, _) in eye_info.items():
    em = bpy.data.meshes.new(f"eye_{side}"); b = bmesh.new()
    bmesh.ops.create_uvsphere(b, u_segments=24, v_segments=16, radius=r * 0.94)
    for v in b.verts: v.co = v.co + Vector((0, 0.08 * r, 0))  # sit a little behind the lids
    for f in b.faces:
        f.smooth = True
        f.material_index = 1 if f.calc_center_median().y < -r * 0.80 else 0
    b.to_mesh(em); b.free(); em.materials.append(white); em.materials.append(iris)
    eo = bpy.data.objects.new(f"eye_{side}", em); eo.location = Vector(c); sc.collection.objects.link(eo)
    low = bpy.data.collections.get("low")
    print("EYE", side, [round(x, 4) for x in c], "r", round(r, 4))
for n in ("face",):
    o = bpy.data.objects.get(n)
    if o: o.hide_render = True; o.hide_viewport = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "raider-head-v1.blend"))

# gate renders
parts = [o for o in sc.objects if o.type == 'MESH' and not o.name.endswith("_dense") and o.name not in ("face", "mh_full_fitted")]
for o in sc.objects:
    if o.type == 'MESH': o.hide_render = o not in parts
tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in parts}
json.dump({"parts": tris, "total_tris": sum(tris.values())}, open(os.path.join(out, "gate-parts.json"), "w"), indent=2)
print("PARTS", json.dumps(tris), "TOTAL", sum(tris.values()))
sh = sc.display.shading; sc.render.engine = 'BLENDER_WORKBENCH'
cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
if cam.name not in sc.collection.objects: sc.collection.objects.link(cam)
sc.camera = cam; cam.data.type = 'ORTHO'
front = Vector((0, -1, 0))
def shoot(path, ang, size, c, res):
    sc.render.resolution_x, sc.render.resolution_y = res; cam.data.ortho_scale = size
    d = front.copy(); d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = c + d * 8; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)
body_c = Vector((0, 0.005, -0.004)); head_c = Vector((0, -0.04, 0.84))
for mode in ("labels", "shape"):
    if mode == "labels":
        sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True; sh.show_object_outline = True
    else:
        sh.light = 'MATCAP'; sh.color_type = 'SINGLE'; sh.single_color = (0.8, 0.8, 0.8); sh.show_object_outline = False
    for nm, ang in (("front", 0), ("three-quarter", 45), ("side", 90), ("back", 180)):
        shoot(os.path.join(out, f"gate-{mode}-{nm}.png"), ang, 2.15, body_c, (700, 1000))
    for nm, ang in (("front", 0), ("three-quarter", 35), ("side", 90), ("back", 180)):
        shoot(os.path.join(out, f"gate-{mode}-head-{nm}.png"), ang, 0.34, head_c, (600, 600))
print("SHEET_DONE")
