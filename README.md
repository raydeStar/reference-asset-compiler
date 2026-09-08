# Reference Asset Compiler

![Ayric in the finished night workshop — actual Unreal Engine capture](docs/images/ayric-workshop-v051/hero.png)

Scene utilities: [physical-unit atmosphere recipes, protected UE derivatives,
and portable pending-approval reviews](docs/SCENE_TOOLS.md). Start with
`python scripts/scene_tools.py --help`; planning needs no editor or GPU.

Character repair: [source-locked head fitting and repeatable neck blending](docs/CHARACTER_HEAD_AND_NECK.md).
`./scripts/run_neck_transition.ps1 -Output work/my-neck-review-v001` replays the
local pinned recipe on CPU; native appearance and human approval remain separate.

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
Right: the 26-bone mascot skeleton derived from the same evidence. The cat
walked from image to a playable UE 5.8 gallery in one working day with two
human approvals.*

This is not "one model call produces a finished character". AI systems propose
isolated candidates; an immutable reference image, fixed-view reviews, numeric
gates, deformation tests, and engine evidence decide what gets promoted. Every
stage writes a receipt with the SHA-256 of what it consumed and produced, and
the ledger refuses to advance past a gate that was not actually passed.

## In the workshop — actual UE 5.8 captures

<p align="center">
  <img src="docs/images/ayric-workshop-v051/portrait.png" width="49%" alt="Window-side character portrait with the moon and desert behind him" />
  <img src="docs/images/ayric-workshop-v051/opposite.png" width="49%" alt="Ayric beside the workshop's furnished workbench and sofa" />
</p>

**Real scene, real materials, no promotional repaint.** These are staged captures
inside the actual v051 night workshop, with its independent props and 3D desert.
A temporary soft portrait fill makes the character readable; saved scene lighting,
textures and character assets are unchanged. The detailed
head was acquired separately with image-conditioned AI, fitted to the existing
body, and attached to its head bone. The face artwork stays locked; a bounded
surface-aware colour **and normal** transition reconciles the neck with the body.
The original black-background inspection shots remain in the media history.

<p align="center">
  <img src="docs/images/ayric-workshop-v051/walk.gif" width="800" alt="An in-place walking cycle inside the workshop: hips, knees, feet and arms animate while the separate head and sword stay attached" />
</p>

*Working locomotion rig: one complete 1.5-second walk cycle, sampled at 24
actual UE animation poses and encoded as a looping GIF. No generated motion or
interpolated frames. This is an editor animation capture, not an FPS benchmark
or a recording of keyboard-controlled gameplay.*

The separate packaged-game audit passes **18 checks** for possession, moving
legs, forward travel, wall collision, jump/landing, attachments and actual native
mesh budgets. Body + head + sword total **36,437 vertices / 54,027 triangles at
LOD0**. This demonstrates the reviewed desktop demo, not every target device.
The head is rigidly attached—facial expressions and cloth simulation are not
implemented. A small collar edge remains visible close up; final neck appearance
awaits human approval. These shots do not silently grant production-ledger approval.

What made the texture work repeatable:

- Match painted features to modeled eyes, nose and mouth; better paint cannot
  repair the wrong facial geometry.
- Keep the face's coherent UVs and approved artwork intact. Correct the narrow
  body/neck transition instead of stamping over the entire character.
- Review albedo separately from roughness, metallic and normal response, then
  inspect both sides in the actual engine.
- Measure socket placement in the reference pose and verify real deformation
  and native vertex counts—not just bone names or capsule movement.

[Reproduce the head/neck method](docs/CHARACTER_HEAD_AND_NECK.md) ·
[Recapture these images and GIF](docs/CHARACTER_SHOWCASE.md) ·
[Media provenance](docs/images/ayric-workshop-v051/provenance.json)

## What you get

