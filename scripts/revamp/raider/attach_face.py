"""Put the wrapped, baked MakeHuman face (with its expression shapes), the acquired hair and the eyeballs on the
rigged Raider, in place of the painted head that was part of the body mesh.

The body's skeleton and weights stay as they are (the face fits the same head shape). The new pieces are
brought into production space with the transform prep_production.py used (its scale, the assembled model's
bounds), then nudged so the painted head they were fitted to lands on the head faces being replaced. The face
rides the head and neck bones, blending down the neck; hair and eyes are rigid on the head.

  $B -b <rigged.blend> --python attach_face.py -- <face-baked.blend> <assembled.glb> <production.json> <out.fbx> <out.blend>
"""
import bpy, bmesh, sys, json, os
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
a = sys.argv[sys.argv.index("--") + 1:]; face_p, asm_p, prod_p, out_fbx, out_blend = a
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = next(o for o in sc.objects if o.type == 'MESH' and o.parent == arm)
head_mat = max(range(len(body.data.materials)), key=lambda i: max(((body.matrix_world @ p.center).z for p in body.data.polygons if p.material_index == i), default=-1)
                 if sum(1 for p in body.data.polygons if p.material_index == i) > 1000 else -1)
old_head = np.array([(body.matrix_world @ body.data.vertices[v].co)[:] for p in body.data.polygons if p.material_index == head_mat for v in p.vertices])
print("OLD head material", body.data.materials[head_mat].name, "verts", len(old_head))

# production transform, as prep_production.py made it
prod = json.load(open(prod_p)); s = prod["scale"]
bpy.ops.import_scene.gltf(filepath=asm_p)
asm = [o for o in bpy.context.selected_objects if o.type == 'MESH']
AV = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in asm])
cx, cy, z0 = (AV[:, 0].min() + AV[:, 0].max()) / 2, (AV[:, 1].min() + AV[:, 1].max()) / 2, AV[:, 2].min()
for o in asm: bpy.data.objects.remove(o)
M = Matrix.Scale(s, 4) @ Matrix.Translation((-cx, -cy, -z0))

with bpy.data.libraries.load(face_p, link=False) as (src, dst):
    # eyelashes are left out: Mark found the lash cards weird at this style; the paint carries the lash line
    # the painted hair's own piece is left out too: it only covered the front fringe, as patchy fragments cut out by
    # dark paint strokes (the "scribbles"); the wrapped scalp already carries the hair paint and the hair's volume
    dst.objects = [n for n in src.objects if n in ("face", "eye_l", "eye_r", "mouth_back", "eyes", "teeth", "tongue") or n.startswith("raider_head")]
new = {}
for o in dst.objects:
    # matrix_basis (from the stored location, rotation, scale): a freshly appended object's matrix_world can be stale
    sc.collection.objects.link(o); o.matrix_world = M @ o.matrix_basis; new[o.name] = o
scan = next(o for n, o in new.items() if n.startswith("raider_head"))
# nudge: the painted head they were fitted to should land on the head faces being replaced
kd = KDTree(len(old_head))
for i, p in enumerate(old_head): kd.insert(p, i)
kd.balance()
shift = Vector((0, 0, 0))
SVw = [scan.matrix_world @ v.co for v in list(scan.data.vertices)[::7]]
for _ in range(4):
    d = np.array([(Vector(kd.find(p + shift)[0]) - (p + shift))[:] for p in SVw]); shift += Vector(np.median(d, 0))
print("NUDGE", [round(x, 4) for x in shift], "residual median", round(float(np.median(np.linalg.norm(d, axis=1))), 4))
for o in new.values(): o.location = o.location + shift
bpy.data.objects.remove(scan)
# bake the transform into the meshes (the rig gate requires applied scale); shape keys move with them
for n, o in new.items():
    if n.startswith("raider_head"): continue
    bpy.context.view_layer.update(); o.data.transform(o.matrix_world, shape_keys=True); o.matrix_world = Matrix.Identity(4)
    if not o.data.uv_layers:   # the eyeballs: a spherical UV so the mesh carries a UV layer like every other part
        uvl = o.data.uv_layers.new(name="UVMap"); c = np.array([v.co[:] for v in o.data.vertices]).mean(0)
        for loop in o.data.loops:
            p_ = np.array(o.data.vertices[loop.vertex_index].co[:]) - c; r_ = np.linalg.norm(p_) + 1e-9
            uvl.data[loop.index].uv = (0.5 + np.arctan2(p_[0], -p_[1]) / (2 * np.pi), 0.5 + np.arcsin(np.clip(p_[2] / r_, -1, 1)) / np.pi)
