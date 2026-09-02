"""Build an Auto-Rig Pro candidate from an approved existing humanoid mesh.

This stage is intentionally asset-neutral. It accepts only an upright A-pose
humanoid facing -Y, reads all proportional Smart markers from a checked-in
profile, preserves rest geometry, binds a welded proxy, and transfers at most
four influences back to the approved render topology.

It stops at an unreviewed .blend candidate. Deformation review, ARP's game
export, Manny-profile validation, FBX round trip, UE import, motion, and cook
remain separate gates. A skeleton has many opportunities to lie; we need not
offer it an omnibus command.

Usage:
  blender -b --factory-startup --python-exit-code 1 \
    --python scripts/blender/rig_humanoid_arp.py -- \
    input.glb candidate.blend rig-candidate.json profile.json hand-landmarks.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.hand_landmarks import DIGITS, SIDES, validate_hand_landmarks  # noqa: E402


ADDON_MODULE = "bl_ext.user_default.auto_rig_pro"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def geometry_fingerprint(obj) -> str:
    """Hash rest coordinates and face order, excluding weights and materials."""
    digest = hashlib.sha256()
    for vertex in obj.data.vertices:
        digest.update(struct.pack("<3d", *vertex.co))
    for polygon in obj.data.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", index))
    return digest.hexdigest()


def triangle_count(obj) -> int:
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def weight_diagnostics(obj) -> dict:
    weighted = 0
    maximum = 0
    for vertex in obj.data.vertices:
        influences = sum(group.weight > 1.0e-6 for group in vertex.groups)
        weighted += influences > 0
        maximum = max(maximum, influences)
    count = len(obj.data.vertices)
    return {
        "vertices": count,
        "weighted_vertices": weighted,
        "coverage": weighted / max(1, count),
        "maximum_influences": maximum,
    }


def fill_unweighted_from_nearest(obj) -> int:
    weighted = [
        vertex.index
        for vertex in obj.data.vertices
        if any(group.weight > 1.0e-6 for group in vertex.groups)
    ]
    missing = [
        vertex.index
        for vertex in obj.data.vertices
        if not any(group.weight > 1.0e-6 for group in vertex.groups)
    ]
    if not missing:
        return 0
    if not weighted:
        raise RuntimeError("Bind produced no valid weight samples")
    tree = KDTree(len(weighted))
    for index in weighted:
        tree.insert(obj.data.vertices[index].co, index)
    tree.balance()
    for index in missing:
        _point, nearest, _distance = tree.find(obj.data.vertices[index].co)
        for assignment in obj.data.vertices[nearest].groups:
            obj.vertex_groups[assignment.group].add(
                [index], assignment.weight, "REPLACE"
            )
    return len(missing)


def import_mesh(source: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module=ADDON_MODULE)
    bpy.ops.import_scene.gltf(filepath=str(source))
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if armatures:
        raise RuntimeError(
            "Input already contains an armature; this stage authors a rig for an approved unrigged mesh"
        )
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Input contains no mesh objects")
    inventory = [
        {
            "name": obj.name,
            "vertices": len(obj.data.vertices),
            "triangles": triangle_count(obj),
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        }
        for obj in sorted(meshes, key=lambda item: item.name)
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    body = max(meshes, key=lambda item: len(item.data.vertices))
    bpy.context.view_layer.objects.active = body
    if len(meshes) > 1:
        bpy.ops.object.join()
    body.name = "SK_RAC_Humanoid_Candidate"
    # Applying object transforms preserves visible world-space geometry while
    # giving ray casts and hashes one coordinate system.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return body, inventory


def bounds(obj):
    points = [vertex.co for vertex in obj.data.vertices]
    minimum = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return minimum, maximum


def snap_front_marker(body, minimum, maximum, spec):
    extent = maximum - minimum
    center_x = (minimum.x + maximum.x) * 0.5
    target_x = center_x + extent.x * float(spec["x_ratio"])
    target_z = minimum.z + extent.z * float(spec["z_ratio"])
    search_x = float(spec["search_x"])
    search_z = float(spec["search_z"])
    candidates = []
    for x_step in range(-12, 13):
        for z_step in range(-12, 13):
            x = target_x + extent.x * search_x * x_step / 12.0
            z = target_z + extent.z * search_z * z_step / 12.0
            distance = ((x - target_x) / max(extent.x, 1.0e-8)) ** 2
            distance += ((z - target_z) / max(extent.z, 1.0e-8)) ** 2
            candidates.append((distance, x, z))
    for _distance, x, z in sorted(candidates):
        origin = Vector((x, minimum.y - extent.y * 4.0, z))
        hit, location, _normal, _index = body.ray_cast(
            origin, Vector((0.0, 1.0, 0.0)), distance=extent.y * 8.0
        )
        if hit:
            return tuple(location)
    raise RuntimeError(
        "No front-surface hit near Smart marker x_ratio={0} z_ratio={1}".format(
            spec["x_ratio"], spec["z_ratio"]
        )
    )


def build_markers(body, profile, hand_landmarks):
    minimum, maximum = bounds(body)
    positions = {
        name: snap_front_marker(body, minimum, maximum, spec)
        for name, spec in profile["markers"].items()
        if name != "hand_loc"
    }
    for side, marker_name in (("l", "hand_loc"), ("r", "hand_loc_sym")):
        base_joints = [
            Vector(hand_landmarks["hands"][side]["digits"][digit][0])
            for digit in ("index", "middle", "ring", "pinky")
        ]
        palm = sum(base_joints, Vector()) / len(base_joints)
        positions[marker_name] = tuple(palm)
    for base in ("shoulder", "foot"):
        source = positions[base + "_loc"]
        center_x = (minimum.x + maximum.x) * 0.5
        positions[base + "_loc_sym"] = (
            center_x - (source[0] - center_x), source[1], source[2]
        )
    bpy.ops.object.empty_add(type="PLAIN_AXES", radius=(maximum.z - minimum.z) * 0.01)
    root = bpy.context.object
    root.name = "arp_markers"
    for name, position in positions.items():
        bpy.ops.object.empty_add(type="PLAIN_AXES", radius=(maximum.z - minimum.z) * 0.01,
                                 location=position)
        marker = bpy.context.object
        marker.name = name
        marker.parent = root
    return positions


def configure_smart(body, profile):
    if profile.get("front_axis") != "-Y":
        raise RuntimeError("This first portable ARP profile requires explicit -Y facing")
    scene = bpy.context.scene
    scene.arp_body_name = body.name
    scene.arp_smart_type = "BODY"
    scene.arp_smart_sym = True
    scene.arp_smart_overwrite = False
    scene.arp_fingers_enable = True
    scene.arp_fingers_to_detect = 5
    scene.arp_smart_eyes = False
    scene.arp_disable_smart_fx = True
    scene.arp_debug_mode = False
    smart = profile["smart"]
    scene.arp_smart_preset_settings = "UE5"
    scene.arp_smart_spine_count = int(smart["spine_count"])
    scene.arp_smart_neck_count = int(smart["neck_count"])
    scene.arp_smart_twist_count = int(smart["twist_count"])
    scene.arp_smart_spine_shape = smart["spine_shape"]
    scene.arp_smart_shoulders_align = smart["shoulders_align"]


def apply_reviewed_hand_landmarks(reference, hand_landmarks):
    """Fit ARP reference hands before Match to Rig creates constraints."""
    bpy.context.view_layer.objects.active = reference
    reference.select_set(True)
    mirror_state = reference.data.use_mirror_x
    reference.data.use_mirror_x = False
    bpy.ops.object.mode_set(mode="EDIT")
    world_to_rig = reference.matrix_world.inverted()
    for side in SIDES:
        hand = hand_landmarks["hands"][side]
        wrist = world_to_rig @ Vector(hand["wrist"])
        joints = {
            digit: [world_to_rig @ Vector(point) for point in hand["digits"][digit]]
            for digit in DIGITS
        }
        knuckle = sum((joints[digit][0] for digit in DIGITS), Vector()) / len(DIGITS)
        forward = joints["middle"][-1] - wrist
        lateral = joints["pinky"][0] - joints["index"][0]
        roll_axis = forward.cross(lateral)
        if roll_axis.length <= 1.0e-8:
            raise RuntimeError("Reviewed hand landmarks are collinear on side {0}".format(side))
        roll_axis.normalize()
        hand_ref = reference.data.edit_bones.get("hand_ref." + side)
        if hand_ref is None:
            raise RuntimeError("ARP reference rig has no hand_ref.{0}".format(side))
        hand_ref.head = wrist
        hand_ref.tail = knuckle
        hand_ref.align_roll(roll_axis)
        for digit in DIGITS:
            for index in range(3):
                bone = reference.data.edit_bones.get(
                    "{0}{1}_ref.{2}".format(digit, index + 1, side)
                )
                if bone is None:
                    raise RuntimeError(
                        "ARP reference digit missing: {0}{1}_ref.{2}".format(
                            digit, index + 1, side
                        )
                    )
                bone.head = joints[digit][index]
                bone.tail = joints[digit][index + 1]
                bone.align_roll(roll_axis)
    bpy.ops.object.mode_set(mode="OBJECT")
    reference.data.use_mirror_x = mirror_state
    bpy.context.view_layer.update()


def detect_and_match(body, hand_landmarks):
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    detect_result = bpy.ops.id.go_detect("EXEC_DEFAULT")
    references = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(references) != 1:
        raise RuntimeError("ARP Smart produced {0} reference rigs".format(len(references)))
    reference = references[0]
    required_hands = {
        "{0}1_ref.{1}".format(digit, side)
        for digit in ("thumb", "index", "middle", "ring", "pinky")
        for side in ("l", "r")
    } | {"hand_ref.l", "hand_ref.r"}
    missing = sorted(required_hands - set(reference.data.bones.keys()))
    if missing:
        raise RuntimeError("ARP Smart did not resolve full hands: {0}".format(missing))
    apply_reviewed_hand_landmarks(reference, hand_landmarks)
    bpy.ops.object.select_all(action="DESELECT")
    reference.select_set(True)
    bpy.context.view_layer.objects.active = reference
    match_result = bpy.ops.arp.match_to_rig("EXEC_DEFAULT")
    # Smart Match may finish in Edit/Pose mode, especially after a finger
    # detection warning. Normalize the context before inspecting its output so
    # the report names the anatomical failure rather than an unrelated poll.
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    if "FINISHED" not in match_result:
        raise RuntimeError(
            "ARP Match to Rig did not finish; inspect Smart finger detection and marker evidence"
        )
    rigs = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "ARMATURE" and obj.data.bones.get("c_spine_01.x") is not None
    ]
    if len(rigs) != 1:
        raise RuntimeError("ARP Match to Rig produced {0} control rigs".format(len(rigs)))
    rig = rigs[0]
    rig.name = "RIG_RAC_Humanoid_ARP"
    required_axial = {
        "c_spine_01.x", "c_spine_02.x", "c_spine_03.x", "c_spine_04.x",
        "c_spine_05.x", "c_subneck_1.x", "c_neck.x",
    }
    missing = sorted(required_axial - set(rig.data.bones.keys()))
    if missing:
        raise RuntimeError("ARP did not create the required UE5 axial controls: {0}".format(missing))
    invalid_drivers = []
    if rig.animation_data:
        invalid_drivers = [
            (driver.data_path, driver.array_index)
            for driver in rig.animation_data.drivers if not driver.is_valid
        ]
    if invalid_drivers:
        raise RuntimeError("ARP control rig has {0} invalid drivers".format(len(invalid_drivers)))
    return rig, sorted(detect_result), sorted(match_result)


def bind(body, rig, profile):
    proxy = body.copy()
    proxy.data = body.data.copy()
    proxy.name = "TMP_RAC_ARP_SkinProxy"
    bpy.context.collection.objects.link(proxy)
    proxy.data.materials.clear()
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1.0e-6)
    bpy.ops.object.mode_set(mode="OBJECT")

    settings = profile["bind"]
    if settings["engine"] != "PSEUDO_VOXELS":
        raise RuntimeError("Only the audited PSEUDO_VOXELS bind is portable in v1")
    scene = bpy.context.scene
    scene.arp_body_name = proxy.name
    scene.arp_bind_engine = "PSEUDO_VOXELS"
    scene.arp_pseudo_voxels_type = str(settings["pseudo_voxels_type"])
    scene.arp_pseudo_voxels_resolution = int(settings["pseudo_voxels_resolution"])
    scene.arp_bind_split = False
    scene.arp_bind_chin = True
    scene.arp_bind_preserve = False
    scene.arp_bind_scale_fix = False
    scene.arp_debug_bind = True
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bind_result = bpy.ops.arp.bind_to_rig("EXEC_DEFAULT")
    proxy_filled = fill_unweighted_from_nearest(proxy)
    proxy_diagnostics = weight_diagnostics(proxy)
    if proxy_diagnostics["coverage"] < float(settings["minimum_weight_coverage"]):
        raise RuntimeError("ARP proxy coverage too low: {0:.3%}".format(
            proxy_diagnostics["coverage"]))

    for group in proxy.vertex_groups:
        if body.vertex_groups.get(group.name) is None:
            body.vertex_groups.new(name=group.name)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    transfer = body.modifiers.new(name="TransferARPWeights", type="DATA_TRANSFER")
    transfer.use_vert_data = True
    transfer.data_types_verts = {"VGROUP_WEIGHTS"}
    transfer.vert_mapping = "POLYINTERP_NEAREST"
    transfer.layers_vgroup_select_src = "ALL"
    transfer.layers_vgroup_select_dst = "NAME"
    transfer.mix_mode = "REPLACE"
    transfer.mix_factor = 1.0
    transfer.object = proxy
    bpy.ops.object.modifier_apply(modifier=transfer.name)
    body_filled = fill_unweighted_from_nearest(body)
    armature = body.modifiers.new(name="AutoRigProArmature", type="ARMATURE")
    armature.object = rig
    armature.use_deform_preserve_volume = False
    body.parent = rig
    bpy.data.objects.remove(proxy, do_unlink=True)
    scene.arp_body_name = body.name
    bpy.ops.object.vertex_group_limit_total(
        group_select_mode="ALL", limit=int(settings["maximum_influences"])
    )
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
    diagnostics = weight_diagnostics(body)
    if diagnostics["coverage"] < float(settings["minimum_weight_coverage"]):
        raise RuntimeError("Runtime skin coverage too low: {0:.3%}".format(
            diagnostics["coverage"]))
    if diagnostics["maximum_influences"] > int(settings["maximum_influences"]):
        raise RuntimeError("Runtime skin exceeds influence cap")
    return sorted(bind_result), proxy_filled, body_filled, diagnostics


def main() -> int:
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(arguments) != 5:
        raise RuntimeError(
            "Expected input.glb output.blend report.json marker-profile.json hand-landmarks.json"
        )
    source, output_blend, report_path, profile_path, hand_path = map(Path, arguments)
    source = source.resolve()
    output_blend = output_blend.resolve()
    report_path = report_path.resolve()
    profile_path = profile_path.resolve()
    hand_path = hand_path.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output_blend.exists() or report_path.exists():
        raise RuntimeError("Refusing to overwrite an existing rig candidate or report")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    source_hash = sha256(source)
    hand_payload = json.loads(hand_path.read_text(encoding="utf-8"))
    hand_landmarks = validate_hand_landmarks(hand_payload, source_hash)

    body, source_parts = import_mesh(source)
    geometry_before = geometry_fingerprint(body)
    configure_smart(body, profile)
    marker_positions = build_markers(body, profile, hand_landmarks)
    rig, detect_result, match_result = detect_and_match(body, hand_landmarks)
    bind_result, proxy_filled, body_filled, diagnostics = bind(body, rig, profile)
    geometry_after = geometry_fingerprint(body)
    if geometry_after != geometry_before:
        raise RuntimeError("Rigging changed approved rest geometry or face order")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.arp-rig-candidate.v1",
        "status": "unreviewed_candidate",
        "source": {"path": str(source), "sha256": source_hash},
        "profile": {"path": str(profile_path), "sha256": sha256(profile_path),
                    "profile_id": profile["profile_id"]},
        "hand_landmarks": {"path": str(hand_path), "sha256": sha256(hand_path),
                           "review": hand_landmarks["review"]},
        "source_parts": source_parts,
        "joined_vertices": len(body.data.vertices),
        "joined_triangles": triangle_count(body),
        "rest_geometry_sha256": geometry_after,
        "rest_geometry_preserved": True,
        "marker_positions": marker_positions,
        "operations": {"detect": detect_result, "match": match_result, "bind": bind_result},
        "rig": {"control_bones": len(rig.data.bones),
                "deform_bones": sum(bone.use_deform for bone in rig.data.bones)},
        "weights": {**diagnostics, "proxy_vertices_filled": proxy_filled,
                    "runtime_vertices_filled": body_filled},
        "output_blend": str(output_blend),
        "production_grade": False,
        "required_next_gates": [
            "fixed-view rest and deformation review",
            "asset-specific hand and clothing weight review",
            "ARP game-engine export",
            "ue5_manny profile gate and FBX round trip",
            "UE5 motion review and cooked runtime",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_ARP_RIG_CANDIDATE_OK report={0}".format(report_path))
    print("The skeleton has passed mechanics, not judgment. Charming posture is not evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
