"""Extract editable modules from an acquired static mesh without redrawing it.

Usage: blender -b --factory-startup --python-exit-code 1 --python SCRIPT --
    source.blend recipe.json fresh-output-directory

Recipes pin the source SHA256 and assign polygons by world-space centroid.
Regions are ordered: the first matching box owns the whole polygon. The
remainder is exported too, so every source polygon remains accounted for.
Cuts are open boundaries, not watertight remeshing or collision certification.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import bpy
from mathutils import Vector


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_recipe(path, source):
    recipe = json.loads(path.read_text(encoding='utf-8-sig'))
    if recipe.get('source_sha256') != digest(source):
        raise ValueError('Source hash differs; measure a new recipe instead of moving the goalposts')
    if not recipe.get('parts'):
        raise ValueError('At least one measured region is required')
    names = [part['name'] for part in recipe['parts']] + [recipe['remainder']]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) for name in names):
        raise ValueError('Part names must be unique safe lowercase filenames')
    for part in recipe['parts']:
        bounds = part['bounds']
        if (len(bounds) != 2 or any(len(row) != 3 for row in bounds)
                or not all(math.isfinite(v) for row in bounds for v in row)
                or any(bounds[0][i] >= bounds[1][i] for i in range(3))):
            raise ValueError('Each region needs finite increasing XYZ bounds')
    return recipe, names


def owner(point, recipe):
    for part in recipe['parts']:
        low, high = part['bounds']
        if all(low[i] <= point[i] <= high[i] for i in range(3)):
            return part['name']
    return recipe['remainder']


def export_part(name, records, output):
    if not records:
        raise ValueError('Empty measured region: ' + name)
    points = [record['positions'][i] for record in records for i in range(len(record['positions']))]
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    pivot = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    vertices, faces, uvs, normals, material_indices, materials = [], [], [], [], [], []
    for record in records:
        start = len(vertices)
        vertices.extend(tuple(p - pivot) for p in record['positions'])
        faces.append(tuple(range(start, len(vertices))))
        uvs.extend(record['uv'])
        normals.extend(record['normals'])
        material = record['material']
        if material not in materials:
            materials.append(material)
        material_indices.append(materials.index(material))
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    for material in materials:
        data.materials.append(material)
    uv = data.uv_layers.new(name='UVMap')
    for loop, value in zip(uv.data, uvs, strict=True):
        loop.uv = value
    for polygon, index in zip(data.polygons, material_indices, strict=True):
        polygon.material_index = index
        polygon.use_smooth = True
    data.normals_split_custom_set(normals)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = output / (name + '.glb')
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', export_yup=True,
                              export_animations=False, use_selection=True)
    # Verify the constructed module against source corners before recording
    # it. Downstream import/round-trip inspection remains a separate gate.
    source_corners = sum(len(record['positions']) for record in records)
    position_error = max((data.vertices[index].co + pivot - expected).length
                         for polygon, record in zip(data.polygons, records, strict=True)
                         for index, expected in zip(polygon.vertices, record['positions'], strict=True))
    uv_error = max((uv.data[index].uv - Vector(expected)).length
                   for index, expected in enumerate(uvs))
    if position_error > 0.00001 or uv_error > 0.000001:
        raise ValueError('Part placement changed source polygon coordinates')
    obj.location = pivot
    return {
        'name': name, 'file': path.name, 'sha256': digest(path),
        'polygons': len(records), 'source_corners': source_corners,
        'triangles': sum(len(face) - 2 for face in faces),
        'position_gltf_m': [pivot.x, pivot.z, -pivot.y],
        'bounds_blender_m': [list(low), list(high)],
        'max_position_error_m': position_error, 'max_uv_error': uv_error,
        'source_polygon_ids': [record['id'] for record in records],
    }


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    source, recipe_path, output = (Path(arg).resolve() for arg in args)
    if output.exists():
        raise ValueError('Output exists; keep the previous partition evidence')
    recipe, names = load_recipe(recipe_path, source)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    if any(obj.type == 'ARMATURE' for obj in bpy.context.scene.objects):
        raise ValueError('This partitioner only supports static sources')
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    groups = {name: [] for name in names}
    count = 0
    for obj in meshes:
        mesh = obj.data
        if obj.modifiers or mesh.shape_keys or mesh.color_attributes or obj.matrix_world.determinant() <= 0:
            raise ValueError('Apply modifiers and use a static positive-transform source without shape keys or colour attributes')
        if len(mesh.uv_layers) != 1:
            raise ValueError('Expected exactly one UV channel; refuse to discard extra channels')
        if not mesh.materials or any(m is None for m in mesh.materials):
            raise ValueError('Source needs valid assigned materials')
        if any(len(poly.vertices) != 3 for poly in mesh.polygons):
            raise ValueError('Expected an already triangulated acquisition derivative')
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for polygon in mesh.polygons:
            positions = [obj.matrix_world @ mesh.vertices[index].co for index in polygon.vertices]
            center = sum(positions, Vector()) / len(positions)
            record = {'id': count, 'positions': positions,
                      'uv': [tuple(mesh.uv_layers[0].data[i].uv) for i in polygon.loop_indices],
                      'normals': [tuple((normal_matrix @ mesh.corner_normals[i].vector).normalized())
                                  for i in polygon.loop_indices],
                      'material': mesh.materials[polygon.material_index]}
            groups[owner(center, recipe)].append(record)
            count += 1
    if any(not records for records in groups.values()):
        raise ValueError('Recipe contains an empty region; inspect its measured bounds')
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    output.mkdir(parents=True)
    parts = [export_part(name, groups[name], output) for name in names]
    ids = [index for part in parts for index in part['source_polygon_ids']]
    if sorted(ids) != list(range(count)):
        raise ValueError('Partition lost or duplicated source polygons')
    bpy.ops.file.pack_all()
    # Native objects retain local pivots and recompose the source placement.
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'modules.blend'))
    report = {'schema': 'reference-asset-compiler.static-partition.v1',
              'source_sha256': digest(source), 'recipe_sha256': digest(recipe_path),
              'script_sha256': digest(Path(__file__)), 'source_polygons': count,
              'all_source_polygons_accounted_for_once': True, 'parts': parts,
              'uv_materials_preserved': True, 'new_geometry_generated': False,
              'open_cut_boundaries': True, 'human_approved': False, 'production_grade': False}
    (output / 'partition.json').write_text(json.dumps(report, indent=2) + '\n')
    print('[PARTITION] Every polygon has one home; the tavern has acquired movable walls.')


if __name__ == '__main__':
    main()
