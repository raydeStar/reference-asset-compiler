"""Calibrate the painter's metallic and roughness on non-metal parts, as a versioned derivative.

Hunyuan3D-Paint 2.1 left the Raider's cloth, skin and leather partly metallic and glossy, so the lit
trousers read as brushed steel. Inside a geometry-derived non-metal UV mask (rasterized from the part
each face belongs to), metallic is set to zero and roughness is lifted to a floor. Metal parts, base
colour, mesh and UVs are copied untouched.

Usage:
  python calibrate_pbr.py <paint_dir> <output_dir> --stem raider-body --mask nonmetal-mask.png [--floor 0.6]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paint_dir", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--stem", required=True)
    ap.add_argument("--mask", type=Path, required=True)
    ap.add_argument("--floor", type=float, default=0.6)
    args = ap.parse_args()
    src, out = args.paint_dir.resolve(), args.output_dir.resolve()
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite retained output: {out}")
    names = {k: f"{args.stem}{s}" for k, s in
             (("mesh", ".obj"), ("mtl", ".mtl"), ("base_color", ".png"), ("metallic", "_metallic.png"),
              ("roughness", "_roughness.png"))}
    for n in names.values():
        if not (src / n).is_file():
            raise RuntimeError(f"Missing source file: {src / n}")
    rough_img = Image.open(src / names["roughness"]).convert("L")
    mask = np.asarray(Image.open(args.mask).convert("L").resize(rough_img.size, Image.Resampling.NEAREST)) > 127
    rough = np.asarray(rough_img).astype(np.float32) / 255
    metal = np.asarray(Image.open(src / names["metallic"]).convert("L")).astype(np.float32) / 255
    new_rough = np.where(mask, np.maximum(rough, args.floor), rough)
    new_metal = np.where(mask, 0.0, metal)
    out.mkdir(parents=True)
    for k in ("mesh", "mtl", "base_color"):
        shutil.copyfile(src / names[k], out / names[k])
    Image.fromarray(np.rint(new_rough * 255).astype(np.uint8), "L").save(out / names["roughness"])
    Image.fromarray(np.rint(new_metal * 255).astype(np.uint8), "L").save(out / names["metallic"])
    report = {
        "schema": "reference-asset-compiler.nonmetal-pbr-calibration.v1",
        "source_dir": str(src), "output_dir": str(out),
        "source_sha256": {k: sha256(src / n) for k, n in names.items()},
        "output_sha256": {k: sha256(out / n) for k, n in names.items()},
        "mask": str(args.mask.resolve()), "mask_sha256": sha256(args.mask),
        "mask_fraction": float(mask.mean()), "roughness_floor": args.floor,
        "nonmetal_before": {"metallic_mean": float(metal[mask].mean()), "roughness_mean": float(rough[mask].mean())},
        "nonmetal_after": {"metallic_mean": float(new_metal[mask].mean()), "roughness_mean": float(new_rough[mask].mean())},
        "base_color_changed": False, "geometry_or_uv_changed": False,
    }
    (out / "pbr-calibration-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("NONMETAL_PBR_OK", json.dumps(report["nonmetal_before"]), "->", json.dumps(report["nonmetal_after"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
