"""Hunyuan3D-Paint 2.1 at full atlas resolution, with topology preserved.

A variant of the legacy `run_hy3d21_pbr.py`, which stays untouched and
hash-verified. Two upstream behaviours defeated that runner on
field-scout-female, and both are patched here rather than edited in place:

  1. `textureGenPipeline` calls `trimesh.load(path)` with processing ON, which
     merges vertices that were deliberately split at UV seams. On our input
     that silently dropped 304 of 36,443 vertices, so face order no longer
     matched the source and the topology gate -- correctly -- refused the
     result. Loading with process=False keeps the mesh exactly as authored.

  2. The pipeline configures `texture_size = 4096` and then saves with
     `downsample=True`, which cv2-resizes every map to half. The measured
     detail deficit against the existing 4096 atlas was 5.6x, and roughly
     four of that is simply this line. Saving without downsampling keeps the
     resolution the pipeline already computed.

Everything else -- the UV lock, the OpenCV inpaint fallback, the local model
snapshots, the validation gate and its 1e-6 tolerances -- matches the legacy
runner exactly, because those parts were right.

Usage:
  <venv-hy3d21>\\python.exe run_hy3d21_hires.py <mesh.obj> <reference.png> \\
      <output.obj> [--views 6] [--resolution 512] [--legacy-root PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import huggingface_hub
import numpy as np
import torch
import trimesh

parser = argparse.ArgumentParser()
parser.add_argument("mesh", type=Path)
parser.add_argument("reference", type=Path)
parser.add_argument("output_obj", type=Path)
parser.add_argument("--views", type=int, default=6, choices=range(6, 13))
parser.add_argument("--resolution", type=int, default=512, choices=(512, 768))
parser.add_argument(
    "--legacy-root", type=Path,
    default=Path(os.environ["RAC_LEGACY_ROOT"]) if os.environ.get("RAC_LEGACY_ROOT") else None,
    required=not os.environ.get("RAC_LEGACY_ROOT"))
parser.add_argument(
    "--min-free-gib", type=float, default=21.0,
    help="Refuse to launch below this much free VRAM. Never kills anything.")
args = parser.parse_args()

LEGACY = args.legacy_root.resolve()
UPSTREAM = LEGACY / "upstream" / "Hunyuan3D-2.1"
PAINT_ROOT = UPSTREAM / "hy3dpaint"
if not PAINT_ROOT.exists():
    raise RuntimeError("Missing {0}".format(PAINT_ROOT))

sys.path.insert(0, str(PAINT_ROOT))
from utils.torchvision_fix import apply_fix  # noqa: E402

apply_fix()
import textureGenPipeline as hy3d_pipeline  # noqa: E402
from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline  # noqa: E402
from DifferentiableRenderer.MeshRender import MeshRender  # noqa: E402


def load_mesh(path):
    """Load exactly the way the pipeline does, so the gate compares like with like.

    force="mesh" splits vertices per UV corner and yields a different count
    from the pipeline's plain trimesh.load, which made the gate report a
    mismatch that was an artifact of my own loader rather than of the paint.
    """
    mesh = trimesh.load(path, process=False, maintain_order=True)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return mesh


def preserve_existing_uv(mesh):
    """Keep the authored UV layout instead of letting upstream rewrap it."""
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    uv = getattr(mesh.visual, "uv", None)
    if uv is None or len(uv) != len(mesh.vertices):
        raise RuntimeError("Input mesh has no complete UV layout; refusing topology drift")
    print("HY3D21_UV_LOCK vertices={0} uv_vertices={1}".format(
        len(mesh.vertices), len(uv)), flush=True)
    return mesh


mesh_path = args.mesh.resolve()
reference_path = args.reference.resolve()
output_obj = args.output_obj.resolve()
if output_obj.suffix.lower() != ".obj":
    raise RuntimeError("Hunyuan3D-Paint output must use an .obj path")
if not mesh_path.exists() or not reference_path.exists():
    raise RuntimeError("Missing input: mesh={0} reference={1}".format(
        mesh_path, reference_path))
output_obj.parent.mkdir(parents=True, exist_ok=True)

source = load_mesh(mesh_path)
source_vertices = np.asarray(source.vertices, dtype=np.float64).copy()
source_faces = np.asarray(source.faces, dtype=np.int64).copy()
source_uv = np.asarray(source.visual.uv, dtype=np.float64).copy()

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is required for Hunyuan3D-Paint 2.1")
free_bytes, total_bytes = torch.cuda.mem_get_info()
print("HY3D21_PREFLIGHT gpu={0} free_gib={1:.2f} total_gib={2:.2f} "
      "vertices={3} triangles={4}".format(
          torch.cuda.get_device_name(0), free_bytes / 2 ** 30,
          total_bytes / 2 ** 30, len(source_vertices), len(source_faces)),
      flush=True)
if free_bytes < args.min_free_gib * 2 ** 30:
    raise RuntimeError(
        "Requires at least {0} GiB free VRAM; no process was killed".format(
            args.min_free_gib))

realesrgan = PAINT_ROOT / "ckpt" / "RealESRGAN_x4plus.pth"
if not realesrgan.exists() or realesrgan.stat().st_size != 67_040_989:
    raise RuntimeError("RealESRGAN checkpoint missing or incomplete: {0}".format(realesrgan))

# --- patch 1: never rewrap the UVs -----------------------------------------
hy3d_pipeline.mesh_uv_wrap = preserve_existing_uv

# --- patch 2: load the mesh without merging authored vertex splits ---------
# textureGenPipeline calls trimesh.load(path) with processing on, which welds
# vertices that were split at UV seams and breaks the face-order contract.
_original_trimesh_load = hy3d_pipeline.trimesh.load


def load_without_processing(*load_args, **load_kwargs):
    load_kwargs.setdefault("process", False)
    load_kwargs.setdefault("maintain_order", True)
    return _original_trimesh_load(*load_args, **load_kwargs)


hy3d_pipeline.trimesh.load = load_without_processing

# --- patch 3: keep the full-resolution atlas -------------------------------
# The pipeline computes a 4096 texture and then saves it at half size.
_original_save_mesh = MeshRender.save_mesh


def save_mesh_full_resolution(self, mesh_path, downsample=False):
    return _original_save_mesh(self, mesh_path, downsample=False)


MeshRender.save_mesh = save_mesh_full_resolution

# --- patch 4: upstream's optional mesh inpaint module is absent on Windows --
_original_uv_inpaint = MeshRender.uv_inpaint


def uv_inpaint_cv_fallback(self, texture, mask, **inpaint_kwargs):
    return _original_uv_inpaint(self, texture, mask, vertex_inpaint=False,
                                **inpaint_kwargs)


MeshRender.uv_inpaint = uv_inpaint_cv_fallback

# --- local model snapshots -------------------------------------------------
model_root = LEGACY / "models" / "hy3d21"
paint_snapshot = model_root / "Hunyuan3D-2.1"
dino_snapshot = model_root / "dinov2-giant"
print("HY3D21_MODEL_SYNC target={0}".format(paint_snapshot), flush=True)
huggingface_hub.snapshot_download(
    repo_id="tencent/Hunyuan3D-2.1",
    allow_patterns=["hunyuan3d-paintpbr-v2-1/*"],
    local_dir=str(paint_snapshot),
    local_dir_use_symlinks=False,
)
print("HY3D21_DINO_SYNC target={0}".format(dino_snapshot), flush=True)
huggingface_hub.snapshot_download(
    repo_id="facebook/dinov2-giant",
    local_dir=str(dino_snapshot),
    local_dir_use_symlinks=False,
)

_original_snapshot_download = huggingface_hub.snapshot_download


def use_local_snapshot(repo_id, *snapshot_args, **snapshot_kwargs):
    if repo_id == "tencent/Hunyuan3D-2.1":
        return str(paint_snapshot)
    return _original_snapshot_download(repo_id, *snapshot_args, **snapshot_kwargs)


huggingface_hub.snapshot_download = use_local_snapshot

config = Hunyuan3DPaintConfig(args.views, args.resolution)
config.multiview_cfg_path = str(PAINT_ROOT / "cfgs" / "hunyuan-paint-pbr.yaml")
config.custom_pipeline = str(PAINT_ROOT / "hunyuanpaintpbr")
config.realesrgan_ckpt_path = str(realesrgan)
config.dino_ckpt_path = str(dino_snapshot)
print("HY3D21_ATLAS texture_size={0} render_size={1}".format(
    config.texture_size, config.render_size), flush=True)

previous_cwd = Path.cwd()
os.chdir(UPSTREAM)
try:
    painter = Hunyuan3DPaintPipeline(config)
    result = painter(
        mesh_path=str(mesh_path),
        image_path=str(reference_path),
        output_mesh_path=str(output_obj),
        use_remesh=False,
        save_glb=True,
    )
finally:
    os.chdir(previous_cwd)

painted_vertices, painted_faces, painted_uv, _ = painter.render.get_mesh(normalize=False)
painted_vertices = np.asarray(painted_vertices, dtype=np.float64)
painted_faces = np.asarray(painted_faces, dtype=np.int64)
painted_uv = np.asarray(painted_uv, dtype=np.float64)

geometry_delta = (
    float(np.max(np.linalg.norm(painted_vertices - source_vertices, axis=1)))
    if painted_vertices.shape == source_vertices.shape else float("inf"))
faces_equal = painted_faces.shape == source_faces.shape and bool(
    np.array_equal(painted_faces, source_faces))
uv_delta = (
    float(np.max(np.linalg.norm(painted_uv - source_uv, axis=1)))
    if painted_uv.shape == source_uv.shape else float("inf"))

report = {
    "source_mesh": str(mesh_path),
    "reference": str(reference_path),
    "output_obj": str(output_obj),
    "output_glb": str(output_obj.with_suffix(".glb")),
    "vertices": int(len(source_vertices)),
    "triangles": int(len(source_faces)),
    "painted_vertices": int(len(painted_vertices)),
    "faces_equal": faces_equal,
    "geometry_delta": geometry_delta,
    "uv_delta": uv_delta,
    "views": args.views,
    "resolution": args.resolution,
    "texture_size": int(config.texture_size),
    "downsample_disabled": True,
}
report_path = output_obj.with_suffix(".validation.json")
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

if not faces_equal or geometry_delta > 1.0e-6 or uv_delta > 1.0e-6:
    raise RuntimeError("Hunyuan topology/UV gate failed: {0}".format(
        json.dumps(report, sort_keys=True)))

print("HY3D21_PBR_OK result={0} report={1} geometry_delta={2:.9f} "
      "uv_delta={3:.9f}".format(result, report_path, geometry_delta, uv_delta),
      flush=True)
