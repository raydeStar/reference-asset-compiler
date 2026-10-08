"""Fingerprint semantic native geometry, morphs, weights and bones, not timestamps."""
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def digest(values):
    array = np.round(np.asarray(values, dtype=np.float64), 7)
    return hashlib.sha256(array.astype('<f8').tobytes()).hexdigest()


def topology_digest(mesh):
    # BMesh may reorder faces or rotate their first loop without changing the
    # surface. Canonicalize those two representations, preserving winding/UVs.
    polygons = []
    for poly in mesh.polygons:
        loops = []
        for index in poly.loop_indices:
            uv = [round(value, 7) for layer in mesh.uv_layers for value in layer.data[index].uv]
            loops.append((mesh.loops[index].vertex_index, *uv))
        rotations = [loops[i:] + loops[:i] for i in range(len(loops))]
        polygons.append((poly.material_index, poly.use_smooth, min(rotations)))
    return hashlib.sha256(json.dumps(sorted(polygons), separators=(',', ':')).encode()).hexdigest()


def main():
    source, out = (Path(x).resolve() for x in sys.argv[sys.argv.index('--') + 1:][:2])
    bpy.ops.wm.open_mainfile(filepath=str(source))
    result = {'meshes': {}, 'rig': {}, 'groom': {}}
    for ob in bpy.context.scene.objects:
        if ob.type == 'MESH':
            data = {'vertices': digest([v.co[:] for v in ob.data.vertices]),
                    'topology_uv_material': topology_digest(ob.data),
                    'world_matrix': digest(ob.matrix_world),
                    'weights': digest([(v.index, g.group, g.weight) for v in ob.data.vertices for g in v.groups]),
                    'group_names': [g.name for g in ob.vertex_groups]}
            if ob.data.shape_keys:
                data['morphs'] = {k.name: digest([v.co[:] for v in k.data]) for k in ob.data.shape_keys.key_blocks}
            result['meshes'][ob.name] = data
        elif ob.type == 'ARMATURE':
            result['rig'] = {b.name: {'parent': b.parent.name if b.parent else None,
                'rest_matrix': digest(b.matrix_local), 'length': round(b.length, 7)} for b in ob.data.bones}
        elif ob.type == 'CURVES':
            result['groom'] = {'points': len(ob.data.points), 'curves': len(ob.data.curves),
                'position': digest([p.position[:] for p in ob.data.points]), 'parent_bone': ob.parent_bone,
                'world_matrix': digest(ob.matrix_world)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print('The fingerprints ignore the date on the suitcase, sir.')


if __name__ == '__main__':
    main()
