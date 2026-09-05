"""UE 5.8 dedicated-process adapter; dry-run unless RAC_SCENE_APPLY=1.

Environment: RAC_SCENE_RECIPE, RAC_SCENE_OUTPUT (fresh),
RAC_SCENE_DEDICATED_EDITOR=1. Never run this inside a user's interactive editor.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.scene_tools import (  # noqa: E402
    plan_atmosphere, read_utf8, require_unchanged,
)


def protected_snapshot(ue):
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    rows = {}
    for actor in actors.get_all_level_actors():
        components = actor.get_components_by_class(ue.StaticMeshComponent)
        for index, component in enumerate(components):
            key = actor.get_actor_label() + ":" + str(index)
            if key in rows:
                raise ValueError("Duplicate protected actor/component label: " + key)
            rows[key] = {
                "location": list(component.get_world_location().to_tuple()),
                "rotation": list(component.get_world_rotation().to_tuple()),
                "scale": list(component.get_world_scale().to_tuple()),
                "mesh": component.static_mesh.get_path_name() if component.static_mesh else None,
                "materials": [component.get_material(i).get_path_name()
                              if component.get_material(i) else None
                              for i in range(component.get_num_materials())],
                "collision": str(component.get_collision_profile_name()),
            }
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    mode = world.get_world_settings().get_editor_property("default_game_mode")
    rows["__game_mode__"] = mode.get_path_name() if mode else None
    return rows


def matches(actual, expected):
    if isinstance(expected, list):
        values = [actual.r, actual.g, actual.b]
        return all(math.isclose(a, e, rel_tol=1e-5, abs_tol=1e-5)
                   for a, e in zip(values, expected))
    return math.isclose(float(actual), expected, rel_tol=1e-5, abs_tol=1e-5)


def verify_fog(actor, component, operation):
    for key, value in operation["properties"].items():
        if not matches(component.get_editor_property(key), value):
            raise ValueError("Property did not stick: " + key)
    if (not matches(actor.get_actor_location().z, operation["z_cm"])
            or any(not matches(x, operation["uniform_scale"])
                   for x in actor.get_actor_scale3d().to_tuple())):
        raise ValueError("Fog transform did not stick")


def run(ue, recipe_path, output, apply=False):
    """No source writes, no actor additions/deletions, no automatic visual verdict."""
    recipe_path, output = Path(recipe_path), Path(output)
    recipe = read_utf8(recipe_path)
    plan = plan_atmosphere(recipe)
    if not ue.SystemLibrary.get_engine_version().startswith("5.8."):
        raise ValueError("Adapter requires UE 5.8; reverify engine conversions before porting")
    project_content = Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_content_dir()))
    map_file = project_content / (recipe["source_map"][6:] + ".umap")
    if not map_file.resolve().is_relative_to(project_content.resolve()):
        raise ValueError("Map escaped the project content root")
    if sha256_file(map_file) != recipe["source_map_sha256"]:
        raise ValueError("Source map hash changed")
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    lib = ue.EditorAssetLibrary
    if lib.does_asset_exist(recipe["target_map"]):
        raise ValueError("Target map already exists; choose a fresh revision")
    output.mkdir(parents=True, exist_ok=False)
    report = dict(plan, ok=False, source_map_sha256=recipe["source_map_sha256"],
                  recipe_sha256=sha256_file(recipe_path), error=None)
    try:
        if not level.load_level(recipe["source_map"]):
            raise ValueError("Could not load source map")
        before = protected_snapshot(ue)
        def targets():
            found = {}
            actors = ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors()
            for operation in plan["operations"]:
                selected = [a for a in actors if a.get_actor_label() == operation["actor"]]
                if len(selected) != 1:
                    raise ValueError("Fog actor must resolve exactly once: " + operation["actor"])
                actor = selected[0]
                component = actor.get_component_by_class(ue.LocalFogVolumeComponent)
                if not component:
                    raise ValueError("Actor is not a local fog volume: " + operation["actor"])
                found[operation["actor"]] = (actor, component)
            return found
        resolved = targets()  # Preflight every name before creating the derivative.
        report["before"] = {
            label: {key: str(component.get_editor_property(key)) for key in
                    ("radial_fog_extinction", "height_fog_extinction", "height_fog_falloff")}
            for label, (_, component) in resolved.items()}
        if apply:
            if not level.new_level_from_template(recipe["target_map"], recipe["source_map"]):
                raise ValueError("Could not create derivative through level subsystem")
            resolved = targets()
            for operation in plan["operations"]:
                actor, component = resolved[operation["actor"]]
                position = actor.get_actor_location()
                position.z = operation["z_cm"]
                actor.set_actor_location(position, False, False)
                scale = operation["uniform_scale"]
                actor.set_actor_scale3d(ue.Vector(scale, scale, scale))
                for key, value in operation["properties"].items():
                    component.set_editor_property(key, ue.LinearColor(*value, 1)
                                                  if isinstance(value, list) else value)
                verify_fog(actor, component, operation)
            require_unchanged(before, protected_snapshot(ue))
            if not level.save_current_level():
                raise ValueError("Could not save derivative")
            report["changes_applied"] = True
            if not level.load_level(recipe["target_map"]):
                raise ValueError("Could not reopen saved derivative")
            resolved = targets()
            for operation in plan["operations"]:
                verify_fog(*resolved[operation["actor"]], operation)
            target_file = project_content / (recipe["target_map"][6:] + ".umap")
            report["target_map_sha256"] = sha256_file(target_file)
            report["saved_derivative_reopened"] = True
        require_unchanged(before, protected_snapshot(ue))
        if sha256_file(map_file) != recipe["source_map_sha256"]:
            raise ValueError("Source map was modified")
        report.update(ok=True, protected_static_components=len(before) - 1,
                      original_static_components_and_game_mode_unchanged=True)
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ue.log("SCENE_ATMOSPHERE_CHECKED -- settings verified; artistic approval belongs to the guest.")
    return report


if __name__ == "__main__":
    import unreal
    if os.environ.get("RAC_SCENE_DEDICATED_EDITOR") != "1":
        raise RuntimeError("Use a dedicated editor process; do not disturb interactive work")
    run(unreal, os.environ["RAC_SCENE_RECIPE"], os.environ["RAC_SCENE_OUTPUT"],
        apply=os.environ.get("RAC_SCENE_APPLY") == "1")
