"""Render where bones' skin weights fall on the Raider's body at bind: red is full weight, black none.

  $B -b <rigged.blend> --python weight_view.py -- <out_dir> <label>=<bone>[+<bone>...] ...
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

a = sys.argv[sys.argv.index('--') + 1:]
out = Path(a[0])
out.mkdir(parents=True, exist_ok=True)
sets = {s.split('=')[0]: s.split('=')[1].split('+') for s in a[1:]}
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'VERTEX'
sc.render.resolution_x, sc.render.resolution_y = 700, 840
cam = bpy.data.objects.new('C', bpy.data.cameras.new('C'))
sc.collection.objects.link(cam)
sc.camera = cam
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.vertex_groups]
for label, bones in sets.items():
    for ob in meshes:
        me = ob.data
        idx = {ob.vertex_groups[b].index for b in bones if b in ob.vertex_groups}
        w = np.array([sum(g.weight for g in v.groups if g.group in idx) for v in me.vertices])
        attr = me.color_attributes.get('wview') or me.color_attributes.new('wview', 'FLOAT_COLOR', 'POINT')
        cols = np.zeros((len(w), 4))
        cols[:, 0] = w
        cols[:, 1] = np.clip(w - 0.66, 0, 1) * 3 * 0.8
        cols[:, 3] = 1
        attr.data.foreach_set('color', cols.ravel())
        me.color_attributes.active_color = attr
    for view, yaw in (('front', 0), ('three_quarter', 40), ('side', 90), ('back', 180)):
        ang = math.radians(-90 + yaw)
        target = Vector((0, 0, 1.3))
        cam.location = target + Vector((math.cos(ang) * 1.7, math.sin(ang) * 1.7, 0.1))
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(out / f'{label}_{view}.png')
        bpy.ops.render.render(write_still=True)
print('WEIGHT_VIEW_DONE')
