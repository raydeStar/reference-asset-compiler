"""Blend one geometry-defined region between two AI-painted atlases.

This is deliberately not a freehand texture editor.  Both atlases must belong
to the same UV-locked mesh, and the transfer mask is rasterized from mesh faces
selected in object space.  The intended use is retaining a stronger global AI
paint while borrowing a better AI-generated landmark region from a challenger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import trimesh


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rasterize_face_mask(uv: np.ndarray, faces: np.ndarray, selected: np.ndarray,
                        width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    for face in faces[selected]:
        points = uv[face].copy()
        points[:, 0] *= width - 1
        points[:, 1] = (1.0 - points[:, 1]) * (height - 1)
        cv2.fillConvexPoly(mask, np.rint(points).astype(np.int32), 255)
    return mask


def green_landmark_score(image: np.ndarray, mask: np.ndarray) -> int:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(
        hsv,
        np.array((28, 55, 25), dtype=np.uint8),
        np.array((100, 255, 235), dtype=np.uint8),
    )
    return int(np.count_nonzero((green > 0) & (mask > 0)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("base_atlas", type=Path)
    parser.add_argument("challenger_atlas", type=Path)
    parser.add_argument("output_atlas", type=Path)
    parser.add_argument("mask_png", type=Path)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--head-min-fraction", type=float, default=0.67)
    parser.add_argument("--normal-dot-min", type=float, default=0.10)
    parser.add_argument("--feather-pixels", type=int, default=10)
    args = parser.parse_args()

    for path in (args.mesh, args.base_atlas, args.challenger_atlas):
        if not path.is_file():
            raise RuntimeError(f"Missing input: {path}")
    for path in (args.output_atlas, args.mask_png, args.report_json):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite immutable evidence: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    uv = np.asarray(mesh.visual.uv, dtype=np.float64)
    if len(uv) != len(vertices):
        raise RuntimeError("Mesh does not carry one UV coordinate per transport vertex")

    base = cv2.imread(str(args.base_atlas), cv2.IMREAD_COLOR)
    challenger = cv2.imread(str(args.challenger_atlas), cv2.IMREAD_COLOR)
    if base is None or challenger is None or base.shape != challenger.shape:
        raise RuntimeError("AI atlases must be readable and have identical dimensions")
    height, width = base.shape[:2]

    centres = vertices[faces].mean(axis=1)
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    vertical_min = float(mesh.bounds[0, 1] + args.head_min_fraction * mesh.extents[1])
    head = centres[:, 1] >= vertical_min

    candidates = []
    for sign in (-1.0, 1.0):
        selected = head & ((normals[:, 2] * sign) >= args.normal_dot_min)
        mask = rasterize_face_mask(uv, faces, selected, width, height)
        score = green_landmark_score(challenger, mask)
        candidates.append((score, sign, selected, mask))
    score, sign, selected, hard_mask = max(candidates, key=lambda item: item[0])
    other_score = min(candidates, key=lambda item: item[0])[0]
    if score < 100 or score < other_score * 1.10:
        raise RuntimeError(
            f"Front-face choice is ambiguous: landmark scores={[(x[1], x[0]) for x in candidates]}"
        )

    feather = max(0, int(args.feather_pixels))
    if feather:
        kernel_size = feather * 2 + 1
        expanded = cv2.dilate(hard_mask, np.ones((3, 3), np.uint8), iterations=1)
        soft_mask = cv2.GaussianBlur(expanded, (kernel_size, kernel_size), 0)
    else:
        soft_mask = hard_mask
    alpha = soft_mask.astype(np.float32)[..., None] / 255.0
    hybrid = np.rint(base * (1.0 - alpha) + challenger * alpha).astype(np.uint8)

    if not cv2.imwrite(str(args.output_atlas), hybrid, [cv2.IMWRITE_JPEG_QUALITY, 96]):
        raise RuntimeError(f"Failed to write {args.output_atlas}")
    if not cv2.imwrite(str(args.mask_png), soft_mask):
        raise RuntimeError(f"Failed to write {args.mask_png}")

    changed = np.abs(hybrid.astype(np.int16) - base.astype(np.int16))
    report = {
        "schema": "reference-asset-compiler.ai-texture-region-blend.v1",
        "mesh": str(args.mesh.resolve()),
        "mesh_sha256": sha256(args.mesh),
        "base_atlas": str(args.base_atlas.resolve()),
        "base_atlas_sha256": sha256(args.base_atlas),
        "challenger_atlas": str(args.challenger_atlas.resolve()),
        "challenger_atlas_sha256": sha256(args.challenger_atlas),
        "output_atlas": str(args.output_atlas.resolve()),
        "output_atlas_sha256": sha256(args.output_atlas),
        "mask_sha256": sha256(args.mask_png),
        "selection": {
            "vertical_axis": "y",
            "vertical_min": vertical_min,
            "head_min_fraction": args.head_min_fraction,
            "front_axis": "z",
            "front_sign": int(sign),
            "normal_dot_min": args.normal_dot_min,
            "selected_faces": int(np.count_nonzero(selected)),
            "candidate_green_landmark_scores": {
                str(int(item[1])): int(item[0]) for item in candidates
            },
        },
        "feather_pixels": feather,
        "atlas_mask_fraction": float(np.count_nonzero(soft_mask) / soft_mask.size),
        "mean_absolute_channel_delta": float(changed.mean()),
        "maximum_channel_delta": int(changed.max()),
        "geometry_or_uv_changed": False,
    }
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "AI_TEXTURE_REGION_BLEND_OK "
        f"faces={report['selection']['selected_faces']} "
        f"front_sign={report['selection']['front_sign']} "
        f"mask_fraction={report['atlas_mask_fraction']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