| Stage | What runs | What you look at |
|---|---|---|
| Geometry | Direct Hunyuan3D single-view or multiview from the reference (historical ComfyUI graph preserved) | Clay front / three-quarter / side / back |
| Modeling approval | You, in the ledger | Same four views, your name on the receipt |
| Cleanup and retopology | Reviewed AutoRemesher or reduction candidates within 20k triangles; optional source-conforming detail refinement (QEM alone does not produce quad deformation loops) | Matcaps, wireframes, deviation numbers |
| Texturing | Hunyuan3D-Paint 2.1 on the exact UV-locked mesh, region-bounded fixes when landmarks drift | Unlit albedo and calibrated lit views |
| Rig | One command, either route: Auto-Rig Pro if installed, otherwise the free landmark rig (Manny-compatible humanoid or 26-bone mascot), 4 influences | Skeleton overlay, five-pose deformation suite |
| Engine | Compile to FBX + PNG + import manifest, headless UE5 import and payload verification | Playable gallery with Manny's idle retargeted onto every character |

Visual review is human-led by default. An expressly user-delegated demo can
record agent judgments with source-, stage- and artifact-bound consent receipts;
these are labeled as agent reviews and never waive mechanical checks. See
[pipeline gates](docs/PIPELINE.md). The new
[Sunset workshop demo](docs/SUNSET_DEMO_COMPLETION.md) is now a verified local
Windows demo. `scripts/play_workshop_demo.ps1 -Lighting Day` opens v018: Manny with a separate
back-carried sword, restored sofa and plants, independently placed props, a flat
rug, corrected support contacts, composed lighting and a real-depth window vista.
All13 editor and12 packaged-game programmatic movement/collision/jump/attachment
checks pass. Eight actual cooked frames were visually reviewed, including a
2.2m paired window baseline. No physical-keyboard test is claimed.
The package is1,131,307,068bytes across48files; no Codex, model server or editor
is needed to play. Review panel: `work/sunset-workshop/evidence/final-demo-v018.html`.
Custom Ayric now has a repaired locomotion rig and a source-locked detailed-head
candidate; see [current repair evidence](docs/AYRIC_REPAIR_2026-09-06.md).
This scene demonstration does not
silently certify every asset's separate production-ready gallery gate. See
[current scene status](docs/SUNSET_WORKSHOP.md).

The launcher now defaults to the separate **night v026** variant: warm work
lights, cool moonlight, small stars through the window and skylight, and very
faint ground-weighted desert haze. The tall dust dome was rejected. All 169
original objects are unchanged; one non-colliding sky sphere was added.
Night passes 12 packaged programmatic checks with nine inspected game captures.
Its local package is 1,132,895,624 bytes across 48 files. No additional models
or downloads are required. Use `-Lighting Night` or `-Lighting Day` to choose.
See [night lighting and evidence](docs/SUNSET_NIGHT.md).

![The playable UE 5.8 gallery: compiled characters and props with Manny idle retargeted onto every skeleton](docs/images/ue5-gallery-playable.jpg)

*The end state: a UE 5.8 level you walk as Manny, every compiled character
looping a retargeted idle, each authority beside its production derivative.*

![Texture review: the same atlas under the factory AgX transform and the calibrated transform](docs/images/cat-texture-review-calibration.jpg)

*The single most useful lesson of the project: judge textures on a calibrated
display transform. The first review render (top middle) was washed out by
Blender's factory AgX transform and showed a hard white glint that turned out to
be a mirror-glossy eye, not paint. The accepted attempt007 (top right, bottom
row) is the same base color under a calibrated transform with the eye roughness
lifted; that is what shipped to UE5.*

![Rig review: skeleton overlay and the five-pose deformation suite](docs/images/cat-rig-review.jpg)

## Quick start

**New here? Read [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) first.**
It has the full "you will need" list so nothing surprises you, and walks from
a fresh clone to a walkable UE5 gallery step by step.

