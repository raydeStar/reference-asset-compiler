"""Numerical operations on the existing UE-local animation packet format.

Units are centimetres, quaternions are xyzw. Contact observations are explicit:
a sync marker is a moment, not permission to nail a foot down for half a walk.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def validate_packet(packet):
    bones = packet.get("bones")
    if not isinstance(bones, list) or not bones or len(set(bones)) != len(bones):
        raise ValueError("packet needs unique, ordered bones")
    if not all(isinstance(b, str) and b for b in bones):
        raise ValueError("invalid bone names")
    clips = packet.get("clips")
    if not isinstance(clips, dict) or not clips:
        raise ValueError("packet needs named clips")
    aliases = set(clips)
    for name, clip in clips.items():
        fps, frames = clip.get("fps"), clip.get("frames")
        if not isinstance(frames, int) or isinstance(frames, bool) or frames < 2:
            raise ValueError(f"{name}: at least two frames required")
        if not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 240:
            raise ValueError(f"{name}: invalid sample rate")
        duration = (frames - 1) / fps
        length = clip.get("length", duration)
        if not isinstance(length, (int, float)) or not math.isfinite(length) or abs(length - duration) > 1 / fps + 1e-6:
            raise ValueError(f"{name}: duration disagrees with frame count")
        if not isinstance(clip.get("loop"), bool) or not isinstance(clip.get("root_motion"), bool):
            raise ValueError(f"{name}: explicit loop and root_motion booleans required")
        tracks = clip.get("tracks", {})
        if not set(bones) <= set(tracks) or set(tracks) - set(bones) - {"root"}:
            raise ValueError(f"{name}: track set disagrees with skeleton")
        for bone, track in tracks.items():
            a = np.asarray(track, dtype=float)
            if a.shape != (frames, 7) or not np.isfinite(a).all():
                raise ValueError(f"{name}/{bone}: finite [frames,7] transforms required")
            if np.max(np.abs(np.linalg.norm(a[:, 3:], axis=1) - 1)) > 0.002:
                raise ValueError(f"{name}/{bone}: non-unit quaternion")
        for alias in clip.get("also_as", []):
            if alias in aliases:
                raise ValueError(f"duplicate clip alias: {alias}")
            aliases.add(alias)
        for moment in (clip.get("contacts_s") or {}).values():
            if not math.isfinite(moment) or not 0 <= moment <= duration + 1e-4:
                raise ValueError(f"{name}: contact marker outside clip")
    return packet


def validate_skeleton(skeleton, bones):
    if skeleton.get("bones") != bones or skeleton.get("units") != "cm":
        raise ValueError("skeleton order/units do not match the packet")
    if skeleton.get("rotation") != "xyzw" or skeleton.get("up_axis") != "Z":
        raise ValueError("expected Z-up, xyzw skeleton")
    parents = skeleton.get("parents", [])
    if len(parents) != len(bones) or any(not isinstance(p, int) or not -1 <= p < i
                                       for i, p in enumerate(parents)):
        raise ValueError("skeleton must be parent-first and acyclic")
    return skeleton


def matrices(tracks):
    a = np.asarray(tracks, dtype=float)
    result = np.broadcast_to(np.eye(4), (*a.shape[:-1], 4, 4)).copy()
    result[..., :3, :3] = Rotation.from_quat(a[..., 3:].reshape(-1, 4)).as_matrix().reshape(*a.shape[:-1], 3, 3)
    result[..., :3, 3] = a[..., :3]
    return result


def transforms(mats):
    a = np.asarray(mats)
    q = Rotation.from_matrix(a[..., :3, :3].reshape(-1, 3, 3)).as_quat().reshape(*a.shape[:-2], 4)
    return np.concatenate((a[..., :3, 3], q), axis=-1)


def world_matrices(clip, skeleton):
    names = skeleton["bones"]
    local = matrices(np.stack([clip["tracks"][b] for b in names], axis=1))
    world = local.copy()
    # A packet can carry a synthetic export root outside the native rig's bone list.
    basis = matrices(skeleton.get("armature_transform", [0, 0, 0, 0, 0, 0, 1]))
    root = basis @ matrices(clip["tracks"]["root"]) if "root" not in names and "root" in clip["tracks"] else basis
    for i, parent in enumerate(skeleton["parents"]):
        world[:, i] = (world[:, parent] if parent >= 0 else root) @ local[:, i]
    return world


def sample_clip(clip, times):
    old = np.arange(clip["frames"]) / clip["fps"]
    times = np.clip(np.asarray(times), 0, old[-1])
    tracks = {}
    for bone, raw in clip["tracks"].items():
        a = np.asarray(raw)
        xyz = np.stack([np.interp(times, old, a[:, j]) for j in range(3)], axis=1)
        q = Slerp(old, Rotation.from_quat(a[:, 3:]))(times).as_quat()
        tracks[bone] = np.concatenate((xyz, q), axis=1).tolist()
    return tracks


def _aim(rotation, old, new):
    u, v = np.asarray(old), np.asarray(new)
    u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
    cross, dot = np.cross(u, v), float(np.clip(np.dot(u, v), -1, 1))
    if np.linalg.norm(cross) < 1e-10:
        if dot > 0:
            return rotation
        axis = np.cross(u, np.eye(3)[np.argmin(np.abs(u))])
        axis /= np.linalg.norm(axis)
        return Rotation.from_rotvec(axis * np.pi).as_matrix() @ rotation
    return Rotation.from_rotvec(cross / np.linalg.norm(cross) * math.acos(dot)).as_matrix() @ rotation


def solve_contact(clip, skeleton, operation):
    """Two-bone IK with an explicit effector offset and explicit actor travel.

    Offsets permit heel/ball contacts without flattening the foot orientation.
    No contacts are inferred from a marker or a low ankle. Unreachable targets
    fail, leaving the source unchanged, instead of stretching accepted bones.
    """
    names, parents = skeleton["bones"], skeleton["parents"]
    chain = [names.index(b) for b in operation["chain"]]
    if len(chain) != 3 or parents[chain[1]] != chain[0] or parents[chain[2]] != chain[1]:
        raise ValueError("contact chain must be three consecutive bones")
    targets = operation.get('sync_effectors', [])
    if len(set(targets)) != len(targets) or any(n not in names or names.index(n) in chain for n in targets):
        raise ValueError('sync_effectors must name distinct non-chain bones')
    conventional_target = 'ik_' + names[chain[-1]]
    if conventional_target in names and conventional_target not in targets:
        raise ValueError('declare the existing IK target in sync_effectors before moving its limb')
    start, end = operation["interval_s"]
    duration = (clip["frames"] - 1) / clip["fps"]
    if not 0 <= start < end <= duration + 1e-6:
        raise ValueError("contact interval outside clip")
    offset = np.asarray(operation.get("offset_cm", [0, 0, 0]), dtype=float)
    actor = np.asarray(operation.get("actor_velocity_cm_s", [0, 0, 0]), dtype=float)
    blend = float(operation.get("blend_s", 0.08))
    if not 0 <= blend <= (end - start) / 2:
        raise ValueError("contact blend exceeds half the support interval")
    world = world_matrices(clip, skeleton)
    times = np.arange(clip["frames"]) / clip["fps"]
    target = np.asarray(operation["target_cm"], dtype=float)
    if any(a.shape != (3,) or not np.isfinite(a).all() for a in (offset, actor, target)):
        raise ValueError("contact vectors must contain three finite values")
    local = matrices(np.stack([clip["tracks"][b] for b in names], axis=1))
    a, b, c = chain
    for f, t in enumerate(times):
        if not start <= t <= end:
            continue
        w = world[f].copy()
        p, joint, tip = w[[a, b, c], :3, 3]
        l1, l2 = np.linalg.norm(joint - p), np.linalg.norm(tip - joint)
        weight = min(1., (t - start) / blend, (end - t) / blend) if blend else 1.
        weight = weight * weight * (3 - 2 * weight)
        if weight < 1e-10:
            continue
        wanted = target - actor * t - w[c, :3, :3] @ offset
        wanted = tip + weight * (wanted - tip)
        distance = np.linalg.norm(wanted - p)
        if distance >= l1 + l2 - 1e-6 or distance <= abs(l1 - l2) + 1e-6:
            raise ValueError(f"unreachable contact at {t:.4f}s; adjust pelvis/target first")
        direction = (wanted - p) / distance
        pole = np.asarray(operation['pole'], dtype=float) if 'pole' in operation else joint - p
        if pole.shape != (3,) or not np.isfinite(pole).all():
            raise ValueError('contact pole must have three finite values')
        pole -= direction * np.dot(pole, direction)
        if np.linalg.norm(pole) < 1e-6:
            pole = np.asarray(operation.get("pole", [0, 1, 0]), dtype=float)
            pole -= direction * np.dot(pole, direction)
        if np.linalg.norm(pole) < 1e-6:
            raise ValueError("contact pole is collinear with limb")
        pole /= np.linalg.norm(pole)
        along = (l1 * l1 - l2 * l2 + distance * distance) / (2 * distance)
        new_joint = p + direction * along + pole * math.sqrt(max(0, l1 * l1 - along * along))
        desired = {a: w[a].copy(), b: w[b].copy(), c: w[c].copy()}
        desired[a][:3, :3] = _aim(w[a, :3, :3], joint - p, new_joint - p)
        desired[b][:3, :3] = _aim(w[b, :3, :3], tip - joint, wanted - new_joint)
        desired[b][:3, 3], desired[c][:3, 3] = new_joint, wanted
        for i in chain:
            parent = parents[i]
            parent_world = desired[parent] if parent in desired else w[parent] if parent >= 0 else w[i] @ np.linalg.inv(local[f, i])
            local[f, i] = np.linalg.inv(parent_world) @ desired[i]
    values = transforms(local)
    for i in chain:
        clip["tracks"][names[i]] = values[:, i].tolist()
    for target_name in targets:
        updated = world_matrices(clip, skeleton)
        i = names.index(target_name)
        parent = parents[i]
        parent_world = updated[:, parent] if parent >= 0 else updated[:, i] @ np.linalg.inv(local[:, i])
        clip['tracks'][target_name] = transforms(np.linalg.inv(parent_world) @ updated[:, chain[-1]]).tolist()


def derive_packet(packet, operations, skeleton=None):
    validate_packet(packet)
    result = copy.deepcopy(packet)
    if skeleton:
        validate_skeleton(skeleton, packet["bones"])
    for op in operations:
        kind = op.get("op")
        if kind == "select":
            selected = op["clips"]
            if not selected or len(set(selected)) != len(selected) or set(selected) - set(result["clips"]):
                raise ValueError("selection must name existing, unique clips")
            result["clips"] = {n: result["clips"][n] for n in selected}
            continue
        if op.get("clip") not in result["clips"]:
            raise ValueError("operation names an absent clip")
        clip = result["clips"][op["clip"]]
        if kind == "rotation_offset":
            bone = op["bone"]
            angles = np.asarray(op["degrees_xyz"], dtype=float)
            if bone not in clip["tracks"] or bone == "root" or angles.shape != (3,) or not np.isfinite(angles).all() or np.max(abs(angles)) > 30:
                raise ValueError("rotation offset needs an existing non-root bone and <=30 degree angles")
            a = np.asarray(clip["tracks"][bone])
            a[:, 3:] = (Rotation.from_quat(a[:, 3:]) * Rotation.from_euler("xyz", angles, degrees=True)).as_quat()
            clip["tracks"][bone] = a.tolist()
        elif kind == "retime":
            # Retiming a gameplay transition requires editing its controller too.
            # Refuse it here instead of silently invalidating impact/handoff timing.
            if clip.get("transition") or clip.get("timing") or clip.get("events") or clip.get("root_motion") or 'root' in clip['tracks']:
                raise ValueError("retime refuses transitions, event-bound clips and root motion")
            factor = float(op["duration_factor"])
            if not math.isfinite(factor) or not 0.5 <= factor <= 2:
                raise ValueError("duration_factor must be 0.5..2")
            old_duration = (clip["frames"] - 1) / clip["fps"]
            frames = max(2, round((clip["frames"] - 1) * factor) + 1)
            clip["tracks"] = sample_clip(clip, np.linspace(0, old_duration, frames))
            actual = (frames - 1) / clip["fps"] / old_duration
            clip.update(frames=frames, length=(frames - 1) / clip["fps"])
            if clip.get("contacts_s"):
                clip["contacts_s"] = {k: t * actual for k, t in clip["contacts_s"].items()}
            if clip.get("speed_cm_s"):
                clip["speed_cm_s"] /= actual
        elif kind == "solve_contact":
            if skeleton is None:
                raise ValueError("contact solving requires a hash-bound skeleton")
            solve_contact(clip, skeleton, op)
        else:
            raise ValueError(f"unsupported animation operation: {kind}")
    return validate_packet(result)


def measure_packet(packet, skeleton, cases):
    validate_packet(packet)
    validate_skeleton(skeleton, packet["bones"])
    result = {}
    for name, case in cases.items():
        if name not in packet["clips"]:
            raise ValueError(f"benchmark clip missing: {name}")
        clip = packet["clips"][name]
        world = world_matrices(clip, skeleton)
        times = np.arange(clip["frames"]) / clip["fps"]
        position = world[..., :3, 3]
        q = transforms(world)[..., 3:]
        gap = np.linalg.norm(position[-1] - position[0], axis=-1)
        angle = np.rad2deg(2 * np.arccos(np.clip(np.abs(np.sum(q[-1] * q[0], axis=-1)), 0, 1)))
        row = {"duration_s": float(times[-1]), "loop": clip["loop"],
               "loop_position_gap_cm": float(gap.max()) if clip["loop"] else None,
               "loop_angle_gap_deg": float(angle.max()) if clip["loop"] else None,
               "peak_joint_speed_cm_s": float(np.linalg.norm(np.diff(position, axis=0), axis=-1).max() * clip["fps"]),
               "contacts": [], "contact_markers_s": clip.get("contacts_s"),
               "sample_rates": {}}
        for hz in (30, 60, 120):
            t = np.linspace(0, times[-1], round(times[-1] * hz) + 1)
            sampled = dict(clip, tracks=sample_clip(clip, t), frames=len(t), fps=hz)
            row["sample_rates"][str(hz)] = {"samples": len(t), "finite": bool(np.isfinite(world_matrices(sampled, skeleton)).all()),
                                           "scope": "offline interpolation, not game-frame-rate proof"}
        for contact in case.get("contacts", []):
            i = skeleton["bones"].index(contact["bone"])
            start, end = contact["interval_s"]
            if not 0 <= start < end <= times[-1] + 1e-6:
                raise ValueError(f"{name}: invalid contact interval")
            selected = (times >= start) & (times <= end)
            if np.count_nonzero(selected) < 2:
                raise ValueError("contact interval must cover at least two samples")
            offset = np.asarray(contact.get("offset_cm", [0, 0, 0]))
            actor = np.asarray(contact.get("actor_velocity_cm_s", [0, 0, 0]))
            if any(a.shape != (3,) or not np.isfinite(a).all() for a in (offset, actor)):
                raise ValueError('contact measurements need finite three-component vectors')
            points = (world[:, i, :3, :3] @ offset + position[:, i] + times[:, None] * actor)[selected]
            floor = contact.get("floor_z_cm")
            if floor is not None and not math.isfinite(floor):
                raise ValueError('contact floor must be finite')
            row["contacts"].append({"bone": contact["bone"], "interval_s": [start, end],
                "drift_cm": float(np.linalg.norm(points - points[0], axis=-1).max()),
                "peak_speed_cm_s": float(np.linalg.norm(np.diff(points, axis=0), axis=-1).max() * clip["fps"]),
                "penetration_cm": float(max(0, floor - points[:, 2].min())) if floor is not None else None,
                "scope": "declared skeletal contact point with explicit actor velocity; not skinned-surface proof"})
        result[name] = row
    transitions = []
    for name, case in cases.items():
        for join in case.get("joins", []):
            target = join["to"]
            c1, c2 = packet["clips"][name], packet["clips"][target]
            t1, t2 = float(join["from_s"]), float(join["to_s"])
            if not 1 / c1["fps"] <= t1 <= (c1["frames"] - 1) / c1["fps"] or not 0 <= t2 <= (c2["frames"] - 2) / c2["fps"]:
                raise ValueError("join must leave a sample on either side for velocity")
            a = world_matrices(dict(c1, tracks=sample_clip(c1, [t1-1/c1['fps'], t1])), skeleton)[..., :3, 3]
            b = world_matrices(dict(c2, tracks=sample_clip(c2, [t2, t2+1/c2['fps']])), skeleton)[..., :3, 3]
            transitions.append({"from": name, "to": target, "from_s": t1, "to_s": t2,
                "position_gap_cm": float(np.linalg.norm(a[-1] - b[0], axis=-1).max()),
                "velocity_gap_cm_s": float(np.linalg.norm((a[-1]-a[0])*c1['fps'] - (b[-1]-b[0])*c2['fps'], axis=-1).max()),
                "scope": "direct component-space join; actual controller blend is a separate check"})
    return {"clips": result, "transitions": transitions, "human_approved": False,
            "gameplay_tested": False, "mesh_intersections": "not_measured"}
