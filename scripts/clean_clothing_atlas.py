"""Remove facial art that was painted onto clothed geometry in a body atlas.

Why this is safe, which earlier attempts were not:

The decals share UV coordinates with the character's real face, so for a while
it looked like painting them out would delete her eyes. It would not. The face
triangles that share those coordinates belong to a *different material* and
therefore sample a *different texture*. Only the clothed triangles read the
body atlas at those texels.

So the repair operates on exactly one set of texels: those covered by
triangles that are (a) in this material, and (b) on clothed geometry. Nothing
else in the atlas is touched, and no face, hand or head texel is reachable by
construction. Hands are excluded because they are legitimately bare skin, and
excluding them is what stopped an earlier version from eroding them.

Usage:
  python scripts/clean_clothing_atlas.py <atlas.png> <uv_regions.npz> <out.png> \
      --material M_Foo_Body [--regions leg,torso,foot] [--report r.json] \
      [--preview-dir dir]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree


def rasterise(px, indices, size, out=None):
    """Barycentric coverage mask for the given triangles."""
    mask = np.zeros((size, size), dtype=bool) if out is None else out
    for tri_index in indices:
        tri = px[tri_index]
        x0 = max(int(np.floor(tri[:, 0].min())), 0)
        x1 = min(int(np.ceil(tri[:, 0].max())), size - 1)
        y0 = max(int(np.floor(tri[:, 1].min())), 0)
        y1 = min(int(np.ceil(tri[:, 1].max())), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        (ax, ay), (bx, by), (cx, cy) = tri
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        inside = (l1 >= -0.003) & (l2 >= -0.003) & (1 - l1 - l2 >= -0.003)
        if inside.any():
            mask[ys[inside], xs[inside]] = True
    return mask


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("atlas", type=Path)
    parser.add_argument("regions_npz", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--material", required=True)
    parser.add_argument(
        "--regions", default="leg,torso,foot",
        help="Clothed regions to clean. 'hand' and 'head' are never included: "
             "they are legitimately skin.")
    parser.add_argument("--grow", type=int, default=3)
    parser.add_argument(
        "--tri-threshold", type=float, default=0.5,
        help="Fraction of a triangle's texels that must read as decal "
             "colour before the triangle is flagged.")
    parser.add_argument("--max-region-frac", type=float, default=0.10)
    parser.add_argument(
        "--cream-radius-m", type=float, default=0.04,
        help="How close in 3D a cream triangle must be to a flagged one "
             "before it is treated as part of the same decal.")
    parser.add_argument(
        "--max-blob-frac", type=float, default=0.02,
        help="Reject a blob larger than this fraction of the cleaned surface; "
             "that is a design feature, not a stray decal.")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()

    image = Image.open(args.atlas).convert("RGB")
    rgb = np.asarray(image).astype(np.int16)
    size = rgb.shape[0]

    npz = np.load(args.regions_npz, allow_pickle=False)
    names = [str(n) for n in npz["region_names"]]
    materials = [str(n) for n in npz["material_names"]]
    uv = npz["uv"]
    region = npz["region"].astype(np.int16)
    centre = npz["centre"]
    material = npz["material"].astype(np.int32)

    report = {
        "atlas": str(args.atlas),
        "material": args.material,
        "regions": args.regions,
        "blobs_removed": 0,
        "texels_removed": 0,
    }
    if args.material not in materials:
        report["skipped"] = "material not present in this mesh"
        print("[CLEAN] {0}: material {1} not present".format(
            args.atlas.name, args.material))
        image.save(args.out)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    px = uv.copy()
    px[..., 0] = np.clip(px[..., 0], 0.0, 1.0) * (size - 1)
    px[..., 1] = (1.0 - np.clip(px[..., 1], 0.0, 1.0)) * (size - 1)

    mine = material == materials.index(args.material)
    wanted = [names.index(r) for r in args.regions.split(",") if r in names]
    clothed = np.flatnonzero(mine & np.isin(region, wanted))
    if not len(clothed):
        report["skipped"] = "no clothed triangles for this material"
        image.save(args.out)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    clothed_mask = rasterise(px, clothed, size)
    report["clothed_texels"] = int(clothed_mask.sum())

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Flat salmon skin and cartoon iris blue. Neither belongs on a trouser leg.
    salmon = (r > 125) & (r < 228) & (g > 78) & (g < 178) & (b > 62) & (b < 168) & (r > g + 22)
    iris = (b > 130) & (b > r + 35) & (b > g + 15) & (g > 80)
    cream = (r > 190) & (g > 180) & (b > 155) & (abs(r - g) < 32)
    decal_colour = salmon | iris
    decal_or_cream = decal_colour | cream

    # Classify per TRIANGLE, not by growing through the image.
    #
    # Growing through pixels does not work on this atlas: islands that touch
    # in UV space come from completely different parts of the body, so a fill
    # started on a thigh decal escapes into the shirt island next to it and
    # takes bites out of the shirt. A triangle either is or is not painted
    # skin-coloured, and that question has an answer independent of whatever
    # happens to be packed beside it.
    max_blob = args.max_blob_frac * clothed_mask.sum()
    remove = np.zeros((size, size), dtype=bool)
    kept = []
    flagged = 0

    def coverage(tri_index, mask):
        tri = px[tri_index]
        x0 = max(int(np.floor(tri[:, 0].min())), 0)
        x1 = min(int(np.ceil(tri[:, 0].max())), size - 1)
        y0 = max(int(np.floor(tri[:, 1].min())), 0)
        y1 = min(int(np.ceil(tri[:, 1].max())), size - 1)
        if x1 < x0 or y1 < y0:
            return None, None
        patch = mask[y0:y1 + 1, x0:x1 + 1]
        if patch.size == 0:
            return None, None
        return patch.mean(), (y0, y1, x0, x1)

    seeds = []
    for tri_index in clothed:
        frac, box = coverage(tri_index, decal_colour)
        if frac is not None and frac >= args.tri_threshold:
            seeds.append(tri_index)

    selected = list(seeds)

    # The sclera is cream, and so is the shirt. Cream can only join the removal
    # if it sits within a few centimetres IN 3D of a triangle already flagged.
    # Proximity in the atlas means nothing here -- the shirt is packed right
    # beside the thigh -- but proximity on the body is exactly the right test.
    if seeds and args.cream_radius_m > 0:
        seed_points = centre[np.asarray(seeds)]
        tree = cKDTree(seed_points)
        for tri_index in clothed:
            if tri_index in set(seeds):
                continue
            frac, box = coverage(tri_index, cream)
            if frac is None or frac < args.tri_threshold:
                continue
            if tree.query(centre[tri_index], k=1)[0] <= args.cream_radius_m:
                selected.append(tri_index)

    for tri_index in selected:
        frac, box = coverage(tri_index, decal_or_cream)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        remove[y0:y1 + 1, x0:x1 + 1] |= decal_or_cream[y0:y1 + 1, x0:x1 + 1]
        flagged += 1

    report["triangles_flagged"] = flagged
    report["clothed_triangles"] = int(len(clothed))
    fraction = flagged / max(len(clothed), 1)
    report["flagged_fraction"] = round(fraction, 5)

    if fraction > args.max_region_frac:
        report["skipped"] = (
            "{0:.1%} of clothed triangles read as skin, which is a character "
            "wearing skin tones rather than a stray decal".format(fraction)
        )
        print("[CLEAN] {0}: skipped -- {1}".format(args.atlas.name, report["skipped"]))
        image.save(args.out)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    labels, count = ndimage.label(remove)
    filtered = np.zeros_like(remove)
    for index in range(1, count + 1):
        blob = labels == index
        area = int(blob.sum())
        if area < 24 or area > max_blob:
            continue
        filtered |= ndimage.binary_fill_holes(blob)
        kept.append(area)
    remove = filtered

    if not kept:
        report["skipped"] = "no decal-coloured blobs on clothed geometry"
        print("[CLEAN] {0}: nothing to remove".format(args.atlas.name))
        image.save(args.out)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    # Grow slightly to catch the antialiased skirt, but never outside the
    # clothed texels -- that containment is the whole safety argument.
    remove = ndimage.binary_dilation(remove, iterations=args.grow) & clothed_mask

    result = np.asarray(image).copy()
    source = clothed_mask & ~remove
    if source.any():
        indices = ndimage.distance_transform_edt(
            ~source, return_distances=False, return_indices=True
        )
        result[remove] = result[tuple(indices)][remove]
        soft = ndimage.uniform_filter(result.astype(np.float32), size=(7, 7, 1))
        result[remove] = soft[remove].astype(np.uint8)

    report["blobs_removed"] = len(kept)
    report["texels_removed"] = int(remove.sum())
    report["largest_blob_texels"] = int(max(kept))
    Image.fromarray(result).save(args.out)
    print("[CLEAN] {0}: removed {1} blob(s), {2} texels from {3} clothed texels".format(
        args.atlas.name, len(kept), int(remove.sum()), int(clothed_mask.sum())))

    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        ys, xs = np.where(remove)
        if len(ys):
            pad = 140
            x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, size - 1)
            y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, size - 1)
            before = image.crop((x0, y0, x1, y1))
            after = Image.fromarray(result).crop((x0, y0, x1, y1))
            pair = Image.new("RGB", (before.width * 2 + 8, before.height), (30, 30, 30))
            pair.paste(before, (0, 0))
            pair.paste(after, (before.width + 8, 0))
            pair.save(args.preview_dir / "clean-before-after.png")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
