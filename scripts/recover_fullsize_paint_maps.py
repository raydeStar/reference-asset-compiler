"""Recover retained full-resolution Hunyuan bakes; never upscale or rerun inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def recover(attempt: Path, output: Path, *, stem: str = "painted", diagnostics: Path | None = None):
    attempt, output = attempt.resolve(), output.resolve()
    if not stem or Path(stem).name != stem or stem in {".", ".."}:
        raise ValueError("Paint stem must be a filename stem, not a path")
    diagnostics = diagnostics.resolve() if diagnostics is not None else attempt / "diagnostics"
    if output.exists():
        raise ValueError("Retained maps are immutable; choose a fresh output directory")
    validation_path = attempt / (stem + ".validation.json")
    validation = json.loads(validation_path.read_text())
    if (validation.get("faces_equal") is not True or
            not 0 <= validation.get("geometry_delta", float("inf")) <= 1e-6 or
            not 0 <= validation.get("uv_delta", float("inf")) <= 1e-6):
        raise ValueError("Cannot recover maps from an invalid geometry/UV paint run")
    albedo_path = diagnostics / "post-inpaint-albedo.png"
    mr_path = diagnostics / "post-inpaint-metallic-roughness.png"
    albedo = Image.open(albedo_path).convert("RGB")
    mr = Image.open(mr_path).convert("RGB")
    if albedo.size != mr.size or albedo.width != albedo.height:
        raise ValueError("Full-resolution bake channels do not agree")
    maps = {"BaseColor": albedo, "Metallic": mr.getchannel("R"), "Roughness": mr.getchannel("G")}
    suffixes = {"BaseColor": "", "Metallic": "_metallic", "Roughness": "_roughness"}
    correspondence = {}
    for channel, full in maps.items():
        exported_path = attempt / (stem + suffixes[channel] + ".jpg")
        exported = Image.open(exported_path).convert(full.mode)
        if full.size != (exported.width * 2, exported.height * 2):
            raise ValueError("Expected retained bake at exactly twice the exported dimensions")
        # The upstream exporter averages each 2x2 block. JPEG/quantization
        # introduces small differences; a flip or unrelated bake must not pass.
        reduced = np.asarray(full.resize(exported.size, Image.Resampling.BOX), dtype=np.float32)
        error = float(np.abs(reduced - np.asarray(exported, dtype=np.float32)).mean())
        if error > 5.0:
            raise ValueError(f"{channel} bake/export correspondence failed: MAE {error:.3f}")
        correspondence[channel] = {"export_sha256": sha(exported_path), "mean_absolute_error_255": error}
    output.mkdir(parents=True)
    shutil.copyfile(albedo_path, output / "BaseColor.png")
    maps["Metallic"].save(output / "Metallic.png")
    maps["Roughness"].save(output / "Roughness.png")
    receipt = {
        "schema": "reference-asset-compiler.fullsize-paint-recovery.v1",
        "operation": "retain original full-size albedo; split authored R metallic and G roughness",
        "source_validation_sha256": sha(validation_path),
        "source_obj_sha256": sha(attempt / (stem + ".obj")),
        "source_uv_transport_sha256": sha(Path(validation["source_mesh"])),
        "reference_sha256": sha(Path(validation["reference"])),
        "diagnostics": {str(p): sha(p) for p in (albedo_path, mr_path)},
        "output_maps": {channel: {"name": channel + ".png", "sha256": sha(output / (channel + ".png"))} for channel in maps},
        "resolution": albedo.width,
        "export_correspondence": correspondence,
        "upscaled": False, "inference_rerun": False, "geometry_or_uv_changed": False,
    }
    (output / "recovery.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("FULLSIZE_PAINT_RECOVERED", output, "-- the detail was in the cupboard all along.")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stem", default="painted", help="Existing paint output basename; default preserves legacy layout")
    parser.add_argument("--diagnostics", type=Path, help="Retained diagnostics directory if separate from paint outputs")
    args = parser.parse_args()
    recover(args.attempt, args.output, stem=args.stem, diagnostics=args.diagnostics)
