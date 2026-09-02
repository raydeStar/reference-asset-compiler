"""Build a review level with every compiled character placed on it.

A level is what makes a cook meaningful: cooking loose assets proves they
serialise, but cooking a map proves the references resolve, the materials
compile for the target platform, and the skeletal meshes carry their
skeletons. It is also what a fixed-camera screenshot needs to exist.

Characters are spaced along X so a single camera sees the line-up, each with
its feet on Z=0 -- which is the origin convention the compiler normalises to,
so anything floating or sunk here is a real defect rather than a placement
mistake.

It is built to be reviewed BY HAND, not only screenshotted: a floor to cast
shadows onto, a name over every character because a row of near-identical
pairs is unreadable otherwise, and a PlayerStart so you can walk the line.
Authorities are labelled in blue and production derivatives in white.

Open `/Game/Compiled/L_RacGallery` and press Play. Turn texture streaming off
before judging anything -- `r.Streaming.FullyLoadUsedTextures 1` in the
console, or launch with -NoTextureStreaming -- because the 4096 maps arrive
several frames late and a character caught mid-stream looks blocky and washed
out in a way the asset is not.

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
SPACING_CM = 160.0
# Props stand in their own row 3 m in front of the characters, close enough
# to compare against them for scale and far enough not to be read as part of
# the line.
# +Y, not -Y. The characters face +Y and every review camera stands on that
# side looking back along -Y, so the prop row has to be between the camera and
# the line-up. Put it at -300 and the chairs are behind the characters, out of
# every existing shot, facing away.
PROP_ROW_Y_CM = 300.0
PROP_SPACING_CM = 110.0


def find_meshes():
    """Every compiled character, in a stable order."""
    found = []
    for path in unreal.EditorAssetLibrary.list_assets("/Game/Compiled", recursive=True):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.SkeletalMesh):
            found.append((path, asset))
    found.sort(key=lambda pair: pair[0])
    return found


def find_props():
    """Every compiled static prop.

    Kept separate from the characters rather than sorted in with them. A prop
    is a metre tall and a character is two, and interleaving them in one row
    makes the row read as a scale error. They get their own row in front.
    """
    found = []
    for path in unreal.EditorAssetLibrary.list_assets("/Game/Compiled", recursive=True):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.StaticMesh):
            found.append((path, asset))
    found.sort(key=lambda pair: pair[0])
    return found


def main():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    meshes = find_meshes()
    unreal.log("RAC gallery: {0} skeletal meshes".format(len(meshes)))

    # new_level does NOT guarantee an empty level when one already exists at
    # that path -- it leaves the current level loaded and everything spawned
    # after it is ADDED. Nineteen rebuilds later the map held nineteen copies
    # of every character stacked in the same spot, nineteen directional
    # lights, six floors, and two leftover post-process volumes from an
    # abandoned exposure experiment that were quietly darkening the whole
    # scene. Stacked copies z-fight, which reads as a character having a
    # second model inside him.
    #
    # So clear it explicitly and check that the clear worked.
    level_subsystem.new_level(LEVEL_PATH)
    existing = actor_subsystem.get_all_level_actors()
    if existing:
        actor_subsystem.destroy_actors(existing)
    remaining = actor_subsystem.get_all_level_actors()
    if remaining:
        unreal.log_error("RAC could not clear {0}: {1} actors remain".format(
            LEVEL_PATH, len(remaining)))
        return

    # A floor, so the characters stand on something and cast shadows onto it
    # rather than floating over a void.
    floor_mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
    if floor_mesh is not None:
        floor = actor_subsystem.spawn_actor_from_object(
            floor_mesh, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator())
        if floor is not None:
            floor.set_actor_label("Floor")
            floor.set_actor_scale3d(unreal.Vector(60.0, 60.0, 1.0))
            # The floor keeps the plane's default material. The engine grid
            # materials were tried instead, to take the glare off and give a
            # sense of scale, and they are unlit -- which drags auto-exposure
            # down and leaves the characters in near-darkness.

    placed = []
    start = -SPACING_CM * (len(meshes) - 1) / 2.0
    for index, (path, mesh) in enumerate(meshes):
        location = unreal.Vector(start + index * SPACING_CM, 0.0, 0.0)
        actor = actor_subsystem.spawn_actor_from_object(
            mesh, location, unreal.Rotator())
        if actor is None:
            unreal.log_error("RAC could not place {0}".format(path))
            continue
        name = os.path.basename(path).split(".")[0]
        actor.set_actor_label(name)
        placed.append({"asset": path, "x_cm": location.x})
        unreal.log("RAC placed {0} at X={1:.0f}".format(path, location.x))

        # Label each one, because a line-up of near-identical pairs is
        # unreviewable if you cannot tell which is the authority.
        label = actor_subsystem.spawn_actor_from_class(
            unreal.TextRenderActor,
            unreal.Vector(location.x, 0.0, 215.0),
            unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0))
        if label is None:
            continue
        component = label.text_render
        component.set_text(unreal.Text(name.replace("-production", "\nPRODUCTION")
                                       if name.endswith("-production")
                                       else name + "\nauthority"))
        component.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
        component.set_world_size(16.0)
        component.set_text_render_color(
            unreal.Color(r=255, g=255, b=255, a=255)
            if name.endswith("-production")
            else unreal.Color(r=150, g=180, b=255, a=255))
        label.set_actor_label("Label_" + name)

    # No PostProcessVolume. Locking exposure was tried, to make side-by-side
    # judgements comparable, and both settings that Python exposes are wrong
    # here: AEM_MANUAL with a bias reads the bias as EV compensation and blew
    # the frame out at +10, and pinning min/max brightness to 1.0 crushed the
    # whole scene to near-black. The default adaptation looks correct, so it
    # is left alone rather than half-tuned.

    # Props go in their own row, closer to the camera, and one of each is
    # turned to face the line-up: a chair seen only from the front tells you
    # nothing about its back, and the whole point of standing them here is
    # that someone walks around them.
    props = find_props()
    if props:
        prop_start = -PROP_SPACING_CM * (len(props) * 2 - 1) / 2.0
        for index, (path, mesh) in enumerate(props):
            name = os.path.basename(path).split(".")[0]
            for repeat, yaw in ((0, 0.0), (1, 180.0)):
                location = unreal.Vector(
                    prop_start + (index * 2 + repeat) * PROP_SPACING_CM,
                    PROP_ROW_Y_CM, 0.0)
                actor = actor_subsystem.spawn_actor_from_object(
                    mesh, location, unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
                if actor is None:
                    unreal.log_error("RAC could not place {0}".format(path))
                    continue
                actor.set_actor_label("{0}{1}".format(
                    name, "" if repeat == 0 else "_turned"))
                placed.append({"asset": path, "x_cm": location.x,
                               "y_cm": location.y, "yaw": yaw})
                unreal.log("RAC placed prop {0} at X={1:.0f} yaw={2:.0f}".format(
                    path, location.x, yaw))
            label = actor_subsystem.spawn_actor_from_class(
                unreal.TextRenderActor,
                unreal.Vector(prop_start + (index * 2 + 0.5) * PROP_SPACING_CM,
                              PROP_ROW_Y_CM, 130.0),
                unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0))
            if label is not None:
                component = label.text_render
                component.set_text(unreal.Text(
                    name.replace("-production", "\nPRODUCTION")
                    if name.endswith("-production") else name + "\nauthority"))
                component.set_horizontal_alignment(
                    unreal.HorizTextAligment.EHTA_CENTER)
                component.set_world_size(7.0)
                component.set_text_render_color(
                    unreal.Color(r=255, g=255, b=255, a=255)
                    if name.endswith("-production")
                    else unreal.Color(r=150, g=180, b=255, a=255))
                label.set_actor_label("Label_" + name)

    # Somewhere to stand when you press Play and walk the line.
    actor_subsystem.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(0.0, 620.0, 90.0),
        unreal.Rotator(roll=0.0, pitch=0.0, yaw=-90.0))

    # Light it well enough to judge an asset by.
    #
    # A DirectionalLight and a SkyLight alone leave the level nearly black: a
    # SkyLight captures the sky, and with no atmosphere there is no sky to
    # capture, so it contributes nothing and the characters are lit from one
    # side against a void. A SkyAtmosphere gives it something to capture.
    #
    # unreal.Rotator is (roll, pitch, yaw). A pitch/yaw/roll triple passed
    # positionally aims the sun somewhere other than intended.
    sun = actor_subsystem.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(0, 0, 500),
        unreal.Rotator(roll=0.0, pitch=-38.0, yaw=-55.0))
    try:
        sun.directional_light_component.set_intensity(6.0)
    except Exception:  # noqa: BLE001 - default intensity is workable
        pass
    actor_subsystem.spawn_actor_from_class(
        unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator())
    sky = actor_subsystem.spawn_actor_from_class(
        unreal.SkyLight, unreal.Vector(0, 0, 500), unreal.Rotator())
    try:
        component = sky.sky_light_component
        component.set_editor_property("real_time_capture", True)
        component.set_intensity(1.0)
    except Exception:  # noqa: BLE001 - captured lighting is a nicety
        pass

    level_subsystem.save_current_level()
    unreal.log("RAC_GALLERY_SAVED {0} with {1} characters".format(
        LEVEL_PATH, len(placed)))

    if ROOT:
        report = {"level": LEVEL_PATH, "placed": placed}
        out = os.path.join(ROOT, "work", "ue5-gallery.json")
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)


main()
