"""Remove detached reconstruction debris, retaining the connected trunk and crown."""
import hashlib
import json
import shutil
from pathlib import Path

import trimesh


root = Path(__file__).resolve().parents[2]
public = root / 'apps/lakeside-village/public/assets/pine-tree.glb'
review = root / 'work/lakeside-pine-tree/modeling-review-v1'
rejected = review / 'rejected-floating-fragments.glb'
output_dir = root / 'work/lakeside-pine-tree/modeling-clean-v2'
output_dir.mkdir(exist_ok=False)
shutil.copy2(public, rejected)
source_hash = hashlib.sha256(public.read_bytes()).hexdigest()
mesh = trimesh.load(public, force='mesh', process=False)
components = sorted(mesh.split(only_watertight=False), key=lambda item: len(item.faces), reverse=True)
clean = components[0]
assert len(clean.faces) / len(mesh.faces) > 0.98, 'Refuse a cleanup that removes substantial tree structure'
assert len(clean.split(only_watertight=False)) == 1
output = output_dir / 'mesh.glb'
clean.export(output)
exported = trimesh.load(output, force='mesh', process=False)
assert len(exported.split(only_watertight=False)) == 1
assert len(exported.faces) == len(clean.faces)
receipt = {'schema':'stillwater.tree-cleanup.v1','reason':'User observed floating shards next to the tree','parent':str(rejected),'parent_sha256':source_hash,'output':str(output),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'components_before':len(components),'components_after':1,'faces_before':len(mesh.faces),'faces_after':len(clean.faces),'removed_triangles':len(mesh.faces)-len(clean.faces),'removed_components_faces':[len(part.faces) for part in components[1:]],'preserved_main_component_geometry':True,'generated_geometry_added':False}
(output_dir / 'cleanup-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
shutil.copy2(output, public)
print(json.dumps(receipt,indent=2))
