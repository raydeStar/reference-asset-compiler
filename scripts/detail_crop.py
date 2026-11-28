"""Crop one detail (head, hand) out of an approved reference and upscale it 4x for a close acquisition.

A whole-body image-conditioned acquisition gives a head or a hand only a small share of the generator's
resolution: the Raider's head came out with lumpy hair and shallow eyes, and his gloves with fused,
stubby fingers. Cropping the detail and acquiring it alone restores that structure (see
docs/WORKFLOW_PLAYBOOK.md, "Detail acquisition"). The crop is a derived image: this script writes a
lineage JSON beside it binding the box, the upscaler and the source hash.

Runs under a Python that has torch and spandrel (the ComfyUI embedded Python on this workstation).

Usage:
  python scripts/detail_crop.py <reference.png> <out.png> --box X0 Y0 X1 Y1 \
      [--model RealESRGAN_x4.pth] [--margin 0.15] [--mirror]

The box is in reference pixels; it is squared about its centre, grown by the margin, and padded with
white where it leaves the picture. --mirror flips the result left-right (to acquire the other hand).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("reference", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--box", type=int, nargs=4, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--model", type=Path, default=Path(r"C:\Comfy\ComfyUI\models\upscale_models\RealESRGAN_x4.pth"))
    ap.add_argument("--margin", type=float, default=0.15)
    ap.add_argument("--mirror", action="store_true")
    args = ap.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite: {args.output}")
    im = Image.open(args.reference).convert("RGB")
    x0, y0, x1, y1 = args.box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = int(round(max(x1 - x0, y1 - y0) * (1 + 2 * args.margin)))
    sq = (int(round(cx - side / 2)), int(round(cy - side / 2)))
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    src = (max(0, sq[0]), max(0, sq[1]), min(im.width, sq[0] + side), min(im.height, sq[1] + side))
    canvas.paste(im.crop(src), (src[0] - sq[0], src[1] - sq[1]))
    if args.mirror:
        canvas = ImageOps.mirror(canvas)
    import torch
    import spandrel
    model = spandrel.ModelLoader().load_from_file(str(args.model)).eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    x = torch.from_numpy(np.asarray(canvas).astype(np.float32) / 255).permute(2, 0, 1)[None].to(device)
    with torch.no_grad():
        y = model(x).clamp(0, 1)
    up = Image.fromarray((y[0].permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    up.save(args.output)
    lineage = {
        "schema": "reference-asset-compiler.detail-crop.v1",
        "source": str(args.reference.resolve()), "source_sha256": sha256(args.reference),
        "box": args.box, "square": [sq[0], sq[1], sq[0] + side, sq[1] + side], "margin": args.margin,
        "mirror": args.mirror, "upscaler": args.model.name, "upscaler_sha256": sha256(args.model),
        "output": str(args.output.resolve()), "output_sha256": sha256(args.output), "size": list(up.size),
    }
    args.output.with_suffix(".lineage.json").write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    print("DETAIL_CROP_OK", args.output, up.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
