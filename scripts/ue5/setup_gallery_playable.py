"""Make the gallery walkable and put every character in the Manny idle pose.

Runs after ``build_gallery_level.py``. Two jobs:

1. Idle poses. Epic's ``MM_Idle`` is bound to the Manny skeleton. Every
   compiled character has its own skeleton asset, so the idle is retargeted
   onto each one through an IK Retargeter built here from bone names: one IK
   Rig for Manny, one per target skeleton, chains named identically so the
   exact-name auto-map lines them up (Root, Spine, Head, clavicles, arms,
   legs). A mascot's tail has no Manny chain and is deliberately left
   unmapped, exactly as ``mascot_biped_tail.retarget_note`` demands, so it
   holds its rest pose instead of inheriting spine motion. The retargeted
   sequences land under ``/Game/Compiled/Retargeted`` and every
   SkeletalMeshActor in the gallery plays its own copy, looping.

2. Playability. The project's default game mode is the Third Person template
   game mode (``Config/DefaultEngine.ini``), whose character is Manny. The
   gallery already has a PlayerStart, so pressing Play drops the reviewer in
   as Manny facing the line-up.

Every retarget result is recorded in ``work/ue5-gallery-idle.json`` so a
character that failed to retarget is listed, not silently left in bind pose.

Runs headless:
  UnrealEditor-Cmd.exe <project> -ExecutePythonScript="<this file>" \
      -unattended -nop4 -nosplash -stdout
"""

from __future__ import annotations

import json
import os
import traceback

import unreal

ROOT = os.environ.get("RAC_ROOT")
LEVEL_PATH = "/Game/Compiled/L_RacGallery"
MANNY_MESH = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
IDLE_ANIM = "/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle"
RETARGET_FOLDER = "/Game/Compiled/Retargeted"
# Each run gets its own subfolder: assets deleted earlier in the same editor
# session cannot be recreated under the same object path, so a rebuild that
# reuses names fails silently with a None asset.
RUN_TOKEN = os.environ.get("RAC_RETARGET_RUN") or __import__("datetime").datetime.now().strftime("r%Y%m%d%H%M%S")
RIG_FOLDER = "{0}/{1}/Rigs".format(RETARGET_FOLDER, RUN_TOKEN)
ANIM_FOLDER = "{0}/{1}/Anims".format(RETARGET_FOLDER, RUN_TOKEN)

# Chains by name; each entry is (start bone, candidate end bones in preference
# order). A chain is added only when both ends exist on the skeleton, so the
# same table serves Manny (spine_05, ball_l), the UE4 mannequin (spine_03,
# ball_l) and the mascot (spine_03, foot_l, no fingers).
CHAINS = {
    "Spine": ("spine_01", ("spine_05", "spine_04", "spine_03", "spine_02")),
    "Head": ("neck_01", ("head",)),
    "LeftClavicle": ("clavicle_l", ("clavicle_l",)),
    "RightClavicle": ("clavicle_r", ("clavicle_r",)),
    "LeftArm": ("upperarm_l", ("hand_l",)),
    "RightArm": ("upperarm_r", ("hand_r",)),
    "LeftLeg": ("thigh_l", ("ball_l", "foot_l")),
    "RightLeg": ("thigh_r", ("ball_r", "foot_r")),
}
RETARGET_ROOT = "pelvis"


def bones_of(mesh):
    """Bone names via a transient component; USkeleton exposes none to Python."""
    return skeleton_probe(mesh)[0]


def skeleton_probe(mesh):
    """Bone names plus the cumulative ancestor scale above the pelvis.

    Blender's FBX export leaves these skeletons with bone offsets in metres
    under a root scaled by 100. The retargeter writes the pelvis translation in
    component centimetres as if that root were unit scale, which lifts the
    character 100x too high. The factor is measured here, never assumed.
    """
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, -100000), unreal.Rotator())
    try:
        component = actor.skeletal_mesh_component
        component.set_skeletal_mesh_asset(mesh)
        names = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
        scale = 1.0
        ancestors = []
        if RETARGET_ROOT in names:
            bone = str(component.get_parent_bone(RETARGET_ROOT))
            while bone and bone != "None":
                local = component.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
                scale *= float(local.scale3d.z)
                ancestors.append(bone)
                bone = str(component.get_parent_bone(bone))
        return names, scale, ancestors
    finally:
        unreal.EditorLevelLibrary.destroy_actor(actor)


