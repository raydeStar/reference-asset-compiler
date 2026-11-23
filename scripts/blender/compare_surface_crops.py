"""Compare visible surface depth in matched repair close-ups, independent of the material.

blender -b --factory-startup --python-exit-code 1 --python compare_surface_crops.py --
    before.glb after.glb cameras.json new-output-directory

Each orthographic crop names a target, direction from target to camera, width in
metres, and optionally aspect (width/height). An alarm means inspect the marked
area; this is not a general geometry or visual acceptance gate.
"""
import hashlib
import json
import sys
from collections import deque
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def scene_tree(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(path))
    else:
        bpy.ops.import_scene.gltf(filepath=str(path))
    graph = bpy.context.evaluated_depsgraph_get()
    positions, faces = [], []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or obj.hide_render:
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        offset = len(positions)
        positions.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        faces.extend(tuple(i + offset for i in tri.vertices) for tri in mesh.loop_triangles)
        evaluated.to_mesh_clear()
    if not faces:
        raise ValueError(f'No renderable triangles in {path}')
    return BVHTree.FromPolygons(positions, faces, all_triangles=True)


def depths(tree, view, resolution):
    aim = Vector(view['direction']).normalized()
    up = Vector((0, 0, 1))
    right = up.cross(aim)
    if right.length < .001:
        raise ValueError('Crop direction must not be parallel to world Z')
    right.normalize()
    up = aim.cross(right)
    width, height = resolution, round(resolution / view.get('aspect', 1.0))
    step = view['width_m'] / width
    origin = Vector(view['target']) + aim * 4
    result = np.full((height, width), np.nan)
    for y in range(height):
        start = origin + up * ((y + .5 - height / 2) * step)
        for x in range(width):
            ray = start + right * ((x + .5 - width / 2) * step)
            hit = tree.ray_cast(ray, -aim, 8)
            if hit[0] is not None:
                result[y, x] = hit[3]
    return result


def largest_region(mask):
    remaining = {tuple(v) for v in np.argwhere(mask)}
    largest = 0
    while remaining:
        queue = deque([remaining.pop()])
        size = 0
        while queue:
            y, x = queue.popleft()
            size += 1
            for cell in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if cell in remaining:
                    remaining.remove(cell)
                    queue.append(cell)
        largest = max(largest, size)
    return largest


def compare(before, after, options, output):
    valid = np.isfinite(before)
    # Ignore silhouettes and real depth steps in the *original*, never smooth
    # the candidate's hole away. All eight neighbours must support the sample.
    interior = valid.copy()
    for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
        adjacent = np.roll(before, (dy, dx), (0, 1))
        interior &= np.isfinite(adjacent) & (np.abs(before - adjacent) < options['depth_step_mm'] / 1000)
    interior[[0, -1]] = False
    interior[:, [0, -1]] = False
    if not interior.any():
        raise ValueError(f'Empty reference crop: {output.stem}')
    loss = interior & (~np.isfinite(after) | (after - before > options['recession_mm'] / 1000))
    largest = largest_region(loss)
    rgba = np.ones((*before.shape, 4), dtype=np.float32)
    rgba[:, :, :3] = np.where(valid[:, :, None], .18, .032)
    rgba[loss] = (.96, .08, .025, 1)
    image = bpy.data.images.new(output.stem, width=before.shape[1], height=before.shape[0])
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(output)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    proportion = largest / int(interior.sum())
    return {'tested_pixels': int(interior.sum()), 'recessed_or_missing_pixels': int(loss.sum()),
            'largest_connected_pixels': largest, 'largest_fraction': proportion,
            'needs_inspection': proportion > options['max_connected_fraction'],
            'map': output.name, 'map_sha256': digest(output)}


def main():
    before, after, cameras, output = (Path(a).resolve() for a in sys.argv[sys.argv.index('--') + 1:])
    options = json.loads(cameras.read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    original, changed = scene_tree(before), scene_tree(after)
    rows = {}
    for name, view in options['views'].items():
        if not name or Path(name).name != name or name in ('.', '..'):
            raise ValueError('Crop name must be a filename stem')
        a = depths(original, view, options['resolution'])
        b = depths(changed, view, options['resolution'])
        rows[name] = compare(a, b, options, output / (name + '.png'))
    receipt = {'inputs': {str(p): digest(p) for p in (before, after, cameras, Path(__file__))},
               'blender': bpy.app.version_string, 'views': rows,
               'needs_inspection': any(v['needs_inspection'] for v in rows.values())}
    (output / 'report.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print('CROP_DEPTH:', {k: round(v['largest_fraction'], 4) for k, v in rows.items()},
          '— a tidy atlas cannot fill a hole.')
    return 1 if receipt['needs_inspection'] else 0


if __name__ == '__main__':
    sys.exit(main())
