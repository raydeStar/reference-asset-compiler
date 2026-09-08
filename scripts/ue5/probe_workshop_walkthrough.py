"""Dedicated-editor PIE probe: real spawned pawn, movement and wall collision.

Calls gameplay movement input, not keyboard automation. No cooked-runtime or
human visual approval is implied. The dedicated editor exits when complete.
"""
import json
import os
import time
from pathlib import Path

import unreal

root = Path(os.environ["RAC_ROOT"])
out = root / "work/sunset-workshop/evidence" / os.environ.get("RAC_WALK_REVIEW", "walkthrough-v001")
if out.exists():
    raise RuntimeError("Retained walkthrough evidence must not be overwritten")
out.mkdir(parents=True)
level_path = os.environ.get("RAC_WORKSHOP_LEVEL", "/Game/SunsetWorkshop/L_WorkshopPreview_v003")
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not level.load_level(level_path):
    raise RuntimeError("Workshop preview is unavailable")
level.editor_set_game_view(True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
state = {"phase": "camera", "since": time.monotonic(), "samples": [], "frames": []}


def point(value):
    return [round(value.x, 3), round(value.y, 3), round(value.z, 3)]


def advance(phase):
    state.update(phase=phase, since=time.monotonic())


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    if level.is_in_play_in_editor():
        level.editor_request_end_play()
    report = {"level": level_path, "error": error, "samples": state["samples"],
              "frames": state["frames"], "pawn_class": state.get("pawn_class"),
              "checks": state.get("checks", {}), "movement_input": "Character.add_movement_input",
              "physical_keyboard_tested": False, "cooked_runtime_verified": False,
              "ok": error is None and all(state.get("checks", {}).values())}
    (out / "walkthrough.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("WORKSHOP_WALKTHROUGH_FINISHED " + str(report["ok"]) + " -- boots, not teleportation.")
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        elapsed = time.monotonic() - state["since"]
        phase = state["phase"]
        if phase == "camera" and elapsed > 3:
            editor.set_level_viewport_camera_info(unreal.Vector(-260, 210, 175),
                                                  unreal.Rotator(pitch=-6, yaw=-25, roll=0))
            advance("overview")
        elif phase == "overview" and elapsed > 20:
            unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, str(out / "overview.png"))
            advance("overview_capture")
        elif phase == "overview_capture" and elapsed > 5:
            if not (out / "overview.png").is_file():
                raise RuntimeError("Overview screenshot was not written")
            state["frames"].append("overview.png")
            level.editor_request_begin_play()
            advance("spawn")
        elif phase in ("spawn", "walk", "wall", "capture"):
            world = editor.get_game_world()
            pawn = unreal.GameplayStatics.get_player_character(world, 0) if world else None
            if pawn is None:
                if elapsed > 30:
                    raise RuntimeError("No possessed player character spawned")
                return
            if phase == "spawn" and elapsed > 5:
                location = pawn.get_actor_location()
                state["start"] = point(location)
                state["pawn_class"] = pawn.get_class().get_path_name()
                state["samples"].append({"phase": "spawn", "position": point(location)})
                state["checks"] = {"possessed": pawn.get_controller() is not None,
                                   "spawn_on_floor": 60 < location.z < 130}
                advance("walk")
            elif phase == "walk":
                pawn.add_movement_input(unreal.Vector(1, 0, 0), 1.0, False)
                if elapsed > 4:
                    location = pawn.get_actor_location()
                    state["samples"].append({"phase": "walk_to_window", "position": point(location)})
                    state["checks"]["walked_forward"] = location.x - state["start"][0] > 100
                    state["checks"]["inside_east_wall"] = location.x < 432
                    state["wall_start"] = point(location)
                    advance("wall")
            elif phase == "wall":
                pawn.add_movement_input(unreal.Vector(1, 0, 0), 1.0, False)
                if elapsed > 2:
                    location = pawn.get_actor_location()
                    state["samples"].append({"phase": "continued_against_wall", "position": point(location)})
                    state["checks"]["blocked_by_wall"] = abs(location.x - state["wall_start"][0]) < 5
                    state["checks"]["still_on_floor"] = 60 < location.z < 130
                    unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, str(out / "player-window.png"))
                    advance("capture")
            elif phase == "capture" and elapsed > 5:
                if not (out / "player-window.png").is_file():
                    raise RuntimeError("Player screenshot was not written")
                state["frames"].append("player-window.png")
                finish()
    except Exception as error:
        finish(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
