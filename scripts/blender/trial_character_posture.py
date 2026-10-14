"""Isolated posture trials on the acquired T-pose; no source or UE changes."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_character_seams import apply_idle, setup_scene


def move_bone(rig, name, offset=(0, 0, 0), axis=None, degrees=0):
    bone = rig.pose.bones[name]
    before = bone.matrix.copy()
    matrix = before.copy()
    if axis:
        rotation = Matrix.Rotation(math.radians(degrees), 4, axis)
        matrix = rotation @ matrix
        matrix.translation = before.translation
    matrix.translation += Vector(offset)
    bone.matrix = matrix
    bpy.context.view_layer.update()


def clearance(rig, mesh):
    graph = bpy.context.evaluated_depsgraph_get()
    posed = mesh.evaluated_get(graph)
    verts = [posed.matrix_world @ v.co for v in posed.data.vertices]
    # The torso and coat skirt only: wrist/lining overlap belongs to a different seam check.
    ids = {v.index for v in mesh.data.vertices if v.co.z < 1.28 and abs(v.co.x) < .33}
    faces = [p.vertices[:] for p in mesh.data.polygons if all(i in ids for i in p.vertices)]
    coat = BVHTree.FromPolygons(verts, faces, all_triangles=False)
    result = {}
    for side in ['l', 'r']:
        hand = bpy.data.objects['Character02_hand_' + side]
        obj = hand.evaluated_get(graph)
        hv = [obj.matrix_world @ v.co for v in obj.data.vertices]
        palm = {v.index for v in hand.data.vertices if abs(v.co.x) > .69}
        hf = [p.vertices[:] for p in hand.data.polygons if all(i in palm for i in p.vertices)]
        hand_bvh = BVHTree.FromPolygons(hv, hf, all_triangles=False)
        pairs = coat.overlap(hand_bvh)
        distances = [coat.find_nearest(hv[i])[3] for i in palm]
        result[side] = {'intersecting_triangle_pairs': len(pairs), 'minimum_surface_distance_m': min(distances),
                        'wrist': list(rig.pose.bones['hand_' + side].head)}
    return result


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
    result = []
    for name, depression, spread, abduct, erect in [('elbow', .03, .025, 3, -3)]:
        apply_idle(rig, args.manny_dir)
        original = {b.name: b.matrix_basis.copy() for b in rig.pose.bones}
        if erect:
            move_bone(rig, 'spine_03', axis='X', degrees=erect)
        for side, sign in [('l', 1), ('r', -1)]:
            move_bone(rig, 'clavicle_' + side, (sign * spread, 0, -depression))
            move_bone(rig, 'upperarm_' + side, axis='Y', degrees=-sign * abduct)
            if name == 'elbow':
                move_bone(rig, 'lowerarm_' + side, axis='Y', degrees=-sign * 12)
            if name == 'forward':
                move_bone(rig, 'upperarm_' + side, axis='X', degrees=-12)
        corrections = {b.name: [list(row) for row in original[b.name].inverted() @ b.matrix_basis]
                       for b in rig.pose.bones if not np.allclose(np.array(original[b.name]), np.array(b.matrix_basis), atol=1e-5)}
        result.append({'name': name, 'clearance': clearance(rig, mesh), 'corrections_local': corrections,
                       'settings': {'depression': depression, 'spread': spread, 'abduct': abduct, 'erect': erect}})
        for view, angle, elevation in [('front', 0, 0), ('side', 90, 0), ('top34', 35, 40), ('back', 180, 0)]:
            direction = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)), math.tan(math.radians(elevation)))).normalized()
            scene.camera.location = Vector((0, 0, 1.25)) + direction * 5
            scene.camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
            scene.camera.data.ortho_scale = 1.2
            scene.render.filepath = str((args.out / f'{name}-{view}.png').resolve())
            bpy.ops.render.render(write_still=True)
    (args.out / 'trials.json').write_text(json.dumps(result, indent=2))
    print('POSTURE_TRIALS_COMPLETE: four applicants for the post of upright gentleman, sir.')


if __name__ == '__main__':
    main()
