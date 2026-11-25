"""Import props as glTF into Unreal and photograph each one close, from editor sessions.

  set RAC_PROP_GLBS=label=C:/path/a.glb;label2=C:/path/b.glb
  set RAC_PROP_OUT=C:/path/to/evidence
  UnrealEditor.exe <project> -ExecutePythonScript="<this file>" -nosplash -nop4
  set RAC_PROP_PHASE=shots
  UnrealEditor.exe <project> -ExecCmds="py <this file>" -nosplash -nop4

What Framewright shows should be what Unreal shows, because that is where most
imports arrive. The first launch imports each file the way an artist would,
through Unreal's own glTF importer (Interchange), with nothing converted on the
way, and stands each prop in the engine's default lit level (sun, sky,
atmosphere). Imports land under `/Game/PropReview/<label>`, replacing an earlier
import of the same label.

The second launch photographs them: from above, as the owner looked at the
WK-04.1 stair's treads; a three-quarter view; and close on the middle. Two
launches, because a project that runs `-ExecutePythonScript` quits the editor
as soon as the script returns, before a single frame is drawn. `-ExecCmds`
leaves it running. `take_high_res_screenshot` writes its file frames later, so
the cameras are stepped through on the editor's tick, a screenshot per camera,
and the editor quits itself when the last file is on disk.
"""

from __future__ import annotations

import json
import os
import time

import unreal

GLBS = [item.split("=", 1) for item in os.environ.get("RAC_PROP_GLBS", "").split(";") if "=" in item]
OUT = os.environ.get("RAC_PROP_OUT", os.path.join(os.environ.get("RAC_ROOT", "."), "work", "ue5-evidence", "props"))
LEVEL = "/Game/PropReview/L_PropReview"
TEMPLATE = "/Engine/Maps/Templates/Template_Default"
SPACING = 600.0  # cm between props, so no prop shades another
LEAD = 8.0  # seconds for the level to stream in and shaders to settle
STEP = 5.0  # seconds a shot
VIEWS = {
    # (camera offset as a share of the prop's size, pitch, yaw)
    "above": ((-0.15, 0.0, 0.55), -72.0, 0.0),
    "three-quarter": ((-0.55, -0.55, 0.45), -28.0, 45.0),
    "close": ((-0.2, 0.0, 0.3), -55.0, 0.0),
}


def log(message):
    unreal.log("RAC_PROP_REVIEW " + message)


def import_glb(label, path):
    destination = "/Game/PropReview/" + label
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = destination
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    meshes = [unreal.load_asset(name) for name in unreal.EditorAssetLibrary.list_assets(destination, recursive=True)]
    meshes = [asset for asset in meshes if isinstance(asset, unreal.StaticMesh)]
    if not meshes:
        raise RuntimeError("Unreal imported no static mesh from " + path)
    return meshes[0]


def build():
    if not GLBS:
        raise RuntimeError("Set RAC_PROP_GLBS to label=path pairs")
    os.makedirs(OUT, exist_ok=True)
    meshes = [(label, import_glb(label, path)) for label, path in GLBS]
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL):
        unreal.EditorAssetLibrary.delete_asset(LEVEL)
    if not levels.new_level_from_template(LEVEL, TEMPLATE):
        raise RuntimeError("Could not make the review level from " + TEMPLATE)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in actors.get_all_level_actors():
        # The template's floor would hide the underside and shade a low prop.
        if isinstance(actor, unreal.StaticMeshActor):
            actors.destroy_actor(actor)
    record = []
    for index, (label, mesh) in enumerate(meshes):
        placed = actors.spawn_actor_from_object(mesh, unreal.Vector(index * SPACING, 0.0, 0.0), unreal.Rotator())
        placed.set_actor_label("RAC_Prop_" + label)
        _, extent = placed.get_actor_bounds(False)
        materials = [entry.material_interface.get_path_name() for entry in mesh.static_materials
                     if entry.material_interface]
        record.append({"label": label, "mesh": mesh.get_path_name(), "materials": materials,
                       "bounds_cm": [round(extent.x * 2, 1), round(extent.y * 2, 1), round(extent.z * 2, 1)]})
    levels.save_current_level()
    with open(os.path.join(OUT, "ue5-prop-review.json"), "w", encoding="utf-8") as stream:
        json.dump({"engine": unreal.SystemLibrary.get_engine_version(), "props": record}, stream, indent=2)
    log("built {0} with {1} props".format(LEVEL, len(record)))


def photograph():
    os.makedirs(OUT, exist_ok=True)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    levels.load_level(LEVEL)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    shots = []
    for actor in actors.get_all_level_actors():
        name = actor.get_actor_label()
        if not name.startswith("RAC_Prop_"):
            continue
        label = name[len("RAC_Prop_"):]
        centre, extent = actor.get_actor_bounds(False)
        size = max(extent.x, extent.y, extent.z) * 2.0
        for view, (offset, pitch, yaw) in VIEWS.items():
            location = centre + unreal.Vector(*offset) * size
            shots.append((label, view, location, unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)))
    if not shots:
        raise RuntimeError("No RAC_Prop_ actors in " + LEVEL + "; run the build phase first")
    try:
        levels.editor_set_game_view(True)
    except Exception:  # noqa: BLE001 - decoration only
        pass
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    # Paced by the wall clock, as the game review's close-ups are: each shot
    # gets STEP seconds, the camera is set at the start of its step, and the
    # screenshot is asked for near its end, once the view has settled and
    # streamed in. A tick count is no clock: the editor can tick many times in
    # one frame while a screenshot is being drawn.
    state = {"started": time.monotonic(), "shot": -1, "placed": -1}

    def tick(_delta):
        t = time.monotonic() - state["started"] - LEAD
        if t < 0:
            return
        index = int(t // STEP)
        if index >= len(shots):
            if t >= len(shots) * STEP + STEP:
                log("done {0} shots".format(len(shots)))
                unreal.unregister_slate_post_tick_callback(handle)
                unreal.SystemLibrary.quit_editor()
            return
        label, view, location, rotation = shots[index]
        if state["placed"] != index:
            state["placed"] = index
            editor.set_level_viewport_camera_info(location, rotation)
        if t - index * STEP >= STEP - 1.0 and state["shot"] != index:
            state["shot"] = index
            target = os.path.join(OUT, "ue5-{0}-{1}.png".format(label, view)).replace("\\", "/")
            unreal.SystemLibrary.execute_console_command(world, "HighResShot 1 filename=" + target)
            log("requested " + target)

    handle = unreal.register_slate_post_tick_callback(tick)


if os.environ.get("RAC_PROP_PHASE") == "shots":
    photograph()
else:
    build()
