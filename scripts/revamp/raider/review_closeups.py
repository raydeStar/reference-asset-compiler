"""Close-up review of the Manny-axis Raider: the same body regions at bind and in real Manny frames.

Texture or UV faults (stretch, seams) show at bind; skinning faults appear only once posed. Each pose is applied as
Unreal's one-to-one retarget would (manny_pose.py), then each region is shot from the front, three-quarter, side and
back under the studio light of final_renders.py.

  $B -b <raider_hero_rigged_manny.blend> --python review_closeups.py -- <manny_refpose.json> <manny_anim_poses.json>
      <out_dir> [--poses RefPose,MM_Idle,...] [--regions torso,legs] [--res 900]
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manny_pose import MannyPoser  # noqa: E402

# region: (look-at height m, camera distance m)
REGIONS = {'torso': (1.32, 1.5), 'arms': (1.15, 2.0), 'hands': (0.95, 1.4), 'legs': (0.55, 1.7), 'full': (0.95, 3.4)}
VIEWS = {'front': 0, 'three_quarter': 40, 'side': 90, 'back': 180}

argv = sys.argv[sys.argv.index('--') + 1:]
manny = json.loads(Path(argv[0]).read_text())
poses = json.loads(Path(argv[1]).read_text())['poses']
out = Path(argv[2])
out.mkdir(parents=True, exist_ok=True)


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


wanted = opt('--poses', 'RefPose,MM_Idle,MF_Unarmed_Jog_Fwd,MM_Attack_01').split(',')
regions = opt('--regions', 'torso,arms,legs').split(',')
res = int(opt('--res', '900'))
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
poser = MannyPoser(rig, manny)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = res, int(res * 1.2)
sc.world = sc.world or bpy.data.worlds.new('w')
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.42, 0.43, 0.46, 1)
bg.inputs['Strength'].default_value = 0.9
for name, energy, rot in (('key', 2.6, (55, 0, -35)), ('fill', 0.7, (65, 0, 60)), ('rim', 1.6, (110, 0, 170))):
    lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN'))
    lamp.data.energy = energy
    lamp.rotation_euler = [math.radians(r) for r in rot]
    sc.collection.objects.link(lamp)
cam = bpy.data.objects.new('ReviewCam', bpy.data.cameras.new('ReviewCam'))
cam.data.lens = 50
sc.collection.objects.link(cam)
sc.camera = cam


chosen = [('RefPose', None)] if 'RefPose' in wanted else []
for name in wanted:
    hit = next((p for p in poses if p['anim'] == name), None)
    if hit:
        chosen.append((f"{name}_{hit['time']:.2f}".replace('.', 'p'), hit))
shots = []
for tag, pose in chosen:
    pelvis = poser.apply(pose, bpy.context.view_layer)
    follow = Vector((pelvis.x, pelvis.y, 0))
    for region in regions:
        height, dist = REGIONS[region]
        for view, yaw in VIEWS.items():
            a = math.radians(-90 + yaw)       # the character faces -Y
            target = Vector((0, 0, height)) + follow
            cam.location = target + Vector((math.cos(a) * dist, math.sin(a) * dist, 0.15))
            cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
            path = out / f'{tag}_{region}_{view}.png'
            sc.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            shots.append(path.name)
(out / 'shots.json').write_text(json.dumps(shots, indent=1))
print('REVIEW_CLOSEUPS_DONE', len(shots), os.fspath(out))
