"""Read-only assembly measurements: the collar deserves a proper fitting."""
import json
import sys
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_head_transport import uv_islands

root = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
rig = root / 'work/sunset-ayric-v2/rig/anatomical-v002/ayric_rigged.blend'
bpy.ops.wm.open_mainfile(filepath=str(rig))
report = {'body': []}
for obj in bpy.context.scene.objects:
    entry = {'name': obj.name, 'type': obj.type, 'matrix': [list(row) for row in obj.matrix_world]}
    if obj.type == 'MESH':
        pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        image = bpy.data.images.load(str(root/'work/sunset-ayric-v2/prod-calibrated-v001/T_sunset-ayric-v2_BaseColor.png'), check_existing=True)
        pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(image.size[1],image.size[0],4)
        entry.update(vertices=len(pts), bounds=[[min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]])
        entry['head_uv_islands'] = []
        for faces in uv_islands(obj.data, obj.data.uv_layers.active):
            ids = {v for f in faces for v in obj.data.polygons[f].vertices}
            p = [pts[i] for i in ids]
            if min(v.z for v in p) < 1.54 and max(v.z for v in p) > 1.50 and max(abs(v.x) for v in p) < .14:
                colors = []
                for f in faces:
                    uv = sum((obj.data.uv_layers.active.data[loop].uv for loop in obj.data.polygons[f].loop_indices), start=__import__('mathutils').Vector((0,0))) / len(obj.data.polygons[f].loop_indices)
                    colors.append(pixels[min(image.size[1]-1,int(uv.y*image.size[1])),min(image.size[0]-1,int(uv.x*image.size[0])),:3])
                entry['head_uv_islands'].append({'faces':len(faces), 'first_face':faces[0], 'median_rgb':np.median(colors,axis=0).tolist(), 'bounds':[[min(v[i] for v in p) for i in range(3)],[max(v[i] for v in p) for i in range(3)]]})
    if obj.type == 'ARMATURE':
        entry['head_bone'] = {'head': list(obj.data.bones['head'].head_local), 'tail': list(obj.data.bones['head'].tail_local)}
    report['body'].append(entry)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(root / 'work/sunset-ayric-rigid-head-v1/prod-texture-v001/sunset-ayric-rigid-head-v1_production.fbx'))
report['head'] = []
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
        report['head'].append({'name': obj.name, 'matrix': [list(row) for row in obj.matrix_world], 'bounds': [[min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]], 'materials': [s.material.name for s in obj.material_slots]})
print('HEAD_FIT_MEASUREMENTS ' + json.dumps(report))
