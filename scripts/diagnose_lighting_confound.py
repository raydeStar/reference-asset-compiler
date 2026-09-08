"""Read-only falsification and covariance decomposition of the lighting heuristic.

This neither changes an atlas nor overrides a gate. Chromaticity strata are
diagnostic proxies, not ground-truth material labels or replacement acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from gate_texture import fit_baked_light, sample_triangle_colours


def split_covariance(x, y, weights, groups):
    weights = weights / weights.sum()
    mx, my = np.sum(weights * x), np.sum(weights * y)
    total = np.sum(weights * (x - mx) * (y - my))
    within, between, rows = 0., 0., []
    for group in np.unique(groups):
        keep = groups == group
        mass = weights[keep].sum()
        gx = np.average(x[keep], weights=weights[keep])
        gy = np.average(y[keep], weights=weights[keep])
        wc = np.sum(weights[keep] * (x[keep] - gx) * (y[keep] - gy))
        bc = mass * (gx - mx) * (gy - my)
        within += wc
        between += bc
        rows.append({"group": int(group), "triangles": int(keep.sum()),
                     "area_fraction": float(mass), "mean_luma": float(gx),
                     "mean_lambert": float(gy), "within_covariance": float(wc),
                     "between_covariance": float(bc)})
    return {"total_covariance": float(total), "within_covariance": float(within),
            "between_covariance": float(between),
            "decomposition_absolute_error": float(abs(total - within - between)),
            "groups": sorted(rows, key=lambda row: -row["area_fraction"])}


def chromaticity_groups(rgb):
    srgb = rgb / 255.
    linear = np.where(srgb <= .04045, srgb / 12.92, ((srgb + .055) / 1.055) ** 2.4)
    chroma = linear / np.maximum(linear.sum(axis=1, keepdims=True), 1e-8)
    bins = np.floor(chroma[:, :2] / .1).astype(int)
    return bins[:, 0] * 11 + bins[:, 1]


def controls():
    normals = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
    # Six independently painted, constant-reflectance cube faces. No lights.
    clean_luma = np.array([30, 30, 30, 30, 160, 5], float)
    clean = fit_baked_light(normals, clean_luma, np.ones(6))
    rng = np.random.default_rng(823)
    sphere = rng.normal(size=(2000, 3))
    sphere /= np.linalg.norm(sphere, axis=1, keepdims=True)
    shaded_luma = 30 + 100 * np.maximum(sphere[:, 2], 0)
    shaded = fit_baked_light(sphere, shaded_luma, np.ones(len(sphere)))
    return {"unlit_multicolor_cube": clean, "single_material_lambertian_positive_control": shaded,
            "interpretation": "The cube contains no illumination but can correlate with normals by design. This does not prove the real asset is de-lit."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve previous lighting diagnostics")
    payload = json.loads((args.package / "retopo.json").read_text())
    atlas = args.package / payload["baked"]["BaseColor"]
    regions = args.package / "uv-regions.npz"
    data = np.load(regions)
    rgb = np.asarray(Image.open(atlas).convert("RGB"), dtype=float)
    colours = sample_triangle_colours(rgb, data["uv"], np.arange(len(data["uv"])))
    finite = np.isfinite(colours).all(axis=1) & (data["area"] > 0)
    colours, area, normals = colours[finite], data["area"][finite], data["normal"][finite]
    luma = colours @ np.array([.2126, .7152, .0722])
    light = fit_baked_light(normals, luma, area)
    direction = np.asarray(light["direction"], float)
    lambert = np.maximum(normals @ direction, 0)
    z = data["centre"][finite, 2]
    height_bin = np.minimum(((z - z.min()) / (z.max() - z.min()) * 10).astype(int), 9)
    result = {"schema": "reference-asset-compiler.lighting-confound-diagnostic.v1",
              "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (atlas, regions)},
              "controls": controls(), "measured_gate_direction": light,
              "chromaticity_partition": split_covariance(luma, lambert, area, chromaticity_groups(colours)),
              "height_deciles_partition": split_covariance(luma, lambert, area, height_bin),
              "partition_policy": "Fixed 0.1 linear-RGB chromaticity bins, no luminance clustering; height deciles are a separate diagnostic.",
              "gate_override": False, "geometry_or_texture_changed": False,
              "production_ready": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("controls", "measured_gate_direction")}, indent=2))
    for key in ("chromaticity_partition", "height_deciles_partition"):
        print(key, {k: v for k, v in result[key].items() if k != "groups"})


if __name__ == "__main__":
    main()
