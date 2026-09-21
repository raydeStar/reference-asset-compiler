"""Crop a reference image to the head band of the figure in it.

Run with the painter's own interpreter, which is where the background remover
lives. The figure's silhouette decides the crop, not the picture's frame: a
reference with air above the head or a floor below the feet would otherwise put
the head band in the wrong place. The crop is written with its alpha, so the
painter composites it on white the way it does any cutout, and nothing from
the backdrop reaches the paint.

Usage:
  <venv-hy3d21>\\python.exe scripts/crop_reference_region.py <reference> <crop.png> <crop.json>
      [--head-from 0.78] [--margin 0.06]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paint_head_detail import head_crop_box  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("crop", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--head-from", type=float, default=0.78)
    parser.add_argument("--margin", type=float, default=0.06)
    args = parser.parse_args(argv)

    image = Image.open(args.reference)
    image.load()
    if image.mode == "RGBA" and (np.asarray(image.getchannel("A")) < 250).mean() > 0.001:
        cutout = image
        removed = False
    else:
        from rembg import new_session, remove  # noqa: PLC0415 -- only where it exists
        cutout = remove(image.convert("RGB"), session=new_session("u2net"))
        removed = True
    alpha = np.asarray(cutout.getchannel("A"))
    box = head_crop_box(alpha, args.head_from, args.margin)
    if box is None:
        print("[CROP] FAILED: no figure was found in the reference")
        return 1
    # Clamped to the picture by padding rather than by shrinking, so the crop
    # stays square and the head stays where the square puts it.
    left, top, right, bottom = box
    side = right - left
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cutout, (-left, -top))
    canvas.save(args.crop, format="PNG")
    report = {
        "schema": "reference-asset-compiler.reference-crop.v1",
        "reference": str(args.reference),
        "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        "reference_size": list(image.size),
        "background_removed_here": removed,
        "figure_rows": [int(np.where(alpha.max(axis=1) > 16)[0][0]), int(np.where(alpha.max(axis=1) > 16)[0][-1]) + 1],
        "head_from": args.head_from,
        "margin": args.margin,
        "box": [left, top, right, bottom],
        "crop_size": side,
        "crop": str(args.crop),
        "crop_sha256": hashlib.sha256(args.crop.read_bytes()).hexdigest(),
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[CROP] {0} -> {1} square at {2}".format(image.size, side, box))
    return 0


if __name__ == "__main__":
    sys.exit(main())
