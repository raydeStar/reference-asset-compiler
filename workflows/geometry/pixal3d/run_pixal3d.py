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

import inference as upstream  # noqa: E402


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fov", type=float, default=-1.0)
    args = parser.parse_args()

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