def create_asset(name, folder, asset_class, factory):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = "{0}/{1}".format(folder, name)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    asset = tools.create_asset(name, folder, asset_class, factory)
    if asset is None:
        raise RuntimeError("could not create {0}".format(path))
    return asset


def build_ik_rig(name, mesh, bones):
    rig = create_asset(name, RIG_FOLDER, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    controller.set_skeletal_mesh(mesh)
    present = set(bones)
    if RETARGET_ROOT not in present:
        raise RuntimeError("{0}: no '{1}' bone".format(name, RETARGET_ROOT))
    controller.set_retarget_root(RETARGET_ROOT)
    added = {}
    for chain, (start, ends) in CHAINS.items():
        end = next((e for e in ends if e in present), None)
        if start not in present or end is None:
            continue
        controller.add_retarget_chain(chain, start, end, "None")
        added[chain] = [start, end]
    unreal.EditorAssetLibrary.save_loaded_asset(rig)
    return rig, added


def build_retargeter(name, source_rig, target_rig, source_mesh, target_mesh, ancestor_scale=1.0, align="none"):
    retargeter = create_asset(name, RIG_FOLDER, unreal.IKRetargeter, unreal.IKRetargetFactory())
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source_mesh)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target_mesh)
    notes = []
    # Pelvis motion and FK chains only. These skeletons carry bone offsets in
    # metres under a root scaled 100x (Blender FBX export); the pelvis op writes
    # component-space centimetres into that local space, which
    # ``rescale_pelvis_track`` corrects afterwards. IK ops are omitted because
    # their goals would be misplaced the same way and an idle does not need them.
    for op_type in ("/Script/IKRig.IKRetargetPelvisMotionOp", "/Script/IKRig.IKRetargetFKChainsOp"):
        index = controller.add_retarget_op(op_type)
        try:
            controller.run_op_initial_setup(index)
        except Exception as error:  # noqa: BLE001
            notes.append("initial setup failed for {0}: {1}".format(op_type, error))
        notes.append("op:" + op_type.rsplit(".", 1)[-1])
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    if align == "all":
        try:
            controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET)
            notes.append("auto_align_all_bones")
        except Exception as error:  # noqa: BLE001 - alignment is a nicety
            notes.append("auto_align failed: {0}".format(error))
    elif align == "limbs":
        limbs = ["upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
                 "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]
        try:
            controller.auto_align_bones(limbs, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN,
                                        unreal.RetargetSourceOrTarget.TARGET)
            notes.append("auto_align_bones(limbs only)")
        except Exception as error:  # noqa: BLE001
            notes.append("limb auto_align failed: {0}".format(error))
    else:
        notes.append("retarget pose = reference pose (no auto-align)")
    unreal.EditorAssetLibrary.save_loaded_asset(retargeter)
    return retargeter, notes


def rescale_pelvis_track(anim, factor):
    """Divide the pelvis translation keys by the ancestor scale, in place."""
    AL = unreal.AnimationLibrary
    keys = int(AL.get_num_keys(anim))
    positions, rotations, scales = [], [], []
    for key in range(keys):
        pose = AL.get_bone_pose_for_frame(anim, RETARGET_ROOT, key, False)
        t = pose.translation
        positions.append(unreal.Vector(t.x * factor, t.y * factor, t.z * factor))
        rotations.append(pose.rotation)
        scales.append(pose.scale3d)
    controller = anim.controller
    controller.open_bracket("RAC pelvis scale compensation", False)
    ok = controller.set_bone_track_keys(RETARGET_ROOT, positions, rotations, scales, False)
    controller.close_bracket(False)
    if not ok:
        raise RuntimeError("could not rewrite the pelvis track")
    return len(positions)


def strip_ancestor_tracks(anim, ancestors):
    """Remove tracks for the bones above the pelvis.

    The retargeter writes those tracks with unit scale, which overrides the
    skeleton's 100x root scale at playback and shrinks the character to a few
    centimetres. Without a track the bone plays its reference pose.
    """
    AL = unreal.AnimationLibrary
    present = {str(t).lower(): str(t) for t in AL.get_animation_track_names(anim)}
    controller = anim.controller
    removed = []
    controller.open_bracket("RAC strip scaled ancestor tracks", False)
    for bone in ancestors:
        track = present.get(bone.lower())
        if track and controller.remove_bone_track(track, False):
            removed.append(track)
    controller.close_bracket(False)
    return removed


def posed_head_height(mesh, anim):
    """World Z of the head with the idle applied, via a transient actor."""
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator())
    try:
        component = actor.skeletal_mesh_component
        component.set_skeletal_mesh_asset(mesh)
        component.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        component.override_animation_data(anim, True, True, 0.0, 1.0)
        component.set_position(0.0, False)
        component.refresh_bone_transforms()
        head = component.get_socket_location("head").z
        pelvis = component.get_socket_location(RETARGET_ROOT).z
        return head, pelvis
    finally:
        unreal.EditorLevelLibrary.destroy_actor(actor)


