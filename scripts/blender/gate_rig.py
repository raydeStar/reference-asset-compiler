"""Skeleton and skinning gate. Exits 1 on any contract violation.

Validates a skeletal FBX (or .blend) against a declared skeleton profile. There
is no --force flag and there will not be one. The one escape hatch is
`tri_budget_waiver` in the profile, which must name a reason and an approver;
an exceeded budget without a waiver is a hard failure.

Usage:
  blender -b --factory-startup --python scripts/blender/gate_rig.py \
      -- <asset.fbx> <profile.json> <report.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def load_scene(path: Path) -> None:
    if path.suffix.lower() == ".fbx":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        bpy.ops.wm.open_mainfile(filepath=str(path))


def tri_count(mesh) -> int:
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def check_skeleton(armature, profile, failures, warnings, report):
    bones = armature.data.bones
    present = {b.name.lower(): b for b in bones}
    # The FBX round trip can express the root either as a bone or as the
    # armature object itself. Both are legal UE imports; declare which.
    obj_is_root = armature.name.lower() == str(profile.get("root_bone", "")).lower()
    if obj_is_root and profile.get("root_may_be_armature_object"):
        report["root_expressed_as"] = "armature_object"
    elif profile.get("root_bone", "").lower() in present:
        report["root_expressed_as"] = "bone"
    else:
        failures.append(
            "root: profile requires '{0}' as a bone or armature object, found neither "
            "(armature object is '{1}')".format(profile.get("root_bone"), armature.name)
        )
        report["root_expressed_as"] = None

    required = [b for b in profile["required_bones"]]
    missing = [b for b in required if b.lower() not in present]
    # A required root satisfied by the armature object is not missing.
    if report["root_expressed_as"] == "armature_object":
        missing = [b for b in missing if b.lower() != profile["root_bone"].lower()]
    if missing:
        failures.append(
            "bones: {0} required bone(s) absent: {1}".format(len(missing), ", ".join(missing))
        )
    report["required_present"] = len(required) - len(missing)
    report["required_total"] = len(required)
    report["missing_bones"] = missing

    # Names without hierarchy are a coincidence, not a skeleton.
    mismatches = []
    for child, parent in profile.get("expected_parents", {}).items():
        bone = present.get(child.lower())
        if bone is None:
            continue
        actual = bone.parent.name.lower() if bone.parent else None
        if actual != parent.lower():
            mismatches.append(
                {"bone": child, "expected_parent": parent, "actual_parent": actual}
            )
    if mismatches:
        failures.append(
            "hierarchy: {0} bone(s) parented against the profile: {1}".format(
                len(mismatches),
                "; ".join(
                    "{0} expected under {1}, found under {2}".format(
                        m["bone"], m["expected_parent"], m["actual_parent"]
                    )
                    for m in mismatches
                ),
            )
        )
    report["parent_mismatches"] = mismatches

    known = {b.lower() for b in required} | {
        b.lower() for b in profile.get("optional_bones", [])
    }
    unlisted = sorted(b.name for b in bones if b.name.lower() not in known)
    report["unlisted_bones"] = unlisted
    if unlisted and not profile.get("allow_unlisted_bones", False):
        failures.append(
            "bones: {0} bone(s) outside the profile: {1}".format(
                len(unlisted), ", ".join(unlisted)
            )
        )

    expected_count = profile.get("exact_bone_count")
    report["bone_count"] = len(bones)
    if expected_count is not None and len(bones) != expected_count:
        failures.append(
            "bones: profile declares exactly {0} bones, found {1}".format(
                expected_count, len(bones)
            )
        )

    # Non-uniform or non-unit armature scale is how characters arrive in UE
    # a hundred times too large or too small.
    scale = tuple(round(v, 5) for v in armature.scale)
    report["armature_scale"] = list(scale)
    if len(set(scale)) != 1:
        failures.append("scale: armature scale is non-uniform {0}".format(scale))
    elif scale[0] not in (1.0, 0.01):
        warnings.append(
            "scale: armature scale {0} is neither 1.0 nor the 0.01 centimetre "
            "convention; verify Import Uniform Scale in UE5".format(scale[0])
        )


def check_facing(armature, meshes, failures, warnings, report):
    """Mesh and skeleton must face the same way, and that way must be -Y.

    Blender's -Y forward export convention maps to +X in UE5. A mesh that faces
    the other way imports walking backwards; worse, if the mesh disagrees with
    its own skeleton then hand_l drives the visually right hand and knees bend
    the wrong way. Neither is visible in a still render, which is exactly why
    this is a gate and not a review note.
    """
    amw = armature.matrix_world
    bones = armature.data.bones
    facing = {}

    def head_world(name):
        bone = bones.get(name)
        return (amw @ bone.head_local) if bone else None

    def tail_world(name):
        bone = bones.get(name)
        return (amw @ bone.tail_local) if bone else None

    # Skeleton: the toe joint sits ahead of the ankle.
    deltas = []
    for side in ("l", "r"):
        ankle = head_world("foot_" + side)
        toe = head_world("ball_" + side) or tail_world("foot_" + side)
        if ankle and toe:
            deltas.append((toe - ankle).y)
    if deltas:
        mean = sum(deltas) / len(deltas)
        facing["skeleton"] = "-Y" if mean < 0 else "+Y"
        facing["skeleton_toe_delta_y"] = round(mean, 4)
        if mean > 0:
            failures.append(
                "facing: skeleton faces +Y (toe joint is behind the ankle by "
                "{0:.3f}); UE5 expects -Y forward in Blender".format(mean)
            )

    # Left-hand side must sit on +X when facing -Y.
    for pair in (("hand_l", "hand_r"), ("foot_l", "foot_r")):
        left, right = head_world(pair[0]), head_world(pair[1])
        if left and right and abs(left.x - right.x) > 1e-4:
            facing["left_side_axis"] = "+X" if left.x > right.x else "-X"
            if left.x < right.x:
                failures.append(
                    "facing: {0} sits at X={1:.3f} and {2} at X={3:.3f}; the _l "
                    "chain is on the wrong side for a -Y facing character".format(
                        pair[0], left.x, pair[1], right.x
                    )
                )
            break

    # Mesh: eye geometry is the least ambiguous landmark on a character, and
    # unlike a nose it survives hoods, masks and muzzles.
    head_pos = head_world("head")
    eye_y = []
    for obj in meshes:
        mw = obj.matrix_world
        me = obj.data
        for slot_index, mat in enumerate(me.materials):
            if mat is None or "eye" not in mat.name.lower():
                continue
            centres = [
                (mw @ p.center).y
                for p in me.polygons if p.material_index == slot_index
            ]
            if centres:
                eye_y.append(sum(centres) / len(centres))
    if eye_y and head_pos is not None:
        mean_eye = sum(eye_y) / len(eye_y)
        offset = mean_eye - head_pos.y
        facing["mesh"] = "-Y" if offset < 0 else "+Y"
        facing["eye_offset_from_head_bone_y"] = round(offset, 4)
        if offset > 0:
            failures.append(
                "facing: mesh faces +Y -- eye geometry sits {0:.3f} BEHIND the "
                "head bone. The character will import into UE5 facing -X".format(offset)
            )
    elif not eye_y:
        warnings.append(
            "facing: no material with 'eye' in its name, so mesh facing could "
            "not be verified independently of the skeleton"
        )

    if facing.get("mesh") and facing.get("skeleton") and facing["mesh"] != facing["skeleton"]:
        failures.append(
            "facing: mesh faces {0} but skeleton faces {1}. The rig is 180 "
            "degrees out from the geometry: _l bones drive the visually right "
            "side and knees will bend backwards under animation.".format(
                facing["mesh"], facing["skeleton"]
            )
        )
    report["facing"] = facing


def check_mesh(obj, profile, failures, warnings):
    me = obj.data
    entry = {
        "name": obj.name,
        "verts": len(me.vertices),
        "tris": tri_count(me),
        "materials": [m.name if m else None for m in me.materials],
        "uv_layers": [layer.name for layer in me.uv_layers],
        "has_custom_normals": bool(me.has_custom_normals),
    }

    if not me.uv_layers:
        failures.append("{0}: no UV layer".format(obj.name))
    else:
        coords = [tuple(d.uv) for d in me.uv_layers.active.data]
        distinct = len(set(coords))
        oob = sum(
            1 for u, v in coords
            if not (-0.001 <= u <= 1.001 and -0.001 <= v <= 1.001)
        )
        entry["uv_distinct"] = distinct
        entry["uv_out_of_bounds"] = oob
        if distinct < 4:
            failures.append("{0}: degenerate UVs, all loops coincident".format(obj.name))
        if oob:
            failures.append("{0}: {1} UV loops outside 0-1".format(obj.name, oob))

    if tuple(round(v, 4) for v in obj.scale) != (1.0, 1.0, 1.0):
        failures.append("{0}: mesh scale not applied {1}".format(obj.name, tuple(obj.scale)))

    # Skinny triangles are the direct cause of faceted shading and the
    # fingerprint of a Decimate modifier.
    thin = 0
    sampled = me.polygons[:4000]
    for p in sampled:
        vs = [me.vertices[i].co for i in p.vertices]
        if len(vs) < 3:
            continue
        edges = [(vs[i] - vs[(i + 1) % len(vs)]).length for i in range(len(vs))]
        if min(edges) > 1e-9 and max(edges) / min(edges) > 20.0:
            thin += 1
    entry["thin_faces"] = thin
    entry["thin_faces_sampled"] = len(sampled)
    if sampled and thin > len(sampled) * 0.05:
        failures.append(
            "{0}: {1}/{2} high-aspect-ratio faces -- smells like Decimate".format(
                obj.name, thin, len(sampled)
            )
        )

    arm_mods = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object]
    if not arm_mods:
        failures.append("{0}: no armature modifier, mesh is not skinned".format(obj.name))
        return entry

    bone_names = {b.name for b in arm_mods[0].object.data.bones}
    deform_idx = {g.index for g in obj.vertex_groups if g.name in bone_names}
    orphan_groups = sorted(
        g.name for g in obj.vertex_groups if g.name not in bone_names
    )
    max_inf = 0
    unweighted = 0
    for v in me.vertices:
        n = sum(1 for g in v.groups if g.group in deform_idx and g.weight > 1e-5)
        max_inf = max(max_inf, n)
        if n == 0:
            unweighted += 1
    entry["max_influences"] = max_inf
    entry["unweighted_verts"] = unweighted
    entry["orphan_vertex_groups"] = orphan_groups

    cap = profile.get("max_influences", 4)
    if max_inf > cap:
        failures.append(
            "{0}: {1} influences exceeds profile cap of {2}; UE5 will renormalise "
            "and silently change your weights".format(obj.name, max_inf, cap)
        )
    if unweighted:
        failures.append(
            "{0}: {1} vertices carry no bone weight and will collapse to the "
            "origin under animation".format(obj.name, unweighted)
        )
    if orphan_groups:
        warnings.append(
            "{0}: {1} vertex group(s) match no bone: {2}".format(
                obj.name, len(orphan_groups), ", ".join(orphan_groups[:10])
            )
        )
    return entry


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, profile_path, report_path = (Path(a) for a in argv[:3])
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))

    load_scene(asset_path)
    failures: list[str] = []
    warnings: list[str] = []
    report = {
        "asset": str(asset_path),
        "profile": profile["profile_id"],
        "blender_version": bpy.app.version_string,
    }

    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    if len(armatures) != 1:
        failures.append(
            "scene: expected exactly 1 armature, found {0}".format(len(armatures))
        )
    if not meshes:
        failures.append("scene: no mesh objects")

    if armatures:
        check_skeleton(armatures[0], profile, failures, warnings, report)
        if meshes:
            check_facing(armatures[0], meshes, failures, warnings, report)

    report["meshes"] = [check_mesh(o, profile, failures, warnings) for o in meshes]
    total_tris = sum(m["tris"] for m in report["meshes"])
    report["total_tris"] = total_tris

    budget = profile.get("tri_budget")
    waiver = profile.get("tri_budget_waiver")
    if budget is not None and total_tris > budget:
        if waiver and waiver.get("reason") and waiver.get("approved_by"):
            warnings.append(
                "budget: {0} tris exceeds {1} -- WAIVED by {2}: {3}".format(
                    total_tris, budget, waiver["approved_by"], waiver["reason"]
                )
            )
            report["budget_waived"] = True
        else:
            failures.append(
                "budget: {0} tris exceeds profile budget {1} and no "
                "tri_budget_waiver is recorded".format(total_tris, budget)
            )
            report["budget_waived"] = False

    report["failures"] = failures
    report["warnings"] = warnings
    report["ok"] = not failures
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    label = asset_path.name
    for w in warnings:
        print("[GATE RIG] WARN  {0}: {1}".format(label, w))
    if failures:
        print("[GATE RIG] FAILED {0} against profile '{1}':".format(label, profile["profile_id"]))
        for f in failures:
            print("  - {0}".format(f))
        return 1
    print(
        "[GATE RIG] Passed {0} against '{1}'. {2} bones, {3} tris, "
        "max {4} influences, 0 unweighted.".format(
            label,
            profile["profile_id"],
            report.get("bone_count", 0),
            total_tris,
            max((m.get("max_influences", 0) for m in report["meshes"]), default=0),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
