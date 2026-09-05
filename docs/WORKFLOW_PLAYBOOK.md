# Generation workflow playbook

This is the missing operational bridge between an approved picture and the
compiler. It is deliberately explicit about what runs where.

## The short instruction for another AI

Do **not** send texture work to ComfyUI on this workstation. The preserved
ComfyUI graph was the user's image-to-3D geometry workflow. For existing-mesh
PBR texturing, use the isolated Hunyuan3D-Paint 2.1 runner. TRELLIS.2 is a
tested challenger, not the production default. The compiler does not generate
geometry, repaint an atlas, or author a fresh humanoid rig; it normalizes,
gates, packages, imports, and verifies assets that already exist.

If the requested task is “fix these textures,” begin at Stage 4 below. Do not
reinstall random ComfyUI nodes or describe a hypothetical ControlNet pipeline.

## Stage 0 — preflight

```powershell
.\scripts\workflow_doctor.ps1
```

The doctor is read-only. A missing optional challenger is not a reason to
install anything. Before GPU work, also inspect `nvidia-smi`; preserve open
Blender, ComfyUI, and Unreal processes and never kill them automatically.

## Stage 1 — authority intake

Use `rac new` to copy and hash the approved image. Do not substitute a prompt,
generic asset pack, or manually approximated primitive. Pre-segment a reviewed
RGBA cutout for Pixal3D/TRELLIS paths.

## Stage 2 — geometry candidates

### Default: guarded Hunyuan3D-2mv

Use a checked-in request under `configs/generation/`. The preflight hash-binds
the immutable intake image, every conditioned view, the multiview lineage
report, model parameters, and a brand-new attempt directory. The launcher then
checks the exact legacy runner, GPU owners and free VRAM, and any live ComfyUI
queue before running exactly once:

```powershell
.\scripts\run_hy3d_geometry.ps1 `
  -Request .\configs\generation\fox-mascot-ai-v3.json
```

The launcher never kills a process, overwrites an attempt, or auto-retries a
failure. A successful run emits `candidate.glb`, the upstream generation
report, an attempt receipt, and a ledger-compatible candidate receipt. That is
still only an AI geometry candidate; stop for fixed-view modeling review.

### Historical ComfyUI path

Import `workflows/geometry/comfyui/hy3d_final_cut.json`. It is the original
64-node, 83-link graph supplied by the user. Its own notes describe the camera
mirroring/multiview bake, ReActor option, delighting, vertex inpaint, UV wrap,
and postprocess face budget.

On the current installation, the graph's Hunyuan3DWrapper and ReActor nodes
are absent. Preserve the graph; do not silently replace nodes. If its exact
dependencies are restored, use it for geometry and stop at `Hy3DExportMesh`.
Bypass the legacy texture branch unless the task explicitly asks to compare it.

### Pixal3D path

Run the included wrapper inside the verified isolated Pixal3D WSL environment:

```bash
export PIXAL3D_ROOT=/path/to/Pixal3D            # your WSL checkout
python workflows/geometry/pixal3d/run_pixal3d.py \
  --image /path/to/authority-cutout.png \
  --output /path/to/candidate.glb \
  --resolution 1024 --seed 42
```

The RGBA alpha mask is mandatory. Promote neither path until neutral fixed
front, three-quarter, side, and back clay views pass identity, anatomy,
construction, visible-part count, hands/feet, and side-depth review.

## Stage 3 — topology and UV contract

Promote one high-resolution geometry authority without overwriting it. Derive
the runtime mesh. Preserve meaningful loops and use coherent islands per body
part. The legacy per-patch xatlas layouts produced hundreds of tiny islands,
seams, specks, and face pixels on clothing; do not reproduce them merely
because an older script exists.

Run `scripts\run_semantic_cleanup.ps1` first. It accepts only the exact
human-approved modeling mesh, writes a separate native Blender derivative, and
requires identical topology after reopening the file. GLB is review transport,
not an editable topology authority: it may split shared vertices at face-corner
normals. Cleanup can weld coincident vertices, remove degenerate or loose
geometry, and recalculate normals; it cannot invent or remove semantic parts.

The V1 cohort contract is unwaived: no more than 15,000 vertices and 20,000
triangles per runtime asset. A mechanically under-budget remesh is still a
rejection if fixed clay views lose the approved silhouette, face, hands, or
construction details.

`scripts\run_feature_qem_reduction.ps1` is a one-shot diagnostic challenger
for an approved native cleanup authority. It protects high-curvature and dense
detail regions during collapse, refuses to overwrite an attempt, and measures
symmetric surface deviation. Its output is not automatically production
retopology: fixed-view appearance and deformation-aware edge flow retain veto
power. The female V4 trial proved that low surface error can still leave a
faceted, all-triangle mesh unsuitable for humanoid deformation.

After a materially acceptable candidate exists, create the immutable approval
receipt before promoting `production_retopology`:

```powershell
rac retopology-receipt <workspace> <cleaned.blend> <runtime.blend> <report.json> `
  --view <matcap-front.png> --view <matcap-three-quarter.png> `
  --view <matcap-side.png> --view <matcap-back.png> `
  --topology-view <wireframe-front.png> `
  --topology-view <wireframe-three-quarter.png> `
  --topology-view <wireframe-side.png> `
  --topology-view <wireframe-back.png> `
  --approved-by <human-name> --note <review-note>
```

