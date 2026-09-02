"""Capture fixed-camera screenshots of the gallery level, headless.

Uses a SceneCapture2D rendering into a render target rather than the editor's
high-res screenshot, because the latter needs a real viewport and there is none
in an unattended commandlet. The output is what the engine actually rasterises
with the imported materials, which is the point: a Blender render proves what
Blender thinks, not what UE5 shipped.

Runs headless:
  UnrealEditor-Cmd.exe <project> -ExecutePythonScript="<this file>" \
      -unattended -nop4 -nosplash -stdout
"""

from __future__ import annotations

import json
import os

import unreal

ROOT = os.environ.get("RAC_ROOT")
LEVEL_PATH = "/Game/Compiled/L_RacGallery"
RESOLUTION = (1600, 900)

# Fixed views of the line-up, in centimetres. The gallery now holds eight
# characters -- each authority beside its production derivative -- spaced
# 160 cm apart, so the line is about 11 m wide and the wide shot has to stand
# back roughly 14 m to hold it at a 45 degree field of view.
VIEWS = {
    "lineup": ((0.0, -1420.0, 110.0), (0.0, 90.0, 0.0)),
    "lineup-three-quarter": ((-900.0, -1150.0, 190.0), (-6.0, 52.0, 0.0)),
    "pair-female": ((-480.0, -430.0, 110.0), (0.0, 90.0, 0.0)),
    "pair-male": ((-160.0, -430.0, 110.0), (0.0, 90.0, 0.0)),
    "pair-fox": ((160.0, -430.0, 110.0), (0.0, 90.0, 0.0)),
    "pair-ninja": ((480.0, -430.0, 110.0), (0.0, 90.0, 0.0)),
}


def main():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem.load_level(LEVEL_PATH)

    out_dir = os.path.join(ROOT, "work", "ue5-evidence") if ROOT else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # RenderingLibrary needs a real world context; None does not resolve
    # inside a commandlet.
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    render_target = unreal.RenderingLibrary.create_render_target2d(
        world, RESOLUTION[0], RESOLUTION[1],
        unreal.TextureRenderTargetFormat.RTF_RGBA8)
    if render_target is None:
        unreal.log_error("RAC could not create a render target")
        return

    capture_actor = actor_subsystem.spawn_actor_from_class(
        unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    component = capture_actor.get_editor_property("capture_component2d")
    component.set_editor_property("texture_target", render_target)
    component.set_editor_property(
        "capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    component.set_editor_property("fov_angle", 45.0)
    component.set_editor_property("capture_every_frame", False)
    component.set_editor_property("capture_on_movement", False)

    written = []
    for name, (location, rotation) in VIEWS.items():
        capture_actor.set_actor_location_and_rotation(
            unreal.Vector(*location), unreal.Rotator(*rotation), False, True)
        component.capture_scene()
        if not out_dir:
            continue

        # Refuse to write a black frame. A commandlet has no render thread, so
        # the capture silently produces one, and a directory full of black PNGs
        # looks like evidence until somebody opens it. Two sample points are
        # not enough -- a mostly-black frame can have a lit pixel under either
        # of them -- so sample a grid and require a real share of it to be lit.
        lit = 0
        samples = 0
        for gy in range(1, 8):
            for gx in range(1, 8):
                pixel = unreal.RenderingLibrary.read_render_target_pixel(
                    world, render_target,
                    RESOLUTION[0] * gx // 8, RESOLUTION[1] * gy // 8)
                samples += 1
                if pixel.r + pixel.g + pixel.b > 6:
                    lit += 1
        if lit < samples * 0.05:
            unreal.log_warning(
                "RAC capture '{0}' is {1}/{2} lit samples -- no live render "
                "thread. Run this from an interactive editor session.".format(
                    name, lit, samples))
            continue

        path = os.path.join(out_dir, "ue5-{0}.png".format(name))
        unreal.RenderingLibrary.export_render_target(
            world, render_target, out_dir, "ue5-{0}.png".format(name))
        written.append(path)
        unreal.log("RAC captured {0}".format(path))

    actor_subsystem.destroy_actor(capture_actor)
    if ROOT:
        with open(os.path.join(ROOT, "work", "ue5-capture.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"level": LEVEL_PATH, "images": written}, handle, indent=2)
    unreal.log("RAC_CAPTURE_DONE {0} images".format(len(written)))


main()
