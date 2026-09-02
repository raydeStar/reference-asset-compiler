"""Derive a Manny-compatible (ue5_manny) joint set for an unrigged humanoid mesh.

The portable, licence-free rig route. Auto-Rig Pro remains the higher-quality
option when a machine has it; this exists so a clean clone can still rig a
humanoid and run every downstream gate.

Sources, in order of trust:

1. **The mesh.** Height, torso midline, cross-section centroids for the spine,
   the crotch, per-leg centerlines, per-arm centerlines (A-pose or T-pose), toe
   and fingertip reach. Every limb pivot that can be measured is measured.
2. **Epic's Manny reference pose** (`profiles/rigging/manny-reference-pose.json`,
   extracted from the UE 5.8 template mesh) for the proportions the mesh cannot
   disambiguate: where the spine joints sit along the torso, the twist-bone
   fractions, the IK helper bones, and the finger and metacarpal layout, which
   is transplanted onto the measured hand, rotated to the measured forearm and
   scaled to the measured forearm length.

Output is the same landmark schema `rig_from_landmarks.py` consumes for the
mascot, plus overlay renders for review. Fingers are a template fit, not a
measurement: review the overlay before trusting hand deformation.

Usage:
  blender -b --factory-startup --python-exit-code 1 --python \
      scripts/blender/derive_humanoid_landmarks.py -- \
      <mesh.fbx|glb> <out_dir> [--profile profiles/skeletons/ue5_manny.json] \
      [--manny profiles/rigging/manny-reference-pose.json]
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

ROOT = Path(__file__).resolve().parents[2]


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


def import_mesh(path: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif path.suffix.lower() in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        raise RuntimeError("Unsupported mesh type {0}".format(path.suffix))
    for obj in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh in {0}".format(path))
    return meshes


def all_points(meshes) -> np.ndarray:
    chunks = []
    for obj in meshes:
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.asarray(obj.matrix_world)
        chunks.append(co @ m[:3, :3].T + m[:3, 3])
    return np.vstack(chunks)


def slab(points, z, half):
    return points[np.abs(points[:, 2] - z) < half]


def centerline(points, axis_values, bins):
    """Bin points along a scalar coordinate and return bin centroids and arc."""
    order = np.argsort(axis_values)
    points = points[order]
    axis_values = axis_values[order]
    edges = np.linspace(axis_values[0], axis_values[-1] + 1e-9, bins + 1)
    centres = []
    for i in range(bins):
        sel = (axis_values >= edges[i]) & (axis_values < edges[i + 1])
        if sel.sum() >= 3:
            centres.append(points[sel].mean(axis=0))
    centres = np.asarray(centres)
    seg = np.linalg.norm(np.diff(centres, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    return centres, arc


def at_arc(centres, arc, fraction):
    target = fraction * arc[-1]
    return np.array([np.interp(target, arc, centres[:, k]) for k in range(3)])


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    mesh_path, out_dir = (Path(a).resolve() for a in argv[:2])
    profile_path = Path(arg(argv, "--profile", str(ROOT / "profiles/skeletons/ue5_manny.json"))).resolve()
    manny_path = Path(arg(argv, "--manny", str(ROOT / "profiles/rigging/manny-reference-pose.json"))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    landmarks_path = out_dir / "humanoid-landmarks.json"
    if landmarks_path.exists():
        raise RuntimeError("Refusing to overwrite landmark evidence: {0}".format(landmarks_path))
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    manny = json.loads(manny_path.read_text(encoding="utf-8-sig"))

    meshes = import_mesh(mesh_path)
    pts = all_points(meshes)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    H = float(hi[2] - lo[2])
    if H < 0.3:
        raise RuntimeError("Mesh is {0:.3f} m tall; expected metres".format(H))

    # Manny template in the Blender frame: UE component (x, y, z) cm, +Y forward
    # -> Blender (x, -y, z) m, -Y forward, normalized by Manny's height.
    MH = float(manny["height_cm"])
    T = {name: np.array([b["position_cm"][0], -b["position_cm"][1], b["position_cm"][2]]) / MH
         for name, b in manny["bones"].items()}
    parents = {name: b["parent"] for name, b in manny["bones"].items()}

    # Torso midline: central cluster at hip and chest heights.
    def central(z, half, window):
        s = slab(pts, z, half)
        s = s[np.abs(s[:, 0] - (lo[0] + hi[0]) * 0.5) < window]
        return s
    hip_band = central(lo[2] + 0.55 * H, 0.03 * H, 0.16 * H)
    mid_x = float(np.median(hip_band[:, 0]))

    def torso_centroid(z, window=0.12 * H):
        s = slab(pts, z, 0.02 * H)
        s = s[np.abs(s[:, 0] - mid_x) < window]
        return s.mean(axis=0) if len(s) >= 8 else None

    joints = {}
    notes = []

    # Spine chain at Manny's height fractions, y from the mesh cross-section.
    for name in ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head"):
        z = lo[2] + T[name][2] * H
        c = torso_centroid(z, 0.12 * H if not name.startswith("neck") and name != "head" else 0.10 * H)
        y = float(c[1]) if c is not None else float(T[name][1] * H)
        joints[name] = [mid_x, y, float(z)]
    head_top = float(hi[2])

    # Crotch: lowest z where the centre column is still populated.
    crotch_z = None
    for z in np.arange(lo[2] + 0.55 * H, lo[2] + 0.30 * H, -0.01 * H):
        s = slab(pts, z, 0.01 * H)
        if np.count_nonzero(np.abs(s[:, 0] - mid_x) < 0.015 * H) == 0:
            crotch_z = float(z)
            break
    if crotch_z is None:
        crotch_z = lo[2] + 0.47 * H
        notes.append("crotch not detected; Manny proportion used")

    # Legs: per side, centreline from just below the crotch to the ankle.
    ankle_z = lo[2] + 0.046 * H
    for side, sign in (("l", 1.0), ("r", -1.0)):
        leg = pts[(pts[:, 2] < crotch_z) & (pts[:, 2] > ankle_z - 0.01 * H) & (sign * (pts[:, 0] - mid_x) > 0)]
        if len(leg) < 50:
            raise RuntimeError("leg_{0}: too few vertices below the crotch".format(side))
        centres, _arc = centerline(leg, -leg[:, 2], 24)
        # centres run top (high z) to bottom; interpolate on z directly.
        zs = centres[:, 2]
        def leg_xy(z):
            idx = np.argsort(zs)
            return np.array([np.interp(z, zs[idx], centres[idx, k]) for k in (0, 1)])
        hip_z = crotch_z + 0.04 * H
        knee_z = ankle_z + 0.5 * (hip_z - ankle_z)
        hx, hy = leg_xy(crotch_z - 0.02 * H)
        kx, ky = leg_xy(knee_z)
        ax_, ay = leg_xy(ankle_z + 0.02 * H)
        joints["thigh_" + side] = [float(hx), float(hy), float(hip_z)]
        joints["calf_" + side] = [float(kx), float(ky), float(knee_z)]
        joints["foot_" + side] = [float(ax_), float(ay), float(ankle_z)]
        foot = pts[(pts[:, 2] < lo[2] + 0.06 * H) & (np.abs(pts[:, 0] - ax_) < 0.08 * H)]
        toe_y = float(foot[:, 1].min()) if len(foot) else ay - 0.14 * H
        joints["ball_" + side] = [float(ax_), toe_y + 0.4 * (ay - toe_y), float(lo[2] + 0.005 * H)]
        joints["toe_end_" + side] = [float(ax_), toe_y, float(lo[2] + 0.005 * H)]

    # Arms: points outside the torso width between hip and head height.
    for side, sign in (("l", 1.0), ("r", -1.0)):
        arm = pts[(sign * (pts[:, 0] - mid_x) > 0.14 * H) & (pts[:, 2] > lo[2] + 0.40 * H) & (pts[:, 2] < lo[2] + 0.90 * H)]
        if len(arm) < 50:
            raise RuntimeError("arm_{0}: too few vertices beyond the torso".format(side))
        lateral = sign * (arm[:, 0] - mid_x)
        centres, arc = centerline(arm, lateral, 20)
        hand_len = 0.105 * H
        total = arc[-1]
        if total < 0.3 * H:
            notes.append("arm_{0}: short arc {1:.2f} m; sleeve or pose may be tight to the body".format(side, total))
        wrist = at_arc(centres, arc, max(0.0, (total - hand_len) / total))
        shoulder_template = np.array([mid_x + sign * T["upperarm_l"][0] * H,
                                      joints["spine_05"][1] + (T["upperarm_l"][1] - T["spine_05"][1]) * H,
                                      lo[2] + T["upperarm_l"][2] * H])
        shoulder = shoulder_template
        elbow = 0.5 * (shoulder + wrist)
        # Bend the elbow toward the measured centreline at its mid arc.
        mid_c = at_arc(centres, arc, 0.5 * (total - hand_len) / total)
        elbow = 0.5 * elbow + 0.5 * mid_c
        hand_end = at_arc(centres, arc, 1.0)
        joints["clavicle_" + side] = [mid_x + sign * T["clavicle_l"][0] * H, joints["spine_05"][1] + (T["clavicle_l"][1] - T["spine_05"][1]) * H, lo[2] + T["clavicle_l"][2] * H]
        joints["upperarm_" + side] = shoulder.tolist()
        joints["lowerarm_" + side] = elbow.tolist()
        joints["hand_" + side] = wrist.tolist()
        joints["hand_end_" + side] = hand_end.tolist()

        # Fingers and metacarpals: Manny's hand layout rotated onto the measured
        # forearm and scaled to the measured forearm length.
        manny_fore = T["hand_l"] - T["lowerarm_l"]
        mesh_fore = wrist - elbow
        scale = float(np.linalg.norm(mesh_fore) / np.linalg.norm(manny_fore))
        mirror = np.array([sign, 1.0, 1.0])
        rot = Vector(manny_fore * mirror).rotation_difference(Vector(mesh_fore)).to_matrix()
        R = np.asarray(rot)
        for name in T:
            if not name.endswith("_l"):
                continue
            base = name[:-2]
            if not any(base.startswith(d) for d in ("thumb", "index", "middle", "ring", "pinky")):
                continue
            offset = (T[name] - T["hand_l"]) * mirror * scale
            joints[base + "_" + side] = (wrist + R @ offset).tolist()

    # Twist bones by Manny's fraction along each limb segment.
    def frac(a, b, f):
        a = np.asarray(joints[a])
        b = np.asarray(joints[b])
        return (a + (b - a) * f).tolist()
    for side in "lr":
        joints["upperarm_twist_01_" + side] = frac("upperarm_" + side, "lowerarm_" + side, 1 / 3)
        joints["upperarm_twist_02_" + side] = frac("upperarm_" + side, "lowerarm_" + side, 2 / 3)
        joints["lowerarm_twist_01_" + side] = frac("lowerarm_" + side, "hand_" + side, 1 / 3)
        joints["lowerarm_twist_02_" + side] = frac("lowerarm_" + side, "hand_" + side, 2 / 3)
        joints["thigh_twist_01_" + side] = frac("thigh_" + side, "calf_" + side, 1 / 3)
        joints["thigh_twist_02_" + side] = frac("thigh_" + side, "calf_" + side, 2 / 3)
        joints["calf_twist_01_" + side] = frac("calf_" + side, "foot_" + side, 1 / 3)
        joints["calf_twist_02_" + side] = frac("calf_" + side, "foot_" + side, 2 / 3)
    joints["root"] = [0.0, 0.0, float(lo[2])]
    joints["ik_foot_root"] = joints["root"]
    joints["ik_hand_root"] = joints["root"]
    joints["ik_foot_l"] = joints["foot_l"]
    joints["ik_foot_r"] = joints["foot_r"]
    joints["ik_hand_gun"] = joints["hand_r"]
    joints["ik_hand_l"] = joints["hand_l"]
    joints["ik_hand_r"] = joints["hand_r"]
    joints["head_end"] = [mid_x, joints["head"][1], head_top - 0.02 * H]
    joints["ik_root_end"] = [0.0, 0.0, float(lo[2]) + 0.05 * H]

    required = list(profile["required_bones"])
    optional = list(profile.get("optional_bones", []))
    wanted = [b for b in required + optional if b in T or b == "root"]
    if profile.get("root_bone") and profile["root_bone"] not in wanted:
        wanted.insert(0, profile["root_bone"])
    missing = [b for b in required if b not in joints]
    if missing:
        raise RuntimeError("Derivation left required bones without joints: {0}".format(missing))

    # Tails: the designated child, else a short continuation of the parent's direction.
    chain_child = {"pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "spine_04",
                   "spine_04": "spine_05", "spine_05": "neck_01", "neck_01": "neck_02", "neck_02": "head", "head": "head_end",
                   "root": "ik_root_end", "ik_foot_root": "ik_root_end", "ik_hand_root": "ik_root_end"}
    for side in "lr":
        chain_child.update({
            "clavicle_" + side: "upperarm_" + side, "upperarm_" + side: "lowerarm_" + side,
            "lowerarm_" + side: "hand_" + side, "hand_" + side: "middle_01_" + side,
            "thigh_" + side: "calf_" + side, "calf_" + side: "foot_" + side, "foot_" + side: "ball_" + side,
            "ball_" + side: "toe_end_" + side,
            "upperarm_twist_01_" + side: "upperarm_twist_02_" + side, "upperarm_twist_02_" + side: "lowerarm_" + side,
            "lowerarm_twist_01_" + side: "lowerarm_twist_02_" + side, "lowerarm_twist_02_" + side: "hand_" + side,
            "thigh_twist_01_" + side: "thigh_twist_02_" + side, "thigh_twist_02_" + side: "calf_" + side,
            "calf_twist_01_" + side: "calf_twist_02_" + side, "calf_twist_02_" + side: "foot_" + side,
        })
        for digit in ("thumb", "index", "middle", "ring", "pinky"):
            if digit != "thumb":
                chain_child["{0}_metacarpal_{1}".format(digit, side)] = "{0}_01_{1}".format(digit, side)
            chain_child["{0}_01_{1}".format(digit, side)] = "{0}_02_{1}".format(digit, side)
            chain_child["{0}_02_{1}".format(digit, side)] = "{0}_03_{1}".format(digit, side)
            # fingertip: continue the last phalanx by its own length
            p2 = np.asarray(joints["{0}_02_{1}".format(digit, side)])
            p3 = np.asarray(joints["{0}_03_{1}".format(digit, side)])
            joints["{0}_tip_{1}".format(digit, side)] = (p3 + (p3 - p2)).tolist()
            chain_child["{0}_03_{1}".format(digit, side)] = "{0}_tip_{1}".format(digit, side)
    for side in "lr":
        for name in ("ik_foot_", "ik_hand_"):
            b = np.asarray(joints[name + side])
            joints[name + side + "_end"] = (b + np.array([0, 0, 0.05 * H])).tolist()
            chain_child[name + side] = name + side + "_end"
    joints["ik_hand_gun_end"] = (np.asarray(joints["ik_hand_gun"]) + np.array([0, 0, 0.05 * H])).tolist()
    chain_child["ik_hand_gun"] = "ik_hand_gun_end"

    bones = {}
    for name in wanted:
        parent = parents.get(name)
        if name == "root":
            parent = None
        elif parent not in wanted:
            parent = "root"
        tail = chain_child.get(name)
        if tail is None or tail not in joints:
            raise RuntimeError("No tail rule for bone {0}".format(name))
        bones[name] = {"head": name, "tail": tail, "parent": parent,
                       "deform": not (name == "root" or name.startswith("ik_"))}

    payload = {
        "schema": "reference-asset-compiler.humanoid-landmarks.v1",
        "skeleton_profile": profile["profile_id"],
        "payload_fbx": str(mesh_path), "payload_fbx_sha256": sha256(mesh_path),
        "manny_reference": str(manny_path), "manny_reference_sha256": sha256(manny_path),
        "coordinate_space": "mesh_world_meters_blender_minus_y_forward",
        "height_m": H, "midline_x": mid_x, "crotch_z": crotch_z,
        "method": ("Spine, neck and head at Manny's height fractions with y from mesh cross-sections; crotch and per-leg centrelines "
                   "from the mesh; arm centrelines from the mesh beyond the torso with the hand as the outer 10.5% of height; "
                   "fingers and metacarpals are Manny's layout rotated onto the measured forearm and scaled to it; twist bones at thirds; "
                   "IK helpers at Manny's parents."),
        "measured_bones": sorted(b for b in bones if any(b.startswith(p) for p in ("thigh_", "calf_", "foot_", "ball_", "lowerarm_", "hand_"))
                                 and "twist" not in b),
        "template_bones": sorted(b for b in bones if any(b.startswith(p) for p in ("thumb", "index", "middle", "ring", "pinky", "ik_", "clavicle", "upperarm_")) or "twist" in b),
        "notes": notes,
        "joints": joints,
        "bones": bones,
        "reviewed_by": None,
        "review_status": "derived_pending_overlay_review",
    }
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Overlay renders.
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
    for m in meshes:
        m.data.materials.clear()
        m.data.materials.append(ghost)

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
    mats = {"l": emissive("L", (1.0, 0.45, 0.05)), "r": emissive("R", (0.1, 0.5, 1.0)), "c": emissive("C", (0.2, 1.0, 0.3))}
    radius = 0.010 * H
    for name, spec in bones.items():
        if name.startswith("ik_"):
            continue
        s = "l" if name.endswith("_l") else "r" if name.endswith("_r") else "c"
        a = Vector(joints[spec["head"]])
        b = Vector(joints[spec["tail"]])
        r = radius * (0.5 if any(name.startswith(d) for d in ("thumb", "index", "middle", "ring", "pinky")) else 1.0)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=a)
        bpy.context.object.data.materials.append(mats[s])
        d = b - a
        if d.length > 1e-6:
            bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.4, depth=d.length, location=(a + b) * 0.5)
            cyl = bpy.context.object
            cyl.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
            cyl.data.materials.append(mats[s])
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.18, 0.18, 0.18, 1.0)
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
    for view, angle in (("front", 0.0), ("three-quarter", 45.0), ("side", 90.0)):
        a = math.radians(angle)
        cam.location = centre + Vector((math.sin(a) * distance, -math.cos(a) * distance, extent * 0.08))
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = out_dir / "overlay-{0}.png".format(view)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views[view] = sha256(path)
    # hand close-up
    hand = Vector(joints["hand_l"])
    cam_data.lens = 135.0
    cam.location = hand + Vector((0.0, -0.45 * H, 0.05 * H))
    cam.rotation_euler = (hand - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = out_dir / "overlay-hand-left.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    views["hand-left"] = sha256(path)
    payload["overlay_sha256"] = views
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("[LANDMARKS] {0} bones={1} height={2:.3f} crotch_z={3:.3f} notes={4}".format(landmarks_path, len(bones), H, crotch_z, notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