The ledger revalidates the receipt instead of trusting the command that wrote
it. It requires exact semantic-cleanup lineage, the workspace vertex/triangle
budgets, a closed surface, hash-bound fixed views, and identified human review.
Articulated assets additionally require at least 80% quads and four hash-bound
wireframe views for explicit deformation-topology review; an all-triangle
proximity result or a percentage-only face-pairing result cannot pass.

The user preferred the voxel fallback over destructive direct vertex cutting
when the ninja arm became faceted. Use it only as a reviewed repair derivative.

### Geometry from a single image

When you have only the approved picture, write the request with
`"mode": "single_view"` and one `primary` input whose hash equals the source
authority; `scripts\run_hy3d_geometry.ps1` then hash-pins and runs
`run_hy3d_single_view.py` (Hunyuan3D-2, `hunyuan3d-dit-v2-0`). The multiview
route remains preferable when consistent front/left/back guidance exists,
because a single view infers the far side. Both routes stop at the same
fixed-view modeling approval. See `docs/AI_STAGES_SETUP.md` for the request
shape and VRAM needs.

## Stage 4 — existing-mesh PBR texture

### Default: Hunyuan3D-Paint 2.1

The tested local environment remains under the legacy studio. Use the wrapper
from the compiler repository; it verifies the exact legacy runner hash, checks
VRAM, and requires a topology/UV report without auto-retrying:

```powershell
.\scripts\run_hy3d21_texture.ps1 `
  -Mesh <approved-runtime-mesh.glb> `
  -Reference <front-reference.png> `
  -OutputObj <output.obj> `
  -Views 6 -Resolution 512
```

The bundled Python file is a provenance copy. The PowerShell wrapper invokes
the identical, hash-verified runner beside its tested `upstream/` and `models/`
directories in the legacy studio. Do not invoke the bundled provenance copy
directly or edit its path logic ad hoc mid-experiment.

It requires at least 21 GiB free VRAM and refuses face-order, geometry, or UV
drift beyond `1e-6`. A validation JSON is required even if upstream teardown
returns an error. Never auto-retry.

For a new, specifically justified diagnostic attempt, pass
`-DiagnosticsDir <new-directory>` to `scripts/run_hy3d21_texture.ps1`.
It captures the normal and position controls, raw AI multiview PBR images,
enhanced views, bake coverage, and pre/post-inpaint atlases. This is for locating
a correspondence failure before changing the method; it does not turn a repeat
of a visibly rejected candidate into useful evidence.

### Head-detail paint pass (same UVs, second paint)

A full-body paint at 512 px gives a 1.85 m character's head about fifty
pixels per view. `scripts/blender/extract_head_transport.py` cuts the head
and neck faces out of the UV authority with their exact UVs, so a second
`run_hy3d21_texture.ps1` run on that transport fills every view with the
head; `scripts/composite_head_paint.py` then bakes the recovered head maps
onto the body's (possibly repacked) layout and blends them over the body
maps inside the geometry-derived head region, byte-preserving everything
else. The reference must show only head and neck: a crop that kept a strip
of armour made the painter spread armour colour over the whole head.

