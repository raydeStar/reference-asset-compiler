# Setting up the AI stages

Everything in the compiler runs without a GPU except two stages: AI geometry
(Hunyuan3D shape generation) and AI texturing (Hunyuan3D-Paint 2.1). Both live
in a separate "studio tree" outside this repository, named by the environment
variable `RAC_LEGACY_ROOT`, because they hold tens of gigabytes of weights,
third-party checkouts, and CUDA virtual environments that do not belong in Git.

This page says exactly what that tree must contain. `scripts\workflow_doctor.ps1`
checks every item below and reports `[OK]` or `[MISSING]` without launching
anything.

## You will need

| | Requirement |
|---|---|
| GPU | NVIDIA, 24 GB VRAM (verified on an RTX 4090). Texturing refuses to start under 21 GB free. |
| CUDA | 12.4 toolchain for the Hunyuan3D-Paint rasterizer build, plus Visual Studio Build Tools with the C++ workload. |
| Python | 3.11 for the paint environment (`.venv-hy3d21`); the geometry environment (`.venv-hy3d`) follows the upstream Hunyuan3D-2 requirements. |
| Disk | 34,665,936,452 bytes (32.285 GiB) for a fresh one-image stack; 39,594,089,622 bytes (36.875 GiB) with both pinned shape models. Keep 45/50 GiB free respectively, or 60 GiB with room for attempts. |
| Network | Hugging Face downloads of `tencent/Hunyuan3D-2.1` (paint PBR subfolder) and `facebook/dinov2-giant` run automatically on first use through `huggingface_hub`. |

## Studio tree layout

```text
$RAC_LEGACY_ROOT\
  scripts\
    run_hy3d_multiview.py         copy of workflows\geometry\hunyuan3d\run_hy3d_multiview.py
    run_hy3d_single_view.py       copy of workflows\geometry\hunyuan3d\run_hy3d_single_view.py
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

The two runner scripts are **hash-pinned**. `scripts\run_hy3d_geometry.ps1`
and `scripts\run_hy3d21_texture.ps1` compute the SHA-256 of the copy in your
studio tree and refuse to run if it differs from the pin recorded in
`workflows\catalog.json`. Copy the files byte-for-byte; do not edit them in
place. If you need a change, add a versioned wrapper beside them and record the
new hash and the decision, as `workflows/README.md` explains.

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

2. Copy the pinned runners from this repository:

   ```powershell
   Copy-Item workflows\geometry\hunyuan3d\run_hy3d_multiview.py   "$env:RAC_LEGACY_ROOT\scripts\"
   Copy-Item workflows\geometry\hunyuan3d\run_hy3d_single_view.py "$env:RAC_LEGACY_ROOT\scripts\"
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

   Every `hy3d2mv.*` and `hy3d21.*` line should read `[OK]`. The first real
   paint run downloads the weights into `models\hy3d21` and takes several
   minutes longer than later runs.

## Geometry from one image, or from three

Two Hunyuan3D geometry runners share one wrapper, `scripts\run_hy3d_geometry.ps1`,
selected by the request's `mode`:

| Mode | Runner | Model | Inputs | When |
|---|---|---|---|---|
| `single_view` (default when you only have the picture) | `run_hy3d_single_view.py` | `tencent/Hunyuan3D-2` `hunyuan3d-dit-v2-0` | the reference image alone | Any agent or person can run it with nothing but the approved image. The far side is inferred. |
| `multiview` | `run_hy3d_multiview.py` | `tencent/Hunyuan3D-2mv` | front, left, back guidance views bound to the source by a derivation report | When consistent guidance views exist (the cat's were produced by an image model). Better tails, backs, and silhouettes. |

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

The preflight refuses a single-view request whose input is not the immutable
source itself, and refuses a derivation report on it; the receipt is bound by
the source image hash. Single view needs about 12 GB of free VRAM, multiview 18.

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
  to launch under 21 GB free; they never kill anything.

## Known limits

- Windows only for the paint rasterizer build path documented here.
- The paint pipeline's Windows process exits with `-1073741819` on teardown
  after writing valid outputs. The wrapper requires the validation JSON rather
  than a clean exit code, and never retries automatically.
- Weights and upstream code are governed by Tencent's and Meta's licenses, not
  this repository's MIT license.
