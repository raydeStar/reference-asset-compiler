"""Whether a derivative still looks like what it was derived from.

A reduction is measured by how far its surface moved, and for shape that is the
right measure. It cannot see paint. A floor brazier reduced from 120k triangles
stayed within millimetres of its original at every rung and still lost its iron
bands and rivets, because the paint slid with the UVs; surface deviation was
fine, the asset was not.

So the derivative is judged the way a person would judge it: the same fixed
views of both, through the same cameras, compared picture by picture. The
comparison is structural similarity (SSIM) over the asset only -- the
background is excluded, or a small object on a large grey field would score
well whatever was painted on it -- in two passes:

- **beauty**, lit: what somebody sees, with relief, shading and paint together;
- **albedo**, unlit base colour: where the paint is. Lighting can soften a
  smear in the beauty pass; it cannot here.

Every view must pass, not their average, because a good front cannot excuse a
broken side. The silhouettes must also agree, which is what catches a part
that went missing rather than a colour that slid.

The thresholds are below, with the measurements that chose them. They are
deliberately a little stricter than what a faithful re-bake scores, because the
owner's standard for these props is that they must not get worse.

Nothing here imports Blender: the pictures are rendered elsewhere
(``scripts/blender/render_appearance_views.py``) and compared here, so the
judgement can be tested, read and argued with on any machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

SCHEMA = "reference-asset-compiler.appearance-gate.v1"
VIEWS_SCHEMA = "reference-asset-compiler.appearance-views.v1"

# Calibrated on the floor brazier, 2026-10-04 (docs/COMPILER.md, "Re-baking a
# reduced painted prop"), worst view of four, 512 px, 32 samples:
#
#                          beauty  albedo
#   .blend vs delivered GLB  1.000   1.000   the same asset: renders are deterministic
#   smeared, any rung       <=0.80  <=0.933  reduced 5k-16.8k without a re-bake
#   re-baked 16.8k           0.956   0.977   indistinguishable by eye
#   re-baked 15k             0.952   0.974   where the surface gates also settled
#   re-baked 11.2k           0.935   0.965   soft bowl shading
#   re-baked 7.5k            0.912   0.947   faceted rim, softer bands
#   re-baked 5k              0.872   0.918   a strap kinked and cracked
#
# So no smear passes, and a re-bake passes only where nobody could tell it
# from the original -- the owner's standard for these props is "must not get
# worse", not "close enough".
#
# A view's mean can hide one bad spot, so the worst 16 px patch on the asset is
# held to a floor as well. Silhouette edges keep it well below 1 even for a
# faithful re-bake (0.455 lit, 0.567 unlit at worst across nine accepted pilot
# props); a crack or a kink drags it far lower (brazier 7.5k: 0.21 / 0.35;
# 5k: -0.03 / 0.27).
THRESHOLDS: dict[str, Any] = {
    "beauty": {"minimum_ssim": 0.94, "minimum_worst_patch_ssim": 0.35},
    "albedo": {"minimum_ssim": 0.96, "minimum_worst_patch_ssim": 0.45},
    "minimum_silhouette_iou": 0.97,
}
PATCH = 16

BACKGROUND = 0.5
SSIM_SIGMA = 1.5
SSIM_K1, SSIM_K2 = 0.01, 0.03


class AppearanceError(ValueError):
    """Two sets of views that cannot honestly be compared."""


def load_view(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """An RGBA render as (RGB composited on neutral grey, alpha), both 0..1."""
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float64) / 255.0
    alpha = rgba[..., 3]
    rgb = rgba[..., :3] * alpha[..., None] + BACKGROUND * (1.0 - alpha[..., None])
    return rgb, alpha


def luma(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def ssim_map(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Per-pixel structural similarity of two single-channel images in 0..1."""
    if first.shape != second.shape:
        raise AppearanceError("Images of different sizes cannot be compared: {0} and {1}".format(
            first.shape, second.shape))
    c1, c2 = (SSIM_K1 ** 2), (SSIM_K2 ** 2)

    def blur(values):
        return ndimage.gaussian_filter(values, SSIM_SIGMA, truncate=3.5)

    mean_a, mean_b = blur(first), blur(second)
    var_a = blur(first * first) - mean_a * mean_a
    var_b = blur(second * second) - mean_b * mean_b
    covariance = blur(first * second) - mean_a * mean_b
    return (((2 * mean_a * mean_b + c1) * (2 * covariance + c2))
            / ((mean_a * mean_a + mean_b * mean_b + c1) * (var_a + var_b + c2)))


