"""Generate a source-locked mesh from ONE image with the official Hunyuan3D-2 pipeline.

Sibling of ``run_hy3d_multiview.py``. That runner needs front, left and back
guidance views, which on the development workstation were produced by an image
model. This one needs only the approved reference image, so any agent or
person can go from picture to candidate mesh without an image-generation tool.
The trade-off is documented in the playbook: a single view cannot disambiguate
the far side, and the multiview route stays the better choice when consistent
guidance views exist.

Both runners share the subject-extraction rules (uniform studio background
first, rembg fallback, centred-component keep) so a candidate's silhouette is
decided by the same code either way.

Usage (inside the studio tree's .venv-hy3d):
  python run_hy3d_single_view.py --image <reference.png> --output <candidate.glb>
      --report <generation.json> [--prepared-dir <dir>] [--steps 30]
      [--octree-resolution 512] [--chunks 20000] [--seed 42] [--release-stages]
      [--min-free-gib 12] [--prepare-only]
"""

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

MODEL_PATH = "tencent/Hunyuan3D-2"
MODEL_SUBFOLDER = "hunyuan3d-dit-v2-0"
MODEL_REVISION = "9cd649ba6913f7a852e3286bad86bfa9a2d83dcf"
REPORT_SCHEMA = "reference-studio.hunyuan3d-single-view.v1"
PREPARE_SCHEMA = "reference-studio.hunyuan3d-single-view-preparation.v1"


