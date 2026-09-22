"""Place an existing textured or rigged asset on the floor at a real height.

Only a uniform placement is applied. Topology, UVs, skin weights and materials
remain intact; a rig's rest joints move with its vertices. Placement is baked
for rigs so static bounds readers and skinning consumers agree on the height.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    source, output, report = (Path(value).resolve() for value in args[:3])
    height = float(args[3])
    if not 0.01 <= height <= 100:
        raise ValueError('Height must be 0.01 through 100 metres')
    if output.exists() or report.exists() or output.with_suffix('.blend').exists():
        raise RuntimeError('Preserve the earlier normalized asset')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if source.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(source))
    elif source.suffix.lower() == '.glb':
        bpy.ops.import_scene.gltf(filepath=str(source))
    else:
        raise ValueError('Expected a .blend or .glb asset')
    widgets = {bone.custom_shape for obj in bpy.context.scene.objects if obj.type == 'ARMATURE'
               for bone in obj.pose.bones if bone.custom_shape is not None}
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in widgets]
    if not meshes:
        raise ValueError('No mesh to normalize')
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    if hi.z - lo.z <= 1e-6:
        raise ValueError('No vertical extent')
    scale = height / (hi.z - lo.z)
    rigged = any(o.type == 'ARMATURE' for o in bpy.context.scene.objects)
    roots = [o for o in bpy.context.scene.objects if o.parent is None and o.type in {'EMPTY', 'MESH', 'ARMATURE'}]
    parent = bpy.data.objects.new('AssetPlacement', None)
    bpy.context.scene.collection.objects.link(parent)
    for obj in roots:
        world = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = world
    parent.scale = (scale, scale, scale)
    # Centre the footprint, not the character's pose or mesh topology.
    parent.location = Vector((0 if rigged else -(lo.x + hi.x) * .5,
                              0 if rigged else -(lo.y + hi.y) * .5, -lo.z)) * scale
    bpy.context.view_layer.update()
    if rigged:
        # glTF ignores a skinned mesh node's transform. Baking the same uniform
        # placement into the rest joints and mesh avoids double-scaled metadata
        # in consumers that also inspect the unposed POSITION accessor bounds.
        objects = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE' or o in meshes]
        placements = [(o, o.matrix_world.copy()) for o in objects]
        for obj, world in placements:
            obj.parent = None
            obj.matrix_world = world
        bpy.context.view_layer.update()
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        bpy.data.objects.remove(parent, do_unlink=True)
        bpy.context.view_layer.update()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.context.scene.objects:
        if obj in meshes or obj.type in {'ARMATURE', 'EMPTY'}:
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_yup=True,
                              export_animations=False, export_skins=True,
                              export_cameras=False, export_lights=False, use_selection=True)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = {
        'schema': 'reference-asset-compiler.browser-normalization.v1',
        'source': str(source.resolve()), 'source_sha256': digest(source),
        'output': str(output.resolve()), 'output_sha256': digest(output),
        'source_bounds_blender_m': [list(lo), list(hi)],
        'uniform_scale': scale, 'height_m': height,
        'anchor': 'floor-anatomical-origin' if rigged else 'floor-footprint-center',
        'dimensions_gltf_m': [(hi.x-lo.x)*scale, height, (hi.y-lo.y)*scale],
        'topology_uv_weights_materials_unchanged': True,
        'rig_placement_baked': rigged,
        'bones': sum(len(o.data.bones) for o in bpy.context.scene.objects if o.type == 'ARMATURE'),
        'triangles': sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes),
        'human_approved': False, 'production_grade': False,
    }
    report.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print('[NORMALIZE] Correct height and floor anchor; no platform shoes required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
