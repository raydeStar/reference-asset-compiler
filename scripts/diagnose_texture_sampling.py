"""Read-only comparison of legacy bounding-box and surface-only texture samples."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from gate_texture import sample_triangle_colours, fit_baked_light
from repair_workshop_interiors import triangle_pixels


def surface_colours(rgb, uv):
    colors = []
    fallback = 0
    for triangle in uv:
        pixels = triangle_pixels(triangle, rgb.shape[0])
        if pixels is not None and len(pixels[0]):
            yy, xx, _weights = pixels
            colors.append(np.median(rgb[yy, xx], axis=0))
        else:
            fallback += 1
            center = triangle.mean(axis=0)
            x, y = center[0] * rgb.shape[1] - .5, (1 - center[1]) * rgb.shape[0] - .5
            colors.append([ndimage.map_coordinates(rgb[..., c], [[y], [x]], order=1,
                                                    mode="nearest")[0] for c in range(3)])
    return np.asarray(colors), fallback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Retain prior diagnostics")
    payload = json.loads((args.package / "retopo.json").read_text())
    atlas = args.package / payload["baked"]["BaseColor"]
    data_path = args.package / "uv-regions.npz"
    data = np.load(data_path)
    rgb = np.asarray(Image.open(atlas).convert("RGB")).astype(float)
    old = sample_triangle_colours(rgb, data["uv"], np.arange(len(data["uv"])))
    new, fallback = surface_colours(rgb, data["uv"])
    luma = np.array([.2126, .7152, .0722])
    result = {"schema": "reference-asset-compiler.texture-sampling-diagnostic.v1",
              "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (atlas, data_path)},
              "bounds_sampling": fit_baked_light(data["normal"], old @ luma, data["area"]),
              "surface_sampling": fit_baked_light(data["normal"], new @ luma, data["area"]),
              "median_rgb_absolute_delta": float(np.median(np.abs(old-new))),
              "subpixel_centroid_fallback_triangles": fallback,
              "geometry_or_texture_changed": False, "gate_override": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
