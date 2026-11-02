"""High-resolution inspection renders of the rigged Raider: whole figure from eight directions, back of the neck,
the mouth open from the front, and every loose piece of each mesh listed by size and position, so floating
fragments are found by measurement as well as by eye.

  $B -b <rigged.blend> --python inspect_views.py -- <out_dir>
"""
import bpy, bmesh, sys, math, os, json
import numpy as np
from mathutils import Vector, Euler
out = sys.argv[sys.argv.index("--") + 1:][0]; os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
pieces = []
for o in sc.objects:
    if o.type != 'MESH': continue
    bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6); bm.faces.ensure_lookup_table()
    seen = set()
    for f in bm.faces:
        if f.index in seen: continue
        stack = [f]; seen.add(f.index); grp = []
        while stack:
            g = stack.pop(); grp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen: seen.add(h.index); stack.append(h)
        P = np.array([(o.matrix_world @ v.co)[:] for g in grp for v in g.verts])
        pieces.append({"object": o.name, "faces": len(grp), "centre": P.mean(0).round(3).tolist(), "size": float(np.ptp(P, 0).max())})
    bm.free()
small = sorted([p for p in pieces if p["faces"] < 60], key=lambda p: p["faces"])
json.dump({"pieces": len(pieces), "small_pieces": small}, open(f"{out}/pieces.json", "w"), indent=1)
print("PIECES", len(pieces), "small(<60 faces)", len(small))
sc.render.engine = 'BLENDER_EEVEE'; sc.view_settings.view_transform = 'Standard'
w = sc.world or bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.75, 0.78, 1)
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", 'SUN')); sun.data.energy = 2.6; sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'
def shoot(path, ang, size, c, res=(900, 1300), elev=0):
    sc.render.resolution_x, sc.render.resolution_y = res; cam.data.ortho_scale = size
    d = Vector((0, -1, 0)); d.rotate(Euler((math.radians(elev), 0, math.radians(ang)))); cam.location = c + d * 6
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler(); sc.render.filepath = path; bpy.ops.render.render(write_still=True)
for ang in range(0, 360, 45): shoot(f"{out}/body-{ang:03d}.png", ang, 2.05, Vector((0, 0, 0.91)))
head = arm.matrix_world @ arm.data.bones["head"].head_local
for nm, ang, el in (("neck-back", 180, 0), ("neck-back-high", 180, -25), ("neck-side", 90, 0), ("neck-front", 0, 0)):
    shoot(f"{out}/{nm}.png", ang, 0.42, head + Vector((0, 0, -0.02)), (800, 800), el)
face = bpy.data.objects.get("face")
if face and face.data.shape_keys:
    kb = face.data.shape_keys.key_blocks
    for k in kb[1:]: k.value = 0
    kb["mouth-open"].value = 1.0
    shoot(f"{out}/mouth-open.png", 0, 0.14, head + Vector((0, -0.05, 0.03)), (800, 800))
    kb["mouth-open"].value = 0.0
print("INSPECT_OK")