REST_ANCHORS = ("head", "foot_l", "foot_r")


def evaluate_pose(component, anim, frame):
    """Component-space bone positions at one frame, composed from the data.

    A placed component does not re-evaluate its animation inside a commandlet,
    so poses are composed here: each bone takes its animation track transform
    when it has one, otherwise its reference-pose local transform (which is how
    the stripped, scaled root contributes its 100x), and the chain is composed
    parent-first in skeleton index order.
    """
    AL = unreal.AnimationLibrary
    tracks = {str(t).lower(): str(t) for t in AL.get_animation_track_names(anim)}
    names = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    world = {}
    for name in names:
        track = tracks.get(name.lower())
        if track and anim is not None:
            local = AL.get_bone_pose_for_frame(anim, track, frame, False)
        else:
            local = component.get_socket_transform(name, unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
        parent = str(component.get_parent_bone(name))
        if parent and parent != "None" and parent in world:
            world[name] = unreal.MathLibrary.compose_transforms(local, world[parent])
        else:
            world[name] = local
    return {name: transform.translation for name, transform in world.items()}


SEGMENTS = (("neck_01", "head"), ("pelvis", "spine_03"),
            ("upperarm_l", "lowerarm_l"), ("lowerarm_l", "hand_l"),
            ("upperarm_r", "lowerarm_r"), ("lowerarm_r", "hand_r"),
            ("thigh_l", "calf_l"), ("calf_l", "foot_l"),
            ("thigh_r", "calf_r"), ("calf_r", "foot_r"))
SAMPLE_FRAMES = (0, 60, 120, 180)


def segment_directions(component, anim, frame):
    pose = evaluate_pose(component, anim, frame)
    out = {}
    for a, b in SEGMENTS:
        if a in pose and b in pose:
            d = pose[b] - pose[a]
            if d.length() > 1e-3:
                d.normalize()
                out[(a, b)] = d
    return out


def pose_mismatch(component, anim, source_dirs):
    """Mean angle (degrees) between the target's posed limb segments and the
    source Manny's, over sampled frames. The retarget is right when the target
    ends up in the same pose as the source, whatever its rest pose was."""
    import math
    total, count = 0.0, 0
    for frame in SAMPLE_FRAMES:
        target_dirs = segment_directions(component, anim, frame)
        for key, src in source_dirs[frame].items():
            tgt = target_dirs.get(key)
            if tgt is None:
                continue
            total += math.degrees(math.acos(max(-1.0, min(1.0, float(src.dot(tgt))))))
            count += 1
    return total / max(count, 1)


def retarget_idle(retargeter, source_mesh, target_mesh, suffix):
    idle_data = unreal.EditorAssetLibrary.find_asset_data(IDLE_ANIM)
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.set_editor_property("assets_to_retarget", [idle_data])
    inputs.set_editor_property("source_mesh", source_mesh)
    inputs.set_editor_property("target_mesh", target_mesh)
    inputs.set_editor_property("ik_retarget_asset", retargeter)
    inputs.set_editor_property("suffix", "_" + suffix)
    inputs.set_editor_property("target_path", ANIM_FOLDER)
    inputs.set_editor_property("use_source_path", False)
    inputs.set_editor_property("include_referenced_assets", False)
    inputs.set_editor_property("overwrite_existing_files", True)
    results = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    anims = []
    for data in results:
        asset = data.get_asset()
        if isinstance(asset, unreal.AnimSequence):
            anims.append(asset)
    if not anims:
        raise RuntimeError("batch retarget produced no AnimSequence")
    return anims[0]


def manifest_index():
    """asset folder name -> manifest, from out/<id>/<id>.ue5import.json."""
    index = {}
    if not ROOT:
        return index
    out_root = os.path.join(ROOT, "out")
    for name in sorted(os.listdir(out_root)):
        path = os.path.join(out_root, name, name + ".ue5import.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as handle:
                manifest = json.load(handle)
            folder = "".join(p.capitalize() for p in name.replace("_", "-").split("-"))
            index[folder] = manifest
    return index


def main():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not level_subsystem.load_level(LEVEL_PATH):
        unreal.log_error("RAC could not load {0}".format(LEVEL_PATH))
        return

    manny = unreal.EditorAssetLibrary.load_asset(MANNY_MESH)
    if manny is None or unreal.EditorAssetLibrary.load_asset(IDLE_ANIM) is None:
        unreal.log_error("RAC Manny mesh or MM_Idle is missing from the project")
        return

    # A rebuild must start clean: drop the level's references to the previous
    # retargeted idles, then remove the whole retarget folder. Otherwise the
    # old rigs cannot be deleted and asset creation silently returns None.
    for actor in actor_subsystem.get_all_level_actors():
        if isinstance(actor, unreal.SkeletalMeshActor):
            component = actor.skeletal_mesh_component
            component.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_CUSTOM_MODE)
            component.set_editor_property("animation_data", unreal.SingleAnimationPlayData())
    if unreal.EditorAssetLibrary.does_directory_exist(RETARGET_FOLDER):
        try:
            if not unreal.EditorAssetLibrary.delete_directory(RETARGET_FOLDER):
                unreal.log_warning("RAC could not delete {0}; stale assets may remain".format(RETARGET_FOLDER))
        except Exception as error:  # noqa: BLE001 - stale anims whose skeleton is gone refuse to load
            unreal.log_warning("RAC could not delete {0}: {1}".format(RETARGET_FOLDER, error))
    manny_bones = bones_of(manny)
    manny_rig, manny_chains = build_ik_rig("IK_RAC_Manny", manny, manny_bones)
    idle = unreal.EditorAssetLibrary.load_asset(IDLE_ANIM)
    probe = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, -100000), unreal.Rotator())
    try:
        probe.skeletal_mesh_component.set_skeletal_mesh_asset(manny)
        manny_dirs = {frame: segment_directions(probe.skeletal_mesh_component, idle, frame) for frame in SAMPLE_FRAMES}
    finally:
        unreal.EditorLevelLibrary.destroy_actor(probe)
    unreal.log("RAC Manny IK rig chains: {0}".format(sorted(manny_chains)))

    report = {"level": LEVEL_PATH, "source_mesh": MANNY_MESH, "idle": IDLE_ANIM, "run_folder": RIG_FOLDER.rsplit("/", 1)[0],
              "manny_chains": manny_chains, "characters": []}
    manifests = manifest_index()
    rigs_by_mesh = {}

    for actor in actor_subsystem.get_all_level_actors():
        if not isinstance(actor, unreal.SkeletalMeshActor):
            continue
        component = actor.skeletal_mesh_component
        mesh = component.get_skeletal_mesh_asset()
        if mesh is None:
            continue
        mesh_path = mesh.get_path_name()
        folder = mesh_path.split("/")[3] if mesh_path.startswith("/Game/Compiled/") else None
        entry = {"actor": actor.get_actor_label(), "mesh": mesh_path,
                 "skeleton_profile": (manifests.get(folder) or {}).get("skeleton_profile")}
        try:
            if mesh_path not in rigs_by_mesh:
                bones, ancestor_scale, ancestors = skeleton_probe(mesh)
                short = folder or mesh.get_name()
                rig, chains = build_ik_rig("IK_RAC_" + short, mesh, bones)
                variants = []
                for align in ("none", "limbs", "all"):
                    tag = {"none": "refpose", "limbs": "limbsaligned", "all": "allaligned"}[align]
                    retargeter, notes = build_retargeter(
                        "RTG_RAC_Manny_to_{0}_{1}".format(short, tag), manny_rig, rig, manny, mesh,
                        ancestor_scale, align)
                    anim = retarget_idle(retargeter, manny, mesh, "{0}_{1}".format(short, tag))
                    if abs(ancestor_scale - 1.0) > 1e-3:
                        keys = rescale_pelvis_track(anim, 1.0 / ancestor_scale)
                        removed = strip_ancestor_tracks(anim, ancestors)
                        unreal.EditorAssetLibrary.save_loaded_asset(anim)
                        notes.append("pelvis track rescaled by {0:.4f} over {1} keys (ancestor scale {2:.1f}); ancestor tracks removed: {3}".format(
                            1.0 / ancestor_scale, keys, ancestor_scale, removed))
                    mismatch = pose_mismatch(component, anim, manny_dirs)
                    variants.append({"tag": tag, "retargeter": retargeter, "anim": anim, "notes": notes,
                                     "pose_mismatch_deg": round(mismatch, 1)})
                    unreal.log("RAC variant {0} {1}: mean segment mismatch vs Manny {2:.1f} deg".format(short, tag, mismatch))
                # Policy, not the raw metric: aligning every bone scores best on
                # segment direction but pitches faces down, because these
                # skeletons' head and spine bones tilt differently from Manny's
                # while their faces already look forward. Limb rest poses do
                # differ legitimately (the ninja is near a T-pose), so only limbs
                # are aligned. The metric is recorded for every variant.
                preferred = [v for v in variants if v["tag"] == "limbsaligned"]
                best = preferred[0] if preferred else min(variants, key=lambda v: v["pose_mismatch_deg"])
                retargeter, anim, notes = best["retargeter"], best["anim"], list(best["notes"])
                notes.append("chosen {0} by policy; mismatch vs Manny {1}".format(
                    best["tag"], {v["tag"]: v["pose_mismatch_deg"] for v in variants}))
                pelvis0 = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, RETARGET_ROOT, 0, False).translation
                pelvis_cm = pelvis0.length() * ancestor_scale
                notes.append("retargeted pelvis frame0 local=({0:.3f},{1:.3f},{2:.3f}) ancestor scale {3:.1f} -> {4:.1f} cm from parent".format(
                    pelvis0.x, pelvis0.y, pelvis0.z, ancestor_scale, pelvis_cm))
                if not (20.0 < pelvis_cm < 200.0):
                    raise RuntimeError("retargeted pelvis height implausible: {0}".format(notes[-1]))
                rigs_by_mesh[mesh_path] = {
                    "rig": rig.get_path_name(), "chains": chains,
                    "retargeter": retargeter.get_path_name(), "notes": notes,
                    "retarget_pose_variant": best["tag"],
                    "pose_mismatch_deg": {v["tag"]: v["pose_mismatch_deg"] for v in variants},
                    "idle": anim.get_path_name(),
                    "unmapped_target_bones_note": (
                        "tail chain intentionally absent" if "tail_01" in bones else None),
                    "anim": anim,
                }
            record = rigs_by_mesh[mesh_path]
            anim = record["anim"]
            component.set_editor_property("animation_mode",
                                          unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            component.override_animation_data(anim, True, True, 0.0, 1.0)
            # The placed actor evaluates the pose on assignment, so the posed
            # head height is a direct check that the skeleton neither collapsed
            # nor flew off: it must sit between 55% and 105% of the mesh height
            # above the actor's own feet.
            head_z = float(evaluate_pose(component, anim, 0)["head"].z)
            mesh_height = float(mesh.get_bounds().box_extent.z) * 2.0
            entry["posed_head_z_cm"] = round(head_z, 1)
            entry["mesh_height_cm"] = round(mesh_height, 1)
            if not (0.55 * mesh_height < head_z < 1.05 * mesh_height):
                raise RuntimeError("posed skeleton implausible: head z {0:.1f} of mesh height {1:.1f}".format(head_z, mesh_height))
            entry.update({k: v for k, v in record.items() if k != "anim"})
            entry["ok"] = True
            unreal.log("RAC idle assigned: {0} <- {1}".format(actor.get_actor_label(), record["idle"]))
        except Exception as error:  # noqa: BLE001 - report every failure, keep going
            entry.update({"ok": False, "error": str(error), "traceback": traceback.format_exc()})
            unreal.log_error("RAC idle FAILED for {0}: {1}".format(actor.get_actor_label(), error))
        report["characters"].append(entry)

    unreal.EditorAssetLibrary.save_directory(RETARGET_FOLDER, recursive=True)
    level_subsystem.save_current_level()
    report["ok"] = all(c.get("ok") for c in report["characters"]) and bool(report["characters"])
    unreal.log("RAC_GALLERY_IDLE_SAVED ok={0} characters={1}".format(
        report["ok"], len(report["characters"])))
    if ROOT:
        with open(os.path.join(ROOT, "work", "ue5-gallery-idle.json"), "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)


main()
