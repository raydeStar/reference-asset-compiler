"""Game review step 4: head weights and the under-hair scatter mask, then a neck-turn render to look at.

blender -b <manny.blend> --python game_review_finish.py -- <job.json> <out.blend> <neck-pose.png>

1. Head weights (reference_asset_compiler.game_review.blend_weights): every vertex of a rigid head material (hair,
   scalp, eyes, lashes, occlusion, teeth, tongue, mouth) rides the head bone alone; skin blends head -> neck_02 ->
   neck_01 by height under the measured chin and fades into the rig's own weights above the collar. Envelope weights
   hung Remora's chin about a quarter on the spine, and it stepped whenever the idle tilted her head.
2. Colour attribute 'ScatterMask' (R=G=B): 0 on skin within scatter_mask_m[0] of hair, 1 beyond scatter_mask_m[1].
   The skin material multiplies its subsurface opacity by it, so the hair's shadow edge does not glow red.
3. The head and neck turned and tilted, rendered at the jaw: the chin must turn with the head, with no step.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.kdtree import KDTree

args = sys.argv[sys.argv.index('--') + 1:]
job = json.loads(Path(args[0]).read_text(encoding='utf-8'))
out, pose_png = Path(args[1]), Path(args[2])
sys.path.insert(0, str(Path(job['repo_root']) / 'src'))
from reference_asset_compiler.game_review import blend_weights, head_chain, is_hair, material_kind, smoothstep  # noqa: E402

rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
obj = next(o for o in bpy.data.objects if o.type == 'MESH')
me = obj.data
mats = [m.name for m in me.materials]
n = len(me.vertices)
co = np.empty(n * 3)
me.vertices.foreach_get('co', co)
world = np.array(obj.matrix_world)
co = co.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
bones = {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}
for b in ('head', 'neck_01', 'neck_02'):
    assert b in bones, f'the rig has no {b} bone'

mat_index = np.empty(len(me.polygons), int)
me.polygons.foreach_get('material_index', mat_index)
kind, hair_v, skin_v = {}, set(), set()
for p, mi in zip(me.polygons, mat_index):
    name = mats[mi]
    k = material_kind(name, job)
    if is_hair(name, job):
        hair_v.update(p.vertices)
    if k == 'skin':
        skin_v.update(p.vertices)
    if k:
        for i in p.vertices:
            if kind.get(i) != 'skin':      # a vertex shared with skin follows the skin rule (a smooth seam)
                kind[i] = k
assert skin_v, 'no skin vertices: check skin_materials'
assert hair_v, 'no hair vertices: check hair_materials'

# the chin: the lowest of the most-forward skin above neck_01 (forward is -Y in Blender)
skin = np.array(sorted(skin_v))
upper = skin[co[skin, 2] > bones['neck_01'][2]]
front = upper[co[upper, 1] < np.percentile(co[upper, 1], 15)]
chin_z = float(co[front, 2].min())
height = float(co[:, 2].max() - co[:, 2].min())
chain = head_chain(chin_z, height, job['head_weights'])

groups = {g.name: g for g in obj.vertex_groups}
names = {g.index: g.name for g in obj.vertex_groups}
for b in ('head', 'neck_01', 'neck_02'):
    if b not in groups:
        groups[b] = obj.vertex_groups.new(name=b)
changed = {'rigid': 0, 'skin': 0}
for i, k in kind.items():
    old = {names[g.group]: g.weight for g in me.vertices[i].groups}
    new = {'head': 1.0} if k == 'rigid' else blend_weights(float(co[i, 2]), old, chain)
    if new is None:
        continue
    for b in old:
        groups[b].remove([i])
    for b, w in new.items():
        groups[b].add([i], w, 'REPLACE')
    changed[k] += 1

# what now carries the chin (it should be the head)
near = [i for i in front if abs(co[i, 2] - chin_z) < 0.015]
carried = {}
for i in near:
    for g in me.vertices[i].groups:
        carried[names[g.group]] = carried.get(names[g.group], 0.0) + g.weight / len(near)

# scatter mask
near_m, far_m = job['scatter_mask_m']
kd = KDTree(len(hair_v))
for i in hair_v:
    kd.insert(co[i], i)
kd.balance()
mask = np.ones(n)
for i in skin_v - hair_v:
    mask[i] = smoothstep(kd.find(co[i])[2], near_m, far_m)
attr = me.color_attributes.get('ScatterMask') or me.color_attributes.new('ScatterMask', 'BYTE_COLOR', 'POINT')
attr.data.foreach_set('color', np.c_[mask, mask, mask, np.ones(n)].astype(np.float32).ravel())
me.color_attributes.active_color = attr

# hair sway shapes: loose hair in front of the ears, still at the roots and free at the tips. The review's play
# script drives them with a spring from the head's acceleration (Python cannot add physics nodes to an AnimBP).
motion = job.get('hair_motion', {})
sway_report = None
if motion.get('enabled', True):
    scalp_ids = {i for i, name in enumerate(mats) if is_hair(name, job) and 'scalp' in name.lower()}
    scalp_v = set()
    for p, mi in zip(me.polygons, mat_index):
        if mi in scalp_ids:
            scalp_v.update(p.vertices)
    anchor = sorted((skin_v | scalp_v) - (hair_v - scalp_v))
    akd = KDTree(len(anchor))
    for i in anchor:
        akd.insert(co[i], i)
    akd.balance()
    strands = np.array(sorted(hair_v - scalp_v))
    head_y = float(bones['head'][1])
    free = np.array([smoothstep(akd.find(co[i])[2], motion.get('free_from_m', 0.01), motion.get('free_at_m', 0.09))
                     for i in strands])
    # in front of the ears only: the braid and knot at the back stay on the head (forward is -Y)
    front = np.array([smoothstep(head_y + 0.02 - co[i, 1], 0.0, 0.04) for i in strands])
    weight = free * front
    inverse = np.linalg.inv(world[:3, :3])
    if not me.shape_keys:
        obj.shape_key_add(name='Basis', from_mix=False)
    basis = me.shape_keys.key_blocks[0]
    base_co = np.empty(n * 3)
    basis.data.foreach_get('co', base_co)
    base_co = base_co.reshape(-1, 3)
    sway = motion.get('sway_m', 0.035)
    # one shape per direction, so the play script never needs a negative morph weight
    shapes = {'rac_hair_sway_left': np.array([sway, 0, 0]), 'rac_hair_sway_right': np.array([-sway, 0, 0]),
              'rac_hair_sway_forward': np.array([0, -sway, 0]), 'rac_hair_sway_back': np.array([0, sway, 0]),
              'rac_hair_lift': np.array([0, 0, motion.get('lift_m', 0.025)])}
    for name, direction in shapes.items():
        if name in me.shape_keys.key_blocks:
            obj.shape_key_remove(me.shape_keys.key_blocks[name])
        key = obj.shape_key_add(name=name, from_mix=False)
        moved = base_co.copy()
        moved[strands] += weight[:, None] * (inverse @ direction)
        key.data.foreach_set('co', moved.ravel())
        key.value = 0.0
    sway_report = {'strand_vertices': int(len(strands)), 'moving_vertices': int(np.sum(weight > 0.05)),
                   'fully_free_vertices': int(np.sum(weight > 0.95)), 'sway_m': sway,
                   'lift_m': motion.get('lift_m', 0.025), 'shapes': list(shapes)}
out.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out.resolve()))

report = {
    'chin_z_m': round(chin_z, 4), 'height_m': round(height, 4),
    'bones_z_m': {b: round(float(bones[b][2]), 4) for b in ('head', 'neck_02', 'neck_01')},
    'chain_z_m': {k: round(v, 4) for k, v in chain.items()},
    'vertices_changed': changed, 'chin_carried_by': {k: round(v, 3) for k, v in sorted(carried.items(), key=lambda x: -x[1])},
    'scatter_mask': {'near_m': near_m, 'far_m': far_m, 'skin_vertices': len(skin_v), 'hair_vertices': len(hair_v),
                     'masked_vertices': int(np.sum(mask < 0.999))},
    'hair_materials': sorted({m for m in mats if is_hair(m, job)}),
    'rigid_materials': sorted({m for m in mats if material_kind(m, job) == 'rigid'}),
    'hair_motion': sway_report,
}
assert report['chin_carried_by'].get('head', 0) > 0.98, report['chin_carried_by']

# neck-turn evidence (not saved into the blend)
for b, (x, z) in {'neck_01': (8, 10), 'neck_02': (8, 10), 'head': (10, 12)}.items():
    pb = rig.pose.bones[b]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = Euler((math.radians(x), 0, math.radians(z)))
bpy.context.view_layer.update()
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = 700
scene.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w')
scene.world = w
w.color = (0.05, 0.05, 0.055)
for o in [o for o in scene.objects if o.type in ('LIGHT', 'CAMERA')]:
    bpy.data.objects.remove(o)
t = Vector((float(bones['head'][0]), float(bones['head'][1]) - 0.05, chin_z))
for name, loc, e, s in (('Key', (-0.6, -1.2, 1.0), 40, 0.8), ('Fill', (0.9, -1.0, 0.1), 12, 1.0)):
    light = bpy.data.lights.new(name, 'AREA')
    light.energy, light.size = e, s
    lo = bpy.data.objects.new(name, light)
    scene.collection.objects.link(lo)
    lo.location = t + Vector(loc)
    lo.rotation_euler = (t - lo.location).to_track_quat('-Z', 'Y').to_euler()
cd = bpy.data.cameras.new('c')
cd.lens = 100
cam = bpy.data.objects.new('c', cd)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = t + Vector((0.35, -0.85, -0.05))
cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
pose_png.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(pose_png.resolve())
bpy.ops.render.render(write_still=True)
report['neck_pose_render'] = str(pose_png)

# the sway shapes at full weight, from the front-three-quarter: roots must stay, tips must swing clear of the face
if sway_report:
    for b in ('neck_01', 'neck_02', 'head'):
        rig.pose.bones[b].rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()
    head = Vector(bones['head'].tolist())
    cam.location = head + Vector((0.3, -0.75, 0.02))
    cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cd.lens = 70
    keys = me.shape_keys.key_blocks
    sway_shots = []
    for label, values in (('rest', {}), ('left', {'rac_hair_sway_left': 1}), ('right', {'rac_hair_sway_right': 1}),
                          ('forward', {'rac_hair_sway_forward': 1}), ('back', {'rac_hair_sway_back': 1}),
                          ('lift', {'rac_hair_lift': 1})):
        for name in sway_report['shapes']:
            keys[name].value = values.get(name, 0.0)
        bpy.context.view_layer.update()
        path = pose_png.parent / f'hair-sway-{label}.png'
        scene.render.filepath = str(path.resolve())
        bpy.ops.render.render(write_still=True)
        sway_shots.append(path.name)
    report['hair_motion']['renders'] = sway_shots
Path(str(out) + '.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
print('GAME_REVIEW_FINISH', json.dumps(report))
