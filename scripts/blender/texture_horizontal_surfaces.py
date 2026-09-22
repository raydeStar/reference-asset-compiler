"""Map a reference-conditioned albedo onto existing horizontal static faces.

This downstream repair changes selected UV corners and materials only. It does
not invent geometry or infer a material from a prompt. Review and retain the
image authority separately; the receipt binds its actual bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_signature(meshes):
    data = [(o.name, [list(row) for row in o.matrix_world],
             [list(v.co) for v in o.data.vertices],
             [list(p.vertices) for p in o.data.polygons]) for o in meshes]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'output', 'report', 'albedo'):
        parser.add_argument(key, type=Path)
    parser.add_argument('--minimum-up', type=float, default=.7)
    parser.add_argument('--include-down', action='store_true')
    parser.add_argument('--tile-metres', type=float, default=1)
    parser.add_argument('--roughness', type=float, default=.78)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    source, output, report, albedo = (getattr(args, key).resolve() for key in ('source', 'output', 'report', 'albedo'))
    if not .5 <= args.minimum_up <= 1 or not .01 <= args.tile_metres <= 100 or not 0 <= args.roughness <= 1:
        raise ValueError('Normal threshold, tile size or roughness is outside the supported range')
    if source.suffix.lower() not in ('.blend', '.glb') or output.suffix.lower() != '.glb':
        raise ValueError('Expected a static .blend/.glb source and .glb output')
    for path in (output, output.with_suffix('.blend'), report):
        if path.exists():
            raise RuntimeError('Preserve the existing candidate: '+str(path))
    if not source.is_file() or not albedo.is_file():
        raise ValueError('Source mesh and albedo must exist')
    source_hash, albedo_hash = digest(source), digest(albedo)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if source.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        bpy.ops.import_scene.gltf(filepath=str(source))
    if any(o.type == 'ARMATURE' for o in bpy.context.scene.objects):
        raise ValueError('Horizontal material repair is only for static assets')
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    before_geometry = geometry_signature(meshes)
    selected, untouched = [], []
    for obj in meshes:
        if not obj.data.uv_layers.active:
            raise ValueError('The acquired model must already have UVs')
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for face in obj.data.polygons:
            up = (normal_matrix @ face.normal).normalized().z
            if (abs(up) if args.include_down else up) >= args.minimum_up:
                selected.append((obj, face))
            else:
                untouched.append((obj, face, face.material_index,
                                  [tuple(obj.data.uv_layers.active.data[n].uv) for n in face.loop_indices]))
    if not selected or len(selected) > .8*(len(selected)+len(untouched)):
        raise ValueError('Horizontal selection is empty or unexpectedly covers most faces')
    material = bpy.data.materials.new('Reference horizontal surface')
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Roughness'].default_value = args.roughness
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
        face.material_index = slots[obj.name]
        for n in face.loop_indices:
            point = obj.matrix_world @ obj.data.vertices[obj.data.loops[n].vertex_index].co
            obj.data.uv_layers.active.data[n].uv = (point.x/args.tile_metres, point.y/args.tile_metres)
    if geometry_signature(meshes) != before_geometry:
        raise RuntimeError('Material repair unexpectedly altered geometry')
    for obj, face, slot, uvs in untouched:
        if face.material_index != slot or [tuple(obj.data.uv_layers.active.data[n].uv) for n in face.loop_indices] != uvs:
            raise RuntimeError('Material repair unexpectedly altered an unselected face')
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_animations=False,
                              export_cameras=False, export_lights=False)
    report.write_text(json.dumps({
        'schema':'reference-asset-compiler.horizontal-material.v1',
        'source_sha256':source_hash, 'albedo_sha256':albedo_hash, 'output_sha256':digest(output),
        'selected_faces':len(selected), 'untouched_faces':len(untouched),
        'minimum_up':args.minimum_up, 'include_down':args.include_down,
        'tile_metres':args.tile_metres, 'roughness':args.roughness,
        'geometry_signature':before_geometry, 'geometry_unchanged':True,
        'unselected_uvs_and_material_slots_unchanged':True,
        'human_approved':False, 'production_grade':False,
    }, indent=2), encoding='utf-8')
    print(f'[SURFACE] {len(selected)} existing faces dressed; no new furniture smuggled in.')


if __name__ == '__main__':
    main()