You need Windows, Python 3.11+, Blender 5.2 LTS, and Unreal Engine 5.8; about
5 GB of disk for the no-AI route. The AI stages additionally need an NVIDIA GPU
with 24 GB of VRAM, a local Hunyuan3D 2.1 checkout, and roughly 60 GB in total;
see *AI stages* below and the disk tiers in the getting-started guide.

```powershell
git clone <this repo> reference-asset-compiler
cd reference-asset-compiler
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
python scripts\rac_env.py --all          # where Blender and Unreal were found
.\scripts\workflow_doctor.ps1            # read-only report of every route
.\scripts\verify.ps1                     # contract tests; must pass
```

If a tool is not found, point at it:

```powershell
$env:RAC_BLENDER    = "C:\path\to\blender.exe"
$env:RAC_UNREAL_CMD = "C:\path\to\UnrealEditor-Cmd.exe"
```

### Run it without Codex

Codex is an operator, not a runtime dependency. The resumable operator command
drives the same hash-bound PowerShell, Python, Blender, and Unreal stages:

```powershell
$env:RAC_LEGACY_ROOT = "D:\rac-studio"
python scripts\crank_from_image.py brass-lantern D:\art\lantern.png `
  --kind static_prop --height 0.55 `
  --height-reason "Measured against the 0.9 m table in the concept sheet."
```

It runs until the next visual gate, prints the exact review directory, and
stops. Inspect the four views, then rerun the same command with
`--approve-modeling-by "Your Name"`, `--approve-retopology-by "Your Name"`,
or `--approve-texture-by "Your Name"` as requested. Add `--import-ue5` on the
final run to import and verify the packaged payload in the local validation
project. `--prepare-only` writes and hashes the request without launching GPU
work.

This first operator route is wired end-to-end for **static props**; it has
passed request/preflight and contract tests but has not yet been certified by
a fresh full GPU-to-UE run. Humanoids and mascots use the same one-image
geometry intake and modeling review, but the command stops there: generic
deformation-aware retopology, hand landmarks, rig export, and motion proof are
not yet safe to automate. It does not call a triangle soup a character merely
because optimism is inexpensive.

### Try it on a mesh you already have (no AI, no GPU)

The static-prop route needs nothing but a mesh and a base color:

```jsonc
// recipes/my-crate.json
{
  "asset_id": "my-crate",
  "kind": "static_prop",
  "articulation": "static",
  "source": { "authority_fbx": "D:/art/crate.glb" },
  "material_textures": { "MAT-Crate": { "BaseColor": "D:/art/crate_basecolor.png" } },
  "normalize": {
    "mesh_name": "SM_Crate",
    "target_height_m": 0.6,
    "target_height_reason": "Measured against the character cohort, not guessed.",
    "recenter": true,
    "material_renames": { "MAT-Crate": "M_Crate_Body" }
  }
}
```

```powershell
python scripts\compile_prop.py recipes\my-crate.json     # join, scale, rename
python scripts\build_production.py my-crate               # heal, unwrap, bake, gate
python scripts\promote_production.py my-crate             # publish out\my-crate-production\
```

### Try it on a rigged character you already have

Write a recipe with `"kind": "mascot"` or `"humanoid"`, a `skeleton_profile`
from `profiles/skeletons/`, and `material_textures` with `BaseColor` and a
packed `ORM` (R occlusion, G roughness, B metallic), then:

```powershell
.\scripts\compile_asset.ps1 -Recipe recipes\my-character.json
```

That normalizes scale and origin, gates the skeleton against the profile,
measures texture quality, renders fixed views, runs the five-pose deformation
suite, and writes `out\my-character\my-character.ue5import.json`.

### See it in Unreal

Create the disposable validation project once (it copies the Third Person
Blueprint character, the Mannequin content and the Input pack from your own
engine install; nothing is redistributed):

```powershell
.\scripts\setup_ue5_project.ps1
```

Then import, build the gallery, retarget the idles, and play:

