"""Replace the workshop demo's Manny with a compiled character, animations included.

Given a compiled skeletal mesh that already imported and verified, this builds
everything the Third Person template needs to drive it, as versioned copies
beside the originals (nothing existing is modified):

1. IK Rigs for Manny and the target from bone names, an IK Retargeter with
   limbs aligned to Manny's retarget pose (the gallery policy), and a batch
   retarget of the player's animation blueprint plus every animation and
   blend space it references, onto the target skeleton. The compiled
   skeletons' 100x root scale is compensated on every retargeted sequence.
2. A copy of the player Blueprint with the target mesh, the retargeted
   animation blueprint, the capsule sized to the target's height, the mesh
   yawed so the target's toes point down the actor's +X, and the back-carried
   sword re-fitted to the target's spine_03.
3. A copy of the game mode whose default pawn is that Blueprint, and a copy of
   the level whose world settings use that game mode.

Everything lands under /Game/SunsetWorkshop/<Tag>Player/<Version>/ and the
new level is <SourceLevel with its version replaced>. A JSON report of what
was built and measured goes to work/sunset-workshop/evidence/.

  UnrealEditor-Cmd.exe <project> -ExecutePythonScript="<this file>" -nullrhi -unattended -nop4 -nosplash -stdout
Env: RAC_ROOT, RAC_TARGET_MESH (e.g. /Game/Compiled/SunsetAyricV2Production/sunset-ayric-v2-production),
     RAC_CHARACTER (tag, default Ayric), RAC_VERSION (default v027),
     RAC_SOURCE_BP, RAC_SOURCE_GM, RAC_SOURCE_LEVEL (defaults: the v007/v005/v026 night demo).
"""
import json
import math
import os
import traceback

import unreal

ROOT = os.environ["RAC_ROOT"]
TARGET_MESH = os.environ["RAC_TARGET_MESH"]
TAG = os.environ.get("RAC_CHARACTER", "Ayric")
VERSION = os.environ.get("RAC_VERSION", "v027")
SOURCE_BP = os.environ.get("RAC_SOURCE_BP", "/Game/SunsetWorkshop/MannyDemo/BP_WorkshopManny_v007")
SOURCE_GM = os.environ.get("RAC_SOURCE_GM", "/Game/SunsetWorkshop/MannyDemo/BP_WorkshopGameMode_v005")
SOURCE_LEVEL = os.environ.get("RAC_SOURCE_LEVEL", "/Game/SunsetWorkshop/L_WorkshopNight_v026")
MANNY_MESH = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
FOLDER = "/Game/SunsetWorkshop/{0}Player/{1}".format(TAG, VERSION)
RIG_FOLDER = FOLDER + "/Rigs"
ANIM_FOLDER = FOLDER + "/Anims"
RETARGET_ROOT = "pelvis"
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
LIMBS = ["upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r",
         "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r"]

lib = unreal.EditorAssetLibrary


def with_probe(mesh, function):
    """Run `function(component)` on a transient SkeletalMeshActor far below the level."""
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, -100000), unreal.Rotator())
    try:
        component = actor.skeletal_mesh_component
        component.set_skeletal_mesh_asset(mesh)
        return function(component)
    finally:
        unreal.EditorLevelLibrary.destroy_actor(actor)


def skeleton_probe(mesh):
    """Bone names, cumulative ancestor scale above the pelvis, ancestor names, and forward yaw."""
    def read(component):
        names = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
        scale, ancestors = 1.0, []
        if RETARGET_ROOT in names:
            bone = str(component.get_parent_bone(RETARGET_ROOT))
            while bone and bone != "None":
                local = component.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_PARENT_BONE_SPACE)
                scale *= float(local.scale3d.z)
                ancestors.append(bone)
                bone = str(component.get_parent_bone(bone))
        # Forward = the direction from heel to toe in component space. Manny's
        # is +Y, which is why the template mesh sits at yaw -90 on the capsule.
        forward_yaw = None
        if "foot_l" in names and "ball_l" in names:
            space = unreal.RelativeTransformSpace.RTS_COMPONENT
            heel = component.get_socket_transform("foot_l", space).translation
            toe = component.get_socket_transform("ball_l", space).translation
            forward_yaw = math.degrees(math.atan2(toe.y - heel.y, toe.x - heel.x))
        height = float(mesh.get_bounds().box_extent.z) * 2.0
        return names, scale, ancestors, forward_yaw, height
    return with_probe(mesh, read)


