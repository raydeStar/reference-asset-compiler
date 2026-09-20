"""Fixed-view evidence for an existing mesh; never changes the imported authority."""
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


parser = argparse.ArgumentParser()
parser.add_argument('--mesh', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--beauty', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.out.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(args.mesh.resolve()))
points = [obj.matrix_world @ Vector(corner) for obj in bpy.context.scene.objects if obj.type == 'MESH' for corner in obj.bound_box]
lo = Vector(tuple(min(point[i] for point in points) for i in range(3)))
hi = Vector(tuple(max(point[i] for point in points) for i in range(3)))
center = (lo + hi) / 2
span = max(hi - lo)
scene = bpy.context.scene
scene.render.resolution_x = scene.render.resolution_y = 600
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world = bpy.data.worlds.new('Review world')
scene.world.color = (0.18,0.18,0.16)
if args.beauty:
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.55,0.58,0.52,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5
    for index, (position,power,size) in enumerate([((-3,-4,5),500,4),((3,-1,3),200,3),((1,3,4),350,3)]):
        light_data = bpy.data.lights.new('Studio '+str(index),'AREA')
        light_data.energy = power * span * span
        light_data.shape = 'DISK'
        light_data.size = size * span
        light = bpy.data.objects.new(light_data.name, light_data)
        scene.collection.objects.link(light)
        light.location = center + Vector(position) * span
        light.rotation_euler = (center-light.location).to_track_quat('-Z','Y').to_euler()
else:
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'SINGLE'
    scene.display.shading.single_color = (0.58,0.58,0.53)
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.background_type = 'WORLD'
camera_data = bpy.data.cameras.new('Fixed review camera')
camera_data.type = 'ORTHO'
camera_data.ortho_scale = span * 1.4
camera = bpy.data.objects.new('Fixed review camera',camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
for name, direction in {'front':(0,-4,1.7),'three-quarter':(3,-4,2.4),'side':(4,0,1.7),'back':(0,4,1.7)}.items():
    camera.location = center + Vector(direction).normalized() * span * 3
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath = str((args.out / (name+'.png')).resolve())
    bpy.ops.render.render(write_still=True)
print('STILLWATER_VIEWS_OK. Four mirrors, fewer places for a flaw to hide.')
