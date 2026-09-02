"""Derive mascot_biped_tail joint landmarks from approved, source-bound evidence.

Nothing here is drawn by hand. Limb joints come from the reviewer-passed joint
ring centers that were fitted to the AI surface during retopology; the spine,
head, and tail come from cross-sections of the exact texture-approved payload.
The ring profile lives in the retopology frame, so the similarity transform
recorded by the texture payload binding is applied first.

Outputs a landmark JSON bound to the payload hash plus overlay renders (joints
and bones drawn over the semi-transparent mesh) for the reviewer.

Usage:
  blender -b --factory-startup --python scripts/blender/derive_mascot_landmarks.py -- \
      <production.fbx> <fitted-ring-profile.json> <texture-payload-binding.json> \
      <out_dir> [--tail-y-fraction 0.14] [--tail-z-fraction 0.39]
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def world_vertices(obj) -> np.ndarray:
    coords = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    matrix = np.asarray(obj.matrix_world)
    return coords @ matrix[:3, :3].T + matrix[:3, 3]


def slab_centroid(points: np.ndarray, z: float, half: float, x_window: float, x_center: float):
    sel = (np.abs(points[:, 2] - z) < half) & (np.abs(points[:, 0] - x_center) < x_window)
    if sel.sum() < 8:
        return None
    return points[sel].mean(axis=0)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    fbx_path, rings_path, binding_path, out_dir = (Path(a).resolve() for a in argv[:4])
    tail_y_fraction = arg(argv, "--tail-y-fraction", 0.14, float)
    tail_z_fraction = arg(argv, "--tail-z-fraction", 0.39, float)
    out_dir.mkdir(parents=True, exist_ok=True)
    landmarks_path = out_dir / "mascot-landmarks.json"
    if landmarks_path.exists():
        raise RuntimeError("Refusing to overwrite landmark evidence: {0}".format(landmarks_path))

    rings = json.loads(rings_path.read_text(encoding="utf-8-sig"))
    binding = json.loads(binding_path.read_text(encoding="utf-8-sig"))
    scale = float(binding["uniform_scale_applied"])
    translation = np.asarray(binding["translation_applied"], dtype=np.float64)

    def to_payload(p):
        return np.asarray(p, dtype=np.float64) * scale + translation

    ring = {r["id"]: to_payload(r["center"]) for r in rings["rings"]}

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Expected exactly one mesh in the payload")
    body = meshes[0]
    pts = world_vertices(body)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    height = float(hi[2] - lo[2])

    # The rings were named from the viewer's side. The payload faces -Y, so the
    # character's own left is +X. Bones use the character's side.
    side = {"l": "right", "r": "left"}
    joints: dict[str, list[float]] = {}
    for s, ring_side in side.items():
        joints["shoulder_" + s] = ring[ring_side + "_upper_arm_support"].tolist()
        joints["elbow_" + s] = ring[ring_side + "_elbow"].tolist()
        joints["wrist_" + s] = ring[ring_side + "_wrist"].tolist()
        joints["hip_" + s] = ring[ring_side + "_upper_thigh_support"].tolist()
        joints["knee_" + s] = ring[ring_side + "_knee"].tolist()
        joints["ankle_" + s] = ring[ring_side + "_ankle"].tolist()
    for s in "lr":
        if (s == "l") != (joints["shoulder_" + s][0] > joints["shoulder_" + ("r" if s == "l" else "l")][0]):
            raise RuntimeError("Side mapping is inconsistent with ring positions")
    raw_ring_joints = {k: list(v) for k, v in joints.items()}

    # Torso midline from cross-sections of the payload, arms and tail excluded
    # by a lateral window around the neck ring's x.
    neck = ring["neck"]
    mid_x = float(neck[0])

    # The rings were fitted as retopology support guides, not pivots, and the
    # fit moved the two sides by different amounts. The payload itself is
    # bilaterally symmetric about the midline to within a few millimetres, so
    # limb pivots are mirrored: each pair takes the mean lateral offset, y and
    # z. Raw ring positions are kept in the file for audit.
    symmetrized = {}
    for base in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
        left = np.asarray(joints[base + "_l"])
        right = np.asarray(joints[base + "_r"])
        offset = 0.5 * ((left[0] - mid_x) + (mid_x - right[0]))
        y = 0.5 * (left[1] + right[1])
        z = 0.5 * (left[2] + right[2])
        joints[base + "_l"] = [mid_x + offset, y, z]
        joints[base + "_r"] = [mid_x - offset, y, z]
        symmetrized[base] = {"lateral_offset_m": float(offset),
                             "left_right_delta_before_m": float(np.linalg.norm(left - np.array([2 * mid_x - right[0], right[1], right[2]])))}
    hips_mid = (np.asarray(joints["hip_l"]) + np.asarray(joints["hip_r"])) * 0.5
    pelvis = np.array([hips_mid[0], hips_mid[1], hips_mid[2] + 0.03 * height / 1.8])
    neck_base = np.array([mid_x, float(neck[1]), float(neck[2])])
    torso_x_window = 0.2 * height / 1.8
    spine_points = []
    for fraction in (0.25, 0.5, 0.75):
        z = pelvis[2] + (neck_base[2] - pelvis[2]) * fraction
        centroid = slab_centroid(pts, z, 0.03, torso_x_window, mid_x)
        if centroid is None:
            centroid = pelvis + (neck_base - pelvis) * fraction
        spine_points.append([mid_x, float(centroid[1]), float(z)])
    # Hand and foot ends come from the surface beyond the wrist and ankle.
    for s in "lr":
        wrist = np.asarray(joints["wrist_" + s])
        elbow = np.asarray(joints["elbow_" + s])
        direction = wrist - elbow
        direction /= np.linalg.norm(direction)
        rel = pts - wrist
        along = rel @ direction
        radial = np.linalg.norm(rel - np.outer(along, direction), axis=1)
        beyond = along[(along > 0) & (radial < 0.14 * height / 1.8)]
        reach = float(np.percentile(beyond, 95)) if len(beyond) else 0.08 * height / 1.8
        joints["hand_end_" + s] = (wrist + direction * max(0.05, 0.85 * reach)).tolist()
        ankle = np.asarray(joints["ankle_" + s])
        foot_sel = (np.abs(pts[:, 0] - ankle[0]) < 0.12 * height / 1.8) & (pts[:, 2] < ankle[2] + 0.02)
        toe_y = float(pts[foot_sel][:, 1].min()) if foot_sel.sum() else ankle[1] - 0.1
        joints["toe_" + s] = [float(ankle[0]), toe_y + 0.02, float(lo[2] + 0.02)]

    top_sel = np.abs(pts[:, 0] - mid_x) < torso_x_window
    top_z = float(pts[top_sel][:, 2].max())
    head_z = neck_base[2] + 0.30 * (top_z - neck_base[2])
    head_centroid = slab_centroid(pts, head_z, 0.04, 0.35 * height / 1.8, mid_x)
    # The head pivot sits at the skull base above the neck, not at the face
    # centroid; blend only a third of the way toward the slab centroid.
    centroid_y = float(head_centroid[1]) if head_centroid is not None else float(neck_base[1])
    head = [mid_x, float(neck_base[1]) + 0.35 * (centroid_y - float(neck_base[1])), float(head_z)]
    head_end = [mid_x, head[1], top_z - 0.03 * height / 1.8]
    joints.update({
        "root": [0.0, 0.0, 0.0],
        "pelvis": pelvis.tolist(),
        "spine_01": spine_points[0], "spine_02": spine_points[1], "spine_03": spine_points[2],
        "neck_01": neck_base.tolist(), "head": head, "head_end": head_end,
    })
    shoulder_z = 0.5 * (joints["shoulder_l"][2] + joints["shoulder_r"][2])
    for s, sign in (("l", 1.0), ("r", -1.0)):
        joints["clavicle_" + s] = [mid_x + sign * 0.05 * height / 1.8, spine_points[2][1], shoulder_z + 0.02]

    # Tail: behind the body (+Y) and below the hips. Ordered from its root by
    # distance, binned into a centerline, and sampled at thirds.
    tail_sel = (pts[:, 1] > tail_y_fraction * height) & (pts[:, 2] < tail_z_fraction * height)
    tail_pts = pts[tail_sel]
    if len(tail_pts) < 60:
        raise RuntimeError("Tail selection found too few vertices: {0}".format(len(tail_pts)))
    root_index = int(np.argmin(np.linalg.norm(tail_pts - pelvis, axis=1)))
    distances = np.linalg.norm(tail_pts - tail_pts[root_index], axis=1)
    order = np.argsort(distances)
    bins = 10
    edges = np.linspace(0.0, distances.max() + 1e-6, bins + 1)
    centers = []
    for i in range(bins):
        sel = (distances >= edges[i]) & (distances < edges[i + 1])
        if sel.sum() < 3:
            raise RuntimeError("Tail centerline bin {0} is empty; tail is not one tube".format(i))
        centers.append(tail_pts[sel].mean(axis=0))
    centers = np.asarray(centers)
    seg = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    def at(fraction):
        target = fraction * arc[-1]
        return np.array([np.interp(target, arc, centers[:, k]) for k in range(3)])
    tail_root = at(0.0)
    tail_root[1] -= 0.02 * height / 1.8  # start just inside the body
    joints.update({
        "tail_01": tail_root.tolist(), "tail_02": at(1.0 / 3.0).tolist(),
        "tail_03": at(2.0 / 3.0).tolist(), "tail_end": at(1.0).tolist(),
    })
    _ = order

    bones = {
        "root": ("root", None),
        "pelvis": ("pelvis", "spine_01"), "spine_01": ("spine_01", "spine_02"),
        "spine_02": ("spine_02", "spine_03"), "spine_03": ("spine_03", "neck_01"),
        "neck_01": ("neck_01", "head"), "head": ("head", "head_end"),
        "clavicle_l": ("clavicle_l", "shoulder_l"), "upperarm_l": ("shoulder_l", "elbow_l"),
        "lowerarm_l": ("elbow_l", "wrist_l"), "hand_l": ("wrist_l", "hand_end_l"),
        "clavicle_r": ("clavicle_r", "shoulder_r"), "upperarm_r": ("shoulder_r", "elbow_r"),
        "lowerarm_r": ("elbow_r", "wrist_r"), "hand_r": ("wrist_r", "hand_end_r"),
        "thigh_l": ("hip_l", "knee_l"), "calf_l": ("knee_l", "ankle_l"), "foot_l": ("ankle_l", "toe_l"),
        "thigh_r": ("hip_r", "knee_r"), "calf_r": ("knee_r", "ankle_r"), "foot_r": ("ankle_r", "toe_r"),
        "tail_01": ("tail_01", "tail_02"), "tail_02": ("tail_02", "tail_03"), "tail_03": ("tail_03", "tail_end"),
        # Manny-convention IK roots: non-deforming, at the origin under root.
        "ik_foot_root": ("root", "ik_root_end"), "ik_hand_root": ("root", "ik_root_end"),
    }
    joints["ik_root_end"] = [0.0, 0.0, 0.05]
    payload = {
        "schema": "reference-asset-compiler.mascot-landmarks.v1",
        "asset_id": rings["asset_id"],
        "skeleton_profile": "mascot_biped_tail",
        "payload_fbx": str(fbx_path), "payload_fbx_sha256": sha256(fbx_path),
        "ring_profile": str(rings_path), "ring_profile_sha256": sha256(rings_path),
        "ring_profile_source_sha256": rings.get("source_sha256"),
        "binding_report": str(binding_path), "binding_report_sha256": sha256(binding_path),
        "ring_to_payload_transform": {"uniform_scale": scale, "translation": translation.tolist()},
        "side_convention": "payload faces -Y; character left is +X; ring ids were viewer-side names, so right_* rings feed _l bones",
        "coordinate_space": "payload_world_meters",
        "height_m": height, "midline_x": mid_x,
        "tail_selection": {"y_min_m": tail_y_fraction * height, "z_max_m": tail_z_fraction * height,
                           "vertices": int(len(tail_pts)), "arc_length_m": float(arc[-1])},
        "joints": joints,
        "raw_ring_joints": raw_ring_joints,
        "symmetrization": symmetrized,
        "bones": {name: {"head": h, "tail": t,
                         "parent": ("root" if name.startswith("ik_") else None),
                         "deform": not (name == "root" or name.startswith("ik_"))}
                  for name, (h, t) in bones.items()},
        "reviewed_by": None,
        "review_status": "derived_pending_overlay_review",
    }
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Overlay renders: translucent body, emissive joints and bones.
    scene = bpy.context.scene
    for c in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if c in scene.render.bl_rna.properties["engine"].enum_items.keys():
            scene.render.engine = c
            break
    ghost = bpy.data.materials.new("Ghost")
    ghost.use_nodes = True
    g = ghost.node_tree.nodes["Principled BSDF"]
    g.inputs["Base Color"].default_value = (0.75, 0.75, 0.78, 1.0)
    g.inputs["Alpha"].default_value = 0.28
    if hasattr(ghost, "surface_render_method"):
        ghost.surface_render_method = "BLENDED"
    else:
        ghost.blend_method = "BLEND"
    body.data.materials.clear()
    body.data.materials.append(ghost)

    def emissive(name, rgb):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        emission = b.inputs.get("Emission Color") or b.inputs.get("Emission")
        emission.default_value = (*rgb, 1.0)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = 3.0
        return m
    mats = {"l": emissive("L", (1.0, 0.45, 0.05)), "r": emissive("R", (0.1, 0.5, 1.0)),
            "c": emissive("C", (0.2, 1.0, 0.3))}
    joint_radius = 0.012 * height / 1.8
    for name, (h, t) in bones.items():
        if name.startswith("ik_"):
            continue
        s = "l" if name.endswith("_l") else "r" if name.endswith("_r") else "c"
        a = Vector(joints[h])
        b = Vector(joints[t]) if t else Vector(joints[h]) + Vector((0, 0, 0.1))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=joint_radius, location=a)
        bpy.context.object.data.materials.append(mats[s])
        d = b - a
        if d.length > 1e-6:
            bpy.ops.mesh.primitive_cylinder_add(radius=joint_radius * 0.4, depth=d.length,
                                                location=(a + b) * 0.5)
            cyl = bpy.context.object
            cyl.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
            cyl.data.materials.append(mats[s])

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.18, 0.18, 0.18, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = world
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 16
    centre = Vector((lo + hi) * 0.5)
    extent = float(max(hi - lo))
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (extent * 1.25) / (2.0 * math.tan(fov * 0.5))
    views = {}
    for view, angle in (("front", 0.0), ("three-quarter", 45.0), ("side", 90.0), ("back", 180.0)):
        a = math.radians(angle)
        cam.location = centre + Vector((math.sin(a) * distance, -math.cos(a) * distance, extent * 0.08))
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = out_dir / "overlay-{0}.png".format(view)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views[view] = sha256(path)
    payload["overlay_sha256"] = views
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("[LANDMARKS] {0} joints={1} tail_arc={2:.3f}m".format(landmarks_path, len(joints), arc[-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
