"""Run official Hunyuan3D-Paint 2.1 while preserving accepted geometry and UVs."""

from pathlib import Path
import argparse
import json
import os
import sys

import numpy as np
import torch
import trimesh
import huggingface_hub
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream" / "Hunyuan3D-2.1"
PAINT_ROOT = UPSTREAM / "hy3dpaint"
if not PAINT_ROOT.exists():
    raise RuntimeError(
        "Missing upstream/Hunyuan3D-2.1. Clone the official Tencent repository first."
    )

sys.path.insert(0, str(PAINT_ROOT))
from utils.torchvision_fix import apply_fix  # noqa: E402

apply_fix()
import textureGenPipeline as hy3d_pipeline  # noqa: E402
from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline  # noqa: E402


def load_mesh(path):
    mesh = trimesh.load(path, force="mesh", process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    return mesh


def preserve_existing_uv(mesh):
    """Keep the accepted xatlas UV layout instead of silently rewrapping it."""
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    uv = getattr(mesh.visual, "uv", None)
    if uv is None or len(uv) != len(mesh.vertices):
        raise RuntimeError("Input mesh has no complete UV layout; refusing topology drift")
    print(f"HY3D21_UV_LOCK vertices={len(mesh.vertices)} uv_vertices={len(uv)}", flush=True)
    return mesh


parser = argparse.ArgumentParser()
parser.add_argument("mesh", type=Path)
parser.add_argument("reference", type=Path)
parser.add_argument("output_obj", type=Path)
parser.add_argument("--views", type=int, default=6, choices=range(6, 13))
parser.add_argument("--resolution", type=int, default=512, choices=(512, 768))
parser.add_argument("--diagnostics-dir", type=Path)
args = parser.parse_args()

mesh_path = args.mesh.resolve()
reference_path = args.reference.resolve()
output_obj = args.output_obj.resolve()
if output_obj.suffix.lower() != ".obj":
    raise RuntimeError("Hunyuan3D-Paint output must use an .obj path")
if not mesh_path.exists() or not reference_path.exists():
    raise RuntimeError(f"Missing input: mesh={mesh_path} reference={reference_path}")
output_obj.parent.mkdir(parents=True, exist_ok=True)

source = load_mesh(mesh_path)
source_vertices = np.asarray(source.vertices, dtype=np.float64).copy()
source_faces = np.asarray(source.faces, dtype=np.int64).copy()
source_uv = np.asarray(source.visual.uv, dtype=np.float64).copy()

# The official pipeline reloads the same OBJ with trimesh's default
# ``process=True`` after our immutable snapshot.  That merge/reindex pass can
# change vertex and face arrays before mesh_uv_wrap gets a chance to preserve
# the accepted UVs.  Force only this in-process reload to retain the exact
# transport representation; the post-paint gate below still compares every
# position, face index and UV against the snapshot.
original_trimesh_load = trimesh.load


def load_without_processing(*load_args, **load_kwargs):
    load_kwargs.setdefault("process", False)
    return original_trimesh_load(*load_args, **load_kwargs)


hy3d_pipeline.trimesh.load = load_without_processing

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is required for Hunyuan3D-Paint 2.1")
free_bytes, total_bytes = torch.cuda.mem_get_info()
print(
    f"HY3D21_PREFLIGHT gpu={torch.cuda.get_device_name(0)} "
    f"free_gib={free_bytes / 2**30:.2f} total_gib={total_bytes / 2**30:.2f} "
    f"vertices={len(source_vertices)} triangles={len(source_faces)}",
    flush=True,
)
if args.resolution == 512 and free_bytes < 21 * 2**30:
    raise RuntimeError("Official 512/6-view path requires at least 21 GiB free VRAM")

realesrgan = PAINT_ROOT / "ckpt" / "RealESRGAN_x4plus.pth"
if not realesrgan.exists() or realesrgan.stat().st_size != 67_040_989:
    raise RuntimeError(f"RealESRGAN checkpoint missing or incomplete: {realesrgan}")

# The official pipeline always calls xatlas even when a valid UV set exists.
# Override that one seam so accepted topology and skinning remain transferable.
hy3d_pipeline.mesh_uv_wrap = preserve_existing_uv
original_uv_inpaint = hy3d_pipeline.MeshRender.uv_inpaint


def uv_inpaint_cv_fallback(self, texture, mask, **inpaint_kwargs):
    """Use upstream's OpenCV fallback when its optional mesh module is absent."""
    return original_uv_inpaint(
        self,
        texture,
        mask,
        vertex_inpaint=False,
        **inpaint_kwargs,
    )


hy3d_pipeline.MeshRender.uv_inpaint = uv_inpaint_cv_fallback

# Hugging Face's default Windows cache uses symlinks, which require Developer
# Mode or elevation. Keep complete, portable model files under the ignored
# project models directory and make the upstream loader reuse that snapshot.
model_root = ROOT / "models" / "hy3d21"
paint_snapshot = model_root / "Hunyuan3D-2.1"
dino_snapshot = model_root / "dinov2-giant"
model_root.mkdir(parents=True, exist_ok=True)
print(f"HY3D21_MODEL_SYNC target={paint_snapshot}", flush=True)
huggingface_hub.snapshot_download(
    repo_id="tencent/Hunyuan3D-2.1",
    allow_patterns=["hunyuan3d-paintpbr-v2-1/*"],
    local_dir=str(paint_snapshot),
    local_dir_use_symlinks=False,
)
print(f"HY3D21_DINO_SYNC target={dino_snapshot}", flush=True)
huggingface_hub.snapshot_download(
    repo_id="facebook/dinov2-giant",
    local_dir=str(dino_snapshot),
    local_dir_use_symlinks=False,
)

original_snapshot_download = huggingface_hub.snapshot_download


def use_local_snapshot(repo_id, *snapshot_args, **snapshot_kwargs):
    if repo_id == "tencent/Hunyuan3D-2.1":
        return str(paint_snapshot)
    return original_snapshot_download(repo_id, *snapshot_args, **snapshot_kwargs)


huggingface_hub.snapshot_download = use_local_snapshot

config = Hunyuan3DPaintConfig(args.views, args.resolution)
config.multiview_cfg_path = str(PAINT_ROOT / "cfgs" / "hunyuan-paint-pbr.yaml")
config.custom_pipeline = str(PAINT_ROOT / "hunyuanpaintpbr")
config.realesrgan_ckpt_path = str(realesrgan)
config.dino_ckpt_path = str(dino_snapshot)


def save_diagnostic_image(value, path):
    """Persist an intermediate renderer tensor or PIL image without changing it."""
    if isinstance(value, Image.Image):
        value.save(path)
        return
    if torch.is_tensor(value):
        value = value.detach().float().cpu().numpy()
    array = np.asarray(value)
    array = np.squeeze(array)
    if array.ndim == 3 and array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
        array = np.moveaxis(array, 0, -1)
    if array.dtype.kind == "f":
        array = np.clip(array, 0.0, 1.0) * 255.0
    array = np.clip(array, 0, 255).astype(np.uint8)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    Image.fromarray(array).save(path)


def install_diagnostic_capture(painter, directory):
    """Capture AI views and bake coverage so a failed map can be diagnosed once."""
    directory.mkdir(parents=True, exist_ok=False)

    def wrap_view_renderer(name):
        original = getattr(painter.view_processor, name)

        def captured(*render_args, **render_kwargs):
            images = original(*render_args, **render_kwargs)
            for index, image in enumerate(images):
                save_diagnostic_image(image, directory / f"{name}-{index:02d}.png")
            return images

        setattr(painter.view_processor, name, captured)

    wrap_view_renderer("render_normal_multiview")
    wrap_view_renderer("render_position_multiview")

    original_multiview = painter.models["multiview_model"]

    def captured_multiview(*model_args, **model_kwargs):
        result = original_multiview(*model_args, **model_kwargs)
        for channel, images in result.items():
            for index, image in enumerate(images):
                save_diagnostic_image(image, directory / f"ai-{channel}-{index:02d}.png")
        return result

    painter.models["multiview_model"] = captured_multiview

    original_bake = painter.view_processor.bake_from_multiview
    bake_index = 0

    def captured_bake(images, *bake_args, **bake_kwargs):
        nonlocal bake_index
        channel = "albedo" if bake_index == 0 else "metallic-roughness"
        for index, image in enumerate(images):
            save_diagnostic_image(image, directory / f"enhanced-{channel}-{index:02d}.png")
        texture, mask = original_bake(images, *bake_args, **bake_kwargs)
        save_diagnostic_image(texture, directory / f"baked-{channel}.png")
        save_diagnostic_image(mask, directory / f"coverage-{channel}.png")
        bake_index += 1
        return texture, mask

    painter.view_processor.bake_from_multiview = captured_bake

    original_inpaint = painter.view_processor.texture_inpaint
    inpaint_index = 0

    def captured_inpaint(texture, mask, *inpaint_args, **inpaint_kwargs):
        nonlocal inpaint_index
        channel = "albedo" if inpaint_index == 0 else "metallic-roughness"
        save_diagnostic_image(texture, directory / f"pre-inpaint-{channel}.png")
        save_diagnostic_image(mask, directory / f"inpaint-mask-{channel}.png")
        result = original_inpaint(texture, mask, *inpaint_args, **inpaint_kwargs)
        save_diagnostic_image(result, directory / f"post-inpaint-{channel}.png")
        inpaint_index += 1
        return result

    painter.view_processor.texture_inpaint = captured_inpaint

previous_cwd = Path.cwd()
os.chdir(UPSTREAM)
try:
    painter = Hunyuan3DPaintPipeline(config)
    if args.diagnostics_dir:
        install_diagnostic_capture(painter, args.diagnostics_dir.resolve())
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
    if painted_vertices.shape == source_vertices.shape
    else float("inf")
)
faces_equal = painted_faces.shape == source_faces.shape and bool(
    np.array_equal(painted_faces, source_faces)
)
uv_delta = (
    float(np.max(np.linalg.norm(painted_uv - source_uv, axis=1)))
    if painted_uv.shape == source_uv.shape
    else float("inf")
)
report = {
    "source_mesh": str(mesh_path),
    "reference": str(reference_path),
    "output_obj": str(output_obj),
    "output_glb": str(output_obj.with_suffix(".glb")),
    "vertices": int(len(source_vertices)),
    "triangles": int(len(source_faces)),
    "faces_equal": faces_equal,
    "geometry_delta": geometry_delta,
    "uv_delta": uv_delta,
    "views": args.views,
    "resolution": args.resolution,
}
report_path = output_obj.with_suffix(".validation.json")
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
if not faces_equal or geometry_delta > 1.0e-6 or uv_delta > 1.0e-6:
    raise RuntimeError(f"Hunyuan topology/UV gate failed: {json.dumps(report, sort_keys=True)}")

print(
    f"HY3D21_PBR_OK result={result} report={report_path} "
    f"geometry_delta={geometry_delta:.9f} uv_delta={uv_delta:.9f}",
    flush=True,
)
