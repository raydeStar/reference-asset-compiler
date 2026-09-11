"""CPU-only export regression fixture, not reconstructed artwork or an asset approval."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

import compile_prop
import rac_env

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.io import read_json, sha256_file, write_json  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--blender", type=Path)
    args = parser.parse_args(argv)
    blender = args.blender or rac_env.find_blender()
    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / "fixture.fbx"
    texture = root / "fixture.png"
    Image.new("RGB", (16, 16), (100, 140, 180)).save(texture)
    expression = (
        "import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
        "bpy.ops.mesh.primitive_cube_add(size=2); "
        "o=bpy.context.object; m=bpy.data.materials.new('M_Fixture'); m.use_nodes=True; "
        "o.data.materials.append(m); bpy.context.scene.unit_settings.system='METRIC'; "
        "bpy.context.scene.unit_settings.scale_length=1; "
        f"bpy.ops.export_scene.fbx(filepath={str(source)!r}, use_selection=True, "
        "object_types={'MESH'}, add_leaf_bones=False, bake_anim=False)"
    )
    result = subprocess.run([str(blender), "--background", "--factory-startup",
                             "--python-exit-code", "1", "--python-expr", expression],
                            capture_output=True, text=True, errors="replace", timeout=120)
    (root / "fixture-stdout.log").write_text(result.stdout, encoding="utf-8")
    (root / "fixture-stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode or not source.is_file():
        raise RuntimeError(f"Fixture export failed; retained at {root}")
    original_hashes = {str(p): sha256_file(p) for p in (source, texture)}
    recipe = root / "fixture-recipe.json"
    write_json(recipe, {"asset_id": "export-fixture", "kind": "static_prop",
                        "source": {"authority_fbx": str(source)},
                        "material_textures": {"M_Fixture": {"BaseColor": str(texture)}},
                        "normalize": {"target_height_m": 0.6,
                                      "target_height_reason": "Synthetic export regression fixture",
                                      "mesh_name": "SM_ExportFixture", "recenter": True}})
    compile_prop.ROOT = root
    output = compile_prop.compile_prop(recipe, blender)
    manifest = read_json(output / "export-fixture.ue5import.json")
    receipt = read_json(output / "compile-receipt.json")
    roundtrip = root / "roundtrip.json"
    expression = (
        "import bpy,json; from pathlib import Path; "
        "bpy.ops.wm.read_factory_settings(use_empty=True); "
        f"bpy.ops.import_scene.fbx(filepath={str(output / 'export-fixture.fbx')!r}); "
        "meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']; "
        "points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]; "
        "result={'height_m':max(p.z for p in points)-min(p.z for p in points), "
        "'tris':sum(len(p.vertices)-2 for o in meshes for p in o.data.polygons)}; "
        f"Path({str(roundtrip)!r}).write_text(json.dumps(result))"
    )
    imported = subprocess.run([str(blender), "--background", "--factory-startup",
                               "--python-exit-code", "1", "--python-expr", expression],
                              capture_output=True, text=True, errors="replace", timeout=120)
    (root / "roundtrip-stdout.log").write_text(imported.stdout, encoding="utf-8")
    (root / "roundtrip-stderr.log").write_text(imported.stderr, encoding="utf-8")
    if imported.returncode or not roundtrip.is_file():
        raise RuntimeError(f"FBX roundtrip failed; retained at {root}")
    native = read_json(roundtrip)
    checks = {"height_0_6m": abs(manifest["height_m"] - 0.6) < 1e-5,
              "triangles_12": manifest["triangles"] == 12,
              "fbx_roundtrip": abs(native["height_m"] - 0.6) < 1e-5 and native["tris"] == 12,
              "inputs_unchanged": all(sha256_file(Path(p)) == h for p, h in original_hashes.items()),
              "published_hashes": all(sha256_file(output / p) == h for p, h in receipt["files"].items())}
    before = {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*") if p.is_file()}
    try:
        compile_prop.compile_prop(recipe, blender)
        checks["existing_authority_refused"] = False
    except FileExistsError:
        checks["existing_authority_refused"] = before == {
            str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*") if p.is_file()}
    report = {"schema": "reference-asset-compiler.prop-export-smoke.v1",
              "ok": all(checks.values()), "checks": checks, "inference_launched": False,
              "synthetic_fixture_only": True, "asset_approval": False,
              "manifest_sha256": sha256_file(output / "export-fixture.ue5import.json")}
    write_json(root / "smoke.json", report)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        return 1
    print("RAC_PROP_EXPORT_OK -- the test cube has its passport; no character was summoned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
