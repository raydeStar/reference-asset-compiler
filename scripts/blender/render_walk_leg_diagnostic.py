# SPDX-License-Identifier: MIT
"""CPU clay close-ups and projected joint coordinates for a specific GLB walk."""
import argparse
import json
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asset', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.asset, args.out = args.asset.resolve(), args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.gltf(filepath=str(args.asset))
    rig = next(o for o in scene.objects if o.type == 'ARMATURE')
    for track in rig.animation_data.nla_tracks:
        track.mute = True
    action = bpy.data.actions.get('MF_Unarmed_Walk_Fwd')
    assert action is not None
    rig.animation_data.action = action
    clay = bpy.data.materials.new('DiagnosticClay')
    clay.diffuse_color = (.50, .56, .62, 1)
    clay.use_nodes = True
    clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.50,.56,.62,1)
    clay.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .75
    scene.view_layers[0].material_override = clay
    camera = bpy.data.objects.new('LegReview', bpy.data.cameras.new('LegReview'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type, camera.data.ortho_scale = 'ORTHO', 1.15
    for name, position, energy in [('key',(3,-4,4),500),('fill',(-3,-2,2),300)]:
        light = bpy.data.objects.new(name,bpy.data.lights.new(name,'AREA'))
        scene.collection.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((0,0,.6))-light.location).to_track_quat('-Z','Y').to_euler()
        light.data.energy, light.data.size = energy, 3
    scene.world = bpy.data.worlds.new('ReviewBackground')
    scene.world.color = (.15,.15,.15)
    scene.render.engine = 'CYCLES'
    scene.cycles.device, scene.cycles.samples = 'CPU', 16
    scene.cycles.use_denoising = True
    scene.render.threads_mode, scene.render.threads = 'FIXED', 8
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 520, 620, 100
    result = []
    for f in (0, 10, 20, 30):
        scene.frame_set(f)
        for view, xyz in [('front',(0,-5,.6)),('side',(5,0,.6))]:
            camera.location = xyz
            camera.rotation_euler = (Vector((0,0,.6))-camera.location).to_track_quat('-Z','Y').to_euler()
            bpy.context.view_layer.update()
            path = args.out/f'{view}-{f:02}.png'
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            points = {}
            for side in 'lr':
                for name in ['thigh','calf','foot','ball']:
                    n = f'{name}_{side}'
                    pixel = world_to_camera_view(scene,camera,rig.matrix_world @ rig.pose.bones[n].head)
                    points[n] = [pixel.x*520,(1-pixel.y)*620]
            result.append({'frame':f,'view':view,'path':str(path.resolve()),'joints_px':points})
    (args.out/'projections.json').write_text(json.dumps(result,indent=2))
    print('LEG_VIEWS_COMPLETE -- no trouser seam has been permitted to conceal a joint.')


if __name__ == '__main__':
    main()
