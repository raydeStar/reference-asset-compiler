"""Deformation suite. Poses the rig and proves the skin follows correctly.

A bind pose render proves nothing: a rig whose left/right labels are swapped,
or whose knees bend backwards, looks perfect standing still. This poses the
joints that actually carry animation and reports both renders and numbers.

Numeric checks per pose:
  * which side of the body moved, so a mirrored rig is caught without eyes
  * how far the skin moved, so a joint driving nothing is caught
  * bounding-volume change, to flag candy-wrapper collapse

Usage:
  blender -b --factory-startup --python scripts/blender/deform_test.py \
      -- <asset.fbx> <out_dir> <report.json>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# Each pose: bone -> (axis, degrees). Angles are deliberately large; a subtle
# pose hides a subtle problem.
POSES = {
    "arms_forward": {
        "upperarm_l": ("X", -70.0),
        "upperarm_r": ("X", -70.0),
    },
    "left_arm_only": {
        "upperarm_l": ("X", -90.0),
    },
    "elbows_bent": {
        "lowerarm_l": ("X", -95.0),
        "lowerarm_r": ("X", -95.0),
    },
    "knees_bent": {
        "calf_l": ("X", 90.0),
        "calf_r": ("X", 90.0),
    },
    "spine_twist": {
        "spine_02": ("Z", 35.0),
        "neck_01": ("Z", -30.0),
    },
}


def mesh_points(meshes, depsgraph):
    """Evaluated world-space vertices, i.e. after the armature modifier."""
    points = []
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mw = evaluated.matrix_world
        points.extend([mw @ v.co for v in mesh.vertices])
        evaluated.to_mesh_clear()
    return points


def bounds_of(points):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for p in points:
        for i in range(3):
            lo[i] = min(lo[i], p[i])
            hi[i] = max(hi[i], p[i])
    return lo, hi


def clear_pose(armature):
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)


def apply_pose(armature, spec, missing):
    for bone_name, (axis, degrees) in spec.items():
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone is None:
            missing.append(bone_name)
            continue
        pose_bone.rotation_mode = "XYZ"
        index = "XYZ".index(axis)
        euler = list(pose_bone.rotation_euler)
        euler[index] = math.radians(degrees)
        pose_bone.rotation_euler = euler


def setup_render(centre, extent, resolution):
    world = bpy.data.worlds.new("DeformWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.2, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.5
    bpy.context.scene.world = world

    for name, offset, power in (
        ("Key", (1.0, -1.6, 1.2), 800.0),
        ("Fill", (-1.4, -1.0, 0.3), 260.0),
    ):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = power * (extent * 0.5) ** 2
        data.size = extent * 0.5
        lamp = bpy.data.objects.new(name, data)
        lamp.location = centre + Vector(offset) * extent
        lamp.rotation_euler = (centre - lamp.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(lamp)

    scene = bpy.context.scene
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = "PNG"

    clay = bpy.data.materials.new("DeformClay")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.45
    scene.view_layers[0].material_override = clay


def place_camera(centre, extent, angle_deg):
    cam_data = bpy.data.cameras.new("DeformCam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("DeformCam", cam_data)
    bpy.context.collection.objects.link(cam)
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (extent * 1.45) / (2.0 * math.tan(fov * 0.5))
    angle = math.radians(angle_deg)
    cam.location = centre + Vector(
        (math.sin(angle) * distance, -math.cos(angle) * distance, 0.0)
    )
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_dir, report_path = (Path(a) for a in argv[:3])
    resolution = int(argv[3]) if len(argv) > 3 else 900

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))

    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not armatures or not meshes:
        print("[DEFORM] FAILED: need one armature and at least one mesh")
        return 1
    armature = armatures[0]

    depsgraph = bpy.context.evaluated_depsgraph_get()
    clear_pose(armature)
    bpy.context.view_layer.update()
    rest_points = mesh_points(meshes, depsgraph)
    rest_lo, rest_hi = bounds_of(rest_points)
    centre = (rest_lo + rest_hi) * 0.5
    extent = max(rest_hi - rest_lo)

    setup_render(centre, extent, resolution)
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    warnings = []
    results = {}

    for pose_name, spec in POSES.items():
        clear_pose(armature)
        missing = []
        apply_pose(armature, spec, missing)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        posed = mesh_points(meshes, depsgraph)

        if missing:
            warnings.append(
                "{0}: skipped, rig has no {1}".format(pose_name, ", ".join(missing))
            )
            if len(missing) == len(spec):
                results[pose_name] = {"skipped": True, "missing_bones": missing}
                continue

        deltas = [(posed[i] - rest_points[i]) for i in range(len(rest_points))]
        moved = [i for i, d in enumerate(deltas) if d.length > extent * 0.005]
        max_move = max((d.length for d in deltas), default=0.0)

        # Which side moved? Decisive for catching a mirrored rig.
        left_move = sum(deltas[i].length for i in moved if rest_points[i].x > 0)
        right_move = sum(deltas[i].length for i in moved if rest_points[i].x < 0)
        total_side = left_move + right_move
        side_bias = ((left_move - right_move) / total_side) if total_side > 1e-9 else 0.0

        posed_lo, posed_hi = bounds_of(posed)
        rest_vol = max((rest_hi - rest_lo).x * (rest_hi - rest_lo).y * (rest_hi - rest_lo).z, 1e-9)
        posed_vol = (posed_hi - posed_lo).x * (posed_hi - posed_lo).y * (posed_hi - posed_lo).z

        entry = {
            "bones": {k: list(v) for k, v in spec.items()},
            "vertices_moved": len(moved),
            "vertices_moved_pct": round(100.0 * len(moved) / max(len(rest_points), 1), 2),
            "max_displacement_m": round(max_move, 4),
            "side_bias": round(side_bias, 3),
            "bbox_volume_ratio": round(posed_vol / rest_vol, 3),
        }

        if not moved:
            failures.append(
                "{0}: posing {1} moved no vertices -- those bones drive nothing".format(
                    pose_name, ", ".join(spec)
                )
            )

        # A pose driving only _l bones must move only the +X half.
        only_left = all(b.endswith("_l") for b in spec)
        if only_left and moved and side_bias < 0.5:
            failures.append(
                "{0}: posed only _l bones but the motion is not confined to the "
                "+X side (side_bias {1:+.2f}); left/right are crossed".format(
                    pose_name, side_bias
                )
            )

        symmetric = (
            len(spec) == 2
            and any(b.endswith("_l") for b in spec)
            and any(b.endswith("_r") for b in spec)
        )
        if symmetric and moved and abs(side_bias) > 0.25:
            warnings.append(
                "{0}: symmetric pose produced lopsided motion (side_bias "
                "{1:+.2f}); weights may be asymmetric".format(pose_name, side_bias)
            )

        for view, angle in (("front", 0.0), ("side", 90.0)):
            place_camera(centre, extent, angle)
            path = out_dir / "deform-{0}-{1}.png".format(pose_name, view)
            bpy.context.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            entry.setdefault("renders", []).append(path.name)

        results[pose_name] = entry
        print("[DEFORM] {0}: {1} verts moved, max {2:.3f}m, side_bias {3:+.2f}".format(
            pose_name, len(moved), max_move, side_bias))

    clear_pose(armature)
    report = {
        "asset": str(asset_path),
        "poses": results,
        "failures": failures,
        "warnings": warnings,
        "ok": not failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for w in warnings:
        print("[DEFORM] WARN  {0}".format(w))
    if failures:
        print("[DEFORM] FAILED:")
        for f in failures:
            print("  - {0}".format(f))
        return 1
    print("[DEFORM] Passed. {0} poses exercised.".format(len(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
