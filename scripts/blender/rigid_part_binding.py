"""Explicit source-bound, single-bone binding for already separated rigid parts."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import bpy


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def part_fingerprint(obj):
    """Skin weights may change; the approved shell and its UVs may not."""
    digest = hashlib.sha256()
    for vertex in obj.data.vertices:
        digest.update(struct.pack("<3f", *vertex.co))
    for poly in obj.data.polygons:
        digest.update(struct.pack("<II", len(poly.vertices), poly.material_index))
        for index in poly.vertices:
            digest.update(struct.pack("<I", index))
    for layer in obj.data.uv_layers:
        digest.update(layer.name.encode())
        for loop in layer.data:
            digest.update(struct.pack("<2f", *loop.uv))
    digest.update(json.dumps([slot.material.name if slot.material else None
                              for slot in obj.material_slots]).encode())
    return digest.hexdigest()


def bind_rigid_parts(meshes, landmarks, profile, build_skeleton,
                     input_path, landmarks_path, profile_path, out_fbx, report_path):
    contract = profile["rigid_part_binding"]
    payload_hash = file_hash(input_path)
    if contract.get("payload_sha256") != payload_hash:
        raise RuntimeError("Rigid-part declaration is not bound to this payload")
    mapping = contract.get("parts", {})
    names = {obj.name for obj in meshes}
    if not mapping or set(mapping) != names:
        raise RuntimeError(f"Rigid-part declaration must name every mesh exactly: meshes={sorted(names)} mapping={sorted(mapping)}")
    for obj in meshes:
        if len(obj.vertex_groups) or any(mod.type == "ARMATURE" for mod in obj.modifiers):
            raise RuntimeError(f"Rigid input already has skin data: {obj.name}")
    before = {obj.name: part_fingerprint(obj) for obj in meshes}
    world = {obj.name: obj.matrix_world.copy() for obj in meshes}
    rig, deform_names = build_skeleton(landmarks, profile)
    invalid = {name: bone for name, bone in mapping.items() if bone not in deform_names}
    if invalid:
        raise RuntimeError(f"Rigid owners must be existing deform bones: {invalid}")
    for bone in rig.data.bones:
        # FBX does not round-trip Blender's use_deform flag; keep a portable receipt too.
        bone["rac_deform"] = bool(bone.use_deform)
    rows = []
    for obj in meshes:
        group = obj.vertex_groups.new(name=mapping[obj.name])
        group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        obj.parent = rig
        obj.matrix_world = world[obj.name]
        modifier = obj.modifiers.new(name="RAC_RigidPart", type="ARMATURE")
        modifier.object = rig
        modifier.use_vertex_groups = True
        modifier.use_bone_envelopes = False
        bpy.context.view_layer.update()
        transform_error = max(abs(obj.matrix_world[r][c] - world[obj.name][r][c])
                              for r in range(4) for c in range(4))
        if part_fingerprint(obj) != before[obj.name] or transform_error > 1e-7:
            raise RuntimeError(f"Binding changed approved part {obj.name}")
        if not all(len(v.groups) == 1 and abs(v.groups[0].weight - 1.0) < 1e-7
                   for v in obj.data.vertices):
            raise RuntimeError(f"Rigid weights are not one-hot: {obj.name}")
        rows.append({"name": obj.name, "bone": mapping[obj.name], "vertices": len(obj.data.vertices),
                     "triangles": sum(len(p.vertices) - 2 for p in obj.data.polygons),
                     "fingerprint_before": before[obj.name], "fingerprint_after": part_fingerprint(obj),
                     "world_transform_max_error": transform_error, "maximum_influences": 1})
    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    blend_path = out_fbx.with_suffix(".blend")
    if blend_path.exists():
        raise RuntimeError(f"Refusing to overwrite {blend_path}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, path_mode="RELATIVE", embed_textures=False,
        apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z", global_scale=1.0,
        apply_unit_scale=True, bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"}, use_armature_deform_only=False,
        primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
        use_custom_props=True,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    vertices = sum(row["vertices"] for row in rows)
    report = {
        "schema": "reference-asset-compiler.landmark-rig-candidate.v1",
        "asset_id": landmarks.get("asset_id"), "skeleton_profile": profile["profile_id"],
        "profile_sha256": file_hash(profile_path), "payload_fbx": str(input_path),
        "payload_fbx_sha256": payload_hash, "landmarks": str(landmarks_path),
        "landmarks_sha256": file_hash(landmarks_path), "blender_version": bpy.app.version_string,
        "armature_object": rig.name, "bone_count": len(rig.data.bones),
        "bones": {b.name: {"head": list(b.head_local), "tail": list(b.tail_local),
                            "parent": b.parent.name if b.parent else None, "deform": b.use_deform}
                  for b in rig.data.bones},
        "triangles": sum(row["triangles"] for row in rows), "parts": rows,
        "bind": {"method": "EXPLICIT_RIGID_PARTS", "vertices": vertices,
                 "weighted_vertices": vertices, "coverage": 1.0, "maximum_influences": 1,
                 "influence_cap": profile.get("max_influences", 4), "unweighted_filled_from_nearest": 0,
                 "bones_without_weights": sorted(deform_names - set(mapping.values()))},
        "geometry_unchanged": True, "uvs_unchanged": True, "parts_unchanged": True,
        "units": {"scene": "metres", "fbx_scale_mode": "FBX_SCALE_ALL",
                  "unreal_root_scale_note": "Expected 100x root scale converting metres to centimetres; Unreal import has not been run."},
        "output_fbx": str(out_fbx), "output_fbx_sha256": file_hash(out_fbx),
        "output_blend": str(blend_path), "output_blend_sha256": file_hash(blend_path),
        "status": "candidate_pending_gate_and_deformation",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[LANDMARK RIG] {len(rows)} rigid parts, {len(rig.data.bones)} bones, 100% single-bone weights. Armour, mercifully, is not pudding.")
    return 0
