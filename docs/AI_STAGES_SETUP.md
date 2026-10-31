# Setting up the AI stages

*Type: reference*

Everything in the compiler runs without a GPU except two stages: AI geometry
(Hunyuan3D shape generation) and AI texturing (Hunyuan3D-Paint 2.1). Both live
in a separate "studio tree" outside this repository, named by the environment
variable `RAC_LEGACY_ROOT`, because they hold tens of gigabytes of weights,
third-party checkouts, and CUDA virtual environments that do not belong in Git.

This page says exactly what that tree must contain. `scripts\workflow_doctor.ps1`
checks the selected route and reports `[OK]` or `[MISSING]` without launching
inference. Use `-Profile geometry` or `-Profile texture` to check one AI route;
the default `all` can also launch read-only background Blender add-on probes.
`-SkipAddonProbes` disables those optional probes. JSON and text both exit 2
when a required component is missing.

## You will need

| | Requirement |
|---|---|
| GPU | NVIDIA, 24 GB card (verified on an RTX 4090). The launchers measure free VRAM in MiB: texturing refuses to start under 21 GiB (21,504 MiB) free, or 10.5 GiB (10,752 MiB, a 12 GB card) on the studio runner, which releases stages by default (see [Painting with less VRAM](#painting-with-less-vram)); geometry, either mode, under 8 GiB (8,192 MiB) with the default `release_stages`, or 10 GiB (10,240 MiB) resident. These are measured; see [Running geometry with less VRAM](#running-geometry-with-less-vram). |
| CUDA | 12.4 toolchain for the Hunyuan3D-Paint rasterizer build, plus Visual Studio Build Tools with the C++ workload. |
| Python | 3.11 for the paint environment (`.venv-hy3d21`); the geometry environment (`.venv-hy3d`) follows the upstream Hunyuan3D-2 requirements. |
| Disk | 34,665,936,452 bytes (32.285 GiB) for a fresh one-image stack; 39,594,089,622 bytes (36.875 GiB) with both pinned shape models. Keep 45/50 GiB free respectively, or 60 GiB with room for attempts. |
| Network | Hugging Face downloads of `tencent/Hunyuan3D-2.1` (paint PBR subfolder) and `facebook/dinov2-giant` run automatically on first use through `huggingface_hub`. |

## Studio tree layout

```text
$RAC_LEGACY_ROOT\
  scripts\
    run_hy3d21_pbr.py             copy of workflows\texture\hunyuan3d21\run_hy3d21_pbr.py
  upstream\
    Hunyuan3D-2\                  git clone of Tencent-Hunyuan/Hunyuan3D-2 (geometry)
    Hunyuan3D-2.1\                git clone of Tencent-Hunyuan/Hunyuan3D-2.1 at 82920d6 (paint)
      hy3dpaint\ckpt\RealESRGAN_x4plus.pth   67,040,989 bytes, checked exactly
  models\
    hy3d21\Hunyuan3D-2.1\         hunyuan3d-paintpbr-v2-1 weights (auto-downloaded on first run)
    hy3d21\dinov2-giant\          DINOv2 giant (auto-downloaded on first run)
  .venv-hy3d\Scripts\python.exe   geometry environment
  .venv-hy3d21\Scripts\python.exe paint environment (Python 3.11, CUDA 12.4 PyTorch)
```

The runners are **hash-pinned** by their PowerShell launchers. Geometry runs
directly from this repository's `workflows/geometry/hunyuan3d/` directory,
using the studio's Python environment and installed upstream package. No
geometry runner copy is needed in the studio. Paint still executes the pinned
studio copy. Copy that file byte-for-byte; do not edit it in place. Version
runner changes and update the corresponding launcher pin.

## Measured component sizes

Measured on the verified Windows installation on 2026-09-04 using logical
file lengths:

| Component | Bytes | GiB | Notes |
|---|---:|---:|---|
| One pinned FP16 geometry payload | 4,928,153,166-170 | 4.590 | Exact `config.yaml` plus `model.fp16.safetensors`; single-view and multiview differ by four bytes. |
| Hunyuan3D-Paint 2.1 PBR | 6,887,589,708 | 6.415 | `hunyuan3d-paintpbr-v2-1` only. |
| DINOv2 giant | 9,092,168,676 | 8.468 | Current sync downloads both `.bin` and `.safetensors`. |
| `.venv-hy3d` | 5,970,391,978 | 5.560 | Geometry runtime. |
| `.venv-hy3d21` | 7,025,227,469 | 6.543 | Paint runtime and CUDA extensions. |
| `upstream/Hunyuan3D-2` | 268,455,880 | 0.250 | Checkout only. |
| `upstream/Hunyuan3D-2.1` | 493,949,575 | 0.460 | Includes the 67,040,989-byte RealESRGAN checkpoint. |
| **Fresh one-image total** | **34,665,936,452** | **32.285** | Single-view geometry plus the complete paint stack above. |
| **Fresh both-model total** | **39,594,089,622** | **36.875** | Adds the separately pinned multiview shape payload. |

Run this on any installation to get its real footprint:

```powershell
.\scripts\measure_ai_install.ps1 -StudioRoot $env:RAC_LEGACY_ROOT
.\scripts\measure_ai_install.ps1 -StudioRoot $env:RAC_LEGACY_ROOT -Json
```

The measurement counts duplicate weight formats when both are present. It is
therefore an honest disk figure, not a theoretical minimum download. The
verified workstation currently reports 39,594,554,524 bytes (36.875 GiB): its
older multiview cache retains both FP16 checkpoint formats and its single-view
payload has not been downloaded yet.

## Steps

1. Pick a location with room and set the variable for the session (or your
   user environment):

   ```powershell
   $env:RAC_LEGACY_ROOT = "D:\rac-studio"
   New-Item -ItemType Directory -Force "$env:RAC_LEGACY_ROOT\scripts", "$env:RAC_LEGACY_ROOT\upstream", "$env:RAC_LEGACY_ROOT\models\hy3d21" | Out-Null
   ```

2. Copy the pinned paint runner (geometry runs from the repository directly):

   ```powershell
   Copy-Item workflows\texture\hunyuan3d21\run_hy3d21_pbr.py   "$env:RAC_LEGACY_ROOT\scripts\"
   ```

3. Clone the upstream repositories:

   ```powershell
   git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2   "$env:RAC_LEGACY_ROOT\upstream\Hunyuan3D-2"
   git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 "$env:RAC_LEGACY_ROOT\upstream\Hunyuan3D-2.1"
   git -C "$env:RAC_LEGACY_ROOT\upstream\Hunyuan3D-2.1" checkout 82920d6
   ```

4. Create the paint environment and build its rasterizer. Follow the upstream
   README for the exact PyTorch and CUDA wheel matching your driver, then apply
   this repository's Windows patch before building the extension:

   ```powershell
   py -3.11 -m venv "$env:RAC_LEGACY_ROOT\.venv-hy3d21"
   & "$env:RAC_LEGACY_ROOT\.venv-hy3d21\Scripts\python.exe" -m pip install -r "$env:RAC_LEGACY_ROOT\upstream\Hunyuan3D-2.1\requirements.txt"
   & "$env:RAC_LEGACY_ROOT\.venv-hy3d21\Scripts\python.exe" workflows\texture\hunyuan3d21\patch_hy3d21_windows.py "$env:RAC_LEGACY_ROOT\upstream\Hunyuan3D-2.1"
   # then build hy3dpaint\custom_rasterizer and hy3dpaint\DifferentiableRenderer per the upstream README
   ```

   The patch fixes two Windows-only build failures in the upstream rasterizer
   (64-bit `long` assumptions and the CUDA unsupported-compiler opt-in). It is
   idempotent and refuses a source layout it does not recognize.

5. Download the RealESRGAN checkpoint the paint pipeline expects into
   `upstream\Hunyuan3D-2.1\hy3dpaint\ckpt\RealESRGAN_x4plus.pth`. The runner
   verifies its exact size.

6. Create the geometry environment the same way from
   `upstream\Hunyuan3D-2\requirements.txt` into `.venv-hy3d`, and install the
   `hy3dgen` package from that checkout.

7. Run the doctor:

   ```powershell
   .\scripts\workflow_doctor.ps1
   ```

   Every `hy3d2mv.*`, `hy3d2.runner_exact` and `hy3d21.*` line should read
   `[OK]` (`hy3d2.runner_exact` is the single-view runner hash). The first real
   paint run downloads the weights into `models\hy3d21` and takes several
   minutes longer than later runs.

## Geometry from one image, or from three

Two Hunyuan3D geometry runners share one wrapper, `scripts\run_hy3d_geometry.ps1`,
selected by the request's `mode`. A request that omits `mode` runs multiview
(`geometry_request.py` and the launcher both default to it); write
`"mode": "single_view"` explicitly when only the picture exists:

| Mode | Runner | Model | Inputs | When |
|---|---|---|---|---|
| `single_view` (choose it explicitly when you only have the picture) | `run_hy3d_single_view.py` | `tencent/Hunyuan3D-2` `hunyuan3d-dit-v2-0` | the reference image alone | Any agent or person can run it with nothing but the approved image. The far side is inferred. |
| `multiview` (what runs when `mode` is omitted) | `run_hy3d_multiview.py` | `tencent/Hunyuan3D-2mv` | front, left, back guidance views bound to the source by a derivation report | When consistent guidance views exist (the cat's were produced by an image model). Better tails, backs, and silhouettes. |

Both runners pin the model revision and fetch only the config plus the FP16
safetensors they actually open. This matters most for single-view: the upstream
subfolder currently exposes five equivalent checkpoint variants totalling
24,642,009,013 bytes (22.950 GiB), while this runner downloads the required
4,928,153,166 bytes (4.590 GiB).

A single-view request looks like this (`configs/generation/<asset>-attempt001.json`):

```json
{
  "schema": "reference-asset-compiler.hy3d-geometry-request.v1",
  "mode": "single_view",
  "asset_id": "<asset>",
  "workspace": "${RAC_REPO_ROOT}/work/<asset>",
  "source_authority": { "path": "${RAC_REPO_ROOT}/work/<asset>/references/primary.png", "sha256": "<sha256>" },
  "inputs": [ { "view": "primary", "path": "${RAC_REPO_ROOT}/work/<asset>/references/primary.png", "sha256": "<sha256>" } ],
  "parameters": { "seed": 42, "steps": 40, "octree_resolution": 512, "chunks": 20000 },
  "output_directory": "${RAC_REPO_ROOT}/work/<asset>/candidates/hy3d-single-seed42-attempt001"
}
```

`${RAC_REPO_ROOT}` is not an environment variable. It is a placeholder that
`rac geometry-preflight --repo-root <checkout>` substitutes (the launcher passes
its own repository root); `${RAC_LEGACY_ROOT}` in a request is substituted from
`--legacy-root` the same way. Checked-in requests therefore carry no
machine-local paths. Workspaces created with `rac new --workspace-root <dir>`
are found by passing the same `--workspace-root <dir>` to the preflight.

The preflight refuses a single-view request whose input is not the immutable
source itself, and refuses a derivation report on it; the receipt is bound by
the source image hash. Either mode needs 8 GiB (8,192 MiB) of free VRAM by
default, or 10 GiB (10,240 MiB) with `"release_stages": false`.

## Running geometry with less VRAM

The fp16 checkpoint holds three models, read from its safetensors header: the
image conditioner (DINOv2, 2.117 GiB), the diffusion model (2.074 GiB) and the
shape VAE (0.399 GiB). `release_stages` (default `true`) moves the conditioner
to the CPU once it has encoded the views, and the diffusion model once
sampling ends, before volume decoding. Each stage still runs on the GPU with
its original weights and dtype. Nothing upstream is patched. Set
`"release_stages": false` in a request's `parameters` to keep all three
resident.

Calibrated on 2026-10-30 on the RTX 4090
([evidence](evidence/geometry-vram-calibration-20261030.json)), 40 steps,
octree 512, 20000 chunks, one asset per mode:

| Mode | Stages | Peak reserved | Peak allocated | Generation | GLB |
| --- | --- | --- | --- | --- | --- |
| single view | resident | 7.65 GiB | 6.59 GiB | 57.2 s | identical |
| single view | released | 4.99 GiB | 4.88 GiB | 55.0 s | identical |
| multiview | resident | 7.94 GiB | 6.61 GiB | 63.7 s | identical |
| multiview | released | 5.18 GiB | 5.02 GiB | 67.8 s | identical |

The released and resident GLBs were byte-identical in both modes, so the
release changes only memory. The old 12 and 18 GiB floors were estimates more
than twice the real peak. The launcher's floors are now the measured reserved
peak plus about 2.5 GiB for the CUDA context and other inputs: 8 GiB
(8,192 MiB) released and 10 GiB (10,240 MiB) resident, for either mode.
`-MinimumFreeVramMiB` still overrides, and the runner rechecks the floor after
CUDA initialises. A geometry job therefore fits beside a 12 GB paint or
ComfyUI workload on a 24 GB card, or alone on a 10–12 GB card (untested off
the 4090).

`chunks` is the other memory control. It sets how many grid points the VAE
decodes at once; fewer chunks lower the decoding peak and add time. Unlike
`octree_resolution` or `steps`, it does not change what is computed. Higher
chunk counts or octree resolutions than the calibrated ones need their own
measurement.

Every generation report carries `load_seconds`, `release_stages` and a `vram`
block with the device, free memory at start and
`torch.cuda.max_memory_allocated`/`max_memory_reserved`. A run that raises,
including an out-of-memory error, writes `generation-failure.json` with the
same block before the launcher records the failed attempt.

Two larger levers are not wired up because they change the output and need a
modeling gate: upstream's FlashVDM turbo decoder (a different VAE checkpoint,
much faster decoding) and its hierarchical volume decoding (refines only near
the surface instead of decoding a dense 513-cubed grid).

## Painting with less VRAM

Measured on 2026-10-30 on the RTX 4090 with the CH-03 guard mesh
([evidence](evidence/paint-vram-calibration-20261030.json)). Resident
Hunyuan3D-Paint fills the 24 GiB card at every setting. Its weights hold
7.7 GiB and the diffusion steps add about 1.6 GiB. The peak comes at the end of
multiview generation, when the VAE decodes every albedo and metal-rough view in
one batch. At 12 views × 768 the PyTorch pool reached 35.5 GiB, so about 11 GiB
spilled into Windows shared memory. That spill is the slowdown recorded earlier.

The studio runner (`run_hy3d21_texture.ps1 -RunnerKind studio`) releases stages
by default; `-KeepStagesResident` restores the old behaviour. Released means:

1. The CLIP text encoder (never called: the UNet uses learned prompt
   embeddings) and DINO (it encodes the reference once) leave the GPU before
   sampling.
2. The idle UNet waits in host memory while the VAE encodes the reference and
   the normal and position views.
3. Each UNet feed-forward runs one image at a time, and the multiview attention
   runs one (guidance branch, material) sequence at a time. The sequences never
   attend to each other, so this splits the work without changing what is
   computed.
4. The VAE decodes the generated views one at a time.
5. The diffusion pipeline leaves the GPU before the upscale and bake.
6. `PYTORCH_CUDA_ALLOC_CONF` (`garbage_collection_threshold:0.8,max_split_size_mb:256`)
   keeps fragmentation from eating the margin. It affects placement only.
7. The PyTorch pool is budgeted to the free VRAM at launch, less 512 MiB
   (`set_per_process_memory_fraction`). On Windows, an over-full card borrows
   shared system memory instead of failing, so without a budget the cache
   never has to recycle. One uncapped astrolabe run reserved 27.7 GiB on the
   24 GiB card while using 6.8 GiB, and crawled for two hours until stopped.

| Views × resolution | Stages | Peak reserved | Peak allocated | Paint time |
| --- | --- | --- | --- | --- |
| 6 × 512 | resident | 20.4 GiB | 13.4 GiB | 49 s |
| 6 × 512 | released, 10 GiB cap | 8.5 GiB | 7.8 GiB | 54 s |
| 12 × 768 | resident | 35.4 GiB (spills) | 21.1 GiB | 119 s |
| 12 × 768 | released, 10 GiB cap | 9.0 GiB | 7.9 GiB | 94 s |

The AR-02 astrolabe (14,062 triangles) is heavier. At 12 × 768, resident paint
reserved 44.4 GiB and took 178 s, spilling into shared memory. Released under
the 10 GiB cap it peaked at 9.6 GiB reserved and 9.1 GiB allocated, and took
125 s. Before items 2, 3 (attention) and 6 it ran out of memory under the cap,
first in the condition encode and then in the first diffusion step. Its maps
moved 0.10% of base-colour pixels by more than 16/255 against the resident
paint, and the four-view renders match
([on-model comparison](evidence/paint-12gb-astrolabe-20261030.jpg)).

The capped rows ran under `torch.cuda.set_per_process_memory_fraction`, so the
allocator could not exceed 10 GiB, about what a 12 GB card leaves after the
CUDA context and the desktop. Every setting fits. On a larger card, item 7
sets the budget to that card's free memory, so the cache may grow into spare
VRAM but never past it. The launcher's floor is 10,752 MiB for any released setting
and 21,504 MiB resident or on the legacy runner. `-MinimumFreeVramMiB` still
overrides.

diffusers derives a pipeline's `device` from the first module in an unordered
set of component names, and upstream seeds its noise generator on
`pipeline.device`. With the text encoder on the CPU, a process could therefore
sample on the CPU (a crash) or draw its noise on the CPU, which gives a
different paint, like a different seed. The runner pins both to the GPU. A
comparison sheet sent before the pin went in showed that re-roll, not the
release itself.

Paint is deterministic: repeated runs give byte-identical maps, resident or
released. Released maps are **not** byte-identical to resident ones, because
batch-of-one convolutions round differently and the upscale, bake and inpaint
amplify it in places. At 12 × 768, 1.2% of base-colour pixels moved by more than
4/255 and 0.04% by more than 16/255 (0.07% with the 12 GB changes), almost all
of them single pixels on UV island edges ([side by side and ×4 difference](evidence/paint-release-compare-20261030.jpg)).
Moving the weights alone kept the maps byte-identical but did not lower the
peak, and slicing the reference encode as well moved more pixels. On the model
the difference is invisible: in four-view renders of both paints
([on-model comparison](evidence/paint-release-on-model-20261030.jpg)) no pixel
of the front view differs by more than 16/255, and the user judged them
identical on 2026-10-30, so release is the studio default. Reproduce a texture
painted before that date with `-KeepStagesResident`. The legacy runner is
unchanged.

## Optional historical geometry through ComfyUI

Earlier geometry work on the development workstation ran through the preserved
ComfyUI graph `workflows\geometry\comfyui\hy3d_final_cut.json`, which needs
ComfyUI with the `ComfyUI-Hunyuan3DWrapper` and `ComfyUI_essentials` custom
nodes and the `hunyuan3d-dit-v2-0` shape model. The graph also contains
optional texture, upscale, and face-swap branches that the compiler does not
use; the playbook says to stop at `Hy3DExportMesh`.

The current default bypasses that graph and calls the Hunyuan Python runner
directly. `run_hy3d_geometry.ps1` only queries `http://127.0.0.1:8188/queue`
when a ComfyUI process is already running, so it can refuse to steal a busy
GPU. It does not start ComfyUI or queue a ComfyUI prompt. Wraparound-image
generation may be added later as an optional, hash-bound preprocessing stage;
it is not required for the single-view route and is not silently implied here.

## What the doctor cannot check

- That your GPU driver and the CUDA wheel agree; the first run tells you.
- That the rasterizer extension built; the paint runner fails at import if not.
- That another process owns the GPU. The wrappers read `nvidia-smi` and refuse
  to launch under their MiB floors (21 GiB for paint); they never kill anything.

## Review renders while the GPU is busy

EEVEE needs the GPU even in background Blender, and a review render on the same
card slows a running paint or geometry job. Set `RAC_RENDER_DEVICE=CPU` to
render with Cycles on the CPU instead. The turnaround, closeup, material-ID, UV
debug, landmark overlay, deformation, pose test, orthographic view and skin
sweep renderers honour it; label renders (material ID, UV debug) turn
denoising off so their colours stay exact.

## Known limits

- Windows only for the paint rasterizer build path documented here.
- The paint pipeline's Windows process exits with `-1073741819` on teardown
  after writing valid outputs. The wrapper requires the validation JSON rather
  than a clean exit code, and never retries automatically.
- Weights and upstream code are governed by Tencent's and Meta's licenses, not
  this repository's MIT license.
