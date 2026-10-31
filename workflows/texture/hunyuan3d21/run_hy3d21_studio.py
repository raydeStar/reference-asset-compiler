"""Hunyuan3D-Paint 2.1 for a studio: full atlas, lossless maps, topology kept.

The hash-verified legacy runner (`run_hy3d21_pbr.py`) stays untouched. This is
the variant a browser studio launches, and it patches five upstream behaviours
rather than editing them in place:

  1. `textureGenPipeline` calls `trimesh.load(path)` with processing ON, which
     can merge vertices and break the face-order contract (304 vertices went
     missing on one character). Loading with process=False keeps the mesh as
     authored. NOT with maintain_order=True, which the hi-res variant used:
     that keeps the OBJ's 9,000 positions instead of splitting them per UV
     corner, so every vertex on a seam carries one island's UV into the faces
     of another. On a Smart-Projected ninja a third of all faces then spanned
     the sheet, and the paint on them was whatever the sliver crossed. That is
     what "the jacket's olive spread across the face" was.

  2. The pipeline configures `texture_size = 4096` and then saves with
     `downsample=True`, which cv2-resizes every map to half. Twelve views at
     768, each enhanced four times over and baked at 2048, carry more than a
     2048 atlas can hold; `--atlas 4096` keeps what was computed.

  3. Every map is written as JPEG. The base colour is the one map somebody
     looks at, and a JPEG here is the first of what became three lossy passes
     by the time a model reached a browser. Written as PNG instead: the next
     stage decides what to compress, once, knowing what it is compressing.

  4. Upstream's optional mesh inpaint module is absent on Windows; the OpenCV
     fallback is used, as the legacy runner does.

  5. Painter normals are averaged on an exact-position proxy and expanded back
     to the original indices. UV seams must not become lighting in the paint.

  6. With --release-stages, the VAE decodes the generated views one at a
     time instead of all albedo and metal-rough views in one batch, which was
     the whole run's peak (21.1 GiB allocated at 12 views x 768; the reserved
     pool reached 35 GiB and spilled into shared memory). The multiview
     pipeline and DINO then move to the CPU before the upscale and bake, and
     the allocator cache is emptied after each RealESRGAN upscale. Paint is
     deterministic, so the maps are compared byte for byte against a resident run.
     One-shot helpers leave the GPU before sampling: the CLIP text encoder is
     never called (the UNet uses learned prompt embeddings), and DINO encodes
     the reference once, before the first diffusion step.

     Each UNet feed-forward runs one image at a time, the multiview attention
     runs one (guidance, material) sequence at a time, and the idle UNet waits
     in host memory while the VAE encodes the reference and the normal and
     position views, so 12 views x 768 fits a 10 GiB allocator (a 12 GB card).

The UV lock, the local model snapshots, the validation gate and its 1e-6
tolerances match the legacy runner exactly, because those parts were right.

Usage:
  <venv-hy3d21>\\python.exe run_hy3d21_studio.py <mesh.obj> <reference.png> \\
      <output.obj> [--views 12] [--resolution 768] [--atlas 4096] [--legacy-root PATH]
      [--release-stages]
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path

import huggingface_hub
import numpy as np

# Read when CUDA first allocates. Large blocks are not split and freed cache is
# reclaimed before the pool is full, so a 12 GB card is not lost to
# fragmentation (0.8 GiB sat free in pieces when a 540 MiB request failed).
# Placement only: what is computed does not change.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "garbage_collection_threshold:0.8,max_split_size_mb:256")
import torch  # noqa: E402
import trimesh
from seam_normals import install_seam_normal_repair

parser = argparse.ArgumentParser()
parser.add_argument("mesh", type=Path)
parser.add_argument("reference", type=Path)
parser.add_argument("output_obj", type=Path)
parser.add_argument("--views", type=int, default=6, choices=range(6, 13))
parser.add_argument("--smooth-conditioning-normals", action="store_true",
                    help="Use seam-independent vertex normals for organic character conditioning; default keeps face normals")
parser.add_argument("--resolution", type=int, default=512, choices=(512, 768))
parser.add_argument("--atlas", type=int, default=4096, choices=(2048, 4096),
                    help="The sheet the maps are written at. The pipeline computes 4096 "
                         "either way; 2048 is upstream's downsample.")
parser.add_argument(
    "--legacy-root", type=Path,
    default=Path(os.environ["RAC_LEGACY_ROOT"]) if os.environ.get("RAC_LEGACY_ROOT") else None,
    required=not os.environ.get("RAC_LEGACY_ROOT"))
parser.add_argument(
    "--min-free-gib", type=float, default=21.0,
    help="Refuse to launch below this much free VRAM. Never kills anything.")
parser.add_argument("--release-stages", action="store_true",
                    help="Move diffusion weights off the GPU before the upscale and bake.")
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
from DifferentiableRenderer import mesh_utils  # noqa: E402
from DifferentiableRenderer.MeshRender import MeshRender  # noqa: E402


def load_mesh(path):
    """Load exactly the way the pipeline does, so the gate compares like with like.

    force="mesh" and no merging: trimesh splits a vertex wherever its UV
    differs, which is the only representation in which one UV per vertex can
    carry a seam at all.
    """
    mesh = trimesh.load(path, force="mesh", process=False)
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

# Hunyuan recomputes vertex normals from the UV-split transport. Share normals
# at exact positions without collapsing any authored geometry or UV corners.
normal_proxy = install_seam_normal_repair(trimesh.geometry, source_vertices, source_faces)
print('HY3D21_SEAM_NORMALS', normal_proxy, flush=True)

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
# Windows drivers back an over-full card with shared system memory instead of
# failing the allocation, so the caching allocator never has to reuse its
# cache: one released astrolabe run reserved 26 GiB on a 24 GiB card while
# using 7, and crawled for two hours. A pool budget of the free memory makes
# PyTorch recycle its cache first, as it already does on a 12 GB card.
# Placement only. Resident runs exceed physical VRAM by design and are left as
# they were.
pool_budget_bytes = None
if args.release_stages:
    pool_budget_bytes = max(free_bytes - 512 * 2 ** 20, 0)
    torch.cuda.set_per_process_memory_fraction(pool_budget_bytes / total_bytes)
    print("HY3D21_POOL_BUDGET gib={0:.2f}".format(pool_budget_bytes / 2 ** 30), flush=True)

realesrgan = PAINT_ROOT / "ckpt" / "RealESRGAN_x4plus.pth"
if not realesrgan.exists() or realesrgan.stat().st_size != 67_040_989:
    raise RuntimeError("RealESRGAN checkpoint missing or incomplete: {0}".format(realesrgan))

# --- patch 1: never rewrap the UVs -----------------------------------------
hy3d_pipeline.mesh_uv_wrap = preserve_existing_uv

# --- patch 1b: load the mesh without merging authored vertex splits --------
_original_trimesh_load = hy3d_pipeline.trimesh.load


def load_without_processing(*load_args, **load_kwargs):
    load_kwargs.setdefault("process", False)
    load_kwargs.setdefault("force", "mesh")
    return _original_trimesh_load(*load_args, **load_kwargs)


hy3d_pipeline.trimesh.load = load_without_processing

# --- patch 2: keep the atlas the caller asked for ---------------------------
_original_save_mesh = MeshRender.save_mesh


def save_mesh_at_requested_atlas(self, mesh_path, downsample=False):
    return _original_save_mesh(self, mesh_path, downsample=(args.atlas == 2048))


MeshRender.save_mesh = save_mesh_at_requested_atlas

# --- patch 3: lossless maps -------------------------------------------------
_original_save_texture_map = mesh_utils._save_texture_map


def save_texture_map_as_png(texture, base_path, suffix="", image_format=".jpg", color_convert=None):
    return _original_save_texture_map(texture, base_path, suffix, ".png", color_convert)


mesh_utils._save_texture_map = save_texture_map_as_png

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

def release_between_stages(painter):
    multiview, upscale = painter.models["multiview_model"], painter.models["super_model"]
    for name, component in multiview.pipeline.components.items():
        if isinstance(component, torch.nn.Module):
            size = sum(p.numel() * p.element_size() for p in component.parameters())
            print("HY3D21_COMPONENT {0} gib={1:.3f} device={2}".format(
                name, size / 2 ** 30, next(component.parameters()).device), flush=True)
    execution_device = multiview.pipeline.unet.device
    if getattr(multiview.pipeline.unet, "use_learned_text_clip", False):
        # diffusers derives `device` from the first module in a *set* of
        # component names. With the encoder on the CPU, some processes would
        # sample on the CPU, and upstream seeds its noise generator on
        # `pipeline.device`, so others would draw different noise: a re-rolled
        # paint. Pin both to the GPU the pipeline runs on.
        pipeline_type = type(multiview.pipeline)
        pipeline_type._execution_device = property(lambda _: execution_device)
        pipeline_type.device = property(lambda _: execution_device)
        multiview.pipeline.text_encoder.to("cpu")
    dino = getattr(multiview, "dino_v2", None)
    if dino is not None:
        def encode_reference_then_release(*dino_args, **dino_kwargs):
            states = dino(*dino_args, **dino_kwargs)
            dino.to("cpu")
            torch.cuda.empty_cache()
            return states

        multiview.dino_v2 = encode_reference_then_release
    # Run each UNet feed-forward one image at a time. At 9-12 views x 768 its
    # 4x-wide intermediate for every view at once exceeded 10 GiB.
    chunked = 0
    for module in multiview.pipeline.unet.modules():
        if hasattr(type(module), "set_chunk_feed_forward"):
            module.set_chunk_feed_forward(1, 0)
            chunked += 1
    print("HY3D21_FEED_FORWARD_CHUNKED blocks={0}".format(chunked), flush=True)
    # The multiview attention joins every view's tokens into one sequence per
    # (guidance branch, material) pair; the pairs never attend to each other,
    # so run them one at a time. RoPE angles come from the pair's voxel
    # indices, sliced to match and cached beside upstream's own cache.
    split = 0
    for module in multiview.pipeline.unet.modules():
        attention = module._modules.get("attn_multiview")
        if attention is None:
            continue
        attend = attention.forward

        def attend_one_sequence_at_a_time(hidden_states, encoder_hidden_states=None, position_indices=None,
                                          n_pbrs=1, _attend=attend, **attend_kwargs):
            if hidden_states.shape[0] == 1:
                return _attend(hidden_states, encoder_hidden_states=encoder_hidden_states,
                               position_indices=position_indices, n_pbrs=n_pbrs, **attend_kwargs)
            outputs = []
            for index in range(hidden_states.shape[0]):
                indices = None
                if position_indices is not None:
                    batch = index // n_pbrs
                    indices = position_indices.setdefault(("rac_sequence", batch), {
                        "voxel_indices": position_indices["voxel_indices"][batch:batch + 1],
                        "voxel_resolution": position_indices["voxel_resolution"]})
                context = None if encoder_hidden_states is None else encoder_hidden_states[index:index + 1]
                outputs.append(_attend(hidden_states[index:index + 1], encoder_hidden_states=context,
                                       position_indices=indices, n_pbrs=1, **attend_kwargs))
            return torch.cat(outputs)

        attention.forward = attend_one_sequence_at_a_time
        split += 1
    print("HY3D21_MULTIVIEW_ATTENTION_SPLIT blocks={0}".format(split), flush=True)
    pipeline = multiview.pipeline
    encode_images = pipeline.encode_images

    def encode_without_unet(*encode_args, **encode_kwargs):
        # The batched condition encodes peak while 3.7 GiB of UNet sits idle.
        pipeline.unet.to("cpu")
        torch.cuda.empty_cache()
        try:
            return encode_images(*encode_args, **encode_kwargs)
        finally:
            pipeline.unet.to(execution_device)

    pipeline.encode_images = encode_without_unet
    torch.cuda.empty_cache()
    vae = multiview.pipeline.vae
    decode = vae.decode

    def decode_one_at_a_time(*decode_args, **decode_kwargs):
        # Slice the decode only. Slicing the reference encode as well shifts
        # the sampled latents and with them the whole diffusion trajectory.
        vae.use_slicing = True
        try:
            return decode(*decode_args, **decode_kwargs)
        finally:
            vae.use_slicing = False

    vae.decode = decode_one_at_a_time

    def generate_then_release(*call_args, **call_kwargs):
        views = multiview(*call_args, **call_kwargs)
        multiview.pipeline.to("cpu")
        gc.collect()
        torch.cuda.empty_cache()
        return views

    def upscale_then_trim(image):
        enhanced = upscale(image)
        torch.cuda.empty_cache()
        return enhanced

    painter.models["multiview_model"] = generate_then_release
    painter.models["super_model"] = upscale_then_trim


config = Hunyuan3DPaintConfig(args.views, args.resolution)
config.multiview_cfg_path = str(PAINT_ROOT / "cfgs" / "hunyuan-paint-pbr.yaml")
config.custom_pipeline = str(PAINT_ROOT / "hunyuanpaintpbr")
config.realesrgan_ckpt_path = str(realesrgan)
config.dino_ckpt_path = str(dino_snapshot)
print("HY3D21_ATLAS texture_size={0} render_size={1} written_at={2} format=png".format(
    config.texture_size, config.render_size, args.atlas), flush=True)

previous_cwd = Path.cwd()
os.chdir(UPSTREAM)
try:
    painter = Hunyuan3DPaintPipeline(config)
    torch.cuda.reset_peak_memory_stats()
    if args.release_stages:
        release_between_stages(painter)
    if args.smooth_conditioning_normals:
        painter.render.shader_type = 'vertex'
    print('HY3D21_CONDITIONING_NORMALS', painter.render.shader_type, flush=True)
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

written = sorted(p.name for p in output_obj.parent.glob(output_obj.stem + "*.png"))
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
    "atlas": args.atlas,
    "downsample_disabled": args.atlas != 2048,
    "map_format": "png",
    "maps": written,
    "release_stages": args.release_stages,
    "vram": {"device": torch.cuda.get_device_name(0), "free_bytes_at_start": int(free_bytes),
             "pool_budget_bytes": pool_budget_bytes,
             "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
             "peak_reserved_bytes": int(torch.cuda.max_memory_reserved())},
}
report_path = output_obj.with_suffix(".validation.json")
report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

if not faces_equal or geometry_delta > 1.0e-6 or uv_delta > 1.0e-6:
    raise RuntimeError("Hunyuan topology/UV gate failed: {0}".format(
        json.dumps(report, sort_keys=True)))

print("HY3D21_PBR_OK result={0} report={1} geometry_delta={2:.9f} "
      "uv_delta={3:.9f}".format(result, report_path, geometry_delta, uv_delta),
      flush=True)