# Eyes: one smooth material per eye instead of colour by face (the iris and pupil looked blocky up close).
# Sclera, limbus, iris and pupil blend by the angle from the eye's front, the front being where the iris faces were.
for n in ("eye_l", "eye_r"):
    if n not in new: continue
    o = new[n]; me_ = o.data; P = np.array([v.co[:] for v in me_.vertices]); cen = P.mean(0)
    iris_idx = [i for i, m_ in enumerate(me_.materials) if m_ and "_iris" in m_.name]
    iris_col = tuple(me_.materials[iris_idx[0]].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value) if iris_idx else (0.39, 0.41, 0.41, 1)
    fc = np.array([p_.center[:] for p_ in me_.polygons if p_.material_index in iris_idx]) if iris_idx else P[P[:, 1].argmin()][None]
    fwd_ = fc.mean(0) - cen; fwd_ /= np.linalg.norm(fwd_)
    m = bpy.data.materials.new(f"EYE_{n[-1]}"); m.use_nodes = True; nt = m.node_tree; N_ = nt.nodes; Lk = nt.links
    geo = N_.new("ShaderNodeNewGeometry"); sub = N_.new("ShaderNodeVectorMath"); sub.operation = 'SUBTRACT'; sub.inputs[1].default_value = tuple(cen)
    nrm_ = N_.new("ShaderNodeVectorMath"); nrm_.operation = 'NORMALIZE'; dot = N_.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'; dot.inputs[1].default_value = tuple(fwd_)
    ramp = N_.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    lim = tuple(x * 0.45 for x in iris_col[:3]) + (1,)
    stops = [(0.0, (0.6, 0.55, 0.5, 1)), (0.86, (0.6, 0.55, 0.5, 1)), (0.885, lim), (0.9, iris_col), (0.955, tuple(x * 0.8 for x in iris_col[:3]) + (1,)), (0.97, (0.02, 0.02, 0.02, 1)), (1.0, (0.02, 0.02, 0.02, 1))]
    cr.elements[0].position, cr.elements[0].color = stops[0]; cr.elements[1].position, cr.elements[1].color = stops[-1]
    for pos_, col_ in stops[1:-1]:
        e_ = cr.elements.new(pos_); e_.color = col_
    bs = N_["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.1
    Lk.new(geo.outputs["Position"], sub.inputs[0]); Lk.new(sub.outputs[0], nrm_.inputs[0]); Lk.new(nrm_.outputs[0], dot.inputs[0])
    Lk.new(dot.outputs["Value"], ramp.inputs["Fac"]); Lk.new(ramp.outputs["Color"], bs.inputs["Base Color"])
    me_.materials.clear(); me_.materials.append(m)
    for p_ in me_.polygons: p_.material_index = 0
eyes_y = [np.array([v.co[:] for v in new[n].data.vertices]).mean(0) for n in ("eye_l", "eye_r") if n in new]
print("EYES at", [[round(x, 3) for x in e] for e in eyes_y], "head bone y", round((arm.matrix_world @ arm.data.bones["head"].head_local).y, 3))

# the face's skin image comes from disk (fix_neck_paint.py repaints it after the bake)
skin_png = os.path.join(os.path.dirname(face_p), "face_skin.png")
for im_ in bpy.data.images:
    if im_.name.startswith("face_skin") and os.path.exists(skin_png):
        im_.unpack(method='REMOVE') if im_.packed_file else None; im_.filepath = skin_png; im_.source = 'FILE'; im_.reload(); im_.pack()
# remove the old head from the body
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == head_mat], context='FACES_ONLY')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# the body carries hundreds of loose slivers left by reducing its shells: sweep pieces under a dozen faces
# (weld exactly coincident vertices first: the mesh is split at UV seams, and unwelded, small UV islands
# would read as loose pieces)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
bm.faces.ensure_lookup_table(); seen = set(); loose = []
for f in bm.faces:
    if f.index in seen: continue
    stack = [f]; seen.add(f.index); grp = []
    while stack:
        g = stack.pop(); grp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen: seen.add(h.index); stack.append(h)
    if len(grp) < 12: loose += grp
bmesh.ops.delete(bm, geom=loose, context='FACES'); bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
print("BODY loose slivers removed", len(loose))
bm.to_mesh(body.data); bm.free()

# The body still carries the original painted neck and chest skin inside the collar, with ragged edges, lying
# on the new face's neck: body faces on the face's surface (within 1 cm) and facing the same way go. The collar's
# inner side faces the neck, so it stays.
from mathutils.bvhtree import BVHTree
fbm = bmesh.new(); fbm.from_mesh(new["face"].data); fbm.transform(new["face"].matrix_world); fbvh = BVHTree.FromBMesh(fbm)
bm = bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table(); over = []
for f in bm.faces:
    c = body.matrix_world @ f.calc_center_median()
    loc, nrm, _, dd = fbvh.find_nearest(c)
    if loc is not None and dd < 0.01 and (body.matrix_world.to_3x3() @ f.normal).dot(nrm) > 0.3: over.append(f)
