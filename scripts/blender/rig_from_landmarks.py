"""Author a profile-conformant deform skeleton from a landmark file and skin it.

Generic successor of rig_mascot_biped_tail.py: works for any skeleton profile
(mascot_biped_tail, ue5_manny) given a landmark file whose bones name their
head/tail joints, parent and deform flag.

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
    root_name = profile["root_bone"]
    allowed = set(required) | set(optional) | {root_name}
    missing = [b for b in required if b not in bone_spec]
    extra = [b for b in bone_spec if b not in allowed]
    if missing or (extra and not profile.get("allow_unlisted_bones", False)):
        raise RuntimeError("Landmark bones do not match the profile: missing={0} extra={1}".format(missing, extra))
    exact = profile.get("exact_bone_count")
    if exact is not None and len(bone_spec) != exact:
        raise RuntimeError("Profile declares exactly {0} bones; landmarks define {1}".format(exact, len(bone_spec)))
    # Parent precedence: the landmark file, then the profile, then root.
    parents = {}
    for name, spec in bone_spec.items():
        if spec.get("parent"):
            parents[name] = spec["parent"]
    for name, parent in profile.get("expected_parents", {}).items():
        parents.setdefault(name, parent)
    parents.setdefault("tail_01", "pelvis")
    for name in bone_spec:
        if name != root_name and name not in parents:
            parents[name] = root_name
    # Parents before children, whatever order the file lists them in.
    build_order = []
    def visit(name):
        if name in build_order or name not in bone_spec:
            return
        parent = parents.get(name)
        if parent and parent != name:
            visit(parent)
        build_order.append(name)
    for name in bone_spec:
        visit(name)

    # Profiles like ue5_manny express the root as the armature object (UE turns
    # that node into the root bone); mascot_biped_tail requires a real bone.
    root_as_object = bool(profile.get("root_may_be_armature_object")) and root_name not in required
    if root_as_object:
        bone_spec = {k: v for k, v in bone_spec.items() if k != root_name}
        parents = {k: (None if v == root_name else v) for k, v in parents.items() if k != root_name}
        build_order = [b for b in build_order if b != root_name]
    armature_data = bpy.data.armatures.new(profile["profile_id"])
    rig = bpy.data.objects.new(root_name if root_as_object else "Armature", armature_data)
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
    if root_name in armature_data.bones:
        armature_data.bones[root_name].use_deform = False
    for name, spec in bone_spec.items():
        if spec.get("deform") is False:
            armature_data.bones[name].use_deform = False
    deform_names = {b.name for b in armature_data.bones if b.use_deform}

    # Heat-based automatic weights. Heat fails on meshes with split vertices or
    # layered shells, so try the approved mesh first, then a welded proxy whose
    # weights are transferred back, and only then envelope weights.
    def try_auto(target):
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        return weight_diagnostics(target, deform_names)["coverage"]

    def clear_groups(target):
        for group in list(target.vertex_groups):
            target.vertex_groups.remove(group)
        for modifier in [m for m in target.modifiers if m.type == "ARMATURE"]:
            target.modifiers.remove(modifier)

    bind_method = "ARMATURE_AUTO"
    coverage = try_auto(body)
    if coverage < 0.5:
        clear_groups(body)
        proxy = body.copy()
        proxy.data = body.data.copy()
        proxy.name = "TMP_RAC_SkinProxy"
        bpy.context.collection.objects.link(proxy)
        proxy.data.materials.clear()
        bpy.ops.object.select_all(action="DESELECT")
        proxy.select_set(True)
        bpy.context.view_layer.objects.active = proxy
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=1.0e-4)
        bpy.ops.object.mode_set(mode="OBJECT")
        proxy_coverage = try_auto(proxy)
        if proxy_coverage >= 0.5:
            bind_method = "ARMATURE_AUTO_on_welded_proxy"
            fill_unweighted_from_nearest(proxy, deform_names)
            for group in proxy.vertex_groups:
                if body.vertex_groups.get(group.name) is None:
                    body.vertex_groups.new(name=group.name)
            bpy.ops.object.select_all(action="DESELECT")
            body.select_set(True)
            bpy.context.view_layer.objects.active = body
            transfer = body.modifiers.new(name="TransferWeights", type="DATA_TRANSFER")
            transfer.use_vert_data = True
            transfer.data_types_verts = {"VGROUP_WEIGHTS"}
            transfer.vert_mapping = "POLYINTERP_NEAREST"
            transfer.layers_vgroup_select_src = "ALL"
            transfer.layers_vgroup_select_dst = "NAME"
            transfer.mix_mode = "REPLACE"
            transfer.mix_factor = 1.0
            transfer.object = proxy
            bpy.ops.object.modifier_apply(modifier=transfer.name)
            armature_mod = body.modifiers.new(name="Armature", type="ARMATURE")
            armature_mod.object = rig
            body.parent = rig
        else:
            bind_method = "ARMATURE_ENVELOPE"
            bpy.ops.object.select_all(action="DESELECT")
            body.select_set(True)
            rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
        bpy.data.objects.remove(proxy, do_unlink=True)
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
        "schema": "reference-asset-compiler.landmark-rig-candidate.v1",
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
    print("[LANDMARK RIG] {0} bones={1} coverage={2:.4%} max_inf={3} filled={4} method={5} no_weight_bones={6}".format(
        out_fbx, len(armature_data.bones), diagnostics["coverage"], diagnostics["maximum_influences"],
        filled, bind_method, unweighted_bones))
    return 0


if __name__ == "__main__":
    sys.exit(main())
