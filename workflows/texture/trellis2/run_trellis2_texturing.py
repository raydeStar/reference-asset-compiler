"""Texture an accepted game mesh with TRELLIS.2 while locking its topology.

Run this script inside the isolated WSL TRELLIS.2 environment. TRELLIS.2
normalizes mesh coordinates for inference, so this wrapper restores the exact
source vertices before export and refuses any face-order or vertex-count drift.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
from PIL import Image
import torch
import trimesh

from trellis2.pipelines import Trellis2TexturingPipeline, rembg


class AlphaOnlyBackgroundModel:
    """Refuse background removal while satisfying TRELLIS' loader contract."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def to(self, device: object) -> "AlphaOnlyBackgroundModel":
        return self

    def cpu(self) -> "AlphaOnlyBackgroundModel":
        return self

    def __call__(self, image: Image.Image) -> Image.Image:
        raise RuntimeError(
            "Background removal was requested despite a required pre-segmented RGBA reference"
        )


def bridge_dinov3_encoder_layers(pipeline: Trellis2TexturingPipeline) -> str:
    """Bridge the layer path used by TRELLIS to the installed Transformers API."""
    dinov3 = pipeline.image_cond_model.model
    if hasattr(dinov3, "layer"):
        return "native-layer"

    encoder = getattr(dinov3, "model", None)
    layers = getattr(encoder, "layer", None)
    if layers is None:
        raise RuntimeError(
            "Unsupported DINOv3 model layout: expected `.layer` or `.model.layer`"
        )

    # TRELLIS manually iterates the encoder blocks. Transformers 5.x nests
    # those same blocks under DINOv3ViTModel.model, so provide the legacy path
    # expected by the official extractor without replacing any computation.
    dinov3.layer = layers
    return "transformers-5-model-layer-alias"


