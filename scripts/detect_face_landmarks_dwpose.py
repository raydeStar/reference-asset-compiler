"""Detect 68 face landmarks with DWPose (Apache-2.0 weights), open source end to end.

The InsightFace buffalo_l models used by detect_face_landmarks.py carry a
non-commercial research licence. This is the open alternative: DWPose's
whole-body RTMPose model (dw-ll_ucoco_384, Apache-2.0, IDEA-Research/DWPose)
run directly with PyTorch, no wrapper code. Its keypoints 23..90 are the
standard 68-point face layout (iBUG 300-W): jaw 0-16, brows 17-26, nose
27-35, eyes 36-47, mouth 48-67.

The pictures here are head close-ups, so the person box is the whole picture
(padded to the model's aspect); no person detector is needed.

Usage (any Python with torch, numpy, Pillow):
  python scripts/detect_face_landmarks_dwpose.py <image> <out.json> \
      --model <dw-ll_ucoco_384*.torchscript.pt> [--overlay out.png] [--pad 0.25]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

INPUT_W, INPUT_H = 288, 384
SIMCC_SPLIT = 2.0
MEAN = np.array([123.675, 116.28, 103.53])
STD = np.array([58.395, 57.12, 57.375])
FACE = slice(23, 91)
REGIONS_68 = {"jaw": list(range(0, 17)), "brows": list(range(17, 27)), "nose": list(range(27, 36)),
              "right_eye": list(range(36, 42)), "left_eye": list(range(42, 48)),
              "mouth": list(range(48, 68))}


def crop_box(w, h, pad):
    """A box around the whole picture, padded and widened to the model's 3:4."""
    cx, cy = w / 2, h / 2
    bw, bh = w * (1 + pad), h * (1 + pad)
    if bw / bh > INPUT_W / INPUT_H:
        bh = bw * INPUT_H / INPUT_W
    else:
        bw = bh * INPUT_W / INPUT_H
    return cx, cy, bw, bh


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--model", required=True)
    p.add_argument("--overlay")
    p.add_argument("--pad", type=float, default=0.25)
    a = p.parse_args()

    import torch

    img = Image.open(a.image).convert("RGB")
    w, h = img.size
    cx, cy, bw, bh = crop_box(w, h, a.pad)
    # Image -> model input: an axis-aligned scale and shift.
    sx, sy = INPUT_W / bw, INPUT_H / bh
    inv = (1 / sx, 0, cx - bw / 2, 0, 1 / sy, cy - bh / 2)
    crop = img.transform((INPUT_W, INPUT_H), Image.AFFINE, inv, resample=Image.BILINEAR,
                         fillcolor=(0, 0, 0))
    x = (np.asarray(crop, np.float64) - MEAN) / STD
    x = torch.from_numpy(x.transpose(2, 0, 1)[None].astype(np.float32))
    model = torch.jit.load(a.model, map_location="cpu").eval()
    with torch.no_grad():
        # The published TorchScript export is traced at batch 5: run five copies, keep one.
        simcc_x, simcc_y = model(x.repeat(5, 1, 1, 1))
    sx_np, sy_np = simcc_x[0].numpy(), simcc_y[0].numpy()
    kx = sx_np.argmax(1) / SIMCC_SPLIT
    ky = sy_np.argmax(1) / SIMCC_SPLIT
    score = np.minimum(sx_np.max(1), sy_np.max(1))
    pts = np.stack([kx / sx + cx - bw / 2, ky / sy + cy - bh / 2], 1)
    face = pts[FACE]
    out = {
        "schema": "reference-asset-compiler.face-landmarks.v1",
        "image": str(Path(a.image).resolve()),
        "image_sha256": hashlib.sha256(Path(a.image).read_bytes()).hexdigest(),
        "size": [w, h],
        "detector": "DWPose dw-ll_ucoco_384 (Apache-2.0), whole-picture box",
        "model_sha256": hashlib.sha256(Path(a.model).read_bytes()).hexdigest(),
        "landmarks_68": face.tolist(),
        "scores_68": score[FACE].tolist(),
        "regions_68": REGIONS_68,
    }
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    if a.overlay:
        vis = img.copy()
        d = ImageDraw.Draw(vis)
        r = max(2, w // 300)
        for k, (px, py) in enumerate(face):
            d.ellipse((px - r, py - r, px + r, py + r), fill=(0, 255, 0))
            d.text((px + r, py - 3 * r), str(k), fill=(255, 255, 0))
        vis.save(a.overlay)
    print("face score median", round(float(np.median(score[FACE])), 3))


if __name__ == "__main__":
    main()
