# SPDX-License-Identifier: MIT
"""Inspect, bake and reimport UE-local clip packets on a preserved native game rig.

Run with Blender --background --factory-startup --python-exit-code 1 --python
this_file -- --source character.blend --packet clips.json --out fresh-directory
[--mode inspect|export] [--clips comma,separated] [--render-views].
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'anim'))
from rotation_metrics import rotation_error_degrees  # noqa: E402

AXES = Matrix.Diagonal((1., -1., 1., 1.))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def from_ue(values):
    x, y, z, qx, qy, qz, qw = values
    m = Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
    m.translation = Vector((x / 100, y / 100, z / 100))
    return AXES @ m @ AXES


def to_ue(m):
    m = AXES @ m @ AXES
    q = m.to_quaternion()
    return [*(m.translation * 100), q.x, q.y, q.z, q.w]


def fingerprint(rig):
    """Canonical native geometry, UV, weights, materials, images and bind data."""
    state = {"bones": [(b.name, b.parent.name if b.parent else None, [list(v) for v in b.matrix_local])
                       for b in rig.data.bones], "meshes": [], "images": []}
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type != "MESH":
            continue
        mesh = obj.data
        state["meshes"].append({"name": obj.name, "matrix": [list(v) for v in obj.matrix_world],
            "vertices": [list(v.co) for v in mesh.vertices],
            "polygons": [list(p.vertices) for p in mesh.polygons],
            "uv": [[list(d.uv) for d in layer.data] for layer in mesh.uv_layers],
            "groups": [g.name for g in obj.vertex_groups],
            "weights": [[(g.group, g.weight) for g in v.groups] for v in mesh.vertices],
            "materials": [m.name if m else None for m in mesh.materials]})
    for image in bpy.data.images:
        if image.packed_file:
            state["images"].append((image.name, hashlib.sha256(image.packed_file.data).hexdigest()))
        elif image.filepath and Path(bpy.path.abspath(image.filepath)).is_file():
            state["images"].append((image.name, sha(bpy.path.abspath(image.filepath))))
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def find_rig(names):
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE" and
            set(names) <= {b.name for b in o.data.bones}]
    if len(rigs) != 1:
        raise ValueError("one unambiguous game rig matching the packet is required")
    return rigs[0]


def pose_world(rig):
    return {b.name: rig.matrix_world @ b.matrix for b in rig.pose.bones}


def render_views(out, rig, action, motion_fps=0, ffmpeg=None, motion_width=180):
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    camera = bpy.data.objects.new("AnimationReviewCamera", bpy.data.cameras.new("AnimationReviewCamera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type, camera.data.ortho_scale = "ORTHO", 2.5
    for name, xyz, energy in (("key", (3, -4, 5), 800), ("fill", (-4, -2, 3), 600), ("rim", (2, 4, 4), 900)):
        obj = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(obj)
        obj.location = xyz
        obj.rotation_euler = (Vector((0, 0, 1)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        obj.data.energy, obj.data.shape, obj.data.size = energy, "DISK", 5
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples = "CPU", 8
    scene.cycles.use_denoising = True
    scene.render.threads_mode, scene.render.threads = "FIXED", 8
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 360, 440, 100
    scene.world = scene.world or bpy.data.worlds.new("AnimationReviewWorld")
    scene.world.color = (.2, .2, .2)
    rig.animation_data.action = action
    out.mkdir()
    files = []
    views = {"front": (0,-5,1), "three-quarter": (3,-4,1), "side": (5,0,1), "back": (0,5,1)}
    for label, frame in (("start", int(action.frame_range[0])), ("middle", round(sum(action.frame_range) / 2)), ("end", int(action.frame_range[1]))):
        scene.frame_set(frame)
        for view, xyz in views.items():
            camera.location = xyz
            camera.rotation_euler = (Vector((0,0,1)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
            file = out / f"{label}-{view}.png"
            scene.render.filepath = str(file)
            bpy.ops.render.render(write_still=True)
            files.append({"path": str(file), "sha256": sha(file)})
    if motion_fps:
        scene.render.resolution_x, scene.render.resolution_y = motion_width, round(motion_width * 11 / 9)
        scene.cycles.samples = 8 if motion_width >= 360 else 2
        native_fps = scene.render.fps / scene.render.fps_base
        first, last = action.frame_range
        duration = (last - first) / native_fps
        # Uniform review cadence; a non-looping action is explicitly repeated,
        # not claimed to have a seamless end-to-start transition.
        count = max(2, math.ceil(duration * motion_fps))
        for view, xyz in views.items():
            sequence = out / ('motion-' + view)
            sequence.mkdir()
            camera.location = xyz
            camera.rotation_euler = (Vector((0,0,1)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
            for index in range(count):
                frame = first + index / count * (last - first)
                scene.frame_set(math.floor(frame), subframe=frame % 1)
                scene.render.filepath = str(sequence / f'{index:05d}.png')
                bpy.ops.render.render(write_still=True)
            video = out / (view + '-two-repeats.mp4')
            command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-n',
                       '-framerate', str(motion_fps), '-i', str(sequence / '%05d.png'),
                       '-vf', f'loop=loop=1:size={count}:start=0', '-frames:v', str(count * 2),
                       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', str(video)]
            subprocess.run(command, check=True, timeout=120)
            files.append({'path': str(video), 'sha256': sha(video), 'view': view,
                          'repeats': 2, 'review_fps': motion_fps, 'frames': count * 2,
                          'resolution': [scene.render.resolution_x, scene.render.resolution_y],
                          'scope': 'Exported-GLB review; two repeats, no gameplay proof'})
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--packet", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--mode", choices=("inspect", "export"), default="inspect")
    p.add_argument("--clips", default="")
    p.add_argument("--render-views", action="store_true")
    p.add_argument('--motion-fps', type=int, choices=(0, 12, 24, 30), default=0)
    p.add_argument('--ffmpeg', help='Explicit local FFmpeg executable for review videos')
    p.add_argument('--motion-width', type=int, choices=(180, 360), default=180)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.out = args.out.resolve()
    if args.motion_fps and (not args.render_views or not args.ffmpeg):
        raise ValueError('motion review needs --render-views and --ffmpeg')
    packet = json.loads(args.packet.read_text(encoding="utf-8-sig"))
    if packet["provenance"]["character_blend_sha256"] != sha(args.source):
        raise ValueError("character hash disagrees with packet")
    wanted = args.clips.split(',') if args.clips else list(packet["clips"])
    if len(set(wanted)) != len(wanted) or set(wanted) - set(packet["clips"]):
        raise ValueError("select unique existing clips")
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {"source_sha256": sha(args.source), "packet_sha256": sha(args.packet),
               "script_sha256": sha(__file__), "blender": bpy.app.version_string,
               "rotation_metric_sha256": sha(Path(__file__).resolve().parents[1]/'anim/rotation_metrics.py'),
               "human_approved": False, "gameplay_tested": False, "error": None}
    try:
        bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
        rig = find_rig(packet["bones"])
        if any(b.constraints for b in rig.pose.bones):
            raise ValueError("constrained rigs require a separate control-rig adapter")
        if any(abs(s - 1) > 1e-5 for s in rig.matrix_world.to_scale()):
            raise ValueError("native game rig must have unit object scale")
        names = packet["bones"]
        parents = [names.index(rig.data.bones[n].parent.name) if rig.data.bones[n].parent else -1 for n in names]
        local_rest = {b.name: b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local.copy()
                      for b in rig.data.bones}
        skeleton = {"schema": "reference-asset-compiler.animation-skeleton.v1", "bones": names,
                    "parents": parents, "units": "cm", "rotation": "xyzw", "up_axis": "Z",
                    "armature_transform": to_ue(rig.matrix_world),
                    "rest_local": {n: to_ue(local_rest[n]) for n in names},
                    "source_sha256": sha(args.source), "blender": bpy.app.version_string}
        save(args.out / "skeleton.json", skeleton)
        if args.mode == "inspect":
            receipt["native_fingerprint"] = fingerprint(rig)
            return
        before = fingerprint(rig)
        object_rest = rig.matrix_world.copy()
        rig.animation_data_clear()
        rig.rotation_mode = 'QUATERNION'
        for old_action in list(bpy.data.actions):
            bpy.data.actions.remove(old_action)
        for b in rig.pose.bones:
            b.matrix_basis = Matrix.Identity(4)
            b.rotation_mode = 'QUATERNION'
        scene = bpy.context.scene
        actions, expected = {}, {}
        rates = {packet["clips"][n]["fps"] for n in wanted}
        if len(rates) != 1:
            raise ValueError("export one sample rate per bundle")
        scene.render.fps = round(next(iter(rates)))
        scene.render.fps_base = scene.render.fps / next(iter(rates))
        for name in wanted:
            c = packet["clips"][name]
            action = bpy.data.actions.new(name)
            action.use_fake_user = True
            rig.animation_data_create()
            rig.animation_data.action = action
            for f in range(c["frames"]):
                # This existing rig's armature object becomes the UE export root.
                # Key identity on in-place clips too, so another action's travel cannot leak.
                root = from_ue(c['tracks']['root'][f]) if 'root' in c['tracks'] and 'root' not in names else Matrix.Identity(4)
                rig.matrix_world = object_rest @ root
                for prop in ('location', 'rotation_quaternion', 'scale'):
                    rig.keyframe_insert(data_path=prop, frame=f)
                for bone in rig.pose.bones:
                    if bone.name not in c["tracks"]:
                        continue
                    bone.matrix_basis = local_rest[bone.name].inverted() @ from_ue(c["tracks"][bone.name][f])
                    for prop in ("location", "rotation_quaternion", "scale"):
                        bone.keyframe_insert(data_path=prop, frame=f, group=bone.name)
            actions[name] = action
            expected[name] = []
            for f in range(c["frames"]):
                scene.frame_set(f)
                expected[name].append(pose_world(rig))
            print(f"BAKED {name}: {c['frames']} frames; the joints have kept their appointments.", flush=True)
        rig.animation_data.action = None
        rig.matrix_world = object_rest
        bpy.context.view_layer.update()
        after = fingerprint(rig)
        if after != before:
            raise ValueError("baking changed native geometry, UVs, weights, images or bind data")
        scene.frame_start, scene.frame_end = 0, max(packet['clips'][n]['frames'] for n in wanted)-1
        rig.animation_data.action = actions[wanted[0]]
        scene.frame_set(0)
        native = args.out / 'animated.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(native))
        glb = args.out / 'animated.glb'
        # Static attachments parented to animated bones must be exported from
        # the same bind pose in every variant. Otherwise their rest transforms
        # inherit decomposition noise from the selected action's first frame.
        rig.animation_data.action = None
        rig.matrix_world = object_rest.copy()
        for bone in rig.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', export_animations=True,
            export_animation_mode='ACTIONS', export_frame_range=False, export_force_sampling=True,
            export_cameras=False, export_lights=False)
        rig.animation_data.action = actions[wanted[0]]
        scene.frame_set(0)
        fbx = args.out / 'animated.fbx'
        bpy.ops.export_scene.fbx(filepath=str(fbx), object_types={'ARMATURE','MESH'},
            add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=True,
            bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0.0,
            apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y')
        receipt.update(native_fingerprint_before=before, native_fingerprint_after=after,
                       root_contract='Synthetic packet root is armature-object animation; native bone hierarchy is preserved. Unreal root extraction still needs destination verification.',
                       exports=[{"path": str(f), "sha256": sha(f)} for f in (native, glb, fbx)])
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = round(next(iter(rates)))
        bpy.context.scene.render.fps_base = bpy.context.scene.render.fps / next(iter(rates))
        bpy.ops.import_scene.gltf(filepath=str(glb))
        rig = find_rig(names)
        errors = {}
        imported = {}
        for name in wanted:
            matches = [a for a in bpy.data.actions if a.name == name]
            if not matches:
                matches = [a for a in bpy.data.actions if a.name.endswith('|' + name)]
            if len(matches) != 1:
                raise ValueError(f"reimport could not resolve exact clip {name}: {[a.name for a in bpy.data.actions]}")
            action = matches[0]
            imported[name] = action
            rig.animation_data_create()
            rig.animation_data.action = action
            worst_cm, worst_deg = 0., 0.
            for f, source in enumerate(expected[name]):
                bpy.context.scene.frame_set(f)
                actual = pose_world(rig)
                for n in names:
                    worst_cm = max(worst_cm, (actual[n].translation - source[n].translation).length * 100)
                    worst_deg = max(worst_deg, rotation_error_degrees(actual[n].to_quaternion(), source[n].to_quaternion()))
            errors[name] = {"position_error_cm": worst_cm, "orientation_error_deg": worst_deg,
                            "samples": len(expected[name]), "passed": worst_cm < .05 and worst_deg < .1}
        receipt["glb_roundtrip"] = errors
        receipt["technical_passed"] = all(e['passed'] for e in errors.values())
        if args.render_views:
            receipt['views'] = {}
            for name in wanted:
                receipt['views'][name] = render_views(args.out / ('views-' + name), rig, imported[name], args.motion_fps, args.ffmpeg, args.motion_width)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = round(next(iter(rates)))
        bpy.context.scene.render.fps_base = bpy.context.scene.render.fps / next(iter(rates))
        bpy.ops.import_scene.fbx(filepath=str(fbx), use_anim=True, anim_offset=0)
        rig = find_rig(names)
        errors = {}
        for name in wanted:
            matches = [a for a in bpy.data.actions if a.name == name or
                       (a.name.startswith(rig.name + '|') and a.name.endswith('|' + name))]
            if len(matches) != 1:
                raise ValueError(f'FBX reimport cannot resolve {name}: {[a.name for a in bpy.data.actions]}')
            rig.animation_data_create()
            rig.animation_data.action = matches[0]
            worst_cm, worst_deg = 0., 0.
            for f, source in enumerate(expected[name]):
                bpy.context.scene.frame_set(f)
                actual = pose_world(rig)
                for n in names:
                    worst_cm = max(worst_cm, (actual[n].translation - source[n].translation).length * 100)
                    worst_deg = max(worst_deg, rotation_error_degrees(actual[n].to_quaternion(), source[n].to_quaternion()))
            errors[name] = {'position_error_cm': worst_cm, 'orientation_error_deg': worst_deg,
                            'samples': len(expected[name]), 'passed': worst_cm < .05 and worst_deg < .1}
        receipt['fbx_roundtrip'] = errors
        receipt['technical_passed'] &= all(e['passed'] for e in errors.values())
        if not receipt["technical_passed"]:
            raise ValueError("exported animation exceeds roundtrip tolerances")
    except Exception as error:
        receipt['error'] = str(error)
        receipt['technical_passed'] = False
        raise
    finally:
        save(args.out / 'receipt.json', receipt)


if __name__ == '__main__':
    main()
