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

  7. With --bake-size, every view is shrunk to about a texel a pixel before it
     is baked, so a texel's one sample is an average and not a random pore of a
     view far finer than the sheet (see bake_at_texel_scale). --atlas 8192
     computes and writes the sheet at 8192.

  8. The bake adds each view into the sheet as it is projected, instead of
     keeping every view's sheet-sized projection and merging them all again
     after each view. Same sums, same order, same maps (see
     bake_from_multiview_one_view_at_a_time).

  9. The map from texels to surface points keeps only the texels the mesh
     covers, instead of a dozen sheet-sized scratch buffers (see
     extract_textiles_covered_texels_only). With 8, an 8192 sheet's peak fell
     from 13.2-18 GiB allocated to the diffusion's own, so it fits the same
     12 GB card as a 4096 sheet. The maps are byte for byte the same.

 10. With --inpaint-reach N, the texels no view saw are filled by OpenCV only
     within a band round the mesh's own texels, at least N wide and wider where
     the views left deeper gaps (sheet_fill.reach_for); the rest of the sheet
     takes the mean of the nearest painted texels around it, so the band's
     outer edge is painted colour and not black. Upstream fills the whole sheet
     with OpenCV on one core per map: on an 8192 sheet that holds a half-metre
     section, 99% of it is empty and took 140 s, of a section's 210 s, to fill
     texels the section pass never reads. The mesh's texels near paint come out
     as the whole-sheet fill leaves them; faces no view saw, and the sheet
     outside the band, take other fill colours (reach_for says why that is so).

 11. With --jobs FILE, one process paints a list of meshes, loading the models
     once. The painter seeds every run itself (seed 0, a fresh generator) and
     each job puts the diffusion back on the card as the first found it, so a
     job's maps are those a process of its own would paint. Each job writes its
     own validation report; a job that fails is recorded and the next goes on.

 12. With --maps-only, the GLB is not written: it is the same maps packed by
     Blender's exporter, which the section pass can read as they are.

The UV lock, the local model snapshots, the validation gate and its 1e-6
tolerances match the legacy runner exactly, because those parts were right.

Usage:
  <venv-hy3d21>\\python.exe run_hy3d21_studio.py <mesh.obj> <reference.png> \\
      <output.obj> [--views 12] [--resolution 768] [--atlas 4096|8192] [--legacy-root PATH]
      [--release-stages] [--bake-size N] [--inpaint-reach N]
  <venv-hy3d21>\\python.exe run_hy3d21_studio.py --jobs jobs.json [the same options]
      where jobs.json is a list of {"mesh", "reference", "output_obj", "bake_size"}
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gc
import json
import os
import sys
import time
import traceback
from pathlib import Path

import cv2
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
from sheet_fill import inpaint_near, reach_for

parser = argparse.ArgumentParser()
parser.add_argument("mesh", type=Path, nargs="?")
parser.add_argument("reference", type=Path, nargs="?")
parser.add_argument("output_obj", type=Path, nargs="?")
parser.add_argument("--jobs", type=Path,
                    help="A JSON list of {mesh, reference, output_obj, bake_size}, painted in one process")
parser.add_argument("--inpaint-reach", type=int, default=0,
                    help="Fill the texels no view saw with OpenCV only within this many texels of the "
                         "mesh, and the rest of the sheet from the nearest painted texels. 0 fills the "
                         "whole sheet as upstream does.")
parser.add_argument("--views", type=int, default=6, choices=range(6, 13))
parser.add_argument("--smooth-conditioning-normals", action="store_true",
                    help="Use seam-independent vertex normals for organic character conditioning; default keeps face normals")
parser.add_argument("--resolution", type=int, default=512, choices=(512, 768))
parser.add_argument("--bake-size", type=int, default=0,
                    help="Shrink every view to this many pixels, with an antialiasing filter, before it "
                         "is baked: about one pixel a texel. 0 keeps upstream's sizes.")
parser.add_argument("--atlas", type=int, default=4096, choices=(2048, 4096, 8192),
                    help="The sheet the maps are written at. The pipeline computes 4096 "
                         "either way; 2048 is upstream's downsample.")
parser.add_argument(
    "--legacy-root", type=Path,
    default=Path(os.environ["RAC_LEGACY_ROOT"]) if os.environ.get("RAC_LEGACY_ROOT") else None,
    required=not os.environ.get("RAC_LEGACY_ROOT"))
