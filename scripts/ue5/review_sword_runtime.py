"""Isolated workshop fixture: native sword, four sides and all three LODs.

This never changes the sword, its material, or the playable workshop. The
fixture is visual evidence only, not proof of back attachment or gameplay.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import time

import unreal


root = Path(os.environ["RAC_ROOT"])
version = os.environ.get("RAC_SWORD_REVIEW_VERSION", "v001")
if version not in {"v001", "v002", "v003"}:
    raise ValueError("Unknown sword review fixture version")
out = root / ("work/sunset-workshop/evidence/sword-runtime-" + version)
target = "/Game/SunsetWorkshop/L_SwordReview_" + version
source_level = "/Game/SunsetWorkshop/L_WorkshopPreview_v004"
mesh_path = "/Game/Compiled/SunsetSwordV1Production/sunset-sword-v1-production"
manifest = root / "out/sunset-sword-v1-production/sunset-sword-v1-production.ue5import.json"
import_receipt = root / "work/sunset-sword-v1/validation/ue5-import.json"
if out.exists() or unreal.EditorAssetLibrary.does_asset_exist(target):
    raise RuntimeError("Preserve prior sword evidence; choose a versioned fixture")
mesh = unreal.load_asset(mesh_path)
if not isinstance(mesh, unreal.StaticMesh):
    raise RuntimeError("The exact imported sword is missing")
out.mkdir(parents=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.new_level_from_template(target, source_level):
    raise RuntimeError("Could not create separate sword review fixture")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sword = actors.spawn_actor_from_object(mesh, unreal.Vector(0, 100, 5), unreal.Rotator())
sword.set_actor_label("RAC_Sword_VisualFixture_NotAttachment")
component = sword.static_mesh_component
component.set_collision_profile_name("NoCollision")
component.set_editor_property("forced_lod_model", 1)
review_lights = []
if version in {"v002", "v003"}:
    fill_intensity = 1800 if version == "v002" else 180
    # Neutral fill belongs to this inspection copy, never the playable level.
    for label, xyz, rotation in [
        ("Front", (0, -90, 145), (-20, 90)),
        ("Back", (0, 285, 145), (-20, -90)),
        ("Side", (190, 100, 145), (-20, 180)),
    ]:
        light = actors.spawn_actor_from_class(unreal.RectLight, unreal.Vector(*xyz),
            unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=0))
        light.set_actor_label("RAC_Sword_InspectionFill_" + label)
        lamp = light.get_component_by_class(unreal.RectLightComponent)
        lamp.set_mobility(unreal.ComponentMobility.MOVABLE)
        lamp.set_intensity(fill_intensity)
        lamp.set_editor_property("source_width", 140.0)
        lamp.set_editor_property("source_height", 180.0)
        lamp.set_editor_property("attenuation_radius", 500.0)
        review_lights.append({"label": label, "position": xyz, "intensity": fill_intensity,
                              "source_width": 140, "source_height": 180})
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.editor_set_game_view(True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
views = [
    ("front", (0, -55, 80), 1),
    ("three-quarter", (110, -10, 80), 1),
    ("side", (155, 100, 80), 1),
    ("back", (0, 255, 80), 1),
    ("front-lod1", (0, -55, 80), 2),
    ("front-lod2", (0, -55, 80), 3),
]
aim = (0, 100, 72.5)
state = {"index": 0, "phase": "startup", "time": time.monotonic(), "frames": []}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    component.set_editor_property("forced_lod_model", 1)
    saved = level.save_current_level()
    record = {
        "schema": "reference-asset-compiler.ue-static-multiview-review.v1",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "level": target, "source_level": source_level, "source_level_preserved": True,
        "inspection_fill_lights": review_lights,
        "manifest_sha256": sha(manifest), "import_receipt_sha256": sha(import_receipt),
        "placed": [{"asset": mesh_path, "position_cm": [0, 100, 5], "yaw": 0,
                    "label": sword.get_actor_label(), "collision": "NoCollision"}],
        "native_lods": [{"lod": lod, "vertices": unreal.EditorStaticMeshLibrary.get_number_verts(mesh, lod),
                         "triangles": mesh.get_num_triangles(lod), "sections": mesh.get_num_sections(lod)}
                        for lod in range(mesh.get_num_lods())],
        "frames": state["frames"], "error": error, "level_saved": bool(saved),
        "scope": "Static editor visual fixture only; no character, attachment, movement or cooked proof",
        "production_ready": False,
    }
    (out / "review.json").write_text(json.dumps(record, indent=2) + "\n")
    unreal.log("RAC_SWORD_REVIEW_RETAINED -- six viewpoints, no sleight of hand.")
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        now = time.monotonic()
        name, xyz, forced_lod = views[state["index"]]
        frame = out / (name + ".png")
        if state["phase"] == "startup" and now - state["time"] > 5:
            component.set_editor_property("forced_lod_model", forced_lod)
            dx, dy, dz = [aim[i] - xyz[i] for i in range(3)]
            rot = unreal.Rotator(pitch=math.degrees(math.atan2(dz, math.hypot(dx, dy))),
                                 yaw=math.degrees(math.atan2(dy, dx)), roll=0)
            editor.set_level_viewport_camera_info(unreal.Vector(*xyz), rot)
            state.update(phase="warm", time=now)
        elif state["phase"] == "warm" and now - state["time"] > 12:
            unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, str(frame))
            state.update(phase="capture", time=now)
        elif state["phase"] == "capture" and frame.is_file() and now - state["time"] > 3:
            state["frames"].append({"name": name, "path": str(frame), "sha256": sha(frame),
                                   "mesh": mesh_path, "camera_position": xyz, "camera_target": aim,
                                   "forced_lod_model": component.get_editor_property("forced_lod_model")})
            state["index"] += 1
            if state["index"] == len(views):
                finish()
            else:
                state.update(phase="startup", time=now - 6)
        elif now - state["time"] > 90:
            finish("Timed out capturing sword view " + name)
    except Exception as error:
        finish(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
