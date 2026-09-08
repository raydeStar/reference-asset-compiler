"""Import a sibling circuit board without generated baked-light UVs.

The workshop uses dynamic lighting. Preserve the accepted FBX, all authored
UVs/normals/materials and original engine asset; measure native LOD0 again.
"""
import hashlib
import json
import os
from pathlib import Path

import unreal


def main():
    root = Path(os.environ["RAC_ROOT"])
    report_path = root / "work/sunset-workshop/evidence/board-dynamic-import-v001.json"
    destination = "/Game/SunsetWorkshop/Optimized/BoardDynamic_v001"
    original_path = "/Game/Compiled/SunsetCircuitBoardProduction/sunset-circuit-board-production"
    if report_path.exists() or unreal.EditorAssetLibrary.does_directory_exist(destination):
        raise RuntimeError("Retain earlier import probes")
    original = unreal.load_asset(original_path)
    if not isinstance(original,unreal.StaticMesh):
        raise RuntimeError("Original board is missing")
    folder = root / "out/sunset-circuit-board-production"
    source = folder / "sunset-circuit-board-production.fbx"
    if not source.is_file():
        raise RuntimeError("Published board FBX is missing")
    state = json.loads((root / "work/sunset-circuit-board/state.json").read_text())
    if state["stages"]["texture_approval"]["status"] != "passed":
        raise RuntimeError("Board appearance must already be approved")
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.import_mesh = True
    options.import_as_skeletal = False
    options.import_materials = False
    options.import_textures = False
    data = options.static_mesh_import_data
    data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.compute_weighted_normals = True
    data.auto_generate_collision = True
    data.combine_meshes = True
    data.generate_lightmap_u_vs = False
    task = unreal.AssetImportTask()
    task.filename = str(source)
    task.destination_path = destination
    task.destination_name = "SM_BoardDynamic_v001"
    task.automated = True
    task.replace_existing = False
    task.save = True
    task.options = options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = next((unreal.load_asset(p) for p in task.imported_object_paths
                 if isinstance(unreal.load_asset(p),unreal.StaticMesh)),None)
    if mesh is None:
        raise RuntimeError("No native static mesh produced")
    for i,_slot in enumerate(original.get_editor_property("static_materials")):
        mesh.set_material(i,original.get_material(i))
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    count = unreal.EditorStaticMeshLibrary.get_number_verts(mesh,0)
    report = {"schema":"reference-asset-compiler.board-dynamic-import-probe.v1",
              "source_fbx":str(source),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
              "engine":unreal.SystemLibrary.get_engine_version(),"original_mesh":original_path,
              "original_lod0_vertices":unreal.EditorStaticMeshLibrary.get_number_verts(original,0),
              "candidate_mesh":mesh.get_path_name(),"candidate_lod0_vertices":count,
              "budget":15000,"within_budget":0<count<=15000,
              "change":"disable generated lightmap UVs for dynamic lighting; no source geometry or artwork edit",
              "original_asset_preserved":True,"runtime_review_passed":False}
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    unreal.log("BOARD_DYNAMIC_PROBE " + str(count) + " vertices -- no chips were shaved for this test.")


main()
