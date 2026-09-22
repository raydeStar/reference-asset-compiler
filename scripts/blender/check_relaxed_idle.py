"""Reimport an exported GLB and check its declared relaxed standing idle.

blender -b --factory-startup --python-exit-code 1 --python scripts/blender/check_relaxed_idle.py \
    -- candidate.glb Clip_Name report.json --height 1.82

Requires the canonical humanoid bone names in idle_pose.JOINTS. It refuses an
unmatched clip or skeleton instead of quietly measuring the rest pose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from reference_asset_compiler.idle_pose import JOINTS, check_relaxed_standing_idle


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=Path)
    parser.add_argument("clip")
    parser.add_argument("report", type=Path)
    parser.add_argument("--height", type=float, required=True, help="Bind-pose character height in metres")
    args = parser.parse_args(argv)
    if args.report.exists():
        raise ValueError("Keep the previous receipt; use a fresh report path.")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.asset.resolve()))
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Expected one humanoid armature.")
    rig = rigs[0]
    missing = set(JOINTS) - set(rig.pose.bones.keys())
    if missing:
        raise ValueError(f"Unmapped skeleton bones: {sorted(missing)}")
    if not rig.animation_data:
        raise ValueError("The delivered asset has no animation data.")
    # Imported glTF clips live in NLA strips. Match the original clip name,
    # since Blender may add an object suffix to its internal Action name.
    matches = [(track, strip) for track in rig.animation_data.nla_tracks
               for strip in track.strips if track.name == args.clip or strip.action.name == args.clip]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one imported clip named {args.clip!r}.")
    chosen, strip = matches[0]
    rig.animation_data.action = None
    for track in rig.animation_data.nla_tracks:
        track.mute = track != chosen
        track.is_solo = False
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start, end = strip.frame_start, strip.frame_end
    if end <= start:
        raise ValueError("Idle clip has no duration.")
    count = max(9, math.ceil((end - start) / fps * 24) + 1)
    if count > 10001:
        raise ValueError("Clip exceeds this review tool's bounded sampling budget.")
    samples, orientations = [], []
    for index in range(count):
        frame = start + (end - start) * index / (count - 1)
        scene.frame_set(math.floor(frame), subframe=frame % 1)
        bpy.context.view_layer.update()
        samples.append({"time": (frame - start) / fps,
                        "joints": {name: list(rig.matrix_world @ rig.pose.bones[name].head)
                                   for name in JOINTS}})
        if index in (0, count - 1):
            orientations.append({bone.name: (rig.matrix_world @ bone.matrix).to_quaternion().copy()
                                 for bone in rig.pose.bones})
    result = check_relaxed_standing_idle(samples, height=args.height)
    # Quaternion sign is immaterial; report the smaller equivalent angle.
    max_rotation_gap = max(min(math.degrees(a.rotation_difference(orientations[-1][name]).angle),
                               360 - math.degrees(a.rotation_difference(orientations[-1][name]).angle))
                           for name, a in orientations[0].items())
    if max_rotation_gap > .5:
        result["findings"].append({"code": "loop_rotation_discontinuity", "degrees": max_rotation_gap})
        result["checks_passed"] = False
    result.update({"asset_sha256": hashlib.sha256(args.asset.read_bytes()).hexdigest(),
                   "clip": args.clip, "sample_count": count, "height": args.height,
                   "max_loop_rotation_gap_degrees": max_rotation_gap,
                   "samples": samples, "limitations": "Joint checks do not prove mesh clearance, deformation quality, natural motion, or artistic acceptance."})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"IDLE_POSE_CHECK {'PASS' if result['checks_passed'] else 'FAIL'} -- a pose is not a pardon; visual review remains.")
    if not result["checks_passed"]:
        raise RuntimeError(f"Idle pose rejected: {len(result['findings'])} findings. See {args.report}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
