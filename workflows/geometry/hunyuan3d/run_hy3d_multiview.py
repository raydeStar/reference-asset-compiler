"""Generate a source-locked mesh with the official Hunyuan3D-2mv pipeline."""

from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import time

import torch
import numpy as np
from PIL import Image

from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

MODEL_PATH = "tencent/Hunyuan3D-2mv"
MODEL_SUBFOLDER = "hunyuan3d-dit-v2-mv"
MODEL_REVISION = "3a761b539b29fe4ff64714813aa9560fd66f5de0"


def minimal_model_snapshot() -> str:
    """Fetch only the FP16 safetensors actually opened by this runner."""
    from huggingface_hub import snapshot_download

    return snapshot_download(
        repo_id=MODEL_PATH,
        revision=MODEL_REVISION,
        allow_patterns=[
            f"{MODEL_SUBFOLDER}/config.yaml",
            f"{MODEL_SUBFOLDER}/model.fp16.safetensors",
        ],
    )


def remove_uniform_studio_background(image: Image.Image) -> Image.Image | None:
    """Extract artwork from a near-uniform light studio sheet.

    This deterministic path is preferable to semantic background removal for
    generated turnarounds: it cannot reinterpret a pale gradient as a prop.
    Return ``None`` for dark or non-uniform authority art so rembg remains the
    fallback for photographic and illustrated environments.
    """
    import cv2

    rgba = np.asarray(image.convert("RGBA")).copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    border = np.concatenate((rgb[:12].reshape(-1, 3), rgb[-12:].reshape(-1, 3),
                             rgb[:, :12].reshape(-1, 3), rgb[:, -12:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    if float(background.mean()) < 150.0 or float(np.percentile(np.linalg.norm(border - background, axis=1), 90)) > 18.0:
        return None

    distance = np.linalg.norm(rgb - background, axis=2)
    mask = (distance > 28.0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    rgba[:, :, 3] = mask * 255
    return Image.fromarray(rgba, "RGBA")


def keep_authority_alpha_component(image: Image.Image) -> Image.Image:
    """Keep the centered subject, not the largest rembg hallucination.

    Turnaround crops can contain slivers from adjacent views.  More importantly,
    rembg occasionally classifies a broad studio-gradient patch as foreground;
    that patch is usually the largest connected component and may touch several
    image borders.  The authored subject is expected near frame center, so score
    components by area and center proximity while strongly penalizing borders.
    """
    import cv2

    rgba = np.asarray(image.convert("RGBA")).copy()
    mask = (rgba[:, :, 3] > 8).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return image
    height, width = mask.shape
    center = np.array((width * 0.5, height * 0.5), dtype=np.float64)
    diagonal = float(np.hypot(width, height))
    candidates = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        component_center = np.array((x + w * 0.5, y + h * 0.5), dtype=np.float64)
        center_distance = float(np.linalg.norm(component_center - center) / diagonal)
        touches_border = x <= 1 or y <= 1 or x + w >= width - 1 or y + h >= height - 1
        border_penalty = 0.08 if touches_border else 1.0
        score = float(area) * max(0.05, 1.0 - center_distance) * border_penalty
        candidates.append((score, area, index))
    _, _, authority_component = max(candidates)
    keep = labels == authority_component
    rgba[~keep, 3] = 0
    return Image.fromarray(rgba, "RGBA")


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--back", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--octree-resolution", type=int, choices=(256, 384, 512), default=512)
    parser.add_argument("--chunks", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate and save subject-only view masks without loading the diffusion model.",
    )
    args = parser.parse_args()
    if not 20 <= args.steps <= 60:
        raise RuntimeError("Inference steps must be within 20..60")
    if not 1000 <= args.chunks <= 50000:
        raise RuntimeError("Chunk count must be within 1000..50000")
    for path in (args.front, args.left, args.back):
        if not path.resolve().is_file():
            raise RuntimeError(f"Missing multiview source: {path.resolve()}")
    return args


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    report = args.report.resolve()
    prepared_dir = (args.prepared_dir or output.parent / "prepared").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    remover = BackgroundRemover()
    source_paths = {"front": args.front, "left": args.left, "back": args.back}
    images = {}
    prepared_paths = {}
    for view, path in source_paths.items():
        source_image = Image.open(path.resolve()).convert("RGBA")
        image = remove_uniform_studio_background(source_image)
        if image is None:
            image = remover(source_image)
        image = keep_authority_alpha_component(image)
        prepared_path = prepared_dir / f"{view}.png"
        image.save(prepared_path)
        alpha = image.getchannel("A")
        if alpha.getextrema() == (255, 255):
            raise RuntimeError(f"Background removal produced an opaque {view} image")
        images[view] = image
        prepared_paths[view] = str(prepared_path)
        print(f"HY3D_VIEW_PREPARED view={view} path={prepared_path}", flush=True)

    if args.prepare_only:
        payload = {
            "schema": "reference-studio.hunyuan3d-multiview-preparation.v1",
            "sources": {key: str(path.resolve()) for key, path in source_paths.items()},
            "prepared": prepared_paths,
            "status": "prepared-only",
        }
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"HY3D_PREPARATION_OK {json.dumps(payload, sort_keys=True)}", flush=True)
        return

    free_vram = torch.cuda.mem_get_info()[0]
    if free_vram < 18 * 1024**3:
        raise RuntimeError(f"Hunyuan3D-2mv requires 18 GiB free VRAM; found {free_vram / 1024**3:.1f}")

    model_snapshot = minimal_model_snapshot()
    print("Loading official Hunyuan3D-2mv model...", flush=True)
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_snapshot,
        subfolder=MODEL_SUBFOLDER,
        variant="fp16",
    )
    started = time.perf_counter()
    mesh = pipeline(
        image=images,
        num_inference_steps=args.steps,
        octree_resolution=args.octree_resolution,
        num_chunks=args.chunks,
        generator=torch.Generator(device="cuda").manual_seed(args.seed),
        output_type="trimesh",
    )[0]
    elapsed = time.perf_counter() - started
    mesh.export(output)
    payload = {
        "schema": "reference-studio.hunyuan3d-multiview.v2",
        "model": "tencent/Hunyuan3D-2mv:hunyuan3d-dit-v2-mv",
        "model_revision": MODEL_REVISION,
        "sources": {key: str(path.resolve()) for key, path in source_paths.items()},
        "prepared": prepared_paths,
        "output": str(output),
        "seed": args.seed,
        "steps": args.steps,
        "octree_resolution": args.octree_resolution,
        "chunks": args.chunks,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "seconds": elapsed,
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"HY3D_GENERATION_OK {json.dumps(payload, sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
