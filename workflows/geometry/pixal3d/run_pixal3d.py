"""Run the official Pixal3D inference path with an alpha-only rembg shim.

The Pixal3D model itself is ungated, but its default pipeline eagerly creates
the separately gated RMBG-2.0 model even when the input already contains a
valid alpha mask.  This wrapper keeps upstream inference intact while making
that optional preprocessing boundary explicit and reproducible.
"""

from argparse import ArgumentParser
import os
from pathlib import Path
import site
import sys

from PIL import Image


PIXAL_ROOT = Path(os.environ.get("PIXAL3D_ROOT", "/path/to/Pixal3D"))

# WSL can inject ~/.local ahead of the isolated Pixal environment even when the
# launcher uses the environment's Python executable.  That silently selected an
# old Transformers build on one workstation.  Remove that ambient path before
# importing Pixal and prefer PyTorch SDPA, which is present in the verified
# environment, unless the caller deliberately selects another backend.
os.environ.setdefault("PYTHONNOUSERSITE", "1")
os.environ.setdefault("ATTN_BACKEND", "sdpa")
user_site = Path(site.getusersitepackages()).resolve()
sys.path[:] = [
    entry
    for entry in sys.path
    if not entry or Path(entry).resolve() != user_site
]
sys.path.insert(0, str(PIXAL_ROOT))

from pixal3d.pipelines import rembg  # noqa: E402


class AlphaOnlyBackground:
    """Stand-in used only when the caller supplied a meaningful alpha mask."""

    def __init__(self, **_kwargs):
        pass

    def to(self, _device):
        return self

    def cuda(self):
        return self

    def cpu(self):
        return self

    def __call__(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGBA" or image.getchannel("A").getextrema() == (255, 255):
            raise RuntimeError(
                "Pixal3D alpha-only mode requires a non-opaque RGBA authority image"
            )
        return image


# Patch the eagerly-created preprocessing dependency, not Pixal3D's generation
# or texture models. The pipeline bypasses this object for non-opaque RGBA input.
rembg.BiRefNet = AlphaOnlyBackground

import numpy as np  # noqa: E402
import inference as upstream  # noqa: E402

# Pixal's exporter rebuilds a surface from its volume and simplifies it to a
# vertex target (1,000,000 upstream). Neither of the compiler's reductions keeps
# a Pixal mesh's hard edges: the voxel rebuild melts them and edge collapse
# wrinkles them, even at 200k triangles. Pixal's own simplifier, asked for
# 100,000 vertices, gave the Frastown skiff 98k clean triangles. Each extra
# target is exported from the same generation, beside the main file and turned
# the way upstream turns it, so the dense mesh and the game mesh are one boat
# and a normal bake from one onto the other lines up.
EXTRA_TARGETS = []
_UPSTREAM_ROTATION = np.array([[-1, 0, 0, 0], [0, 0, -1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=np.float64)
_to_glb = upstream.o_voxel.postprocess.to_glb


def to_glb_with_extra_targets(*args, **kwargs):
    glb = _to_glb(*args, **kwargs)
    for target, path in EXTRA_TARGETS:
        extra = _to_glb(*args, **{**kwargs, "decimation_target": target})
        extra.apply_transform(_UPSTREAM_ROTATION)
        extra.export(path, extension_webp=True)
        print("[Pixal3D] decimation_target {0} -> {1}".format(target, path), flush=True)
    return glb


upstream.o_voxel.postprocess.to_glb = to_glb_with_extra_targets


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fov", type=float, default=-1.0)
    parser.add_argument("--extra-targets", default="",
                        help="Comma-separated vertex targets, each also exported from the same "
                             "generation as <output>-v<target>.glb, e.g. 100000 for a game mesh")
    args = parser.parse_args()
    stem = os.path.splitext(args.output)[0]
    for target in [int(item) for item in args.extra_targets.split(",") if item.strip()]:
        EXTRA_TARGETS.append((target, "{0}-v{1}.glb".format(stem, target)))

    image = Image.open(args.image)
    if image.mode != "RGBA" or image.getchannel("A").getextrema() == (255, 255):
        raise RuntimeError("Authority image must contain a non-opaque alpha channel")

    upstream.run_inference(
        image_path=args.image,
        output_path=args.output,
        seed=args.seed,
        manual_fov=args.fov,
        low_vram=True,
        resolution=args.resolution,
    )


if __name__ == "__main__":
    main()