```powershell
$env:RAC_ROOT = (Get-Location).Path
$ue = python scripts\rac_env.py --unreal-cmd
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\import_and_verify.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\build_gallery_level.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\setup_gallery_playable.py" -unattended -nop4 -nosplash -stdout
& (python scripts\rac_env.py --unreal-editor) .\work\ue5-validate\RacValidate.uproject -game -windowed -ResX=1920 -ResY=1080 -NoTextureStreaming
```

The first command imports every `out\<asset>\<asset>.ue5import.json` and
verifies what the engine actually built (height, materials, textures sampled,
LODs, texture settings). The second builds a lit gallery level with every
character on a floor. The third retargets Manny's `MM_Idle` onto every skeleton
and makes the level playable with the Third Person template character. The last
drops you in as Manny to walk the line. `RAC_ASSET_IDS=my-crate,my-character`
limits the import to named assets.

`work/ue5-validate` is ignored by Git; `setup_ue5_project.ps1` recreates it on
any machine with UE 5.8 installed (see `docs/UE5_VALIDATION.md`).

## The full image-to-engine route

This is what the cat went through. Each command refuses to overwrite an
attempt directory and writes a JSON receipt beside its output; the ledger
(`state.json` in the asset workspace) records which stage passed on what
evidence and who approved it.

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

Two decisions are yours and cannot be automated away: modeling approval and
texture approval. Everything else is scripted, measured, and rerunnable.
`docs/WORKFLOW_PLAYBOOK.md` walks through each stage with the exact commands;
`docs/HANDOFF.md` is the running record of the cat and the earlier assets.

![Eye fix: a mirror-glossy eye under the key light before and after the roughness floor](docs/images/cat-eye-roughness-fix.jpg)

*A typical bounded fix. The white shape on the left eye was not paint; the
painter had left the eye at roughness 0.11 and the key light mirrored off it.
One script lifted only the two eye regions to a 0.7 floor and recorded the
mask, the texel count, and the hashes.*

## AI stages: what you need and what is honest about them

- **Geometry** defaults to the hash-pinned Hunyuan3D-2/2mv Python runner. It does not
  execute a ComfyUI graph. The launcher only inspects a live ComfyUI queue so
  it will not steal the GPU from somebody else's job. The original ComfyUI
  geometry graph remains preserved as an optional historical route.
- **Texturing** uses the official Hunyuan3D-Paint 2.1 pipeline through
  `scripts/run_hy3d21_texture.ps1`, patched only to keep your UVs instead of
  rewrapping. It needs 21 GB of free VRAM and a `upstream/Hunyuan3D-2.1`
  checkout plus model weights beside the runner; the wrapper checks both and
  never auto-retries a crash.
- **Rigging** is either-or, chosen per run by `scripts/run_rig_candidate.ps1`:
  Auto-Rig Pro when your Blender has it (better binding on layered clothing,
  needs your licence and a reviewed hand-landmark file), otherwise the free
  landmark rig built into this repo. See *Rigging with or without Auto-Rig Pro*.
- **Texture upscaling** is not a separate default stage. The painter currently
  generates 512- or 768-square views, enhances those views with RealESRGAN,
  bakes at 4096 square, and exports 2048-square maps in the verified local
  route. View resolution is not atlas resolution. No separate final-atlas
  upscaler is run; large furniture still has to pass the texel-density gate.
- **Wraparound-image generation** is not in the one-image operator. ComfyUI may
  later supply hash-bound guidance views for the multiview runner, but today the
  command uses the approved source image directly and infers the hidden side.
- **Retargeting** in the gallery builds IK Rigs from bone names and retargets
  `MM_Idle`, aligning limb chains to Manny and keeping spine and head at rest.
  Chain alignment cannot fix roll about a bone axis, so a character whose hands
  rest with a different palm orientation than Manny's will show twisted hands.
  Open `/Game/Compiled/Retargeted/<run>/Rigs/RTG_RAC_Manny_to_<Asset>` in the
  IK Retargeter and rotate `hand_l` / `hand_r` in the target retarget pose;
  the gallery script records which variant it chose and why.

