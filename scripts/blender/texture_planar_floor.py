"""Apply an image-conditioned tile to the existing lowest upward-facing surface.

Geometry is never created or changed. This is downstream material/UV cleanup of
an acquired mesh, with explicit height, normal and tile-size selection limits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report', 'albedo'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--floor-height-fraction', type=float, default=.06)
    parser.add_argument('--minimum-up', type=float, default=.65)
    parser.add_argument('--tile-metres', type=float, default=3)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    source, output, report, albedo = (getattr(args, key).resolve() for key in ('source','output','report','albedo'))
    if not 0 < args.floor_height_fraction <= .2 or not .1 <= args.minimum_up <= 1 or not .01 <= args.tile_metres <= 100:
        raise ValueError('Floor selection and tile size are outside their supported ranges')
    if output.exists() or output.with_suffix('.blend').exists() or report.exists():
        raise RuntimeError('Preserve the previous material candidate')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if source.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if any(o.type == 'ARMATURE' for o in bpy.context.scene.objects):
        raise ValueError('This floor pass is only for a static architectural asset')
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    low, high = min(p.z for p in points), max(p.z for p in points)
    ceiling = low + (high-low)*args.floor_height_fraction
    selected = []
    for obj in meshes:
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for face in obj.data.polygons:
            centre = obj.matrix_world @ face.center
            normal = (normal_matrix @ face.normal).normalized()
            if centre.z <= ceiling and normal.z >= args.minimum_up:
                selected.append((obj, face))
    total = sum(len(o.data.polygons) for o in meshes)
    if not selected or len(selected) > total*.7:
        raise ValueError('Floor selection is empty or unexpectedly covers most of the model')
    material = bpy.data.materials.new('Reference flagstone floor')
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Roughness'].default_value = .93
    shader.inputs['Metallic'].default_value = 0
    texture = material.node_tree.nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.load(str(albedo))
    texture.extension = 'REPEAT'
    material.node_tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
    slots = {}
    for obj, face in selected:
        if obj.name not in slots:
            slots[obj.name] = len(obj.data.materials)
            obj.data.materials.append(material)
            if not obj.data.uv_layers:
                obj.data.uv_layers.new(name='UVMap')
        face.material_index = slots[obj.name]
        for index in face.loop_indices:
            point = obj.matrix_world @ obj.data.vertices[obj.data.loops[index].vertex_index].co
            obj.data.uv_layers.active.data[index].uv = (point.x/args.tile_metres, point.y/args.tile_metres)
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_animations=False,
                              export_cameras=False, export_lights=False)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    report.write_text(json.dumps({
        'schema':'reference-asset-compiler.planar-floor-material.v1',
        'source_sha256':digest(source), 'albedo_sha256':digest(albedo), 'output_sha256':digest(output),
        'selected_faces':len(selected), 'total_faces':total, 'ceiling_world_z':ceiling,
        'minimum_up':args.minimum_up, 'tile_metres':args.tile_metres,
        'geometry_unchanged':True, 'nonfloor_materials_and_uvs_unchanged':True,
        'human_approved':False, 'production_grade':False,
    }, indent=2), encoding='utf-8')
    print(f'[FLOOR] {len(selected)} acquired faces clothed in reference stone; no masonry invented.')


if __name__ == '__main__':
    main()
