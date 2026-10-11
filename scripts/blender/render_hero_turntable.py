# SPDX-License-Identifier: MIT
"""Render a seamless 360-degree studio turntable MP4 & GIF of Character02 using RTX 4090 OptiX.

Renders frames in Blender Cycles (OptiX), then encodes using ffmpeg into:
  - 1080x1080 H.264 MP4 (clean 24fps loop)
  - 720x720 high-quality palette-matched GIF (for Discord/socials)

Usage:
  blender -b <blend> --python scripts/blender/render_hero_turntable.py -- \\
      <manny_refpose.json> <manny_anim_poses.json> <out_dir> [--frames 72] [--samples 48] [--res 1080]
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
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


def setup_optix(scene, samples=48):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == "OPTIX")
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPTIX"
    scene.render.film_transparent = False


def setup_studio(scene):
    if scene.world is None:
        scene.world = bpy.data.worlds.new("StudioWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.025, 0.028, 0.035, 1.0)
        bg.inputs[1].default_value = 1.0

    # Ground shadow catcher
    mesh = bpy.data.meshes.new("FloorMesh")
    floor = bpy.data.objects.new("StudioFloor", mesh)
    scene.collection.objects.link(floor)
    verts = [(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    floor.is_shadow_catcher = True


def setup_lighting():
    for ob in list(bpy.data.objects):
        if ob.type == "LIGHT":
            bpy.data.objects.remove(ob, do_unlink=True)

    # Key
    kd = bpy.data.lights.new("Key", type="AREA")
    kd.energy = 750.0
    kd.size = 1.5
    kd.color = (1.0, 0.94, 0.88)
    k = bpy.data.objects.new("Key", kd)
    k.location = (-1.8, -2.4, 2.5)
    k.rotation_euler = (math.radians(48), 0, math.radians(-38))
    bpy.context.collection.objects.link(k)

    # Fill
    fd = bpy.data.lights.new("Fill", type="AREA")
    fd.energy = 250.0
    fd.size = 2.0
    fd.color = (0.72, 0.84, 1.0)
    f = bpy.data.objects.new("Fill", fd)
    f.location = (2.2, -1.8, 1.6)
    f.rotation_euler = (math.radians(35), 0, math.radians(45))
    bpy.context.collection.objects.link(f)

    # Rim
    rd = bpy.data.lights.new("Rim", type="SPOT")
    rd.energy = 1400.0
    rd.spot_size = math.radians(65)
    rd.spot_blend = 0.35
    rd.color = (0.05, 0.80, 1.0)
    r = bpy.data.objects.new("Rim", rd)
    r.location = (0.7, 2.0, 2.3)
    r.rotation_euler = (math.radians(-130), 0, math.radians(160))
    bpy.context.collection.objects.link(r)


def apply_smirk():
    facial = [ob for ob in bpy.data.objects if ob.type == "MESH" and ob.data.shape_keys]
    weights = {
        "mouth-corner-puller": 0.25,
        "mouth-upward-retraction": 0.15,
        "eyebrows-left-up": 0.20,
        "eye-left-slit": 0.10,
        "mouth-open": 0.05,
    }
    for ob in facial:
        for k in ob.data.shape_keys.key_blocks:
            if k.name in weights:
                k.value = weights[k.name]
    bpy.context.view_layer.update()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("ref_pose")
    p.add_argument("anim_poses")
    p.add_argument("out_dir")
    p.add_argument("--frames", type=int, default=72)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--res", type=int, default=1080)
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "turntable_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    manny = json.loads(Path(args.ref_pose).read_text())
    poses_list = json.loads(Path(args.anim_poses).read_text())["poses"]
    pose = next(p for p in poses_list if p["anim"] == "MM_Idle" and abs(p["time"] - 3.78) < 0.05)
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
    setup_optix(scene, samples=args.samples)
    setup_studio(scene)
    setup_lighting()
    apply_smirk()

    pelvis_scale = rest["pelvis"][1][2] / manny_ref["pelvis"][2]
    G, Pp = {}, {}
    for n in order:
        src = pose["bones"][n]
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

    # Camera setup for turntable
    cam = bpy.data.objects.new("TurntableCam", bpy.data.cameras.new("TurntableCam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 55.0

    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.render.image_settings.file_format = "PNG"

    orbit_radius = 3.6
    orbit_height = 1.05
    look_target = Vector((0.0, 0.0, 0.95))

    print(f"Starting Turntable Render: {args.frames} frames @ {args.res}x{args.res}, {args.samples} samples OptiX...")
    t0 = time.time()

    for f in range(1, args.frames + 1):
        angle = (f - 1) / args.frames * 2.0 * math.pi
        x = -math.sin(angle) * orbit_radius
        y = -math.cos(angle) * orbit_radius
        cam.location = Vector((x, y, orbit_height))
        cam.rotation_euler = (look_target - cam.location).to_track_quat("-Z", "Y").to_euler()

        frame_file = frames_dir / f"frame_{f:04d}.png"
        scene.render.filepath = str(frame_file)
        bpy.ops.render.render(write_still=True)
        if f % 12 == 0 or f == args.frames:
            elapsed = time.time() - t0
            fps = f / elapsed
            print(f"Rendered frame {f}/{args.frames} ({fps:.2f} fps, {elapsed:.1f}s elapsed)")

    render_time = time.time() - t0
    print(f"Frames rendered in {render_time:.2f}s. Encoding MP4 and GIF with ffmpeg...")

    out_mp4 = out_dir / "05_Hero_Turntable_360.mp4"
    out_gif = out_dir / "05_Hero_Turntable_360.gif"

    # Encode MP4 (H.264, 24fps)
    cmd_mp4 = [
        "ffmpeg", "-y",
        "-framerate", "24",
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        str(out_mp4),
    ]
    subprocess.run(cmd_mp4, check=True)
    print(f"MP4 encoded: {out_mp4}")

    # Encode GIF (palettegen + paletteuse for pristine color fidelity)
    cmd_gif = [
        "ffmpeg", "-y",
        "-i", str(out_mp4),
        "-filter_complex",
        "[0:v] fps=24,scale=640:-1:flags=lanczos,split [a][b];[a] palettegen=stats_mode=diff [p];[b][p] paletteuse=dither=bayer:bayer_scale=3",
        str(out_gif),
    ]
    subprocess.run(cmd_gif, check=True)
    print(f"GIF encoded: {out_gif}")

    # Clean up frames directory to save disk space
    shutil.rmtree(frames_dir)
    print(f"TURNTABLE COMPLETE in {time.time() - t0:.2f}s total!")


if __name__ == "__main__":
    main()
