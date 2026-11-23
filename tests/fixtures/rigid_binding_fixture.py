"""Real-Blender regression for immutable multi-part, one-hot rig binding."""
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

root, folder = (Path(p) for p in sys.argv[sys.argv.index('--') + 1:])
sys.path.insert(0, str(root / 'scripts/blender'))
import rig_from_landmarks as runner

bpy.ops.wm.read_factory_settings(use_empty=True)
for name, z in [('Body', .4), ('Head', 1.0)]:
    bpy.ops.mesh.primitive_cube_add(size=.3, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
source = folder / 'source.fbx'
bpy.ops.export_scene.fbx(filepath=str(source), add_leaf_bones=False)
digest = hashlib.sha256(source.read_bytes()).hexdigest()
profile = {'profile_id': 'rigid_fixture', 'root_bone': 'root',
           'required_bones': ['root', 'head', 'finger'], 'optional_bones': [],
           'max_influences': 4, 'rigid_part_binding': {'payload_sha256': digest,
                                                       'parts': {'Body': 'root', 'Head': 'head'}}}
# A real root is deliberately non-deforming, so bind the body to a pelvis instead.
profile['required_bones'].append('pelvis')
profile['rigid_part_binding']['parts']['Body'] = 'pelvis'
landmarks = {'skeleton_profile': 'rigid_fixture', 'payload_fbx_sha256': digest,
             'joints': {'root': [0, 0, 0], 'pelvis': [0, 0, .4], 'head': [0, 0, .85],
                        'top': [0, 0, 1.15], 'finger': [.2, 0, 1], 'tip': [.3, 0, 1]},
             'bones': {'root': {'head': 'root', 'tail': 'pelvis', 'deform': False},
                       'pelvis': {'head': 'pelvis', 'tail': 'head', 'parent': 'root'},
                       'head': {'head': 'head', 'tail': 'top', 'parent': 'pelvis'},
                       'finger': {'head': 'finger', 'tail': 'tip', 'parent': 'head', 'deform': False}}}
lm = folder / 'landmarks.json'
pf = folder / 'profile.json'
lm.write_text(json.dumps(landmarks))
pf.write_text(json.dumps(profile))


def invoke(label):
    sys.argv = ['test', '--', str(source), str(lm), str(pf), str(folder / (label + '.fbx')),
                str(folder / (label + '.json'))]
    return runner.main()


def snapshot():
    result = {}
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            result[obj.name] = {'points': np.array([obj.matrix_world @ v.co for v in obj.data.vertices]),
                                'polys': [tuple(p.vertices) for p in obj.data.polygons],
                                'uv': {u.name: np.array([tuple(v.uv) for v in u.data]) for u in obj.data.uv_layers}}
    return result


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source))
before = snapshot()
invoke('valid')
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
assert not rig.data.bones['finger'].use_deform
for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
    assert len(obj.vertex_groups) == 1
    assert all(len(v.groups) == 1 and v.groups[0].weight == 1 for v in obj.data.vertices)
rig.pose.bones['head'].rotation_mode = 'XYZ'
rig.pose.bones['head'].rotation_euler.z = math.radians(65)
bpy.context.view_layer.update()
head = bpy.data.objects['Head']
evaluated = head.evaluated_get(bpy.context.evaluated_depsgraph_get())
posed = np.array([evaluated.matrix_world @ v.co for v in evaluated.data.vertices])
rest = before['Head']['points']
assert np.max(np.abs(np.linalg.norm(posed[:, None] - posed[None, :], axis=2) -
                     np.linalg.norm(rest[:, None] - rest[None, :], axis=2))) < 1e-6
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(folder / 'valid.fbx'))
after = snapshot()
assert set(before) == set(after)
for name in before:
    assert np.max(np.abs(before[name]['points'] - after[name]['points'])) < 1e-6
    assert before[name]['polys'] == after[name]['polys']
    assert set(before[name]['uv']) == set(after[name]['uv'])
    for uv in before[name]['uv']:
        assert np.max(np.abs(before[name]['uv'][uv] - after[name]['uv'][uv])) < 1e-7
    obj = bpy.data.objects[name]
    assert all(len(v.groups) == 1 and obj.vertex_groups[v.groups[0].group].name != 'finger'
               for v in obj.data.vertices)
for label, mutation, fragment in [
    ('bad_hash', lambda c: c.update(payload_sha256='wrong'), 'not bound'),
    ('missing_part', lambda c: c['parts'].pop('Head'), 'every mesh'),
    ('nondeform_owner', lambda c: c['parts'].update(Head='finger'), 'deform bones')]:
    candidate = json.loads(json.dumps(profile))
    mutation(candidate['rigid_part_binding'])
    pf.write_text(json.dumps(candidate))
    try:
        invoke(label)
    except RuntimeError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f'{label} was not rejected')
print('RIGID_BINDING_FIXTURE_OK: UVs, parts, rigid motion, FBX round-trip and rejection paths; all the screws remain accounted for.')