def worst_patch(similarity: np.ndarray, inside: np.ndarray, size: int = PATCH) -> float:
    """The lowest mean SSIM of any patch that lies mostly on the asset.

    A view's mean can average one crack or kink away; a patch cannot. Patches
    that are mostly background are skipped, or every silhouette edge would be
    the worst patch.
    """
    weight = inside.astype(np.float64)
    total = ndimage.uniform_filter(np.where(inside, similarity, 0.0), size)
    cover = ndimage.uniform_filter(weight, size)
    valid = cover > 0.75
    if not valid.any():
        return float(similarity[inside].mean()) if inside.any() else 1.0
    return float((total[valid] / cover[valid]).min())


def compare_pair(reference: Path, candidate: Path) -> dict[str, float]:
    """How alike one view of the original and the same view of a derivative are."""
    reference_rgb, reference_alpha = load_view(reference)
    candidate_rgb, candidate_alpha = load_view(candidate)
    if reference_rgb.shape != candidate_rgb.shape:
        raise AppearanceError("{0} and {1} are different sizes".format(reference.name,
                                                                       candidate.name))
    inside_reference = reference_alpha > 0.5
    inside_candidate = candidate_alpha > 0.5
    union = inside_reference | inside_candidate
    if not union.any():
        raise AppearanceError("{0} shows nothing to compare".format(reference.name))
    intersection = inside_reference & inside_candidate
    # A little of the background around the asset, so an edge that moved is
    # inside the comparison rather than just outside it.
    region = ndimage.binary_dilation(union, iterations=2)
    full = ssim_map(luma(reference_rgb), luma(candidate_rgb))
    similarity = full[region]
    difference = np.abs(reference_rgb - candidate_rgb)[intersection] if intersection.any() else \
        np.zeros((1, 3))
    return {
        "ssim": round(float(similarity.mean()), 5),
        "ssim_p05": round(float(np.percentile(similarity, 5)), 5),
        "worst_patch_ssim": round(worst_patch(full, union), 5),
        "silhouette_iou": round(float(intersection.sum()) / float(union.sum()), 5),
        "colour_mae_255": round(float(difference.mean()) * 255.0, 3),
        "pixels": int(region.sum()),
    }


def read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != VIEWS_SCHEMA:
        raise AppearanceError("{0} is not an appearance-views manifest".format(path))
    return manifest


def check_comparable(reference: dict[str, Any], candidate: dict[str, Any]) -> None:
    """Refuse a comparison whose pictures were not taken the same way."""
    if reference.get("resolution") != candidate.get("resolution"):
        raise AppearanceError("The views were rendered at different sizes ({0} and {1}).".format(
            reference.get("resolution"), candidate.get("resolution")))
    if reference.get("framing") != candidate.get("framing"):
        raise AppearanceError(
            "The candidate was not rendered through the original's cameras, so the same pixel "
            "is not the same place on the asset in both pictures.")
    for key in ("display", "passes"):
        if reference.get(key) != candidate.get(key):
            raise AppearanceError("The views differ in {0}: {1} against {2}.".format(
                key, reference.get(key), candidate.get(key)))
    for key in ("samples", "seed", "engine"):
        if (reference.get("device") or {}).get(key) != (candidate.get("device") or {}).get(key):
            raise AppearanceError("The views were rendered with different {0}.".format(key))
    wanted = {(item["pass"], item["view"]) for item in reference.get("views", [])}
    have = {(item["pass"], item["view"]) for item in candidate.get("views", [])}
    if wanted != have:
        raise AppearanceError("The candidate is missing views: {0}".format(
            sorted(wanted - have)))


