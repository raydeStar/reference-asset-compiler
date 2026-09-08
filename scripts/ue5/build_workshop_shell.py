"""Build ONLY the image-mapped architectural study, never substitute prop meshes.

Run via UnrealEditor-Cmd -ExecutePythonScript with RAC_ROOT set. Uses NullRHI
for CPU-only assembly. Every run needs a new RAC_WORKSHOP_LEVEL name: an
existing level is deliberately refused rather than cleared or overwritten.
This is not an asset approval, a finished scene, or runtime verification.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import unreal


def main():
    root = Path(os.environ["RAC_ROOT"])
    art = root / "work/sunset-workshop/art"
    level_path = os.environ.get(
        "RAC_WORKSHOP_LEVEL", "/Game/SunsetWorkshop/L_WorkshopShell_v004")
    if not level_path.startswith("/Game/SunsetWorkshop/"):
        raise RuntimeError("Workshop output must stay in /Game/SunsetWorkshop")
    library = unreal.EditorAssetLibrary
    if library.does_asset_exist(level_path):
        raise RuntimeError("Level already exists; choose a new version, good sir.")
    for name in ("wall", "vista", "floor", "chalkboard"):
        if not (art / (name + ".png")).is_file():
            raise RuntimeError("Missing source-conditioned artwork: " + name)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not level.new_level(level_path):
        raise RuntimeError("Could not create separate workshop map")
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    destination = level_path.rsplit("/", 1)[0] + "/" + level_path.rsplit("/", 1)[1]
    materials = {}
    hashes = {}
    for name in ("wall", "vista", "floor", "chalkboard"):
        path = art / (name + ".png")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        task = unreal.AssetImportTask()
        task.filename = str(path)
        task.destination_path = destination + "/Textures"
        task.automated = True
        task.replace_existing = False
        task.save = True
        tools.import_asset_tasks([task])
        texture = library.load_asset(task.destination_path + "/" + name)
        if not isinstance(texture, unreal.Texture2D):
            raise RuntimeError("Texture import failed: " + name)
        material = tools.create_asset("M_" + name, destination, unreal.Material,
                                      unreal.MaterialFactoryNew())
        material.set_editor_property("two_sided", True)
        edit = unreal.MaterialEditingLibrary
        sample = edit.create_material_expression(
            material, unreal.MaterialExpressionTextureSample, -300, 0)
        sample.set_editor_property("texture", texture)
        if name == "vista":
            material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
            eye = edit.create_material_expression(material, unreal.MaterialExpressionEyeAdaptation, -500, 160)
            inverse = edit.create_material_expression(material, unreal.MaterialExpressionDivide, -100, 0)
            edit.connect_material_expressions(sample, "RGB", inverse, "A")
            edit.connect_material_expressions(eye, "", inverse, "B")
            edit.connect_material_property(inverse, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        else:
            edit.connect_material_property(sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
            roughness = edit.create_material_expression(
                material, unreal.MaterialExpressionConstant, -300, 160)
            roughness.set_editor_property("r", 0.85)
            edit.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
        if name == "wall":
            uv = edit.create_material_expression(material, unreal.MaterialExpressionTextureCoordinate, -900, 0)
            append = edit.create_material_expression(material, unreal.MaterialExpressionAppendVector, -700, 160)
            for label, pin, y in (("TileU", "A", 100), ("TileV", "B", 240)):
                parameter = edit.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -900, y)
                parameter.set_editor_property("parameter_name", label)
                parameter.set_editor_property("default_value", 1.0)
                edit.connect_material_expressions(parameter, "", append, pin)
            scaled = edit.create_material_expression(material, unreal.MaterialExpressionMultiply, -500, 0)
            edit.connect_material_expressions(uv, "", scaled, "A")
            edit.connect_material_expressions(append, "", scaled, "B")
            edit.connect_material_expressions(scaled, "", sample, "UVs")
        edit.recompile_material(material)
        library.save_loaded_asset(material)
        materials[name] = material

    cube = library.load_asset("/Engine/BasicShapes/Cube")
    plane = library.load_asset("/Engine/BasicShapes/Plane")
    placed = []
    wall_instances = {}

    def wall_material(size):
        # Consistent texel density on each module's main face; stretching the
        # same square sheet over a thin pillar makes spaghetti out of steel.
        thin = min(range(3), key=lambda i: size[i])
        face = [size[i] for i in range(3) if i != thin]
        key = tuple(round(v / 200.0, 3) for v in face)
        if key not in wall_instances:
            name = "MI_Wall_" + "_".join(str(v).replace(".", "p") for v in key)
            instance = tools.create_asset(name, destination, unreal.MaterialInstanceConstant,
                                           unreal.MaterialInstanceConstantFactoryNew())
            edit = unreal.MaterialEditingLibrary
            edit.set_material_instance_parent(instance, materials["wall"])
            for parameter, value in zip(("TileU", "TileV"), key):
                edit.set_material_instance_scalar_parameter_value(instance, parameter, value)
            library.save_loaded_asset(instance)
            wall_instances[key] = instance
        return wall_instances[key]

    def piece(name, position, size, material="wall", rotation=None, flat=False):
        actor = actors.spawn_actor_from_object(
            plane if flat else cube, unreal.Vector(*position),
            rotation or unreal.Rotator())
        if actor is None:
            raise RuntimeError("Could not place " + name)
        actor.set_actor_label(name)
        actor.set_actor_scale3d(unreal.Vector(*(v / 100.0 for v in size)))
        actor.static_mesh_component.set_material(0, wall_material(size) if material == "wall" else materials[material])
        actor.static_mesh_component.set_collision_profile_name(
            "NoCollision" if flat else "BlockAll")
        if flat:
            actor.static_mesh_component.set_editor_property("cast_shadow", False)
        placed.append({"name": name, "position_cm": position, "size_cm": size,
                       "material": material, "collision": not flat})
        return actor

    # Room modules carry AI-derived surface mapping. No furniture stand-ins:
    # a cube wearing a sofa's name would be a rather poor valet's trick.
    for x in range(-400, 401, 100):
        for y in range(-300, 301, 100):
            piece("Floor_%s_%s" % (x, y), (x, y, -8), (98, 98, 16), "floor")
    for x in range(-400, 401, 100):
        piece("BackWall_%s" % x, (x, -355, 170), (100, 20, 340))
    for y in range(-300, 301, 100):
        piece("WestWall_%s" % y, (-455, y, 170), (20, 100, 340))
    # Actual openings, not pictures pasted onto a solid wall.
    piece("WindowSillWall", (455, 0, 52), (20, 700, 104))
    piece("WindowHeaderWall", (455, 0, 320), (20, 700, 40))
    piece("WindowLeftPier", (455, -285, 202), (20, 130, 196))
    piece("WindowRightPier", (455, 285, 202), (20, 130, 196))
    for z in (108, 298):
        piece("WindowFrame_%s" % z, (441, 0, z), (40, 458, 14))
    for y in (-226, 226):
        piece("WindowUpright_%s" % y, (441, y, 203), (40, 14, 204))
    # North wall has a walkable 160 cm doorway and a small adjoining corridor.
    piece("DoorWallLeft", (-270, 355, 170), (360, 20, 340))
    piece("DoorWallRight", (270, 355, 170), (360, 20, 340))
    piece("DoorLintel", (0, 355, 295), (180, 25, 90))
    piece("CorridorFloor", (0, 515, -8), (180, 320, 16))
    piece("CorridorEnd", (0, 675, 150), (200, 20, 300))
    for x in (-100, 100):
        piece("CorridorSide_%s" % x, (x, 515, 150), (20, 300, 300))
    # Roof slabs leave a real skylight opening at X=0..220, Y=-100..150.
    piece("RoofWest", (-225, 0, 350), (450, 720, 20))
    piece("RoofEast", (340, 0, 350), (240, 720, 20))
    piece("RoofSouth", (110, -230, 350), (220, 260, 20))
    piece("RoofNorth", (110, 255, 350), (220, 210, 20))
    for y in (-120, 170):
        piece("SkylightRail_%s" % y, (110, y, 335), (260, 12, 25))
    for x in (0, 110, 220):
        piece("SkylightRib_%s" % x, (x, 25, 352), (8, 300, 8))
    # Plane local U stays horizontal, V vertical. Pitch+Yaw pointed the old
    # study's backdrop along the window wall instead of toward the window.
    piece("DesertVista_BackdropNotWalkable", (1800, 0, 530), (2800, 1400, 100),
          "vista", unreal.Rotator(pitch=0, yaw=90, roll=90), flat=True)
    piece("ChalkboardFrame", (-440, -70, 220), (14, 278, 188))
    piece("ChalkboardSurface", (-432, -70, 220), (260, 173, 100),
          "chalkboard", unreal.Rotator(pitch=0, yaw=-90, roll=90), flat=True)

    start = actors.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(-220, 180, 100),
        unreal.Rotator(pitch=0, yaw=-35, roll=0))
    start.set_actor_label("Workshop_PlayerStart_ThirdPerson")
    sun = actors.spawn_actor_from_class(
        unreal.DirectionalLight, unreal.Vector(300, 100, 700),
        unreal.Rotator(pitch=-42, yaw=195, roll=0))
    sun_component = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sun_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun_component.set_intensity(6.0)
    sun_component.set_light_color(unreal.LinearColor(1.0, 0.81, 0.56, 1.0))
    actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(), unreal.Rotator())
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500), unreal.Rotator())
    sky_component = sky.get_component_by_class(unreal.SkyLightComponent)
    sky_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky_component.set_editor_property("real_time_capture", True)
    sky_component.set_intensity(0.7)
    if not level.save_current_level():
        raise RuntimeError("Workshop level save failed")
    report = {"schema": "rac.workshop-shell.v1", "level": level_path,
              "status": "architectural study only; props and runtime verification pending",
              "source_art_sha256": hashes, "separate_module_count": len(placed),
              "placed": placed, "runtime_verified": False, "asset_approvals_granted": False}
    evidence = root / "work/sunset-workshop/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (level_path.rsplit("/", 1)[1] + ".json")).write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("WORKSHOP_SHELL_SAVED: the room exists; the furniture has not arrived.")


main()
