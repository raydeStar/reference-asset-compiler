"""Create lightweight, unapproved modeling previews from retained AI candidates.

Run with Blender --background --python prepare_preview.py -- --repo <repo>.
The immutable generation GLBs stay untouched. No texture or approval is authored.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--asset', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = args.repo
    asset = args.asset
    workspace = root / 'work' / ('lakeside-' + asset)
    source = workspace / 'candidates/hy3d-single-seed42-attempt001/candidate.glb'
    review = workspace / 'modeling-review-v1'
    review.mkdir(exist_ok=True)
    output = root / 'apps/lakeside-village/public/assets' / (asset + '.glb')
    if output.exists():
        raise RuntimeError('Preview already exists; preserve it and make an explicit new revision.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = asset
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    vertices = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lo = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
    hi = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
    center = (lo + hi) / 2
    span = max(hi - lo)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 600
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.world = bpy.data.worlds.new('Review world')
    scene.world.color = (0.16, 0.17, 0.16)
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.studiolight_rotate_z = 0.3
    scene.display.shading.color_type = 'SINGLE'
    scene.display.shading.single_color = (0.58, 0.58, 0.53)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.background_type = 'WORLD'
    camera_data = bpy.data.cameras.new('Review camera')
    camera = bpy.data.objects.new('Review camera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = span * 1.4
    views = {'front': (0,-4,1.7), 'three-quarter': (3,-4,2.4), 'side': (4,0,1.7), 'back': (0,4,1.7)}

    def render_views(prefix):
        result = []
        for name, direction in views.items():
            camera.location = center + Vector(direction).normalized() * span * 3
            camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
            path = review / (prefix + '-' + name + '.png')
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            result.append({'view': name, 'path': str(path), 'sha256': sha(path)})
        return result

    authority_views = render_views('authority')
    before = len(obj.data.polygons)
    targets = {'pine-tree': 12000, 'mossy-rock': 12000, 'timber-cabin': 65000, 'round-cottage': 60000, 'wooden-dock': 32000, 'rowboat': 35000, 'barrel-crates': 32000}
    modifier = obj.modifiers.new('Browser modeling preview', 'DECIMATE')
    modifier.ratio = min(1.0, targets[asset] / before)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    after = len(obj.data.polygons)
    obj.data.materials.clear()
    material = bpy.data.materials.new('Neutral modeling preview')
    material.diffuse_color = (0.58,0.58,0.53,1)
    obj.data.materials.append(material)
    preview_views = render_views('matcap')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', use_selection=True, export_materials='EXPORT')
    receipt = {'schema':'stillwater.modeling-preview.v1','asset':asset,'source':str(source),'source_sha256':sha(source),'output':str(output),'output_sha256':sha(output),'source_triangles':before,'preview_triangles':after,'method':'Blender decimate modeling review derivative','texture_generated':False,'human_visual_review':False,'approval':'pending','authority_views':authority_views,'preview_views':preview_views}
    (review / 'preview-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('STILLWATER_PREVIEW_OK ' + asset + ' ' + str(after) + ' triangles. The butler has preserved the original.')


main()
