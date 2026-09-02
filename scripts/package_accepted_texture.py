"""Package an accepted full-resolution AI texture without repainting it.

This is deliberately a remediation step, not a texture generator. It takes the
normalised FBX written by ``compile_prop.py``, the retained full-resolution
Hunyuan3D-Paint buffers, and the exact approved UV sampling record. Uniform
scale changes physical triangle area, so the copied UV-region record scales
area by scale squared while leaving UVs, normals, regions, and material IDs
bit-for-bit unchanged.

Usage:
  python scripts/package_accepted_texture.py office-chair-ai-v2 \
      --source-retopo work/.../retopo.json \
      --source-regions work/.../uv-regions.npz \
      --source-ao work/.../T_cleaned_AO.png \
      --source-albedo work/.../post-inpaint-albedo.png \
      --source-mr work/.../post-inpaint-metallic-roughness.png \
      --profile profiles/skeletons/static_prop.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import rac_env

ROOT = Path(__file__).resolve().parents[1]
BLENDER = rac_env.find_blender()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"required input is missing: {resolved}")
    return resolved


def run(command: list[str], label: str) -> None:
    completed = subprocess.run(command, cwd=ROOT, text=True)
    if completed.returncode:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset")
    parser.add_argument("--source-retopo", type=Path, required=True)
    parser.add_argument("--source-regions", type=Path, required=True)
    parser.add_argument("--source-ao", type=Path, required=True)
    parser.add_argument("--source-albedo", type=Path, required=True)
    parser.add_argument("--source-mr", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--resolution", type=int, default=4096)
    args = parser.parse_args()

    work = ROOT / "work" / args.asset
    prod = work / "prod-v2"
    if prod.exists():
        raise ValueError(f"refusing to overwrite retained production directory: {prod}")

    source_retopo = require_file(args.source_retopo)
    source_regions = require_file(args.source_regions)
    source_ao = require_file(args.source_ao)
    source_albedo = require_file(args.source_albedo)
    source_mr = require_file(args.source_mr)
    profile = require_file(args.profile)
    blender = require_file(args.blender)
    source_fbx = require_file(ROOT / "out" / args.asset / f"{args.asset}.fbx")
    source_manifest_path = require_file(
        ROOT / "out" / args.asset / f"{args.asset}.ue5import.json"
    )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8-sig"))
    expected_height = float(source_manifest["height_m"])
    expected_triangles = int(source_manifest["triangles"])
    materials = source_manifest.get("materials") or []
    if len(materials) != 1:
        raise ValueError(f"accepted texture remediation requires one material, found {materials}")
    material_name = materials[0]
    normalise_report_path = require_file(work / "normalize-prop-report.json")
    normalise_report = json.loads(normalise_report_path.read_text(encoding="utf-8-sig"))
    scale = float(normalise_report["uniform_scale_applied"])
    height = float(normalise_report["after"]["height_m"])
    triangles = int(normalise_report["after"]["tris"])
    if abs(height - expected_height) > 0.0005 or triangles != expected_triangles:
        raise ValueError(
            f"normalised payload drifted: height={height:.6f}m triangles={triangles}"
        )

    albedo = Image.open(source_albedo).convert("RGB")
    mr = Image.open(source_mr).convert("RGB")
    if albedo.size != (args.resolution, args.resolution):
        raise ValueError(f"albedo is {albedo.size}, expected {args.resolution} square")
    if mr.size != albedo.size:
        raise ValueError(f"metallic-roughness size {mr.size} does not match albedo")

    prod.mkdir(parents=True)
    production_fbx = prod / f"{args.asset}_production.fbx"
    base_path = prod / f"T_{args.asset}_BaseColor.png"
    ao_path = prod / f"T_{args.asset}_AO.png"
    roughness_path = prod / f"T_{args.asset}_Roughness.png"
    metallic_path = prod / f"T_{args.asset}_Metallic.png"
    albedo.save(base_path)
    Image.open(source_ao).convert("L").resize(
        albedo.size, Image.Resampling.LANCZOS
    ).save(ao_path)
    mr_array = np.asarray(mr)
    Image.fromarray(mr_array[:, :, 0], mode="L").save(metallic_path)
    Image.fromarray(mr_array[:, :, 1], mode="L").save(roughness_path)

    production_recipe = {
        "asset_id": args.asset,
        "kind": "static_prop",
        "source": {"authority_fbx": str(source_fbx)},
        "normalize": {
            "mesh_name": "SM_" + "".join(part.capitalize() for part in args.asset.split("-")),
            "target_height_m": height,
            "recenter": True,
            "yaw_degrees": 0.0,
            "material_renames": {},
        },
    }
    production_textures = {
        material_name: {
            "BaseColor": str(base_path.resolve()),
            "Roughness": str(roughness_path.resolve()),
            "Metallic": str(metallic_path.resolve()),
        }
    }
    production_recipe_path = prod / "production-normalize-recipe.json"
    production_texture_map_path = prod / "production-texture-map.json"
    production_normalise_report_path = prod / "production-normalize-report.json"
    production_recipe_path.write_text(
        json.dumps(production_recipe, indent=2) + "\n", encoding="utf-8"
    )
    production_texture_map_path.write_text(
        json.dumps(production_textures, indent=2) + "\n", encoding="utf-8"
    )
    run([
        str(blender), "-b", "--factory-startup", "--python",
        str(ROOT / "scripts" / "blender" / "normalize_prop.py"), "--",
        str(production_recipe_path.resolve()), str(production_fbx.resolve()),
        str(production_normalise_report_path.resolve()),
        str(production_texture_map_path.resolve()),
    ], "production FBX texture binding")
    production_normalise = json.loads(
        production_normalise_report_path.read_text(encoding="utf-8-sig")
    )
    if (int(production_normalise["after"]["tris"]) != triangles
            or abs(float(production_normalise["after"]["height_m"]) - height) > 0.0005):
        raise ValueError("production FBX binding changed geometry or physical scale")

    with np.load(source_regions, allow_pickle=False) as region_data:
        payload = {key: region_data[key] for key in region_data.files}
    payload["area"] = payload["area"] * (scale * scale)
    regions_path = prod / "uv-regions.npz"
    np.savez_compressed(regions_path, **payload)

    retopo = json.loads(source_retopo.read_text(encoding="utf-8-sig"))
    retopo.update({
        "resolution": args.resolution,
        "output_fbx": production_fbx.name,
        "physical_scale": {
            "uniform_scale": scale,
            "height_m": height,
            "source": str(normalise_report_path.resolve()),
        },
        "baked": {
            "BaseColor": base_path.name,
            "AO": ao_path.name,
            "Roughness": roughness_path.name,
            "Metallic": metallic_path.name,
        },
        "texture_lineage": {
            "operation": "retain accepted 4096 pre-downsample Hunyuan mapping",
            "source_albedo": str(source_albedo),
            "source_albedo_sha256": sha256(source_albedo),
            "source_metallic_roughness": str(source_mr),
            "source_metallic_roughness_sha256": sha256(source_mr),
            "uv_operation": "unchanged UVs; physical areas scaled by uniform_scale squared",
        },
    })
    retopo_path = prod / "retopo.json"
    retopo_path.write_text(json.dumps(retopo, indent=2) + "\n", encoding="utf-8")

    gate_path = prod / "gate-tex.json"
    run([
        sys.executable,
        str(ROOT / "scripts" / "gate_texture.py"),
        str(regions_path),
        str(base_path),
        str(profile),
        str(gate_path),
        "--material-name",
        material_name,
    ], "texture gate")

    run([
        str(blender), "-b", "--factory-startup", "--python",
        str(ROOT / "scripts" / "blender" / "render_turnaround.py"), "--",
        str(production_fbx.resolve()), str((prod / "turn").resolve()), "1024",
    ], "fixed-view render")

    receipt = {
        "schema": "reference-asset-compiler.accepted-texture-remediation.v1",
        "asset_id": args.asset,
        "source_texture_attempt": str(source_albedo.parent.parent),
        "source_albedo_sha256": sha256(source_albedo),
        "source_metallic_roughness_sha256": sha256(source_mr),
        "production_fbx_sha256": sha256(production_fbx),
        "retopo_sha256": sha256(retopo_path),
        "gate_texture_sha256": sha256(gate_path),
        "uniform_scale": scale,
        "height_m": height,
        "triangles": triangles,
        "operations": [
            "copy exact retained 4096 albedo",
            "split official metallic channel 0 and roughness channel 1",
            "uniformly normalize frozen geometry to measured physical height",
            "preserve UV coordinates and scale recorded surface area analytically",
        ],
    }
    (prod / "accepted-texture-remediation.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[ACCEPTED TEXTURE] {args.asset}: {triangles} tris, {height:.3f} m, "
        f"{args.resolution} atlas -- the old map grew up without changing its face."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
