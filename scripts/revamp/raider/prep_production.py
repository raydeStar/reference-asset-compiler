"""Make the assembled Raider a single real-scale production mesh for the rig stage: join body, head and
hands (materials kept), scale to the declared height with the soles on the floor, centred, facing -Y.

  $B -b --factory-startup --python prep_production.py -- <assembled.glb> <out.glb> [height_m]
"""
import bpy, sys, json
import numpy as np
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]; src, out = a[0], a[1]; height = float(a[2]) if len(a) > 2 else 1.82
# RAC's hero tier allows 60-80k triangles for everything the skeletal mesh ships (profiles/triangle-budgets.json);
# spend it on the face and hands first
BUDGET = {"raider_head": 18000, "raider_hand_r": 6000, "raider_hand_l": 6000, "raider_body": 46000}
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
report_tris = {}
for o in obs:
    o.data.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4)
    key = next((k for k in BUDGET if o.name.startswith(k)), None)
    n = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if key and n > BUDGET[key]:
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("reduce", 'DECIMATE'); m.ratio = BUDGET[key] / n; m.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=m.name)
    report_tris[o.name] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    o.select_set(True)
print("REDUCED", report_tris)
bpy.context.view_layer.objects.active = obs[0]; bpy.ops.object.join(); ob = bpy.context.view_layer.objects.active
ob.name = "raider"; ob.data.name = "raider"
V = np.array([v.co[:] for v in ob.data.vertices]); s = height / np.ptp(V[:, 2])
cx, cy = (V[:, 0].min() + V[:, 0].max()) / 2, (V[:, 1].min() + V[:, 1].max()) / 2
ob.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation((-cx, -cy, -V[:, 2].min())))
for p in ob.data.polygons: p.use_smooth = True
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)
V = np.array([v.co[:] for v in ob.data.vertices])
rep = {"source": src, "part_triangles": report_tris, "height_m": height, "scale": float(s), "faces": len(ob.data.polygons), "verts": len(ob.data.vertices),
       "materials": [m.name for m in ob.data.materials], "bbox": [V.min(0).round(4).tolist(), V.max(0).round(4).tolist()]}
json.dump(rep, open(out + ".json", "w"), indent=2); print("PROD_OK", json.dumps(rep))
