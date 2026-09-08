"""Read built LOD vertex counts for the explicitly approved workshop imports."""
import json
import os
from pathlib import Path

import unreal


root = Path(os.environ["RAC_ROOT"])
output = root / "work/sunset-workshop/evidence/ue-vertex-audit-v001.json"
if output.exists():
    raise RuntimeError("Retained audit exists; do not overwrite the evidence")
records = []
for name in ("radio", "wrench", "circuit-board", "crate", "stool"):
    asset = "sunset-" + name + "-production"
    folder = "".join(part.capitalize() for part in asset.split("-"))
    mesh = unreal.load_asset("/Game/Compiled/" + folder + "/" + asset)
    if mesh is None:
        raise RuntimeError("Missing approved workshop import: " + asset)
    counts = [unreal.EditorStaticMeshLibrary.get_number_verts(mesh, lod)
              for lod in range(mesh.get_num_lods())]
    records.append({"asset": asset, "mesh": mesh.get_path_name(),
                    "lod_vertices": counts, "budget": 15000,
                    "within_budget": bool(counts and 0 < counts[0] <= 15000)})
output.write_text(json.dumps({"engine_version": unreal.SystemLibrary.get_engine_version(),
                              "assets": records, "ok": all(r["within_budget"] for r in records)},
                             indent=2) + "\n", encoding="utf-8")
unreal.log("WORKSHOP_VERTEX_AUDIT_WRITTEN -- imported vertices also answer to the butler.")
