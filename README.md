# Reference Asset Compiler

![Ayric in the finished night workshop — actual Unreal Engine capture](docs/images/ayric-workshop-v051/hero.png)

[![tests](https://github.com/raydeStar/reference-asset-compiler/actions/workflows/tests.yml/badge.svg)](https://github.com/raydeStar/reference-asset-compiler/actions/workflows/tests.yml)
![license](https://img.shields.io/badge/license-MIT-blue.svg)
![engine](https://img.shields.io/badge/Unreal%20Engine-5.8-black.svg)
![blender](https://img.shields.io/badge/Blender-5.2%20LTS-orange.svg)

**Open-source, evidence-gated pipeline from one concept image to a rigged,
textured, animation-ready Unreal Engine 5 character.** AI image-to-3D
(Hunyuan3D) for geometry and PBR textures, Blender for retopology, UV, rigging
and deformation tests, UE 5.8 for import verification and a playable review
gallery, and a hash-bound ledger so every approval is reproducible. Rigging works
with or without Auto-Rig Pro. MIT licensed.

*Keywords: AI 3D character generation, image to 3D, Hunyuan3D 2.1, Blender
auto-rig, UE5 Manny skeleton, IK Retargeter, game-ready character pipeline,
indie game dev tools.*

![From a single reference image to a skinned skeleton in UE5](docs/images/hero-cat-image-to-ue5.jpg)

*Left: the approved reference. Middle: the compiled payload, lit in Blender.
Right: the 26-bone mascot skeleton derived from the same evidence. The cat went
from image to a playable UE 5.8 gallery in one working day with two human
approvals.* Not "one model call produces a finished character": AI systems
propose isolated candidates; fixed-view reviews, numeric gates, deformation
tests and engine evidence decide what gets promoted, and every stage writes a
receipt with the SHA-256 of what it consumed and produced.

## In the workshop — actual UE 5.8 captures

<p align="center">
  <img src="docs/images/ayric-workshop-v051/portrait.png" width="49%" alt="Window-side character portrait with the moon and desert behind him" />
  <img src="docs/images/ayric-workshop-v051/opposite.png" width="49%" alt="Ayric beside the workshop's furnished workbench and sofa" />
</p>

*Staged captures inside the actual v051 night workshop; a disclosed temporary
portrait fill makes the face readable, saved lighting and assets are unchanged.*

<p align="center">
  <img src="docs/images/ayric-workshop-v051/walk.gif" width="800" alt="An in-place walking cycle inside the workshop: hips, knees, feet and arms animate while the separate head and sword stay attached" />
</p>

*One 1.5-second walk cycle, 24 actual UE animation poses, no generated or
interpolated frames; an editor animation capture, not gameplay footage.*

The detailed head was acquired separately with image-conditioned AI, fitted to
the existing body and attached to its head bone; a bounded neck transition
reconciles colour and normals. The packaged-game audit passes 18 checks; body,
head and sword total 36,437 vertices / 54,027 triangles at LOD0. The head is
rigidly attached, a small collar edge remains visible close up, the body texture
ships under a provisional waiver, and the neck awaits human approval; these
shots do not grant production-ledger approval.
[Reproduce the head/neck method](docs/CHARACTER_HEAD_AND_NECK.md) ·
[Recapture these images and GIF](docs/CHARACTER_SHOWCASE.md) ·
[Media provenance](docs/images/ayric-workshop-v051/provenance.json) ·
[Earlier showcase notes and status](docs/SHOWCASE_HISTORY.md)

## What you get

| Stage | What runs | What you look at |
|---|---|---|
| Geometry | Direct Hunyuan3D single-view or multiview from the reference (historical ComfyUI graph preserved) | Clay front / three-quarter / side / back |
| Modeling approval | You, in the ledger | Same four views, your name on the receipt |
| Cleanup and retopology | Reviewed AutoRemesher or reduction candidates within 20k triangles; optional source-conforming detail refinement (QEM alone does not produce quad deformation loops) | Matcaps, wireframes, deviation numbers |
| Texturing | Hunyuan3D-Paint 2.1 on the exact UV-locked mesh, region-bounded fixes when landmarks drift | Unlit albedo and calibrated lit views |
| Rig | One command, either route: Auto-Rig Pro if installed, otherwise the free landmark rig (Manny-compatible humanoid or 26-bone mascot), 4 influences | Skeleton overlay, five-pose deformation suite |
| Engine | Compile to FBX + PNG + import manifest, headless UE5 import and payload verification | Playable gallery with Manny's idle retargeted onto every character |

Visual review is human-led by default; a user-delegated demo can record agent
judgments with hash-bound consent receipts, labeled as such. Stages, human
gates and receipt schemas: [docs/PIPELINE.md](docs/PIPELINE.md#ledger-stages).

## Quick start

**New here? Read [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) first.**
Windows, Python 3.11+, Blender 5.2 LTS, Unreal Engine 5.8, about 5 GB of disk;
the AI stages add an NVIDIA GPU with 24 GB of VRAM and roughly 60 GiB.

```powershell
git clone https://github.com/raydeStar/reference-asset-compiler.git
cd reference-asset-compiler
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\rac_env.py --all
.\scripts\workflow_doctor.ps1 -Profile ledger  # check the compiler without AI or DCC tools
.\scripts\verify.ps1                          # full local/CI checks, including installed wheel
```

If a tool is not found, set `$env:RAC_BLENDER` or `$env:RAC_UNREAL_CMD`. The
doctor takes `-Profile geometry|texture|ue` and `-Json` (exit 0 ready, 2 missing)
and never launches inference. Wrappers prefer `.venv`; activate it for the
`python` commands below. The release wheel runs the ledger CLI outside a checkout.

### Run it without Codex

Codex is an operator, not a runtime dependency. The resumable operator command
drives the same hash-bound PowerShell, Python, Blender and Unreal stages:

```powershell
$env:RAC_LEGACY_ROOT = "D:\rac-studio"
python scripts\crank_from_image.py brass-lantern D:\art\lantern.png `
  --kind static_prop --height 0.55 `
  --height-reason "Measured against the 0.9 m table in the concept sheet."
```

It runs until the next visual gate, prints the review directory, and stops;
rerun with `--approve-modeling-by`, `--approve-retopology-by` or
`--approve-texture-by "Your Name"`. `--import-ue5` imports the packaged payload;
`--prepare-only` hashes the request without GPU work. Wired end-to-end for
**static props** (request/preflight and contract tests, not yet a fresh full
GPU-to-UE run); humanoids and mascots stop after modeling review because generic
retopology, hand landmarks, rig export and motion proof are not yet safe to automate.

### Try it on a mesh you already have (no AI, no GPU)

The static-prop route needs a mesh (FBX, GLB/glTF or OBJ) and a base color.
`examples/crate/` is a complete CC0 example that runs from a fresh clone:

```powershell
python scripts\compile_prop.py examples\crate\crate.json     # join, scale, rename
python scripts\build_production.py example-crate              # heal, unwrap, bake, gate
python scripts\promote_production.py example-crate            # publish out\example-crate-production\
```

Copy its recipe for your own prop: [examples/crate/README.md](examples/crate/README.md),
[docs/PROPS.md](docs/PROPS.md).

### Try it on a rigged character you already have

Write a recipe with `"kind": "mascot"` or `"humanoid"`, a `skeleton_profile`
from `profiles/skeletons/`, and `material_textures` with `BaseColor` and a
packed `ORM` (R occlusion, G roughness, B metallic), then run
`.\scripts\compile_asset.ps1 -Recipe recipes\my-character.json`. It normalizes
scale and origin, gates the skeleton against the profile, measures texture
quality, renders fixed views, runs the five-pose deformation suite, and writes
`out\my-character\my-character.ue5import.json`.

### See it in Unreal

`.\scripts\setup_ue5_project.ps1` creates the disposable validation project
once from your own engine install (nothing is redistributed). Then:

```powershell
$env:RAC_ROOT = (Get-Location).Path
$ue = python scripts\rac_env.py --unreal-cmd
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\import_and_verify.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\build_gallery_level.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\setup_gallery_playable.py" -unattended -nop4 -nosplash -stdout
& (python scripts\rac_env.py --unreal-editor) .\work\ue5-validate\RacValidate.uproject -game -windowed -ResX=1920 -ResY=1080 -NoTextureStreaming
```

Import and verify every `out\<asset>\<asset>.ue5import.json`, build a lit
gallery, retarget Manny's `MM_Idle` onto every skeleton, walk the line as
Manny. Details: [docs/UE5_VALIDATION.md](docs/UE5_VALIDATION.md).

## The full image-to-engine route

What the cat went through. Each command refuses to overwrite an attempt
directory and writes a JSON receipt; the ledger (`state.json` in the asset
workspace) records which stage passed on what evidence and who approved it.
Exact commands: `docs/WORKFLOW_PLAYBOOK.md`.

```text
approved image
  -> rac new                              immutable reference, routing decision
  -> run_hy3d_geometry.ps1                isolated AI geometry candidate: single image, or
                                          three guidance views when you have them (Hunyuan3D)
  -> rac promote modeling_approval        YOU, on four clay views
  -> run_semantic_cleanup.ps1             conservative topology sanitation
  -> run_paired_feature_qem.ps1 /         20k-triangle quad-dominant retopology with
     run_feature_fairing.ps1              joint-ring guides, deviation measured
  -> rac promote production_retopology    YOU, on matcaps and wireframes
  -> run_texture_uv_prep.ps1              geometry-locked UV transport for the painter
  -> run_hy3d21_texture.ps1               Hunyuan3D-Paint 2.1, topology and UV gate 1e-6
  -> project_ai_reference_region.py       region-bounded landmark fix if the paint drifted
  -> clamp_region_roughness.py            PBR channel fix if the paint left eyes mirror-glossy
  -> render_turnaround.py ... calibrated  the views you actually judge on
  -> package_character_texture.py         PNG maps bound to the UV authority, texture gate
  -> rac promote texture_approval         YOU, on calibrated lit views
  -> run_rig_candidate.ps1                Auto-Rig Pro if installed, else landmark rig:
                                          derive_*_landmarks.py + rig_from_landmarks.py,
                                          then gate_rig.py and deform_test.py
  -> record_rig_and_skin.py,              ledger receipts
     record_deformation.py
  -> compile_asset.ps1                    production package + UE import manifest
  -> import_and_verify.py                 headless UE5 import, payload checks
  -> record_ue5_import.py                 ledger receipt
  -> build_gallery_level.py,              playable gallery with retargeted idles
     setup_gallery_playable.py
  -> record_ue5_motion_review.py          YOU, in the engine
  -> cook and record_cook_evidence.py     the only path to production_ready: true
```

## AI stages: what you need and what is honest about them

- **Geometry** defaults to the hash-pinned Hunyuan3D-2/2mv Python runners, run
  straight from `workflows/geometry/hunyuan3d/` (`mode` omitted means multiview,
  `single_view` when only the picture exists). No ComfyUI graph is executed; the
  launcher only inspects a live ComfyUI queue so it will not steal the GPU.
- **Texturing** uses the official Hunyuan3D-Paint 2.1 pipeline through
  `scripts/run_hy3d21_texture.ps1`, patched only to keep your UVs. It needs
  21 GiB of free VRAM and the studio's `upstream/Hunyuan3D-2.1` checkout plus
  weights; the wrapper hash-verifies the studio copy of the runner and never
  auto-retries a crash. `workflows/texture/hunyuan3d21/` holds provenance copies.
- **Rigging** is either-or per run (`scripts/run_rig_candidate.ps1`): Auto-Rig
  Pro when your Blender has it, otherwise the free landmark rig.
- **Texture upscaling** is not a separate stage: 512- or 768-square views,
  RealESRGAN enhancement, a 4096 bake, 2048-square export. View resolution is
  not atlas resolution; large furniture still has to pass the texel-density gate.
  Wraparound guidance images are not generated by the one-image operator.
- **Retargeting** aligns limb chains to Manny by bone name; it cannot fix roll
  about a bone axis, so hands with a different palm orientation twist. Rotate
  `hand_l` / `hand_r` in the target retarget pose.

`docs/AI_STAGES_SETUP.md` lists the studio tree file by file;
`workflows/README.md` is the routing table with runner hashes. Nothing here
redistributes model weights, licensed add-ons, Unreal Engine, or reference artwork.

### Measured AI install size

Logical file sizes on the verified Windows installation, 2026-09-04, plus the
exact files selected from the pinned shape-model revisions:

| Component | Bytes | GiB |
|---|---:|---:|
| One pinned FP16 shape model (single-view or multiview) | 4,928,153,166-170 | 4.590 |
| Hunyuan3D-Paint 2.1 PBR weights | 6,887,589,708 | 6.415 |
| DINOv2 giant | 9,092,168,676 | 8.468 |
| Geometry Python environment | 5,970,391,978 | 5.560 |
| Paint Python environment | 7,025,227,469 | 6.543 |
| Two pinned upstream checkouts, including RealESRGAN | 762,405,455 | 0.710 |
| **Fresh one-image stack** | **34,665,936,452** | **32.285** |
| **Fresh stack with both shape models** | **39,594,089,622** | **36.875** |

Keep **45 GiB free** for one-image-only, **50 GiB** for both geometry modes,
**60 GiB** with room for attempts. `scripts\measure_ai_install.ps1 -StudioRoot
D:\rac-studio` measures the actual installation.

## Rigging with or without Auto-Rig Pro

```powershell
.\scripts\run_rig_candidate.ps1 -InputMesh .\work\hero\prod-v1\hero_production.fbx `
    -Profile ue5_manny -OutputDirectory .\work\hero\rig\attempt001
```

One command probes Blender for Auto-Rig Pro; with it and `-HandLandmarks` it
runs the Auto-Rig Pro candidate, otherwise it derives joints from the mesh at
Manny's proportions, builds the skeleton, binds with heat weights (welded-proxy
and envelope fallbacks), exports FBX, and runs the same two gates either route
must pass. `rig-route.json` records which route ran; `-Backbone` forces one.

![Landmark-derived Manny-compatible skeleton over an unrigged humanoid, with the hand close-up](docs/images/humanoid-landmark-rig-overlay.jpg)

| | Auto-Rig Pro route | Landmark route |
|---|---|---|
| Cost | Paid Blender add-on, your licence | Free, in this repo |
| Inputs | Approved mesh + reviewed hand-landmark file | Approved mesh (+ joint-ring guides for mascots) |
| Binding | Pseudo-voxel; forgiving on layered clothing | Heat weights; falls back to a welded proxy, then envelope weights on meshes heat cannot solve |
| Fingers | From reviewed landmarks | From Manny's layout scaled to the hand |
| Gates | Same: `gate_rig.py`, `deform_test.py` | Same |
| Output | Candidate `.blend`, export via ARP game exporter | Rigged FBX directly |

## Known debts, stated plainly

Recorded in `docs/DECISIONS.md` and the per-asset evidence; the honest edge of
"99% of the way there":

- **Skeleton root scale.** Blender's FBX export leaves a 100x scale on the root
  bone with bone offsets in metres. UE imports it correctly; tools that write
  component-space centimetres into that local space will not. The gallery
  script compensates; the durable fix is a centimetre export.
- **Texel density and UV layout.** The 2048 Hunyuan atlas spreads to roughly
  20 texels/cm² on a Manny-scale body, and Smart Project produces confetti
  islands. Both are measured on every build and carried as a named waiver.
- **Whiskers and thin detail** survive retopology as geometry spikes, which
  read as brown sticks up close.
- **Human gates** remain by design: modeling, retopology, texture, runtime and
  motion review, cook.

## Repository layout

```text
configs/ profiles/ recipes/ schemas/   adapter registry, hard gates, per-asset recipes, JSON contracts
docs/                                  reference docs, dated logs, evidence JSON; docs/README.md is the index
examples/                              `rac plan` intake samples and the runnable crate compile example
integrations/                          optional UE5 editor plugins (packaged-game audit, socket and seam helpers)
scripts/  (blender/, ue5/)             the compiler; stages that run inside Blender and Unreal
src/  tests/                           planner, immutable workspace, ledger and audit CLI; contract tests
workflows/                             preserved generation entrypoints and the routing catalog
out/, work/                            compiled packages and asset workspaces; ignored by Git
```

## Resuming with an agent

Start with `CLAUDE.md` (rules and routing), then [docs/STATUS.md](docs/STATUS.md)
for the current asset matrix, artifact paths and the next unresolved gate;
[docs/AGENT_TASKS.md](docs/AGENT_TASKS.md) for scoped open work;
[docs/DECISIONS.md](docs/DECISIONS.md) for what failed and why. `docs/HANDOFF.md`
is the dated history; [docs/README.md](docs/README.md) indexes every document.
Contributions: [CONTRIBUTING.md](CONTRIBUTING.md); reports: [SECURITY.md](SECURITY.md).

## License

MIT. Third-party models, tools, add-ons, artwork, and Unreal Engine retain
their own licenses.
