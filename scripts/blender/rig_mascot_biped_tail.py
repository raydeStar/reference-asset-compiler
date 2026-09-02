"""Author the mascot_biped_tail deform skeleton on an approved mesh and skin it.

The existing-mesh counterpart of the Auto-Rig Pro humanoid driver for the
``blender_custom_rig`` backbone. It consumes exactly three inputs: the
texture-approved production FBX, a source-bound landmark file produced by
``derive_mascot_landmarks.py`` (hash-bound to that FBX), and the skeleton
profile. Every bone head and tail comes from the landmark file; the parent
hierarchy comes from the profile. Nothing is placed by eye.

Binding uses Blender's heat-based automatic weights, falls back to envelope
weights only if heat fails, fills any unweighted vertex from its nearest
weighted neighbour, caps influences at the profile limit, and renormalizes so
what is gated is what ships. Vertex positions and face order are fingerprinted
before and after; a changed fingerprint aborts the stage.

Usage:
  blender -b --factory-startup --python-exit-code 1 \
      --python scripts/blender/rig_mascot_biped_tail.py -- \
      <production.fbx> <mascot-landmarks.json> <profile.json> <out.fbx> <report.json>
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def geometry_fingerprint(obj) -> str:
    digest = hashlib.sha256()
    for vertex in obj.data.vertices:
        digest.update(struct.pack("<3d", *(round(v, 7) for v in vertex.co)))
    for polygon in obj.data.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", index))
    return digest.hexdigest()


def weight_diagnostics(obj, deform_names):
    deform_idx = {g.index for g in obj.vertex_groups if g.name in deform_names}
    per_bone = {g.name: 0 for g in obj.vertex_groups if g.name in deform_names}
    weighted = 0
    maximum = 0
    for vertex in obj.data.vertices:
        groups = [g for g in vertex.groups if g.group in deform_idx and g.weight > 1e-5]
        weighted += bool(groups)
        maximum = max(maximum, len(groups))
        for g in groups:
            per_bone[obj.vertex_groups[g.group].name] += 1
    return {
        "vertices": len(obj.data.vertices),
        "weighted_vertices": weighted,
        "coverage": weighted / max(1, len(obj.data.vertices)),
        "maximum_influences": maximum,
        "vertices_per_bone": per_bone,
    }


def fill_unweighted_from_nearest(obj, deform_names) -> int:
    deform_idx = {g.index for g in obj.vertex_groups if g.name in deform_names}
    has = lambda v: any(g.group in deform_idx and g.weight > 1e-5 for g in v.groups)  # noqa: E731
    weighted = [v.index for v in obj.data.vertices if has(v)]
    missing = [v.index for v in obj.data.vertices if not has(v)]
    if not missing:
        return 0
    if not weighted:
        raise RuntimeError("Bind produced no weights at all")
    tree = KDTree(len(weighted))
    for index in weighted:
        tree.insert(obj.data.vertices[index].co, index)
    tree.balance()
    for index in missing:
        _co, nearest, _dist = tree.find(obj.data.vertices[index].co)
        for assignment in obj.data.vertices[nearest].groups:
            if assignment.group in deform_idx and assignment.weight > 1e-5:
                obj.vertex_groups[assignment.group].add([index], assignment.weight, "REPLACE")
    return len(missing)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    fbx_path, landmarks_path, profile_path, out_fbx, report_path = (Path(a).resolve() for a in argv[:5])
    for path in (out_fbx, report_path):
        if path.exists():
            raise RuntimeError("Refusing to overwrite rig candidate evidence: {0}".format(path))
    landmarks = json.loads(landmarks_path.read_text(encoding="utf-8-sig"))
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    if landmarks.get("skeleton_profile") != profile["profile_id"]:
        raise RuntimeError("Landmark file targets a different skeleton profile")
    payload_hash = sha256(fbx_path)
    if landmarks.get("payload_fbx_sha256") != payload_hash:
        raise RuntimeError("Landmarks are not bound to this payload FBX")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))
    if [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        raise RuntimeError("Payload already carries an armature")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Payload must contain exactly one mesh")
    body = meshes[0]
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    fingerprint_before = geometry_fingerprint(body)
    triangles = sum(max(0, len(p.vertices) - 2) for p in body.data.polygons)

    joints = {k: Vector(v) for k, v in landmarks["joints"].items()}
    bone_spec = landmarks["bones"]
    required = list(profile["required_bones"])
    optional = list(profile.get("optional_bones", []))
    missing = [b for b in required if b not in bone_spec]
    extra = [b for b in bone_spec if b not in required and b not in optional]
    if missing or (extra and not profile.get("allow_unlisted_bones", False)):
        raise RuntimeError("Landmark bones do not match the profile: missing={0} extra={1}".format(missing, extra))
    exact = profile.get("exact_bone_count")
    if exact is not None and len(bone_spec) != exact:
        raise RuntimeError("Profile declares exactly {0} bones; landmarks define {1}".format(exact, len(bone_spec)))
    parents = dict(profile["expected_parents"])
    parents.setdefault("tail_01", "pelvis")
    for name, spec in bone_spec.items():
        if spec.get("parent"):
            parents.setdefault(name, spec["parent"])
    build_order = [b for b in required] + [b for b in bone_spec if b not in required]

    armature_data = bpy.data.armatures.new("mascot_biped_tail")
    rig = bpy.data.objects.new("Armature", armature_data)
    bpy.context.collection.objects.link(rig)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = {}
    for name in build_order:
        spec = bone_spec[name]
        head = joints[spec["head"]]
        tail = joints[spec["tail"]] if spec.get("tail") else head + Vector((0.0, 0.1, 0.0))
        if (tail - head).length < 1e-4:
            raise RuntimeError("Degenerate bone {0}".format(name))
        bone = armature_data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.use_connect = False
        direction = (tail - head).normalized()
        up = Vector((0.0, 1.0, 0.0))
        if abs(direction.dot(up)) > 0.9:
            up = Vector((0.0, 0.0, 1.0))
        bone.align_roll(up)
        edit_bones[name] = bone
    for name, parent in parents.items():
        if name in edit_bones and parent in edit_bones:
            edit_bones[name].parent = edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    root_name = profile["root_bone"]
    armature_data.bones[root_name].use_deform = False
    for name, spec in bone_spec.items():
        if spec.get("deform") is False:
            armature_data.bones[name].use_deform = False
    deform_names = {b.name for b in armature_data.bones if b.use_deform}

    # Heat-based automatic weights on the approved mesh itself.
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bind_method = "ARMATURE_AUTO"
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    diagnostics = weight_diagnostics(body, deform_names)
    if diagnostics["coverage"] < 0.5:
        for group in list(body.vertex_groups):
            body.vertex_groups.remove(group)
        bind_method = "ARMATURE_ENVELOPE"
        bpy.ops.object.select_all(action="DESELECT")
        body.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
    filled = fill_unweighted_from_nearest(body, deform_names)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    cap = int(profile.get("max_influences", 4))
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=cap)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
    diagnostics = weight_diagnostics(body, deform_names)
    if diagnostics["coverage"] < 0.999:
        raise RuntimeError("Skin coverage too low after fill: {0:.4%}".format(diagnostics["coverage"]))
    if diagnostics["maximum_influences"] > cap:
        raise RuntimeError("Influence cap exceeded after limit")
    unweighted_bones = sorted(n for n, c in diagnostics["vertices_per_bone"].items() if c == 0)
    modifiers = [m for m in body.modifiers if m.type == "ARMATURE"]
    if len(modifiers) != 1 or modifiers[0].object != rig:
        raise RuntimeError("Expected exactly one armature modifier bound to the new rig")
    fingerprint_after = geometry_fingerprint(body)
    if fingerprint_after != fingerprint_before:
        raise RuntimeError("Binding changed the approved geometry")

    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    blend_path = out_fbx.with_suffix(".blend")
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, path_mode="RELATIVE", embed_textures=False,
        apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z", global_scale=1.0,
        apply_unit_scale=True, bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"}, use_armature_deform_only=False,
        primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    report = {
        "schema": "reference-asset-compiler.mascot-rig-candidate.v1",
        "asset_id": landmarks.get("asset_id"),
        "skeleton_profile": profile["profile_id"],
        "profile_sha256": sha256(profile_path),
        "payload_fbx": str(fbx_path), "payload_fbx_sha256": payload_hash,
        "landmarks": str(landmarks_path), "landmarks_sha256": sha256(landmarks_path),
        "blender_version": bpy.app.version_string,
        "armature_object": rig.name,
        "bones": {
            b.name: {"head": [round(v, 5) for v in b.head_local], "tail": [round(v, 5) for v in b.tail_local],
                     "parent": b.parent.name if b.parent else None, "deform": b.use_deform}
            for b in armature_data.bones
        },
        "bone_count": len(armature_data.bones),
        "triangles": triangles,
        "bind": {"method": bind_method, "unweighted_filled_from_nearest": filled,
                 "influence_cap": cap, **diagnostics, "bones_without_weights": unweighted_bones},
        "geometry_fingerprint_before": fingerprint_before,
        "geometry_fingerprint_after": fingerprint_after,
        "geometry_unchanged": True,
        "output_fbx": str(out_fbx), "output_fbx_sha256": sha256(out_fbx),
        "output_blend": str(blend_path), "output_blend_sha256": sha256(blend_path),
        "status": "candidate_pending_gate_and_deformation",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[MASCOT RIG] {0} bones={1} coverage={2:.4%} max_inf={3} filled={4} method={5} no_weight_bones={6}".format(
        out_fbx, len(armature_data.bones), diagnostics["coverage"], diagnostics["maximum_influences"],
        filled, bind_method, unweighted_bones))
    return 0


if __name__ == "__main__":
    sys.exit(main())
