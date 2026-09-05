"""Read-only probe of the workshop demo's player setup, for a character swap.

Answers, without changing anything: which Blueprint and game mode the demo
level uses, what skeletal mesh and animation blueprint the player carries, how
the mesh and sword components are placed on the capsule, and which animation
assets that animation blueprint pulls in. Writes work/ue5-workshop-player-probe.json.

  UnrealEditor-Cmd.exe <project> -ExecutePythonScript="<this file>" -nullrhi -unattended -nop4 -nosplash -stdout
Env: RAC_ROOT (repo), RAC_PROBE_LEVEL (default /Game/SunsetWorkshop/L_WorkshopNight_v026),
     RAC_PROBE_BP (default /Game/SunsetWorkshop/MannyDemo/BP_WorkshopManny_v007).
"""
import json
import os
import traceback

import unreal

ROOT = os.environ.get("RAC_ROOT")
LEVEL = os.environ.get("RAC_PROBE_LEVEL", "/Game/SunsetWorkshop/L_WorkshopNight_v026")
BP_PATH = os.environ.get("RAC_PROBE_BP", "/Game/SunsetWorkshop/MannyDemo/BP_WorkshopManny_v007")


def describe_component(component):
    info = {"class": component.get_class().get_name(), "name": component.get_name()}
    for prop in ("relative_location", "relative_rotation", "relative_scale3d"):
        try:
            info[prop] = str(component.get_editor_property(prop))
        except Exception:  # noqa: BLE001
            pass
    if isinstance(component, unreal.SkeletalMeshComponent):
        mesh = component.get_skeletal_mesh_asset()
        info["skeletal_mesh"] = mesh.get_path_name() if mesh else None
        anim_class = component.get_editor_property("anim_class")
        info["anim_class"] = anim_class.get_path_name() if anim_class else None
        info["animation_mode"] = str(component.get_editor_property("animation_mode"))
        if mesh:
            skeleton = mesh.get_editor_property("skeleton")
            info["skeleton"] = skeleton.get_path_name() if skeleton else None
    if isinstance(component, unreal.StaticMeshComponent):
        mesh = component.get_editor_property("static_mesh")
        info["static_mesh"] = mesh.get_path_name() if mesh else None
    if isinstance(component, unreal.CapsuleComponent):
        info["capsule_half_height"] = component.get_editor_property("capsule_half_height")
        info["capsule_radius"] = component.get_editor_property("capsule_radius")
    if isinstance(component, unreal.SceneComponent):
        try:
            parent = component.get_editor_property("attach_parent")
            info["attach_parent"] = parent.get_name() if parent else None
            info["attach_socket"] = str(component.get_editor_property("attach_socket_name"))
        except Exception:  # noqa: BLE001
            pass
    return info


def main():
    report = {"level": LEVEL, "blueprint": BP_PATH}
    lib = unreal.EditorAssetLibrary
    try:
        bp = lib.load_asset(BP_PATH)
        sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        fn = unreal.SubobjectDataBlueprintFunctionLibrary
        handles = sub.k2_gather_subobject_data_for_blueprint(bp)
        components = []
        for handle in handles:
            obj = fn.get_object_for_blueprint(fn.get_data(handle), bp)
            if obj is not None:
                components.append(describe_component(obj))
        report["components"] = components
        anim_paths = [c.get("anim_class") for c in components if c.get("anim_class")]
        report["anim_blueprints"] = []
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        for anim_class_path in anim_paths:
            package = anim_class_path.split(".")[0]
            deps = registry.get_dependencies(unreal.Name(package), unreal.AssetRegistryDependencyOptions())
            report["anim_blueprints"].append({
                "class": anim_class_path,
                "dependencies": sorted(str(d) for d in deps) if deps else [],
            })
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_subsystem.load_level(LEVEL):
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            gm = world.get_world_settings().get_editor_property("default_game_mode")
            report["level_game_mode"] = gm.get_path_name() if gm else None
            if gm:
                cdo = unreal.get_default_object(gm)
                pawn = cdo.get_editor_property("default_pawn_class")
                report["level_default_pawn"] = pawn.get_path_name() if pawn else None
        manny = lib.load_asset("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple")
        report["manny_skeleton"] = manny.get_editor_property("skeleton").get_path_name() if manny else None
        anims = lib.list_assets("/Game/Characters/Mannequins/Animations", recursive=True, include_folder=False)
        report["mannequin_animation_assets"] = sorted(anims)
        compiled = lib.list_assets("/Game/Compiled", recursive=True, include_folder=False)
        report["compiled_assets"] = sorted(a for a in compiled if "SunsetAyric" in a)
        report["ok"] = True
    except Exception as error:  # noqa: BLE001
        report.update({"ok": False, "error": str(error), "traceback": traceback.format_exc()})
    out = os.path.join(ROOT, "work", "ue5-workshop-player-probe.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    unreal.log("RAC_WORKSHOP_PLAYER_PROBE ok={0} -> {1}".format(report.get("ok"), out))


if __name__ == "__main__":
    main()