Measured result on `sunset-ayric-v2` (2026-09-05): the pass paints skin,
hair, eyes and beard at ten times the earlier resolution, but on that
shallow-featured 19.6k-triangle head the views disagreed about where the
face was and the bake carried doubled eyes. Rejected under the landmark
rule. The tooling is validated; the method needs a head with real sockets
and a nose, or a single registered front image, to place features.

Hunyuan3D-Paint was the strongest full-body PBR base, not an accepted face
solution. It improved clothing and material response while degrading facial
identity. Review unlit albedo and lit PBR separately.

### Challenger: TRELLIS.2

```bash
cd /mnt/c/path/to/reference-asset-compiler       # your clone, seen from WSL
source /path/to/envs/trellis2/bin/activate      # your TRELLIS.2 environment
export PYTHONPATH=/path/to/TRELLIS.2
python workflows/texture/trellis2/run_trellis2_texturing.py \
  /path/to/approved-runtime-mesh.glb \
  /path/to/authority-cutout.png \
  /path/to/trellis-candidate.glb \
  --resolution 512 --texture-size 2048 --seed 42
```

The full-body trial was technically topology-safe but visually rejected for
facial bands, identity loss, and triangular speckling. Use only as an isolated
challenger or bounded semantic donor. The ninja's best legacy texture combined
a Hunyuan body with a constrained TRELLIS head donor; that does not justify
unmasked whole-body replacement.

### Texture acceptance

Render beauty evidence with the `calibrated` display profile:

```powershell
& $blender -b --factory-startup --python scripts\blender\render_turnaround.py -- `
  <painted.obj|glb> <new-fixed-views-dir> 1024 albedo smooth calibrated
```

The factory AgX transform at exposure 0 washed the cat's saturated fur to
salmon pink and clipped a third of the subject; it is kept only as `factory`
for reproducing old evidence and must not decide a texture gate.

If a lit view shows a hard highlight that the unlit albedo does not, check the
roughness map before blaming the art. `scripts/clamp_region_roughness.py`
lifts glossy texels inside a geometry-derived region mask to a floor as a
versioned derivative; it never touches base color, metallic, mesh, or UVs.

Once the reviewer passes the lit views, package an unrigged character with
`scripts/package_character_texture.py` (props use
`scripts/package_accepted_texture.py`). It stages the accepted maps as PNG,
binds them to the unchanged UV authority, applies only a recorded uniform
height and floor-origin transform, runs the texture gate against the skeleton
profile, and renders calibrated fixed views. A gate waiver must name the human
who accepted the measured debt. Then record `unwrap_and_bake` and
`texture_approval` with `rac promote` and the exact evidence files.

Reject displaced/stamped eyes, doubled scarf lines, a U under the chin, face
pixels on trousers, random bright specks, baked lighting, projection outlines,
and atlas seams. Facial landmarks must align to the modeled eye sockets, nose,
mouth, jaw, and hairline. The female remains the canonical failing example.

## Stage 5 — rigging

For a new humanoid, the preferred authoring tool is the user's licensed
Auto-Rig Pro installation in a compatible Blender. The extension is not bundled.
Live preflight on 2026-08-31 proved Auto-Rig Pro 3.74.40 operational in Blender
5.2.1, including Smart detection, Match to Rig, Bind, and the UE5 spine/neck/twist
controls. Run `scripts\workflow_doctor.ps1` to repeat that check without saving
preferences or changing an asset. The remaining blocker is a portable,
asset-neutral production driver. A candidate-only A-pose driver now lives at
`scripts\run_arp_rig_candidate.ps1`; it preserves rest geometry, uses explicit
checked-in body marker ratios, requires source-hash-bound and reviewer-approved
wrist plus per-digit joints, binds through a welded proxy, caps influences at
four, and refuses overwrite. The retained legacy driver still contains
field-scout-specific hand, clothing, material, and corrective assumptions that
must not leak into this generic stage. Deformation, ARP game export, Manny FBX,
and UE gates remain mandatory before promotion.

```powershell
.\scripts\run_arp_rig_candidate.ps1 `
  -InputMesh <approved-existing-mesh.glb> `
  -HandLandmarks <reviewed-source-bound-hand-landmarks.json> `
  -OutputDirectory <new-empty-candidate-directory>
```

The landmark file follows `schemas/hand-landmarks.schema.json`. It is not a
convenience hint: its source hash and reviewer approval are promotion evidence.

