"""Calibrate scalar PBR channels within retained geometry-bound PNG masks.

No color generation or geometry editing. Inputs and mask provenance are pinned
by configuration; outside the exact support every scalar texel is preserved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calibrate(roughness, metallic, support, floor, ceiling):
    if not 0 <= floor <= 1 or not 0 <= ceiling <= 1:
        raise ValueError("PBR bounds must be between zero and one")
    if roughness.shape != metallic.shape or support.shape != roughness.shape:
        raise ValueError("PBR maps and geometry support must have identical dimensions")
    rough, metal = roughness.copy(), metallic.copy()
    rough[support] = np.maximum(rough[support], round(floor * 255))
    metal[support] = np.minimum(metal[support], round(ceiling * 255))
    return rough, metal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.output.exists():
        raise ValueError("Preserve existing PBR candidates; choose a fresh output")
    for record in config["inputs"].values():
        if sha(record["path"]) != record["sha256"]:
            raise ValueError("Changed pinned input: " + record["path"])
    inputs = {key: Path(row["path"]) for key, row in config["inputs"].items()}
    rough = np.asarray(Image.open(inputs["Roughness"]).convert("L"))
    metal = np.asarray(Image.open(inputs["Metallic"]).convert("L"))
    support = np.zeros_like(rough, dtype=bool)
    for key in config["mask_keys"]:
        mask = np.asarray(Image.open(inputs[key]).convert("L"))
        if mask.shape != support.shape:
            raise ValueError("Never resize a geometry-bound mask implicitly")
        support |= mask > 0
    if not support.any() or support.mean() > config["maximum_atlas_fraction"]:
        raise ValueError("Unexpected material region coverage")
    calibrated = calibrate(rough, metal, support, config["roughness_floor"],
                           config["metallic_ceiling"])
    args.output.mkdir(parents=True)
    shutil.copyfile(inputs["BaseColor"], args.output / "BaseColor.png")
    changed = {}
    for channel, source, result in zip(("Roughness", "Metallic"), (rough, metal), calibrated):
        if not np.array_equal(source[~support], result[~support]):
            raise ValueError("Calibration escaped the geometry support")
        Image.fromarray(result).save(args.output / (channel + ".png"))
        changed[channel] = int(np.count_nonzero(source != result))
    Image.fromarray(support.astype(np.uint8) * 255).save(args.output / "support.png")
    report = {
        "schema": "reference-asset-compiler.scalar-pbr-calibration.v1",
        "config": str(args.config.resolve()), "config_sha256": sha(args.config),
        "inputs": config["inputs"], "support_texels": int(support.sum()),
        "changed_texels": changed, "base_color_bit_identical": True,
        "outside_support_bit_identical": True, "geometry_or_uv_changed": False,
        "outputs": {p.name: sha(p) for p in args.output.glob("*.png")},
        "production_ready": False, "status": "requires_lit_material_review",
    }
    (args.output / "calibration.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PBR_REGION_CALIBRATED", changed, "-- skin need not impersonate chrome.")


if __name__ == "__main__":
    main()
