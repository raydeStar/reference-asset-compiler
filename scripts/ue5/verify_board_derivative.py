"""Read-only native verification of the retained board optimization, not a reimport."""
import hashlib
import json
import os
from pathlib import Path
import sys

import unreal

ROOT = Path(os.environ["RAC_ROOT"])
sys.path.insert(0, str(ROOT / "scripts/ue5"))
from import_and_verify import verify  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    version = os.environ.get("RAC_BOARD_VERSION", "v001")
    if version not in {"v001", "v002"}:
        raise ValueError("Unknown retained board version")
    output = ROOT / ("work/sunset-workshop/evidence/board-native-verify-" + version + ".json")
    if output.exists():
        raise ValueError("Retained verification exists; the archive has a long memory.")
    source = "/Game/Compiled/SunsetCircuitBoardProduction/sunset-circuit-board-production"
    target = "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_" + version
    manifest_path = ROOT / "out/sunset-circuit-board-production/sunset-circuit-board-production.ue5import.json"
    manifest = json.loads(manifest_path.read_text())
    intake = json.loads((ROOT / "work/sunset-circuit-board/intake.json").read_text())
    root = source.rsplit("/", 1)[0]
    results = []
    for path in (source, target):
        entry = verify(manifest, root, mesh_path=path, budgets=intake["budgets"])
        entry["manifest_sha256"] = digest(manifest_path)
        results.append(entry)
    material_paths = []
    for path in (source, target):
        mesh = unreal.load_asset(path)
        material_paths.append([slot.material_interface.get_path_name()
                               for slot in mesh.get_editor_property("static_materials")])
    native_files = []
    for path in (source, target):
        file = ROOT / "work/ue5-validate/Content" / (path.removeprefix("/Game/") + ".uasset")
        native_files.append({"path": str(file), "sha256": digest(file), "mesh": path})
    derivative = {"source_mesh": source, "candidate_mesh": target,
                  "operation": "native_lod_reduction", "triangle_fractions": [.85, .5, .25],
                  "source_manifest_sha256": digest(manifest_path),
                  "material_interfaces_identical": material_paths[0] == material_paths[1],
                  "material_interfaces": material_paths, "native_files": native_files}
    artifact_paths = [ROOT / "work/sunset-workshop/evidence/board-reduced-v001.json"]
    if version == "v002":
        artifact_paths.append(ROOT / "work/sunset-workshop/evidence/board-scale-normalization-v002.json")
    derivative["artifacts"] = [{"path": str(p), "sha256": digest(p)} for p in artifact_paths]
    results[1]["checks"].append({"check": "derivative_material_identity",
                                "ok": derivative["material_interfaces_identical"],
                                "detail": material_paths})
    results[1]["ok"] = all(c["ok"] for c in results[1]["checks"])
    report = {"engine_version": unreal.SystemLibrary.get_engine_version(),
              "assets": [results[1]], "source_diagnostic": results[0],
              "native_derivative": derivative, "ok": results[1]["ok"]}
    output.write_text(json.dumps(report, indent=2) + "\n")
    unreal.log("BOARD_NATIVE_VERIFY " + str(report["ok"]) + " -- no flattering vertex counts.")


if __name__ == "__main__":
    main()
