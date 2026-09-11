"""Compile a static prop in an isolated, hash-bound attempt; never replace an authority."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NORMALIZE_SCRIPT = ROOT / "scripts" / "blender" / "normalize_prop.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import rac_env  # noqa: E402
from reference_asset_compiler.io import read_json, sha256_file, write_json  # noqa: E402


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", re.sub(r"^M_", "", name))


def snapshot(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required input is missing: {path}")
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def require_unchanged(rows: list[dict]) -> None:
    for row in rows:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            raise ValueError(f"Input changed during compilation: {row['path']}")


def validate_output(report: dict, attempt_id: str, recipe: Path, source: dict,
                    texture_map: dict, fbx: Path, asset: str) -> None:
    if (report.get("schema") != "reference-asset-compiler.prop-normalization.v1"
            or report.get("run_id") != attempt_id or report.get("asset_id") != asset):
        raise ValueError("Normalization receipt does not belong to this attempt")
    if report.get("input_recipe_sha256") != sha256_file(recipe):
        raise ValueError("Normalization recipe hash mismatch")
    if (report.get("source_sha256") != source["sha256"]
            or Path(report.get("source_authority", "")).resolve() != Path(source["path"])):
        raise ValueError("Normalization source mesh mismatch")
    expected_textures = {str(Path(path).resolve()): sha256_file(Path(path))
                         for slots in texture_map.values() for path in slots.values()}
    if report.get("input_texture_hashes") != expected_textures:
        raise ValueError("Normalization texture hashes mismatch")
    if not fbx.is_file() or fbx.stat().st_size == 0:
        raise ValueError("Normalization did not produce a nonempty FBX")
    if (report.get("output_fbx_sha256") != sha256_file(fbx)
            or Path(report.get("output_fbx", "")).resolve() != fbx.resolve()):
        raise ValueError("Normalization output FBX mismatch")
    after = report.get("after", {})
    height, tris = after.get("height_m"), after.get("tris")
    if (type(height) not in (int, float) or not math.isfinite(height) or height <= 0
            or type(tris) is not int or tris <= 0):
        raise ValueError("Normalization requires positive finite height and triangle measurements")


def build_manifest(asset: str, recipe: dict, measured: dict, texture_map: dict) -> dict:
    manifest = {
        "asset_id": asset,
        "asset_kind": "static_prop",
        "articulation": "static",
        # Keyed the way every other manifest in out/ is keyed, because the UE5
        # importer reads them all the same way and a prop that spells the mesh
        # key differently is simply skipped -- with one log line, in the middle
        # of a successful-looking import of everything else.
        "fbx": asset + ".fbx",
        "ue5_mesh_type": "StaticMesh",
        "materials": sorted(texture_map),
        "textures": {
            material: {
                slot: {
                    "file": "textures/{0}".format(Path(path).name),
                    "settings": {"compression": "TC_Default", "sRGB": True,
                                 "flip_green": False},
                }
                for slot, path in slots.items()
            }
            for material, slots in texture_map.items()
        },
        "measurements": {
            "height_m": measured["after"]["height_m"],
            "height_cm_in_ue5": round(measured["after"]["height_m"] * 100.0, 1),
            "total_tris": measured["after"]["tris"],
        },
        "height_m": measured["after"]["height_m"],
        "triangles": measured["after"]["tris"],
        "ue5_import": {
            "import_as_skeletal": False,
            # The FBX is written in metres and Unreal works in centimetres, and
            # convert_scene handles that from the file's own unit header -- the
            # characters import at uniform scale 1 the same way. A prop that
            # arrives a hundred times too small or too large is almost always
            # this pair being set to compensate for each other.
            "import_uniform_scale": 1,
            "convert_scene": True,
            "force_front_x_axis": False,
            "normal_import_method": "ImportNormals",
            "generate_collision": True,
            "collision_note": "Auto convex from the mesh. A five-spoke base is "
                              "not convex, so the hull bridges between the "
                              "spokes; for something you walk into rather than "
                              "roll under, that is the right trade."
        },
        "lods": [
            {"lod": 0, "percent_triangles": 1, "screen_size": 1, "source": "imported"},
            {"lod": 1, "percent_triangles": 0.5, "screen_size": 0.4,
             "source": "ue5_reduction"},
            {"lod": 2, "percent_triangles": 0.25, "screen_size": 0.15,
             "source": "ue5_reduction"},
        ],
        "source_authority": measured["source_authority"],
        "reference_authority": recipe["source"].get("reference_authority"),
    }
    return manifest


def compile_prop(recipe_path: Path, blender: Path) -> Path:
    recipe_path = recipe_path.resolve()
    recipe_input = snapshot(recipe_path)
    recipe = rac_env.expand_tree(json.loads(recipe_path.read_text(encoding="utf-8-sig")))
    if recipe.get("kind") != "static_prop":
        raise ValueError("This driver compiles static_prop recipes only")
    asset = recipe["asset_id"]
    if not isinstance(asset, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", asset):
        raise ValueError("asset_id must be lower-case-hyphenated")
    source = snapshot(Path(recipe["source"]["authority_fbx"]).resolve())
    recipe["source"]["authority_fbx"] = source["path"]
    out = ROOT / "out" / asset
    if out.exists():
        raise FileExistsError(f"Authority destination already exists: {out}; choose a new asset id")
    run_id = uuid.uuid4().hex
    attempt = ROOT / "work" / asset / "compile-attempts" / run_id
    attempt.mkdir(parents=True, exist_ok=False)
    payload = attempt / "payload"
    textures = payload / "textures"
    textures.mkdir(parents=True)
    execution = {"schema": "reference-asset-compiler.prop-compile.v1", "run_id": run_id,
                 "asset_id": asset, "status": "running", "inputs": [recipe_input, source],
                 "inference_launched": False, "retry_performed": False}
    write_json(attempt / "execution.json", execution)
    try:
        renames = recipe.get("normalize", {}).get("material_renames", {})
        texture_map, destinations = {}, set()
        staged_inputs = []
        for source_material, slots in recipe.get("material_textures", {}).items():
            material = renames.get(source_material, source_material)
            if material in texture_map:
                raise ValueError(f"Material rename collision: {material}")
            texture_map[material] = {}
            for slot, path in slots.items():
                source_texture = snapshot(Path(path).resolve())
                execution["inputs"].append(source_texture)
                suffix = Path(path).suffix.lower()
                if not suffix or not re.fullmatch(r"[A-Za-z0-9_]+", slot):
                    raise ValueError("Textures require a file extension and a simple slot name")
                # Downstream baking discovers *_BaseColor.png. Keep that contract,
                # and actually encode PNG when the input is a JPEG or other format.
                name = f"T_{slug(material)}_{slot}.png"
                if name.lower() in destinations:
                    raise ValueError(f"Texture filename collision: {name}")
                destinations.add(name.lower())
                destination = textures / name
                if suffix == ".png":
                    shutil.copyfile(source_texture["path"], destination)
                else:
                    with Image.open(source_texture["path"]) as image:
                        image.convert("RGBA").save(destination, format="PNG")
                staged = snapshot(destination)
                if suffix == ".png" and staged["sha256"] != source_texture["sha256"]:
                    raise ValueError("Texture changed while staging")
                staged_inputs.append(staged)
                texture_map[material][slot] = str(destination)
        frozen_recipe = attempt / "recipe.json"
        write_json(frozen_recipe, recipe)
        map_path = attempt / "texture-map.json"
        write_json(map_path, texture_map)
        staged_inputs.extend([snapshot(frozen_recipe), snapshot(map_path)])
        fbx, report = payload / f"{asset}.fbx", attempt / "normalize-prop-report.json"
        command = [str(blender), "-b", "--factory-startup", "--python-exit-code", "1",
                   "--python", str(NORMALIZE_SCRIPT), "--",
                   str(frozen_recipe), str(fbx), str(report), str(map_path), run_id]
        execution["command"] = command
        write_json(attempt / "execution.json", execution)
        done = subprocess.run(command, capture_output=True, text=True, errors="replace", cwd=ROOT)
        (attempt / "stdout.log").write_text(done.stdout, encoding="utf-8")
        (attempt / "stderr.log").write_text(done.stderr, encoding="utf-8")
        execution["exit_code"] = done.returncode
        if done.returncode:
            raise RuntimeError(f"Blender failed with exit {done.returncode}; logs: {attempt}")
        measured = read_json(report)
        require_unchanged(execution["inputs"] + staged_inputs)
        validate_output(measured, run_id, frozen_recipe, source, texture_map, fbx, asset)
        shutil.copyfile(report, payload / "normalize-prop-report.json")
        manifest = build_manifest(asset, recipe, measured, texture_map)
        manifest["compile_receipt"] = {"file": "compile-receipt.json"}
        receipt = {"schema": "reference-asset-compiler.prop-publication.v1", "run_id": run_id,
                   "inputs": execution["inputs"], "normalization_sha256": sha256_file(report),
                   "files": {str(p.relative_to(payload)).replace("\\", "/"): sha256_file(p)
                             for p in payload.rglob("*") if p.is_file()}}
        write_json(payload / "compile-receipt.json", receipt)
        manifest["compile_receipt"]["sha256"] = sha256_file(payload / "compile-receipt.json")
        write_json(payload / f"{asset}.ue5import.json", manifest)
        # Build beside the final directory, then rename it whole. The old authority
        # is never used as a scratch pad, even when the spell fizzles halfway through.
        publish = ROOT / "out" / f".{asset}-{run_id}"
        publish.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(payload, publish)
        for file in payload.rglob("*"):
            if file.is_file() and sha256_file(file) != sha256_file(publish / file.relative_to(payload)):
                raise ValueError("Publication copy hash mismatch")
        if out.exists():
            raise FileExistsError(f"Authority appeared during compile; retained candidate at {attempt}")
        publish.rename(out)
        execution.update(status="published", output=str(out), receipt_sha256=sha256_file(
            out / "compile-receipt.json"))
        print(f"[PROP] {asset}: {manifest['triangles']} tris -> {out}; the receipts check out.")
        return out
    except BaseException as error:
        execution.update(status="failed", failure=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json(attempt / "execution.json", execution)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--blender", type=Path)
    args = parser.parse_args(argv)
    try:
        blender = args.blender or rac_env.find_blender()
        if not blender.is_file():
            raise FileNotFoundError(f"Blender executable is missing: {blender}")
        compile_prop(args.recipe, blender)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"[PROP] FAILED: {error} -- the previous authority keeps its keys.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
