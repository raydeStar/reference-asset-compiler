# SPDX-License-Identifier: MIT
"""Render baked clips (bake_library_clips.py's clips.json) on the character's game rig, for review.

  blender -b --factory-startup <character game .blend> --python-exit-code 1 -P scripts/anim/preview_baked_clips.py --
      --clips <clips.json> --names MF_Unarmed_Jog_Fwd,MM_Idle --views q34,side --out <dir> [--seconds 3] [--size 400x560]

Writes <out>/<clip>/<view>_<frame>.png at the clip's fps (loops repeat to fill --seconds) and, when ffmpeg is on
PATH, <out>/<clip>_<view>.mp4. Fixed cameras and sun lights, EEVEE; the tracks are the exact data the game keys.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clip_retarget as cr  # noqa: E402

OFFSETS = {'front': (0, -4.6), 'side': (4.6, 0), 'q34': (3.3, -3.3), 'back': (0, 4.6), 'q34back': (3.3, 3.3)}


def matrix_from_ue(k):
    x, y, z, qx, qy, qz, qw = k
    m = Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
    m.translation = Vector((x / 100, y / 100, z / 100))
    return np.array(cr.UE_AXES @ m @ cr.UE_AXES)


def stage(scene, size):
    for o in list(scene.objects):
        if o.type in ('CAMERA', 'LIGHT'):
            bpy.data.objects.remove(o)
    cam = bpy.data.objects.new('review_cam', bpy.data.cameras.new('review_cam'))
    scene.collection.objects.link(cam)
    cam.data.lens = 50
    scene.camera = cam
    for name, rot, energy in [('key', (50, 0, -35), 4.0), ('fill', (60, 0, 140), 1.5)]:
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN'))
        light.data.energy = energy
        light.rotation_euler = [math.radians(a) for a in rot]
        scene.collection.objects.link(light)
    scene.world = scene.world or bpy.data.worlds.new('w')
    scene.world.color = (0.3, 0.3, 0.32)
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = size
    return cam


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--clips', type=Path, required=True)
    p.add_argument('--names', required=True)
    p.add_argument('--views', default='q34')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=0)
    p.add_argument('--size', default='400x560')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    a.out = a.out.resolve()     # Blender would resolve a relative render path against the .blend
    data = json.loads(a.clips.read_text())
    scene = bpy.context.scene
    rig = cr.TargetRig(next(o for o in scene.objects if o.type == 'ARMATURE'))
    cam = stage(scene, tuple(int(v) for v in a.size.split('x')))
    ffmpeg = shutil.which('ffmpeg')
    for name in a.names.split(','):
        clip = data['clips'][name]
        out = a.out / name
        out.mkdir(parents=True, exist_ok=True)
        n, fps = clip['frames'], clip['fps']
        total = round((a.seconds or max(2 * (n - 1) / fps, 2.0)) * fps)
        period = n - 1 if clip['loop'] else n
        for f in range(total):
            k = f % period if clip['loop'] else min(f, n - 1)
            local = np.array([matrix_from_ue(clip['tracks'][b][k]) if b in clip['tracks'] else rig.local_rest[i]
                              for i, b in enumerate(rig.names)])
            rig.apply(local)
            bpy.context.view_layer.update()
            for v in a.views.split(','):
                ox, oy = OFFSETS[v]
                cam.location = Vector((ox, oy, 1.05))
                cam.rotation_euler = (Vector((0, 0, 0.95)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
                scene.render.filepath = str(out / f'{v}_{f:04d}.png')
                bpy.ops.render.render(write_still=True)
        if ffmpeg:
            for v in a.views.split(','):
                subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', str(out / f'{v}_%04d.png'),
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', str(a.out / f'{name}_{v}.mp4')], check=True)
        print('PREVIEWED', name, total, flush=True)


if __name__ == '__main__':
    main()
