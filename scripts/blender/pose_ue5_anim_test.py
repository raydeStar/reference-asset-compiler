"""Pose a Manny-conformant character with real Manny animation frames and render it.

This predicts what UE's IK retargeter produces when both retarget poses share
Manny's bone rotations: every bone takes Manny's component-space rotation, the
pelvis translation scales by pelvis height, and every other bone keeps this
character's own bone lengths. Arms that reach the knees, a twisted wrist or a
collapsing shoulder show up here before anything reaches Unreal.

blender -b <name>_UE5.blend --python pose_ue5_anim_test.py -- \
    <manny_refpose.json> <manny_anim_poses.json> <out_dir> [--res 640]

RAC_RENDER_DEVICE=CPU (rebuild_character.py --device CPU sets it) renders with Cycles on the CPU:
EEVEE needs a GPU even in the background.
"""
import json
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

M_UE = np.diag([1.0, -1.0, 1.0])
P_AX = np.diag([1.0, -1.0, 1.0])


def qmat(q):
    x, y, z, w = q
    return np.array(Quaternion((w, x, y, z)).to_matrix())


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ref_path, poses_path, out = argv[0], argv[1], Path(argv[2]).resolve()
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 640
    out.mkdir(parents=True, exist_ok=True)
    manny = json.loads(Path(ref_path).read_text())
    poses = json.loads(Path(poses_path).read_text())["poses"]
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
    if os.environ.get("RAC_RENDER_DEVICE", "").upper() == "CPU":
        scene.render.engine = "CYCLES"
        scene.cycles.device, scene.cycles.samples, scene.cycles.use_denoising = "CPU", 8, True
    else:
        scene.render.engine = "BLENDER_EEVEE"
    print("RENDER ENGINE", scene.render.engine, scene.cycles.device if scene.render.engine == "CYCLES" else "")
    scene.render.resolution_x, scene.render.resolution_y = res, int(res * 1.25)
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.42, 0.42, 0.42, 1)
    cam = bpy.data.objects.new("TestCam", bpy.data.cameras.new("TestCam"))
    scene.collection.objects.link(cam)
    cam.data.lens = float(argv[argv.index("--lens") + 1]) if "--lens" in argv else 50.0
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    scene.camera = cam
    views = {"front": (Vector((0, -5.2, 1.0)),), "three_quarter": (Vector((-3.4, -3.9, 1.15)),),
             "side": (Vector((5.2, 0, 1.0)),), "back": (Vector((1.2, 4.6, 1.9)),)}
    wanted = argv[argv.index("--views") + 1].split(",") if "--views" in argv else ["front", "three_quarter", "side"]
    views = {k: v for k, v in views.items() if k in wanted}
    pelvis_scale = rest["pelvis"][1][2] / manny_ref["pelvis"][2]
    receipts = []
    for pose in [{"anim": "RefPose", "time": 0, "bones": None}] + poses:
        if only and pose["anim"] not in only:
            continue
        G, Pp = {}, {}
        for n in order:
            if pose["bones"] is None:
                G[n] = rest[n][0]
                Pp[n] = rest[n][1]
                continue
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
        hand = (Pp["middle_03_l"] + Pp["middle_03_r"]) / 2 if "middle_03_l" in Pp else None
        tag = f"{pose['anim']}_{pose['time']:.2f}".replace(".", "p")
        receipts.append({"pose": tag, "fingertip_height_cm": None if hand is None else float(hand[2]),
                         "hand_l_cm": Pp["hand_l"].round(2).tolist(), "head_cm": Pp["head"].round(2).tolist()})
        # Follow the pelvis so root motion stays in frame.
        follow = Vector(M_UE @ Pp["pelvis"] / 100.0)
        follow.z = 0.0
        for view, (loc,) in views.items():
            cam.location = loc + follow
            target = Vector((0, 0, 0.92)) + follow
            if "--follow-z" in argv:              # clips off the ground (hanging, gliding)
                target.z = Pp["spine_03"][2] / 100.0
            cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = str(out / f"{tag}_{view}.png")
            bpy.ops.render.render(write_still=True)
    (out / "pose-receipts.json").write_text(json.dumps(receipts, indent=1))
    print("POSE TEST DONE", out)


if __name__ == "__main__":
    main()
