# Source-locked character head and neck workflow

The reusable rule is **geometry fit first, approved face locked, body transition
last**. Merely reversing two image stamps does not register a face to a mesh.
Use an image-conditioned AI head with modeled facial features and coherent UVs;
fit that existing surface to the rigged body, then reconcile the small neck band.
No manual replacement head geometry, portrait redraw or whole-body repaint is
part of this repair. The workshop uses a rigid head attachment, not a facial rig.

## Repeat the neck transfer without Codex or an inference GPU

From the repository root, with the recipe's local source artifacts available:

```powershell
./scripts/run_neck_transition.ps1 -Output work/sunset-ayric-v2/rig/my-neck-review-v001
```

Pass `-Blender C:/path/to/blender.exe` on another installation. `-SkipReview`
skips the five CPU albedo close-ups, not validation. Existing output directories
are refused. No GPU inference or service/model install is needed for this step.

`recipes/assemblies/sunset-ayric-neck-transition.json` pins the assembly and both
texture images by SHA256, names the head/body objects, and defines a measured
neck box, proximity limit, feather heights and target skin roughness/metallicity.
For another character, make a new recipe and measure its collar/neck; these metre
coordinates and source hashes are **not** universal human anatomy defaults.

The implementation:

1. Builds a BVH of the already fitted head. For each body corner near the neck,
   finds the nearest head triangle and barycentrically transports its UV sample.
2. Stores that existing head colour as linear RGB and geometric blend weight as
   alpha in the body mesh's `RAC_NeckTransfer` corner-colour attribute. Original
   images remain read-only. Colour classification is per pixel: a blue triangle
   corner may enclose a skin-coloured texel, so corner-only classification misses
   the very seam we need to repair.
3. Blends only skin-like texels in the measured neck band. Height and colour
   guards protect the blue collar and gold trim. Roughness/metallicity blend with
   the same mask. The matching head surface normal is transported in two new
   auxiliary UV channels, expressed in the body's tangent frame. Authored normal
   detail blends toward that direction only inside the mask. Original UV0 and
   the normal/AO behaviour outside the mask remain unchanged. This is a bounded
   material transition, not a claim that all surface intersections are welded.
4. Checks an exact before/after fingerprint of head/body positions, topology,
   original UV0, mesh normals, transforms, body weights and skeleton. The only
   added mesh data are colour and two auxiliary normal-transport UV channels.
   Exports a fresh FBX and
   records hashes, affected corners and colour encoding in `neck-transfer.json`.

Blender exports colour with `colors_type='LINEAR'`. UE imports vertex colours
with `VertexColorImportOption.REPLACE`. The native adapter clones the original
material and instance, preserves texture parameters, and adds the same blend.
Pre-skinned position must pass through a vertex interpolator before pixel use;
connecting it directly to the pixel shader produces a grey fallback material.
Do not accept a successful import commandlet as proof the shader rendered.

The body contains ngons, so the transport computes UV tangent frames from its
loop triangles without triangulating the protected mesh. UE reverses UV V at
import; the normal decoder accounts for both that reversal and tangent Y.
The editor bridge's read-only `inspect_skeletal_seam_buffers` probe verifies
actual native vertex colour presence/ranges rather than assuming FBX settings
guarantee transport. Opposite-side native views remain necessary for the normal
direction check; a mathematical transform is not a substitute for that review.

## Reproduce the head/body fit

The fit recipe pins the existing anatomical rig, detailed AI head, body texture,
measured head UV-island rules, two additional skin-only islands, and rigid head
placement. The source hash is what makes those polygon/island identifiers safe.

```powershell
$blender = 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'
$repo = (Get-Location).Path
& $blender -b --factory-startup --python-exit-code 1 --python "$repo/scripts/blender/assemble_workshop_head_candidate.py" -- $repo --output work/sunset-ayric-v2/rig/my-head-fit-v001
& $blender -b --factory-startup --python-exit-code 1 --python "$repo/scripts/blender/verify_workshop_body_subset.py" -- $repo --job work/sunset-ayric-v2/rig/my-head-fit-v001
```

The subset verifier requires exact surviving positions/UVs/weights and skeleton.
Restored source split normals allow less than 0.0001 component error from Blender
custom-normal encoding. A fresh recipe replay passed with 7,947 body polygons
and maximum normal delta 0.00007582. FBX/Blend files can contain changing metadata;
semantic fingerprints, not byte-identical exports, are the repeatability check.

