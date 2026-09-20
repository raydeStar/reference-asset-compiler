"""UV-wrap the visually reviewed demo derivatives; retain their exact parent hashes."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--revision', default='v1')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    asset = args.asset
    root = args.repo
    source = root / 'apps/lakeside-village/public/assets' / (asset + '.glb')
    dest = root / 'work' / ('lakeside-' + asset) / ('uv-' + args.revision)
    dest.mkdir(exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.data.validate(verbose=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.006, area_weight=0.3, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    output = dest / 'mesh.glb'
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', use_selection=True, export_materials='EXPORT')
    receipt = {'schema':'stillwater.uv-derivative.v1','asset':asset,'source':str(source),'source_sha256':sha(source),'output':str(output),'output_sha256':sha(output),'method':'Blender Smart UV Project, 66 degrees, 0.006 island margin','faces':len(obj.data.polygons),'uv_layers':len(obj.data.uv_layers),'human_visual_review':False,'reviewer':'codex','scope':'user-delegated Three.js scene demo; no production ledger approval claimed'}
    (dest / 'uv-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('STILLWATER_UV_OK ' + asset + '. The canvas is ready; the painter may enter.')


main()