parser.add_argument(
    "--min-free-gib", type=float, default=21.0,
    help="Refuse to launch below this much free VRAM. Never kills anything.")
parser.add_argument("--maps-only", action="store_true",
                    help="Write the OBJ and its PNG maps, not the GLB. The GLB is the same maps packed by "
                         "Blender's exporter (metal-rough as 255, roughness, metallic); a caller that reads "
                         "the maps saves that export, about 12 s a job at 8192.")
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


def job_list():
    """What to paint: the one mesh named on the command line, or every entry of --jobs.

    Every job is checked before a model is loaded, so a bad entry stops the
    batch before the card is touched rather than part way through it.
    """
    if args.jobs is not None:
        if args.mesh or args.reference or args.output_obj:
            parser.error("give a mesh, a reference and an output, or --jobs, not both")
        entries = json.loads(args.jobs.read_text(encoding="utf-8-sig"))
        if not isinstance(entries, list) or not entries:
            raise RuntimeError("--jobs must hold a list of at least one job: {0}".format(args.jobs))
        jobs = [{"mesh": Path(entry["mesh"]), "reference": Path(entry["reference"]),
                 "output_obj": Path(entry["output_obj"]), "bake_size": int(entry.get("bake_size") or 0)}
                for entry in entries]
    else:
        if not (args.mesh and args.reference and args.output_obj):
            parser.error("give a mesh, a reference and an output, or --jobs")
        jobs = [{"mesh": args.mesh, "reference": args.reference, "output_obj": args.output_obj,
                 "bake_size": args.bake_size}]
    for job in jobs:
        for key in ("mesh", "reference", "output_obj"):
            job[key] = job[key].resolve()
        if job["output_obj"].suffix.lower() != ".obj":
            raise RuntimeError("Hunyuan3D-Paint output must use an .obj path: {0}".format(job["output_obj"]))
        if not job["mesh"].exists() or not job["reference"].exists():
            raise RuntimeError("Missing input: mesh={0} reference={1}".format(job["mesh"], job["reference"]))
        if not 0 <= job["bake_size"] <= 4096:
            raise RuntimeError("A bake size runs from 0 to 4096: {0}".format(job["bake_size"]))
    return jobs


JOBS = job_list()
_original_mean_vertex_normals = trimesh.geometry.mean_vertex_normals


def take_source(job):
    """The mesh as authored, kept for the gate, with its normals shared across UV seams."""
    job["output_obj"].parent.mkdir(parents=True, exist_ok=True)
    source = load_mesh(job["mesh"])
    vertices = np.asarray(source.vertices, dtype=np.float64).copy()
    faces = np.asarray(source.faces, dtype=np.int64).copy()
    uv = np.asarray(source.visual.uv, dtype=np.float64).copy()
    # Hunyuan recomputes vertex normals from the UV-split transport. Share normals
    # at exact positions without collapsing any authored geometry or UV corners.
    # Installed on upstream's own function each time, never on the last job's.
    trimesh.geometry.mean_vertex_normals = _original_mean_vertex_normals
    normal_proxy = install_seam_normal_repair(trimesh.geometry, vertices, faces)
    print('HY3D21_SEAM_NORMALS', normal_proxy, flush=True)
    return vertices, faces, uv


if not torch.cuda.is_available():
    raise RuntimeError("CUDA is required for Hunyuan3D-Paint 2.1")