`docs/AI_STAGES_SETUP.md` lists the studio tree the two AI stages expect, file
by file, with the hash-pinned runners copied from `workflows/`.

Nothing here redistributes model weights, licensed add-ons, Unreal Engine, or
the reference artwork.

### Measured AI install size

These are logical file sizes measured on the verified Windows installation on
2026-09-04, plus the exact files selected from the pinned shape-model
revisions—not estimates copied from model-card headlines:

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

The current DINO download contains both `pytorch_model.bin` and
`model.safetensors`; both are counted. The pinned geometry runners now request
only `config.yaml` and `model.fp16.safetensors`; upstream's broad single-view
download otherwise pulls five equivalent checkpoint files totalling
24,642,009,013 bytes (22.950 GiB). Keep **45 GiB free** for a one-image-only
installation, **50 GiB** for both geometry modes, or **60 GiB** if you also
want room for attempts and evidence. Run
`scripts\measure_ai_install.ps1 -StudioRoot D:\rac-studio` to measure the
actual installation rather than trusting this snapshot.

## Rigging with or without Auto-Rig Pro

```powershell
.\scripts\run_rig_candidate.ps1 -InputMesh .\work\hero\prod-v1\hero_production.fbx `
    -Profile ue5_manny -OutputDirectory .\work\hero\rig\attempt001
```

That one command probes Blender for Auto-Rig Pro. If it is operational and you
pass `-HandLandmarks`, it runs the Auto-Rig Pro candidate. Otherwise it derives
joints from the mesh itself: spine, neck and head at Manny's proportions with
depth from the mesh cross-sections; crotch, legs and arms from per-limb
centrelines; Manny's finger and metacarpal layout transplanted onto the measured
hand; twist bones at thirds; IK helpers where Manny has them. It builds the
skeleton, binds with heat weights (welded-proxy and envelope fallbacks), exports
FBX, and runs the same two gates either route must pass. `rig-route.json`
records which route ran and why. `-Backbone landmark` or `-Backbone arp` forces
a route.

![Landmark-derived Manny-compatible skeleton over an unrigged humanoid, with the hand close-up](docs/images/humanoid-landmark-rig-overlay.jpg)

*The free route on the field-scout male mesh with its armature stripped: 86
bones, passes the ue5_manny gate and the five-pose suite. Fingers are Manny's
layout fitted to the measured forearm, not a measurement; check the hand
overlay before trusting finger deformation.*

Honest comparison:

| | Auto-Rig Pro route | Landmark route |
|---|---|---|
| Cost | Paid Blender add-on, your licence | Free, in this repo |
| Inputs | Approved mesh + reviewed hand-landmark file | Approved mesh (+ joint-ring guides for mascots) |
| Binding | Pseudo-voxel; forgiving on layered clothing | Heat weights; falls back to a welded proxy, then envelope weights on meshes heat cannot solve |
| Fingers | From reviewed landmarks | From Manny's layout scaled to the hand |
| Gates | Same: `gate_rig.py`, `deform_test.py` | Same |
| Output | Candidate `.blend`, export via ARP game exporter | Rigged FBX directly |

## Known debts, stated plainly

These are recorded in `docs/DECISIONS.md` and the per-asset evidence, and they
are the honest edge of "99% of the way there":

- **Skeleton root scale.** Blender's FBX export leaves a 100x scale on the root
  bone with bone offsets in metres. UE renders and imports it correctly; any
  retargeter or physics tool that writes component-space centimetres into that
  local space will not. The gallery script compensates; the durable fix is a
  centimetre export, which touches every compiled asset.
- **Texel density and UV layout.** The 2048 Hunyuan atlas spreads to roughly
  20 texels/cm² on a Manny-scale body, and Smart Project produces confetti
  islands. Both are measured on every build and carried as a named waiver, not
  silently passed. A coherent semantic UV pass and a higher-resolution paint
  are the remedies.
- **Whiskers and thin detail** survive retopology as geometry spikes; texture
  follows them faithfully, which reads as brown sticks up close.
- **Two human gates** remain by design.

## Repository layout

```text
configs/        Adapter registry and generation requests; no machine-local paths
docs/           Playbook, pipeline, decisions, handoff, evidence JSON per asset
docs/images/    The screenshots in this README
profiles/       Hard gates: skeleton contracts, texture limits, retopology guides
recipes/        One per compiled asset: source, scale, materials, waivers, and why
schemas/        Portable JSON contracts
scripts/        The compiler
  blender/        Stages run inside Blender (retopo, UV, rig, deformation, renders)
  ue5/            Stages run inside Unreal (import, verify, gallery, retarget)
