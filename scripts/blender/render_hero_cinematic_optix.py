# SPDX-License-Identifier: MIT
"""Cinematic high-resolution ray-traced showcase renders of Character02 using RTX 4090 OptiX.

Renders 4 studio-lit, high-sample hero shots:
  1. Full-body three-quarter stance (MM_Idle)
  2. Portrait close-up with 85mm depth of field, signature Arcane smirk, and Aether cyan rim
  3. Combat attack strike pose (MM_Attack_01)
  4. Dynamic dash action pose (MM_Dash)

Usage:
  blender -b <blend> --python scripts/blender/render_hero_cinematic_optix.py -- \\
      <manny_refpose.json> <manny_anim_poses.json> <out_dir>
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

M_UE = np.diag([1.0, -1.0, 1.0])
P_AX = np.diag([1.0, -1.0, 1.0])


def qmat(q):
    x, y, z, w = q
    return np.array(Quaternion((w, x, y, z)).to_matrix())


def setup_optix_cycles(scene, samples=256):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == "OPTIX")
        print(f"Device: {d.name}, Type: {d.type}, Use: {d.use}")
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPTIX"
    scene.render.film_transparent = False


def setup_studio_environment(scene):
    if scene.world is None:
        scene.world = bpy.data.worlds.new("StudioWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        # Subtle dark slate charcoal studio tone
        bg.inputs[0].default_value = (0.028, 0.030, 0.038, 1.0)
        bg.inputs[1].default_value = 1.0

    # Large floor plane with shadow catcher for natural contact grounding
    mesh = bpy.data.meshes.new("StudioFloorMesh")
    floor = bpy.data.objects.new("StudioFloor", mesh)
    scene.collection.objects.link(floor)
    verts = [(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)]
    faces = [(0, 1, 2, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    floor.is_shadow_catcher = True


def setup_cinematic_lighting():
    # Clear existing lights
    for ob in list(bpy.data.objects):
        if ob.type == "LIGHT":
            bpy.data.objects.remove(ob, do_unlink=True)

    # 1. Warm Key Light (Key from upper front-left)
    key_data = bpy.data.lights.new("Key_Warm", type="AREA")
    key_data.energy = 850.0
    key_data.size = 1.4
    key_data.color = (1.0, 0.94, 0.88)
    key = bpy.data.objects.new("Key_Warm", key_data)
    key.location = (-1.8, -2.4, 2.5)
    key.rotation_euler = (math.radians(48), 0, math.radians(-38))
    bpy.context.collection.objects.link(key)

    # 2. Cool Fill Light (Soft fill from right)
    fill_data = bpy.data.lights.new("Fill_Cool", type="AREA")
    fill_data.energy = 280.0
    fill_data.size = 2.2
    fill_data.color = (0.72, 0.84, 1.0)
    fill = bpy.data.objects.new("Fill_Cool", fill_data)
    fill.location = (2.2, -1.8, 1.6)
    fill.rotation_euler = (math.radians(35), 0, math.radians(45))
    bpy.context.collection.objects.link(fill)

    # 3. Aether Cyan Rim Light (Dramatic backlight skimming hair and coat)
    rim_data = bpy.data.lights.new("Rim_AetherCyan", type="SPOT")
    rim_data.energy = 1600.0
    rim_data.spot_size = math.radians(65)
    rim_data.spot_blend = 0.35
    rim_data.color = (0.05, 0.80, 1.0)
    rim = bpy.data.objects.new("Rim_AetherCyan", rim_data)
    rim.location = (0.7, 2.0, 2.3)
    rim.rotation_euler = (math.radians(-130), 0, math.radians(160))
    bpy.context.collection.objects.link(rim)

    # 4. Subtle Under-Bounce
    bounce_data = bpy.data.lights.new("Bounce_Under", type="AREA")
    bounce_data.energy = 80.0
    bounce_data.size = 3.0
    bounce_data.color = (0.6, 0.7, 0.8)
    bounce = bpy.data.objects.new("Bounce_Under", bounce_data)
    bounce.location = (0, -1.0, 0.1)
    bounce.rotation_euler = (math.radians(-60), 0, 0)
    bpy.context.collection.objects.link(bounce)


def apply_signature_smirk():
    """Apply the signature Arcane smirk and brow arch to facial shape keys."""
    facial_objects = [ob for ob in bpy.data.objects if ob.type == "MESH" and ob.data.shape_keys]
    smirk_weights = {
        "mouth-corner-puller": 0.25,
        "mouth-upward-retraction": 0.15,
        "eyebrows-left-up": 0.20,
        "eye-left-slit": 0.10,
        "mouth-open": 0.05,
    }
    for ob in facial_objects:
        for key in ob.data.shape_keys.key_blocks:
            if key.name in smirk_weights:
                key.value = smirk_weights[key.name]
    bpy.context.view_layer.update()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ref_path, poses_path, out_dir = argv[0], argv[1], Path(argv[2]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manny = json.loads(Path(ref_path).read_text())
    poses_list = json.loads(Path(poses_path).read_text())["poses"]
    poses = {f"{p['anim']}_{p['time']:.2f}".replace(".", "p"): p for p in poses_list}
    parents = {b["name"]: b["parent"] for b in manny["bones"]}
    manny_ref = {b["name"]: np.array(b["pos"]) for b in manny["bones"]}

    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    rest = {}
    for b in rig.data.bones:
        Bm = np.array(b.matrix_local.to_3x3())
        rest[b.name] = (M_UE @ Bm @ P_AX, M_UE @ np.array(b.head_local) * 100.0)
    rest["root"] = (np.eye(3), np.zeros(3))

    order = []
    def visit(n):
        if n in order:
            return
        if parents[n]:
            visit(parents[n])
        order.append(n)
    for n in parents:
        visit(n)

    scene = bpy.context.scene
    setup_optix_cycles(scene, samples=256)
    setup_studio_environment(scene)
    setup_cinematic_lighting()
    apply_signature_smirk()

    cam = bpy.data.objects.new("CinematicCam", bpy.data.cameras.new("CinematicCam"))
    scene.collection.objects.link(cam)
    scene.camera = cam

    pelvis_scale = rest["pelvis"][1][2] / manny_ref["pelvis"][2]

    def apply_pose(pose_data):
        G, Pp = {}, {}
        for n in order:
            if pose_data is None or pose_data.get("bones") is None:
                G[n] = rest[n][0]
                Pp[n] = rest[n][1]
                continue
            src = pose_data["bones"][n]
            G[n] = qmat(src["quat"])
            p = parents[n]
            if p is None:
                Pp[n] = np.zeros(3)
            elif n == "pelvis":
                Pp[n] = np.array(src["pos"]) * pelvis_scale
            else:
                local = rest[p][0].T @ (rest[n][1] - rest[p][1])
                Pp[n] = Pp[p] + G[p] @ local

        for n in order:
            if n == "root" or n not in rig.pose.bones:
                continue
            mat = Matrix((M_UE @ G[n] @ P_AX).tolist()).to_4x4()
            mat.translation = Vector(M_UE @ Pp[n] / 100.0)
            rig.pose.bones[n].matrix = mat
            bpy.context.view_layer.update()
        return Pp

    shots = [
        {
            "name": "01_Hero_Idle_FullBody",
            "pose": poses.get("MM_Idle_3p78"),
            "res": (2048, 2048),
            "lens": 52.0,
            "cam_offset": Vector((-1.6, -3.2, 1.15)),
            "look_target": Vector((0.0, 0.0, 0.95)),
            "portrait": False,
            "dof": False,
        },
        {
            "name": "02_Hero_Portrait_Smirk",
            "pose": poses.get("MM_Idle_3p78"),
            "res": (2048, 2048),
            "lens": 85.0,
            "cam_offset": Vector((-0.25, -1.65, 0.02)),
            "look_target": Vector((0.0, -0.02, 0.0)),
            "portrait": True,
            "dof": True,
            "fstop": 2.8,
        },
        {
            "name": "03_Hero_Combat_Attack",
            "pose": poses.get("MM_Attack_01_0p25"),
            "res": (2048, 2048),
            "lens": 46.0,
            "cam_offset": Vector((-1.4, -2.8, 1.25)),
            "look_target": Vector((0.0, 0.0, 1.05)),
            "portrait": False,
            "dof": False,
        },
        {
            "name": "04_Hero_Action_Dash",
            "pose": poses.get("MM_Dash_0p19"),
            "res": (2048, 2048),
            "lens": 46.0,
            "cam_offset": Vector((-1.6, -2.4, 0.90)),
            "look_target": Vector((0.0, 0.0, 0.85)),
            "portrait": False,
            "dof": False,
        },
    ]

    receipts = []
    t_start_all = time.time()

    for shot in shots:
        print(f"\n==========================================")
        print(f"--- Rendering {shot['name']} ---")
        t_shot_start = time.time()

        scene.render.resolution_x, scene.render.resolution_y = shot["res"]
        cam.data.lens = shot["lens"]

        # Apply pose first so bone positions are evaluated
        Pp = apply_pose(shot["pose"])

        # Compute root follow offset for animations with translation
        follow = Vector(M_UE @ Pp["pelvis"] / 100.0)
        follow.z = 0.0

        if shot.get("portrait"):
            # Anchor camera to head bone location
            head_pos = Vector(M_UE @ Pp["head"] / 100.0)
            target = head_pos + shot["look_target"]
            cam.location = head_pos + shot["cam_offset"]
        else:
            target = shot["look_target"] + follow
            cam.location = shot["cam_offset"] + follow

        direction = target - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

        if shot.get("dof"):
            cam.data.dof.use_dof = True
            cam.data.dof.focus_distance = direction.length
            cam.data.dof.aperture_fstop = shot["fstop"]
        else:
            cam.data.dof.use_dof = False

        out_path = out_dir / f"{shot['name']}.png"
        scene.render.filepath = str(out_path)
        bpy.ops.render.render(write_still=True)
        shot_duration = time.time() - t_shot_start
        print(f"Saved: {out_path} ({shot_duration:.2f}s)")

        receipts.append({
            "name": shot["name"],
            "resolution": shot["res"],
            "samples": scene.cycles.samples,
            "lens_mm": shot["lens"],
            "cam_location": cam.location.to_tuple(3),
            "render_time_s": round(shot_duration, 2),
            "output_file": str(out_path.name),
        })

    total_duration = time.time() - t_start_all
    summary = {
        "device": "NVIDIA GeForce RTX 4090 (OptiX)",
        "samples": scene.cycles.samples,
        "total_render_time_s": round(total_duration, 2),
        "shots": receipts,
    }
    (out_dir / "showcase-receipts.json").write_text(json.dumps(summary, indent=2))
    print(f"\nALL 4 SHOWCASE SHOTS COMPLETED in {total_duration:.2f}s")


if __name__ == "__main__":
    main()
