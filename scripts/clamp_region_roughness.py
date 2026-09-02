"""Raise the roughness floor of glossy texels inside a geometry-derived UV region.

This is a PBR channel calibration, not a repaint. Base color, metallic, mesh,
and UVs are copied bit-for-bit; only roughness texels that the AI painter left
mirror-glossy inside the supplied region mask are lifted to a floor value. The
region mask must come from a geometry selection (for example the head-front
mask rasterized by ``project_ai_reference_region.py``), so the edit stays bound
to modeled features rather than to a hand-drawn shape.

Why it exists: Hunyuan3D-Paint 2.1 gave the cat's eyes roughness near 0.11 on
an otherwise 0.95 head. Under any sizeable light the lumpy eye geometry then
mirrors the light as a hard white blob that overrides the painted glint the
reference calls for. Lifting the floor keeps the painted glint as the visual
highlight.

Usage:
  python scripts/clamp_region_roughness.py <source_attempt_dir> <output_dir> \
      --region-mask <mask.png> [--glossy-below 0.5] [--floor 0.45] \
      [--min-component-texels 1000] [--dilate-pixels 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--region-mask", type=Path, required=True)
    parser.add_argument("--stem", default="cat-painted")
    parser.add_argument("--glossy-below", type=float, default=0.5)
    parser.add_argument("--floor", type=float, default=0.45)
    parser.add_argument("--min-component-texels", type=int, default=1000)
    parser.add_argument("--dilate-pixels", type=int, default=2)
    parser.add_argument("--jpeg-quality", type=int, default=96)
    args = parser.parse_args()

    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite immutable evidence: {output}")
    stem = args.stem
    names = {
        "mesh": f"{stem}.obj",
        "mtl": f"{stem}.mtl",
        "base_color": f"{stem}.jpg",
        "metallic": f"{stem}_metallic.jpg",
        "roughness": f"{stem}_roughness.jpg",
    }
    for name in names.values():
        if not (source / name).is_file():
            raise RuntimeError(f"Missing source file: {source / name}")
    if not args.region_mask.is_file():
        raise RuntimeError(f"Missing region mask: {args.region_mask}")

    rough_img = Image.open(source / names["roughness"]).convert("L")
    rough = np.asarray(rough_img).astype(np.float32) / 255.0
    region = np.asarray(Image.open(args.region_mask).convert("L").resize(
        rough_img.size, Image.Resampling.NEAREST)) > 127
    glossy = region & (rough < args.glossy_below)
    labels, count = ndimage.label(glossy)
    components = []
    keep = np.zeros_like(glossy)
    for index in range(1, count + 1):
        selected = labels == index
        area = int(selected.sum())
        ys, xs = np.nonzero(selected)
        record = {
            "texels": area,
            "bbox_xyxy": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "roughness_mean_before": float(rough[selected].mean()),
            "kept": area >= args.min_component_texels,
        }
        components.append(record)
        if record["kept"]:
            keep |= selected
    if not keep.any():
        raise RuntimeError("No glossy component inside the region met the size threshold")
    if args.dilate_pixels > 0:
        keep = ndimage.binary_dilation(keep, iterations=args.dilate_pixels) & region

    lifted = rough.copy()
    lifted[keep] = np.maximum(lifted[keep], args.floor)
    changed = int(np.count_nonzero(lifted != rough))

    output.mkdir(parents=True)
    for key in ("mesh", "mtl", "base_color", "metallic"):
        shutil.copyfile(source / names[key], output / names[key])
    Image.fromarray(np.rint(lifted * 255.0).astype(np.uint8), mode="L").save(
        output / names["roughness"], quality=args.jpeg_quality, subsampling=0)
    mask_path = output / "roughness-lift-mask.png"
    Image.fromarray((keep * 255).astype(np.uint8), mode="L").save(mask_path)

    for key in ("mesh", "mtl", "base_color", "metallic"):
        if sha256(source / names[key]) != sha256(output / names[key]):
            raise RuntimeError(f"Copy drifted for {names[key]}")

    written = np.asarray(Image.open(output / names["roughness"]).convert("L")).astype(np.float32) / 255.0
    report = {
        "schema": "reference-asset-compiler.region-roughness-clamp.v1",
        "source_dir": str(source),
        "source_sha256": {key: sha256(source / name) for key, name in names.items()},
        "output_dir": str(output),
        "output_sha256": {key: sha256(output / name) for key, name in names.items()},
        "region_mask": str(args.region_mask.resolve()),
        "region_mask_sha256": sha256(args.region_mask),
        "lift_mask_sha256": sha256(mask_path),
        "parameters": {
            "glossy_below": args.glossy_below,
            "floor": args.floor,
            "min_component_texels": args.min_component_texels,
            "dilate_pixels": args.dilate_pixels,
            "jpeg_quality": args.jpeg_quality,
        },
        "components": components,
        "region_texels": int(region.sum()),
        "lifted_texels": int(keep.sum()),
        "changed_texels": changed,
        "atlas_fraction_changed": float(changed / rough.size),
        "roughness_in_lift_mask": {
            "before_mean": float(rough[keep].mean()),
            "after_mean": float(written[keep].mean()),
        },
        "base_color_changed": False,
        "metallic_changed": False,
        "geometry_or_uv_changed": False,
    }
    (output / "roughness-clamp-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "REGION_ROUGHNESS_CLAMP_OK "
        f"components_kept={sum(1 for c in components if c['kept'])} "
        f"lifted_texels={report['lifted_texels']} floor={args.floor}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
