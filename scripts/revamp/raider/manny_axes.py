"""Give the rigged Raider Manny's bone axes without touching his joints, weights or shape keys.

The landmark rig names its bones after Manny but orients them its own way, so in Unreal the IK retargeter can only
match bone directions: every clip copied from a Manny-conformant character (Character02) came out with rolled
forearms, wrists, knees and ankles. fit_ue5_manny_rig.py's frame solver gives each bone Manny's frame turned onto
this character's joints; here it re-orients the existing armature's rest bones in place (heads stay put), adds
Manny's missing non-deform bones, and checks the mesh at rest has not moved.

The torso chain (pelvis to neck) takes Manny's frames exactly instead. Its segments are short, so a few centimetres'
difference in where this character's spine joints sit turned their aimed frames 26-47 degrees from Manny's, and
copying Manny's rotations then tilted the whole upper chest back by that much (the shoulders rode up to the ears in
every clip). With Manny's own frames the torso keeps the sculpted posture and moves by Manny's change from his
reference pose; the limbs keep aimed frames so they still hang and swing as Manny's do. The torso is fixed inside the
solve, before the limbs aim: overriding it afterwards left each clavicle carrying the spine's old 26 degree
correction as a roll about its own axis, which pitched the whole shoulder and handed about 17 degrees of twist on
down the arm.

  $B -b <raider_hero_rigged.blend> --python manny_axes.py -- <manny_refpose.json> <out.blend>
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'blender'))
from fit_ue5_manny_rig import M_UE, NON_DEFORM, P_AX, solve_frames  # noqa: E402

a = sys.argv[sys.argv.index('--') + 1:]
manny = json.load(open(a[0]))
out = Path(a[1])
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and any(
    m.type == 'ARMATURE' and m.object is rig for m in o.modifiers)]
assert rig.matrix_world == Matrix.Identity(4), 'expects an unscaled armature at the origin'


def evaluated():
    dg = bpy.context.evaluated_depsgraph_get()
    return {o.name: np.array([v.co[:] for v in o.evaluated_get(dg).to_mesh().vertices]) for o in meshes}


before = evaluated()
# joints (Blender metres): this rig's heads; Manny's bones it lacks sit where Manny has them, mapped to Blender
J = {b.name: np.array(b.head_local[:]) for b in rig.data.bones}
for b in manny['bones']:
    if b['name'] not in J:
        J[b['name']] = M_UE @ np.array(b['pos'], float) / 100.0
TORSO = ('pelvis', 'spine_01', 'spine_02', 'spine_03', 'spine_04', 'spine_05', 'neck_01', 'neck_02')
order, Pe, Re, Rm = solve_frames(manny, J, exact=TORSO)
parents = {b['name']: b['parent'] for b in manny['bones']}
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
eb = rig.data.edit_bones
added = []
for n in order:
    if n == 'root':
        continue
    bone = eb.get(n)
    if bone is None:
        bone = eb.new(n)
        bone.head, bone.tail = Vector(J[n]), Vector(J[n]) + Vector((0, 0, 0.05))
        added.append(n)
    length = bone.length
    mat = Matrix((M_UE @ Re[n] @ P_AX).tolist()).to_4x4()
    mat.translation = Vector(J[n])
    bone.matrix = mat
    bone.length = length
for n in added:
    p = parents[n]
    if p and p != 'root':
        eb[n].parent = eb[p]
    eb[n].use_deform = n not in NON_DEFORM
bpy.ops.object.mode_set(mode='OBJECT')
after = evaluated()
moved = max(float(np.abs(after[k] - before[k]).max()) for k in before)
heads = max(float(np.linalg.norm(np.array(b.head_local[:]) - J[b.name])) for b in rig.data.bones)
report = {'bones': len(rig.data.bones), 'added': added, 'rest_mesh_max_move_m': moved, 'head_max_move_m': heads}
print('MANNY_AXES', report)
assert moved < 1e-4 and heads < 1e-6, report
bpy.ops.wm.save_as_mainfile(filepath=str(out))
Path(str(out) + '.json').write_text(json.dumps(report, indent=2))
print('MANNY_AXES_OK', out)
