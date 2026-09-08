"""Assign lining ownership on the existing AI collar, without repainting the face."""
import json
import sys
from pathlib import Path
import bpy

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
job = root/'work/sunset-ayric-v2/rig/head-assembly-v008'
if job.exists():
    raise RuntimeError('Keep prior collar evidence')
source = root/'work/sunset-ayric-v2/rig/head-assembly-v006/assembly-fit.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
body = bpy.data.objects['SK_SunsetAyricV2']
record = json.loads((source.parent/'assembly.json').read_text())
removed = set(record['removed_source_polygons'])
original_ids = [i for i in range(9670) if i not in removed]
sys.path.insert(0,str(root/'scripts/blender'))
from extract_head_transport import uv_islands
with bpy.data.libraries.load(str(root/'work/sunset-ayric-v2/rig/anatomical-v002/ayric_rigged.blend'),link=False) as (available, loaded):
    loaded.meshes = list(available.meshes)
source_mesh = loaded.meshes[0]
lining_faces = {f for island in uv_islands(source_mesh,source_mesh.uv_layers.active) if island[0] in {1668,2121,2801,3307} for f in island}
mat = bpy.data.materials.new('M_Ayric_CollarLining')
mat.use_nodes = True
bsdf = mat.node_tree.nodes['Principled BSDF']
bsdf.inputs['Base Color'].default_value = (.008,.018,.032,1)
bsdf.inputs['Metallic'].default_value = 0
bsdf.inputs['Roughness'].default_value = .82
body.data.materials.append(mat)
for p in body.data.polygons:
    if original_ids[p.index] in lining_faces:
        p.material_index = len(body.data.materials)-1
job.mkdir(parents=True)
bpy.ops.wm.save_as_mainfile(filepath=str(job/'assembly-fit.blend'))
(job/'lining.json').write_text(json.dumps({'status':'lining_candidate','source':str(source),'source_island_first_faces':[1668,2121,2801,3307], 'body_polygons':sorted(lining_faces),'linear_base_color':[.008,.018,.032],'roughness':.82,'face_texture_changed':False,'geometry_changed':False},indent=2))
print('COLLAR_LINING_CANDIDATE -- skin stays on the person, not the tailoring.')