# ... and, within 8 cm of the new neck, any remaining body face painted as skin (bright, warm; leather is darker)
import colorsys
mat0 = body.data.materials[0]; atlas = next(n.image for n in mat0.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and any(l.to_socket.name == "Base Color" for l in n.outputs[0].links))
AW, AH = atlas.size; AP = np.array(atlas.pixels[:], np.float32).reshape(AH, AW, -1)
uvl = bm.loops.layers.uv.active; fz = [v.co.z for v in new["face"].data.vertices]; fmin = min(fz)
neck_top = (arm.matrix_world @ arm.data.bones["head"].head_local).z + 0.02
for f in bm.faces:
    if f in over or f.material_index != 0: continue
    c = body.matrix_world @ f.calc_center_median()
    if not (fmin - 0.02 < c.z < neck_top and abs(c.x) < 0.14): continue
    # close to the new neck only: leather straps share skin's hue (a colour-only rule shredded them, and so did
    # a 5 cm reach for brighter skin: the strap by the collar is bright leather)
    dn = fbvh.find_nearest(c)[3]
    # ... or standing directly in front of the new neck (a ray back from the face hits the neck within 6 cm):
    # the skin-painted sliver in the open V stood a little over 3 cm proud of it
    if dn > 0.08: continue
    uv = sum((l[uvl].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    # the atlas pixels are already display colour: brightening them again washed skin out to ~0.26 saturation,
    # under the cutoff, while darker leather passed. Skin is bright and warm; leather is darker.
    r, g, b = AP[min(AH - 1, int(uv.y * AH)), min(AW - 1, int(uv.x * AW)), :3]
    h_, s_, v_ = colorsys.rgb_to_hsv(float(r), float(g), float(b)); h_ *= 360
    if 8 <= h_ <= 38 and s_ > 0.3 and v_ > 0.55: over.append(f)
bmesh.ops.delete(bm, geom=list(set(over)), context='FACES'); bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
# removing the neck skin strands small fragments around the neck: sweep again (pieces under 12 faces anywhere,
# under 60 within 5 cm of the new neck)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6); bm.faces.ensure_lookup_table(); seen = set(); frag = []
for f in bm.faces:
    if f.index in seen: continue
    stack = [f]; seen.add(f.index); grp = []
    while stack:
        g = stack.pop(); grp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen: seen.add(h.index); stack.append(h)
    near = fbvh.find_nearest(body.matrix_world @ grp[0].calc_center_median())[3] < 0.05
    if len(grp) < 12 or (near and len(grp) < 60): frag += grp
bmesh.ops.delete(bm, geom=frag, context='FACES'); bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(body.data); bm.free(); fbm.free()
print("BODY neck skin faces removed", len(set(over)), "fragments swept", len(frag))

# attach: face on head and neck by height, hair and eyes rigid on the head
B = arm.data.bones
zw = lambda n: (arm.matrix_world @ B[n].head_local).z
z_n1, z_n2, z_h = zw("neck_01"), zw("neck_02"), zw("head")
for name, o in new.items():
    if name.startswith("raider_head"): continue
    bpy.context.view_layer.update()
    for vg in list(o.vertex_groups): o.vertex_groups.remove(vg)
    groups = {n: o.vertex_groups.new(name=n) for n in ("neck_01", "neck_02", "head")}
    for v in o.data.vertices:
        z = (o.matrix_world @ v.co).z
        if name != "face" or z >= z_h + 0.02: w = {"head": 1.0}
        elif z >= z_n2:
            t = (z - z_n2) / max(z_h + 0.02 - z_n2, 1e-6); w = {"head": t, "neck_02": 1 - t}
        else:
            t = np.clip((z - z_n1) / max(z_n2 - z_n1, 1e-6), 0, 1); w = {"neck_02": t, "neck_01": 1 - t}
        for n, val in w.items():
            if val > 1e-4: groups[n].add([v.index], float(val), 'REPLACE')
    mw = o.matrix_world.copy(); o.parent = arm; o.matrix_parent_inverse = arm.matrix_world.inverted(); o.matrix_world = mw
    md = o.modifiers.new("Armature", 'ARMATURE'); md.object = arm
print("ATTACHED", sorted(n for n in new if not n.startswith("raider_head")))
os.makedirs(os.path.dirname(out_blend), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
for o in sc.objects: o.select_set(o.type in ('ARMATURE', 'MESH'))
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="COPY", embed_textures=True, use_mesh_modifiers=False)
print("FACE_ATTACH_OK")
