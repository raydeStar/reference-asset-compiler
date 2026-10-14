"""Fixed, source-bound review of the game rig, including neck and both wrists.

Use the final game blend, not the intermediate native-rig portrait. The receipt
names the exact source and keeps artistic acceptance explicitly pending.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply_idle(rig, manny_dir, animation="MM_Idle", pose_index=0):
    """Apply a recorded Manny pose in component space, retaining this rig's lengths."""
    reference = json.loads((manny_dir / "manny_refpose.json").read_text())
    poses = json.loads((manny_dir / "manny_anim_poses.json").read_text())["poses"]
    pose = [p for p in poses if p["anim"] == animation][pose_index]
    axes = np.diag([1., -1., 1.])
    parents = {b["name"]: b["parent"] for b in reference["bones"]}
    reference_pos = {b["name"]: np.array(b["pos"]) for b in reference["bones"]}
    rest = {b.name: (axes @ np.array(b.matrix_local.to_3x3()) @ axes,
                     axes @ np.array(b.head_local) * 100.) for b in rig.data.bones}
    rest["root"] = (np.eye(3), np.zeros(3))
    order = []

    def visit(name):
        if name in order:
            return
        if parents[name]:
            visit(parents[name])
        order.append(name)

    for name in parents:
        visit(name)
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    rotations, positions = {}, {}
    scale = rest["pelvis"][1][2] / reference_pos["pelvis"][2]
    for name in order:
        source = pose["bones"][name]
        x, y, z, w = source["quat"]
        rotations[name] = np.array(Quaternion((w, x, y, z)).to_matrix())
        parent = parents[name]
        if parent is None:
            positions[name] = np.zeros(3)
        elif name == "pelvis":
            positions[name] = np.array(source["pos"]) * scale
        else:
            offset = rest[parent][0].T @ (rest[name][1] - rest[parent][1])
            positions[name] = positions[parent] + rotations[parent] @ offset
        if name != "root" and name in rig.pose.bones:
            matrix = Matrix((axes @ rotations[name] @ axes).tolist()).to_4x4()
            matrix.translation = Vector(axes @ positions[name] / 100.)
            rig.pose.bones[name].matrix = matrix
            bpy.context.view_layer.update()
    return {"animation": pose["anim"], "time": pose["time"],
            "reference_sha256": sha(manny_dir / "manny_refpose.json"),
            "poses_sha256": sha(manny_dir / "manny_anim_poses.json")}


def setup_scene(device, resolution, samples):
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = device
    scene.cycles.samples = samples
    scene.cycles.seed = 23
    scene.cycles.use_denoising = True
    if device == "GPU":
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for item in preferences.devices:
            item.use = item.type == "OPTIX"
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.world = bpy.data.worlds.new("SeamReviewWorld")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.18, 0.18, 0.18, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.5
    for name, position, energy, size in (
        ("Key", (2, -3, 4), 450, 3), ("Fill", (-3, -1, 2), 300, 3),
        ("Rim", (1, 3, 3), 400, 2)):
        lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(lamp)
        lamp.location = position
        lamp.rotation_euler = (Vector((0, 0, 1)) - lamp.location).to_track_quat("-Z", "Y").to_euler()
        lamp.data.energy, lamp.data.shape, lamp.data.size = energy, "DISK", size
    camera = bpy.data.objects.new("SeamReviewCamera", bpy.data.cameras.new("SeamReviewCamera"))
    scene.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.clip_start = 0.01
    scene.camera = camera
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--manny-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("CPU", "GPU"), default="CPU")
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--only", help="comma-separated shot names")
    parser.add_argument("--animation", default="MM_Idle")
    parser.add_argument("--pose-index", type=int, default=0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, out = args.source.resolve(), args.out.resolve()
    if out.exists():
        raise FileExistsError("Choose a fresh review directory; old evidence has tenure, sir.")
    out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    source_inventory = {}
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        vertices = [obj.matrix_world @ v.co for v in obj.data.vertices]
        source_inventory[obj.name] = {
            "vertices": len(vertices), "faces": len(obj.data.polygons),
            "bounds": [[min(v[i] for v in vertices), max(v[i] for v in vertices)] for i in range(3)],
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots]}
    pose = apply_idle(rig, args.manny_dir.resolve(), args.animation, args.pose_index)
    scene = setup_scene(args.device, args.resolution, args.samples)
    wanted = set(args.only.split(",")) if args.only else None
    shots = []

    def render(name, center, angle, scale, elevation=math.degrees(math.atan(0.08))):
        if wanted and name not in wanted:
            return
        direction = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)),
                            math.tan(math.radians(elevation)))).normalized()
        camera = scene.camera
        camera.location = Vector(center) + direction * 5
        camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        camera.data.ortho_scale = scale
        scene.render.filepath = str(out / (name + ".png"))
        bpy.ops.render.render(write_still=True)
        shots.append({"name": name, "center": list(center), "angle": angle, "scale": scale,
                      "elevation_degrees": elevation,
                      "sha256": sha(out / (name + ".png"))})

    for view, angle in (("front", 0), ("three-quarter", 35), ("side", 90), ("back", 180)):
        render("full-" + view, (0, 0, 0.94), angle, 1.95)
        render("neck-" + view, (0, -0.015, 1.53), angle, 0.38)
    for side in ("l", "r"):
        center = rig.matrix_world @ rig.pose.bones["hand_" + side].head
        center.z -= 0.035
        render("wrist-" + side, center, 30 if side == "l" else -30, 0.28)
        render("wrist-" + side + "-outer", center, 100 if side == "l" else -100, 0.28)
    render("full-top-three-quarter", (0, 0, 1.0), 35, 1.95, 40)
    render("shoulders-top-three-quarter", (0, -0.015, 1.45), 35, 0.8, 40)
    neck = rig.pose.bones["neck_01"]
    neck.rotation_mode = "QUATERNION"
    neck.rotation_quaternion = neck.rotation_quaternion @ Quaternion(Vector((0, 1, 0)), math.radians(25))
    bpy.context.view_layer.update()
    render("neck-turn", (0, -0.015, 1.55), 0, 0.44)
    report = {"source": str(source), "source_sha256": sha(source), "blender": bpy.app.version_string,
              "script_sha256": sha(__file__), "pose": pose, "inventory": source_inventory,
              "device": args.device, "samples": args.samples, "seed": 23, "shots": shots,
              "production_ready": False, "human_review": "pending"}
    (out / "review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SEAM REVIEW: the game rig has faced the lights, sir. " + str(out))


if __name__ == "__main__":
    main()
