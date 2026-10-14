"""Record the existing T-pose, posed joints and garment clearance for diagnosis."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_character_seams import apply_idle, setup_scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--paint', type=Path, required=True)
    parser.add_argument('--manny-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    mesh = bpy.data.objects['Character02_Outfit_And_Hands']
    for mat in bpy.data.materials:
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and 'body_basecolor' in node.image.name:
                    node.image = bpy.data.images.load(str(args.paint.resolve()), check_existing=True)
    scene = setup_scene('GPU', 768, 16)
    result = {'source': str(args.source), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'blender': bpy.app.version_string, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'bones': {}, 'poses': [], 'geometry_changed': False}
    for b in rig.data.bones:
        result['bones'][b.name] = {'head': list(b.head_local), 'tail': list(b.tail_local),
                                 'matrix': [list(row) for row in b.matrix_local],
                                 'parent': b.parent.name if b.parent else None}
    rest = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
    mesh.data.calc_loop_triangles()
    tris = np.array([t.vertices for t in mesh.data.loop_triangles])
    weights = np.zeros((len(rest), len(mesh.vertex_groups)), dtype=np.float32)
    for v in mesh.data.vertices:
        for g in v.groups:
            weights[v.index, g.group] = g.weight
    np.savez_compressed(args.out / 'mesh.npz', rest=rest, triangles=tris, weights=weights,
                        groups=np.array([g.name for g in mesh.vertex_groups]))
    for name, animation, index in [('rest', None, 0), ('idle', 'MM_Idle', 0), ('jog', 'MM_Run_Fwd', 0), ('attack', 'MM_Attack_01', 0)]:
        if animation:
            poses = json.loads((args.manny_dir / 'manny_anim_poses.json').read_text())['poses']
            if not any(p['anim'] == animation for p in poses):
                result.setdefault('unavailable_poses', []).append(animation)
                continue
            apply_idle(rig, args.manny_dir, animation, index)
        else:
            rig.animation_data_clear()
            for b in rig.pose.bones:
                b.matrix_basis = Matrix.Identity(4)
            bpy.context.view_layer.update()
        obj = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        positions = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
        np.save(args.out / (name + '.npy'), positions)
        result['poses'].append({'name': name, 'animation': animation,
                               'joints': {b.name: list(b.head) for b in rig.pose.bones},
                               'matrices': {b.name: [list(row) for row in b.matrix] for b in rig.pose.bones}})
        if name not in ['rest', 'idle']:
            continue
        for view, angle, elevation in [('front', 0, 0), ('side', 90, 0), ('top34', 35, 40)]:
            direction = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)), math.tan(math.radians(elevation)))).normalized()
            scene.camera.location = Vector((0, 0, 1.25)) + direction * 5
            scene.camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
            scene.camera.data.ortho_scale = 1.4 if name == 'rest' else 1.2
            scene.render.filepath = str((args.out / f'{name}-{view}.png').resolve())
            bpy.ops.render.render(write_still=True)
    (args.out / 'inspection.json').write_text(json.dumps(result, indent=2))
    print('POSTURE_INSPECTION_COMPLETE: the skeleton has been asked to stand up straight, sir.')


if __name__ == '__main__':
    main()
