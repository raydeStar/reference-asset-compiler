# SPDX-License-Identifier: MIT
"""Profile-bounded stance, arm relaxation and measured sole contact on the native rig."""

import math

import numpy as np
from mathutils import Matrix

import clip_retarget as cr
import transition_clips as tc
from skin_geometry import matrix, deform


def polish_idle(packet, rig, boots, spec):
    ix = rig.index
    clip = packet["clips"]["MM_Idle"]
    inverse = np.linalg.inv(rig.rest)
    legs = tc.Legs(rig)
    worlds = [
        tc.fk(rig, np.array([matrix(clip["tracks"][n][f]) for n in rig.names]))
        for f in range(clip["frames"])
    ]
    reference = worlds[0].copy()
    families = {
        n: [ix[n]] + [ix[b.name] for b in rig.obj.data.bones[n].children_recursive]
        for n in rig.names
    }

    def rotate(w, bone, rotation):
        ids = families[bone]
        pivot = w[ix[bone], :3, 3].copy()
        w[ids, :3, 3] = pivot + (w[ids, :3, 3] - pivot) @ rotation.T
        w[ids, :3, :3] = rotation @ w[ids, :3, :3]

    def sole(w, side):
        return min(
            float(deform(data, w @ inverse)[ids[side], 2].min())
            for _, data, ids in boots
            if ids[side]
        )

    goals = {}
    for s, sign in [("l", 1), ("r", -1)]:
        foot = reference[ix["foot_" + s]]
        direction = reference[ix["ball_" + s], :3, 3] - foot[:3, 3]
        yaw = math.radians(sign * spec["toe_out_degrees"])
        target = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
        flat = direction.copy()
        flat[2] = 0
        corrected = cr._aim(foot, flat, target)[:3, :3]
        position = foot[:3, 3].copy()
        position[0] = sign * spec["stance_width_cm"] / 200
        goals[s] = (position, corrected)
    measurements = []
    for frame, w in enumerate(worlds):
        pelvis = ix["pelvis"]
        shift = (reference[pelvis, :3, 3] - w[pelvis, :3, 3]) * (1 - spec["pelvis_motion_scale"])
        w[families["pelvis"], :3, 3] += shift
        for side, sign in [("l", 1), ("r", -1)]:
            for bone, child, key in [
                ("upperarm", "lowerarm", "upperarm_direction"),
                ("lowerarm", "hand", "forearm_direction"),
            ]:
                a, b = ix[bone + "_" + side], ix[child + "_" + side]
                current = w[b, :3, 3] - w[a, :3, 3]
                original = reference[b, :3, 3] - reference[a, :3, 3]
                target = np.array(spec.get(key + "_" + side, spec[key]), float)
                target[0] *= sign
                target += spec["arm_motion_scale"] * (
                    current / np.linalg.norm(current) - original / np.linalg.norm(original)
                )
                rotated = cr._aim(w[a], current, target)
                rotate(w, bone + "_" + side, rotated[:3, :3] @ w[a, :3, :3].T)
            a = w[ix["thumb_02_" + side], :3, 3] - w[ix["thumb_01_" + side], :3, 3]
            b = w[ix["index_02_" + side], :3, 3] - w[ix["index_01_" + side], :3, 3]
            a /= np.linalg.norm(a)
            b /= np.linalg.norm(b)
            axis = np.cross(a, b)
            if np.linalg.norm(axis) > 1e-8:
                angle = min(
                    math.radians(spec["thumb_adduction_degrees"]), math.acos(np.clip(a @ b, -1, 1))
                )
                rotate(w, "thumb_01_" + side, np.array(Matrix.Rotation(angle, 3, axis)))
        # Both soles agree on the floor before breathing is allowed to take credit.
        positions = {s: g[0].copy() for s, g in goals.items()}
        for _ in range(8):
            for s in "lr":
                legs.place(w, s, positions[s], goals[s][1], knee_keep=0.08)
                positions[s][2] += spec["sole_clearance_cm"] / 100 - sole(w, s)
        for source, target in cr.IK_PINS:
            if target in ix:
                w[ix[target]] = w[ix[source]].copy()
        measurements.append({"frame": frame, "sole_cm": {s: sole(w, s) * 100 for s in "lr"}})
    worlds[-1] = worlds[0].copy()
    for f, w in enumerate(worlds):
        local = rig.world_to_local(w)
        for n in rig.names:
            clip["tracks"][n][f] = [float(v) for v in cr.ue_from_matrix(local[ix[n]])]
    clip.setdefault("layers", {})["idle_polish"] = spec
    return {"measurements": measurements, "mesh_weights_and_bind_changed": False}