def preserve_source_uv_during_preprocess(pipeline: Trellis2TexturingPipeline) -> None:
    """Keep source UVs so TRELLIS does not unwrap and split seam vertices."""
    original_preprocess = pipeline.preprocess_mesh

    def preprocess_with_uv(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        processed = original_preprocess(mesh)
        if len(processed.vertices) != len(mesh.vertices) or not np.array_equal(
            np.asarray(processed.faces), np.asarray(mesh.faces)
        ):
            raise RuntimeError("TRELLIS.2 preprocessing changed source topology")
        if mesh.visual.uv is None:
            raise RuntimeError("Source UVs disappeared before TRELLIS.2 preprocessing")
        processed.visual = trimesh.visual.TextureVisuals(
            uv=np.asarray(mesh.visual.uv, dtype=np.float64).copy()
        )
        return processed

    pipeline.preprocess_mesh = preprocess_with_uv


def allow_normal_axis_conversion(pipeline: Trellis2TexturingPipeline) -> None:
    """Make cached Trimesh normals writable for TRELLIS' GLB axis conversion."""
    original_postprocess = pipeline.postprocess_mesh

    def postprocess_with_writable_normals(
        mesh: trimesh.Trimesh,
        pbr_voxel: object,
        resolution: int = 1024,
        texture_size: int = 1024,
    ) -> trimesh.Trimesh:
        normals = mesh.vertex_normals
        if not normals.flags.writeable:
            normals.setflags(write=True)
        return original_postprocess(mesh, pbr_voxel, resolution, texture_size)

    pipeline.postprocess_mesh = postprocess_with_writable_normals


def load_single_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, process=False)
    if isinstance(loaded, trimesh.Scene):
        geometries = list(loaded.geometry.values())
        if len(geometries) != 1:
            raise RuntimeError(f"Expected one mesh in {path}, found {len(geometries)}")
        # Apply the GLB node transform before conditioning. Pulling the raw
        # geometry would silently rotate this character onto its face.
        loaded = loaded.to_geometry()
    if not isinstance(loaded, trimesh.Trimesh):
        raise RuntimeError(f"Unsupported mesh payload: {type(loaded).__name__}")
    if loaded.visual.uv is None:
        raise RuntimeError("Source mesh has no UV coordinates")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--resolution", type=int, choices=(512, 1024), default=512)
    parser.add_argument("--texture-size", type=int, choices=(1024, 2048, 4096), default=2048)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("TRELLIS.2 requires CUDA")
    free_gib, total_gib = (value / 2**30 for value in torch.cuda.mem_get_info())
    print(
        f"TRELLIS2_PREFLIGHT gpu={torch.cuda.get_device_name()} "
        f"free_gib={free_gib:.2f} total_gib={total_gib:.2f}",
        flush=True,
    )

    source = load_single_mesh(args.mesh.resolve())
    source_vertices = np.asarray(source.vertices, dtype=np.float64).copy()
    source_faces = np.asarray(source.faces, dtype=np.int64).copy()
    source_uv = np.asarray(source.visual.uv, dtype=np.float64).copy()
    reference = Image.open(args.reference.resolve()).convert("RGBA")
    alpha = np.asarray(reference.getchannel("A"))
    if np.all(alpha == 255):
        raise RuntimeError(
            "Reference must contain a meaningful alpha mask. Pre-segment it before running "
            "TRELLIS.2 so this wrapper does not depend on the gated BRIA RMBG model."
        )

    # TRELLIS constructs its background-removal model unconditionally even
    # though preprocess_image correctly skips it for RGBA input. Replace only
    # that constructor with a fail-closed stub; the alpha mask remains the
    # sole segmentation authority.
    rembg.BiRefNet = AlphaOnlyBackgroundModel

    pipeline = Trellis2TexturingPipeline.from_pretrained(
        "microsoft/TRELLIS.2-4B",
        config_file="texturing_pipeline.json",
    )
    dinov3_compatibility = bridge_dinov3_encoder_layers(pipeline)
    preserve_source_uv_during_preprocess(pipeline)
    allow_normal_axis_conversion(pipeline)
    print(f"TRELLIS2_DINOV3_COMPAT mode={dinov3_compatibility}", flush=True)
    pipeline.cuda()
    textured = pipeline.run(
        source.copy(),
        reference,
        seed=args.seed,
        resolution=args.resolution,
        texture_size=args.texture_size,
    )

    faces_equal = np.array_equal(np.asarray(textured.faces), source_faces)
    if len(textured.vertices) != len(source_vertices) or not faces_equal:
        raise RuntimeError(
            "TRELLIS.2 topology drift: "
            f"vertices={len(textured.vertices)}/{len(source_vertices)} "
            f"faces_equal={faces_equal}"
        )

    # TRELLIS.2 deliberately normalizes the mesh for inference. Keep its PBR
    # material and UV export convention, but restore the accepted game shell.
    textured.vertices = source_vertices
    output_uv = np.asarray(textured.visual.uv, dtype=np.float64)
    uv_exact_delta = float(np.max(np.abs(output_uv - source_uv)))
    uv_vflip_delta = float(
        np.max(np.abs(output_uv - np.column_stack((source_uv[:, 0], 1.0 - source_uv[:, 1]))))
    )
    if min(uv_exact_delta, uv_vflip_delta) > 1.0e-6:
        raise RuntimeError(
            f"Unexpected TRELLIS.2 UV drift: exact={uv_exact_delta} vflip={uv_vflip_delta}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    textured.export(args.output, extension_webp=False)
    report = {
        "source_mesh": str(args.mesh.resolve()),
        "reference": str(args.reference.resolve()),
        "reference_alpha_range": [int(alpha.min()), int(alpha.max())],
        "background_removal": "presegmented-rgba",
        "dinov3_compatibility": dinov3_compatibility,
        "topology_compatibility": "preserve-source-uv-during-preprocess",
        "trimesh_compatibility": "writable-cached-vertex-normals",
        "output": str(args.output.resolve()),
        "vertices": len(source_vertices),
        "triangles": len(source_faces),
        "faces_equal": faces_equal,
        "geometry_delta_after_restore": float(
            np.max(np.abs(np.asarray(textured.vertices) - source_vertices))
        ),
        "uv_exact_delta": uv_exact_delta,
        "uv_vflip_delta": uv_vflip_delta,
        "resolution": args.resolution,
        "texture_size": args.texture_size,
        "seed": args.seed,
        "free_gib_at_start": free_gib,
    }
    report_path = args.output.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"TRELLIS2_TEXTURE_OK report={report_path} {json.dumps(report)}", flush=True)


if __name__ == "__main__":
    main()
