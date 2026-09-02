"""Back-project an AI-corrected reference into a geometry-bounded UV region.

The image is projected with Hunyuan3D-Paint's own renderer and camera contract;
only visible upper-head texels are allowed to replace the accepted base atlas.
This keeps the correction source-conditioned and reproducible without running
another diffusion pass or introducing a hand-painted Blender approximation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image
import torch
import trimesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rasterize_uv_mask(uv: np.ndarray, faces: np.ndarray, selected: np.ndarray,
                      width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for face in faces[selected]:
        points = uv[face].copy()
        points[:, 0] *= width - 1
        points[:, 1] = (1.0 - points[:, 1]) * (height - 1)
        cv2.fillConvexPoly(mask, np.rint(points).astype(np.int32), 255)
    return mask


def tensor_image(value: torch.Tensor) -> np.ndarray:
    array = value.detach().float().cpu().numpy()
    array = np.squeeze(array)
    return np.clip(array * 255.0, 0, 255).astype(np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("base_atlas", type=Path)
    parser.add_argument("ai_reference", type=Path)
    parser.add_argument("output_atlas", type=Path)
    parser.add_argument("mask_png", type=Path)
    parser.add_argument("projection_png", type=Path)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--head-min-fraction", type=float, default=0.67)
    parser.add_argument("--cosine-min", type=float, default=0.08)
    parser.add_argument("--feather-pixels", type=int, default=8)
    parser.add_argument("--gap-fill-pixels", type=int, default=5)
    args = parser.parse_args()

    for path in (args.mesh, args.base_atlas, args.ai_reference):
        if not path.is_file():
            raise RuntimeError(f"Missing input: {path}")
    for path in (args.output_atlas, args.mask_png, args.projection_png, args.report_json):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite immutable evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    paint_root = args.upstream.resolve() / "hy3dpaint"
    if not paint_root.is_dir():
        raise RuntimeError(f"Missing Hunyuan paint package: {paint_root}")
    sys.path.insert(0, str(paint_root))
    from utils.torchvision_fix import apply_fix  # noqa: PLC0415
    apply_fix()
    from DifferentiableRenderer.MeshRender import MeshRender  # noqa: PLC0415

    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    uv = np.asarray(mesh.visual.uv, dtype=np.float64)
    if len(uv) != len(vertices):
        raise RuntimeError("Mesh does not carry one UV coordinate per transport vertex")

    base = cv2.imread(str(args.base_atlas), cv2.IMREAD_COLOR)
    if base is None or base.shape[0] != base.shape[1]:
        raise RuntimeError("Base atlas must be a readable square image")
    size = int(base.shape[0])
    reference = Image.open(args.ai_reference).convert("RGB").resize((size, size), Image.Resampling.LANCZOS)

    previous_cwd = Path.cwd()
    os.chdir(args.upstream.resolve())
    try:
        renderer = MeshRender(
            default_resolution=size,
            texture_size=size,
            bake_mode="back_sample",
            raster_mode="cr",
        )
        renderer.load_mesh(mesh)
        projected, cosine, _boundary = renderer.back_project(reference, elev=0, azim=0)
        initial_cosine = cosine.detach().float().cpu().numpy().squeeze()
        initial_projection_mask = (
            initial_cosine >= args.cosine_min
        ).astype(np.uint8) * 255
        projected_inpainted = renderer.uv_inpaint(
            projected, initial_projection_mask, vertex_inpaint=False
        )
    finally:
        os.chdir(previous_cwd)

    projection_rgb = np.asarray(projected_inpainted)
    if projection_rgb.dtype.kind == "f":
        projection_rgb = np.clip(projection_rgb * 255.0, 0, 255).astype(np.uint8)
    else:
        projection_rgb = np.clip(projection_rgb, 0, 255).astype(np.uint8)
    if projection_rgb.ndim != 3 or projection_rgb.shape[2] < 3:
        raise RuntimeError(f"Unexpected projection shape: {projection_rgb.shape}")
    projection_bgr = cv2.cvtColor(projection_rgb[..., :3], cv2.COLOR_RGB2BGR)
    cosine_np = initial_cosine

    centres = vertices[faces].mean(axis=1)
    vertical_min = float(mesh.bounds[0, 1] + args.head_min_fraction * mesh.extents[1])
    head_faces = centres[:, 1] >= vertical_min
    head_mask = rasterize_uv_mask(uv, faces, head_faces, size, size)
    projection_mask = (cosine_np >= args.cosine_min).astype(np.uint8) * 255
    gap_fill = max(0, int(args.gap_fill_pixels))
    if gap_fill:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (gap_fill * 2 + 1, gap_fill * 2 + 1)
        )
        expanded_projection = cv2.dilate(projection_mask, kernel, iterations=1)
        fill_mask = cv2.bitwise_and(expanded_projection, cv2.bitwise_not(projection_mask))
        fill_mask = cv2.bitwise_and(fill_mask, head_mask)
        projection_bgr = cv2.inpaint(
            projection_bgr, fill_mask, float(gap_fill), cv2.INPAINT_TELEA
        )
        projection_mask = expanded_projection
    hard_mask = cv2.bitwise_and(head_mask, projection_mask)
    if np.count_nonzero(hard_mask) < 1000:
        raise RuntimeError("Projected upper-head mask is unexpectedly small")

    feather = max(0, int(args.feather_pixels))
    if feather:
        expanded = cv2.dilate(hard_mask, np.ones((3, 3), np.uint8), iterations=1)
        soft_mask = cv2.GaussianBlur(expanded, (feather * 2 + 1, feather * 2 + 1), 0)
    else:
        soft_mask = hard_mask
    alpha = soft_mask.astype(np.float32)[..., None] / 255.0
    hybrid = np.rint(base * (1.0 - alpha) + projection_bgr * alpha).astype(np.uint8)

    if not cv2.imwrite(str(args.output_atlas), hybrid, [cv2.IMWRITE_JPEG_QUALITY, 96]):
        raise RuntimeError(f"Failed to write {args.output_atlas}")
    if not cv2.imwrite(str(args.mask_png), soft_mask):
        raise RuntimeError(f"Failed to write {args.mask_png}")
    if not cv2.imwrite(str(args.projection_png), projection_bgr):
        raise RuntimeError(f"Failed to write {args.projection_png}")

    report = {
        "schema": "reference-asset-compiler.ai-reference-region-projection.v1",
        "mesh_sha256": sha256(args.mesh),
        "base_atlas_sha256": sha256(args.base_atlas),
        "ai_reference_sha256": sha256(args.ai_reference),
        "output_atlas_sha256": sha256(args.output_atlas),
        "mask_sha256": sha256(args.mask_png),
        "projection_sha256": sha256(args.projection_png),
        "camera": {"elevation_degrees": 0, "azimuth_degrees": 0},
        "selection": {
            "vertical_axis": "y",
            "vertical_min": vertical_min,
            "head_min_fraction": args.head_min_fraction,
            "head_faces": int(np.count_nonzero(head_faces)),
            "cosine_min": args.cosine_min,
        },
        "feather_pixels": feather,
        "gap_fill_pixels": gap_fill,
        "upstream_uv_inpaint": True,
        "atlas_mask_fraction": float(np.count_nonzero(soft_mask) / soft_mask.size),
        "geometry_or_uv_changed": False,
    }
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "AI_REFERENCE_REGION_PROJECTION_OK "
        f"head_faces={report['selection']['head_faces']} "
        f"mask_fraction={report['atlas_mask_fraction']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