free_bytes, total_bytes = torch.cuda.mem_get_info()
print("HY3D21_PREFLIGHT gpu={0} free_gib={1:.2f} total_gib={2:.2f} jobs={3}".format(
          torch.cuda.get_device_name(0), free_bytes / 2 ** 30, total_bytes / 2 ** 30, len(JOBS)),
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


def inpaint_near_the_mesh(render, texture, mask, reach):
    """Upstream's OpenCV fill within `reach` texels of the mesh (sheet_fill.inpaint_near).

    The mesh's own texels are the ones the texel map found covered. If the
    paint lies off them, something does not line up, and the whole sheet is
    filled as upstream does rather than guessing.
    """
    texture_np = texture.cpu().numpy() if isinstance(texture, torch.Tensor) else np.asarray(texture)
    if isinstance(mask, torch.Tensor):
        mask = (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8)
    image = (texture_np * 255).astype(np.uint8)
    known = mask == 255
    footprint = (render.texture_indices >= 0).cpu().numpy()
    stray = int((known & ~footprint).sum()) if footprint.shape == known.shape else -1
    if stray < 0 or stray > 0.01 * max(int(known.sum()), 1):
        # The mesh's texels do not line up with the paint: fill the whole sheet.
        print("HY3D21_INPAINT whole sheet: the mesh's texels do not match the paint "
              "(shape {0} vs {1}, {2} painted texels off the mesh)".format(footprint.shape, known.shape, stray),
              flush=True)
        return cv2.inpaint(image, 255 - mask, 3, cv2.INPAINT_NS)
    reach, deepest, unseen = reach_for(mask, footprint, reach)
    filled, near = inpaint_near(image, mask, footprint, reach)
    print("HY3D21_INPAINT reach={0} deepest_gap={1:.1f} unseen_face_texels={2} texels_filled_near_mesh={3} "
          "of_sheet={4}".format(reach, deepest, unseen, near, int((~known).sum())), flush=True)
    return filled


def uv_inpaint_cv_fallback(self, texture, mask, **inpaint_kwargs):
    if args.inpaint_reach > 0 and not inpaint_kwargs:
        return inpaint_near_the_mesh(self, texture, mask, args.inpaint_reach)
    return _original_uv_inpaint(self, texture, mask, vertex_inpaint=False,
                                **inpaint_kwargs)


MeshRender.uv_inpaint = uv_inpaint_cv_fallback

# --- patch 4b: bake one view at a time ---------------------------------------
from utils.pipeline_utils import ViewProcessor  # noqa: E402


@torch.no_grad()
def bake_from_multiview_one_view_at_a_time(self, views, camera_elevs, camera_azims, view_weights):
    """Upstream's bake, with each view added in as it is projected.

    Upstream keeps every view's projection (a texture, a weight map and an
    unused boundary map, each the size of the sheet) in lists, and calls the
    merge inside its loop, so the lists are merged from scratch after every
    view: 78 passes for 12 views where 12 do. At an 8192 sheet the lists were
    the whole run's peak, 13 to 18 GiB allocated, over a 12 GB card. Here the
    same sums are taken in the same order, view by view, with the same rule
    for skipping a view whose texels are already 99% painted, so the merged
    texture and mask are the ones upstream's last pass returns, byte for byte.
    """
    render = self.render
    texture_merge = trust_map_merge = None
    for view, camera_elev, camera_azim, weight in zip(views, camera_elevs, camera_azims, view_weights):
        texture, cos_map, _ = render.back_project(view, camera_elev, camera_azim)
        cos_map = weight * (cos_map ** self.config.bake_exp)
        if texture_merge is None:
            texture_merge = torch.zeros(render.texture_size + (texture.shape[-1],)).to(render.device)
            trust_map_merge = torch.zeros(render.texture_size + (1,)).to(render.device)
        view_sum = (cos_map > 0).sum()
        painted_sum = ((cos_map > 0) * (trust_map_merge > 0)).sum()
        if not painted_sum / view_sum > 0.99:
            texture_merge += texture * cos_map
            trust_map_merge += cos_map
        del texture, cos_map
    texture_merge = texture_merge / torch.clamp(trust_map_merge, min=1e-8)
    return texture_merge, trust_map_merge > 1e-8


ViewProcessor.bake_from_multiview = bake_from_multiview_one_view_at_a_time

# --- patch 4c: map texels to the surface without sheet-sized scratch ----------


@torch.no_grad()
def extract_textiles_covered_texels_only(self):
    """Upstream's texel-to-surface map, holding only the texels the mesh covers.

    Upstream builds it from a dozen sheet-sized buffers at once: the raster,
    positions and smoothed normals for every texel, a 64-bit row and column for
    every texel, then masks them to the covered ones. At an 8192 sheet that
    was 7.2 GiB on top of the models already on the card, the run's peak (13.2
    GiB). The smoothed normals are wasted too: upstream then overwrites every
    covered texel's normal with its face's flat normal. Here the covered texels
    are found once from the raster, and only their positions, face normals and
    rows and columns are kept, in upstream's order, so every map that follows
    is byte for byte the same.
    """
    vertex_count = self.vtx_uv.shape[0]
    vtx_uv = torch.cat(
        (self.vtx_uv, torch.zeros_like(self.vtx_uv[:, 0:1]), torch.ones_like(self.vtx_uv[:, 0:1])), axis=1)
    vtx_uv = vtx_uv.view(1, vertex_count, 4) * 2 - 1
    rast_out, _ = self.raster_rasterize(vtx_uv, self.uv_idx, resolution=self.texture_size)
    height, width = self.texture_size
    face_of_texel = rast_out[0, ..., 3].reshape(-1)
    covered = torch.nonzero(face_of_texel > 0).squeeze(1)
    faces = (face_of_texel[covered] - 1).long()
    barycentric = rast_out[0, ..., :3].reshape(-1, 3)[covered]
    del rast_out, face_of_texel
    # custom_rasterizer.interpolate's own arithmetic -- the corners' values
    # weighted by the barycentrics and summed over the corners -- on the covered
    # texels only, a slice at a time: it built (8192 x 8192 x 3 x 3) index and
    # value tensors for the whole sheet, 6.4 GiB, to keep a third of them.
    corners = self.pos_idx.long()
    position = torch.empty((covered.shape[0], 3), dtype=self.vtx_pos.dtype, device=self.device)
    step = 1 << 22
    for start in range(0, covered.shape[0], step):
        stop = min(start + step, covered.shape[0])
        values = self.vtx_pos[corners[faces[start:stop]]]
        position[start:stop] = torch.sum(barycentric[start:stop].view(-1, 3, 1) * values, axis=-2)
    del barycentric
    v0 = self.vtx_pos[self.pos_idx[:, 0], :]
    v1 = self.vtx_pos[self.pos_idx[:, 1], :]
    v2 = self.vtx_pos[self.pos_idx[:, 2], :]
    face_normals = torch.nn.functional.normalize(torch.cross(v1 - v0, v2 - v0, dim=-1), dim=-1)
    texture_indices = torch.full((height, width), -1, device=self.device, dtype=torch.long)
    texture_indices.view(-1)[covered] = torch.arange(covered.shape[0], device=self.device, dtype=torch.long)
    self.tex_position = torch.cat((position, torch.ones_like(position[:, :1])), axis=-1)
    self.tex_normal = face_normals.reshape(-1, 3)[faces]
    self.tex_grid = torch.stack((covered // width, covered % width), -1)
    self.texture_indices = texture_indices


MeshRender.extract_textiles = extract_textiles_covered_texels_only


def inpaint_while_baking(painter):
    """Start each map's CPU inpaint as soon as it is baked.

    Upstream bakes base colour and metal-rough on the GPU, then inpaints them
    one after the other on one CPU core: about 18 s each at a 4096 atlas.
    OpenCV releases the GIL, so the two run side by side here, on the same
    inputs and the same function. The result is byte-identical.
    """
    view_processor = painter.view_processor
    bake, inpaint = view_processor.bake_from_multiview, view_processor.texture_inpaint
    workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rac-inpaint")
    started = {}

    def bake_then_start_inpaint(*bake_args, **bake_kwargs):
        texture, mask = bake(*bake_args, **bake_kwargs)
        # The exact mask upstream derives before calling texture_inpaint.
        mask_np = (mask.squeeze(-1).cpu().numpy() * 255).astype(np.uint8)
        started[id(texture)] = (texture, mask_np, workers.submit(inpaint, texture, mask_np))
        return texture, mask

    def finish_inpaint(texture, mask, *inpaint_args, **inpaint_kwargs):
        entry = started.pop(id(texture), None)
        if (entry is None or entry[0] is not texture or inpaint_args or inpaint_kwargs
                or not np.array_equal(entry[1], mask)):
            return inpaint(texture, mask, *inpaint_args, **inpaint_kwargs)
        return entry[2].result()

    view_processor.bake_from_multiview = bake_then_start_inpaint
    view_processor.texture_inpaint = finish_inpaint

def bake_at_texel_scale(painter, size_of):
    """Bake each view from about one pixel a texel, not from far finer.

    The bake gives each texel one bilinear sample of a view. Upstream bakes from
    the views as upscaled four times (3072 pixels for 768), and its resize to
    `render_size` reaches only the first two views: the loop counts the two map
    kinds, not the twelve views. On a whole model a 3072 view is near a texel a
    pixel and the sample is smooth. On a half-metre section the same view is
    0.2 mm a pixel against 1.75 mm texels, each texel takes one pore at random,
    and the skiff's wood came out as broken dashes and single-texel specks.
    Shrinking each view first, with an antialiasing filter, makes the sample an
    average: on the same section the speckle measure halved and the grain ran as
    continuous lines again. At an 8192 sheet it is the painter's own detail.

    `size_of()` is read at each bake, so every job of a batch has its own size;
    0 bakes the views as upstream sizes them.
    """
    from PIL import Image as PilImage  # noqa: PLC0415

    baked = painter.view_processor.bake_from_multiview

    def bake_shrunk(images, *bake_args, **bake_kwargs):
        size = size_of()
        if size:
            images = [image.resize((size, size), PilImage.LANCZOS) for image in images]
        return baked(images, *bake_args, **bake_kwargs)

    painter.view_processor.bake_from_multiview = bake_shrunk


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

    def rearm():
        """Put the diffusion back on the card as the first job found it, for the next job.

        After a job the diffusion pipeline and DINO wait in host memory. The
        first job began with both on the card and the never-called text
        encoder in host memory; so does every job after it.
        """
        multiview.pipeline.to(execution_device)
        if getattr(multiview.pipeline.unet, "use_learned_text_clip", False):
            multiview.pipeline.text_encoder.to("cpu")
        if dino is not None:
            dino.to(execution_device)
        gc.collect()
        torch.cuda.empty_cache()

    return rearm


config = Hunyuan3DPaintConfig(args.views, args.resolution)
if args.atlas == 8192:
    # Upstream computes at 4096 whatever is asked; a sheet of 8192 is computed at 8192.
    config.texture_size = 8192
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
    inpaint_while_baking(painter)
    current = {"bake_size": 0}
    bake_at_texel_scale(painter, lambda: current["bake_size"])
    rearm = release_between_stages(painter) if args.release_stages else None
    if args.smooth_conditioning_normals:
        painter.render.shader_type = 'vertex'
    print('HY3D21_CONDITIONING_NORMALS', painter.render.shader_type, flush=True)
finally:
    os.chdir(previous_cwd)


def paint(job, number):
    """One mesh through the painter, its gate checked and its report written."""
    started = time.monotonic()
    mesh_path, reference_path, output_obj = job["mesh"], job["reference"], job["output_obj"]
    print("HY3D21_JOB_START number={0} of={1} mesh={2}".format(number + 1, len(JOBS), mesh_path), flush=True)
    source_vertices, source_faces, source_uv = take_source(job)
    print("HY3D21_JOB_MESH vertices={0} triangles={1}".format(len(source_vertices), len(source_faces)),
          flush=True)
    current["bake_size"] = job["bake_size"]
    if job["bake_size"]:
        print("HY3D21_BAKE_SIZE", job["bake_size"], flush=True)
    if rearm is not None and number > 0:
        rearm()
    torch.cuda.reset_peak_memory_stats()
    os.chdir(UPSTREAM)
    try:
        result = painter(
            mesh_path=str(mesh_path),
            image_path=str(reference_path),
            output_mesh_path=str(output_obj),
            use_remesh=False,
            save_glb=not args.maps_only,
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
        "output_glb": None if args.maps_only else str(output_obj.with_suffix(".glb")),
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
        "bake_size": job["bake_size"],
        "inpaint_reach": args.inpaint_reach,
        "downsample_disabled": args.atlas != 2048,
        "map_format": "png",
        "maps": written,
        "release_stages": args.release_stages,
        "batch": {"jobs": len(JOBS), "number": number + 1} if args.jobs is not None else None,
        "seconds": round(time.monotonic() - started, 1),
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
          "uv_delta={3:.9f} seconds={4}".format(result, report_path, geometry_delta, uv_delta,
                                                report["seconds"]),
          flush=True)


if args.jobs is None:
    paint(JOBS[0], 0)
else:
    # A job that fails is recorded beside its output and the batch goes on: it
    # is not retried here, and the caller sees which jobs have no report.
    failures = 0
    for number, job in enumerate(JOBS):
        try:
            paint(job, number)
        except Exception as problem:  # noqa: BLE001 -- recorded, then the next job
            failures += 1
            job["output_obj"].with_suffix(".failure.json").write_text(json.dumps({
                "mesh": str(job["mesh"]), "error": "{0}: {1}".format(type(problem).__name__, problem),
                "traceback": traceback.format_exc()}, indent=2) + "\n", encoding="utf-8")
            print("HY3D21_JOB_FAILED number={0} error={1}".format(number + 1, problem), flush=True)
    print("HY3D21_BATCH_DONE jobs={0} failed={1}".format(len(JOBS), failures), flush=True)
    if failures:
        sys.exit(1)
