"""Compare texture candidates on the unchanged, final character in fixed views."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_character_seams import apply_idle, setup_scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manny-dir', type=Path, required=True)
    parser.add_argument('--paint', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', choices=['CPU', 'GPU'], default='CPU')
    parser.add_argument('--reference', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    pose = {'animation': 'reference'} if args.reference else apply_idle(rig, args.manny_dir.resolve())
    if args.reference:
        rig.data.pose_position = 'REST'
    scene = setup_scene(args.device, 768, 24)
    material = bpy.data.materials['Character02_Source_Outfit']
    node = next(n for n in material.node_tree.nodes if n.type == 'TEX_IMAGE')
    report = {'source': str(args.source), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'blender': bpy.app.version_string, 'seed': 23, 'samples': 24, 'pose': pose,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'paints': []}
    for index, paint in enumerate(args.paint):
        node.image = bpy.data.images.load(str(paint.resolve()), check_existing=False)
        shots = []
        for name, center, angle, scale, elevation in [('front', (0, 0, .94), 0, 1.95, .08),
                                           ('side', (0, 0, .94), 90, 1.95, .08),
                                           ('back', (0, 0, .94), 180, 1.95, .08),
                                           ('collar', (0, -.015, 1.53), 0, .38, .08),
                                           ('top-three-quarter', (0, 0, 1.0), 35, 1.95, math.tan(math.radians(40))),
                                           ('shoulders-top-three-quarter', (0, -.015, 1.45), 35, .8, math.tan(math.radians(40)))]:
            direction = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)), elevation)).normalized()
            scene.camera.location = Vector(center) + direction * 5
            scene.camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
            scene.camera.data.ortho_scale = scale
            target = args.out / f'{index}-{name}.png'
            scene.render.filepath = str(target.resolve())
            bpy.ops.render.render(write_still=True)
            shots.append({'file': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        report['paints'].append({'file': str(paint), 'sha256': hashlib.sha256(paint.read_bytes()).hexdigest(), 'shots': shots})
    (args.out / 'review.json').write_text(json.dumps(report, indent=2))
    print('Paint comparison served, sir. The mesh has not moved a stitch.')


if __name__ == '__main__':
    main()
