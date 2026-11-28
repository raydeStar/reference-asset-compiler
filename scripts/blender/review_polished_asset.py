"""CPU fixed-view review, optional diagnostic poses, and packed transport-native copy."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--textures', type=Path, required=True)
    args = parser.parse_args(argv)
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    cfg = json.loads(args.textures.read_text(encoding='utf-8-sig'))
    if cfg.get('schema') != 'reference-asset-compiler.polish-review-recipe.v1' or cfg.get('source_sha256') != sha(args.source):
        raise ValueError('Review settings must bind the current acquired candidate')
    if args.output.exists() or args.report.exists() or args.source.resolve() == args.output.resolve():
        raise ValueError('Keep earlier reviews; choose distinct new paths')
    size, samples = cfg.get('resolution', 768), cfg.get('samples', 24)
    if not 128 <= size <= 2048 or not 2 <= samples <= 256:
        raise ValueError('Review resolution/samples are outside the bounded CPU range')
    directory = args.output.parent/'views'
    directory.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.source.resolve()))
    scene = bpy.context.scene
    rigs = [o for o in scene.objects if o.type == 'ARMATURE']
    display_shapes = {bone.custom_shape for rig in rigs for bone in rig.pose.bones if bone.custom_shape}
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render
              and o.visible_get() and o not in display_shapes]
    if not meshes:
        raise ValueError('No renderable geometry')
    clip = cfg.get('clip')
    if clip:
        matched = []
        for rig in rigs:
            if rig.animation_data:
                rig.animation_data.action = None
                for track in rig.animation_data.nla_tracks:
                    track.mute, track.is_solo = track.name != clip, False
                    if not track.mute:
                        matched.append(track)
        if len(matched) != 1:
            raise ValueError('Review clip must match exactly one imported track')
    else:
        for rig in rigs:
            rig.animation_data_clear()
            for bone in rig.pose.bones:
                bone.matrix_basis.identity()
    scene.frame_set(cfg.get('frame', 0))
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(v) for o in meshes for v in o.bound_box]
    low, high = [Vector([f(v[i] for v in corners) for i in range(3)]) for f in (min, max)]
    center, span = (low + high) / 2, max(high-low)*1.10
    if not math.isfinite(span) or span <= 0:
        raise ValueError('Cannot frame a zero-sized asset')
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.seed = 231
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = cfg.get('threads', 12)
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.world = bpy.data.worlds.new('RAC neutral studio')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.14, .16, .18, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .5
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.hide_render = True
    lights = []
    for name, location, power, width in [
        ('Key', (-1, -1.8, 1.3), 100, 1), ('Fill', (1.25, -.5, .7), 45, 1.25),
        ('Rim', (.5, 1, 1.1), 85, .7),
    ]:
        light = bpy.data.lights.new(name, 'AREA')
        light.energy, light.size = power*span**2, width*span
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(location)*span
        obj.rotation_euler = (center-obj.location).to_track_quat('-Z', 'Y').to_euler()
        lights.append(obj)
    camera = bpy.data.objects.new('RAC review camera', bpy.data.cameras.new('RAC review camera'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = 'ORTHO'
    camera.data.clip_start, camera.data.clip_end = span*.001, span*20
    defaults = [('front', [0, 0, 1]), ('quarter', [-.65, 0, 1]),
                ('side', [-1, 0, 0]), ('back', [0, 0, -1])]
    views = [dict(name=n, axis=a) for n, a in defaults] + cfg.get('closeups', [])
    names = [v['name'] for v in views]
    if len(views) > 24 or len(names) != len(set(names)) or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', n) for n in names):
        raise ValueError('Review cameras need unique safe names')

    def z_up(vec):
        return Vector((vec[0], -vec[2], vec[1]))

    records = []
    def render(view, prefix=''):
        target = z_up(view['center']) if 'center' in view else center
        axis = z_up(view['axis'])
        if axis.length < 1e-9:
            raise ValueError('Review camera axis cannot be zero')
        camera.location = target + axis.normalized()*span*4
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.ortho_scale = view.get('width', span)
        name = prefix+view['name']
        scene.render.filepath = str((directory/(name+'.png')).resolve())
        bpy.ops.render.render(write_still=True)
        records.append(dict(name=name, sha256=sha(directory/(name+'.png'))))

    for view in views:
        render(view)
    if cfg.get('moving_light', True):
        original = lights[0].location.copy()
        for n, x in [('left', -1.2), ('center', 0), ('right', 1.2)]:
            lights[0].location = center + Vector((x, -1.8, 1.3))*span
            lights[0].rotation_euler = (center-lights[0].location).to_track_quat('-Z', 'Y').to_euler()
            render(views[1], 'light-'+n+'-')
        lights[0].location = original
        lights[0].rotation_euler = (center-original).to_track_quat('-Z', 'Y').to_euler()
    # Save the held review state before diagnostic rotations; native authority stays untouched.
    bpy.ops.file.pack_all()
    images = [i for i in bpy.data.images if i.source == 'FILE' and i.users]
    if not all(i.packed_file for i in images):
        raise ValueError('Every used file image must be packed')
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    poses = cfg.get('poses', [])
    if poses:
        if len(rigs) != 1 or len(poses) > 12:
            raise ValueError('Diagnostic poses require one rig and at most twelve cases')
        rig = rigs[0]
        baseline = {b.name:b.matrix_basis.copy() for b in rig.pose.bones}
        rig.animation_data_clear()
        for pose in poses:
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', pose['name']):
                raise ValueError('Invalid pose name')
            for bone in rig.pose.bones:
                bone.matrix_basis = baseline[bone.name]
            bpy.context.view_layer.update()
            for rotation in pose.get('rotations', []):
                bone = rig.pose.bones[rotation['bone']]
                axis = rig.matrix_world.to_3x3().inverted() @ z_up(rotation['axis'])
                desired = Quaternion(axis.normalized(), math.radians(rotation['degrees'])) @ bone.matrix.to_quaternion()
                basis = bone.bone.matrix_local
                if bone.parent:
                    basis = bone.parent.matrix @ bone.parent.bone.matrix_local.inverted() @ basis
                bone.rotation_mode = 'QUATERNION'
                bone.rotation_quaternion = basis.to_quaternion().inverted() @ desired
                bpy.context.view_layer.update()
            for view in views:
                if view['name'] in pose.get('views', ['front', 'quarter']):
                    render(view, pose['name']+'-')
    bpy.ops.wm.open_mainfile(filepath=str(args.output.resolve()))
    packed = [i for i in bpy.data.images if i.source == 'FILE' and i.users]
    if len(packed) != len(images) or not all(i.packed_file for i in packed):
        raise ValueError('Packed native reopen failed')
    markup = ''.join(f'<figure><figcaption>{html.escape(r["name"])}</figcaption><img src="views/{r["name"]}.png"></figure>' for r in records)
    (args.output.parent/'Review.html').write_text('<!doctype html><meta charset="utf-8"><title>RAC polish review</title>'
        '<style>body{background:#182026;color:#eee;font:16px system-ui}main{display:flex;flex-wrap:wrap}figure{width:30%;margin:1%}img{width:100%}</style>'
        '<h1>RAC polish review</h1><p>Fixed cameras, moving light and declared diagnostic poses. Visual acceptance pending.</p><main>'+markup+'</main>', encoding='utf8')
    receipt = dict(schema='reference-asset-compiler.polish-review.v1', source_sha256=sha(args.source),
        output_sha256=sha(args.output), recipe_sha256=sha(args.textures), blender=bpy.app.version_string,
        views=records, packed_images=len(packed), all_images_packed_after_reopen=True,
        clip=clip, diagnostic_poses=poses, production_ready=False, visual_acceptance='pending',
        native_kind='Packed GLB-import review copy; original authored skeleton rest frames are not replaced')
    args.report.write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print('POLISH_REVIEW_COMPLETE -- four sides to every story, and every texture packed.')


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--')+1:])