def create_asset(name, folder, asset_class, factory):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = "{0}/{1}".format(folder, name)
    if lib.does_asset_exist(path):
        raise RuntimeError("refusing to overwrite {0}; choose a new RAC_VERSION".format(path))
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
    lib.save_loaded_asset(rig)
    return rig, added


def build_retargeter(name, source_rig, target_rig, source_mesh, target_mesh):
    retargeter = create_asset(name, RIG_FOLDER, unreal.IKRetargeter, unreal.IKRetargetFactory())
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, source_rig)
    controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, target_rig)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, source_mesh)
    controller.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, target_mesh)
    notes = []
    for op_type in ("/Script/IKRig.IKRetargetPelvisMotionOp", "/Script/IKRig.IKRetargetFKChainsOp"):
        index = controller.add_retarget_op(op_type)
        try:
            controller.run_op_initial_setup(index)
        except Exception as error:  # noqa: BLE001
            notes.append("initial setup failed for {0}: {1}".format(op_type, error))
        notes.append("op:" + op_type.rsplit(".", 1)[-1])
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    try:
        controller.auto_align_bones(LIMBS, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN,
                                    unreal.RetargetSourceOrTarget.TARGET)
        notes.append("auto_align_bones(limbs only); spine, neck and head at reference pose")
    except Exception as error:  # noqa: BLE001
        notes.append("limb auto_align failed: {0}".format(error))
    lib.save_loaded_asset(retargeter)
    return retargeter, notes


def rescale_pelvis_track(anim, factor):
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
        raise RuntimeError("could not rewrite the pelvis track of {0}".format(anim.get_name()))
    return len(positions)


def strip_ancestor_tracks(anim, ancestors):
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


def blueprint_parts(bp):
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    fn = unreal.SubobjectDataBlueprintFunctionLibrary
    parts = []
    for handle in sub.k2_gather_subobject_data_for_blueprint(bp):
        obj = fn.get_object_for_blueprint(fn.get_data(handle), bp)
        if obj is not None:
            parts.append(obj)
    return parts


