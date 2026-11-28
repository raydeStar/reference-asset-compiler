"""Make the assembled Raider a single real-scale production mesh for the rig stage: join body, head and
hands (materials kept), scale to the declared height with the soles on the floor, centred, facing -Y.

  $B -b --factory-startup --python prep_production.py -- <assembled.glb> <out.glb> [height_m] [--body-budget N]
      [--head-budget N] [--hand-budget N]

--body-budget raises the body's triangle budget so parts already reduced to the production density
(build_parts.py --budget-scale) are not collapsed a second time: that second collapse, across the joined closed
shells, is what spiked the shells' rims and opened holes in them on the v5 Raider. --head-budget lowers the
acquired head's: it only stands in until the face stage swaps in the speaking face, but the rig gate counts it
against the hero tier's 80k ceiling. --hand-budget sets each hand's.
"""
import bpy
import bmesh
import sys
import json
import numpy as np
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
height = float(a[2]) if len(a) > 2 and not a[2].startswith("--") else 1.82
# RAC's hero tier allows 60-80k triangles for everything the skeletal mesh ships (profiles/triangle-budgets.json);
# spend it on the face and hands first
BUDGET = {"raider_head": 18000, "raider_hand_r": 6000, "raider_hand_l": 6000, "raider_body": 46000}
if "--body-budget" in a:
    BUDGET["raider_body"] = int(a[a.index("--body-budget") + 1])
if "--head-budget" in a:
    BUDGET["raider_head"] = int(a[a.index("--head-budget") + 1])
if "--hand-budget" in a:
    BUDGET["raider_hand_r"] = BUDGET["raider_hand_l"] = int(a[a.index("--hand-budget") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
report_tris = {}
for o in obs:
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bm.to_mesh(o.data)
    bm.free()
    key = next((k for k in BUDGET if o.name.startswith(k)), None)
    n = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if key and n > BUDGET[key]:
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("reduce", 'DECIMATE')
        m.ratio = BUDGET[key] / n
        m.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=m.name)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(o.data)
    bm.free()
    report_tris[o.name] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    o.select_set(True)
print("REDUCED", report_tris)
bpy.context.view_layer.objects.active = obs[0]
bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = "raider"
ob.data.name = "raider"
V = np.array([v.co[:] for v in ob.data.vertices])
s = height / np.ptp(V[:, 2])
cx, cy = (V[:, 0].min() + V[:, 0].max()) / 2, (V[:, 1].min() + V[:, 1].max()) / 2
ob.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation((-cx, -cy, -V[:, 2].min())))
for p in ob.data.polygons:
    p.use_smooth = True
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
V = np.array([v.co[:] for v in ob.data.vertices])
rep = {"source": src, "part_triangles": report_tris, "height_m": height, "scale": float(s), "faces": len(ob.data.polygons), "verts": len(ob.data.vertices),
       "materials": [m.name for m in ob.data.materials], "bbox": [V.min(0).round(4).tolist(), V.max(0).round(4).tolist()]}
json.dump(rep, open(out + ".json", "w"), indent=2)
print("PROD_OK", json.dumps(rep))
