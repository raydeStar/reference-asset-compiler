"""Transport an AI face donor through reviewed camera landmarks into bounded UVs.

This is downstream mapping, not a repaint generator. The AI donor is acquired
separately. Its camera drift is corrected in texture space only, and each
changed atlas texel is bound to front-visible head geometry. No mesh or UV
coordinate is changed, and no other material channel is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import Delaunay

from repair_workshop_interiors import triangle_pixels
from projection_visibility import project_surface, depth_visible


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def warp_coordinates(points, target, donor):
    triangulation = Delaunay(target)
    simplex = triangulation.find_simplex(points)
    valid = simplex >= 0
    safe = np.maximum(simplex, 0)
    transforms = triangulation.transform[safe]
    bary = np.einsum("ijk,ik->ij", transforms[:, :2], points - transforms[:, 2])
    weights = np.column_stack((bary, 1 - bary.sum(axis=1)))
    mapped = np.einsum("ij,ijk->ik", weights, donor[triangulation.simplices[safe]])
    return mapped, valid


def pad_face_gutters(result, occupied, support, radius):
    """Extend changed edge colors only into unused atlas space, never a neighbor."""
    distance, nearest = ndimage.distance_transform_edt(~occupied, return_indices=True)
    padding = (~occupied) & (distance <= radius) & support[tuple(nearest)]
    padded = result.copy()
    padded[padding] = result[nearest[0][padding], nearest[1][padding]]
    return padded, padding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    source, donor_path, correspondence = [Path(config[k]).resolve()
                                         for k in ("base_color", "donor_image", "correspondence")]
    for key, path in (("base_color", source), ("donor_image", donor_path), ("correspondence", correspondence)):
        if sha(path) != config["hashes"][key]:
            raise ValueError("Changed input: " + key)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Keep retained face attempts; choose a new output")
    base = np.asarray(Image.open(source).convert("RGB"))
    donor = np.asarray(Image.open(donor_path).convert("RGB"))
    donor_float = donor.astype(float)
    size = base.shape[0]
    if base.shape[:2] != (size, size):
        raise ValueError("Expected square native atlas")
    # Load once: a compressed depth image must not be decoded per triangle.
    with np.load(correspondence) as archive:
        data = {key: archive[key] for key in archive.files}
    depth_only = config.get("depth_visibility_only", False)
    if depth_only and "depth_buffer" not in data:
        raise ValueError("Disabling the normal fade requires per-pixel depth visibility")
    target = np.asarray(config["target_landmarks_1024"], float)
    donor_points = np.asarray(config["donor_landmarks_1024"], float)
    if target.shape != donor_points.shape or target.shape[1:] != (2,):
        raise ValueError("Paired camera landmarks are required")
    # The polygon explicitly follows the head's camera-space skin boundary.
    # It is not a loose image mask that could include clothes at the same UV.
    from PIL import ImageDraw
    region = Image.new("L", (1024, 1024))
    ImageDraw.Draw(region).polygon([tuple(p) for p in config["target_face_boundary_1024"]], fill=255)
    region = np.array(region) > 0
    feather = ndimage.distance_transform_edt(region) / config["boundary_feather_pixels"]
    feather = np.clip(feather, 0, 1)
    result = base.copy()
    alpha_map = np.zeros((size, size), np.float32)
    protected = np.zeros((size, size), bool)
    occupied = np.zeros((size, size), bool)
    for i, uv in enumerate(data["uv"]):
        pixels = triangle_pixels(uv, size)
        if pixels is None:
            continue
        yy, xx, weights = pixels
        occupied[yy, xx] = True
        if not data["eligible"][i]:
            protected[yy, xx] = True
            continue
        screen = weights @ data["screen"][i]
        pixel_visible = np.ones(len(screen), dtype=bool)
        if "depth_buffer" in data:
            screen, depth = project_surface(weights, data["screen"][i], data["depth"][i])
            pixel_visible = depth_visible(screen, depth, data["depth_buffer"],
                                          float(data["depth_tolerance"]))
        mapped, valid = warp_coordinates(screen, target, donor_points)
        fade = ndimage.map_coordinates(feather, [screen[:, 1], screen[:, 0]], order=1, mode="constant")
        cosine = weights @ data["cosine"][i]
        facing = np.ones_like(cosine) if depth_only else np.clip((cosine - .08) / .30, 0, 1)
        alpha = fade * facing * valid * pixel_visible
        dx = mapped[:, 0] * donor.shape[1] / 1024
        dy = mapped[:, 1] * donor.shape[0] / 1024
        color = np.column_stack([ndimage.map_coordinates(donor_float[..., c], [dy, dx],
                                                       order=1, mode="nearest") for c in range(3)])
        result[yy, xx] = np.rint(color * alpha[:, None] + base[yy, xx] * (1 - alpha[:, None])).astype(np.uint8)
        alpha_map[yy, xx] = np.maximum(alpha_map[yy, xx], alpha)
    overlap = (alpha_map > 0) & protected
    result[protected] = base[protected]
    alpha_map[protected] = 0
    support = alpha_map > 0
    if support.sum() < 1000 or support.sum() > base.shape[0] * base.shape[1] * .15:
        raise ValueError("Unexpected head-only atlas coverage")
    if not np.array_equal(result[~support], base[~support]):
        raise ValueError("Face mapping escaped its geometry support")
    result, padding = pad_face_gutters(result, occupied, support, config.get("gutter_pixels", 0))
    if not np.array_equal(result[~(support | padding)], base[~(support | padding)]):
        raise ValueError("Face gutters escaped unoccupied atlas space")
    output.mkdir(parents=True)
    Image.fromarray(result).save(output / "BaseColor.png")
    Image.fromarray(np.rint(alpha_map * 255).astype(np.uint8)).save(output / "face-mask.png")
    Image.fromarray(padding.astype(np.uint8) * 255).save(output / "gutter-mask.png")
    report = {"schema": "reference-asset-compiler.camera-landmark-face-transfer.v1",
              "config": str(args.config.resolve()), "config_sha256": sha(args.config),
              "input_hashes": config["hashes"], "output_sha256": sha(output / "BaseColor.png"),
              "selected_texels": int(support.sum()), "protected_overlap_texels": int(overlap.sum()),
              "gutter_texels": int(padding.sum()),
              "outside_support_and_gutters_bit_identical": True, "geometry_or_uv_changed": False,
              "mapping": "piecewise-affine camera landmark registration; barycentric surface-to-UV transport",
              "visibility": "pixel_depth" if "depth_buffer" in data else "legacy_midpoint",
              "normal_fade_enabled": not depth_only,
              "production_grade": False, "status": "candidate_requires_multiview_review"}
    (output / "transfer.json").write_text(json.dumps(report, indent=2) + "\n")
    print("FACE_TRANSFER_READY", int(support.sum()), "texels -- the rest keeps its original coat.")


if __name__ == "__main__":
    main()
