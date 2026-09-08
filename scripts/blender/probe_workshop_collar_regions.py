"""Diagnostic false colours identify collar ownership, without editing authority."""
import sys
from pathlib import Path
import bpy

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
sys.path.insert(0,str(root/'scripts/blender'))
from extract_head_transport import uv_islands
source = root/'work/sunset-ayric-v2/rig/head-assembly-v006/assembly-fit.blend'
output = root/'work/sunset-ayric-v2/rig/neck-transition-probe-v001.blend'
if output.exists():
    raise RuntimeError('Preserve the diagnostic')
bpy.ops.wm.open_mainfile(filepath=str(source))
body = bpy.data.objects['SK_SunsetAyricV2']
# Recover source polygon IDs from the immutable trim receipt.
import json
record = json.loads((source.parent/'assembly.json').read_text())
removed = set(record['removed_source_polygons'])
original_ids = [i for i in range(9670) if i not in removed]
for key, ids, color in [('CollarSides',{1668,2121},(.1,.8,.2,1)),('InnerFront',{2801,3307},(.8,.1,.8,1))]:
    material = bpy.data.materials.new('DIAGNOSTIC_'+key)
    material.use_nodes = True
    material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
    body.data.materials.append(material)
    # Source island list is saved by reopening the original temporarily below.
    material['source_islands'] = list(ids)
original = bpy.data.libraries.load(str(root/'work/sunset-ayric-v2/rig/anatomical-v002/ayric_rigged.blend'),link=False)
with original as (available, loaded):
    loaded.meshes = list(available.meshes)
source_mesh = loaded.meshes[0]
mapping = {}
for island in uv_islands(source_mesh,source_mesh.uv_layers.active):
    for f in island:
        mapping[f] = island[0]
for p in body.data.polygons:
    island = mapping[original_ids[p.index]]
    if island in {1668,2121}:
        p.material_index = len(body.data.materials)-2
    elif island in {2801,3307}:
        p.material_index = len(body.data.materials)-1
bpy.ops.wm.save_as_mainfile(filepath=str(output))
print('COLLAR_OWNERSHIP_PROBE -- false colour, true boundaries.')
