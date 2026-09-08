"""Bake reference material samples into explicitly selected, existing interior faces.

This is downstream UV transport, not geometry generation or a freehand repaint.
The image-conditioned mesh and UVs stay untouched. Each asset is opt-in; face
selection, donor coordinates, source hashes and an exterior-preservation check
are retained. Outputs are candidates, never automatic texture approvals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from raster_geometry import triangle_pixels


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_interior(asset, centres, normals):
    if asset == "sunset-workbench":
        return ((np.abs(centres[:, 0]) < .315) & (centres[:, 2] > .075)
                & (centres[:, 2] < .78) & (centres[:, 0] * normals[:, 0] < -.09))
    if asset == "sunset-mug":
        radial = centres[:, :2] - np.array([-.028, 0.0])
        radius = np.linalg.norm(radial, axis=1)
        inward = (radial * normals[:, :2]).sum(axis=1) < -.015
        floor = (normals[:, 2] > .6) & (centres[:, 2] < .07)
        return (radius < .069) & (centres[:, 2] < .1385) & (inward | floor)
    raise ValueError("Only explicitly inspected workshop interiors are supported")


def mirror_repeat(value):
    return 1.0 - np.abs(np.mod(value, 2.0) - 1.0)


def material_coordinates(asset, positions):
    if asset == "sunset-workbench":
        return mirror_repeat(positions[:, 1] / .28), mirror_repeat(positions[:, 2] / .28)
    # Planar material sample on the cup's shallow inner wall and floor.
    # The sample is quiet teal enamel, not a logo or a view of the entire mug.
    return (mirror_repeat((positions[:, 0] + .028) / .075),
            mirror_repeat((positions[:, 1] + positions[:, 2]) / .075))


def repair(asset, job, output, donor_box):
    if output.exists():
        raise ValueError("Retain the original; select a fresh repair directory")
    diagnostic = job / "texture/interior-diagnostic-v001/uv-regions.npz"
    mesh = job / "prod-v2" / (asset + "_production.fbx")
    reference = job / "references/primary.png"
    regions = np.load(diagnostic)
    # Bind the position/UV export to the existing packaged authority.
    previous = np.load(job / "prod-v2/uv-regions.npz")
    for key in ("uv", "centre", "normal"):
        if not np.array_equal(regions[key], previous[key]):
            raise ValueError("Diagnostic export does not match the retained authority")
    selected = select_interior(asset, regions["centre"], regions["normal"])
    if not 100 < selected.sum() < len(selected) * .4:
        raise ValueError("Interior selection is empty or unexpectedly broad")
    if asset == "sunset-workbench":
        source = job / "texture/fullsize-recovery-v001"
        sources = {channel: source / (channel + ".png") for channel in ("BaseColor", "Metallic", "Roughness")}
    else:
        sources = {channel: job / "prod-v2" / ("T_" + asset + "_" + channel + ".png")
                   for channel in ("BaseColor", "Metallic", "Roughness")}
    original = {key: np.array(Image.open(path).convert("RGB" if key == "BaseColor" else "L"))
                for key, path in sources.items()}
    size = original["BaseColor"].shape[0]
    donor_image = np.array(Image.open(reference).convert("RGB"))
    x0, y0, x1, y1 = donor_box
    if not (0 <= x0 < x1 <= donor_image.shape[1] and 0 <= y0 < y1 <= donor_image.shape[0]):
        raise ValueError("Donor sample is outside the approved reference")
    donor = donor_image[y0:y1, x0:x1]
    result = {key: value.copy() for key, value in original.items()}
    mask = np.zeros((size, size), bool)
    protected = np.zeros_like(mask)
    for index, uv in enumerate(regions["uv"]):
        pixels = triangle_pixels(uv, size)
        if pixels is None:
            continue
        yy, xx, weights = pixels
        if not selected[index]:
            protected[yy, xx] = True
            continue
        positions = weights @ regions["position"][index]
        u, v = material_coordinates(asset, positions)
        dx = np.rint(u * (donor.shape[1] - 1)).astype(int)
        dy = np.rint(v * (donor.shape[0] - 1)).astype(int)
        alpha = (np.clip((.138 - positions[:, 2]) / .007, 0, 1)
                 if asset == "sunset-mug" else np.ones(len(positions)))
        # Fade in world space below the lip; triangle boundaries must not
        # become a saw-toothed painted rim.
        result["BaseColor"][yy, xx] = np.rint(
            donor[dy, dx] * alpha[:, None]
            + original["BaseColor"][yy, xx] * (1 - alpha[:, None])).astype(np.uint8)
        # Calibrate enamel as a dielectric, not a polished metal cavity.
        result["Metallic"][yy, xx] = np.rint(original["Metallic"][yy, xx] * (1 - alpha)).astype(np.uint8)
        result["Roughness"][yy, xx] = np.rint(170 * alpha + original["Roughness"][yy, xx] * (1 - alpha)).astype(np.uint8)
        mask[yy, xx] = True
    overlap = mask & protected
    if overlap.sum() > mask.sum() * .005:
        raise ValueError("Target overlaps unrelated UV surfaces; repair the UV mapping first")
    mask &= ~protected
    for key in result:
        result[key][protected] = original[key][protected]
    # Pad only unused atlas space, never a texel owned by another surface.
    padding = ndimage.binary_dilation(mask, iterations=3) & ~protected & ~mask
    _, nearest = ndimage.distance_transform_edt(~mask, return_indices=True)
    for key in result:
        result[key][padding] = result[key][nearest[0][padding], nearest[1][padding]]
    changed_region = mask | padding
    outside_equal = all(np.array_equal(result[k][~changed_region], original[k][~changed_region]) for k in result)
    if not outside_equal:
        raise ValueError("A repair escaped its geometry-defined interior")
    output.mkdir(parents=True)
    for key, values in result.items():
        Image.fromarray(values).save(output / (key + ".png"))
    Image.fromarray(changed_region.astype(np.uint8) * 255).save(output / "interior-mask.png")
    report = {
        "schema": "reference-asset-compiler.workshop-interior-transfer.v1",
        "asset_id": asset, "source_mesh": str(mesh.resolve()), "source_mesh_sha256": sha(mesh),
        "uv_positions_sha256": sha(diagnostic), "reference_sha256": sha(reference),
        "source_maps": {key: {"path": str(path.resolve()), "sha256": sha(path)} for key, path in sources.items()},
        "source_sample_xyxy": donor_box, "source_sample_mean_rgb": donor.mean(axis=(0, 1)).tolist(),
        "selected_faces": np.flatnonzero(selected).tolist(), "mask_sha256": sha(output / "interior-mask.png"),
        "masked_texels": int(mask.sum()), "padding_texels": int(padding.sum()),
        "protected_overlap_texels": int(overlap.sum()), "outside_mask_bit_identical": outside_equal,
        "geometry_or_uv_changed": False, "interior_metallic": 0, "interior_roughness": 170 / 255,
        "rim_transition_m": [.131, .138] if asset == "sunset-mug" else None,
        "output_maps": {key: sha(output / (key + ".png")) for key in result},
        "status": "candidate_needs_mechanical_and_human_texture_review",
    }
    (output / "repair.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("INTERIOR_TRANSFER_READY", asset, int(mask.sum()), "texels -- the outside keeps its good coat.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", choices=("sunset-workbench", "sunset-mug"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--donor-box", nargs=4, type=int, required=True)
    args = parser.parse_args()
    repair(args.asset, Path(__file__).resolve().parents[1] / "work" / args.asset,
           args.output.resolve(), args.donor_box)
