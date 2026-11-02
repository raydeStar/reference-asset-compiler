"""Find which part each painted face belongs to (nearest reduced part surface; the exporter can drop degenerate
faces, so order is not trusted) and rasterize atlas masks: one for the non-metal parts, plus a per-face part
record for splitting the atlas back onto the parts later."""
import bpy
import sys
import json
import numpy as np
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index("--") + 1:]
obj_path, out_dir, size = a[0], a[1], int(a[2])
METAL = {"plate", "buckle"}
low = bpy.data.collections["low"]
parts = sorted([o for o in low.objects if o.type == 'MESH'], key=lambda o: o.name)
trees = []
for o in parts:
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    V = [o.matrix_world @ v.co for v in me.vertices]
    F = [list(p.vertices) for p in me.polygons]
    trees.append(BVHTree.FromPolygons(V, F))
    ev.to_mesh_clear()
bpy.ops.wm.obj_import(filepath=obj_path, forward_axis='NEGATIVE_Z', up_axis='Y')
ob = [o for o in bpy.context.selected_objects if o.type == 'MESH'][0]
me = ob.data
uv = me.uv_layers.active.data
tris_uv = []
pid = np.zeros(len(me.polygons), np.int32)
far = 0
for p in me.polygons:
    c = ob.matrix_world @ p.center
    best, bi = 1e9, 0
    for i, t in enumerate(trees):
        hit = t.find_nearest(c)
        if hit[0] is not None and hit[3] < best:
            best, bi = hit[3], i
    pid[p.index] = bi
    far += best > 0.01
    if parts[bi].name not in METAL:
        tris_uv.append([(uv[li].uv.x, uv[li].uv.y) for li in list(p.loop_indices)[:3]])
np.save(f"{out_dir}/nonmetal-uv-tris.npy", np.array(tris_uv, np.float32))
np.save(f"{out_dir}/painted-face-parts.npy", pid)
counts = {parts[i].name: int((pid == i).sum()) for i in range(len(parts))}
json.dump({"parts": [o.name for o in parts], "counts": counts, "faces_far_from_parts": int(far)}, open(f"{out_dir}/painted-face-parts.json", "w"), indent=2)
print("MASK_OK", counts, "far", far)
