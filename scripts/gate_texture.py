"""Texture quality gate. Turns "the texture isn't great" into numbers.

Four measurements, each aimed at a failure this project has actually shipped:

  baked lighting   The brief's rule is that albedo contains no directional
                   shadow. Fit the light direction that best explains the
                   albedo's luminance from surface normals alone. A real
                   albedo has no such direction; a back-projected one does,
                   and the correlation says how badly.

  contamination    Advisory only. Measures how much clothed surface is
                   chromatically close to the character's own skin. It flags
                   the "eye stamped on a trouser leg" defect, but it cannot
                   distinguish that from a character who simply wears
                   earth-toned clothing -- the fox mascot reads 34% purely
                   because orange fur resembles an orange face. Reported as a
                   number to watch, never as a pass/fail.

  texel density    Texels per square centimetre. Both the floor and the
                   spread matter: an atlas that is uniformly too coarse gives
                   a soft character everywhere, and an uneven one gives a
                   sharp face on a blurry arm.

  fragmentation    UV island count and median island area. A confetti atlas
                   puts a seam through every few centimetres of surface, and
                   no amount of inpainting fixes that.

Thresholds come from the profile so a stylised mascot and a hero humanoid can
be held to different standards. Exits 1 on failure unless a waiver is present.

Usage:
  python scripts/gate_texture.py <uv_regions.npz> <atlas.png> <profile.json> \
      <report.json> [--material-name M_Foo]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def jsonable(value):
    """numpy scalars are not JSON serialisable and leak in from np.round."""
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    raise TypeError(repr(value))


def sample_triangle_colours(rgb, uv, indices):
    """Median colour under each triangle's UV footprint."""
    size = rgb.shape[0]
    px = uv.copy()
    px[..., 0] = np.clip(px[..., 0], 0.0, 1.0) * (size - 1)
    px[..., 1] = (1.0 - np.clip(px[..., 1], 0.0, 1.0)) * (size - 1)

    out = np.full((len(indices), 3), np.nan)
    for slot, tri_index in enumerate(indices):
        tri = px[tri_index]
        x0 = max(int(np.floor(tri[:, 0].min())), 0)
        x1 = min(int(np.ceil(tri[:, 0].max())), size - 1)
        y0 = max(int(np.floor(tri[:, 1].min())), 0)
        y1 = min(int(np.ceil(tri[:, 1].max())), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        patch = rgb[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3)
        if len(patch):
            out[slot] = np.median(patch, axis=0)
    return out


def fit_baked_light(normals, luma, weights):
    """Best-fit directional light explaining albedo luminance.

    Searches a coarse hemisphere of directions and returns the strongest
    weighted correlation between luminance and max(0, n . L). A clean albedo
    has no direction that explains its brightness; a lit one does.
    """
    best = {"correlation": 0.0, "direction": None}
    lum = luma - np.average(luma, weights=weights)
    lum_var = np.sqrt(np.average(lum * lum, weights=weights))
    if lum_var < 1e-6:
        return best

    for theta in np.linspace(0.0, np.pi, 13):
        for phi in np.linspace(0.0, 2.0 * np.pi, 25, endpoint=False):
            direction = np.array([
                np.sin(theta) * np.cos(phi),
                np.sin(theta) * np.sin(phi),
                np.cos(theta),
            ])
            lambert = np.maximum(normals @ direction, 0.0)
            centred = lambert - np.average(lambert, weights=weights)
            var = np.sqrt(np.average(centred * centred, weights=weights))
            if var < 1e-6:
                continue
            corr = np.average(lum * centred, weights=weights) / (lum_var * var)
            if abs(corr) > abs(best["correlation"]):
                best = {
                    "correlation": float(corr),
                    "direction": [round(float(v), 3) for v in direction],
                }
    return best


def uv_islands(uv, indices, size=1024):
    """Island count and area distribution, rasterised coarsely."""
    mask = np.zeros((size, size), dtype=bool)
    px = uv.copy()
    px[..., 0] = np.clip(px[..., 0], 0.0, 1.0) * (size - 1)
    px[..., 1] = (1.0 - np.clip(px[..., 1], 0.0, 1.0)) * (size - 1)
    for tri_index in indices:
        tri = px[tri_index]
        x0 = max(int(np.floor(tri[:, 0].min())), 0)
        x1 = min(int(np.ceil(tri[:, 0].max())), size - 1)
        y0 = max(int(np.floor(tri[:, 1].min())), 0)
        y1 = min(int(np.ceil(tri[:, 1].max())), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        mask[y0:y1 + 1, x0:x1 + 1] = True
    labels, count = ndimage.label(mask)
    if not count:
        return {"islands": 0, "coverage_pct": 0.0}
    areas = np.bincount(labels.ravel())[1:]
    return {
        "islands": int(count),
        "coverage_pct": round(100.0 * mask.sum() / (size * size), 1),
        "median_island_px": int(np.median(areas)),
        "largest_island_px": int(areas.max()),
        "islands_under_64px": int((areas < 64).sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("regions_npz", type=Path)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--material-name")
    args = parser.parse_args()

    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    limits = profile.get("texture_limits", {})
    rgb = np.asarray(Image.open(args.atlas).convert("RGB")).astype(np.float64)

    npz = np.load(args.regions_npz, allow_pickle=False)
    names = [str(n) for n in npz["region_names"]]
    material_names = [str(n) for n in npz["material_names"]]
    uv = npz["uv"]
    region = npz["region"].astype(np.int16)
    normal = npz["normal"]
    area = npz["area"]
    material = npz["material"].astype(np.int32)

    if args.material_name and args.material_name in material_names:
        keep = material == material_names.index(args.material_name)
    else:
        keep = np.ones(len(uv), dtype=bool)
    indices = np.flatnonzero(keep)

    colours = sample_triangle_colours(rgb, uv, indices)
    finite = ~np.isnan(colours).any(axis=1)
    indices = indices[finite]
    colours = colours[finite]
    luma = colours @ np.array([0.2126, 0.7152, 0.0722])

    failures = []
    warnings = []
    report = {
        "atlas": str(args.atlas),
        "material": args.material_name,
        "atlas_size": int(rgb.shape[0]),
        "triangles_sampled": int(len(indices)),
    }

    # --- baked lighting -----------------------------------------------------
    light = fit_baked_light(normal[indices], luma, area[indices])
    report["baked_lighting"] = light
    limit = limits.get("max_baked_light_correlation")
    if limit is not None and abs(light["correlation"]) > limit:
        failures.append(
            "baked lighting: albedo luminance correlates {0:+.2f} with a "
            "directional light from {1}; limit is {2:.2f}. A delight pass was "
            "skipped.".format(light["correlation"], light["direction"], limit)
        )

    # --- skin on clothed geometry -------------------------------------------
    # Hands are deliberately absent from the clothed set: they are legitimately
    # bare skin, and including them is what made an earlier version erode them.
    head_ids = [names.index("head")]
    clothed_ids = [names.index(r) for r in ("leg", "torso", "arm") if r in names]

    head_sel = np.isin(region[indices], head_ids)
    skin_ref = colours[head_sel]
    contamination = None
    if len(skin_ref) > 100:
        total = skin_ref.sum(axis=1, keepdims=True)
        total[total < 1e-6] = 1e-6
        ref_chroma = skin_ref / total
        ref_luma = skin_ref.mean(axis=1)
        warm = (
            (ref_chroma[:, 0] > ref_chroma[:, 1])
            & (ref_chroma[:, 1] > ref_chroma[:, 2])
            & (ref_luma > 70)
        )
        if warm.sum() > 50:
            mean = ref_chroma[warm].mean(axis=0)
            inv_cov = np.linalg.inv(np.cov(ref_chroma[warm].T) + np.eye(3) * 1e-6)
            skin_luma = ref_luma[warm].mean()

            clothed_sel = np.isin(region[indices], clothed_ids)
            if clothed_sel.sum():
                sub = colours[clothed_sel]
                sub_total = sub.sum(axis=1, keepdims=True)
                sub_total[sub_total < 1e-6] = 1e-6
                delta = sub / sub_total - mean
                distance = np.sqrt(np.einsum("ij,jk,ik->i", delta, inv_cov, delta))
                hit = (distance < 2.5) & (sub.mean(axis=1) > skin_luma * 0.55)
                weights = area[indices][clothed_sel]
                contamination = float(
                    weights[hit].sum() / max(weights.sum(), 1e-9)
                )
    # Advisory only -- see the module docstring for why this cannot gate.
    report["skin_chroma_on_clothed_fraction_advisory"] = (
        round(contamination, 5) if contamination is not None else None
    )

    # --- texel density ------------------------------------------------------
    size = rgb.shape[0]
    density = {}
    for name in names:
        sel = region[indices] == names.index(name)
        if sel.sum() < 20:
            continue
        uv_area = 0.0
        for tri_index in indices[sel]:
            tri = uv[tri_index]
            uv_area += abs(
                (tri[1, 0] - tri[0, 0]) * (tri[2, 1] - tri[0, 1])
                - (tri[2, 0] - tri[0, 0]) * (tri[1, 1] - tri[0, 1])
            ) * 0.5
        world_area = float(area[indices][sel].sum())
        if world_area > 1e-9:
            # texels per cm^2
            density[name] = round(float(uv_area) * size * size / (world_area * 10000.0), 1)
    report["texel_density_per_cm2"] = density
    if density:
        floor = limits.get("min_texel_density_per_cm2")
        lowest = min(density.values())
        report["texel_density_min"] = lowest
        if floor is not None and lowest < floor:
            failures.append(
                "texel density: {0} texels/cm2 on '{1}' is below the {2} floor. "
                "The atlas is too coarse for this subject's surface area; a "
                "larger atlas or a smaller character is needed.".format(
                    lowest, min(density, key=density.get), floor)
            )
    if len(density) >= 2:
        ratio = max(density.values()) / max(min(density.values()), 1e-6)
        report["texel_density_ratio"] = round(ratio, 2)
        limit = limits.get("max_texel_density_ratio")
        if limit is not None and ratio > limit:
            worst = min(density, key=density.get)
            best = max(density, key=density.get)
            warnings.append(
                "texel density: {0} has {1:.1f}x the density of {2} "
                "({3} vs {4} texels/cm2); limit is {5:.1f}x".format(
                    best, ratio, worst, density[best], density[worst], limit)
            )

    # --- fragmentation ------------------------------------------------------
    islands = uv_islands(uv, indices)
    report["uv_islands"] = islands
    limit = limits.get("max_uv_islands")
    if limit is not None and islands.get("islands", 0) > limit:
        warnings.append(
            "fragmentation: {0} UV islands; limit is {1}. Every island edge is "
            "a seam and a bleed boundary.".format(islands["islands"], limit)
        )

    waiver = profile.get("texture_waiver")
    if failures and waiver and waiver.get("reason") and waiver.get("approved_by"):
        for f in failures:
            warnings.append("WAIVED by {0}: {1}".format(waiver["approved_by"], f))
        report["texture_waived"] = True
        failures = []

    report["failures"] = failures
    report["warnings"] = warnings
    report["ok"] = not failures
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, default=jsonable), encoding="utf-8")

    for w in warnings:
        print("[GATE TEX] WARN  {0}".format(w))
    if failures:
        print("[GATE TEX] FAILED {0}:".format(args.atlas.name))
        for f in failures:
            print("  - {0}".format(f))
        return 1
    print(
        "[GATE TEX] Passed {0}. baked-light corr {1:+.2f}, skin-on-clothed "
        "{2}, {3} islands.".format(
            args.atlas.name,
            light["correlation"],
            ("{0:.2%} (advisory)".format(contamination)
             if contamination is not None else "n/a"),
            islands.get("islands", 0),
        )
    )
    print("[GATE TEX]   texel density {0} texels/cm2 (min across regions)".format(
        report.get("texel_density_min")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
