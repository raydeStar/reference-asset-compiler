"""Take a real viewport screenshot of the gallery, from an editor session.

  UnrealEditor.exe <project> -ExecutePythonScript="<this file>" -nosplash

Set RAC_VIEW to one of the names in VIEWS to choose the camera. The image
lands in `work/ue5-evidence/`.

Why not the SceneCapture2D route in `capture_gallery.py`: `capture_scene()`
queues work for the render thread, and Python reads the render target back in
the same call, before the GPU has drawn anything. Every frame comes out black,
in a commandlet AND in a full editor. Taking more samples does not help --
the problem is timing, not sampling.

`take_high_res_screenshot` sidesteps it by handing the job to the engine and
letting it write the file some frames later. That means this script finishes
long before the image exists, so whoever launches the editor has to leave it
running for a few seconds and collect the file afterwards.
"""

from __future__ import annotations

import os

import unreal

ROOT = os.environ.get("RAC_ROOT")
LEVEL_PATH = "/Game/Compiled/L_RacGallery"

# Eight characters, each authority beside its production derivative, spaced
# 160 cm apart on X -- about 11 m of line-up, so the wide shot stands well back.
# Rotations are (pitch, yaw) in degrees. They are handed to unreal.Rotator by
# KEYWORD, because its positional order is (roll, pitch, yaw) -- passing a
# pitch/yaw/roll triple positionally aims the camera straight up at an empty
# sky, which is a perfectly black screenshot and looks exactly like a broken
# render path.
# The characters face +Y, so the camera stands on the +Y side and looks back
# along -Y (yaw -90) to see their fronts.
VIEWS = {
    "lineup": ((0.0, 980.0, 105.0), (-2.0, -90.0)),
    "lineup-three-quarter": ((760.0, 820.0, 150.0), (-5.0, -132.0)),
    "pair-female": ((-480.0, 330.0, 100.0), (-2.0, -90.0)),
    "pair-male": ((-160.0, 330.0, 100.0), (-2.0, -90.0)),
    "pair-fox": ((160.0, 330.0, 100.0), (-2.0, -90.0)),
    "pair-ninja": ((480.0, 330.0, 100.0), (-2.0, -90.0)),
    # Tight two-shots: authority on the left of frame, derivative on the
    # right, close enough to judge a face rather than a silhouette.
    "close-female": ((-480.0, 175.0, 135.0), (-4.0, -90.0)),
    "close-male": ((-160.0, 175.0, 135.0), (-4.0, -90.0)),
    "close-fox": ((160.0, 165.0, 120.0), (-4.0, -90.0)),
    "close-ninja": ((480.0, 175.0, 135.0), (-4.0, -90.0)),
    # The prop row stands 3 m in front of the line-up at Y=+300, on the same
    # side of it as every other camera here.
    "props": ((0.0, 640.0, 90.0), (-5.0, -90.0)),
    "props-three-quarter": ((330.0, 600.0, 110.0), (-8.0, -128.0)),
    # From between the two rows, looking back at the prop row's far side --
    # which is the half of a chair a front view never shows.
    "props-behind": ((0.0, 130.0, 110.0), (-6.0, 90.0)),
    "lineup-with-props": ((0.0, 1050.0, 270.0), (-9.0, -90.0)),
}

view = os.environ.get("RAC_VIEW", "lineup")
location, (pitch, yaw) = VIEWS.get(view, VIEWS["lineup"])

unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(LEVEL_PATH)

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
editor.set_level_viewport_camera_info(
    unreal.Vector(*location), unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw))

out_dir = os.path.join(ROOT or ".", "work", "ue5-evidence")
if not os.path.isdir(out_dir):
    os.makedirs(out_dir)
target = os.path.join(out_dir, "ue5-{0}.png".format(view))
if os.path.isfile(target):
    os.remove(target)

# Game view hides the editor's grid, icons and selection outlines, so the
# image shows what the engine renders rather than what the editor decorates.
try:
    unreal.EditorLevelLibrary.editor_set_game_view(True)
except Exception:  # noqa: BLE001 - decoration only
    pass

unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, target)
unreal.log("RAC_SCREENSHOT_REQUESTED {0} -> {1}".format(view, target))
