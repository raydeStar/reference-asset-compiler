"""Capture real UE viewport frames in a dedicated, self-closing editor process.

Never inject this into a user's open editor: it exits the process after capture.
RAC_ROOT is required. Optional RAC_WORKSHOP_LEVEL and RAC_WORKSHOP_REVIEW choose
the saved map and a fresh evidence directory. This is visual evidence, not a
claim that player collision, input, or cooked runtime have been verified.
"""
import json
import os
import time
from pathlib import Path

import unreal

root = Path(os.environ["RAC_ROOT"])
level_path = os.environ.get("RAC_WORKSHOP_LEVEL", "/Game/SunsetWorkshop/L_WorkshopShell_v004")
out = root / "work/sunset-workshop/evidence" / os.environ.get("RAC_WORKSHOP_REVIEW", "shell-review-v001")
if out.exists():
    raise RuntimeError("Review directory already exists; old evidence keeps its seat.")
out.mkdir(parents=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.load_level(level_path):
    raise RuntimeError("Cannot load workshop map")
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
unreal.EditorLevelLibrary.editor_set_game_view(True)
views = [
    ("interior", (-350, 220, 170), (-4, -30)),
    ("window", (30, 90, 160), (3, 0)),
    ("corridor", (0, 110, 165), (-4, 90)),
    ("chalkboard", (150, 30, 180), (4, -170)),
]
state = {"index": 0, "phase": "camera", "since": time.monotonic(), "done": []}


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    (out / "capture.json").write_text(json.dumps({
        "level": level_path, "frames": state["done"], "error": error,
        "runtime_verified": False,
    }, indent=2), encoding="utf-8")
    if error:
        unreal.log_error(error)
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        now = time.monotonic()
        name, location, (pitch, yaw) = views[state["index"]]
        target = out / (name + ".png")
        if state["phase"] == "camera":
            editor.set_level_viewport_camera_info(
                unreal.Vector(*location), unreal.Rotator(pitch=pitch, yaw=yaw, roll=0))
            state.update(phase="warmup", since=now)
        elif state["phase"] == "warmup" and now - state["since"] > 20:
            unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, str(target))
            state.update(phase="capture", since=now)
        elif state["phase"] == "capture":
            if target.is_file() and target.stat().st_size > 1000 and now - state["since"] > 5:
                state["done"].append({"name": name, "file": str(target), "location": location,
                                      "pitch": pitch, "yaw": yaw})
                state["index"] += 1
                if state["index"] == len(views):
                    finish()
                else:
                    state.update(phase="camera", since=now)
            elif now - state["since"] > 90:
                finish("Timed out waiting for actual viewport image " + name)
    except Exception as error:
        finish(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
