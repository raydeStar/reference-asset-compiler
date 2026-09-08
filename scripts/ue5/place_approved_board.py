"""Place the verified native board as an independent prop in a new workshop revision."""
import hashlib
import json
import os
from pathlib import Path

import unreal


def main():
    root = Path(os.environ["RAC_ROOT"])
    job = root / "work/sunset-circuit-board"
    state = json.loads((job / "state.json").read_text())
    for stage in ("texture_approval", "ue5_import", "ue5_runtime_review"):
        if state["stages"][stage]["status"] != "passed":
            raise RuntimeError("Board lacks " + stage)
        for row in state["stages"][stage]["evidence"]:
            path = Path(row["path"])
            path = path if path.is_absolute() else job / path
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise RuntimeError("Board evidence changed: " + str(path))
    source = "/Game/SunsetWorkshop/L_WorkshopPreview_v003"
    target = "/Game/SunsetWorkshop/L_WorkshopPreview_v004"
    output = root / "work/sunset-workshop/evidence/L_WorkshopPreview_v004.json"
    if unreal.EditorAssetLibrary.does_asset_exist(target) or output.exists():
        raise RuntimeError("Retain every scene revision")
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level.new_level_from_template(target, source):
        raise RuntimeError("Could not copy the playable preview")
    mesh_path = "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v002"
    mesh = unreal.load_asset(mesh_path)
    bounds = mesh.get_bounds()
    local_floor = bounds.origin.z - bounds.box_extent.z
    location = unreal.Vector(56, -248, 92.3 - local_floor)
    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_object(
        mesh, location, unreal.Rotator())
    actor.set_actor_label("CircuitBoard_Foreground")
    actor.set_folder_path("Workshop/IndependentProps")
    # Like the other small tools, this is visual clutter, not a knee-high wall.
    actor.static_mesh_component.set_collision_profile_name("NoCollision")
    if not level.save_current_level():
        raise RuntimeError("New workshop map failed to save")
    receipt = {"schema": "rac.workshop-preview-addition.v1", "level": target,
               "source_level": source, "source_preserved": True,
               "placed": [{"label": actor.get_actor_label(), "mesh": mesh_path,
                           "position_cm": location.to_tuple(), "local_floor_cm": local_floor,
                           "table_surface_cm": 92.3, "collision": False}],
               "import_receipt_sha256": hashlib.sha256((job / "validation/ue5-import-board-native-v002.json").read_bytes()).hexdigest(),
               "runtime_review_sha256": hashlib.sha256((job / "validation/ue5-runtime-review.json").read_bytes()).hexdigest(),
               "runtime_verified": False, "production_ready": False}
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    unreal.log("WORKSHOP_BOARD_PLACED -- a separate circuit board, as ordered.")


if __name__ == "__main__":
    main()
