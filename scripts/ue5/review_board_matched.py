"""Unobstructed original/reduced board comparison at identical transforms, forced LOD0."""
import hashlib
import json
import os
from pathlib import Path
import time

import unreal


root = Path(os.environ["RAC_ROOT"])
version = os.environ.get("RAC_BOARD_VERSION", "v001")
if version not in {"v001", "v002"}:
    raise ValueError("Unknown retained board revision")
out = root / ("work/sunset-workshop/evidence/board-matched-review-" + version)
target = "/Game/SunsetWorkshop/L_BoardMatchedReview_" + version
if out.exists() or unreal.EditorAssetLibrary.does_asset_exist(target):
    raise RuntimeError("Preserve previous matched review")
out.mkdir(parents=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.new_level_from_template(target, "/Game/SunsetWorkshop/L_WorkshopPreview_v003"):
    raise RuntimeError("Could not create an isolated review level")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
removed = []
for actor in actors.get_all_level_actors():
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    if component and component.static_mesh:
        path = component.static_mesh.get_path_name()
        if any(token in path for token in ("SunsetWrenchProduction/", "SunsetMugProduction/")):
            removed.append({"label": actor.get_actor_label(), "mesh": path})
            actors.destroy_actor(actor)
paths = {
    "original": "/Game/Compiled/SunsetCircuitBoardProduction/sunset-circuit-board-production",
    "reduced": "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_" + version,
}
meshes = {key: unreal.load_asset(path) for key, path in paths.items()}
if any(mesh is None for mesh in meshes.values()):
    raise RuntimeError("A comparison mesh is missing")
board = actors.spawn_actor_from_object(meshes["original"], unreal.Vector(74, -225, 92.3), unreal.Rotator())
board.set_actor_label("RAC_BoardMatchedFixture")
component = board.static_mesh_component
component.set_collision_profile_name("NoCollision")
component.set_editor_property("forced_lod_model", 1)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.editor_set_game_view(True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
views = [("high", (74, -278, 153), (-48, 90)),
         ("grazing", (74, -300, 114), (-15, 90))]
steps = [(name + "-" + kind, kind, xyz, rot) for name, xyz, rot in views
         for kind in ("original", "reduced")]
state = {"index": 0, "phase": "startup", "time": time.monotonic(), "frames": []}


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    level.save_current_level()
    record = {"schema": "reference-asset-compiler.ue-native-matched-review.v1",
              "engine_version": unreal.SystemLibrary.get_engine_version(),
              "level": target, "source_level_preserved": True,
              "fixture_only_removed_actors": removed,
              "assets": {key: {"path": paths[key], "lod0_vertices":
                         unreal.EditorStaticMeshLibrary.get_number_verts(mesh, 0)}
                         for key, mesh in meshes.items()},
              "forced_lod_model": component.get_editor_property("forced_lod_model"),
              "frames": state["frames"], "error": error, "production_ready": False}
    (out / "review.json").write_text(json.dumps(record, indent=2) + "\n")
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        now = time.monotonic()
        name, kind, xyz, rotation = steps[state["index"]]
        frame = out / (name + ".png")
        if state["phase"] == "startup" and now - state["time"] > 5:
            component.set_static_mesh(meshes[kind])
            editor.set_level_viewport_camera_info(unreal.Vector(*xyz),
                unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=0))
            state.update(phase="warm", time=now)
        elif state["phase"] == "warm" and now - state["time"] > 12:
            unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, str(frame))
            state.update(phase="capture", time=now)
        elif state["phase"] == "capture" and frame.is_file() and now - state["time"] > 4:
            state["frames"].append({"path": str(frame), "sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                                   "mesh": paths[kind], "camera_position": xyz, "camera_pitch_yaw": rotation,
                                   "actor_position": [74, -225, 92.3], "forced_lod_model": 1})
            state["index"] += 1
            if state["index"] == len(steps):
                finish()
            else:
                state.update(phase="startup", time=now - 6)
        elif now - state["time"] > 90:
            finish("Timed out capturing matched board")
    except Exception as error:
        finish(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
