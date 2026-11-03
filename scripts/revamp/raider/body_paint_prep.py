"""Join the Raider's reduced parts into one paint mesh with one UV atlas (islands stay inside their part) and
record which part every face came from, so the painted atlas can be split back onto the parts. The acquired
face, beard and hair stay in so the painter sees the whole character the reference shows; the painted head
replaces them later.

  $B -b <parts.blend> --python body_paint_prep.py -- <out-prefix> [--part-uv]

--part-uv cuts each part's charts the way a pattern is cut (part_uv.py) and packs them with an 8 px margin at 4096,
instead of one Smart UV Project over the joined mesh (about 10k saw-edged islands, each a seam in the paint).
"""
import bpy
import os
import sys
import json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from part_uv import CLOTH, islands, unwrap  # noqa: E402
a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
PART_UV = "--part-uv" in a
low = bpy.data.collections["low"]
parts = sorted([o for o in low.objects if o.type == 'MESH'], key=lambda o: o.name)
names = [o.name for o in parts]
for o in bpy.context.scene.objects:
    o.select_set(False)
copies = []
for i, o in enumerate(parts):
    c = o.copy()
    c.data = o.data.copy()
    bpy.context.scene.collection.objects.link(c)
    c.modifiers.clear()
    me = c.data
    me.attributes.new("part_id", 'INT', 'FACE').data.foreach_set("value", np.full(len(me.polygons), i, np.int32))
    for uvl in list(me.uv_layers):
        me.uv_layers.remove(uvl)
    me.materials.clear()
    copies.append(c)
uv_report = {}
if PART_UV:
    for c, n in zip(copies, names):
        # cloth parts (build_parts.py BASE) fold sharply only where a skirt turns under
        uv_report[n] = unwrap(c, CLOTH) if n in ("face", "skin", "glove", "jacket", "trousers", "boot") else unwrap(c)
        print("PART_UV", n, uv_report[n])
for c in copies:
    c.select_set(True)
bpy.context.view_layer.objects.active = copies[0]
bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = "raider_body_paint"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
# triangles only, so the part record matches the exported faces one to one
bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
if PART_UV:
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(margin=0.002, margin_method='FRACTION', rotate=True, shape_method='CONCAVE')
else:
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
    # a fixed fraction margin (4 px at 4096): the default scaled margin left 88% of the atlas empty across ~10k
    # islands
    bpy.ops.uv.pack_islands(margin=0.001, margin_method='FRACTION', rotate=True, shape_method='CONCAVE')
bpy.ops.object.mode_set(mode='OBJECT')
for p in ob.data.polygons:
    p.use_smooth = True
m = bpy.data.materials.new("paint")
m.use_nodes = True
ob.data.materials.append(m)
pid = np.zeros(len(ob.data.polygons), np.int32)
ob.data.attributes["part_id"].data.foreach_get("value", pid)
for o in list(bpy.context.scene.objects):
    if o is not ob:
        o.select_set(False)
ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=out + ".glb", export_format='GLB', use_selection=True, export_materials='EXPORT',
                          export_normals=True, export_texcoords=True, export_yup=True, export_attributes=False)
np.save(out + "-face-parts.npy", pid)
rep = {"parts": names, "faces": len(ob.data.polygons), "verts": len(ob.data.vertices),
       "faces_per_part": {n: int((pid == i).sum()) for i, n in enumerate(names)}, "uv_islands": islands(ob.data),
       "part_uv": uv_report}
json.dump(rep, open(out + ".json", "w"), indent=2)
print("BODY_PREP", json.dumps(rep)[:300])
