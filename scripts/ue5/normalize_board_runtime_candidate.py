"""Normalize the existing reduced board to its published physical height.

Uniform build scale only; no new geometry, materials or silhouette invention.
"""
import json
import os
from pathlib import Path

import unreal


def main():
    root = Path(os.environ["RAC_ROOT"])
    source = "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v001"
    target = "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v002"
    output = root / "work/sunset-workshop/evidence/board-scale-normalization-v002.json"
    if output.exists() or unreal.EditorAssetLibrary.does_asset_exist(target):
        raise ValueError("Never overwrite a retained board candidate")
    mesh = unreal.load_asset(source)
    before = mesh.get_bounds()
    extensions = {key: mesh.get_editor_property(key).to_tuple() for key in
                  ("positive_bounds_extension", "negative_bounds_extension")}
    if any(any(abs(v) > 1e-6 for v in row) for row in extensions.values()):
        raise ValueError("Bounds are padded; diagnose padding before touching geometry")
    manifest = root / "out/sunset-circuit-board-production/sunset-circuit-board-production.ue5import.json"
    height = json.loads(manifest.read_text())["measurements"]["height_cm_in_ue5"]
    factor = height / (before.box_extent.z * 2)
    if not .85 < factor < 1.15:
        raise ValueError("Unexpected scale drift; this repair is bounded to small reduction drift")
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    settings = [subsystem.get_lod_build_settings(mesh, i) for i in range(mesh.get_num_lods())]
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source, target)
    for i, row in enumerate(settings):
        old = row.build_scale3d
        row.build_scale3d = unreal.Vector(old.x * factor, old.y * factor, old.z * factor)
        subsystem.set_lod_build_settings(candidate, i, row)
    unreal.EditorAssetLibrary.save_loaded_asset(candidate)
    after = candidate.get_bounds()
    result = {"schema": "reference-asset-compiler.native-scale-normalization.v1",
              "engine_version": unreal.SystemLibrary.get_engine_version(),
              "source_mesh": source, "candidate_mesh": target,
              "bounds_extensions": extensions, "uniform_build_scale_factor": factor,
              "before_height_cm": before.box_extent.z * 2,
              "after_height_cm": after.box_extent.z * 2, "expected_height_cm": height,
              "source_preserved": True, "visual_review_passed": False}
    output.write_text(json.dumps(result, indent=2) + "\n")
    unreal.log("BOARD_SCALE_NORMALIZED " + str(result) + " -- centimetres deserve honesty.")


if __name__ == "__main__":
    main()
