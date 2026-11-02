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
    dst.objects = [n for n in src.objects if n in ("face", "hair", "eye_l", "eye_r") or n.startswith("raider_head")]
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
eyes_y = [np.array([v.co[:] for v in new[n].data.vertices]).mean(0) for n in ("eye_l", "eye_r") if n in new]
print("EYES at", [[round(x, 3) for x in e] for e in eyes_y], "head bone y", round((arm.matrix_world @ arm.data.bones["head"].head_local).y, 3))

# remove the old head from the body
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index == head_mat], context='FACES_ONLY')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(body.data); bm.free()

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
