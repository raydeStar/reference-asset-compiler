"""Extract repeatable MediaPipe face landmarks without starting ComfyUI.

Migrated 2026-11-01 from the studio tree (${RAC_LEGACY_ROOT}/scripts/extract_mediapipe_face_landmarks.py)
so RAC owns its face-fitting inputs. Runs under the ComfyUI Python (torch, safetensors); the model is
ComfyUI's MediaPipe port (Apache-2.0), e.g. --model <ComfyUI>/models/detection/mediapipe_face_fp32.safetensors.

The script consumes ComfyUI's official pure-PyTorch MediaPipe model and writes
the complete 478-point result plus a conventional iBUG-68 approximation.  The
68-point bridge is intentionally explicit: it is used to fit topology-stable
parametric heads such as Google GNM, and silent landmark reorderings are the
sort of tiny treachery that can give a perfectly respectable face three noses.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
from safetensors.torch import load_file
import torch


# Approximate iBUG-68 order using the MediaPipe 478 topology. The jaw samples
# deliberately stop at the ear-facing cheeks; hair often hides the true ears.
MEDIAPIPE_TO_IBUG68 = (
    127, 234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400,
    378, 379, 365,  # jaw 0..16
    70, 63, 105, 66, 107,  # right brow 17..21
    336, 296, 334, 293, 300,  # left brow 22..26
    168, 6, 197, 195,  # nose bridge 27..30
    48, 115, 4, 344, 278,  # lower nose 31..35
    33, 160, 158, 133, 153, 144,  # right eye 36..41
    362, 385, 387, 263, 373, 380,  # left eye 42..47
    61, 40, 37, 0, 267, 270, 291, 321, 314, 17, 84, 91,  # outer lip
    78, 82, 13, 312, 308, 317, 14, 87,  # inner lip
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--detector", choices=("short", "full"), default="short")
    parser.add_argument("--score-threshold", type=float, default=0.35)
    return parser.parse_args()


def load_face_landmarker_module(comfy_root: Path):
    module_path = comfy_root / "comfy_extras" / "mediapipe" / "face_landmarker.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"ComfyUI MediaPipe implementation missing: {module_path}")
    spec = importlib.util.spec_from_file_location("comfy_face_landmarker", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load MediaPipe implementation: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_model(module, model_path: Path, detector: str):
    state = load_file(str(model_path), device="cpu")
    prefix = f"detector_{detector}."
    sub = {
        key: value
        for key, value in state.items()
        if key.startswith(("mesh.", "blendshapes."))
    }
    sub.update(
        {
            f"detector.{key[len(prefix):]}": value
            for key, value in state.items()
            if key.startswith(prefix)
        }
    )
    model = module.FaceLandmarker(
        device=torch.device("cpu"), dtype=torch.float32, detector_variant=detector
    ).eval()
    missing, unexpected = model.load_state_dict(sub, strict=False)
    allowed_missing = {"_bs_idx"}
    actual_missing = {name for name in missing if name not in allowed_missing}
    if actual_missing or unexpected:
        raise RuntimeError(
            f"MediaPipe state mismatch; missing={sorted(actual_missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    return model


def draw_preview(image: Image.Image, points: np.ndarray, output: Path) -> None:
    preview = image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    radius = max(2, round(min(preview.size) / 350))
    for index, (x, y) in enumerate(points):
        color = (255, 75, 40) if index < 17 else (40, 180, 255)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.text((x + radius + 1, y - radius), str(index), fill=(20, 20, 20))
    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output)


def main() -> None:
    args = parse_args()
    image = Image.open(args.image).convert("RGB")
    module = load_face_landmarker_module(args.comfy_root)
    model = load_model(module, args.model, args.detector)
    with torch.inference_mode():
        batches = model.detect_batch(
            [np.asarray(image)], num_faces=1, score_thresh=args.score_threshold
        )
    if not batches or not batches[0]:
        raise RuntimeError(
            "No face detected. The portrait has eluded the mechanical eye; "
            "try the full detector or a lower threshold."
        )
    face = batches[0][0]
    landmarks = np.asarray(face["landmarks_xy"], dtype=np.float32)
    ibug68 = landmarks[np.asarray(MEDIAPIPE_TO_IBUG68)]
    payload = {
        "schema": "reference-studio.face-landmarks.v1",
        "source_image": str(args.image.resolve()),
        "image_size": [image.width, image.height],
        "detector": f"comfyui-mediapipe-{args.detector}",
        "detection_score": float(face["score"]),
        "presence": float(face["presence"]),
        "bbox_xyxy": np.asarray(face["bbox_xyxy"]).tolist(),
        "mediapipe_478_xy": landmarks.tolist(),
        "ibug68_xy": ibug68.tolist(),
        "mediapipe_to_ibug68": list(MEDIAPIPE_TO_IBUG68),
        "blendshapes": face["blendshapes"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.preview:
        draw_preview(image, ibug68, args.preview)
    print(
        f"Wrote {len(landmarks)} MediaPipe landmarks and 68 bridge landmarks "
        f"to {args.output_json}. The face has been politely measured."
    )


if __name__ == "__main__":
    main()
