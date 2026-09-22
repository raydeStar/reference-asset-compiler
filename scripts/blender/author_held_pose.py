"""Author a source-bound, held pose as a clip without changing the bind pose.

Usage: blender -b --factory-startup --python-exit-code 1 --python
scripts/blender/author_held_pose.py -- source.blend recipe.json new-output-directory

Recipes are specific to a measured rig. This is not automatic idle generation.
Run check_relaxed_idle.py on the resulting GLB and review all four views before import.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Quaternion, Vector


def main(argv):
    if len(argv) != 3:
        raise ValueError("Expected source.blend, recipe.json and a fresh output directory.")
    source, recipe_path, target = map(lambda p: Path(p).resolve(), argv)
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != recipe["source_sha256"]:
        raise ValueError("Recipe source hash does not match; remeasure the changed rig.")
    if target.exists():
        raise ValueError("Preserve previous attempts; choose a fresh output directory.")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(rigs) != 1 or not meshes:
        raise ValueError("Expected one rig and its existing meshes.")
    rig = rigs[0]
    if any(bone.constraints for bone in rig.pose.bones):
        raise ValueError("Constrained control rigs need an explicit bake route.")
    if any(recipe["uv_layer"] not in mesh.data.uv_layers for mesh in meshes):
        raise ValueError("The recipe's export UV layer is missing.")
    rig.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = Quaternion()
        bone.location = (0, 0, 0)
        bone.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    keyed = []
    for entry in recipe["aims"]:
        bone = rig.pose.bones[entry["bone"]]
        direction = Vector(entry["direction"])
        if direction.length < 1e-6:
            raise ValueError("An aim direction cannot be zero.")
        direction.normalize()
        previous = (bone.tail - bone.head).normalized()
        rotation = (Quaternion(direction, math.radians(entry["roll_degrees"]))
                    @ previous.rotation_difference(direction) @ bone.matrix.to_quaternion())
        basis = bone.bone.matrix_local
        if bone.parent:
            basis = bone.parent.matrix @ bone.parent.bone.matrix_local.inverted() @ basis
        bone.rotation_quaternion = basis.to_quaternion().inverted() @ rotation
        keyed.append(bone.name)
        bpy.context.view_layer.update()
    for entry in recipe.get("local_rotations", []):
        bone = rig.pose.bones[entry["bone"]]
        bone.rotation_quaternion = Quaternion(Vector(entry["axis"]), math.radians(entry["degrees"]))
        keyed.append(bone.name)
    if not keyed or len(set(keyed)) != len(keyed):
        raise ValueError("A held pose needs distinct, explicitly posed bones.")
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.render.fps_base = 1
    scene.frame_start, scene.frame_end = 0, 48
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new(recipe["clip"])
    # Both endpoints hold the authored pose. Identity would resurrect the scarecrow.
    for name in keyed:
        for frame in (0, 48):
            rig.pose.bones[name].keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
    scene.frame_set(0)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    target.mkdir(parents=True)
    native = target / "held-pose.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    for mesh in meshes:
        for layer in list(mesh.data.uv_layers):
            if layer.name != recipe["uv_layer"]:
                mesh.data.uv_layers.remove(layer)
    glb = target / "held-pose.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                              export_animations=True, export_animation_mode="ACTIONS",
                              export_yup=True, export_image_format="AUTO")
    raw = glb.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + length])
    if len(doc.get("animations", [])) != 1:
        raise ValueError("Expected one exported held-pose clip.")
    anim = doc["animations"][0]
    channels, samplers = [], []
    for channel in anim["channels"]:
        node = channel["target"]
        if doc["nodes"][node["node"]].get("name") in keyed and node["path"] == "rotation":
            sampler = anim["samplers"][channel["sampler"]]
            channel["sampler"] = len(samplers)
            samplers.append(sampler)
            channels.append(channel)
    if len(channels) != len(keyed):
        raise ValueError("Export omitted an authored rotation channel.")
    anim["channels"], anim["samplers"] = channels, samplers
    encoded = json.dumps(doc, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    other = raw[20 + length:]
    glb.write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(encoded) + len(other))
                    + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + other)
    receipt = {"source_sha256": source_hash,
               "recipe_sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
               "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
               "glb_sha256": hashlib.sha256(glb.read_bytes()).hexdigest(),
               "clip": recipe["clip"], "duration": 2, "posed_bones": keyed,
               "stage": "held pose candidate; movement deferred", "human_approved": False,
               "required_next_checks": ["export payload preservation", "exported pose gate", "four views", "live consumer preview"]}
    (target / "creation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("HELD_POSE_WRITTEN -- the posture is authored; the verdict is still yours.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