def judge(views: Iterable[dict[str, Any]], thresholds: dict[str, Any] | None = None
          ) -> tuple[bool, list[str]]:
    """The verdict on compared views: every one must pass, not their average."""
    thresholds = thresholds or THRESHOLDS
    failures = []
    for entry in views:
        rule = thresholds.get(entry["pass"], {})
        minimum = rule.get("minimum_ssim")
        if minimum is not None and entry["ssim"] < minimum:
            failures.append("{0} {1}: SSIM {2:.3f} is below {3:.3f}".format(
                entry["pass"], entry["view"], entry["ssim"], minimum))
        patch = rule.get("minimum_worst_patch_ssim")
        if patch is not None and entry.get("worst_patch_ssim") is not None \
                and entry["worst_patch_ssim"] < patch:
            failures.append("{0} {1}: its worst {2} px patch scores {3:.3f}, below {4:.3f} -- "
                            "a local flaw the view's mean hides".format(
                                entry["pass"], entry["view"], PATCH, entry["worst_patch_ssim"],
                                patch))
        iou = thresholds.get("minimum_silhouette_iou")
        if iou is not None and entry["silhouette_iou"] < iou:
            failures.append("{0} {1}: silhouette overlap {2:.3f} is below {3:.3f}".format(
                entry["pass"], entry["view"], entry["silhouette_iou"], iou))
    return not failures, failures


def compare_views(reference_manifest: Path, candidate_manifest: Path,
                  thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare every fixed view of a candidate with the original's, and judge it."""
    thresholds = thresholds or THRESHOLDS
    reference_manifest, candidate_manifest = Path(reference_manifest), Path(candidate_manifest)
    reference = read_manifest(reference_manifest)
    candidate = read_manifest(candidate_manifest)
    check_comparable(reference, candidate)
    candidate_files = {(item["pass"], item["view"]): item["file"] for item in candidate["views"]}
    compared = []
    for item in reference["views"]:
        key = (item["pass"], item["view"])
        scores = compare_pair(reference_manifest.parent / item["file"],
                              candidate_manifest.parent / candidate_files[key])
        compared.append({"pass": item["pass"], "view": item["view"], **scores})
    passed, failures = judge(compared, thresholds)
    by_pass = {}
    for name in sorted({entry["pass"] for entry in compared}):
        scores = [entry["ssim"] for entry in compared if entry["pass"] == name]
        patches = [entry["worst_patch_ssim"] for entry in compared if entry["pass"] == name]
        by_pass[name] = {"minimum_ssim": min(scores), "mean_ssim": round(sum(scores) / len(scores), 5),
                         "worst_patch_ssim": min(patches)}
    return {
        "schema": SCHEMA,
        "passed": passed,
        "failures": failures,
        "thresholds": thresholds,
        "summary": by_pass,
        "views": compared,
        "reference": {"manifest": str(reference_manifest), "source": reference.get("source"),
                      "source_sha256": reference.get("source_sha256")},
        "candidate": {"manifest": str(candidate_manifest), "source": candidate.get("source"),
                      "source_sha256": candidate.get("source_sha256")},
    }


FIXED_VIEWS = ("front", "three-quarter", "side", "back")


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def comparison_sheet(rows: list[tuple[str, str, Path]], pass_name: str, path: Path,
                     views: tuple[str, ...] = FIXED_VIEWS) -> Path:
    """The fixed views of each version in one picture, one row each, for a person.

    ``rows`` holds (label, detail, views directory). The numbers decide whether a
    candidate is offered; a person decides whether it is accepted, and this is
    what they look at.
    """
    strips = []
    for label, detail, directory in rows:
        tiles = []
        for view in views:
            with Image.open(Path(directory) / "{0}-{1}.png".format(pass_name, view)) as image:
                rgba = image.convert("RGBA")
            backdrop = Image.new("RGBA", rgba.size, (118, 118, 122, 255))
            backdrop.alpha_composite(rgba)
            tiles.append(backdrop.convert("RGB"))
        width, height = tiles[0].size
        band = 46
        strip = Image.new("RGB", (width * len(tiles), height + band), (24, 24, 28))
        for index, tile in enumerate(tiles):
            strip.paste(tile, (index * width, band))
        draw = ImageDraw.Draw(strip)
        title = _font(22)
        draw.text((12, 6), label, fill=(255, 255, 255), font=title)
        draw.text((12 + draw.textlength(label, font=title) + 18, 10), detail,
                  fill=(190, 190, 190), font=_font(17))
        strips.append(strip)
    sheet = Image.new("RGB", (strips[0].size[0], sum(strip.size[1] for strip in strips)),
                      (24, 24, 28))
    top = 0
    for strip in strips:
        sheet.paste(strip, (0, top))
        top += strip.size[1]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return path
