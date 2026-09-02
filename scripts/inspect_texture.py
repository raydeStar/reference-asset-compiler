"""Downscale a texture for review and report its statistics.

Full-size atlases are too large to look at directly, and "the texture looks
wrong in engine" is usually answerable from the atlas itself: an albedo that
is nearly white will render as a blown-out white character no matter what the
material does.

Usage:
  python scripts/inspect_texture.py <image.png> [out.png] [--size 1024]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def describe(path: Path, out_path: Path | None, size: int) -> None:
    with Image.open(path) as image:
        original_mode = image.mode
        original_size = image.size
        rgb = image.convert("RGB")

        small = rgb.copy()
        small.thumbnail((size, size), Image.LANCZOS)
        if out_path is not None:
            small.save(out_path)

        pixels = list(small.getdata())
        count = len(pixels)
        avg = [sum(p[i] for p in pixels) / count for i in range(3)]
        luma = [0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in pixels]
        luma_sorted = sorted(luma)

        # An atlas is mostly empty padding; ignore near-black to judge the art.
        lit = [v for v in luma if v > 8.0]
        near_white = sum(1 for v in luma if v > 235.0)
        saturation = [max(p) - min(p) for p in pixels]

        print("file           : {0}".format(path.name))
        print("size / mode    : {0} {1}".format(original_size, original_mode))
        print("mean RGB       : {0:.1f}, {1:.1f}, {2:.1f}".format(*avg))
        print("luma p05/50/95 : {0:.0f} / {1:.0f} / {2:.0f}".format(
            luma_sorted[int(count * 0.05)],
            luma_sorted[int(count * 0.50)],
            luma_sorted[int(count * 0.95)],
        ))
        print("mean luma (lit): {0:.1f}  over {1:.0f}% of pixels".format(
            (sum(lit) / len(lit)) if lit else 0.0, 100.0 * len(lit) / count))
        print("near-white     : {0:.1f}% of pixels above 235".format(
            100.0 * near_white / count))
        print("mean saturation: {0:.1f} (0 = greyscale)".format(
            sum(saturation) / count))
        if out_path is not None:
            print("preview        : {0}".format(out_path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("out", type=Path, nargs="?")
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()
    describe(args.image, args.out, args.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
