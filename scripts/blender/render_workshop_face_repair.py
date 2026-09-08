"""Matched CPU face views; true unlit inputs for geometry-bound AI repair."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import import_asset, mesh_bounds, setup_world, add_key_lights, place_camera, normalize_pbr_inputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base-color', type=Path)
    parser.add_argument('--albedo-only', action='store_true')
    parser.add_argument('--clay-only', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise RuntimeError('Keep previous evidence; choose a new directory')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(source)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    low, high = mesh_bounds(meshes)
    size, center = high-low, (high+low)/2
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 12
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    setup_world()
    add_key_lights(center, size.z*.5)
    normalize_pbr_inputs(meshes)
    materials = {slot.material for o in meshes for slot in o.material_slots if slot.material}
    if args.clay_only:
        clay = bpy.data.materials.new('DiagnosticClay')
        clay.use_nodes = True
        bsdf = clay.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (.45,.45,.45,1)
        bsdf.inputs['Roughness'].default_value = .85
        scene.view_layers[0].material_override = clay
    if args.base_color:
        image = bpy.data.images.load(str(args.base_color.resolve()), check_existing=True)
        image.colorspace_settings.name = 'sRGB'
        for mat in materials:
            bsdf = mat.node_tree.nodes.get('Principled BSDF')
            tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
            tex.image = image
            mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    output.mkdir(parents=True)
    frames = []
    for mode in (['clay'] if args.clay_only else ['albedo'] if args.albedo_only else ['beauty', 'albedo']):
        scene.view_settings.exposure = 0 if mode == 'albedo' else -1.5
        if mode == 'albedo':
            for mat in materials:
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                base = nodes.get('Principled BSDF').inputs['Base Color']
                emission = nodes.new('ShaderNodeEmission')
                if base.is_linked:
                    links.new(base.links[0].from_socket, emission.inputs['Color'])
                else:
                    emission.inputs['Color'].default_value = base.default_value
                links.new(emission.outputs[0], nodes.get('Material Output').inputs['Surface'])
        for name, angle in [('front',0),('left',40),('right',-40),('side',90),('opposite',-90)]:
            place_camera(Vector((center.x,center.y,low.z+size.z*.91)),size.z*.24,angle)
            path = output/f'{mode}-{name}.png'
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            frames.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'exposure':scene.view_settings.exposure})
    (output/'review.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'base_color_override':str(args.base_color),'geometry_saved_or_modified':False,'frames':frames},indent=2))
    print('FACE_REPAIR_VIEWS_READY -- even the unflattering side gets a hearing.')


if __name__ == '__main__':
    main()