Two independent executions of the final colour-plus-normal neck method also
matched exactly, including all generated UV/colour values, source fingerprints,
recipe and implementation hashes. Verify another replay with
`scripts/blender/verify_neck_replay.py` (Blender arguments after `--`:
baseline directory, replay directory, fresh output JSON). The retained proof is
`work/sunset-ayric-v2/rig/neck-final-replay-v001/replay-verification.json` for the
first normal-transport implementation. That version exceeded the native vertex
budget and is retained as rejected. The bounded version keeps constant auxiliary
UVs wherever blend weight is zero; otherwise unused per-corner normals split
vertices across the whole body. Its final replay and runtime results are recorded
in `AYRIC_REPAIR_2026-09-06.md`. The native builder now refuses missing colour
buffers, empty blend coverage or more than 15,000 body vertices before creating
a player blueprint.

The user explicitly accepts a separately acquired head and a higher total vertex
count when justified by reviewed game use. This repair does not reject useful
head detail merely to preserve the old single-mesh count. The v050 rejection was
different: unused per-corner data inflated the **body** from 11,825 to 28,908 native
vertices without adding geometry detail. Bounding that data restores 12,574 body
vertices. The separate head remains 12,740 native LOD0 vertices / 19,988 triangles.
Judge the combined avatar, LODs, attachment, materials and actual runtime; these
counts are evidence, not a universal guarantee for every target GPU or game.

To use a new fit as the seam authority, create a new neck recipe pointing to it
and pin its actual SHA256 **after** its fit/subset review. Do not silently replace
the source hash on the canonical recipe to bypass a changed-authority rejection.

## Native adapter and acceptance gates

The workshop-specific `scripts/ue5/build_workshop_head_assembly.py` consumes:

- `RAC_ROOT`: absolute repository path.
- `RAC_VERSION`: fresh native version, e.g. `vNNN`.
- `RAC_ASSEMBLY_JOB`: repository-relative verified body/neck output directory.
- `RAC_ASSEMBLY_MESH_FOLDER`: fresh `/Game/...` destination.
- `RAC_TARGET_MESH`: expected destination skeletal mesh, required by the shared
  player adapter. The build receipt records the actual resolved object path.

Run it as an Unreal Python commandlet on the workshop validation project.
It requires the preserved v036 player, animations, skeleton, existing native AI
head and `integrations/ue5/RacEditorBridge`. This adapter is intentionally specific
to the workshop; it is not a generic import into an arbitrary empty UE project.

The rigid head fits in the **reference pose**: clear the spawned player's idle
animation before measuring the head socket. Otherwise idle displacement becomes
a permanent neck offset. Keep the same skeleton and preserve the body/sword
animation setup. Clone blueprints/maps/materials; do not overwrite the fallback.

Review `review_character_locomotion.py` with `RAC_REVIEW_BLUEPRINT`, `RAC_TARGET_MESH`,
`RAC_ANIM_FOLDER`, and a fresh `RAC_RIG_REVIEW` directory. Inspect all five head
angles and rest/idle/two walking phases/jump. Read the log for shader compile
failures as well as the review JSON. Finally cook a fresh package and run
`RacDemoAudit` with both `RACDemoExpectedMesh` and `RACDemoExpectedHeadMesh`.
Require all attachment, collision, locomotion and actual cooked LOD budget checks.

Human approval of the neck close-ups is separate from these technical checks.
Neither a flattering preview nor a cooked pass automatically promotes an asset.

## Boundaries and retained failures

Whole-face projection onto the shallow old head failed identity/geometry fit.
Height-only head cuts left old chin pieces. Broad warm-colour face removal also
removed gold trim. Flat lining over large collar UV islands damaged the design.
Sparse corner-only skin masks missed pale texels inside otherwise blue triangles.
Each failed version is retained in the workshop evidence, not reused as authority.

The current strategy leaves the approved detailed face and clothing outside the
neck band untouched. A rigid modular junction may still reveal a geometric edge
under extreme close-up or deformation. Do not describe this as a seamless facial
animation rig; facial expressions and cloth remain outside the demonstrated work.

Tests: `./scripts/verify.ps1`. Numerical contracts live in
`src/reference_asset_compiler/neck_transition.py`; Blender transport and native
material construction are in their respective `scripts/blender` and `scripts/ue5`
adapters. See `docs/AYRIC_REPAIR_2026-09-06.md` for exact candidate results.