The single entry point for the rig stage is either-or:

```powershell
.\scripts\run_rig_candidate.ps1 -InputMesh <approved_mesh.fbx> -Profile ue5_manny|mascot_biped_tail `
  -OutputDirectory <new dir> [-Backbone auto|arp|landmark] [-HandLandmarks <reviewed.json>] `
  [-RingProfile <fitted-profile.json> -BindingReport <texture-payload-binding.json>]
```

It probes Auto-Rig Pro, takes it for humanoids when operational and reviewed
hand landmarks are supplied, and otherwise derives landmarks
(`derive_humanoid_landmarks.py` from the mesh and Manny's proportions,
`derive_mascot_landmarks.py` from the reviewed ring guides), builds and binds
with `rig_from_landmarks.py`, and runs `gate_rig.py` and `deform_test.py`.
`rig-route.json` records the route. The individual scripts below remain
callable when you need one step.

For a mascot on `mascot_biped_tail` (the `blender_custom_rig` backbone), the
portable route is landmark-first:

```powershell
& $blender -b --factory-startup --python-exit-code 1 --python scripts\blender\derive_mascot_landmarks.py -- `
  <prod>\<asset>_production.fbx <retopo>\joint-guides-*\fitted-profile.json `
  <prod>\texture-payload-binding.json <work>\rig\mascot-landmarks-v1
& $blender -b --factory-startup --python-exit-code 1 --python scripts\blender\rig_mascot_biped_tail.py -- `
  <prod>\<asset>_production.fbx <work>\rig\mascot-landmarks-v1\mascot-landmarks.json `
  profiles\skeletons\mascot_biped_tail.json <out>\<asset>_rigged.fbx <out>\rig-candidate.json
```

Every joint is derived from reviewer-passed ring centers and payload
cross-sections; review the overlay renders before trusting the bones. Then run
`gate_rig.py`, `record_rig_and_skin.py`, `deform_test.py`, and
`record_deformation.py` exactly as for a humanoid.

AniGen is included only as a challenger. It generates a replacement mesh and
skeleton from the authority image; it does not skin the topology that already
passed modeling and texture approval:

```bash
python workflows/rigging/anigen/run_anigen_candidate.py \
  --upstream /path/to/AniGen \
  --image /path/to/authority.png \
  --output-dir /path/to/candidate \
  --seed 42
```

A generated skeleton must pass the named profile, parent chains, maximum four
influences, side/facing, deformation, FBX round trip, and UE import gates. Do
not accept a random hierarchy because it poses once.

## Stage 6 — compile and UE5 proof

Once an authority FBX and material textures exist:

```powershell
.\scripts\compile_asset.ps1 -Recipe .\recipes\field-scout-male.json
# or the complete retained cohort
.\scripts\compile_all.ps1
```

Then follow `docs/COMPILER.md` for UE import, exact payload verification, map,
and cook.

To review characters in motion, rebuild the gallery and give every placed
skeleton the Manny idle:

```powershell
$env:RAC_ROOT = (Get-Location).Path
& UnrealEditor-Cmd.exe .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\build_gallery_level.py" -unattended -nop4 -nosplash -stdout
& UnrealEditor-Cmd.exe .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\setup_gallery_playable.py" -unattended -nop4 -nosplash -stdout
& UnrealEditor.exe .\work\ue5-validate\RacValidate.uproject -game -windowed -ResX=1920 -ResY=1080 -NoTextureStreaming
```

The second script builds IK Rigs from bone names, exact-maps chains (a
mascot tail stays unmapped), batch-retargets `MM_Idle`, and writes
`work/ue5-gallery-idle.json`. The project's default game mode is the Third
Person template, so `-game` drops the reviewer in as Manny. The compile path is verified; it should not be replaced by ComfyUI.

## Current texture task decision

The remaining texture defects are upstream atlas/projection defects, not UE
material or rig defects. The correct next experiment is:

1. coherent semantic UV islands on the final-scale runtime mesh;
2. de-lit source/reference and base color;
3. Hunyuan3D-Paint 2.1 body PBR candidate;
4. head-only, UV-aware identity projection constrained to head geometry;
5. fixed unlit face/body/edge review;
6. only then compile and UE verify.

Do not patch the female by another whole-face stamp or image-space heuristic.
