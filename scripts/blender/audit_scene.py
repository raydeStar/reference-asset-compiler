"""Headless scene audit. Read-only: opens a .blend, writes JSON, never saves.

Usage:
  blender -b --factory-startup --python scripts/blender/audit_scene.py -- <in.blend> <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

# UE5 Manny required bone contract. Fingers are checked separately because their
# absence is a downgrade, not a disqualification.
UE5_CORE = [
    "root", "pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05",
    "neck_01", "head",
    "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
    "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
    "thigh_l", "calf_l", "foot_l", "ball_l",
    "thigh_r", "calf_r", "foot_r", "ball_r",
]
UE5_FINGERS = [
    "{d}_{i:02d}_{s}".format(d=d, i=i, s=s)
    for s in ("l", "r")
    for d in ("thumb", "index", "middle", "ring", "pinky")
    for i in (1, 2, 3)
]

# Names alone are not the contract. A bone called "upperarm_l" parented to the
# pelvis is not a UE5 skeleton, it is a coincidence.
EXPECTED_PARENT = {
    "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01",
    "spine_03": "spine_02", "neck_01": "spine_05", "head": "neck_01",
    "clavicle_l": "spine_05", "upperarm_l": "clavicle_l",
    "lowerarm_l": "upperarm_l", "hand_l": "lowerarm_l",
    "clavicle_r": "spine_05", "upperarm_r": "clavicle_r",
    "lowerarm_r": "upperarm_r", "hand_r": "lowerarm_r",
    "thigh_l": "pelvis", "calf_l": "thigh_l", "foot_l": "calf_l",
    "ball_l": "foot_l", "thigh_r": "pelvis", "calf_r": "thigh_r",
    "foot_r": "calf_r", "ball_r": "foot_r",
}


def tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def audit_mesh(obj):
    me = obj.data
    report = {
        "name": obj.name,
        "verts": len(me.vertices),
        "tris": tri_count(me),
        "polys": len(me.polygons),
        "ngons": sum(1 for p in me.polygons if len(p.vertices) > 4),
        "quads": sum(1 for p in me.polygons if len(p.vertices) == 4),
        "has_custom_normals": bool(me.has_custom_normals),
        "scale": [round(v, 5) for v in obj.scale],
        "rotation_euler": [round(v, 5) for v in obj.rotation_euler],
        "uv_layers": [layer.name for layer in me.uv_layers],
        "materials": [m.name if m else None for m in me.materials],
        "modifiers": [[m.name, m.type] for m in obj.modifiers],
        "shape_keys": [k.name for k in me.shape_keys.key_blocks] if me.shape_keys else [],
        "vertex_groups": len(obj.vertex_groups),
        "parent": obj.parent.name if obj.parent else None,
    }

    # Skin influence census. UE5 caps at 12 but the practical target is 4 or 8;
    # beyond that the importer silently renormalises and weights change.
    arm_mods = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object]
    if arm_mods:
        bone_names = {b.name for b in arm_mods[0].object.data.bones}
        deform_idx = {g.index for g in obj.vertex_groups if g.name in bone_names}
        max_inf = 0
        unweighted = 0
        histogram = {}
        for v in me.vertices:
            n = sum(1 for g in v.groups if g.group in deform_idx and g.weight > 1e-5)
            max_inf = max(max_inf, n)
            if n == 0:
                unweighted += 1
            histogram[n] = histogram.get(n, 0) + 1
        report["skin"] = {
            "armature": arm_mods[0].object.name,
            "max_influences": max_inf,
            "unweighted_verts": unweighted,
            "influence_histogram": {str(k): v for k, v in sorted(histogram.items())},
            "groups_not_matching_bones": sorted(
                g.name for g in obj.vertex_groups if g.name not in bone_names
            )[:20],
        }

    if me.uv_layers:
        coords = [tuple(d.uv) for d in me.uv_layers.active.data]
        report["uv"] = {
            "loops": len(coords),
            "distinct": len(set(coords)),
            "out_of_bounds": sum(
                1 for u, v in coords
                if not (-0.001 <= u <= 1.001 and -0.001 <= v <= 1.001)
            ),
        }

    # High-aspect-ratio census. Skinny triangles are the faceting culprit.
    thin = 0
    sampled = me.polygons[:4000]
    for p in sampled:
        vs = [me.vertices[i].co for i in p.vertices]
        if len(vs) < 3:
            continue
        edges = [(vs[i] - vs[(i + 1) % len(vs)]).length for i in range(len(vs))]
        if min(edges) > 1e-9 and max(edges) / min(edges) > 20.0:
            thin += 1
    report["thin_faces"] = {"sampled": len(sampled), "count": thin}
    return report


def audit_armature(obj):
    bones = obj.data.bones
    names = [b.name for b in bones]
    lower = {n.lower() for n in names}
    by_lower = {b.name.lower(): b for b in bones}

    present_core = [b for b in UE5_CORE if b in lower]
    present_fingers = [b for b in UE5_FINGERS if b in lower]

    parent_mismatch = []
    for child, parent in EXPECTED_PARENT.items():
        bone = by_lower.get(child)
        if bone is None:
            continue
        actual = bone.parent.name.lower() if bone.parent else None
        if actual != parent:
            parent_mismatch.append(
                {"bone": child, "expected_parent": parent, "actual_parent": actual}
            )

    known = {x for x in UE5_CORE} | {x for x in UE5_FINGERS}
    return {
        "name": obj.name,
        "bone_count": len(bones),
        "scale": [round(v, 5) for v in obj.scale],
        "ue5_core_coverage": "{0}/{1}".format(len(present_core), len(UE5_CORE)),
        "ue5_core_missing": [b for b in UE5_CORE if b not in lower],
        "ue5_fingers_present_count": len(present_fingers),
        "ue5_fingers_missing_count": len(UE5_FINGERS) - len(present_fingers),
        "parent_mismatches": parent_mismatch,
        "non_ue5_bones": sorted(n for n in names if n.lower() not in known),
        "all_bones": sorted(names),
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    blend_path, out_path = Path(argv[0]), Path(argv[1])

    # Auditing the shipped FBX is the only way to know what UE5 actually sees.
    # The .blend may hold a control rig that never reaches the exported file.
    if blend_path.suffix.lower() == ".fbx":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(blend_path))
    else:
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    mesh_reports = [audit_mesh(o) for o in meshes]

    payload = {
        "blend": str(blend_path),
        "blender_version": bpy.app.version_string,
        "unit_scale": bpy.context.scene.unit_settings.scale_length,
        "unit_system": bpy.context.scene.unit_settings.system,
        "object_counts": {
            "mesh": len(meshes),
            "armature": len(armatures),
            "other": len(bpy.data.objects) - len(meshes) - len(armatures),
        },
        "totals": {
            "verts": sum(m["verts"] for m in mesh_reports),
            "tris": sum(m["tris"] for m in mesh_reports),
            "materials": len(bpy.data.materials),
            "images": len([i for i in bpy.data.images if i.name != "Render Result"]),
        },
        "images": [
            {
                "name": i.name,
                "size": list(i.size),
                "colorspace": i.colorspace_settings.name,
                "filepath": i.filepath,
                "packed": bool(i.packed_file),
            }
            for i in bpy.data.images if i.name != "Render Result"
        ],
        "armatures": [audit_armature(o) for o in armatures],
        "meshes": mesh_reports,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("RAC_AUDIT_OK {0}".format(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
