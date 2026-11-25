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

# Take ownership in the actual Linux worker. If its Windows launcher disappears,
# this process keeps the reservation until its own CUDA work has ended.
if __name__ == "__main__":
    import atexit
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
    from reference_asset_compiler.gpu_reservation import linux_reservation, wait_for_memory
    _reservation = linux_reservation()
    _reservation.__enter__()
    atexit.register(_reservation.__exit__, None, None, None)
    wait_for_memory(max(9216, int(os.environ.get("RAC_MIN_FREE_VRAM_MIB", 0))))


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

# The texture stage's image features are upsampled by NAF to a full 1024 x 1024
# map of 1024 channels (4 GiB, with 8 GiB of scratch beside it: the values are
# resized to the full map before attention), only to be sampled at the voxel
# grid's 262,144 projected points. That was the whole run's peak, 14.2 GiB at
# --resolution 1024, against 6.2 GiB for every other step. NAF's attention
# heads are independent, and each owns its own slice of the channels, so here
# each head is upsampled and sampled on its own and the slices are put back in
# upstream's order. The features are the same tensor, compared exactly.
import torch  # noqa: E402
from einops import rearrange  # noqa: E402
from pixal3d.trainers.flow_matching.mixins import image_conditioned_proj as proj_module  # noqa: E402

_original_extractor_forward = proj_module.DinoV3ProjFeatureExtractor.forward


@torch.no_grad()
def naf_projected_one_head_at_a_time(naf, image, features, output_size, proj_grid, *proj_args):
    """NAF's upsampling of `features`, sampled at the projection grid, one attention head at a time."""
    encoded = naf.image_encoder(image, output_size=output_size)
    queries = naf.query_encoder(encoded)
    keys = naf.key_encoder(encoded, features)
    attention = naf.upsampler
    layer = sys.modules[type(attention).__module__]
    hq, wq = queries.shape[-2:]
    hk, wk = keys.shape[-2:]
    dilation = (hq // hk, wq // wk)
    attention.dilation = dilation
    heads = attention.num_heads
    q_all = rearrange(queries, "b (n d) h w -> b h w n d", n=heads)
    k_all = attention._resize(keys, size=(hq, wq), dtype=q_all.dtype)
    width = features.shape[1] // heads
    sampled = []
    for head in range(heads):
        q = q_all[..., head:head + 1, :].contiguous()
        k = k_all[..., head:head + 1, :].contiguous()
        # CrossAttention._resize, for one head's channels: the same nearest-exact
        # resize, then one head where it lays out num_heads.
        v = torch.nn.functional.interpolate(features[:, head * width:(head + 1) * width], size=(hq, wq),
                                            mode="nearest-exact")
        v = rearrange(v, "b (n d) h w -> b h w n d", n=1).to(q.dtype)
        if layer.NATTEN_RECENT:
            out = layer.na2d(q, k, v, kernel_size=attention.kernel_size, dilation=dilation, stride=1,
                             backend="cutlass-fna")
        else:
            out = layer.legacy_attention(q, k, v, attention.kernel_size, dilation, scale=attention.scale)
        out = rearrange(out, "b h w n d -> b (n d) h w")
        sampled.append(proj_grid(out, *proj_args, BHWC=False))
        del q, k, v, out
    return torch.cat(sampled, dim=-1)


def extractor_forward_one_head_at_a_time(self, image, camera_angle_x=None, distance=None, mesh_scale=None,
                                         transform_matrix=None):
    """Upstream's DinoV3ProjFeatureExtractor.forward, with the NAF branch run head by head."""
    if not self.use_naf_upsample:
        return _original_extractor_forward(self, image, camera_angle_x, distance, mesh_scale, transform_matrix)
    if isinstance(image, torch.Tensor):
        assert image.ndim == 4, "Image tensor should be batched (B, C, H, W)"
    elif isinstance(image, list):
        assert all(isinstance(i, Image.Image) for i in image), "Image list should be list of PIL images"
        image = [i.resize((self.image_size, self.image_size), Image.LANCZOS) for i in image]
        image = [np.array(i.convert('RGB')).astype(np.float32) / 255 for i in image]
        image = [torch.from_numpy(i).permute(2, 0, 1).float() for i in image]
        image = torch.stack(image).cuda()
    else:
        raise ValueError(f"Unsupported type of image: {type(image)}")
    batch = image.shape[0]
    image_for_naf = image.clone()
    image = self.transform(image)
    with torch.no_grad():
        z = self.extract_features(image)
        z_clstoken = z[:, 0:1]
        num_reg = getattr(self.model.config, 'num_register_tokens', 4)
        z_regtokens = z[:, 1:1 + num_reg]
        z_patchtokens = z[:, 1 + num_reg:]
        z_patchtokens_spatial = z_patchtokens.reshape(batch, self.patch_number, self.patch_number, -1)
        if camera_angle_x is None or distance is None or mesh_scale is None:
            raise ValueError("camera_angle_x, distance, and mesh_scale must be provided")
        z_proj_lr = self.proj_grid(z_patchtokens_spatial, camera_angle_x, distance, mesh_scale, transform_matrix)
        self._load_naf()
        z_proj_hr = naf_projected_one_head_at_a_time(
            self.naf_model, image_for_naf, z_patchtokens_spatial.permute(0, 3, 1, 2), self.naf_target_size,
            self.proj_grid, camera_angle_x, distance, mesh_scale, transform_matrix)
        z_proj = torch.cat([z_proj_lr, z_proj_hr], dim=-1)
        z_global = torch.cat([z_clstoken, z_regtokens], dim=1)
    return z_global, z_proj


proj_module.DinoV3ProjFeatureExtractor.forward = extractor_forward_one_head_at_a_time


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