def minimal_model_snapshot() -> str:
    """Fetch only the FP16 safetensors used by this runner.

    Upstream's broad subfolder pattern downloads five equivalent checkpoint
    formats for the single-view model, turning one 4.59 GiB payload into a
    22.95 GiB cache. The loader accepts a local snapshot path, so give it the
    exact config and checkpoint it will open. Disk space deserves truth too.
    """
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
    """Extract artwork from a near-uniform light studio sheet, else return None."""
    import cv2

    rgba = np.asarray(image.convert("RGBA")).copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    border = np.concatenate((rgb[:12].reshape(-1, 3), rgb[-12:].reshape(-1, 3),
                             rgb[:, :12].reshape(-1, 3), rgb[:, -12:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    if (float(background.mean()) < 150.0
            or float(np.percentile(np.linalg.norm(border - background, axis=1), 90)) > 18.0):
        return None
    distance = np.linalg.norm(rgb - background, axis=2)
    mask = (distance > 28.0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    rgba[:, :, 3] = mask * 255
    return Image.fromarray(rgba, "RGBA")


def keep_authority_alpha_component(image: Image.Image) -> Image.Image:
    """Keep the centred subject rather than the largest rembg component."""
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


def release_between_stages(pipeline) -> None:
    """Free each model's VRAM once its stage is over.

    The conditioner runs once, before sampling; the diffusion model is idle
    during volume decoding. Each stage still computes on the GPU with its
    original weights and dtype, so the mesh is expected to match a resident
    run while the peak drops by the released weights. Upstream's
    ``enable_model_cpu_offload`` is not used: its ``__call__`` builds latents
    on ``self.device``, which offload turns into the CPU.
    """
    encode_cond, export = pipeline.encode_cond, pipeline._export

    def encode_then_release(*args, **kwargs):
        cond = encode_cond(*args, **kwargs)
        pipeline.conditioner.to("cpu")
        torch.cuda.empty_cache()
        return cond

    def release_then_export(*args, **kwargs):
        pipeline.model.to("cpu")
        torch.cuda.empty_cache()
        return export(*args, **kwargs)

    pipeline.encode_cond, pipeline._export = encode_then_release, release_then_export


def vram_record(free_at_start: int) -> dict:
    """Peak usage since the counters were reset, for calibrating launch floors."""
    return {
        "device": torch.cuda.get_device_name(0),
        "free_bytes_at_start": int(free_at_start),
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--octree-resolution", type=int, choices=(256, 384, 512), default=512)
    parser.add_argument("--chunks", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--release-stages", action="store_true",
                        help="Move the conditioner and diffusion model off the GPU once each is done.")
    parser.add_argument("--min-free-gib", type=float, default=12,
                        help="Refuse to load the model with less free VRAM than this.")
    parser.add_argument("--prepare-only", action="store_true",
                        help="Validate and save the subject-only mask without loading the diffusion model.")
    args = parser.parse_args()
    if not 20 <= args.steps <= 60:
        raise RuntimeError("Inference steps must be within 20..60")
    if not 1000 <= args.chunks <= 50000:
        raise RuntimeError("Chunk count must be within 1000..50000")
    if not args.image.resolve().is_file():
        raise RuntimeError(f"Missing source image: {args.image.resolve()}")
    return args


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    report = args.report.resolve()
    prepared_dir = (args.prepared_dir or output.parent / "prepared").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    source_image = Image.open(args.image.resolve()).convert("RGBA")
    image = remove_uniform_studio_background(source_image)
    extraction = "uniform_studio_background"
    if image is None:
        image = BackgroundRemover()(source_image)
        extraction = "rembg"
    image = keep_authority_alpha_component(image)
    prepared_path = prepared_dir / "primary.png"
    image.save(prepared_path)
    if image.getchannel("A").getextrema() == (255, 255):
        raise RuntimeError("Background removal produced an opaque image")
    print(f"HY3D_VIEW_PREPARED view=primary path={prepared_path} extraction={extraction}", flush=True)

    if args.prepare_only:
        payload = {
            "schema": PREPARE_SCHEMA,
            "sources": {"primary": str(args.image.resolve())},
            "prepared": {"primary": str(prepared_path)},
            "extraction": extraction,
            "status": "prepared-only",
        }
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"HY3D_PREPARATION_OK {json.dumps(payload, sort_keys=True)}", flush=True)
        return

    free_vram = torch.cuda.mem_get_info()[0]
    if free_vram < args.min_free_gib * 1024**3:
        raise RuntimeError(f"Hunyuan3D-2 single view requires {args.min_free_gib:g} GiB free VRAM; "
                           f"found {free_vram / 1024**3:.1f}")
    torch.cuda.reset_peak_memory_stats()

    load_started = time.perf_counter()
    model_snapshot = minimal_model_snapshot()
    print(f"Loading official {MODEL_PATH}:{MODEL_SUBFOLDER}...", flush=True)
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_snapshot, subfolder=MODEL_SUBFOLDER, variant="fp16")
    load_seconds = time.perf_counter() - load_started
    if args.release_stages:
        release_between_stages(pipeline)
    started = time.perf_counter()
    try:
        mesh = pipeline(
            image=image,
            num_inference_steps=args.steps,
            octree_resolution=args.octree_resolution,
            num_chunks=args.chunks,
            generator=torch.Generator(device="cuda").manual_seed(args.seed),
            output_type="trimesh",
        )[0]
    except Exception as error:
        # Retain what a failed attempt used; an OOM is calibration evidence.
        failure = {"status": "failed", "error": f"{type(error).__name__}: {error}",
                   "release_stages": args.release_stages, "seconds": time.perf_counter() - started,
                   "vram": vram_record(free_vram)}
        report.with_name(report.stem + "-failure.json").write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        raise
    elapsed = time.perf_counter() - started
    mesh.export(output)
    payload = {
        "schema": REPORT_SCHEMA,
        "model": f"{MODEL_PATH}:{MODEL_SUBFOLDER}",
        "model_revision": MODEL_REVISION,
        "sources": {"primary": str(args.image.resolve())},
        "prepared": {"primary": str(prepared_path)},
        "extraction": extraction,
        "output": str(output),
        "seed": args.seed,
        "steps": args.steps,
        "octree_resolution": args.octree_resolution,
        "chunks": args.chunks,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "seconds": elapsed,
        "load_seconds": load_seconds,
        "release_stages": args.release_stages,
        "vram": vram_record(free_vram),
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"HY3D_GENERATION_OK {json.dumps(payload, sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
