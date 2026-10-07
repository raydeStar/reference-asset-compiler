"""Review the actual rig, groom attachment and facial controls in posed renders."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


def aim(rig, name, direction):
    bone = rig.pose.bones[name]
    target = Vector(direction).normalized()
    rotation = (bone.tail - bone.head).normalized().rotation_difference(target) @ bone.matrix.to_quaternion()
    basis = bone.bone.matrix_local
    if bone.parent:
        basis = bone.parent.matrix @ bone.parent.bone.matrix_local.inverted() @ basis
    bone.rotation_mode = "QUATERNION"
    bone.rotation_quaternion = basis.to_quaternion().inverted() @ rotation
    bpy.context.view_layer.update()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("--samples", type=int, default=32)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, out = Path(a.source).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    rig = next(ob for ob in scene.objects if ob.type == "ARMATURE")
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type != "CPU"
    scene.cycles.device = "GPU"
    scene.cycles.samples = a.samples
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.camera.data.type = "ORTHO"
    scene.camera.data.ortho_scale = 2.05
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Quaternion()
    for side, sign in (("l", 1), ("r", -1)):
        aim(rig, "upperarm_" + side, (sign * 0.15, 0.02, -1))
        aim(rig, "lowerarm_" + side, (sign * 0.03, -0.20, -1))
        aim(rig, "hand_" + side, (sign * 0.03, -0.14, -1))
        for digit in ("index", "middle", "ring", "pinky"):
            for part, angle in (("01", -8), ("02", -12), ("03", -8)):
                rig.pose.bones[f"{digit}_{part}_{side}"].rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(angle))
    bpy.context.view_layer.update()
    scene.frame_start, scene.frame_end = 0, 48
    scene.render.fps = 24
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new("Ennix_Held_Inspection")
    for bone in rig.pose.bones:
        for frame in (0, 48):
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
    scene.frame_set(0)

    def render(name, angle, centre, scale):
        direction = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)), 0))
        scene.camera.location = Vector(centre) + direction * 5
        scene.camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        scene.camera.data.ortho_scale = scale
        scene.render.filepath = str(out / (name + ".png"))
        bpy.ops.render.render(write_still=True)

    for name, angle in (("front", 0), ("three-quarter", 35), ("side", 90), ("back", 180)):
        render("held-" + name, angle, (0, 0, 0.90), 2.05)
    scene.frame_set(0)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "Ennix_Held_Inspection.blend"))
    # Turn the head separately: hair, eyeballs and teeth must travel with it.
    rig.animation_data_clear()
    rig.pose.bones["neck_01"].rotation_quaternion = Quaternion(Vector((0, 1, 0)), math.radians(30))
    bpy.context.view_layer.update()
    render("head-turn", 0, (0, 0, 1.66), 0.45)
    rig.pose.bones["neck_01"].rotation_quaternion = Quaternion()
    expressions = {"smile": {"mouth-corner-puller": 0.65, "mouth-open": 0.12},
                   "open-mouth": {"mouth-open": 0.70},
                   "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0}}
    facial_objects = [ob for ob in scene.objects if ob.type == "MESH" and ob.data.shape_keys]
    for name, mix in expressions.items():
        for ob in facial_objects:
            for key in ob.data.shape_keys.key_blocks:
                key.value = mix.get(key.name, 0)
        bpy.context.view_layer.update()
        render("face-" + name, 0, (0, -0.02, 1.67), 0.37)
    for ob in facial_objects:
        for key in ob.data.shape_keys.key_blocks:
            key.value = 0
    report = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "clip": "Ennix_Held_Inspection", "held_pose_only": True,
              "facial_controls": {ob.name: len(ob.data.shape_keys.key_blocks) - 1 for ob in facial_objects},
              "expressions_reviewed": expressions, "production_ready": False,
              "note": "Native posed evidence; exported animation and artistic acceptance are separate checks."}
    (out / "pose-review.json").write_text(json.dumps(report, indent=2))
    print("Ennix has lowered his arms, sir. The scarecrow has left the fitting room.")


if __name__ == "__main__":
    main()
