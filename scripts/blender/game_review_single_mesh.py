"""Game review step 1: join a polished character GLB into the one mesh the landmark rig takes.

blender -b --factory-startup --python game_review_single_mesh.py -- <job.json>

glTF rest morph weights (a lid pose, say) do not survive FBX into Unreal, where every morph rests at 0. So each
mesh's rest mix is baked into its basis and the same offset is added to every key, which keeps every morph's delta
exactly as authored; the weights are then 0. Morphs named in the job's bake_morphs are baked at the given weight and
removed (a face variant picked in review). Meshes are joined with transforms applied; Blender gives keyless meshes
basis-only copies of the shared keys, so face morphs survive the join by name. Then the face fixes Mark passed on
Remora: the upper-lid skin a blink uncovers is repainted from the lid skin around it (clear_closed_lids.py; report
'closed_lids'), and the teeth are seated under the lips with the tongue riding the jaw (fit_mouth.py; report 'mouth').
Each runs by default ("auto": skipped with its reason when the head lacks what it needs), is required with true and
off with false.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clear_closed_lids import clear_closed_lids  # noqa: E402
from fit_mouth import fit_mouth  # noqa: E402

job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
dst = Path(job['paths']['single'])
dst.parent.mkdir(parents=True, exist_ok=True)
bake = job.get('bake_morphs', {})
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=job['source'])
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
report = {'source': job['source'], 'source_sha256': job['source_sha256'], 'meshes': {}, 'baked_morphs': {}}


def coords(block, n):
    out = np.empty(n * 3)
    block.data.foreach_get('co', out)
    return out


for o in meshes:
    keys = o.data.shape_keys
    entry = {'vertices': len(o.data.vertices), 'keys': 0, 'baked_rest': {}}
    if keys:
        blocks = keys.key_blocks
        entry['keys'] = len(blocks) - 1
        n = len(o.data.vertices)
        basis = coords(blocks[0], n)
        mix = basis.copy()
        for kb in blocks[1:]:
            weight = bake.get(kb.name, kb.value)
            if weight:
                mix += weight * (coords(kb, n) - basis)
                entry['baked_rest'][kb.name] = round(float(weight), 4)
        offset = mix - basis
        if np.any(offset):
            for kb in blocks:
                kb.data.foreach_set('co', coords(kb, n) + offset)
            for kb in blocks[1:]:
                kb.value = 0.0
            o.data.vertices.foreach_set('co', mix)
            o.data.update()
        for name in bake:
            if name in blocks:
                o.shape_key_remove(blocks[name])
                report['baked_morphs'].setdefault(name, []).append(o.name)
    report['meshes'][o.name] = entry
missing = sorted(set(bake) - set(report['baked_morphs']))
assert not missing, f'bake_morphs not found on any mesh: {missing}'
for o in meshes:
    o.select_set(True)
body = max(meshes, key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = body
for o in meshes:                       # shared mesh data cannot take an applied transform
    if o.data.users > 1:
        o.data = o.data.copy()
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
joined = bpy.context.view_layer.objects.active
joined.name = joined.data.name = job['name']
for o in list(bpy.context.scene.objects):      # the empty parents the glTF import created
    if o.type != 'MESH':
        bpy.data.objects.remove(o)


def face_fix(label, setting, run, done_key):
    """Run a face fix: required (true) must succeed, auto records why it did not, false skips it."""
    if setting is False:
        report[label] = {done_key: False, 'reason': 'off in the recipe'}
        return
    report[label] = run()
    if setting is True:
        assert report[label][done_key], f"{label} (required): {report[label].get('reason')}"


lids = dict(job.get('closed_lids', {'clear': 'auto'}))
face_fix('closed_lids', lids.pop('clear', 'auto'),
         lambda: clear_closed_lids(joined, job['skin_materials'], lids), 'cleared')
mouth = dict(job.get('mouth', {'fit': 'auto'}))
face_fix('mouth', mouth.pop('fit', 'auto'), lambda: fit_mouth(joined, job['skin_materials'], mouth), 'fitted')
z = np.array([v.co.z for v in joined.data.vertices])
report['joined'] = {'vertices': len(joined.data.vertices), 'polygons': len(joined.data.polygons),
                    'shape_keys': len(joined.data.shape_keys.key_blocks) - 1 if joined.data.shape_keys else 0,
                    'height_m': round(float(z.max() - z.min()), 4),
                    'materials': [m.name for m in joined.data.materials]}
low, high = job['height_cm']
assert low <= report['joined']['height_m'] * 100 <= high, f"height {report['joined']['height_m']} m is outside {job['height_cm']} cm"
skin = set(job['skin_materials'])
assert skin <= set(report['joined']['materials']), f'skin_materials not on the mesh: {sorted(skin - set(report["joined"]["materials"]))}'
bpy.ops.export_scene.gltf(filepath=str(dst), export_format='GLB', export_morph=True, export_apply=False,
                          export_yup=True)
Path(str(dst) + '.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print('GAME_REVIEW_SINGLE', json.dumps(report['joined']))