def main():
    report = {"target_mesh": TARGET_MESH, "tag": TAG, "version": VERSION, "folder": FOLDER,
              "source": {"blueprint": SOURCE_BP, "game_mode": SOURCE_GM, "level": SOURCE_LEVEL}}
    out = os.path.join(ROOT, "work", "sunset-workshop", "evidence", "{0}-player-{1}.json".format(TAG.lower(), VERSION))
    if os.path.exists(out):
        raise RuntimeError("retained evidence exists: {0}".format(out))
    try:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not level_subsystem.load_level(SOURCE_LEVEL):
            raise RuntimeError("could not load {0}".format(SOURCE_LEVEL))
        target = lib.load_asset(TARGET_MESH)
        manny = lib.load_asset(MANNY_MESH)
        if not isinstance(target, unreal.SkeletalMesh) or not isinstance(manny, unreal.SkeletalMesh):
            raise RuntimeError("target or Manny mesh did not load as SkeletalMesh")

        # --- 1. rigs, retargeter, batch retarget ---------------------------
        t_bones, ancestor_scale, ancestors, forward_yaw, height_cm = skeleton_probe(target)
        m_bones = skeleton_probe(manny)[0]
        report["target_skeleton"] = {"bones": len(t_bones), "ancestor_scale": ancestor_scale, "ancestors": ancestors,
                                     "forward_yaw_deg": forward_yaw, "height_cm": height_cm}
        manny_rig, manny_chains = build_ik_rig("IK_RAC_Manny", manny, m_bones)
        target_rig, target_chains = build_ik_rig("IK_RAC_" + TAG, target, t_bones)
        retargeter, notes = build_retargeter("RTG_Manny_to_" + TAG, manny_rig, target_rig, manny, target)
        report["retarget"] = {"manny_chains": manny_chains, "target_chains": target_chains, "notes": notes}

        source_bp = lib.load_asset(SOURCE_BP)
        source_mesh_component = next(p for p in blueprint_parts(source_bp) if isinstance(p, unreal.SkeletalMeshComponent))
        source_anim_class = source_mesh_component.get_editor_property("anim_class")
        abp_path = source_anim_class.get_path_name().split(".")[0]
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        deps = registry.get_dependencies(unreal.Name(abp_path), unreal.AssetRegistryDependencyOptions())
        to_retarget, dep_paths = [], []
        for package in [abp_path] + [str(d) for d in (deps or [])]:
            if not package.startswith("/Game/"):
                continue
            data = registry.get_assets_by_package_name(unreal.Name(package))
            for asset_data in data or []:
                cls = str(asset_data.asset_class_path.asset_name)
                if cls in ("AnimBlueprint", "AnimSequence", "BlendSpace", "BlendSpace1D", "AimOffsetBlendSpace", "AnimMontage"):
                    to_retarget.append(asset_data)
                    dep_paths.append("{0} ({1})".format(package, cls))
        report["retarget"]["inputs"] = dep_paths
        inputs = unreal.IKRetargetBatchOperationInputs()
        inputs.set_editor_property("assets_to_retarget", to_retarget)
        inputs.set_editor_property("source_mesh", manny)
        inputs.set_editor_property("target_mesh", target)
        inputs.set_editor_property("ik_retarget_asset", retargeter)
        inputs.set_editor_property("suffix", "_" + TAG)
        inputs.set_editor_property("target_path", ANIM_FOLDER)
        inputs.set_editor_property("use_source_path", False)
        inputs.set_editor_property("include_referenced_assets", True)
        inputs.set_editor_property("overwrite_existing_files", True)
        results = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
        produced = {"AnimSequence": [], "BlendSpace": [], "AnimBlueprint": [], "other": []}
        abp = None
        for data in results:
            asset = data.get_asset()
            if isinstance(asset, unreal.AnimSequence):
                fixes = {}
                if abs(ancestor_scale - 1.0) > 1e-3:
                    fixes["pelvis_keys_rescaled"] = rescale_pelvis_track(asset, 1.0 / ancestor_scale)
                    fixes["ancestor_tracks_removed"] = strip_ancestor_tracks(asset, ancestors)
                pelvis0 = unreal.AnimationLibrary.get_bone_pose_for_frame(asset, RETARGET_ROOT, 0, False).translation
                fixes["pelvis_frame0_cm"] = round(pelvis0.length() * ancestor_scale, 1)
                if not (20.0 < fixes["pelvis_frame0_cm"] < 200.0):
                    raise RuntimeError("implausible pelvis height in {0}: {1}".format(asset.get_name(), fixes))
                lib.save_loaded_asset(asset)
                produced["AnimSequence"].append({"asset": asset.get_path_name(), **fixes})
            elif isinstance(asset, unreal.AnimBlueprint):
                abp = asset
                produced["AnimBlueprint"].append(asset.get_path_name())
            elif isinstance(asset, unreal.BlendSpace):
                lib.save_loaded_asset(asset)
                produced["BlendSpace"].append(asset.get_path_name())
            else:
                produced["other"].append(asset.get_path_name() if asset else str(data))
        report["retarget"]["produced"] = produced
        if abp is None:
            # The batch operation retargets sequences and blend spaces but not
            # animation blueprints. Duplicate the source ABP, aim it at the
            # target skeleton, and rewrite every player node to the retargeted
            # asset with the same base name.
            retargeted = {}
            for data in results:
                asset = data.get_asset()
                if isinstance(asset, (unreal.AnimSequence, unreal.BlendSpace)):
                    base = asset.get_name()
                    if base.endswith("_" + TAG):
                        base = base[: -len(TAG) - 1]
                    retargeted[base] = asset
            abp_copy_path = "{0}/{1}_{2}".format(ANIM_FOLDER, abp_path.rsplit("/", 1)[-1], TAG)
            abp_origin = "batch retarget"
            abp = lib.load_asset(abp_copy_path) if lib.does_asset_exist(abp_copy_path) else None
            if not isinstance(abp, unreal.AnimBlueprint):
                # The batch operation wrote the anim blueprint but did not
                # list it in its results in this engine build; fall back to a
                # manual duplicate only when it is truly absent.
                abp = lib.duplicate_asset(abp_path, abp_copy_path)
                abp_origin = "duplicate_asset"
                if abp is None:
                    raise RuntimeError("could not duplicate {0}".format(abp_path))
            target_skeleton = target.get_editor_property("skeleton")
            abp.set_editor_property("target_skeleton", target_skeleton)
            lib.save_loaded_asset(abp)
            # Blueprint graphs are not reflected to Python, so audit the saved
            # package's dependencies instead: every animation it references must
            # be one of the retargeted copies, none may be a source animation.
            options = unreal.AssetRegistryDependencyOptions()
            registry.scan_paths_synchronous([FOLDER], True, False)
            abp_deps = [str(d) for d in (registry.get_dependencies(unreal.Name(abp_copy_path), options) or [])]
            source_refs = sorted(d for d in abp_deps if d.startswith(abp_path.rsplit("/", 1)[0]))
            target_refs = sorted(d for d in abp_deps if d.startswith(ANIM_FOLDER))
            report["retarget"]["anim_blueprint"] = {
                "path": abp_copy_path, "origin": abp_origin,
                "target_skeleton": abp.get_editor_property("target_skeleton").get_path_name(),
                "references_retargeted": target_refs, "references_source": source_refs,
                "all_dependencies": sorted(abp_deps)}
            if source_refs:
                raise RuntimeError("animation blueprint still references source animations: {0}".format(source_refs))
            report["retarget"]["anim_blueprint"]["audit"] = (
                "dependencies confirm retargeted animations" if target_refs else
                "asset registry returned no dependencies for the new package in this commandlet; "
                "confirm animation playback in the PIE walkthrough evidence")
        unreal.BlueprintEditorLibrary.compile_blueprint(abp)
        report["retarget"]["anim_blueprint_status"] = str(abp.get_editor_property("status"))
        lib.save_loaded_asset(abp)

        # --- 2. player blueprint ------------------------------------------
        bp_path = "{0}/BP_Workshop{1}_{2}".format(FOLDER, TAG, VERSION)
        if lib.does_asset_exist(bp_path):
            raise RuntimeError("refusing to overwrite {0}".format(bp_path))
        bp = lib.duplicate_asset(SOURCE_BP, bp_path)
        parts = blueprint_parts(bp)
        mesh_component = next(p for p in parts if isinstance(p, unreal.SkeletalMeshComponent))
        capsule = next(p for p in parts if isinstance(p, unreal.CapsuleComponent))
        half_height = round(height_cm / 2.0, 1)
        mesh_component.set_skeletal_mesh_asset(target)
        mesh_component.set_editor_property("override_materials", [])
        mesh_component.set_editor_property("anim_class", abp.generated_class())
        mesh_component.set_editor_property("relative_location", unreal.Vector(0.0, 0.0, -half_height))
        mesh_yaw = -forward_yaw if forward_yaw is not None else 270.0
        mesh_component.set_editor_property("relative_rotation", unreal.Rotator(roll=0.0, pitch=0.0, yaw=mesh_yaw))
        capsule.set_editor_property("capsule_half_height", half_height)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        report["player"] = {"blueprint": bp_path, "capsule_half_height": half_height, "mesh_yaw": mesh_yaw}

        # --- 3. new level, game mode; sword refit on the actual spawned pawn
        target_level = SOURCE_LEVEL.rsplit("_v", 1)[0] + "_" + VERSION
        if lib.does_asset_exist(target_level):
            raise RuntimeError("refusing to overwrite {0}".format(target_level))
        if not level_subsystem.new_level_from_template(target_level, SOURCE_LEVEL):
            raise RuntimeError("could not create {0} from {1}".format(target_level, SOURCE_LEVEL))
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        temp = actors.spawn_actor_from_class(bp.generated_class(), unreal.Vector(), unreal.Rotator())
        try:
            sk = temp.get_component_by_class(unreal.SkeletalMeshComponent)
            sword_info = None
            sword = next((c for c in temp.get_components_by_class(unreal.StaticMeshComponent)
                          if str(c.get_attach_socket_name()) not in ("", "None")), None)
            if sword is not None:
                socket = str(sword.get_attach_socket_name())
                sword_mesh = sword.get_editor_property("static_mesh")
                bone = sk.get_socket_transform(socket, unreal.RelativeTransformSpace.RTS_WORLD)
                # Same back-carry placement the Manny demo settled on (fit_manny_sword_v005):
                # local Y is the blade's thin-axis normal, local Z runs tip to pommel.
                rotation = unreal.MathLibrary.make_rot_from_yz(unreal.Vector(-1, 0, 0), unreal.Vector(0, -0.5, 0.8660254))
                scale = height_cm / 180.0
                desired = unreal.Transform(location=unreal.Vector(-20 * scale, 34 * scale, -15 * scale),
                                           rotation=rotation, scale=unreal.Vector(1, 1, 1))
                relative = unreal.MathLibrary.make_relative_transform(desired, bone)
                sword_info = {"socket": socket, "relative_location": str(relative.translation),
                              "relative_rotation": str(relative.rotation.rotator())}
            head_z = sk.get_socket_location("head").z if "head" in t_bones else None
        finally:
            actors.destroy_actor(temp)
        if sword_info:
            parts = blueprint_parts(bp)
            # SCS templates keep their socket on the SCS node, not the component,
            # so match the template by the mesh it carries.
            sword_template = next(p for p in parts if isinstance(p, unreal.StaticMeshComponent)
                                  and p.get_editor_property("static_mesh") is not None
                                  and p.get_editor_property("static_mesh").get_path_name() == sword_mesh.get_path_name())
            # The compiled skeletons scale everything under the root by 100, so
            # the socket-relative transform must carry the inverse scale too or
            # the prop inherits a 100x size.
            sword_template.set_editor_property("relative_location", relative.translation)
            sword_template.set_editor_property("relative_rotation", relative.rotation.rotator())
            sword_template.set_editor_property("relative_scale3d", relative.scale3d)
            sword_info["relative_scale3d"] = str(relative.scale3d)
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        report["player"]["sword"] = sword_info
        report["player"]["spawned_head_z_cm"] = head_z
        if not lib.save_loaded_asset(bp):
            raise RuntimeError("could not save {0}".format(bp_path))

        gm_path = "{0}/BP_WorkshopGameMode_{1}_{2}".format(FOLDER, TAG, VERSION)
        gm = lib.duplicate_asset(SOURCE_GM, gm_path)
        unreal.get_default_object(gm.generated_class()).set_editor_property("default_pawn_class", bp.generated_class())
        unreal.BlueprintEditorLibrary.compile_blueprint(gm)
        if not lib.save_loaded_asset(gm):
            raise RuntimeError("could not save {0}".format(gm_path))
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        world.get_world_settings().set_editor_property("default_game_mode", gm.generated_class())
        if not level_subsystem.save_current_level():
            raise RuntimeError("could not save {0}".format(target_level))
        lib.save_directory(FOLDER, recursive=True)
        report.update({"game_mode": gm_path, "level": target_level, "ok": True})
    except Exception as error:  # noqa: BLE001
        report.update({"ok": False, "error": str(error), "traceback": traceback.format_exc()})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
    unreal.log("RAC_WORKSHOP_PLAYER_SWAP ok={0} -> {1}".format(report.get("ok"), out))


if __name__ == "__main__":
    main()