src/            Planner, immutable workspace, promotion ledger, audit CLI
tests/          Contract and tamper-detection tests (scripts\verify.ps1)
workflows/      Preserved generation entrypoints and the workstation routing catalog
out/, work/     Compiled packages and asset workspaces; ignored by Git, reproducible
```

## Resuming with an agent

Current custom-character review is **Ayric v051**, with a separate detailed head,
repaired locomotion and a repeatable neck transition. The package passes all 18
runtime checks; the latest neck remains a visual-review candidate. Run
`./scripts/play_workshop_demo.ps1 -Lighting Ayric` on the workstation with its
saved package; `AyricLegacy` preserves v036. Night/Manny remains the default.
See [the current handoff](docs/HANDOFF.md) and
[the repair results](docs/AYRIC_REPAIR_2026-09-06.md).

<details>
<summary>Historical experiments and superseded pre-v051 status (retained for provenance)</summary>

The notes below describe earlier stages, not the current assembled demo.

Current scene experiment: [Sunset workshop](docs/SUNSET_WORKSHOP.md) tracks
the modular, reference-conditioned room study and separate prop jobs. The
local early walkthrough has 19 independent prop actors, with player spawn,
gameplay movement and blocking collision checked in UE PIE. It remains work
in progress, not a cooked release. The optimized circuit board now passes its
native import and static UE visual review and is separately placed in preview
v004. Sofa, foliage, the custom character and overall scene polish remain
unfinished. On the workstation with the saved project, launch it with
`./scripts/play_workshop_preview.ps1` (no Codex dependency).

The separate sword has passed native UE import (1.35 m, 11,123 LOD0
vertices) and a delegated six-frame static editor review, including all three
LODs. Animated back attachment and cooked proof remain pending. Actual UE
frames: `work/sunset-workshop/evidence/sword-review-v003.html`.
Ayric's latest held texture package is `prod-collar-v001`, with a
cleaner face/collar transition. It still fails the lighting gate and has not
advanced to rigging. The workstation review is
`work/sunset-workshop/evidence/ayric-collar-review-v001.html`.

An optional IntrinsicAnything albedo challenger now runs in an isolated local
environment; it is not the default pipeline or an approved texture replacement.
Its pinned checkpoint is exactly 15,458,840,153 bytes (15.46 GB decimal).
The measured local tool directories plus auxiliary models total 22.48 GB of
logical file bytes, excluding the interpreter and download/build caches.
The first base inference completed but softened facial detail. See
[the challenger setup and size breakdown](workflows/texture/intrinsicanything/README.md).
No character texture has been replaced by this experiment.
The subsequent six-view tests failed: side estimates collapsed or tiled
estimates introduced bands. This route is stopped, not promoted; see
[the retained lighting escalation](docs/ESCALATE-sunset-lighting.md).

The plant's torn single-view geometry has been replaced by a reviewed
Hunyuan3D-2mv acquisition, directly conditioned on the original plant image
and two explicitly inferred ImageGen depth views. Modeling and conservative
cleanup pass. Runtime topology remains held: the 18k reduction and bounded
normal/refinement challengers leave visible pot facets. Actual comparisons:
`work/sunset-workshop/evidence/plant-repair-review-v001.html`. This did not
change Ayric's held texture or the UE scene.

The face repair now has a separate rigid-head component experiment,
`work/sunset-ayric-rigid-head-v1`. It reuses the exact image-conditioned AI
acquisition; dense modeling, cleanup and static runtime topology have passed.
The accepted head has 10,020 vertices and 19,988 triangles, with valid normals
and closed surfaces. Texturing and head-bone attachment remain unfinished.
Actual clay evidence is shown in
`work/sunset-workshop/evidence/ayric-modular-head-review-v002.html`.
This is a modular avatar route, **not** a monolithic20k character: each body,
head and sword component keeps its own20k triangle/15k vertex ceiling, with
a60k combined target. Actual assembled totals and neck/motion/cooked-runtime
proof remain required. Existing body material/rig holds are unchanged.

Head-texture work now has a comparison panel at
`work/sunset-workshop/evidence/ayric-head-texture-working-v001.html`.
The new UV layout keeps the central face continuous and improves atlas use;
the matte material is preferable to the raw AI scalar maps. Eye-edge paint
and skin/hair transitions still prevent texture approval. The panel labels
failed candidates explicitly; it is not a completed character demo.

The earlier partial face-artwork comparison is
`work/sunset-workshop/evidence/ayric-face-donor-review-v001.html`.
AI-guided, geometry-bound eye mapping improves the irises, while an angled
temple repair remains rejected for incomplete transitions and a small eye
regression. The panel separates actual3D renders from AI source artwork and
includes exact prompts. No face texture approval or completed UE avatar is
claimed; the body and workshop remain unchanged.

The retained coherent-face comparison is
`work/sunset-workshop/evidence/ayric-coherent-face-review-v001.html`.
Three AI artwork views now share surface-derived landmarks; exact subpixel
visibility removes projection striping. Actual front and both angled views
have cleaner eyes and continuous cheeks. The working candidate remains held:
rear hair/neck coloration is gray, and the unchanged lighting-correlation
check measures0.36124 against a0.35 limit. All six directions are shown lit
and unlit. This is progress on the face, not a texture pass or UE release.

The head component has since passed its texture gate. Current review:
`work/sunset-workshop/evidence/ayric-head-texture-review-v002.html`.
Image-conditioned rear hair and bilateral hair mapping preserve the repaired
facial features; the4K,0.33m head/neck FBX passes the unchanged static texture
checks without a waiver. Approval is explicitly agent-delegated and head-only.
The complete avatar is still unfinished: body material, collar fitting,
animation, back-mounted sword and cooked UE gameplay require their own proof.

The repaired head now also passes native UE5.8.2 import and delegated static
appearance review. Actual engine captures:
`work/sunset-workshop/evidence/ayric-head-ue-review-v002.html`.
UE LOD0 is12,740 vertices/19,988 triangles at33cm; all three LODs are measured.
The panel includes albedo controls, both sides, the shadowed rear and the
retained overbright fixture. This is a separate head inspection, not an
attached or animated avatar. No accepted face artwork was changed for UE.

A new body-brightness-only test did not clear the existing lighting gate and
was not promoted. Its evidence is retained at
`work/sunset-workshop/evidence/body-lighting-canary-v001.html`.

</details>

The repository is written to be resumed by Claude Code, Codex, or a person
without chat history. Start with `CLAUDE.md`, then `docs/HANDOFF.md` for the
current asset matrix, exact artifact paths, and the next unresolved gate.
`docs/DECISIONS.md` lists what failed and why, so nobody repeats it.
`docs/AGENT_TASKS.md` lists scoped open work with acceptance criteria, split
into tasks that need a GPU and tasks that do not, so an agent or a contributor
can pick one up cold.

## License

MIT. Third-party models, tools, add-ons, artwork, and Unreal Engine retain
their own licenses.
