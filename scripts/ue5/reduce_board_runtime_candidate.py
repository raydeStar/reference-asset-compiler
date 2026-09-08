"""Build a versioned native LOD0 derivative of the approved board; no source edits."""
import json
import os
from pathlib import Path

import unreal


root = Path(os.environ["RAC_ROOT"])
source = "/Game/Compiled/SunsetCircuitBoardProduction/sunset-circuit-board-production"
target = "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v001"
receipt = root / "work/sunset-workshop/evidence/board-reduced-v001.json"
if unreal.EditorAssetLibrary.does_asset_exist(target) or receipt.exists():
    raise RuntimeError("Keep previous board derivatives")
mesh = unreal.EditorAssetLibrary.duplicate_asset(source,target)
if mesh is None:
    raise RuntimeError("Board copy failed")
subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
options = unreal.EditorScriptingMeshReductionOptions()
rows = []
for fraction,screen in ((.85,1.0),(.5,.4),(.25,.15)):
    row = unreal.EditorScriptingMeshReductionSettings()
    row.percent_triangles = fraction
    row.screen_size = screen
    rows.append(row)
options.reduction_settings = rows
options.auto_compute_lod_screen_size = False
subsystem.set_lods(mesh,options)
unreal.EditorAssetLibrary.save_loaded_asset(mesh)
counts = [unreal.EditorStaticMeshLibrary.get_number_verts(mesh,i) for i in range(mesh.get_num_lods())]
report = {"schema":"reference-asset-compiler.board-runtime-reduction.v1",
          "source_mesh":source,"candidate_mesh":target,"lod_vertices":counts,
          "triangle_fractions":[.85,.5,.25],"budget":15000,"within_budget":counts[0]<=15000,
          "original_asset_preserved":True,"visual_review_passed":False,
          "engine_version":unreal.SystemLibrary.get_engine_version()}
receipt.write_text(json.dumps(report,indent=2)+"\n")
unreal.log("BOARD_REDUCTION_CANDIDATE " + str(counts) + " -- appearance still gets a veto.")
