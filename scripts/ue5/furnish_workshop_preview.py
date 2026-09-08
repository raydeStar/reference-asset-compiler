"""Duplicate the retained shell and furnish it with approved imported props only.

This is an early walkthrough, not a release receipt. Held sofa, plant and board
are deliberately absent. Source maps, imported meshes and the gallery stay put.
"""
import hashlib
import json
import os
from pathlib import Path

import unreal


def main():
    root = Path(os.environ["RAC_ROOT"])
    source = "/Game/SunsetWorkshop/L_WorkshopShell_v004"
    target = "/Game/SunsetWorkshop/L_WorkshopPreview_v003"
    evidence = root / "work/sunset-workshop/evidence/L_WorkshopPreview_v003.json"
    lib = unreal.EditorAssetLibrary
    if lib.does_asset_exist(target) or evidence.exists():
        raise RuntimeError("The preview already exists; choose a fresh revision")
    meshes = {}
    for name in ("workbench", "mug", "radio", "wrench", "crate", "stool"):
        asset = "sunset-" + name
        state = json.loads((root / "work" / asset / "state.json").read_text())
        for gate in ("texture_approval", "ue5_import"):
            if state["stages"][gate]["status"] != "passed":
                raise RuntimeError(asset + " lacks " + gate)
        folder = "".join(p.capitalize() for p in asset.split("-")) + "Production"
        path = "/Game/Compiled/" + folder + "/" + asset + "-production"
        mesh = lib.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("Missing approved mesh " + path)
        verts = unreal.EditorStaticMeshLibrary.get_number_verts(mesh, 0)
        if not 0 < verts <= 15000:
            raise RuntimeError(asset + " exceeds the runtime vertex budget: " + str(verts))
        meshes[name] = mesh
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    # Generic asset duplication leaves a standalone World alive during load
    # on UE 5.8. Use the operation that owns the entire world transition.
    if not level.new_level_from_template(target, source):
        raise RuntimeError("Could not create preview from retained shell")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    placed = []

    def prop(name, label, xyz, yaw=0, collision=True):
        actor = actors.spawn_actor_from_object(meshes[name], unreal.Vector(*xyz),
                                               unreal.Rotator(pitch=0, yaw=yaw, roll=0))
        actor.set_actor_label(label)
        actor.static_mesh_component.set_collision_profile_name("BlockAll" if collision else "NoCollision")
        actor.set_folder_path("Workshop/IndependentProps")
        placed.append({"label": label, "source": "sunset-" + name,
                       "mesh": meshes[name].get_path_name(), "position_cm": xyz,
                       "yaw": yaw, "collision": collision})
        return actor

    # Imported fronts face -Y; rotate each whole prop into the room.
    prop("workbench", "Bench_Chalkboard", (-375, -70, 0), 90)
    prop("workbench", "Bench_Window", (370, -40, 0), -90)
    prop("workbench", "Bench_Foreground", (80, -225, 0), 180)
    prop("radio", "Radio_Chalkboard", (-383, -110, 92.3), -90, False)
    prop("radio", "Radio_Window", (378, -82, 92.3), 90, False)
    prop("mug", "Mug_Chalkboard", (-350, -25, 92.3), 35, False)
    prop("mug", "Mug_Foreground", (8, -216, 92.3), -25, False)
    prop("mug", "Mug_Window", (348, 27, 92.3), -110, False)
    prop("wrench", "Wrench_Foreground_A", (80, -212, 92.3), 22, False)
    prop("wrench", "Wrench_Foreground_B", (118, -242, 92.3), -30, False)
    prop("wrench", "Wrench_Window", (370, -12, 92.3), 75, False)
    prop("stool", "Stool_Chalkboard", (-252, -64, 0), 12)
    prop("stool", "Stool_Window", (245, -42, 0), -8)
    prop("stool", "Stool_Foreground", (66, -103, 0), 35)
    prop("crate", "Crate_Storage_West", (-368, 196, 0), 90)
    prop("crate", "Crate_Storage_East", (353, 213, 0), -20)
    prop("crate", "Crate_SideTable", (166, 203, 0), -12)
    prop("mug", "Mug_SideTable", (163, 202, 55.3), -15, False)
    # New light actors are scene lighting, never substitutions for AI props.
    for label, xyz, yaw in (("TaskLight_Chalkboard", (-415, -70, 255), 0),
                             ("TaskLight_Window", (415, -40, 257), 180),
                             ("TaskLight_Foreground", (80, -313, 253), 90)):
        lamp = actors.spawn_actor_from_class(unreal.RectLight, unreal.Vector(*xyz),
                                            unreal.Rotator(pitch=-30, yaw=yaw, roll=0))
        lamp.set_actor_label(label)
        component = lamp.get_component_by_class(unreal.RectLightComponent)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        component.set_intensity(120)
        component.set_light_color(unreal.LinearColor(1, .70, .38, 1))
        component.set_editor_property("source_width", 80)
        component.set_editor_property("source_height", 15)
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label() == "DesertVista_BackdropNotWalkable":
            actor.set_actor_location(unreal.Vector(700, 0, 530), False, False)
            actor.set_actor_scale3d(unreal.Vector(60, 30, 1))
        if isinstance(actor, unreal.PlayerStart):
            actor.set_actor_location(unreal.Vector(-100, 140, 110), False, False)
            actor.set_actor_rotation(unreal.Rotator(pitch=0, yaw=-30, roll=0), False)
        if isinstance(actor, unreal.SkyLight):
            actor.get_component_by_class(unreal.SkyLightComponent).set_intensity(.38)
    post = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(), unreal.Rotator())
    post.set_actor_label("Workshop_Exposure")
    post.set_editor_property("unbound", True)
    settings = post.get_editor_property("settings")
    settings.set_editor_property("override_auto_exposure_bias", True)
    settings.set_editor_property("auto_exposure_bias", -1.25)
    post.set_editor_property("settings", settings)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    game_mode = lib.load_blueprint_class("/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode")
    if game_mode is None:
        raise RuntimeError("Third Person game mode is unavailable")
    world.get_world_settings().set_editor_property("default_game_mode", game_mode)
    if not level.save_current_level():
        raise RuntimeError("Preview map did not save")
    hashes = {}
    for name in meshes:
        asset = "sunset-" + name + "-production"
        path = root / "out" / asset / (asset + ".ue5import.json")
        hashes[asset] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence.write_text(json.dumps({"schema": "rac.workshop-preview.v1", "level": target,
                                    "source_level": source, "placed": placed, "manifest_hashes": hashes,
                                    "excluded": ["sofa: baked lighting", "board: vertex budget", "plant: rejected geometry"],
                                    "runtime_verified": False, "production_ready": False}, indent=2) + "\n", encoding="utf-8")
    unreal.log("WORKSHOP_PREVIEW_SAVED -- individual props, and room to stretch one's legs.")


main()
