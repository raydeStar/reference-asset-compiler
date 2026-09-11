# Cross-agent handoff: V1 checkpoint

Last updated: 2026-09-06. The sections up to *Definition of V1 completion*
describe the 2026-08-30 checkpoint; everything after them is a dated log
appended in order, so the current state is the last dated section.

## What this checkpoint is

This file is the operational memory needed to resume the project. It records
what was attempted, what the user accepted or rejected, where the strongest
artifacts live, and what remains unproven. It intentionally does not claim
that the current cohort is production-ready.

The portable compiler repository is:

the root of this repository

The legacy experimental studio is:

the tree `RAC_LEGACY_ROOT` points at (machine-local, not in this repository)

The legacy studio must be preserved. It is a large, dirty worktree containing
the current Blender, ComfyUI, texture, rig, render, and UE5 evidence. Open
interactive processes may own files in it.

## User-approved working method

1. Begin with an explicit source image or turnaround. It is the artistic
   authority, not inspiration to approximate loosely.
2. The image must condition an AI geometry or mapping stage. An agent must not
   inspect it and manually or procedurally approximate the asset in Blender.
   Blender is downstream cleanup, retopology, UV/bake, rigging, and evidence.
3. Generate AI geometry candidates in isolation. Compare candidates in fixed
   clay front, three-quarter, side, and back views.
4. Approve modeling before texture work. Geometry repairs must preserve the
   approved high-resolution authority.
5. Texture the approved topology. Facial landmarks must follow the modeled
   sockets and features rather than stamping a resized portrait over the UVs.
6. Rig only after texture acceptance. Humanoids must use the declared UE5
   skeleton contract so the existing animation ecosystem remains available.
7. Validate deformations, UE import, a representative map, and a cooked build.
8. Retain compact evidence and rejection reports; periodically delete only
   reproducible rejected bulk artifacts.

## Compiler status (2026-08-30)

Four legacy characters compile end to end from immutable runtime inputs into
gated UE5 packages. See [COMPILER.md](COMPILER.md). This proves the downstream
compiler mechanics, not V1 asset eligibility: the later AI-conditioned geometry
rule requires a portable image-to-AI-to-runtime lineage that those legacy FBXs
do not inherit automatically. One command:

```powershell
.\scripts\compile_all.ps1
```

| Asset | Skeleton profile | Bones (FBX / UE5) | Tris | Height | Rig gate | Deformation | Texture gate |
|---|---|---|---|---|---|---|---|
| field-scout-male | `ue5_manny` | 86 / 87 | 67,907 | 199.9 cm | pass | pass | waived |
| field-scout-female | `ue5_manny` | 86 / 87 | 70,000 | 200.0 cm | pass | pass | waived |
| ninja-man | `ue4_mannequin` | 75 / 76 | 54,220 | 180.0 cm | pass after repair | pass | waived |
| fox-mascot | `mascot_biped_tail` | 26 / 27 | 69,545 | 199.4 cm | pass | pass | waived |

Measured texture quality, recorded in every shipped manifest:

| Asset | baked-light corr | texels/cm² | UV islands |
|---|---|---|---|
| field-scout-male | +0.18 | 303 | 503 |
| field-scout-female | +0.28 (face +0.41) | 306 | 395 |
| ninja-man | +0.08 | 145 | 942 |
| fox-mascot | -0.33 | 42 | 515 |

Every asset needs a `texture_waiver` to pass the texture gate. That is
deliberate: see [ESCALATE-textures.md](ESCALATE-textures.md).

All three: max 4 influences, zero unweighted vertices, zero out-of-bounds UVs,
zero high-aspect-ratio faces.

### What the new gates found

These were all present in the accepted legacy artifacts and none of them are
visible in a bind-pose render.

1. **ninja-man mesh faced +Y while its skeleton faced -Y.** `hand_l` drove the
   visually right hand and the knees would have bent backwards under animation.
   Repaired by rotating the mesh 180 degrees about its own vertical axis and
   swapping every `_l`/`_r` vertex group in the same pass. Verified: posing
   `upperarm_l` alone now moves only the +X half of the body (`side_bias +1.00`).
2. **ninja-man was 0.95 m tall** — half scale — and offset 17 cm off-origin in
   Y. Now 1.80 m, root bone on the world origin.
3. **fox-mascot's origin sat at mid-body**, feet at Z = -1.0. It would have
   imported sunk a metre into the floor. Now feet on Z = 0.
4. **fox-mascot's authority FBX referenced a texture that does not exist**
   (`textures/packed/fox`, 0x0). It rendered untextured. Materials are now
   rebuilt from the paths declared in the recipe rather than trusting the FBX.
5. **All three carried a 0.01 armature scale** left over from the export addon.
   Baked into the data.

### Second pass (post UE5 import review)

6. **The shipped FBX referenced textures that were never copied.** The export
   wrote them into a `<name>.fbm` sidecar that the packaging step did not
   publish. Textures are now staged under their shipped names *before* export
   and referenced relatively, so exactly one copy of each map ships and the
   reference resolves.
7. **The UE5 import script now creates and assigns a material.** A skeletal
   mesh imported without one renders as a featureless white blob, which reads
   as a broken export when only the material was missing.
8. **Multi-material assets are supported**, which is what let the female be
   compiled at all: her face is a separate projected material.
9. **`gate_texture.py` added.** Baked lighting, texel density and UV
   fragmentation are now measured on every build.
10. **LODs are specified in the manifest** and generated by UE5's reducer,
    never by Blender's Decimate.

### Known limitations, unchanged by this work

- **No normal maps exist** for any asset. Only BaseColor and ORM, and the
  female has no ORM either. The manifest declares the correct Normal import
  settings for when they do.
- **Textures are the binding quality constraint**, not the rigs. All four rigs
  pass their contracts and deform correctly. See
  [ESCALATE-textures.md](ESCALATE-textures.md) for the measured defects and
  what fixing them requires. Two heuristic pixel repairs were built, tested,
  found to make the assets worse, and deleted rather than shipped.
- **field-scout-female is not visually shippable.** Her rig is a clean 86-bone
  Manny and she passes every mechanical gate, but her face is a flat projection
  and two cartoon eye decals are painted onto her trousers.
- **ninja-man is on the UE4 Mannequin skeleton.** Supported in UE5 through the
  stock IK Retargeter; not converted to Manny. See COMPILER.md for why.
- **All three are 2.7x to 3.5x over the 20,000 triangle budget.** Each carries
  an explicit, recorded waiver rather than a silent pass. Retopology is real
  outstanding work.
- **Auto-Rig Pro 3.74.40 is installed and operational** in Blender 5.2.1. A
  headless empty-scene preflight on 2026-08-31 verified Smart detection, Match
  to Rig, Bind, and the UE5 axial controls. The old direct-import failure came
  from initializing ARP against the saved startup mesh, not an absent add-on.
  A portable A-pose candidate driver now exists at
  `scripts/run_arp_rig_candidate.ps1`; it uses explicit checked-in marker and
  bind settings, preserves a geometry hash, and stops before claiming
  deformation or runtime success. Existing shipped FBXs remain immutable
  authorities until this generic path reproduces their full gates.
- **UE5 import and cook are now verified** against UE 5.8.2. All four import at
  exactly their manifest height, with 3 LODs, correct material assignment and
  correct texture settings; the gallery map cooks with 0 errors and 0 warnings
  and all 24 packages present in the referenced set. See COMPILER.md.
- **In-engine screenshots remain unproven.** SceneCapture2D returns black from
  a commandlet and needs an interactive editor session. The numeric import
  verification stands in, and the capture script refuses to write black frames
  rather than leaving misleading evidence on disk.

## Current asset matrix

Primary legacy authorities and experiment ledgers:

| Asset | Reference authority | Primary manifest/ledger |
|---|---|---|
| Original male | `references/field-scout-male-v2/texture-authority-turnaround-v1.png` plus `references/field-scout-male-v2/head-authority-v1.png` | `asset_manifests/field_scout_male_v2_runtime_candidate.json` |
| Female | `references/field-scout-female-v4/turnaround-v1/` and the generated head authorities under `references/field-scout-female/` | `asset_manifests/field_scout_female_v4_authority.json` and `asset_manifests/field_scout_female_texture_selection_v2.json` |
| Ninja | `references/ninja-man-turnaround-v1.png` with split views under `references/ninja-man-v1/` | `asset_manifests/ninja_man_v2_authority_benchmark.json` and `asset_manifests/ninja_man_v2_runtime_candidate.json` |
| Fox mascot | `references/fox-mascot-v1/front-authority.png` plus the selected turnaround under `references/fox-mascot-v2/turnaround-v1/` | `asset_manifests/fox_mascot_v2_authority.json` |
| Office chair | `references/prop-ai-v1/office-chair/turnaround-v2.png` | `asset_manifests/repro-v1-20260830-office-chair.json` |
| Sword | `references/prop-ai-v1/weathered-longsword/front-rgba-no-shadow.png` | `asset_manifests/repro-v1-20260830-weathered-longsword.json` |
| Guitar | `references/prop-ai-v1/sunburst-guitar/turnaround-v2.png` | `asset_manifests/repro-v1-20260830-sunburst-guitar.json` |

These legacy paths identify the latest working record, but the manifests still
need normalization into the compiler schema before they become portable V1
fixtures.

| Asset | Modeling | Texture | Rig/UE | Honest resume state |
|---|---|---|---|---|
| Original male | Historical appearance baseline approved; fresh 70k AI derivative is review-ready but not approved | Broadly accepted legacy texture; final eye repair looks good | Downstream Manny compile evidence exists | **Not V1-eligible yet.** `work/field-scout-male-ai-v2` hash-binds the real Hunyuan multiview source and its QEM modeling derivative, but the selected runtime FBX does not have a receipt-complete derivation chain back to it. Keep the current package as regression evidence. |
| Female V4 | Exact Hunyuan V4 70k modeling checkpoint approved; conservative semantic cleanup passes with identical native round-trip topology | **Rejected/unresolved**: stamped or doubled face, landmark displacement, seam lines | Legacy humanoid setup cannot ratify a rejected texture | `work/field-scout-female-ai-v4` now passes generation, modeling, and semantic cleanup. AutoRemesher erased garment, face, and hand structure. A strict audit found 19 micro-edges behind QuadriFlow's generic refusal; a bounded repair cleared them, but the resulting all-quad challenger exceeded surface-deviation limits and was rejected. The 20k feature-QEM challenger was initially misjudged under flat shading; a geometry-identical smooth review corrected the visual record, but its 0% quad topology still fails the articulated contract before rigging. Production retopology remains pending on a guide- or landmark-aware quad route. See `docs/evidence/field-scout-female-v4-retopology-trials-v1.json`. |
| Ninja | Historical modeling approved after a long cleanup chain; fresh 70k Hunyuan derivative rejected at portable modeling preflight | Broadly accepted legacy texture; eye repair V24 verified in UE | Downstream skeletal import evidence exists | **Not V1-eligible yet.** The preserved Pixal3D authority is genuine AI output, but the current runtime FBX's authored-detail chain is not covered by the portable derivative contract. The fresh Hunyuan V3 challenger is hash-bound in `work/ninja-man-ai-v3` but rejected because it loses the mask, layered vest, wraps, boot construction, hands, and feet. Return to image-conditioned AI acquisition; do not rebuild those details in Blender. |
| Fox mascot (RETIRED by Ayric 2026-09-01) | Historical shape broadly accepted; exactly one tail required | Broadly accepted after cleanup; eye repair V4 verified in UE | Downstream dedicated-skeleton evidence exists | **Not V1-eligible yet.** The recorded Hunyuan candidates were rejected for a head-neck gap, and the selected voxel-union fallback lacks a portable AI-to-runtime derivation chain. `work/fox-mascot-ai-v3` now anchors a fresh run to the primary one-tail source; generation is pending. |
| Office chair | **Passed by Ayric:** the preserved Hunyuan multiview candidate is the modeling authority; conservative native cleanup and the exact closed 18,000-triangle production retopology also pass | **Passed by Ayric and mechanically closed:** the exact retained 4096 parent of the approved Hunyuan mapping measures 427.8 texels/cm2 and +0.345 baked-light correlation after physical normalization | Static prop; UE import passed | `work/office-chair-ai-v2` now passes through UE5 import. The production payload is exactly 1.019 m, 18,000 triangles, samples BaseColor plus packed ORM, and has three UE LODs. `/Game/Compiled/L_RacGallery` contains front/back placements and the visible UE5.8 editor is open for the separate human runtime-review gate. Cook remains correctly blocked until that in-engine review passes. See `docs/evidence/office-chair-ai-v2-ue-import-v1.json`. |
| Sword | AI-produced candidate was generally acceptable | Not finally ratified at the same confidence as chair | Static prop | Re-run through formal static-object gates before claiming pass. |
| Guitar | **Rejected as rudimentary** | **Rejected**: low-quality front, excessive bright specks, failed painted repairs | Static prop | `work/sunburst-guitar-ai-v2` now anchors a fresh AI run to the multiview turnaround; generation is pending. Do not paint frets or hardware onto weak geometry. |

“Provisional pass” means that the visible checkpoint was accepted well enough
to move on. It does not mean production-ready.

## Strongest current repair artifacts

### Adventurer cat replacement (2026-09-01)

Ayric's close review superseded the v1 cat after texture mapping: its tail
curved back into a conspicuous loop, and the face/scarf/chest mapping lacked
local definition. Those are separate failures: the tail invalidates the v1
modeling lineage, while the weak landmarks reject its texture candidate. The
active cohort now points to `orange-adventurer-cat-ai-v2`, whose immutable
AI-edited source and independent front/left/back guidance require exactly one
open, backward-trailing tail. V2 must restart at image-conditioned geometry;
the accepted v1 retopology and texture are retained as rejection evidence, not
silently repaired or promoted.

Ayric approved the corrected v2 dense modeling candidate. Conservative cleanup
passes. The first QEM/pairing chain exposed a native-save ordering bug and five
coincident two-sided detail sheets around the muzzle/head and chest. Deleting
those sheets made the numeric topology look clean but caused 12.6 cm maximum
surface deviation, so that challenger was rejected. Attempt009 retained each
original visible sheet behind a 0.25 mm tetrahedral back shell and met the
numeric topology limits, but Ayric rejected its visibly bumpy body surface.
Feature-aware fairing attempt011 now preserves that closed 20,000-triangle,
80.0126%-quad topology while reducing the low-importance Laplacian roughness
45.90%. It stays within 4.96 mm p99 and 11.63 mm maximum deviation from the
dense AI authority. Fixed matcaps are visibly calmer, but wireframe review still
shows stochastic QEM flow through deformation zones, so it is a surface base,
not a production retopology pass.

Whole-surface AutoRemesher challengers over the faired base are retired: the
calibrated run returned 8,571 triangles with 33 boundary and 37 non-manifold
edges, and erased eyes, whiskers, cuffs, and costume definition. The checker now
rejects open or non-manifold AutoRemesher output instead of reporting a false
mechanical pass. The active challenger projects thirteen source-bound rings at
the neck, shoulders, elbows, wrists, upper thighs, knees, and ankles. A bounded
local fitter keeps every center within 12 cm of its semantic draft and at least
5 mm inside the exact AI-derived surface. Attempt004 passes that projection
audit and awaits Ayric's guide-overlay review before any local joint-band
topology is inserted. Ayric passed that overlay and accepted the slightly wavy
attempt011 surface for texture progression. Four bounded limb-selection audits
then proved that local tube surgery cannot isolate both short legs: narrow
settings select slivers, while useful widths branch into adjacent geometry.
No topology was mutated and that route is retired for this cat. The canonical
retopology receipt now passes with the residual waviness and stochastic joint
flow explicitly carried into deformation validation.

Geometry-locked UV attempt001 passes: the native surface did not move, the OBJ
transport stayed within 0.879 micrometers, and its 19,982 triangles differ from
the 20,000-triangle authority only by measured duplicate faces. After Ayric
authorized ComfyUI lifecycle control, the verified idle server was stopped and
free VRAM rose above the unwaived 21,504 MiB floor. Exactly one six-view,
512-pixel Hunyuan3D-Paint 2.1 attempt then mapped the accepted transport while
remaining directly conditioned by the original v2 image. Its 19,982-triangle
GLB validates at 0.000000151 m geometry delta and 0.000000053 UV delta. The
front initially retained readable costume elements and the open striped tail,
but Ayric rejected its sloppy defining landmarks: the broad round reference
eyes became a pinched teardrop and a narrow tilted eye. Albedo-only evidence
proved the distortion was painted rather than lit. A source-locked AI edit then
created an immutable reference with two round eyes. Exactly one new Hunyuan
paint challenger validated, but its full repaint washed and smeared the body,
so it too was rejected. Geometry-selected atlas borrowing retained one angular
eye; direct Hunyuan-camera projection fixed both eyes but initially exposed UV
boundary hairlines. Attempt006 now runs that direct projection through Hunyuan's
own non-vertex UV inpaint before compositing only the visible front upper head.
Its two eye boundaries and green irises are round and matched in unlit evidence;
only 4.44% of atlas texels are eligible for correction, while attempt001's
stronger body, gear, tail, metallic, and roughness maps remain intact. Geometry
and UVs do not change. The second full paint's files were validated before the
known upstream -1073741819 teardown exit; no automatic retry was made, and
ComfyUI was restored with its original arguments and an empty queue. Attempt006
awaits Ayric's fixed-view approval; no rig claim follows yet. See
`docs/evidence/orange-adventurer-cat-ai-v2-retopology-trials-v1.json`
and `docs/evidence/orange-adventurer-cat-ai-v2-texture-trials-v1.json`.

Ayric reviewed attempt006's beauty views and called the texture janky. Direct
re-rendering of the identical atlas showed the review renderer, not the atlas,
produced the salmon-pink, washed look: `render_turnaround.py` used Blender's
factory AgX transform at exposure 0 under the hot three-light rig, clipping 33%
of subject pixels, while the unlit albedo of the same atlas was already
saturated and reference-like. The OBJ import also read the metallic and
roughness maps as sRGB with doubled specular. The renderer now takes a sixth
argument; `calibrated` (Standard transform, exposure -1.5, data maps as
Non-Color, default specular) puts the forehead fur within a few percent of the
reference RGB. `fixed-views-calibrated/review-sheet.png` under attempt006
presents the same atlas both ways for Ayric's fresh decision. Historical AgX
beauty views across every asset are not comparable with calibrated ones and
should not be used for texture judgement. Hunyuan's metallic map has a uniform
floor near 0.166 and its GLB carries KHR_materials_specular 2.0; both are
recorded as packaging concerns. Remaining real defects at calibrated exposure
are soft chest gear from the 512-pixel paint, confetti-UV patchiness on the
tail, boots, and shorts, and a small tail-root artifact.

Ayric then asked about the white shape on the viewer-left eye. The unlit albedo
proved the eye art was clean, so it was a specular reflection: Hunyuan left both
eyes at roughness near 0.11 on an otherwise 0.95 head and the key light
mirrored off the lumpy eye geometry. `scripts/clamp_region_roughness.py` lifted
only the two glossy components inside attempt006's geometry-derived head-front
mask (4,235 texels, 0.10% of the atlas) to a 0.7 floor, chosen over 0.35 and
0.5 after rendering all three. Base color, metallic, mesh, and UVs are copied
bit-for-bit. `texture/eye-roughness-attempt007/fixed-views-calibrated` holds
its views and a before/after sheet, and it now awaits Ayric's texture decision.
The matcap pass is rendered before albedo again and keeps the factory
transform, fixing black matcaps whenever albedo evidence was requested.

Ayric passed attempt007 and directed the cat to ship at the UE5.8 Manny standard scale.
`scripts/package_character_texture.py` (the character-side counterpart of the
prop remediation step) staged the attempt006 base color and metallic and the
attempt007 roughness as PNG, bound them to the unchanged UV authority, scaled
the payload uniformly from Hunyuan's 2.0 m box to 1.80 m with the origin on the
floor, exported `prod-v1/orange-adventurer-cat-ai-v2_production.fbx`, and
rendered calibrated fixed views. The texture gate measured 19.5 texels/cm2
(floor 120), +0.22 baked-light correlation (limit 0.20), and 783 UV islands
(advisory 300); at the native 2.0 m the density was 15.8. Ayric waived the two
failures in their own name so the debt stays visible. `unwrap_and_bake` and
`texture_approval` are recorded in the ledger and the workspace audit passes.
The next gate is `rig_and_skin` against `mascot_biped_tail`: routing records no
portable existing-mesh rig driver for `blender_custom_rig`, and the Auto-Rig
Pro candidate driver is humanoid-only with no tail, so the rig route needs an
explicit decision before any bones are authored.

The cat now has a portable mascot rig route. `scripts/blender/derive_mascot_landmarks.py`
derives all 26 `mascot_biped_tail` joints from source-bound evidence: the
reviewer-passed joint-ring centers carried into the payload frame and mirrored
about the measured midline, cross-section centroids for the spine, surface
reach for hand and toe ends, and a binned centerline for the tail. It writes a
hash-bound landmark file and skeleton overlays. `scripts/blender/rig_mascot_biped_tail.py`
builds the armature from that file and the profile, binds with heat weights,
caps influences at four, proves the geometry fingerprint is unchanged, and
exports FBX. Attempt001 passed `gate_rig.py` (26 bones, -Y facing, left on
+X, 100% coverage, no fill) and the five-pose deformation suite (left-only
side bias +1.00, no volume collapse). `rig_and_skin` and
`deformation_validation` are recorded and the audit passes. See
`docs/evidence/orange-adventurer-cat-ai-v2-rig-trials-v1.json` and the review
sheet under `rig/mascot-v1-attempt001/`. Next is UE5 import and in-engine
motion review; the interactive editor is open, so process ownership must be
confirmed before the import commandlet runs.

The cat is in UE5. Ayric authorized the run; the open editor turned out to be
the legacy project, so the validation project was free. `recipes/orange-adventurer-cat-ai-v2-production.json`
compiles the exact rigged FBX with the prod-v1 BaseColor and a packed ORM (AO
constant, accepted roughness and metallic); `compile_asset.ps1` passed every
gate with Ayric's texture waiver carried through. Headless import into
`RacValidate` verified 180.0 cm, the body material sampling all three
textures, 3 LODs, and correct texture settings; `ue5_import` is recorded. The
gallery was rebuilt with the cat at X=640, and `scripts/ue5/setup_gallery_playable.py`
built IK Rigs from bone names for Manny and every placed skeleton, exact-mapped
the chains (tail deliberately unmapped), and batch-retargeted `MM_Idle` onto
all nine characters, which now loop it in the level. The Third Person template
character, game mode, and input pack were copied into the project and set as
the global default game mode, so Play drops the reviewer in as Manny at the
PlayerStart. See `docs/evidence/orange-adventurer-cat-ai-v2-ue-import-v1.json`.
`ue5_motion_review` and `cook` remain human-gated.

The first gallery launch showed only the chairs. Two causes: the Third Person
Blueprints had been copied from the C++ template and referenced a missing
`TP_ThirdPerson` module (replaced with the Blueprint-only template's assets),
and every retargeted idle had hoisted its character 50 to 90 metres into the
air because the compiled skeletons carry a 100x root scale with bone offsets in
metres (see DECISIONS). The setup script now measures that ancestor scale,
drops the IK ops, and rescales the pelvis track; all nine idles verify at
plausible pelvis heights in `work/ue5-gallery-idle.json`.

Second launch: the characters rendered but every legacy face pitched down and
the ninja hands and feet twisted, while the cat read correctly. Three retarget
poses were compared per skeleton with the pose composed from the animation
data (the placed component does not re-evaluate inside a commandlet): aligning
all bones to Manny matches segment directions within 2 degrees but rotates the
legacy heads down because their head and spine bones tilt differently from
Manny while their faces already look forward; limbs-only alignment is now the
policy, since limb rest poses differ legitimately (the ninja rests near a
T-pose). Ayric retired the fox mascot the same day: `recipes/fox-mascot.json`,
`out/fox-mascot*`, and the UE `FoxMascot*` content were removed and the gallery
rebuilt with seven skeletal characters. Ayric judged the cat fine in-engine;
the formal `ue5_motion_review` record is still pending.

**V1 stamp (2026-09-01).** Ayric accepted the pipeline as a repeatable product:
the cat runs image -> geometry -> retopology -> texture -> rig -> UE5 gallery
with two human approvals and hash-bound receipts at every stage. Accepted
residuals, to be hand-tweaked rather than scripted further: the ninja's hands
still roll under the retargeted idle (chain alignment cannot fix roll; adjust
`hand_l`/`hand_r` in the target retarget pose of
`/Game/Compiled/Retargeted/<run>/Rigs/RTG_RAC_Manny_to_NinjaMan*`), the 100x
skeleton root scale, and the texture density and UV-island waivers. The README
was rewritten for indie developers with screenshots under `docs/images/`.

Later the same day Ayric asked for an either-or rig route so nobody needs the
paid add-on. `scripts/run_rig_candidate.ps1` probes Auto-Rig Pro and otherwise
runs the free landmark route; `derive_humanoid_landmarks.py` derives the
ue5_manny joint set from the mesh plus Epic's Manny reference pose
(`profiles/rigging/manny-reference-pose.json`, extracted from the UE 5.8
template mesh), and `rig_from_landmarks.py` generalizes the mascot builder to
any profile, expressing the root as the armature object when the profile
allows it. Tested on the field-scout male with its armature stripped: 86
bones, ue5_manny gate passed, five poses passed; heat weights failed on that
layered mesh and the envelope fallback carried it, which is the documented
quality gap versus Auto-Rig Pro. Registered as `blender_landmark_rig` and as
the `blender_custom_rig` driver, both candidate-only.

**Privacy and security review (2026-09-01).** Before publication the tracked
tree and the full history were scanned for credentials, tokens, private keys,
e-mail addresses, IP addresses, and machine paths; the code was swept for
shell execution, unsafe deserialization, and network access. Findings: no
secrets anywhere; network access limited to official Hugging Face model
downloads and a localhost ComfyUI URL; CI actions pinned to commits with
read-only permissions. Two fixes: a personal photo filename inside the
preserved ComfyUI graph was neutralized (hash pin updated in
`workflows/catalog.json`), and the history, which carried the author's
personal e-mail on every commit and machine paths in early diffs, was squashed
into one initial commit under a GitHub no-reply identity. The reviewer handle
"Ayric" remains on receipts and in the LICENSE by choice.

The fox was first removed from the active V1 cohort and replaced by the now
superseded `orange-adventurer-cat-ai-v1`. Ayric had approved its Hunyuan3D modeling
candidate before the later close review exposed the looped tail. Source-bound generation and conservative cleanup passed. Ayric
rejected the 9,408-vertex voxel/AutoRemesher challenger because isolated views
showed erased facial, whisker, hand, belt, and costume detail. A subsequent
regional challenger protected the whisker island but still flattened the face
and costume, exceeded 20,000 triangles, and opened 182 boundary edges; it is
also rejected.

The current bounded challenger preserves the approved AI surface instead of
reconstructing its volume. Feature-weighted QEM first healed the 27 inherited
cleanup holes and reduced the mesh to 9,984 vertices and exactly 20,000
triangles. Compatible triangle pairing then reached 8,792 quads (80.0073%)
without moving a vertex. The result is closed and manifold, with 3.81 mm p99
and 11.09 mm maximum symmetric deviation, and fixed views retain the eyes,
muzzle, whiskers, scarf, belt, pouches, boots, and tail substantially better
than either whole-surface remesher. It is awaiting Ayric's visual decision and
still requires explicit deformation-flow review before the retopology gate can
pass. No texture, rig, or UE claim follows yet. See
`docs/evidence/orange-adventurer-cat-ai-v1-retopology-trials-v1.json`.

Ayric subsequently accepted that presented surface and wireframe, and the
hash-bound production-retopology receipt now passes the workspace audit. A
geometry-locked Smart Project UV derivative moved no source vertices; its OBJ
transport dropped only three of five measured duplicate triangle copies and
otherwise stayed within 0.000000871 m. Hunyuan3D-Paint 2.1 then mapped the
original cat image directly onto that transport. The resulting 19,997-triangle
GLB preserves face order with 0.000000147 m geometry drift and 0.000000053 UV
drift, and supplies BaseColor, metallic, and roughness maps. Four lit views are
awaiting Ayric's texture decision. The fur is paler than the orange authority,
so the mechanical pass is not an artistic pass. See
`docs/evidence/orange-adventurer-cat-ai-v1-texture-trials-v1.json`.

The initial challenger render accidentally overlaid the dense source and low
mesh because the AutoRemesher `.blend` retained both objects. That composite is
explicitly rejected. Review renders must load the exported candidate GLB alone.

Paths below are relative to `${RAC_LEGACY_ROOT}`.

### Original male

- Blender derivative:
  `output/recovery-v2/gallery/face-repair/male-v1/male-eye-repaired.blend`
- Unreal asset:
  `/Game/Pipeline/RecoveryV2/FaceRepair/MaleV1/SK_RecoveryV2_Male_EyeRepairV1`
- UE review image:
  `output/recovery-v2/gallery/face-repair/ue5-ratification/male-face-ue-v1.png`
- Verified import snapshot: 48,456 vertices, 67,907 triangles, 5 material
  sections, 87 bones, maximum 4 influences.

### Ninja

- Blender derivative:
  `output/recovery-v2/gallery/face-repair/ninja-v24/ninja-eye-repaired.blend`
- Unreal asset:
  `/Game/Pipeline/RecoveryV2/FaceRepair/NinjaV24/SK_RecoveryV2_Ninja_EyeRepairV24`
- UE review image:
  `output/recovery-v2/gallery/face-repair/ue5-ratification/ninja-face-ue-v24.png`
- Verified import snapshot: 45,576 vertices, 54,220 triangles, 2 material
  sections, 76 bones, maximum 4 influences.

### Fox

- Blender derivative:
  `output/recovery-v2/gallery/face-repair/fox-v4/fox-eye-repaired.blend`
- Unreal asset:
  `/Game/Pipeline/RecoveryV2/FaceRepair/FoxV4/SK_RecoveryV2_Fox_EyeRepairV4`
- UE review image:
  `output/recovery-v2/gallery/face-repair/ue5-ratification/fox-face-ue-v4.png`
- Verified import snapshot: 46,742 vertices, 69,545 triangles, 5 material
  sections, 27 bones. The accepted derivative has one tail.

### UE project and gallery

- Project: `ue5/ReferenceCharacterPipeline.uproject`
- Gallery map:
  `/Game/Pipeline/RecoveryV2/Gallery/L_RecoveryV2_SevenAssetGallery`
- Installer script: `ue5/Scripts/install_gallery_face_repairs.py`
- Subject render helper: `ue5/Scripts/render_ratification_subject.py`
- Eye-repair authoring script: `scripts/author_runtime_eye_repair.py`

The final face assets were imported and individually rendered. The gallery map
save was blocked by an open-editor file lock, so do not assume the latest face
swaps were persisted into the map. Reopen or duplicate the map safely, install
the verified assets, save, reopen, and prove persistence.

## Highest-value next work

Rewritten 2026-08-31. The previous list asked for a persisted gallery, a
deformation suite, fox deformation and a cooked sample. All four are done and
are recorded in `docs/PRODUCTION-READINESS.md` with the numbers. What follows
is what is actually left.

### Blocking the stated goal: one image in, a finished asset out

1. **A reduction step between the generator and the compiler.** QuadriFlow
   refuses a raw ~1M-triangle generation outright -- whole-mesh and shell by
   shell, 0 quads either way -- so it passes through at full density and fails
   the triangle budget by roughly 50x. The legacy chair pipeline never hit this
   because it reduced 980k to 48k before the compiler saw it. Decimate is not
   the answer; it is a recorded rejection. See `docs/FROM-IMAGE.md`.
   An AutoRemesher adapter and operational preflight now exist, but the first
   raw-chair canary was rejected without retry: 979,546 -> 372,317 triangles,
   31.5% quads, and about 156k boundary/non-manifold edges against a 20k target.
   Keep it as an isolated challenger; it does not close this blocker.
   The legacy lineage has now been corrected: its accepted 48k all-triangle
   outputs came from voxel conditioning followed by the script's collapse-QEM
   fallback, not from QuadriFlow. That operation is explicit and evidence-gated
   at `scripts/run_voxel_qem_reduction.ps1`. A raw longsword canary reduced
   977,341 triangles to 18,000 with zero boundary/non-manifold edges, and fixed
   clay views retain the accepted 48k silhouette. See
   `docs/evidence/reduction-voxel-qem-longsword-v1.json`. This advances the
   blocker to dense-to-runtime UV/texture bake, human modeling approval, and
   UE/cooked proof; it is not production-ready yet.
   The full portable `compile_from_image.py` route has now also reproduced this
   on the normalized 1.30 m longsword authority: reference intake, texture
   extraction, 977,341-triangle FBX authority, 18,000-triangle closed candidate,
   and eight fixed views. It stopped at human modeling approval exactly as the
   contract requires. Compact evidence is in
   `docs/evidence/weathered-longsword-portable-intake-v1.json`. The production
   builder verifies the candidate SHA-256 and now refuses both reduced and
   under-budget authorities unless the workspace ledger binds the exact mesh,
   four neutral fixed views, and an identified human reviewer. `--yes` cannot
   create that approval. After baking, automated cleanup/retopo/unwrap stages
   advance with their hashed reports, but publish pauses again until the exact
   production FBX, baked maps, gate report, and four lit views receive a
   separate hash-bound human texture approval. Publication now advances the
   local collision/static stages only. UE import is bound to the exact consumed
   manifest and extracted from the mutable batch report into per-asset evidence.
   Runtime review requires gallery placement plus a reviewed editor frame; the
   final cook stage separately requires clean cook/package markers, packaged
   executable and content hashes, a packaged run that loaded the gallery, and
   a reviewed in-game frame. Only then can the ledger report production-ready.
2. **The portable rig driver is candidate-only.** `rig_and_skin` now has a
   generic existing-mesh A-pose entrypoint, but a generated humanoid cannot yet
   be finished automatically. Auto-Rig Pro 3.74.40 is operational in Blender
   5.2.1; `scripts/blender/preflight_arp.py` and `workflow_doctor.ps1` prove the
   runtime. The new driver extracts only asset-neutral Smart markers, proxy
   bind, influence limits, geometry preservation, and candidate reporting from
   the field-scout lessons. It still requires a retained-asset canary followed
   by deformation, ARP game export, Manny-profile, FBX, and UE gates. AniGen
   generates a different mesh and rig together, so it
   is a pre-modeling challenger, not a post-approval `rig_and_skin` driver.
   The first retained male canary on 2026-08-31 was rejected without retry:
   body detection and UE5 axial setup ran, but generic-ratio hand placement did
   not resolve the fingers. The driver also exposed a secondary Blender context
   error after that warning; context normalization and durable failure reports
   are now fixed. The next experiment needs explicit reviewed wrist/palm/finger
   landmarks, not another guessed hand ratio.
   The driver now enforces that conclusion: `-HandLandmarks` is mandatory and
   must use `reference-asset-compiler.hand-landmarks.v1`, match the exact source
   mesh SHA-256, contain wrist plus four ordered joints for all five digits on
   both hands, and carry explicit reviewer approval. The retained normalized
   hand-fit report is post-rig donor/anthropometric evidence and is therefore
   not silently converted into this authority.

### Asset defects, still open

3. **field-scout-female's face projection is stamped across her hair.** The
   `_Face` material is a frontal projection covering the fringe and ending in a
   straight horizontal cut. Inherited from the authority, reproduced faithfully,
   and not repairable by the compiler -- the reference never saw the underside of
   that fringe, so there is nothing to recover, only something to invent. This is
   a texture pass. Evidence in `docs/DEFECTS-CLOSEUP-REVIEW.md`.
4. **fox-mascot's ears are faceted** where QuadriFlow met a spiky silhouette, and
   his production atlas carries ~9,000 dilation-filled texels that read as blocky
   patches on his arms. Both predate the eye repair and neither is a hole.
5. **field-scout-female's LODs have never been looked at.** They are built and
   measured; nobody has judged LOD1 or LOD2 at distance by eye.

### Debt carried by explicit waiver

6. **All four characters ship 2x to 3.4x over the 20,000 triangle budget**, each
   with a recorded `budget_waiver`. Retopology to budget is real outstanding
   work, not a formality -- and two of them (male, ninja) cannot be reduced by
   QuadriFlow at all, so it needs a different method.
   The portable V1 cohort now makes 15,000 vertices and 20,000 triangles an
   explicit unwaived release contract for every benchmark member. The female's
   approved 70k source is clean and closed. Two native AutoRemesher trials
   erased visible garment, facial, and hand structure. QuadriFlow's generic
   refusal was traced to 19 sub-0.1 mm edges; after a bounded repair, its mesh
   completed but exceeded the surface-deviation limits. Smooth shading corrected
   the visual record for the feature-QEM challenger, but its all-triangle topology
   still fails the articulated contract. These trials are retained and none is promoted; see
   `docs/evidence/field-scout-female-v4-retopology-trials-v1.json`.
   A pinned Windows-native build of Remi 1.13.1's Instant Meshes field solver
   then passed its own guided-stroke and UV smoke checks. Whole-surface and
   region-aware female trials were rejected for deviation and visible loss of
   hair, pocket, collar, face, and hand detail; one flawed cuff profile also
   removed both lower legs and remains preserved as rejection evidence.
   Uniform field remeshing is retired for this asset.

   A later challenger paired the fidelity-preserving Feature-QEM
   triangles without moving vertices. Blender's greedy pass stopped at 77.60%
   quads, so a bounded augmenting operation converted exactly 150 local
   `1 quad + 2 triangles` neighborhoods into `2 quads`. Attempt 003 now has
   10,002 vertices, 20,000 triangulated faces, 8,889 quads (80.0018%), zero
   boundary/non-manifold edges, p99 deviation 1.58 mm, and maximum deviation
   4.48 mm. Its four fixed views retained the complete AI-derived character,
   but required wireframe review showed stochastic paired-face flow rather than
   reliable rings around shoulders, elbows, hips, knees, wrists, and fingers.
   It is rejected despite its numeric pass. The receipt contract now binds four
   wireframe views as well as four matcaps, preventing another percentage-only
   result from masquerading as deformation-aware topology.

   Thirteen explicit neck and limb rings were then projected onto the exact
   approved AI cleanup surface. Two guide profiles were rejected in fixed views:
   outside-in rays crossed unrelated surfaces, and pelvis-spanning hip bands were
   not local deformation guides. V3 replaced them with local inside-out rings and
   upper-thigh supports and passed its hash-bound visual preflight. Remi still
   could not produce a usable mesh: its first submission rejected the repeated
   terminal point used to display a closed ring; the diagnosed open-path
   representation solved but opened holes during extraction. Both failures are
   retained in `docs/evidence/field-scout-female-v4-joint-guide-trials-v1.json`,
   the guided Remi route is retired, and no third retry is authorized. The next
   challenger must preserve explicit joint loops on the fidelity-safe Feature-QEM
   surface instead of remeshing the whole character again.

   A follow-up tried to preserve closed cycles using only existing Feature-QEM
   edges before triangle pairing. The first constructor produced a branched neck
   graph; the corrected non-overlap constructor proved that no local path connects
   every neck anchor inside the audited band. Both stopped before pairing and
   emitted no mesh. That route is also retired. The next method must insert
   controlled joint-band topology on the accepted AI surface and stitch it into a
   slightly-under-budget fidelity-preserving body; it may not pretend stochastic
   QEM edges are deformation loops.

   That controlled limb-band surgery was then audited and exercised through nine
   immutable challengers. The final contour-lofted candidate remained under the
   unwaived limits at 9,780 vertices, 19,556 triangles, and 81.12% quads, with a
   closed surface and p99 deviation of 2.86 mm. Fixed views still showed visible
   notches where the new bands met sleeves and trousers. The local tube-surgery
   route is therefore retired despite its mechanical pass; see
   `docs/evidence/field-scout-female-v4-limb-band-trials-v1.json`. Resume with a
   deformation-template or garment-aware retopology method constrained to the
   approved AI cleanup surface. Blender remains a downstream cleanup and evidence
   tool here, never a place to reinterpret the reference image into replacement
   geometry.
7. **All four carry a `texture_waiver`** for atlases inherited from the legacy
   back-projection stage, which baked lighting into the albedo.
8. **Per-material metallic and roughness are lost on props.** The chair's
   authority specifies metallic 0.18 on the frame and 0.25 on the rust; the
   shipped ORM derives roughness from albedo luminance and sets metallic to 0.
   Authored scalar channels are now baked per material through the production
   UV layout and packed into ORM. An isolated chair canary preserved all six
   roughness values and both metallic values with 100% reported bake coverage,
   a 1.000 silhouette IoU, and clean fixed views. The legacy character fallback
   remains explicit. This is pending human texture approval and a fresh UE/cook
   rebuild, so the existing shipped chair is not relabeled. See
   `docs/evidence/office-chair-authored-pbr-canary-v1.json`.
9. **Prop collision is a single convex hull**, so nothing fits between the spokes
   of the chair base. Fine for review, wrong for a chair you can push.

### More assets through the route

The portable chair completed texture remediation and native UE5 import on
2026-09-01. Its 4096 atlas is the retained pre-downsample parent of the
Ayric-approved Hunyuan mapping, not a repaint. Uniformly normalizing the frozen
mesh to 1.019 m raised measured density from 27.9 to 427.8 texels/cm2. UE 5.8.2
then verified exact scale, a real textured material, all declared texture
inputs, and three LODs. The persisted gallery and live editor frame are ready
for Ayric's runtime visual decision; that human gate and the subsequent cook
are intentionally still pending.

10. **The sword** should need nothing new -- it is the second static prop and the
    real repeatability test of the prop route.
11. **The guitar is a recorded rejection.** Rebuild it via AI acquisition plus
    explicit structural cleanup before compiling; compiling a rejected mesh only
    produces a tidier rejection. The later source-locked procedural Blender
    reconstruction was also rejected: it visually interpreted the image instead
    of passing the image through an AI geometry/mapping stage. Do not revive it.
    The next candidate must retain the source hash and AI acquisition payload,
    then stop at fixed-view human modeling approval before UV or texture work.
    The retained Pixal3D run has valid AI lineage but fails that visible gate;
    see `docs/evidence/rejection-sunburst-guitar-pixal3d-v1.json`.

### Done, and where the evidence is

- Gallery persisted and rebuilt: `/Game/Compiled/L_RacGallery`, 12 actors.
- Deformation suite: all four characters, `work/<asset>/prod-v2/deform.json`.
- Manny animation drives 87/87 bones on the humanoids, 76/76 ninja, 23/27 fox.
- Cooked and packaged: 546 packages, 0 errors, and a frame captured from inside
  the running build at `work/ue5-evidence/packaged-build-in-game.png`.
- Physics assets and 3 LODs on every asset; UE 5.8.2 reports 0 failed checks
  across all 10 packages.

## Safe resume checklist

```powershell
Set-Location <your clone of this repository>
git status --short --branch
.\scripts\verify.ps1

# Read-only environmental checks before touching the legacy studio.
Get-PSDrive C
Get-Process blender,UnrealEditor,python -ErrorAction SilentlyContinue
nvidia-smi
git -C $env:RAC_LEGACY_ROOT status --short --branch
```

Do not interpret a busy GPU, file lock, or dirty worktree as permission to kill
processes or reset files. Preserve the user's sessions and choose a non-invasive
task or wait.

## Definition of V1 completion

V1 is complete only when the selected benchmark assets have immutable source
authority, accepted fixed-view modeling, accepted topology-locked textures,
profile-correct rigs where applicable, deformation evidence, persisted UE map
placement at consistent scale, and a successful cooked runtime sample. The
same portable ledger must bind every asset back to its image-conditioned AI
geometry or mapping run. The female currently has the only portable character
chain through semantic cleanup; production retopology and texture remain unresolved. The male, ninja, and fox
runtime authorities still lack complete portable derivation chains, while the
chair, sword, and guitar remain unresolved modeling candidates. No asset cohort
is currently ratified as V1 production-ready.

The release claim is now enforced across the complete seven-asset manifest:

```powershell
$env:PYTHONPATH = "src"
py -3.12 -m reference_asset_compiler.cli cohort-audit `
  configs\v1-cohort.json --workspace-root work
```

Exit code `0` means every named workspace independently reports
`production_ready: true`; exit code `1` means the cohort is intact but
incomplete, missing, or invalid. The current checked-in snapshot is
`docs/evidence/v1-cohort-audit-current.json` and truthfully reports 0/7 ready.

## Pending: caped-adventurer-ai-v1 (single-image route, waiting for GPU)

Ayric supplied one reference image (an anime-style woman in a T-pose: brown
hair, white shirt, red jacket and trousers, blue cape, satchel) to prove the
single-image route. Intake is done: `work/caped-adventurer-ai-v1` exists with
the hashed reference, kind humanoid, profile `ue5_manny`. The geometry request
`configs/generation/caped-adventurer-ai-v1-attempt001.json` is in
`single_view` mode and passed preflight (`launch_ready: true`, nothing
launched). The GPU was reserved for other work at the time, so generation was
not started. Next step, when about 12 GB of VRAM is free and Ayric agrees:

```powershell
.\scripts
un_hy3d_geometry.ps1 -Request .\configs\generation\caped-adventurer-ai-v1-attempt001.json
```

then render four clay views of the candidate for modeling approval. Expect the
back of the cape to be inferred from the single view; if it reads wrong, that
is the case for the multiview route with guidance views.

## 2026-09-04: non-Codex single-image operator route

`scripts/crank_from_image.py` is now the user-facing, resumable entrypoint for
people who do not want a coding agent in the loop. It creates a hash-bound
single-view Hunyuan request, launches the pinned Python geometry runner, and
advances deterministic stages until a human modeling, production-retopology,
or texture gate. Static props can continue through Hunyuan3D-Paint packaging
and optional headless UE import. Articulated assets stop after modeling review;
generic deformation-aware retopology, hand landmarks, rig export, and motion
proof remain explicitly unwired.

The current default does not execute ComfyUI. It only inspects a live ComfyUI
queue before direct Hunyuan inference so it will not steal a busy GPU. The old
64-node graph remains preserved as an optional historical route. Installed
direct-geometry plus PBR-paint dependencies measured 39,594,554,524 bytes
(36.875 GiB) on this workstation. The new pinned minimal fetch is 32.285 GiB
for single-view plus paint, or 36.875 GiB with both shape modes. The runners
avoid the unused duplicate shape checkpoints. `scripts/measure_ai_install.ps1`
reproduces the installed measurement and counts duplicate formats rather than
hiding them.

## 2026-09-04 — Sunset workshop intake and CPU preparation

Active request: build the supplied illustrated workshop as a playable UE scene,
keeping tools and furniture separate. See `docs/SUNSET_WORKSHOP.md` for exact
paths and pending gates. Seven reference-conditioned images and five independent
operator requests are prepared. `/Game/SunsetWorkshop/L_WorkshopShell_v002`
contains a saved 104-module architectural study in `work/ue5-validate`; built
with NullRHI, not visually or runtime verified. No new prop meshes exist yet.

GPU inference is blocked by LM Studio's loaded `qwen3.8-27b`. User was asked
whether it may be unloaded; no permission received at this checkpoint. Do not
infer permission from elapsed time. The pending character choice defaults to
the existing Third Person mannequin if no preference is given.

Geometry launcher now runs the repo's hash-pinned runner directly, with studio
venv/upstream unchanged; doctor uses the same route. 75 tests pass and the
guard refuses the occupied GPU before inference. No commits or pushes for this
scene yet. Preserve the unrelated untracked `docs/BLOG_DRAFT.md`.

## 2026-09-04 — Sunset workshop geometry and rendered room checkpoint

The user authorized proceeding after reporting LM Studio broken, and requested
a simple but attractive exterior. A fresh GPU check found no loaded LM model
and 22,218 MiB free; no process was killed. The missing pinned single-view
shape weight downloaded (4,928,151,562 bytes plus 1,604-byte config). All nine
separate image-conditioned Hunyuan3D-2 geometry calls completed successfully.

Workspaces: `work/sunset-{workbench,radio,sofa,wrench,mug,circuit-board,crate,stool,plant}`.
Each has immutable attempt001, normalized FBX, and four clay views. Wrench,
mug, and circuit board also have top/underside/elevated views. See
`work/sunset-workshop/evidence/modeling-review-v003.html` and adjacent JSON
for source/view/mesh hashes. Eight need human modeling decisions. The plant
is explicitly rejected by the agent in that review for torn leaves and floating
fragments; preserve it and repair/replace AI acquisition, never hand-build leaves.
No human approvals or downstream texture/import/cook claims were created.
All nine workspace audits have `ok: true`, `production_ready: false`.

Current architecture-only map: `/Game/SunsetWorkshop/L_WorkshopShell_v004`
in `work/ue5-validate`. 106 independently placed modules, mapped floor and
chalkboard, real window/skylight openings, player start, simple distant panorama.
Actual UE editor screenshots: `work/sunset-workshop/evidence/shell-review-v002/`.
Inspected window/interior/chalkboard images confirm the exposure and UV fixes;
no player movement or cooked runtime was tested. Still an empty-room study.
Earlier maps, failed build and overexposed screenshots are retained. Dedicated
capture editors self-closed; no inference or Blender process remained running.

Pipeline changes include hash-pinned repo geometry runners, optional surface
review cameras, immutable HTML/JSON geometry reviews with explicit rejections,
and dedicated UE scene-build/capture scripts. 82 tests pass. Source image and
derived image prompts/hashes remain in `work/sunset-workshop/art/lineage*.json`.
See `docs/SUNSET_WORKSHOP.md` for next gates. No commit or push for this scene;
preserve unrelated `docs/BLOG_DRAFT.md`. Default playable character remains
the existing Third Person mannequin unless the user chooses otherwise.

## 2026-09-04 — Sunset modeling approved; runtime reductions awaiting review

Ayric replied "yeah broski, these all look great!!" to the explicit request
to approve the eight non-rejected meshes in `modeling-review-v003.html`.
Recorded `modeling_approval=passed`, reviewer `Ayric`, for workbench, radio,
sofa, wrench, mug, circuit-board, crate, and stool. The plant is excluded and
its damaged original is retained. Rehashed every file in the original review
before finishing this checkpoint; all still match.

All eight passed semantic cleanup and now have separate voxel/QEM candidates:
`work/sunset-<name>/retopology/operator-attempt001/voxel-qem-candidate.glb`
with native `.blend`, reduction report, log, and four fixed views. Each is
18,000 triangles, 8,988–9,002 vertices, zero boundary/non-manifold edges.
Wrench, mug, and circuit-board have supplemental `surface-views` too.
The next user decision is **production topology**, not original modeling.
No topology approval, paint, texture approval, or new UE import was recorded.

Review: `work/sunset-workshop/evidence/retopology-review-v001.html` and JSON.
It pairs approved and reduced views and binds mesh/report/image hashes.
Audit snapshots: `audit-<name>-post-modeling-v001.json` in the same evidence
directory. All eight report integrity OK and production readiness false.
After explicit topology approval, resume each original operator command using
the existing recipe height/reason and `--approve-retopology-by Ayric`; stop
at texture review. Supply `--studio-root C:/Comfy/blender-reference-studio`.

Repaired an observed operator bug: successful cleanup emits `.blend`, but
`describe_mesh.py` only imported interchange formats. Added native read;
resumed after diagnosis without rerunning or changing cleanup. Also corrected
passthrough vertex lookup from `vertices` to the producer's `verts` field.
84 tests pass; doctor passes with the studio root supplied. No GPU inference
was needed this turn. UE remains the prior architecture-only v004 map.
All batch/render processes finished. No commit/push; preserve BLOG_DRAFT.md.

## 2026-09-04 — Sunset topology approved; six texture candidates ready

Ayric approved `retopology-review-v001.html` with "approved. lets go".
All eight `production_retopology` stages now record that human approval.
Eight first Hunyuan3D-2.1 paint runs produced validated outputs, followed by
the known `-1073741819` teardown exit. No inference was retried. Preserve
`texture/operator-hy3d21-attempt001/` outputs, diagnostics and logs. The
launcher now records immutable execution receipts separately from validation.

Next review: `work/sunset-workshop/evidence/texture-review-v001.html` plus
JSON hashes. Radio, wrench, mug, circuit-board and stool `prod-v2`, and crate
`prod-v3`, passed mechanical texture checks and need Ayric's texture approval.
Workbench `prod-v2` is agent-rejected for smeared cavity paint/low density.
Sofa `prod-v3` is held for baked lighting (+0.619 versus 0.35 limit). Both
failures are visible in the review. Plant remains rejected at geometry.
No human texture approvals, imports or cooked-runtime claims were made.

Crate and sofa `texture/fullsize-recovery-v001/` recover original 4096 bakes
from retained diagnostics, not a rerun or upscale. Downsample correspondence
and source/output hashes are checked. Both original failed `prod-v2` exports
remain. Crate `prod-v3` passes at 291.4 texels/cm2; sofa's density passes at
151.5 but its baked lighting still fails. See `docs/SUNSET_WORKSHOP.md` for
the complete table, failure reasons and resume flags. For crate retain
`--texture-package-name prod-v3 --paint-map-directory
work/sunset-crate/texture/fullsize-recovery-v001` on operator resumes.
Workbench retains failed UV attempt001 and uses `--uv-attempt 2`.

The UV tool now supports opted-in static triangulated GLB acquisition with
geometry/UV drift checks. Pipeline tests pass 97; all eight fresh audits
(`audit-sunset-<name>-post-texture-v001.json`) pass integrity and correctly
report production readiness false. All generation/render processes finished;
MCP services and unrelated files remain untouched. No commit/push.
UE remains architecture-only `/Game/SunsetWorkshop/L_WorkshopShell_v004`.
Next gates: human texture review for the six eligible candidates, repair the
two held paints, then static validation/import, furnished scene assembly,
player walkthrough and cooked runtime. Check imported vertex counts because
UV splitting increases interchange vertices beyond the native reduction count.

## 2026-09-04 — Interior repair candidates and five UE imports

Ayric approved all other textures while excluding the bench interior and mug
bottom. Recorded exact reviewed texture approvals for radio, wrench, circuit
board, crate and stool, then published separate `out/*-production` derivatives
and scoped UE imports. No legacy package was reimported. Report:
`work/sunset-workshop/evidence/ue-import-approved-five-v002.json`; five pass
material/scale/LOD import checks. First launch failed on relative project path
before import; its v001 log remains. No new AI inference or process killing.

Separate native vertex audit `ue-vertex-audit-v001.json` found board LOD0 at
15,973 vertices versus 15,000 allowed. **Board runtime review is blocked** in
its ledger; appearance remains approved. Radio 13,239, wrench 10,748, crate
12,402, stool 12,840 pass that count. Do not infer budget verification from
the ordinary import report: that verifier does not measure static vertices.

Workbench and mug `prod-interior-v002` are new texture candidates only.
`scripts/repair_workshop_interiors.py` transports reference material samples
onto existing interior faces, preserves geometry/UVs and verifies unchanged
outside-mask texels. Inputs are recovered 4K bench maps and original 2K mug
maps. Reports/masks/maps: each `texture/interior-repair-v002/`. Both texture
checks pass; bench unwrap/bake is now passed, human texture approval pending.
Mug bottom exists; its old black/streaked interior was albedo, not a hole.
v001 attempts are retained/rejected: wrong bench sample included trim; hard
mug selection created a jagged lip. v002 uses green-only sample and spatial
rim blend. No whole-asset repaint, geometry replacement or AI crash retry.

Next user review: `work/sunset-workshop/evidence/interior-repair-review-v002.html`
and JSON; retained rejections in `interior-repair-rejected-v001.html`/JSON.
Sofa appearance was approved but +0.619 baked-light failure remains held,
not waived. Plant remains rejected geometry. See `docs/SUNSET_WORKSHOP.md`.
The operator's `--paint-map-directory` only accepts full-size recovery
receipts, NOT these new region-transfer candidates. Approve the exact
`prod-interior-v002` via texture evidence/ledger utilities after user review;
do not fake a recovery receipt or resume the default prod-v2 command.

Full verification: 102 tests pass; hash/stage audits pass and production
readiness remains false. Scripts now export per-triangle positions alongside
UV-region data for bounded material transfer. Five regression tests cover
selection exclusions, barycentric sampling, unknown assets and continuity.
Scene remains architecture-only v004; furnishing/player walkthrough/cook
still pending. No commit/push; preserve BLOG_DRAFT.md and prior authorities.

## 2026-09-04 — Interior approvals and first furnished playable preview

Latest user approval accepted both `prod-interior-v002` textures. Exact review
files were rehashed before ledger approval. Published workbench/mug production
derivatives and passed scoped imports in `ue-import-interiors-v001.json`.
The five previous texture approvals remain; sofa's mechanical hold is not waived.

Current saved map: `/Game/SunsetWorkshop/L_WorkshopPreview_v003`, project
`work/ue5-validate/RacValidate.uproject`. Original shell v004 and preview v002
are retained. New builder `scripts/ue5/furnish_workshop_preview.py` checks
texture approval, UE import and <=15,000 native LOD0 vertices before placing
18 independent actors from six types (bench, mug, radio, wrench, crate, stool).
Do not rerun against the existing target: choose a fresh revision. Scene
receipt `work/sunset-workshop/evidence/L_WorkshopPreview_v003.json` records
placements and source manifest hashes, not a production release approval.

Dedicated PIE probe `scripts/ue5/probe_workshop_walkthrough.py` passed all six
checks in `evidence/walkthrough-v002/walkthrough.json`: possessed Manny template
character, floor spawn, ~4.9 m actual gameplay-input movement, blocking collision
and floor retention. The collider itself was not identified, so the report's
`blocked_by_wall` name means blocking geometry, not a proven wall-actor hit.
Actual UE `overview.png` and PIE `player-window.png` are beside the report.
No physical keyboard automation or cooked build was tested. v001 probe remains.

The v003 presentation fixes turn radios inward, reduce task lights/exposure,
and enlarge/reposition the desert card. Still an early sparse preview: soft
flat backdrop, repetitive shell, missing sofa/foliage/dressing. Next work is
the sofa baked-light repair, reviewed board budget derivative, and a fresh
image-conditioned plant candidate; do not waive their existing holds. Then
more scene art/collision review and cooked verification. No new inference
was run. 102 tests pass and both new UE scripts byte-compile.

`scripts/play_workshop_preview.ps1` opens this local map in a visible uncooked
editor `-game` window without changing project defaults. Preserve that user
window and do not mutate its project concurrently. Check processes first.
No commit/push; unrelated BLOG_DRAFT.md and legacy authorities untouched.

## 2026-09-04 — Full demo continuation, character and separate sword

Read `docs/SUNSET_DEMO_COMPLETION.md`: the active user goal is the entire
polished demo, not completion of the early v003 preview. User expressly
delegated visual judgment without further input. New scoped authorization
and review receipts record `approved_by=codex`, `human_visual_review=false`,
exact source/stage/evidence hashes; they do not waive mechanical gates.
Default human-only behavior remains when no explicit delegation is supplied.
109 tests passed, including seven delegation tests. No commit/push.

ImageGen produced cel-shaded reference derivatives directly from the supplied
Ayric image, plus a separate sword. Exact prompts, original paths and hashes:
`work/sunset-workshop/character-art/lineage-v001.json`. Geometry acquisition
used the direct image-conditioned Hunyuan single-view runner; Blender is only
downstream. `sunset-ayric-v1` is rejected for fused fingers. Edited reference
v002 produces five separated digits per hand in `sunset-ayric-v2`, whose
modeling and semantic cleanup are passed. Never resurrect v1 as the live asset.

Character retopology `autoremesher-v001` and `projected-v001` lost nose/brow
detail and are retained, rejected by close-up review. Front-head subdivision
of existing quads followed by bounded projection onto the AI cleanup authority
produced `retopology/projected-v002/projected.blend`. It retains 9,790 vertices,
19,588 triangles, 97.4% quads, zero boundary/nonmanifold edges. Four clay and
four native wireframe views plus face closeups were reviewed; topology passed
under explicit delegation. This is not facial-animation or deformation proof.
The isolated native mesh is the approved UV source, not display GLB.

`scripts/blender/refine_retopology_region.py` adds samples only; the separate
projection stage snaps them to source geometry. First launcher failed on a
missing local module path before any asset write, corrected in the script.
One render similarly refused relative paths before writing; use absolute paths.
Neither was an inference crash. UV transport at `texture/uv-v001` passes with
zero native geometry change and 0.000000870 m OBJ roundtrip delta. A single
HunyuanPaint 6-view/512 candidate was launched at `texture/hy3d21-v001` after
22,343 MiB free VRAM and process checks. Inspect its final result before any
resume; never blindly rerun. Next character gate is texture, then rig/export,
actual deformation and UE gameplay with the sword attached to the back.

Sword `sunset-sword-v1` passed modeling, static topology, UV, texture and static
publish checks. `prod-v2` has four inspected lit and four unlit views, coherent
cobalt/cyan blade and dark grip, passing unwaived texture gate. Published
`out/sunset-sword-v1-production`; UE import remains pending. HunyuanPaint
returned the known teardown access violation after valid topology-locked
outputs; retained `painted.execution.json`, no retry. The first sword modeling
review receipt bound raw GLB instead of normalized FBX and promotion correctly
refused it; retained v001 receipt, accepted v002 binds exact normalized FBX.

Workshop itself remains v003. Sofa lighting hold, board vertex-budget hold,
plant rejection, scene polish, custom playable character, cooked evidence and
the final browsable panel remain unfinished. Keep the full goal active.

### Character texture result at end of this continuation

The single paint run completed with geometry delta 0.000000149 m and UV delta
0.000000053; it returned the known post-output teardown access violation
(-1073741819). Outputs and execution receipt remain. No automatic retry.
`work/sunset-ayric-v2/prod-v1` is **rejected**, not approved: 2048 atlas density
50.0 versus 200 required, directional-light correlation about -0.25 versus
absolute 0.12 allowed. Four lit/four unlit views show side-panel discontinuities,
speckled tabard and excessive gloss. Dedicated face front/three-quarter/side
albedo evidence also exposes style/identity drift and triangular black neck
seams. Closeups are in `prod-v1/face-review-v001`, rendered by the new CPU-only
`scripts/blender/review_character_texture_closeups.py`. Do not rig this paint.

Full-size maps were recovered without rerun or upscale into
`texture/fullsize-v001`. Correspondence passes; its diagnostic still fails:
199.8 texels/cm2, -0.243850589 light correlation, 317-island fragmentation
warning. Merely increasing resolution did not repair correspondence or light.
Raw painted OBJ was rendered in `texture/hy3d21-v001/transport-review` and
has the same side artifacts as FBX: this is not solely a packaging defect.
`unwrap_and_bake` rejection binds the exact failed maps/reports/views; topology
remains accepted. Next is a bounded texture/UV/material repair, not another
identical paint invocation, a profile waiver, or a late jump to rigging.

Delegation validation now rejects malformed or duplicated artifact rows and
string-valued stage scopes, with ten focused tests. Both new character jobs
and sword pass workspace integrity audits; readiness is still false.

Final verification for this checkpoint: 112 tests pass, Blender scripts
byte-compile, `git diff --check` passes (line-ending notices only). No UE,
Blender render or Hunyuan inference process remains; 22,342 MiB VRAM and about
331 GiB disk were free. Existing MCP/LM Studio/UI processes were preserved.
Verify ownership again before the next run. Goal remains active and unfinished.

### 2026-09-04: user requests face-only repair, preserve everything else

User: "Man, face texture isn't great, definitely needs work. Everything else
is great though." Preserve the rest of the design. The full-demo completion
goal remains active; this feedback does not waive mechanical gates.

Built-in ImageGen acquired one illustrated facial donor conditioned on the
actual clay closeup plus approved Ayric front reference. Exact prompt, paths
and output hash: `work/sunset-workshop/character-art/face-donor-lineage-v001.json`.
`ayric-face-donor-v001.png` is a donor, NOT an actual 3D render or new mesh.
It shifted features, so direct projection was refused. Downstream piecewise
affine camera-landmark registration maps only front-visible facial surfaces.
No geometry/UV change, local inference, armor/hair repaint or new material
channel. CPU correspondence: `texture/face-correspondence-v001` under Ayric v2.

New scripts: `scripts/blender/export_face_projection.py` and
`scripts/map_face_donor.py`. Immutable configs `texture/face-registration-v001`
through `v003.json`; derivative atlases in `texture/face-transfer-v001` through
`v003`. v001 is rejected for visible UV seams and overly V-shaped smile.
v002 fills only unused UV gutters (never other occupied islands), removing
the fine seams; smile still rejected. v003 registers lip corners and center
explicitly, giving a relaxed closed-mouth smile. Front/three-quarter/side lit
and albedo views inspected: **preferred face repair**, not a texture approval.

Exact current candidate: `work/sunset-ayric-v2/prod-face-v003`, actual 1.85 m
19,588-triangle FBX and 4K maps. `texture/face-transfer-v003/BaseColor.png` SHA256
`e58f89c0eca716ba83687e87b59f0b2b32978c3d2371e3bc0608b17ac04e89fb`.
63,112 facial texels plus 23,395 unused gutter texels selected; all other atlas
pixels bit-identical, zero protected-surface overlap. Roughness/metallic are
unchanged recovered maps. Face closeups: `prod-face-v003/face-review-v001`.
Panels and hash manifests: `work/sunset-workshop/evidence/ayric-face-review-v001`
through `v003.html`/`.json`. Review builder now includes all six facial frames
when present and refuses partial face evidence.

**Still rejected at unwrap_and_bake:** light correlation -0.2397395 (limit .12),
density 199.8 (floor 200), 317-island warning. Preserved original neck/side
defects and forehead/hair lighting band are still visible; do not mistake
face improvement for whole-character production readiness. Next: resolve
UV/material/lighting holds while preserving this face and the user-liked
artwork, then rig/deformation, UE sword attachment, scene polish and cook.
No rigging, UE import, scene edits or cook occurred in this face-repair pass.

119 tests pass, including five registration/gutter tests and two face-panel
completeness/hash tests. Early packaging invocations refused missing pending
CPU transfer output before creating a package; later runs used completed
inputs. These were not inference crashes. No automatic inference retry.

### 2026-09-04: density repaired without changing the face or body design

Previous goal turn was progress (bounded facial mapping). This continuation
repacks existing islands and transfers all three PBR maps, rather than scaling
the character or resizing the image. `scripts/blender/repack_texture_payload.py`
reads the native UV authority and a hash-pinned config, uses concave packing
with 0.002 fractional margin, and CPU emission-bakes at the same 4096 size.
It fingerprints every vertex and polygon before, after, and after reopening.
No reshaping, new artwork, inference, rigging or engine edits occurred.

Exact new derivative: `work/sunset-ayric-v2/texture/repacked-v003`;
config `texture/repack-config-v001.json`. Native SHA256
`4a55bace21f8872e9fb40023597d33859cb2589686040355bc3ba150ab3dfa8b`.
Triangle-based UV occupancy improved 0.373508 to 0.563267. Initial attempts
left the selected UVs unchanged; retained rejection records in `repacked-v001`
and `repacked-diagnostic-v002`. Explicit UV selection synchronization and
reacquiring the UV layer after edit mode fixed it; no bake was attempted on
the rejected no-op. The successful derivative retains 9,790 native vertices.

Packaged candidate: `work/sunset-ayric-v2/prod-repacked-v001`. At unchanged
1.85 m and 19,588 triangles, **density now passes at 301.3 texels/cm2**.
This recovers useful atlas space; it does not generate extra source detail.
`texture/repacked-v003/surface-comparison.json` checks four corresponding
points on every triangle: zero position delta; mean absolute 8-bit errors
BaseColor 0.261, Metallic 0.303, Roughness 0.202. Face-front lit plus body
three-quarter/back albedo inspected and retain the preferred v003 face and
user-liked artwork. Six closeups and all fixed views are saved for review.
No whole-texture visual approval was granted. Panel and exact payload hashes:
`work/sunset-workshop/evidence/ayric-repacked-review-v001.html` / `.json`.

**Remaining hard texture failure:** baked-light correlation -0.24185996 vs
absolute .12. Fragmentation remains a warning (272 raster components, not a
topological island count). Original side/neck artifacts remain. Do not rig
or treat this as the completed demo. The unwrap_and_bake ledger remains
rejected and binds the improved candidate and diagnostics.

Read-only `scripts/diagnose_texture_sampling.py` proved a limitation in the
old gate's rectangle sampler, but not an explanation for the failure:
`texture/sampling-diagnostic-v001.json` measures -0.23974 with rectangle
sampling and -0.22911 strictly inside triangles. **Gate and profile unchanged.**
Do not use this small difference as a waiver or tune artwork to the metric.
Next is a bounded actual delight/material repair while protecting the current
face/artwork, then rig/deformation and the full UE scene/runtime contract.
The official Hunyuan3D-2 Light_Shadow_Remover and its cached v2 checkpoint were
located read-only (cache revision 9cd649ba6913f7a852e3286bad86bfa9a2d83dcf),
but no load or inference was attempted. It operates on 512px images, not a
topology-aware atlas; do not feed the whole UV atlas to it blindly.

Preflight/doctor passed; original MCP and LM Studio UI were preserved. Final
verification: 122 tests, scoped ruff and compile checks pass. Full goal remains
active, not blocked or complete. Workshop remains the early v003 preview.

### 2026-09-04: official delight rejected; separate board budget candidate

The installed official Hunyuan3D-2 `Light_Shadow_Remover` was tested once on
one retained painter view, then on the remaining five after inspecting the
probe. Cached checkpoint revision: `9cd649ba6913f7a852e3286bad86bfa9a2d83dcf`,
`hunyuan3d-delight-v2-0`, 512 px, 50 steps, seed 42. The new
`scripts/run_hy3d_delight_probe.py` records upstream/checkpoint/input hashes,
requires free VRAM and a fresh output directory, and never retries. GPU
ownership was inspected first; measured peak allocation was 3,259,735,040
bytes. Both runs succeeded. No ComfyUI or LM Studio inference was used.

Ayric v2 configs: `texture/delight-probe-config-v001.json`,
`texture/delight-views-config-v001.json`, `texture/delight-bake-config-v001.json`,
and `texture/repack-delighted-config-v001.json`. Corresponding outputs are
`delight-probe-v001`, `delight-views-v001`, `delighted-bake-v001`, and
`repacked-delighted-v001` under `texture/`. Renderer-only backprojection in
`scripts/rebake_delighted_views.py` reproduced all six original camera normal
controls exactly (mean error zero). It transfers smoothed linear-luminance
gain to the original high-resolution views, preserves the repaired facial
texels/gutters and unseen surfaces, and does not change mesh/UV arrays.
The optional inpaint-import warning did not affect this no-inpainting route.

**Reject `prod-delighted-v001`.** Density remains passing at 301.3, but light
correlation is -0.21428409 (limit absolute .12), and inspected actual 3D views
show a worse dark forehead transition next to the protected face. Exact face
pixel preservation did not preserve the appearance of its changed neighbors.
Immutable rejection panel/manifest:
`work/sunset-workshop/evidence/ayric-delight-review-v001.html` / `.json`.
The previous `prod-repacked-v001` remains preferred and the ledger remains
rejected against that candidate. Do not rig or promote the newest bake.
`gate_texture.py` changes only an inaccurate diagnostic sentence claiming a
delight pass was skipped; all measurements, profiles and thresholds are
unchanged. Four transport tests bring the passing full suite to 126.

Independent circuit-board check: importing the same approved FBX with lightmap
UV generation disabled did not change LOD0 (15,973). Retained report:
`work/sunset-workshop/evidence/board-dynamic-import-v001.json`. A separate UE
duplicate `/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v001` using native
LOD fractions .85/.5/.25 has **14,534 / 8,425 / 4,798 vertices**, meeting the
unchanged 15,000 cap. Report: `evidence/board-reduced-v001.json`. Original mesh,
FBX and textures are preserved. The initial relative-project command refused
to open the project; the corrected absolute-project invocation succeeded.

Actual UE comparison fixture `/Game/SunsetWorkshop/L_BoardReview_v001` is NOT
the shipping scene. Both `comparison.png` and `grazing.png` under
`evidence/board-reduction-review-v001/` were inspected; `review.json` hashes
both screenshots and records native counts. The reduced board retains its
green/gold paint and raised components at these views, but the original is
partially occluded by a wrench. Thus visual acceptance remains provisional.
The dedicated review editor self-exited; existing creative processes were
preserved. No original preview level was edited.

Next board work: unobstructed matched-view comparison and a versioned native
import/runtime receipt before placement. Existing `record_ue5_import_stage`
uses a fixed immutable receipt path and cannot simply overwrite the accepted
original import to bless this derivative. Original runtime hold remains.
Next character work: repair the local face/neck lighting transition with
geometry-aware transport rather than repeating whole-body de-lighting. Full
demo still needs character texture/rig/deformation, sword attachment, remaining
props, scene polish and cooked-runtime proof. Full verification: 126 tests,
scoped ruff and diff checks pass; no mechanical waiver or production claim.

### 2026-09-04: forehead registration and skin PBR improve the preferred face

Previous turn was progress (retained delight rejection and native UE board
evidence). This turn returned to the user's face complaint. No AI inference,
new geometry, rigging or UE edits. GPU/process/disk preflight preserved existing
services. The reference-to-3D skill was inspected but its contour-reconstruction
route conflicts with this repo's boundary; only existing downstream mapping
and CPU Blender evidence were used.

The old face region ended halfway down the forehead, leaving original paint
above it. `texture/face-registration-v004.json` extended the existing donor to
the actual visible hairline but stretched brow tails: rejected. v005 retained
the preferred v003 face beneath a forehead-only region but picked up partial
donor eyebrow ghosts: rejected. v006 adds explicit donor-skin correspondence
along the lower forehead boundary. It removes the band without moving the
preferred eyes/brows/nose/mouth. This is camera-landmark texture registration,
not facial reshaping or new artwork. All three output folders are retained as
`texture/face-transfer-v004` through `v006`, with actual six-view closeups.
`texture/forehead-rejections-v001.json` hashes rejected payloads and frames.

v006 changes 28,787 forehead texels plus 8,439 unused gutter texels relative to
v003, with zero protected-surface overlap; every other atlas pixel is identical.
BaseColor SHA256: `d6f02bad77e6a9054a790dd570a473439ab9d49d02f977f34fc5f1234766b613`.
The same geometry-bound face/forehead mask union exposes inappropriate original
skin gloss and metallic values. New `scripts/calibrate_pbr_region.py` applies
a .65 roughness floor and zero metallic ceiling within that exact support,
preserving all BaseColor bytes and scalar texels outside it. No mask resizing
or unbounded dilation. Config `texture/skin-pbr-config-v001.json`; output
`texture/skin-pbr-v001`. 54,290 roughness and 68,437 metallic texels changed,
82,441 support texels. Three tests cover scope, shape and value-bound failures.
Skin front/three-quarter lit and side albedo were inspected; skin glare is
softer. Armor gloss and original neck/side mapping defects are not fixed.

**New preferred held package: `work/sunset-ayric-v2/prod-face-v006`.** Repack
config `texture/repack-face-v006-config-v001.json`, native output
`texture/repacked-face-v006/uv-authority.blend`, SHA256
`618a1ee743ae260a29d5bee46239022430349382fda31fcbf657015f85f72656`.
Existing island occupancy again .373508 -> .563267; unchanged native geometry
verified after reopen. Packaged 1.85 m, 19,588 triangles, 4096 maps, density
301.3. Actual packaged face-front albedo, three-quarter lit, body-back albedo
inspected; all 12 body frames and six facial closeups retained.

Lighting still fails at **-0.2388973783 vs absolute .12**; fragmentation 272
remains advisory. No waiver. `unwrap_and_bake` remains rejected, now bound to
v006 evidence. Previous full ledger is retained in
`texture/ledger-before-face-v006.json`. Audit passes integrity, not readiness.
Panel/manifest: `work/sunset-workshop/evidence/ayric-face-review-v006.html` /
`.json`. Review builder no longer attributes every historical approval to Ayric
when some are explicitly delegated. It grants no approval itself.

Next: geometry-aware neck/side mapping repair and the independent lighting
hold, then rig/deformation, UE back sword and complete workshop/cooked runtime.
Do not repeat the rejected broad delight or forehead/brow variants. Full suite
129 tests and scoped ruff pass; the entire demo goal remains active.

### 2026-09-04: bilateral neck donor and pixel-depth projection

Previous turn was progress (preferred forehead/skin repair). This turn acquired
one built-in ImageGen donor conditioned directly on the actual v006 unlit
three-quarter mesh closeup. Imagegen skill used; no local GPU inference or
fallback CLI. Saved project donor:
`work/sunset-workshop/character-art/ayric-neck-donor-v001.png`, SHA256
`23d02cba109582cb171a25087369fd18eb3907a9fab22633c151373f0ee94c9d`.
Exact prompt/input/output/tool provenance: `neck-donor-lineage-v001.json` beside
it. The donor repairs skin-to-inner-collar paint but changes surrounding pixels;
it is NOT a 3D render. Only bounded neck/collar pixels are transported.

`export_face_projection.py` now accepts angle and bounded head/neck selection,
preserving its old defaults. `--visibility pixel` additionally exports camera
depth and a NumPy rasterized frontmost depth buffer. `projection_visibility.py`
implements perspective-correct surface projection and reciprocal-depth
rasterization. `map_face_donor.py` uses those arrays when present, retaining
the old midpoint route otherwise. It loads the compressed arrays once, not
per triangle. Normal fade can be disabled only when pixel-depth data exists;
this matters for visible concave folds whose smoothed vertex normals point
away from the camera. Occluded fragments remain excluded. This does not
change any texture-acceptance threshold.

The initial Blender export failed before output because importing the old
triangle helper also imported Pillow, unavailable in bundled Blender Python.
Extracted the identical NumPy-only helper into `scripts/raster_geometry.py`,
re-exported by the old module for compatibility. Corrected export then passed;
not an inference crash/retry. Four synthetic tests prove perspective, near/far
occlusion and empty-depth behavior. No new dependency installation.

Retained configs `texture/neck-registration-v001` through `v004.json` and
outputs `texture/neck-transfer-v001` through `v004`. v001/v002 are rejected for
incomplete fold coverage and opposite-side paint; hashes in
`texture/neck-rejections-v001.json`. v003 uses pixel visibility without normal
fade on the camera-facing neck, selecting 20,552 texels. Its support-mask render
is retained in `support-closeups/`. v004 transports the same plain skin/lining
donor through a reflected camera registration using the actual opposite-side
depth buffer, selecting another 22,624 texels. The symmetry is inferred color
mapping, NOT mirrored/new geometry or facial restyling. Each transfer verifies
zero protected overlap and bit-identical pixels outside support plus gutters.

Depth authorities: `texture/neck-correspondence-v002/correspondence.npz` SHA
`9a522d16b9bb4c8369010ddce906d7548747475ee4118bb6432783bc7393977d`,
and `texture/neck-opposite-correspondence-v001/correspondence.npz` SHA
`aeb5bd5bb86c0050b48dc805ce4c522cf80f5790effbcdc2e63195f49d2c2f05`.
Final pre-package BaseColor SHA
`f7baf0eb6f2be0965a5eaac7d60162c48812470aa7408a34d597f3ca1fc3797f`.
`texture/neck-pbr-config-v001.json` / `neck-pbr-v001` calibrate only skin/inner
lining support (40,751 texels) to roughness floor .65 and metallic ceiling 0;
22,456 roughness and 32,813 metallic texels changed, color bytes preserved.

**Preferred held package: `work/sunset-ayric-v2/prod-neck-v001`.** Same native
UV authority as face v006, no additional repack or mesh edits. 1.85 m,
19,588 triangles, 4096 maps, density 301.3. Front and opposite-three-quarter
albedo plus regular three-quarter lit inspected after packaging. The broken
neck paint is improved bilaterally, but collar rim/nape artifacts and earlier
body-side issues remain visible. Lighting **-0.2401985624 still fails .12**;
fragmentation 272 remains advisory. Do not claim a complete neck or texture
approval, rigging readiness, or finished demo.

`review_character_texture_closeups.py --opposite` captures both sides (10
lit/albedo frames). The panel builder includes all four optional opposite
frames atomically and refuses incomplete sets; two tests cover this. Panel:
`work/sunset-workshop/evidence/ayric-neck-review-v001.html` / `.json`.
`unwrap_and_bake` remains rejected, now hash-bound to the preferred neck
candidate, donor and receipts. Prior ledger retained at
`texture/ledger-before-neck-v001.json`; integrity audit passes, readiness false.

Verification: 135 tests and scoped ruff pass. Original UE preview, sword and
board state unchanged. Next resolve remaining collar/nape/body mapping and
diagnose the independent lighting hold causally before another broad paint
attempt; never tune artwork to the score. Full rig/deformation, sword attachment,
workshop polish and cooked-runtime contract remain outstanding.

### 2026-09-04 — lighting falsification and matched native board review

Added read-only `scripts/diagnose_lighting_confound.py` and three synthetic
tests. `work/sunset-ayric-v2/texture/lighting-confound-v001.json` binds the
actual atlas and UV-region hashes. A six-face multicolored, unlit cube scores
+0.983934698 under the existing lighting heuristic; the single-material
Lambertian positive control scores 1.0. This proves a palette confound, NOT
that Ayric is free of baked lighting. Real correlation remains -0.2401985624.
Fixed 0.1 linear-RGB chromaticity partitions attribute approximately 62% of
covariance within groups and 38% between groups. Similar chromaticity is not a
ground-truth material label. No atlas, threshold, profile or ledger changed;
the character texture hold remains in force on `prod-neck-v001`.

`scripts/ue5/review_board_matched.py` produced four real 1920x1080 UE5.8.2
screenshots in `work/sunset-workshop/evidence/board-matched-review-v001/`.
The copied fixture `/Game/SunsetWorkshop/L_BoardMatchedReview_v001` removes
occluding mugs/wrenches only in that copy, swaps both meshes at the identical
position, and forces LOD0. Original 15,973 vertices versus reduced 14,534.
`review.json` records frames/hashes/cameras/native counts with error=null;
`visual-assessment.json` records delegated agent inspection, not human review.
Both high and grazing pairs preserve the board silhouette, chips, ports and
traces at the inspected scale. Original scene and import receipt preserved.
Dedicated UE PID 20320 completed and exited; the requested `-log` path did not
materialize, so evidence is the completed receipt and actual screenshots.

The board's original runtime hold is NOT silently cleared: a versioned native
derivative/import binding is still needed. Existing `runtime_evidence.py`
uses an immutable `validation/ue5-import.json`; preserve it. Import verifier
currently lacks native static vertex-budget checking, and its static branch
returns before generic texture-setting checks. Address these narrowly before
promoting the replacement, without weakening the original checks.

Verification: Python 3.12 `-m pytest`: 138 tests plus 3 subtests pass; scoped
ruff passes. The guessed local `.venv` does not exist, and bare `pytest`
failed import collection because it omitted the repo root; explicit installed
Python `-m pytest` is the working invocation. No GPU inference ran this turn.
Full demo still outstanding; no goal completion or production-ready claim.

### 2026-09-04 — board native import and visual hold resolved

Previous goal turn classified as progress: the matched comparison and lighting
falsification changed the next actions. This pass addressed the board's exact
native import binding, retaining the character hold without changing its art.

`import_and_verify.verify` now accepts an explicit mesh and intake budgets,
counts built static vertices/triangles/sections across every LOD, fails missing
measurements, and reaches the texture-settings check for static props. Four
engine-double tests exercise the real verifier. Its new main guard permits a
read-only dedicated verifier without importing all published assets.

`board-native-verify-v001.json` caught an additional failure: reduced v001
bounds measured 6.535814 cm versus the declared 6 cm, outside the unchanged 8%
scale tolerance. No bounds extensions were present. Retained v001, then
`normalize_board_runtime_candidate.py` duplicated it to
`/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v002` and applied uniform native
build scale 0.9180187407580992. Recorded height 6.000000477 cm. All old meshes
and maps were preserved. This restores a declared physical dimension, not a
vertex-budget workaround. The modest footprint change was separately reviewed.

`board-native-verify-v002.json` now passes all eight native checks: LOD vertex
counts 14,534 / 8,425 / 4,798, triangles 15,300 / 7,650 / 3,824, one section
each, 6 cm height, unchanged material interfaces, correct texture settings.
All reports and dedicated `-abslog` logs reside in
`work/sunset-workshop/evidence/`. `RAC_BOARD_VERSION=v002` selects the retained
candidate in `verify_board_derivative.py` and `review_board_matched.py`.

New `native_revision.py` and `record_native_import_revision` validate the
same-manifest source import, bound native files, reduction/normalization chain,
native checks and intake budgets. CLI `record_ue5_import.py` now accepts
`--native-revision`. Board import was recorded at
`work/sunset-circuit-board/validation/ue5-import-board-native-v002.json`;
`ledger-before-board-native-v002.json` retains the complete previous ledger,
and original `ue5-import.json` is unchanged. At that point runtime remained
blocked; only the separate next review advanced it.

Four actual v002 UE images in `board-matched-review-v002/` were inspected.
Chips, ports, capacitors, mounting holes, green outline and gold traces retain
the approved design in high and grazing pairs. The smaller normalized footprint
is acceptable for the art-directed prop. `record_runtime_review_stage` now
accepts explicit scoped authorization and requires exact native import/frame
bindings for this route. Recorded authorization, delegated review and runtime
receipt under `work/sunset-circuit-board/`; reviewer=codex,
human_visual_review=false. Current board ledger passes through
`ue5_runtime_review`, cook still pending. Seven additional revision/runtime tests
cover stale files, dishonest counts, wrong chains, downstream guards, delegated
review and unmatched cameras. Total 149 tests plus 3 subtests pass; scoped ruff
and diff whitespace checks pass.

`place_approved_board.py` copied v003 to `L_WorkshopPreview_v004`, preserving
all existing props and adding separate `CircuitBoard_Foreground` at
(56, -248, 92.2987326) cm, bounds-aligned to the 92.3 cm table surface. Small
tool collision remains disabled, like the existing wrenches. Addition receipt:
`evidence/L_WorkshopPreview_v004.json`. New scene playback/overview verification
is recorded separately, not implied by this placement receipt.

Operational correction: direct Python `-c`/`-m` resolves an older installed
package unless `PYTHONPATH=<repo>/src` is set. The first runtime-record command
failed before writing; the corrected source-pinned command succeeded. Run
audits with that path too. CLI scripts already prepend the repository source.
No inference or user-process termination occurred; dedicated UE processes
completed normally. Full character texture/rig, sword attachment, sofa/foliage,
room polish and cooked demo remain outstanding.

The v004 dedicated PIE probe completed with all six checks true (possessed,
spawn/floor, walked forward, inside wall, wall blocking, still on floor).
Movement uses `Character.add_movement_input`, from (-100,140,92.15) to
(385.903,111.035,92.15) cm, approximately 4.87 m. Both actual overview and
player-window frames inspected in `evidence/walkthrough-v004/`; Manny remains
the pawn. No physical-keyboard or packaged-runtime claim. The new board is
small in the overview; its close detail is proved by the separate matched
views, not this room camera. Room remains visibly sparse/repetitive with a
soft backdrop. Launcher now defaults to v004; v003 remains explicitly selectable.
README updated to 19 independent props / seven types and removes the resolved
board hold. Source-pinned board and Ayric ledger audits both pass integrity;
neither is production-ready. No UE process remained after these captures.

### 2026-09-04 — bounded bilateral nape repair, texture gate still held

Previous goal turn: progress (board import/runtime review, separate placement
and v004 PIE proof). This turn returned to the character's actual side-view
defect: white/gray and cyan paint crossed skin behind the ear into the collar.
The preferred front eyes/mouth/beard remained outside the repair.

Built-in ImageGen edited the actual packaged opposite-side albedo frame from
`prod-neck-v001/face-review-v001/albedo-face-opposite-side.png`, SHA
`8907c490e790206295eacb1551dd6ad9eaec1ac6c22dfc074586b8a5dca4370c`.
Saved project donor `work/sunset-workshop/character-art/ayric-nape-donor-v001.png`,
SHA `5229f65160d204745974a7953b0b42a9502f614deac5ddb2e5f88fc6774dfefc`.
Exact prompt, original tool output path and input/output hashes are in
`nape-donor-lineage-v001.json`. The donor redraws the ear despite the preservation
prompt. That changed ear is deliberately NOT transported; only plain nape
skin/navy lining samples are used. The donor is not a 3D render.

Existing `export_face_projection.py` generated per-pixel-depth correspondence
from the current packaged FBX at -90 and +90 degrees, bounds .77-.92 height,
.14 half-width. Outputs `texture/nape-correspondence-v001` SHA
`243acb8dc439755749a56655517cf733e7a956213e52786fcd23296a6c172f57`
and `texture/nape-opposite-correspondence-v001` (hash in its receipt/config).
No geometry/UV edits. Configs `nape-registration-v001` through `v003.json` and
transfers of the same names are retained. v001 (18,346 texels) left a white
diagonal at the boundary and is rejected in `nape-rejections-v001.json`.
v002 expands that boundary, using donor samples behind the redesigned ear:
21,781 selected texels + 5,304 unused gutter texels. v003 maps plain donor
skin/lining to the other actual side, with asymmetric target controls:
13,341 selected + 6,028 gutters. Each transfer verifies zero protected overlap,
unchanged geometry/UVs, and bit-identical pixels outside support/gutters.

The first CPU preview bind failed before output because the native authority
material is `RepackTransport`; supplying the existing explicit
`--material-name M_SunsetAyricV2_Body` option fixed that invocation. Not an
inference crash/retry. The only AI call was the new bounded built-in donor.
No local generator or user application was stopped.

`nape-pbr-config-v001.json` / `nape-pbr-v001` calibrate the union of the two
geometry-bound masks: 35,110 quantized-mask texels, roughness floor .65,
metallic ceiling 0. Changed 17,160 roughness and 30,056 metallic texels;
base-color bytes and outside support preserved. This removes the false skin
glint without changing the armor's existing material response.

**Preferred held character package is now `work/sunset-ayric-v2/prod-nape-v001`.**
Same `texture/repacked-face-v006/uv-authority.blend`, 1.85 m, 19,588 triangles,
9790 native vertices and 4096 maps; no extra repack. Final base SHA
`6a505eb81f2e31a458b115682d2237f432fab827d5ad8fc9097983857f6e41cd`.
Density 301.3 passes; lighting -0.2401099355 still fails absolute .12;
fragmentation 272 remains advisory. Twelve full-body and ten face lit/albedo
frames retained. Actual packaged front, side and opposite lit side plus full
front/back inspected. The large pale nape patch is removed and front identity
preserved. A narrow hair-edge/collar artifact and earlier collar/body paint
defects remain; do not call the texture finished or rigging-ready.

Panel `work/sunset-workshop/evidence/ayric-nape-review-v001.html` / `.json`
binds the current held package and all opposite views. Display was queued in
Codex. `texture/ledger-before-nape-v001.json` preserves the old ledger;
`unwrap_and_bake` remains rejected, now bound to the new package and donor/
mapping evidence. Source-pinned integrity audit passes; readiness false.
149 tests plus 3 subtests pass. Board/v004, sword and all old candidates remain
unchanged. Full demo goal stays active. Next work must resolve the remaining
material/collar construction and independent lighting hold causally, not repeat
whole-body delight or tune colors to the score. Rig/deformation, sword attachment,
room polish and cooked-runtime evidence remain genuinely outstanding.

### 2026-09-04 — collar surface repair and separate sword UE import

Previous goal turn classified as progress: bilateral nape repair changed the
preferred held package. Current pass inspected actual nape-package front/side
and full body, then targeted the smeared front gorget rather than changing the
preferred face again. No local inference or user-process termination occurred.
Preflight: 329 GB C: free, RTX4090 about 23 GB free, no UE/Blender process.
`verify.ps1` passed 149 tests. Doctor initially lacked process-local RAC roots;
setting RAC_LEGACY_ROOT=C:/Comfy/blender-reference-studio and
RAC_COMFY_ROOT=C:/Comfy/ComfyUI yielded WORKFLOW_DOCTOR_OK. No install needed.

One built-in ImageGen call edited actual
`prod-nape-v001/face-review-v001/albedo-face-front.png`, SHA
`dab2911832c503458c456d71d5ba71bfc08e77c804fa7b5167386e0710884c9f`.
Project donor `work/sunset-workshop/character-art/ayric-collar-donor-v001.png`,
SHA `2f8b13929523db35c6842f97bd9e1d2c10a7e1e0c3293014c3809f347cb8f0a9`.
Exact prompt and source/output provenance: `collar-donor-lineage-v001.json`.
Only collar paint is transported; any generated face/chest/shoulder changes
are outside the selected domain. This raster is not a 3D render.

`texture/collar-correspondence-v001` used actual packaged FBX, angle0,
height .68-.83 and half-width .15, pixel-depth visibility. That height ceiling
cut the raised rim and produced a visible hard seam in `collar-preview-v001`.
Retain rejection `texture/collar-rejections-v001.json` and its hashed frames.
`collar-correspondence-v002` extends max height to .87, SHA
`833efd18057670722406a676d3a7a561bfd0bc4d8db3b382abfe03f46b170c39`.
`collar-registration-v002.json` also covers the lower damaged gold edge,
while excluding bare neck, face, shoulders and central gem. Both configs use
the original nape atlas, not a chain over rejected v001. No mesh/UV changes.
Final transfer: 74,570 selected texels, 20,697 unused gutter texels, zero
protected overlap, outside support/gutters bit-identical. Base SHA
`5dda5e319d5aa94f6703f33bae3b1398e4d19531b68b06503adc506deed1c0e5`.
`collar-pbr-v001` changes 70,752 roughness texels to a minimum .55 within
74,549 quantized-mask texels, metallic unchanged; all other scalar texels
and base color preserved. Existing scripts used without code changes.

**Preferred held package: `work/sunset-ayric-v2/prod-collar-v001`.** Same
repacked-face-v006 native authority, 1.85 m, 19,588 triangles, 4K maps,
301.3 density. Lighting -0.2378495671 still fails unchanged absolute .12;
272 UV fragments advisory. Packaging exit1 is this expected gate failure,
not a crash. Twelve body frames and ten face frames complete. Inspected
packaged lit front, albedo side/back, and preview front/both three-quarter
albedos. Continuous collar front now reads better. Side/back collar/hair-edge
artifacts, side/body paint and lighting remain unresolved. No rig promotion.

Panel `evidence/ayric-collar-review-v001.html` / `.json` binds the package and
actual views; open_in_codex queued display, not confirmed visible.
`texture/ledger-before-collar-v001.json` preserves old ledger. unwrap_and_bake
remains rejected, bound to new package and mapping/donor evidence. Source-pinned
integrity audit passes, production_ready=false.

Independently advanced the sword's next gate only. First UE invocation used
a relative project path and exited before opening a project; retained
`evidence/sword-import-v001.log`. Corrected absolute path, narrowly scoped
RAC_ASSET_IDS=sunset-sword-v1-production, completed normally in UE5.8.2.
`evidence/sword-import-v002.json` / `.log`: all seven checks pass. New mesh:
`/Game/Compiled/SunsetSwordV1Production/sunset-sword-v1-production`.
Native LOD vertices 11,123 / 6,429 / 3,647; triangles 18,000 / 9,000 / 4,500;
one section each, height135cm, assigned/sampled textures and sRGB correct.
Manifest SHA43884051baa8b3bc9e703990621810e75b0a745fcb9dadd8a29fbfe1cffd08c0.
Recorded immutable `work/sunset-sword-v1/validation/ue5-import.json` through
record_ue5_import.py; ledger audit passes, runtime review/cook remain pending.
No sword attachment or visual runtime claim yet. v004 and all original
authorities remain unchanged. No UE/Blender processes remained after work.
Next independent sword gate is actual UE static visual review; character
material construction and causal lighting resolution remain before rigging.

### 2026-09-04 — sword six-view review; alternative albedo checkpoint staged

Current pass is progress, not demo completion. No character texture changes,
rigging, inference or process termination. Ayric remains `prod-collar-v001`,
unwrap_and_bake rejected, lighting -0.23785 against absolute .12. Do not hide
this hold behind the independent sword progress.

New `scripts/ue5/review_sword_runtime.py` copies v004 into isolated
`L_SwordReview_v001/v002/v003` fixtures. All have six actual 1920x1080 frames:
front, three-quarter, side, back, front LOD1 and front LOD2. Each process ended
normally, error=null and level_saved=true. v001 was underlit; v002's neutral
fill at1800 was overbright. Retained both. v003 uses the same three RectLights
at180; actual six views inspected. Blade outline, guard, gem and pommel read
across views; side has real thickness; reduced LODs retain silhouette. Grip
looks lighter under fill than in Blender. No mesh/material modification.

Recorded delegated static editor review through the source-pinned recorder:
`work/sunset-sword-v1/validation/ue5-runtime-review.json`, approved_by=codex,
human_visual_review=false under existing authorization. Import manifest SHA
43884051baa8b3bc9e703990621810e75b0a745fcb9dadd8a29fbfe1cffd08c0;
import receipt SHA017b8a58fcaebaa49b0b2cf2d37fa1dccfe699d2120ff6434e21b89ec1d4b8bb.
Ledger runtime review passed, cook pending. Not back attachment, collision,
movement or cooked proof. Playable v004 unchanged.
Panel `work/sunset-workshop/evidence/sword-review-v003.html` and bound `.json`
retain accepted and rejected lighting fixtures. Builder
`scripts/build_sword_review.py`; Codex display queued, not confirmed visible.

Pipeline added `static_review.py`: all-frame hash/path/camera/forced-LOD and
native-import binding for explicit static multiview schema. Recorder retains
all frames; central audit revalidates them and refuses downgraded receipts.
152 tests pass, scoped Ruff and git diff --check pass. Source-pinned audits
pass for sword and Ayric; neither production-ready. No dirty work removed.

Alternative albedo tool intake is staged, not inference-proven:
`work/toolchains/IntrinsicAnything` official source revision
e1287870d88fd51d310b8fcd2250057dad8d320e;
LittleFrog/IntrinsicAnything model revision
f2f095e1a9a60a45272299127b372488dca4a619, model card Apache-2.0.
Albedo checkpoint download completed and local SHA assertion passed:
15,458,840,153 bytes, SHA
a5fa7a1caa7e1e3818119cd9a2e8715ee7b86a77fa66447cc4b0767d8ab550f8.
Exact receipt `work/toolchains/intrinsicanything-intake-v001.json`.
Weights/config under `work/toolchains/intrinsicanything-weights/albedo`.
Specular checkpoint not downloaded. Download session95548 finished exit0.
No isolated runtime created yet; existing environments untouched.
Official stack targets Python3.10/torch2.0.1 with old PL/diffusers. Inspected
FrozenCLIPImageEmbedder: calls clip.load('ViT-L/14') then deletes text
transformer, so CLIP model/cache bytes are additional. This is a single-view
albedo candidate, not released multiview inverse rendering. Next safe work:
isolate compatible runtime, account for added dependencies, inspect GPU owners
before one probe; preserve current face/mesh/UV authority and reject failures
without repeated blind inference. Character still needs material resolution
before rigging; full room polish and cooked demo remain open.

### 2026-09-05 — isolated intrinsic-albedo runtime and two-view probes

Previous turn: progress (sword static review). Current turn: progress, not
completion. Installed an isolated inference environment and produced new,
reviewed lighting-estimation evidence; no character atlas or ledger promotion.
`prod-collar-v001` remains the preferred held package, lighting -0.23785,
unwrap_and_bake rejected. Source-pinned audit passes; not production-ready.
Doctor WORKFLOW_DOCTOR_OK and verify RAC_VERIFY_OK; 152 tests pass, scoped
Ruff passes. GPU preflight about22.8GiB free; no generator owners identified,
Comfy8188 connection refused. Existing MCP/LM Studio/UI processes preserved.

`work/toolchains/intrinsicanything-env` uses Python3.10.16, torch2.0.1+cu118,
torchvision.15.2, original PL1.5.2/diffusers.12.1. Requirements and repeatable
instructions: `workflows/texture/intrinsicanything/`. Compiler/Hunyuan envs
unchanged. Initial import exposed missing matplotlib/CarveKit, now included.
Kornia import fetched HardNet into the normal torch cache, 5,345,580 bytes,
SHA1e9a41b19f1dc93c986e91df9aaf5696d1a777ac1d67498492856a65d6f49c16.
CLIP ViT-L/14 downloaded and hash-verified in its isolated cache, 932,768,134
bytes, SHAb8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836.
Logical measured tool directories plus HardNet:22,480,161,554 bytes, excluding
Python interpreter/uv cache. Not allocated disk space (uv uses hardlinks).
Full breakdown `work/toolchains/intrinsicanything-runtime-v001.json` and tool
README; original download-only intake receipt retained.

New `scripts/blender/render_intrinsic_inputs.py` renders unchanged packaged
FBX with emission-only base color, Standard sRGB exposure0/gamma1 and RGBA
object alpha on CPU. Do not feed calibrated exposure-1.5 review frames into
an albedo model. `texture/intrinsic-inputs-v001/inputs.json` binds source FBX
SHAd92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3,
base SHA5dda5e319d5aa94f6703f33bae3b1398e4d19531b68b06503adc506deed1c0e5,
and full-body/front-face images. Mesh/UVs/maps untouched.

New `scripts/run_intrinsicanything_probe.py` validates exact model/CLIP hashes,
source revision, input lineage and21GiB free VRAM. Records full package/source
inventory, settings, outputs, timing and peak allocation; no auto-retry.
v001 failed before sampling: upstream taming wheel contains metadata but no
package because find_packages misses namespace directories. Retained log and
execution receipt. Cloned original taming commit
3ba01b241669f5ade541ce990f7650a3b8f65318 into work/toolchains/taming-transformers;
all configuration classes import successfully when this source is on sys.path.
v002 was a preflight refusal for import-generated untracked __pycache__ only;
retained log, no inference/output directory. Guard now tolerates only those
untracked .pyc files, still rejects source edits. No neural source patch.

`texture/intrinsic-probe-v003` completed the official seed0,100DDIM,batch1,
CFG1/guidance0 baseline on body-front and face-front. 22.797s, peak allocated
5,441,026,560 bytes. Model runs256px then restores output canvas1024px. Both
actual outputs inspected: reject direct replacement for softened eyes/beard
and armor detail. Geometry/texture authorities were not modified.

`texture/intrinsic-highres-v001` completed the documented guided pass using
the hash-bound v003 outputs,200DDIM,guidance3,2x2splits,overlap1,batch1. Nine
patches per view.236.235s, peak allocated7,434,563,072 bytes. Actual outputs
inspected: body bands/specks reduce and principal gold trim survives; face
detail improves over the low-res estimate but rectangular patch transitions
cross forehead/cheek and linework softens. Reject direct face replacement;
hold only as a possible broad illumination donor. Do not substitute it for
the accepted facial landmark paint or promote the texture gate.

Comparison panel `work/sunset-workshop/evidence/intrinsic-review-v001.html`
and `.json` bind inputs, both completed attempts, reviews and both failed
preflights. Builder `scripts/build_intrinsic_review.py`. First column is actual
mesh render; other columns are 2D AI estimates, clearly labeled. Codex display
queued, not confirmed visible. All process sessions terminal; GPU back to
about1.28GiB used/22.86GiB free. No local inference left running.

Next material work: use this independently tested estimator only if bounded
low-frequency illumination transfer can preserve original facial landmarks
and gold linework. It needs matching side/back evidence and UV-aware transport
on the unchanged authority before any new candidate can be judged. Do not
repeat the same direct full-face replacement or quietly tune colors to pass
the correlation score. Character rigging, back attachment, room polish and
cooked demo remain genuinely outstanding.

### 2026-09-05 — complete orbit falsifies IntrinsicAnything transfer route

Previous turn: progress (working isolated estimator plus front-only evidence).
Current turn: progress through new negative evidence and tested downstream
transfer safeguards, not character completion. No actual Ayric atlas transfer
was run. Preferred held package remains `prod-collar-v001`, unchanged lighting
-0.23785, no rig/UE promotion. Full demo goal remains active.

Read `docs/ESCALATE-sunset-lighting.md` before more character inference.
Three completed, retained orbit trials now reject this estimator for the
proposed full-body lighting transfer. Do not repeat angle/crop/seed tweaks.

`scripts/blender/render_intrinsic_inputs.py --body-multiview` adds six actual
CPU unlit RGBA views and hash-bound per-triangle UV/screen/depth/cosine/height
arrays with depth buffers. `texture/intrinsic-orbit-v001` uses0/90/180/270 and
overhead/underside cameras. `--oblique-sides` creates separately retained
`intrinsic-orbit-v002`, replacing90/270 by60/300, accurately labeled right/left
oblique. Geometry/UV/map files remain unchanged. Both receipts bind the current
FBX and base color; existing face inputs and all prior review frames retained.

Official estimator v001 completed six outputs, but both exact-side estimates
turned colored subjects into black silhouettes. Source crops about848x150 and
846x149 are real colored RGBA images, not bad UV renders. Retained
`texture/intrinsic-orbit-rejection-v001.json`. v002 uses the wider obliques;
one side improves, the other still loses nearly all armor color. Third and
final bounded orbit trial v003 uses same inputs with unguided3x1 vertical
splits/overlap1,100DDIM,batch1 (new explicit --vertical-patches3 wrapper option,
not the official guided highres recipe). It completed in97.641s, peak tensor
allocation5,452,954,112bytes. Color returns on the failed side, but horizontal
patch bands and black lower legs/feet appear elsewhere. Rejected before bake.
No neural source edits or automatic crash retries. All sessions terminal:
render66767/76354, inference75280/14138/84405. GPU back to1,281MiB used,
22,858MiB free; original application/MCP processes preserved.

New `scripts/transfer_intrinsic_illumination.py` computes fixed sigma16 masked
log-luminance gains, capped.5..2, perspective/depth-tested UV transport and
head protection. Triangles touching normalized height>=.82 remain unchanged;
transition starts.68. A black-silhouette donor check prevents interpreting
failed estimates as strong darkening. This code is experimentally tested only:
**no real Ayric atlas has been emitted from it**, because visual donor review
failed. Seven new tests include a synthetic full transfer proving protected
head and original atlas bytes unchanged. Full159tests pass; scoped Ruff passes.

Panel `work/sunset-workshop/evidence/intrinsic-orbit-rejections-v001.html`
and matchingJSON bind all18 output hashes, receipts and explicit rejection
reasons. Builder `scripts/build_intrinsic_orbit_rejections.py`. These are
2D estimates, not 3D model changes. No inference or Blender left running.

Primary-source license check: compphoto/Intrinsic README states academic use
only, so it was not installed or used for this shareable pipeline. Do not
infer that a research estimator is commercially deployable. Next turn should
read the escalation, reconsider the material acquisition route causally and
advance an independent actual demo asset gate (foliage/sofa/scene), not loop
on this same failed lighting estimator. Character face/material hold, rigging,
back-carried sword, scene polish and cooked proof all remain outstanding.

### 2026-09-05 — plant acquisition repaired; runtime topology still held

Previous turn: progress through falsified character-lighting orbit and retained
transfer safeguards. This turn: progress on independent plant modeling and
cleanup. Full demo goal remains active, not blocked or complete. Ayric remains
at unchanged `prod-collar-v001`, texture/rig hold intact; UE preview v004 and
all creative application processes preserved.

Built-in ImageGen generated two secondary plant views. Files and exact prompts
are under `work/sunset-plant/references/multiview-v001/{left.png,back.png,lineage.json}`.
Original front input remains immutable intake48f083a3ab3b2ff90e19640b843ae6509163e4d19006432d1167de7f318fb484.
Left SHA f48b0987fb3f815d41fcba63b86ffb17f89799e06530a5954495f86f17ad615b;
back9a8ec4096516abf456b2842f79b8d7845ad482cd2d2494217af1bcb25e58135c.
They are inferred depth guidance, not exact orthographic rotations. The approved
image directly conditions the AI front input; Blender remains downstream.

Guarded request `requests/hy3d-mv-seed42-attempt002.json` completed once with
Hunyuan3D-2mv revision3a761b539b29fe4ff64714813aa9560fd66f5de0,
seed42/40steps/octree512/chunks20000. Generation62.702s,1,252,679vertices,
2,505,442triangles. CandidateSHA d5b175b50e329501a710ba5f7cf72717466e717163eceeec90779e0f40be5353.
Seven actual clay directions inspected: intact broad leaves, pot proportions,
soil/stems and far side acceptable for this stylized scene. Small rounded tips
and chunky stalks explicitly noted, not botanical exactness. Delegated modeling
receipt in `modeling/multiview-v001`; authorizationreviewer=codex/humanfalse.
Old single-view rejection and prior full ledger retained in that directory.
First recording attempt omitted multiview input artifacts; central ledger
refused it without mutation. Corrected evidence includes all inputs/lineage.

`cleanup/multiview-v001/cleaned.blend` SHA8949b98be293c357a552ca8f361ce89bcc5cb0588ab7f9fa06c50e9dc042a2c1.
Conservative sanitation passes native roundtrip;72tiny boundary edges after
degenerate-face removal are reported, not hidden. Runtime voxel reduction
closes them. Cleanup authority retained immutable.

Topology is **rejected** after these retained actual-view trials:
- `retopology/multiview-v001`: voxel512/smooth2/lambda.28/QEM18k;8944vertices,
  18000tris, closed. Pot facets/leaf-underside angular patches appear.
- `multiview-normals-v002`: dense custom-normal modifier transfer, no shape
  change, no sufficient visual improvement; native and GLB views inspected.
- `multiview-normals-v003`: explicit dense BVH barycentric vertex normals,
  unchanged geometry, maxsource-localdistance.003937; artifacts remain.
- `multiview-refined-v004`:600edges selected by area-weighted midpoint error,
  newvertices projected onto original AI surface;9544verts/19200tris/closed.
  Pot artifacts remain, no approval. No image tracing or procedural rebuilding.

New downstream diagnostic scripts: `blender/transfer_surface_normals.py` and
`blender/refine_reduction_surface.py`. They are not default pipeline stages or
proven production fixes. `retopology/multiview-rejections-v001.json` binds all
four rejected mesh/report/front/three-quarter/side/back sets. Central ledger
audit passes integrity with production_retopology=rejected, later gatespending.
`scripts/build_plant_review.py` writes immutable HTML/JSON comparisons:
`work/sunset-workshop/evidence/plant-repair-review-v001.html`.

Doctor passes installed direct geometry/Paint/Blender/ARP/UE routes (optional
Comfy nodes remain absent). scripts/verify.ps1 passed159tests. All inference
and Blender sessions terminal. Next: diagnose curved-surface reduction shading
or choose a materially different retopology route, not another normal-only
rerun. Character face/material hold, rigging, sword attachment, sofa, scene
polish and cooked-demo proof remain genuinely unfinished.

### 2026-09-05 — renewed face feedback; head paint trials rejected

User calls the face texture poor and likes everything else. Returned to the
character without changing props, UE map, rig state or held package. Read
`docs/ESCALATE-sunset-face.md` before another face experiment.

Three built-in ImageGen donors condition on actual head renders; the initial
donor also uses the original photo for identity. Prompts/project copies:
`work/sunset-workshop/character-art/ayric-side-detail-donor-v001.png`,
`ayric-opposite-detail-donor-v001.png`, `ayric-front-hair-donor-v001.png`.
These images are donors, not renders of changed models.

Depth-tested camera-to-UV mapping stays downstream of AI acquisition. Actual
side-only preview improves ear/sideburn detail but leaves a color transition.
Three-view wrap improves hair detail but leaves skin patches/dark breaks in
the left fringe. Both rejected, not preferred-package changes. Five-angle
lit/unlit sets: `texture/side-detail-preview-v001/closeups` and
`texture/head-wrap-preview-v001/closeups`. All ten final frames generated;
front, both sides and opposite three-quarter inspected explicitly.

Final trial base SHA922cc8c541d29a3c35b22cd6badb0e68f40ede82ffd0107829d38e6cdf7e1ba1
belongs only to the rejected wrap. Current `prod-collar-v001` FBX/base hashes
remain d92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3 /
5dda5e319d5aa94f6703f33bae3b1398e4d19531b68b06503adc506deed1c0e5.
Both bindings preserve9790vertices/19588tris, UV authority, face order and
1.85m scale; roughness/metallic byte-identical to current.

Reinspection of actual `retopology/projected-v002/closeups-v001/face-front.png`
exposes shallow modeled eyes/mouth. Reconsider image-conditioned head
acquisition; do not keep polishing front stamps or manually sculpt a
replacement. No ledger stage silently revoked or advanced. Lighting/rig hold
remains. Panel `evidence/ayric-head-detail-review-v001.html` / JSON binds89
files and rejection reasons. One-off builder and mapping/staging drivers:
`work/sunset-ayric-v2/texture/record_head_detail_review.py` and siblings.
They are not a claimed pipeline default. Doctor passed installed direct
routes;159tests passed. CPU renders finished normally, no local inference
or process termination. Full demo goal active, not complete.

### 2026-09-05 — detailed AI head acquired; both runtime reductions rejected

Continued the face repair in new isolated `work/sunset-ayric-head-v1`.
Front reference derives from original identity photo; ImageGen inferred
left/back images guide one guarded Hunyuan3D-2mv run (seed42,40steps,512).
Exact prompts: `references/prompts-v001.json`; lineage under
`references/multiview-v001/`. No hand-authored approximation. Generation
completed normally in62.65s, pinned model revision
3a761b539b29fe4ff64714813aa9560fd66f5de0. GPU owners preserved.

Candidate SHA12e9c6af5959be665d7f87f66af8145ab6791c0e4db54c5055daab2a2f80faa9.
Seven actual clay angles show modeled eyelids, eye volumes, lips, nostrils,
ear conchae and a coherent skull. Component-only modeling passed delegated
review, not whole-character approval. Front solid-silhouette IoU0.931675,
centroid10.142px meets declared0.90/12px. Initial Otsu mask wrongly excluded
bright skin; its failed measurement and explicit outer-contour correction
remain retained. No nonlinear warping. `reference_manifest.json` records scope.

Semantic cleanup passed; source immutable:
`cleanup/multiview-v001/cleaned.blend`
SHA601be1579f57b62591abad0efef4a30fc9fa7eeb65cec2cb208a392480f6bacb.
It retains31 mesh components/33boundary edges and dense beard/hair relief;
this is not final closed runtime topology. Current body/UV/package unchanged.

Topology trials, both rejected:

- `retopology/quad-v001`: AutoRemesher target3000quads, actual11,136tris,
  89.1%quads,4boundary edges, exceeds6,500trial allowance. Facial features
  flattened in actual matched CPU clay.
- `retopology/voxel-quad-v002`: voxel512, minimal smoothing1/lambda0.1,
  QuadriFlow2500target, actual4,030tris/100%quads/6boundary edges. Severe
  eye/lip/hair/ear loss. Normal completion followed by guard rejection.

`retopology/rejections-v001.json` binds meshes, reports, logs and four matched
CPU views per trial. Ledger production_retopology=rejected; audit integrity
passes. No stage waiver. One-off `record_reduction_review.py` builds
`work/sunset-workshop/evidence/ayric-head-geometry-review-v001.html` plus JSON.
Reference prompts, source renders and both rejected sets remain browsable.
All current inference/render sessions terminal, no local generators left.
159tests passed earlier in this turn; no shared pipeline code changed here.

Next unresolved gate is head reduction: diagnose feature-preserving surface
reduction before another global quad remesh. Do not repaint these failures
or pretend boundary closure restores identity. Body-region budget probe
(`modeling/body-region-budget-v001.json`) is only an estimate, not a cut.
Head/body integration, full UV/textures, rigging, sword carry, scene polish
and cooked runtime proof remain incomplete. Full goal remains active.

### 2026-09-05 — surface-preserving head diagnostics locate the next defect

Previous goal turn classified as progress: detailed component acquired and
two remesh failures recorded. This turn preserved body/scene/authorities,
ran159tests successfully, and tested CPU-only reductions. Preflight RTX4090
had22,805MiB free; disk305GB free. MCP services preserved; no inference run.

All paths below are under `work/sunset-ayric-head-v1/retopology/`:

- `feature-qem-v003`: generic weighting20,5,000tris, closed, no quads;
  p99 deviation0.010535 source-world units, angular/missing facial detail.
- `qem-control-v004`: same5,000tris, weighting0; p99 improves to0.008154,
  but still angular eyelids/lips. Generic feature weights are not a cure.
- `face-priority-v005`/`v006`: soft importance masks around existing eye,
  nose and mouth samples, factors0.02/2.0. Stronger setting improves mouth
  volume but not acceptable eyelids. Masks select importance, not geometry.
- `qem-intermediate-v007`:20,000tris, generic mechanics pass, p99 0.002531,
  max0.005084. Actual clay nevertheless introduces a distinct under-eye pit.
  This is an intermediate, not a head-budget or articulated-topology pass.
- `protected-face-v008`: guard rejected before reduction; disconnected
  vertices exceed2% removal cap. No output mesh. `failure.json` retained.
- `protected-face-v009`: keeps all31 components (main9807vertices,
  remaining219), freezes828 existing facial vertices exactly, reduces to
  5,000tris. Triangle pairing yields42.69%quads, below80% requirement.
  Inherits under-eye defect and coarsens ears/neck. Rejected.

Most useful new causal evidence: actual dense cleanup clay has no under-eye
pit; v007 introduces it; v009 retains it in both native pre-pairing triangles
and pairedGLB. Triangle pairing is therefore not its origin. All fixtures
use the same neutral CPU24-sample lighting. Next: diagnose QEM displacement
versus normals at that defect. Bounded dense-source projection may be tested
as a diagnostic; do not claim a pass without visual/topology evidence.

The Blender collapse source was inspected directly: nonplanar edge cost adds
edge length times inverted endpoint-weight penalty times weight factor.
Do not assume large generic feature factors are harmless. Official source:
https://raw.githubusercontent.com/blender/blender/main/source/blender/bmesh/tools/bmesh_decimate_collapse.cc
No shared reduction default changed based on these unsuccessful trials.

`rejections-v002.json` binds all trials and prior rejections; ledger
production_retopology stays rejected, audit integrity passes. New panel:
`work/sunset-workshop/evidence/ayric-head-surface-review-v002.html` plus JSON.
One-off drivers `reduce_face_priority*.py`, `reduce_protected_face*.py`,
`render_reduction_trial.py`, `record_surface_trials.py` stay job-local.
All launched processes terminal, no automatic crash retry. Full Ayric
integration/texture/rig and complete workshop/cooked demo remain unfinished.

### 2026-09-05 — source normals remove under-eye darkness; global transfer rejected

Previous turn is progress: reduction controls isolated the intermediate
defect. This turn tested the actual cause, no GPU inference or authority edits.
All paths below are under `work/sunset-ayric-head-v1/retopology/`.

- `projected-intermediate-v010`: bounded nearest dense-surface projection,
  max displacement0.004757 source units, same connectivity/winding/counts.
  Actual matched clay still has under-eye pit. Rejected as a repair.
- Read-only native probe confirms v007 has no inherited custom normals.
- `normal-intermediate-v011`: barycentric dense-source vertex normals remove
  the dark under-eye pit with exactly unchanged geometry. This establishes a
  shading contribution, not perfect facial geometry or runtime readiness.
- `normal-priority-v012`:5k weighted head, source normals, explicit diagnostic
  mode. Rejection retained; simplified eyelids/mouth and coarse hair remain.
- `normal-protected-v013`:5k paired protected-face head, source normals.
  Under-eye darkness improves, but all-four-angle review reveals objectionable
  neck/rear-skull shading, coarse ears and existing42.69%quad failure. Rejected.

`normal-diagnosis-v003.json` binds all new evidence and prior rejections.
Ledger production_retopology remains rejected; integrity audit passes.
Panel `work/sunset-workshop/evidence/ayric-head-normal-review-v003.html`.
v013 normal/native SHA db6c9ca9221e71fd2abdfa14a8cdf3543a6aa3ce3f1198a365d77077cf8063ea.
Current whole-character FBX hash remains d92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3.

Shared `scripts/blender/transfer_surface_normals.py` now loads exact bound
native BLEND as well as glTF, and supports explicit `--diagnostic-only` for
report-bound rejected reductions. Source/output hashes remain mandatory;
failed/incomplete attempts cannot be used. Diagnostic outputs remain rejected.
Six new routing/binding tests pass; full suite165tests passes. Native-input
derivative reports now bind native output, with glTF only as review transport.
The retained v011-v013 reports predate that final binding fix: their quad
counts refer to native meshes; use `normal-transfer.json` output_blend hashes
and do not infer glTF preserves quads. None is promoted.

Next: if pursuing this shading repair, restrict source-normal transport to
the face, preserving ordinary normals on coarse neck/back. Do not repeat
global normal transfers or source projection as the solution. Actual quad
topology, valid full-character allocation, UV/texture, assembly/deformation,
rigging, sword carry and finished/cooked workshop remain unresolved.
All current Blender sessions terminal; no active generators or automatic retry.

### 2026-09-05 — localized normals and explicit modular head route

Previous turn made progress by identifying source normals as the under-eye
shading repair. Added hash-bound `--region-config` to normal transfer: a
feathered world-space box blends donor normals only in the modeled face.
Geometry remains unchanged. Two new pure routing/region tests; full suite
passes after the change (167tests total).

Old job `work/sunset-ayric-head-v1`:

- `normal-face-only-v014`:5k protected/paired source, face shading improves
  without global-transfer neck/back damage, but geometry remains too coarse.
  Old integrated-humanoid topology remains rejected,42.69%quads unchanged.
- v015 preflight rejected an accidentally wrong5k control hash in its region
  config. No output mesh or processing occurred. Failed config and
  `normal-face-only-v015-failure.json` retained; v016 uses the verified20k hash.
- `normal-face-only-v016`:20k intermediate,836 affected/9190 untouched
  vertices. All four actual clay directions inspected; face improvement,
  substantially better ears/hair and clean neck/rear compared with5k trials.
  Native SHA2fd0b2c2a75e4a5194b8ff78639d14a900a5d67d76f5ba433c014e5a9132df29.
  Still diagnostic, not a pass in the old humanoid ledger.
- Native roundtrip audit `regional-normal-roundtrip-v002.json` verifies exact
  geometry preservation. For v016,54,958 valid outside loop normals differ
  by at most6.8e-7;24 original outside normals are undefined/zero. Initial
  strict probe failed on those zero normals and is retained unchanged.
  Undefined normals/tiny degenerate geometry remain cleanup debt, not waived.

Implementation decision explicitly explained to the user: a separate rigid
head attached to the UE head bone, preserving the requested custom avatar
without forcing a deforming face into the body's remaining5k allocation.
Per-component20k triangles/15k vertices unchanged; combined body/head/sword
target60k, actual summed counts still mandatory. This is not a20k complete
avatar or a benchmark-budget change. Full neck/animation/cooked checks remain.

New `work/sunset-ayric-rigid-head-v1` has immutable intake, explicit
`assembly-contract.json`, reference manifest, and exact acquisition reuse.
Original generation receipt/images/mesh unchanged; no new inference or manual
reconstruction. generate_candidates and component modeling_approval pass,
audit integrity passes. **Next gate is semantic_cleanup**, then independently
reviewed static runtime topology. Prior head/job rejections remain intact.
The20k shaded diagnostic is only a candidate to evaluate after those checks;
do not skip directly to paint or call the modular avatar assembled.

Panel `work/sunset-workshop/evidence/ayric-modular-head-review-v001.html`
compares dense acquisition,20k candidate and coarse5k case and states the
full component/assembly requirements. README/completion contract updated.
Body/UE scene unchanged. All launched processes terminal; no GPU inference.

### 2026-09-05 — rigid head cleanup and static topology accepted

`work/sunset-ayric-rigid-head-v1` now passes semantic_cleanup and
production_retopology. Next gate: UV preparation / unwrap_and_bake, then
head-only texture review. Do not rerun accepted geometry or change the body.

Accepted native authority:
`retopology/face-normals-v006/normal-transfer.blend`, SHA
`0d8cf0a92b97ff808302a3e757d42580a6df5089763841d424030d38b24d5dbe`.
10,020 vertices,19,988 triangles,31 acquired components, zero boundaries,
nonmanifold edges, degenerate faces or undefined corner normals. Four actual
matched CPU clays reviewed; modeled eyelids/lips/ears and hair retained.
Source overlay IoU0.934667 and centroid10.654px pass0.90/12px.
Native geometry unchanged by normal transfer; outside-region normals differ
by at most6.8e-7. Review is explicitly delegated, not human visual review.

Cleanup reused the immutable old dense cleanup and created a new-job receipt.
Runtime edge-cleanup-v001 welded two near-coincident vertices, retained all
components and fixed the three microscopic edges. Contrary to an earlier
inference, the original QEM audit had zero degenerate faces; the24 undefined
corner normals came from collapsed opposing-triangle components.
The initial indexed-delete script failed before output (retained failure).
Corrected collapsed-fragments-v003 removed11 zero-volume duplicate pairs,
but failed the unchanged source-distance guard. Full source sampling also
identified a removed interior fragment. Do not promote that deletion-only mesh.

restored-components-v005 restores all11 components directly from their dense
AI-source connected components, each reduced to8 triangles. A tiny reduction
outside protected facial samples reserves their budget; all protected face
positions stay exact. Source deviation p99=0.002529,max=0.005084 passes the
unchanged0.005/0.020 guard. v006 then reapplies face-only source normals.
No procedural replacement geometry or thresholds changed.

Current delegated receipt: face-normals-v006/delegated-review-v003.json.
Two incomplete promotion submissions are retained: first omitted the dense
input evidence; second included two delegated receipts. Corrected submission
supplies the dense input and exactly one delegated receipt; ledger audit passes.
Full pipeline suite167tests passed this turn. Shared pipeline code unchanged.

Panel: `work/sunset-workshop/evidence/ayric-modular-head-review-v002.html`.
README and face-resume note updated. Textures, head/body assembly, rig/motion,
sword attachment and polished cooked workshop remain unfinished. All processes
launched this turn exited; no GPU inference. Existing body/scene unchanged.

### 2026-09-05 — first detailed-head paint and coherent UV repair; texture held

Concrete progress: first Hunyuan head-only maps generated and inspected in
eight actual native CPU lit/unlit views; shader calibration separates bad
scalar material response from albedo defects. UV strategy repaired from
fragmented Smart Project to a continuous central face plus geometry-derived
seams. **No texture gate promoted.** Accepted static topology stays unchanged.

Job: `work/sunset-ayric-rigid-head-v1`. Prefer `texture/uv-v004` for the next
mapping candidate. Native SHA
`45a523b74fa8460a0e5e9a50a131d6e808062c249ccc2c98943c5f763e774af0`.
229 islands,1660 facial polygons in one island,49.24% sampled atlas occupancy,
zero sampled facial overlap,0.0268% total sampled overlap. Native and OBJ UV
nondegenerate fractions1.0; exact geometry unchanged, OBJ delta8.62e-7.
Corner-split estimate11,290, **not UE built-vertex proof**. One tiny UV area
below1e-10 remains above the1e-12 degenerate threshold. This is UV preparation,
not an accepted textured runtime export.

UV history retained: uv-v001 Smart Project2221 islands,46.17% of selected face
in largest island. uv-v002 repairs face continuity but2192 overall islands,
11.81% sampled occupancy,20,458 corner-split estimate. uv-v003 seam unwrap has
78 islands but239 tiny non-facial UV triangles and some degenerate UVs.
v004 selectively reprojects those239 non-facial triangles, leaving the facial
island intact; no geometry, normal or face-order editing.

`texture/paint-v001` ran Hunyuan3D-Paint6views/512 once on uv-v002, with the
unchanged intake reference. GPU preflight22,769MiB free, no competing generator.
`head.execution.json`: output maps and geometry/UV validation completed, but
teardown exited -1073741819. No inference retry. `head.validation.json` reports
geometry delta9.5e-8, UV delta5.4e-8, faces_equal=true. This does not make the
process clean or the texture acceptable.
`recover_head_maps.py` adapts the existing recovery correspondence checks to
the `head` basename; retained4K bakes, no upscaling. `native-binding` preserves
exact native geometry/UV/custom normals. All source maps remain unchanged.

Raw appearance rejected: chrome-like scalar material, eye-edge blue artifact,
uneven pale temple/cheek transitions and neck shading. Shader-only
`paint-v001/material-calibrated-v002` sets metallic0 and roughness floor0.72;
all four lit views improve markedly, but unchanged albedo defects remain.
It is a preferred diagnostic, not an accepted texture.

`texture/front-priority-v003` is a deterministic rebake of retained AI views
onto uv-v004, no diffusion/model rerun. All six camera-position-control MAEs
are exactly0. Front priority applied only inside geometry-derived facial UV
support,8px feather; outside support unchanged from its multiview baseline.
Native binding and eight CPU views verified. **Rejected as a whole-face repair**:
it introduces cheek/beard boundary transitions and does not prove clean eye
landmark correspondence. v002's incorrect uint8-to-upstream-inpaint units are
separately rejected; v003 uses normalized floats and checks covered colors.
Do not repeat broad front-face replacement or treat camera agreement as proof
that the generated eyes align with modeled features.

Authoritative appearance findings: `texture/appearance-review-v001.json`.
Panel `work/sunset-workshop/evidence/ayric-head-texture-working-v001.html`
shows preferred matte diagnostic, unlit defects, rejected front-priority
rebake and original chrome material.106 hash-bound artifacts.
Next: diagnose/repair actual facial landmark correspondence in the AI paint
views and skin/hair transitions, using uv-v004. A clearer frontal image alone
cannot waive side/unlit review. Existing body-lighting, rig, assembly, sword,
workshop polish and cooked-runtime requirements all remain unresolved.

Post-work verification: full pipeline tests passed (`RAC_VERIFY_OK`), body
production FBX SHA remains d92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3.
All launched render/bake processes are terminal. GPU back to22,768MiB free;
no competing process stopped, no AI inference retried. No shared pipeline
code changed this turn; candidate UV/rebake drivers remain isolated in the job.

### 2026-09-05 — AI donor artwork and bounded eye/temple mapping

Two built-in ImageGen edits are retained in the rigid-head job's `texture/`:
`donor-front-v001.png` (SHA39f95c42864e88ced6631dac976bee92f466fb49737ab4daf2cd88927ce9e6f6)
and `donor-three-quarter-v001.png`. Exact prompts are adjacent
`*-prompt.txt`; acquisition receipts in `eye-donor-v001` and
`angle-donor-v001` hash all inspected render/clay/identity inputs. These are
source artwork, not screenshots of a repaired model. Framing is close but
not pixel-locked; explicit landmark registration was needed.

`export_head_donor_projection.py` uses the actual head-only camera fixture,
not the full-body face fixture in the shared exporter. `donor-projection-v001`
is front; `donor-angle-projection-v001` is40degrees. Both bind the exact
uv-v004 native authority and match the original render camera locations.
Perspective-correct pixel depth and bounded screen polygons control mapping;
landmark triangles are checked against folding. Shared mapping code unchanged.

`texture/eye-donor-v001` maps only two eye bands from the frontal AI artwork.
BaseColor SHA bd79a0c05432d23b1042c2a771fd724c252a3c3d0681695064674e4f065e7668.
96,168 changed texels; all outside support/unused gutters identical to the
uv-v004 retained multiview baseline. Cleaner individual irises survive native
front/angled renders. **Preferred partial eye diagnostic only**: a small
angled inner-corner mark, pale temple bands and broader skin defects remain.
`inner-eye-visibility.json` traces five actual angled pixels to front UV/depth:
four probes front-visible, one occluded. This is not an occlusion-only failure.

`texture/angle-donor-v001` adds a near-eye and temple/cheek transfer from the
new40degree artwork. BaseColor SHA b47fcfd6eb52aa414ce4f9cabfce1512d33b3d0566bddfb9a94c0a91c28108c0.
Native SHA956876c011a370b881d7bb7c3c65d0f6a205b0badf90737ac7f2f8ad9929a04a.
553,619 changed texels, exterior bit-identical. Much of the blank near-side
cheek/temple improves, but a pale wedge above the brow remains; the opposite
temple is untouched. The angled eye transfer introduces a small upper-iris/lid
mark in the front view. **Reject the combined angled map for promotion.**
Do not discard its useful source artwork or claim the temple was fully fixed.

Both bindings reopen with exact geometry, UV and custom normals unchanged.
All16 new native lit/unlit frames were inspected. A premature binding command
ran while mapping was still active and failed before creating output; its
failure receipt is retained. Binding succeeded after mapping exited0. No
Hunyuan inference retry, model installation, body/rig/UE change or stopped app.
Full verify.ps1 passed; current head ledger audit passes with unwrap/texture
still pending. Body FBX remains SHA d92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3.

Verdict: `texture/donor-appearance-review-v001.json`.
Panel: `work/sunset-workshop/evidence/ayric-face-donor-review-v001.html`,81
hash-verified artifacts, including exact AI prompts and actual3D views.
Next is a coverage-complete, landmark-registered coherent skin mapping plan,
not more accumulating small paint patches or a repeat of the crashed painter.
Opposite-view coverage and remaining skin/neck/mouth defects must be resolved
before texture approval. All assembly, body-lighting, rig and cooked-demo
requirements remain active. The full goal is not complete.

### 2026-09-05 — Coherent face mapping and exact visibility repair

Preferred working head texture: `work/sunset-ayric-rigid-head-v1/texture/coherent-skin-v003`.
BaseColor SHA c2392c736b068353f1206a2a8cf94f889e8c7b0c84a829ade5fe03f903311baf.
Native binding SHA e9800aaaf85893d29271ab1600b70d41b32f2bdcc0586e8f315eac23e3919a6b.
Exact uv-v004 geometry, UVs and custom normals unchanged. Not texture-approved.

One built-in ImageGen edit adds `texture/donor-opposite-v001.png` from the actual
-40degree albedo/clay fixture plus the two retained artwork donors. Exact prompt
and acquisition receipt are adjacent. Source camera fixtures v001 underlit and
v002 overexposed clay are retained; calibrated v003 alone conditioned this call.
Artwork is not pixel-locked:15 landmarks are traced to canonical source surface
triangles and projected into all cameras before piecewise donor registration.
All three views blend simultaneously in linear color rather than accumulating
small eye/temple patches. The large pale cheek bands disappear, and eyes remain
coherent in actual frontal and both three-quarter views.

`map_coherent_skin_v001.py` exposed nearest-pixel depth self-occlusion on steep
surfaces: striped old/new color behind ears and neck. New job-local
`exact_projected_visibility.py` uses spatially binned exact projected-triangle
intersection at each subpixel. `test_exact_projection_visibility.py` preserves
the500-sample seeded repro: nearest depth61/500 versus exact500/500 visible,
with foreground occlusion control passing. v002 changes visibility only and
removes stripes in actual renders. v003 additionally feathers grazing confidence
at cosine0.20-0.60 and excludes edge-connected neutral donor background.
No source artwork repainted by these validity mattes. Selected5281878texels;
outside support and unused gutters bit-identical. All36 candidate lit/unlit
frames inspected, six directions per candidate. No further renders pending.

The rear view still has conspicuous gray hair/neck coloration; v003 is the
preferred working face, not a complete360-degree texture. Existing static_prop
gate fails correlation+0.36124097915777215 against0.35. Mechanical metrics are
under `texture/metrics-v001`; density uses provisional0.33m head height and must
be rerun after fitting. Raster union island count is not native island count229.
Do not relax the threshold or mask this failure with a best-angle review.

Verdict: `texture/coherent-appearance-review-v001.json`.
Panel: `work/sunset-workshop/evidence/ayric-coherent-face-review-v001.html`,128
hash-verified artifacts. Opening requested through Codex returned queued, not
proof it is visible. Previous panels/candidates preserved. Head audit passes;
texture/unwrap remain pending. Full verify.ps1 passed this turn. Body FBX was
rehashed unchanged at d92f23c31a7eff73f00817c2ad50d02ce4f9d30723dd509f376c5e208221bfe3.
No shared pipeline changes this turn; all new drivers isolated in the head job.
No local GPU inference retry, new installation, killed app, rig or UE mutation.

Next unresolved gate: rear hair/neck image-conditioned artwork coverage and
lighting-versus-material-color diagnosis, retaining the coherent face sources.
Then full-view texture verification at fitted size. Assembly, body lighting,
rigging, sword attachment, scene polish and cooked runtime remain outstanding.
Full goal remains active, with concrete face progress and no genuine blocker.

### 2026-09-05 — Rigid-head texture accepted and FBX packaged

Previous goal turn was progress; this turn clears the head texture gate.
`work/sunset-ayric-rigid-head-v1/prod-texture-v001` is the accepted component
texture payload, **not** an assembled or UE-imported character.
FBX SHA2eba3696943ffc5754ccebd04d3ed074aa039dcae25aad87400f02d1320c207d.
Source BaseColor `texture/hair-bilateral-v002/BaseColor.png` SHA
1b44e5d6dbcf00936d90fe1c313fbee90fc66c9fbafff3bce56d33f2e1866cbf.
Native binding SHA6227a4a1bcc22c82dce3643406dc2ee3a4d5340f5003862e709adebe67cf0ef0.

One built-in ImageGen edit: `texture/donor-rear-v001.png`, prompt and acquisition
receipt adjacent. Inputs were actual rear albedo/clay plus retained opposite
artwork. Original generated output preserved. `prepare_rear_donor_v001.py`
exports exact180degree correspondence from coherent-skin-v003; no mesh edits.
`map_rear_donor_v001.py` registers silhouette anchors and uses exact subpixel
visibility to map806007rear scalp/nape texels. It removes the gray rear patch
and changes the diagnostic lighting correlation from+0.36124 to-0.26222,
passing the original static_prop0.35limit without a waiver.

Retained angle/opposite source artwork then supplies the blank side-hair areas.
`map_side_hair_v001.py` retains left-only intermediate and combined v001. Combined
v001 is rejected for a copied skin crescent above the near ear. v002 restricts
donor and target domains to hair above the ear, retaining a short-hair fade.
v002 is the preferred accepted component texture; all12native views inspected.
Source UVv004 geometry, UVs and custom normals remain exactly unchanged.
Rear-only six albedo views and all12combined v001 frames were inspected as
diagnostics; no claim that all rear-only beauty frames were reviewed.

Read-only existing body FBX cross-sections are in
`texture/head-fit-measurement-v001.json`: body1.85m, upper head about1.61-1.85m.
Adopted0.33m head plus short neck, with intended lower neck inset in high collar.
Actual assembled placement remains required. `package_character_texture.py`
stages4KPNG/maps, neutralAO and exports unchanged19,988triangles/10,020source
vertices. Similarity-transform maximum error2.94e-8m. Exported gate passes
-0.2526853229014294, density2697.2texels/cm2. No profile edits or waiver.
Native UV island count remains229; raster union count1 is not native topology.
Eight exported FBX beauty/albedo directions inspected in addition to native12.
Packager albedo frames retain calibrated exposure-1.5; native unlit comparison
uses Standard0. Do not mix these exposure groups as a color regression metric.

`record_head_texture_v001.py` records separate unwrap_and_bake and then
texture_approval, each audited. Texture authorization quotes current explicit
user delegation and scopes only this head component. Mechanical checks unwaived.
Strict frontal render equality initially failed before ledger mutation:94 of
133225ROI pixels differ by only1code value, MAE0.0001764. Receipt retained at
`texture/face-roi-check-v001.json`; subsequent local check permits at most1code
level. Do not falsely claim bit-identical rendered pixels. There is no visible
facial feature regression. Source and body authorities remain untouched.

Panel: `work/sunset-workshop/evidence/ayric-head-texture-review-v002.html`,133
hash-verified artifacts, built by `build_head_texture_review_v001.py`.
Open request returned queued, not verified visible. Prior panels preserved.
Full167tests passed this turn; head ledger audit passes after both new gates.
All launched mapping/render/package processes are terminal; no local AI
inference retried, no installed models changed, no interactive process killed.

Next: body material remains failed at-0.2378495670706998 versus absolute0.12;
do not apply the rigid-head static profile to the body or revive rejected
IntrinsicAnything orbits. The new head is ready for component UE import, but
final custom body texture, collar fit/old-head removal, rig/deformation,
head-bone attachment, independent diagonal sword, full workshop polish and
cooked gameplay proof are still outstanding. Full goal stays active; no blocker.

### 2026-09-05 — Head native UE review passed; body luminance canary retained

This goal turn made concrete component progress; full demo remains active.
No shared pipeline source edits, installations, local inference reruns or
accepted body/head/prop authority mutations. All work drivers are job-local.
Initial verify.ps1 passed167tests and RAC_VERIFY_OK this turn.

Body read-only fixed physical sections in
`work/sunset-ayric-v2/texture/modular-body-diagnostic-v001.json` show that
removing the old head does not resolve the lighting failure. Below-head
correlation-0.24840; torso/arms-0.28455; legs-0.28585. These are not gate masks.

One built-in ImageGen edit of the actual front unlit body render:
`texture/imagegen-light-front-v001.png`,1254square, exact prompt adjacent.
Original generated file exec-b68e1a58-7970-49b1-b689-a54e6c15ef27.png retained.
`map_imagegen_light_front_v001.py` uses fixed normalized registration
(silhouetteIoU0.940865), exact projected visibility and only low-frequency
scalar linear-RGB gains. No AI replacement face, hues, seams, geometry or UV.
Output `texture/imagegen-light-front-transfer-v001/BaseColor.png` SHA
54a36dbd4c3730963dc3c14be7e7a241f62e896c68b23c20eac3d5f154fbaf2a.
2,851,469supported texels; protected head/collar and outside support/gutters
remain byte-identical. Original body FBX/base unchanged.

Twelve paired actual-FBX CPU renders retained. Inspected front/oblique albedo,
back albedo and front beauty: inadequate delighting, original side
fragmentation remains. Correlation-0.2444257550 is worse than original
-0.2378495671 and still fails absolute0.12. `review.json` rejects production
use; no body gate advanced. Do not commission five additional donors on this
canary or tune settings to the score. Panel:
`work/sunset-workshop/evidence/body-lighting-canary-v001.html` and JSON.

Independently published the accepted rigid head through
`work/sunset-ayric-rigid-head-v1/publish_head_v001.py`, with collision and static
validation recorded in separate audited calls. No fabricated older out/
authority: manifest points directly to the accepted prod-texture-v001 FBX.
First publication hit a local str-versus-Path hash call after staging three
files, before manifest/ledger write. Corrected it and explicitly resumed only
after checking existing FBX/BaseColor hashes and exact ORM channel bytes;
no staged file overwritten. Native publication is
`out/sunset-ayric-rigid-head-v1-production`, manifest SHA
983f86092c6f5a64903379d9215cb76fada39601b0ac86a9a6f48a94aad9d1ee.
Accepted FBX remains2eba3696943ffc5754ccebd04d3ed074aa039dcae25aad87400f02d1320c207d.

Narrow RAC_ASSET_IDS import in UE5.8.2 passed all seven checks. Reports/logs:
`evidence/head-import-v001.json/.log`; immutable
`validation/ue5-import.json`. Mesh:
`/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production`.
Native LOD vertices12740/7134/3507, tris19988/9994/4996, one section each,
height33cm. Collision disabled for eventual head-bone attachment.

`review_head_ue_v001.py` created only a separate inspection level. Its added
fill washed colors out and its initial front/back labels reversed UE-facing.
Read-only `evidence/export-uv-audit-v001.json` confirms one correct paint UV
channel, so do not claim a UV binding bug. v001 captured8frames but failed its
async finish because Unreal removes __file__; it never produced review.json.
The fixture was saved before that error. CloseMainWindow on the exact owned
helper returned false; final inventory confirmed it remained alive. After
verifying PID48888's exact v001 command and the saved nonempty fixture map,
only that stranded helper was stopped. No user-opened app was terminated.
Original8frames/log/driver
are frozen in `evidence/retained-fixture-v001.json` as rejected evidence.

v002 derives the retained driver with explicit callback paths, actor yaw180,
no added fill and two named albedo-only material overrides on the fixture.
It completed normally and quit. Ten1920x1080 actual engine frames:6LOD0
directions, frontLOD1/2, front/back albedo controls. All inspected. Brown hair,
face/stubble and side/rear coverage coherent; no atlas, mesh, UV or imported
material edits were needed. Rear ordinary lighting is shadowed; unlit control
proves actual rear paint. LOD2 nose faceting at forced portrait scale is
explicitly distance-only screen0.15, not the close-up model.

`record_head_runtime_v002.py` records scoped delegated static appearance
approval; validation/ue5-runtime-review.json and delegated receipt are immutable.
Workspace audit passes; production_ready=false and cook remains pending.
Current panel `work/sunset-workshop/evidence/ayric-head-ue-review-v002.html`
has23hash-bound artifacts, source/rejection links and honest scope. Open request
returned queued, not proof it is currently visible. Both review maps are copies;
live L_WorkshopPreview_v004 and prior panels remain unchanged.

Next: leave the resolved head artwork alone. Body material still needs a new
explained repair route; no acceptance waiver. Then collar fit/old-head removal,
rig/deformation, head-bone and separate diagonal sword attachment, remaining
scene dressing and cooked gameplay. The head and sword have independent native
appearance proof; the custom assembled avatar still does not. No genuine
blocker or full-goal completion is claimed.

### 2026-09-05 — Latest user correction: face texture needs work

Direct user feedback reopens the face artistic review, superseding the earlier
"leave the resolved head artwork alone" direction. Everything else is to stay
untouched by this face repair; praise does not waive unresolved mechanical or
cooked-runtime checks. Historical authority files and delegated receipts are
preserved, with an additive hold in
`work/sunset-ayric-rigid-head-v1/evidence/user-face-revision-v003.json`.

Current UE albedo-front and three-quarter evidence was inspected against the
head reference. Skin/stubble look too photographic for the illustrated target;
warm engine lighting also obscures facial definition. Next: a separate,
reference-conditioned face-only mapping revision with cleaner painted detail
and aligned eyes/brows/mouth, reviewed from front, oblique and both sides in
unlit and lit actual-mesh views, then in UE. Preserve geometry, UVs, hair and
all non-face work. No new replacement texture generated in this feedback pass;
no inference launched, no app closed, no native payload or ledger rewritten.

### 2026-09-05 — HARD PIVOT: park Ayric, finish the Manny workshop

The latest user explicitly stopped character work after the overnight head
effort: "Let's just stop there and move on. I'll keep at it later. I want to
finish this demo off. Do everything else, then create the scene and show me
with the Manny instead." This supersedes custom-character completion for the
current demo. Do NOT resume head/body/rig work or treat those holds as demo
blockers. Updated SUNSET_DEMO_COMPLETION.md records the narrowed character
scope without dropping the remaining workshop work.

Before that pivot, three built-in cel-face donors and their prompts were saved
under `work/sunset-ayric-rigid-head-v1/texture/cel-face-donors-v001` and bound by
`bind_cel_donors_v001.py`. Their local landmark drift was mostly0-2px (front
max3px) and measured, not used to warp. Prepared map_cel_face_v001.py,
bind_cel_face_v001.py and render_cel_face_v001.py were NOT executed. No head
job remains active; all prior authorities and unfinished body artwork survive.

Concrete scene progress after pivot:

- Three reference-conditioned built-in scene images: masked RGBA ivy,
  engineering display, kilim rug, under `work/sunset-workshop/art/polish-v001`.
  lineage.json binds exact prompts, reference, original output and copied files.
  Ivy has60.18% zero alpha; used as honest layered architectural foliage cards,
  not substituted for the held 3D potted plant.
- `build_polish_v001.py` created L_WorkshopDemo_v001 from previewv004 with
  separate added tools/crates, shelves, rug,9ivy cards,2displays, architectural
  trim, lighting and reframed vista. Actual capture revealed wall shader
  failure: ComponentMask's input is unnamed, not "Input". Retain v001 as
  rejected; no source map or approved mesh overwritten.
- `build_polish_v002.py` checks every material connection and fixes that pin;
  it creates separate `/Game/SunsetWorkshop/L_WorkshopDemo_v002` and DemoV002
  materials. All four actual engine views inspected in evidence/demo-v002-review.
  No material-compile failure; map check0errors/0warnings. Scene is improved
  but still needs sofa/potted plant and final composition/lighting work.
- Windows BuildCookRun completed exit0 in56seconds. Exact package log retained
  as `evidence/demo-v002-package.log`; archive
  `output/sunset-workshop-demo-v002/Windows`,50files,1,040,835,859bytes. Staging
  is isolated at `work/sunset-workshop/staged-v002`. Normal UE cook rebuilt its
  generated Saved/Cooked cache; original content and older staged build survive.
- `scripts/play_workshop_demo.ps1` launches the package with explicit demo map,
  avoiding the unchanged project's default gallery map. README and scene docs
  updated. Current review panel `evidence/manny-demo-review-v002.html/json`
  includes package hashes, exact art prompts, four actual editor frames and
  honest incomplete status. This is not claimed cooked movement proof.

Live handoff: packaged UnrealGame.exe PID49044, bootstrap RacValidate.exe
PID27736, opened via launcher. A Windows Security firewall permission dialog
is covering it. Computer-use skill forbids handling security UI; no Allow,
Cancel, or other input was sent. User was asked to choose Cancel (local play
does not require network access). Leave game open. Do not restart or terminate
it based on this UI pause. Revalidate processes/window on resume. Native window
id26936400 was returned for the package, but refresh rather than assuming it
persists. Runtime log `evidence/demo-play-20260905-061649-553.log` is live.

Next: once the user dismisses the security prompt, verify actual Manny input,
jump and collision, capture packaged gameplay, then finish sofa/plant and
remaining scene polish/back sword carry. All self-closing editor helpers have
finished; no local AI inference launched. Prior verification167tests passed;
new job-local scripts compile/run, git diff --check passes. Goal remains active;
the security UI pause is new, not a repeated blocker and not completion.

### 2026-09-05 — Manny/sword gameplay verified; real-depth exterior required

Latest user feedback: the window still looks like a painting. Do not finalize
with the old panorama or replace it with another flat landscape. Required:
reference-conditioned rock meshes at separate depths, horizontal mapped ground,
distant sky and camera-position/parallax proof. SUNSET_DEMO_COMPLETION.md records
this additive requirement. Custom Ayric work stays parked.

Best saved scene is `/Game/SunsetWorkshop/L_WorkshopDemo_v005`, with
`MannyDemo/BP_WorkshopManny_v007` and `BP_WorkshopGameMode_v005`. Important
correction: the original ThirdPerson template actually used SKM_Quinn_Simple.
The new derivative explicitly uses SKM_Manny_Simple; the old template survives.
Sword component WorkshopBackSword is independently attached to spine_03.
The editor-only bridge (now `integrations/ue5/RacEditorBridge`) uses supported C++ SCS
access to persist its attachment socket; strict UE5.8 plugin build succeeded.
Project-local built bridge is work/ue5-validate/Plugins/RacEditorBridge.

Actual PIE evidence `work/sunset-workshop/evidence/manny-demo-v005-play/` has
idle/walking/jumping/window frames and review.json: all13 checks pass, including
actual Manny identity, possession, floor spawn, movement, east-wall collision,
jump/landing and zero sampled sword attachment error. These are PIE checks,
not physical keyboard or cooked-runtime proof. v004 sword was edge-on/floating;
v005 corrects its broadside and diagonal from actual gameplay inspection.
The earlier review callback could re-enter during screenshots; v005 uses a
busy guard and produced four distinct frames. Do not repeat the socket UI
popup approach: input dismissed the popup rather than selecting its entry.

v005 includes v003 corridor roof/door trim, matte chalkboard, reduced task-light
glare and a mapped repair-bench display. Old v002 packaged processes closed
cleanly; no firewall dialog is known to remain. All our editor helpers finished.
The launcher/README/panel still point at the older v002 package; update them
only after a newly verified package, and correct the old Manny/Quinn labeling.

Exterior job: `work/sunset-vista-rock-v1`. Built-in ImageGen directly conditioned
on the original workshop isolated a sandstone formation. Exact image/prompt:
`work/sunset-workshop/art/exterior-v001/rock-reference.png`, rock-prompt.txt.
Reference SHA35aa106a5871ae071c56cc36be22910313da6c009ac5a60c7670f6fafc82e383;
reference-lineage.json retains original source and derivation. One guarded
Hunyuan single-view seed42 attempt succeeded (1693278 raw faces); four normalized
clay views inspected and delegated modeling accepted. Native semantic cleanup
preserved the source; voxel/QEM runtime topology is the next independent gate.
`run_stage.py` wraps the existing operator at one stage per invocation and
never retries geometry. No exterior has yet been placed or proven in UE.

New ground texture/prompt also saved in art/exterior-v001/ground.png and
ground-prompt.txt; built-in image output exec-582260e5-e632-4134-82b3-9def991342f0.
Ground SHA52c5c94ccfc7a2005925388b72df43b1b88bba85def0df0411a69f97a8d01374.
This is a horizontal material input, not a replacement landscape painting.

Sofa remains held. This turn's bounded built-in atlas edit in
work/sunset-sofa/texture/intrinsic-review-v001 was rejected: correlation+.72,
density14.2px/m and mapped gray seam bands. Original prod-v3 is untouched.
Do not repeat whole-atlas editing. Potted plant topology remains held at v010
(9 boundary/nonmanifold edges). No gates waived. Latest verify run167tests pass;
new editor bridge build and v005 gameplay pass. Full demo/cook remains unfinished.

### 2026-09-05 continuation: real exterior depth accepted in editor, v008

Latest scene is `/Game/SunsetWorkshop/L_WorkshopDemo_v008`, preserving v005
Manny/sword. The old flat landscape actor is absent. Five real instances of the
image-conditioned rock mesh sit at different distances, above horizontal mapped
ground, with UE atmosphere/fog and a distant Engine sphere carrying AI-generated
reference-conditioned planetary mapping. The sphere is not AI-generated geometry.
Paired actual UE cameras are 220 cm apart. Their captures show changing rock
overlap; analytical projection gives about 13x more movement for the nearest
versus farthest rock. This is real camera/geometry parallax, not image warping.
v006 dark lighting is retained rejected; v007 lighting improved, v008 composition
is the current accepted editor appearance. All three v008 captures were inspected.
`evidence/exterior-depth-review-v001.html` and matching JSON bind these frames,
source hashes, exact image prompts, and explicit not-cooked/not-complete labels.
Browser panel was opened; automated local-file browser inspection is policy-blocked.

`work/sunset-vista-rock-v1` now passes through delegated static UE multiview
review. Source topology is 8996 vertices/18000 triangles, closed manifold.
Texture uses a reference-conditioned 1254px repeating ground/stone tile over
0.8 m UV repeats, not Hunyuan Paint. New optional repeat-address sampling in
gate_texture preserves all thresholds and defaults to legacy clamp. Actual gate:
correlation +0.031439, density 245.9 texels/cm2 at authoritative scale; fragmentation
1199 islands remains advisory. Larger scene instances reduce world-space density.
v1 material packaging failure (zero slots) retained; v2 adds one material slot
without changing vertices/faces/UVs. First native UE import exceeded the 15k vertex
ceiling because of UV splits (16313); retained `validation/import-failed-v001.json`.
A separate native derivative passes at 14499 vertices/14400 triangles:
`/Game/SunsetWorkshop/Optimized/sunset-vista-rock-v1-production-native-v001`.
Original FBX/native asset and failed evidence remain unchanged. All four actual
native UE front/three-quarter/side/back frames were inspected, then recorded in
`validation/ue5-runtime-review.json` with explicit delegated-not-human and
editor-only scope. No collision or cook approval inferred from these images.

Latest pipeline verification: 171 tests pass, routing passes, diff check passes.
v008 Manny PIE regression has been launched using review_manny_demo_v008.py;
check `evidence/manny-demo-v008-play/review.json` before claiming its result.
The launcher still targets the old v002 cooked package (Quinn), not this scene.
Sofa and potted plant holds above remain; custom head remains parked.

### v008 package and live handoff, 08:00 local

v008 PIE regression passed all 13 checks; actual idle/window captures were
inspected. All sampled sword attachment errors are 0 cm. Native rock static
review is recorded; its cook ledger remains pending (do not infer approval).
Fresh BuildCookRun succeeded in 55 s, 0 errors/0 warnings. Separate archive
`output/sunset-workshop-demo-v008/Windows` contains 48 files, 1048623348 bytes.
Preserved package and cook logs under evidence/demo-v008-{package,cook}.log.
`demo-v008-package-load.json` binds archive executable/container hashes and
the clean package result; it explicitly does NOT certify physical input or
visually reviewed cooked parallax. The live runtime log confirms the exact
v008 map and BP_WorkshopGameMode_v005 loaded successfully.

Launcher now targets v008. It was run for the user's requested walkaround;
RacValidate.exe PID21072 was alive at last check, log
`evidence/demo-play-20260905-080022-027.log`. Preserve this interactive game.
No security prompts were interacted with. Native UI automation is unavailable
through the current CUA surface; do not work around it with OS input injection.
New immutable review snapshot is exterior-depth-review-v002.html/json,
updated for v008 PIE/package/load truth. Remaining: cooked physical-input and
parallax visual review, sofa/plant holds and any final scene polish. Do not
restart the custom head, claim full completion, or close the user's game.

### 2026-09-05 plant progress and placement feedback pivot

Previous goal turn was progress: v008 build/package/load. Current resume verified
171 tests/routing pass, C free318GB, RTX4090 free21782MiB and live v008 game
PID21072 (preserved). No inference launched. Plant topology work created retained
CPU downstream derivatives, with brief standard Blender fixed-view renders:
- surface-relax-v011 source loader failed because cleanup object is geometry_0,
  not GEO_RAC_. v012 repaired only loading; tangential pot relaxation then failed
  visual review with lip dents (face order/foliage unchanged). Do not tune it.
- regional-quad-pot-v013/v014 QuadriFlow preparation refused a closed pot.
  v014/diagnostic.json proved zero nonmanifold vertices/edges and consistent
  winding. Blender source checks per-axis edge coordinates against1e-4 too:
  https://github.com/blender/blender/blob/main/source/blender/editors/object/object_remesh.cc#L630
- v015 preparation found27 micro-edges; dissolve_degenerate distance.00018
  removed them without opening the surface. QuadriFlow then succeeded at2235
  pot vertices/4466triangles; combined with retained foliage19014triangles.
- v016 direct root-ring stitching refused unmatched loops, retained rejection.
- regional-union-v017 exact same-source region union succeeded at9669vertices,
  19450triangles, zero boundary/nonmanifold edges. Actual four clay views were
  inspected; pot shading and root overlap improve substantially. Some foliage
  underside simplification remains. This is a candidate, not a promoted topology
  receipt; work paused for the user's new scene-placement correction. Original
  dense/source and all rejected trials remain. No plant texture inference ran.

User supplied actual packaged screenshots showing floating rock skirts and a
tilted rug; requests lowering rocks, better matte rock texture, and a full object
placement re-audit. Moon explicitly loved: preserve unchanged. Read-only
placement-audit-v009.json enumerated all native actor bounds/supports. Rug's
rotation tuple used roll=-8, not yaw=-8: its corners span-13.41..15.81cm around
nominalZ1.2. Rocks' minimum bounds touched ground but their irregular skirts did
not; pivot equality is insufficient contact evidence.

New saved derivative L_WorkshopDemo_v009, ground_scene_v009.py:
- rug flat yaw-8, pitch/roll0, Z.18cm, no card cast shadow;
- each rock skirt buried6% of actual instance height below groundZ-400;
- separate scene-only M_MatteSandstone + per-instance materials: existing
  reference-conditioned tile, specular0/roughness1/metallic0, contrast1.15,
  NormalFromHeightmap relief2, scale-compensated physical repeat~.571m;
- table items support+0.05cm, shelf items corrected to measured shelf tops;
  floor props and stacked crate supports already had correct bounds;
- moon and Manny unchanged, native mesh/material authority untouched.
Build log has no Python/material compile errors. rock-material-probe-v009.log
failed only on nonexistent get_transient_package; corrected read-only transient
probe succeeded with input socket names in rock-material-probe-v009.json and
v010.log. Do not repeat that unsupported API.

review_grounding_v009.py is capturing7 actual UE frames into exterior-v009-review:
paired window positions, wide room, downward rock contact, low rug contact,
table props, shelf props. Check its live UnrealEditor PID/log and final review.json;
do not claim visual acceptance until all relevant images are inspected. Current
user's running package remainsv008; v009 not cooked or launched yet.

### Latest user correction at 08:40: mountain appearance is lighting, defer it

User walked over to the mountains and clarified that their apparent floating
was lighting. Explicitly says no need to fix that now; perform lighting and
atmosphere in the final post-composition pass. Stop further mountain lowering.
Preserve the liked moon. Current open v008 game and launcher remain unchanged.
v009/v010 lowering/material trials are unpromoted experiments, not an accepted
placement requirement. When merging the genuine interior fixes into the next
scene, retain/restore the v008 mountain transforms unless a later final visual
composition judgment specifically changes them. Do not require burial merely
to satisfy the superseded floating diagnosis.

Actual v009 rug/table/shelf views were inspected: rug flat and supported; props
seated. v010 lowered rocks from6% to12% buried height and captured four actual
views; all viewed, then a separate v010 package succeeded in67s. Package retained
at output/sunset-workshop-demo-v010, log evidence/demo-v010-package.log. It was
NOT launched and launcher was NOT advanced. Those experiments remain separate.

Wide audit also found real stretched wall mapping on perpendicular corridor
box faces. fix_wall_projection_v011.py attempts normal-aware XYZ projection
using the existing reference-conditioned wall texture (front face mappings and
220cm scale preserved). v011 failed at Abs named Input pin; v012 fixed that
unary connection but failed at ComponentMask's named Input pin. No completed
wall repair has been saved or claimed. Both failed map copies merely retain
v010 template geometry. v011 review ran on that unchanged template; its captures
are explicitly rejected as proof of a repair in surface-v011-rejection.json.
Next safe implementation step: bind unary expressions through their actual
single/unnamed socket, using get_material_expression_input_names introspection,
and test connections before creating/promoting another scene. Do not repeat
named Input guesses. Source scripts, old maps, failed logs are retained.

At the latest read-only process check no UnrealEditor helper remained running.
The v008 user game was preserved. No generation/inference job is active from this
turn. Plant regional-union-v017 remains a reviewed but unpromoted topology
candidate; sofa hold persists. Custom character stays parked. Goal unfinished.

### 2026-09-05 interior repair v013, exterior correction honored

Latest process checks found no user game or creative app running before the
new helper. No user process was stopped or relaunched. GPU free22321MiB at that
check; no inference used. The v008 archive/launcher remain unchanged.

probe_wall_inputs_v013.py inspected actual UE sockets on transient expressions:
Abs and ComponentMask both report a single unnamed None socket. Explicit empty
input names connect successfully. fix_interior_v013.py preflights those links
before creating persistent assets, then builds the complete material and a new
L_WorkshopDemo_v013 directly from v008 (NOT the lowered v009/v010 experiments).
Original mountain transforms/materials, moon, exterior lighting and Manny are
retained. Only flat rug yaw/Z, measured table/shelf support contacts and modular
wall/ceiling material projections change. Native AI assets remain untouched.

New SurfaceV013/M_WallAllFaces selects XYZ planar samples by absolute vertex
normal, keeping the existing reference-conditioned wall texture, 220cm scale
and tint. Build succeeded with no Python/material errors. Evidence:
interior-v013-build.json/.log and wall-inputs-v013.json/.log.

review_interior_v013.py completed five actual 1600x900 UE frames in
evidence/exterior-v013-review: room, corridor, rug-contact, table-props,
shelf-props. Every image was inspected. The rug is flat, props seated, and
the corridor shows full panel art rather than collapsed stripes. Recorded
hash-bound codex-only editor visual acceptance in interior-v013-visual-review.json
using record_interior_review_v013.py. Capture report error=null; no compile
errors in interior-v013-review.log. Helper PID36888 exited normally. This is
an interior repair approval, NOT a cooked/runtime or final-lighting approval.
The cyan shelf spill, exposure balance and exterior shadows/atmosphere remain
for the final composition pass as the user requested. No v013 cook was run.

New source scripts pass py_compile; git diff --check passes (line-ending
warnings only). Full 171-test/routing pass earlier in this same goal turn remains
applicable; no compiler library changes here. Plant v017 four clay views and
dense side/three-quarter were inspected again: same foliage silhouette, smoother
pot than old QEM, but underside simplification remains visible. No new plant
approval or texture job was issued. Sofa hold and final demo requirements remain.

### 2026-09-05 plant texture progress, sofa rejection, native material correction

User correction remains authoritative: leave mountains at v008 transforms;
final lighting/shadows/atmosphere pass comes after composition, preserve moon.
Working interior derivative remains v013 directly from v008. Launcher/archive
remain v008; no new scene cook, game launch, mountain movement or character work.

Plant regional-union-v017 topology is now delegated-codex accepted via
approve_topology_v017.py and its immutable receipt:9669verts19450tris, closed,
source blend8c4056cd5fb4556245794435adf0c9aa41799aa849a6cb81951f9ce2b5f95edd.
Fine foliage underside simplification is disclosed. One six-view512 Hunyuan
Paint attempt is retained at texture/multiview-paint-v001/paint, with separate
diagnostics. Geometry/UV validation passed but process shutdown exited
-1073741819; execution receipt retained, no automatic retry. Full4096 buffers
recovered without upscaling. UV-single-material-v002 changes slot binding only.
prod-multiview-v001 slot failure and v002 green interior spill/plastic gloss
are explicitly rejected. Reference-conditioned ImageGen soil tile is stored at
texture/soil-mapping-v003/soil.png with prompt.txt; map_soil_v003.py bakes it
only onto existing interior faces, preserving geometry/primary UVs. Constant
roughness.82/metallic0 are authored data, not inferred AI PBR channels.

Plant prod-multiview-v003 passed texture gates: correlation+.174095,
density587.9texels/cm2;1100UV islands remains an advisory/native split risk.
All four lit/unlit and elevated/top soil views inspected; delegated texture
approval and promotion completed. Published out/sunset-plant-production manifest
SHA91358479463b525ff6078756d7d4713c618bc297711d854f7ce62f71c08e0824.
Original native import exceeded vertices(17167/19450tris); retained report.
reduce_native_v001.py saved independent native-v001 at14850verts15560tris,
LOD1 7450/6224,LOD2 4206/3112. Native-v001 import receipt passed and remains
the ledger binding. Its actual native views revealed an unwanted bumpy/grid
normal and must NOT receive runtime visual approval.

probe_native_material_v002.py exported actual Engine DefaultNormal to
validation/material-probe-v002/default-normal.png: noisy tiled-wall relief!
scripts/ue5/import_asset.py now creates versioned master
M_RAC_CharacterMaster_v002 with HasNormal scalar:0 uses explicit(0,0,1),1 uses
authored normal. Old master/instances unchanged. fix_native_normal_v002.py saved
/Game/SunsetWorkshop/Optimized/sunset-plant-production-native-v002, same reduced
geometry with new PlantSurfaceV002/M_SunsetPlant_Production. Native-v002.json
mechanical checks pass, same counts; editor helper exited cleanly. Attempted
--native-revision material-v002 did NOT advance ledger: existing schema supports
same-material LOD reduction only, not changed material. Do not force that gate.

review_native_v002.py intentionally emits diagnostic candidate schema, not an
import-bound runtime receipt. Four actual1600x900 captures are in
validation/native-review-v002, error=null; all viewed. Unsolicited normal relief
is removed. Three-quarter/side/back show terracotta detail, soil and foliage;
first front frame lacks fine albedo detail visible later, requiring warm-up or
streaming diagnosis before final visual acceptance. normal-fallback-review-v002
records narrow diagnostic findings only; no plant scene placement/runtime/cook
approval yet. The original native-v001 remains intact and rejected visually.

Sofa: ImageGen de-lit reference stored in texture/delighted-reference-v002,
reference.png/prompt.txt/lineage.json; same approved sofa structure. One Paint
attempt texture/delighted-paint-v002 validates geometry/UV but has the same
retained shutdown error, not retried. Full4096 buffers recovered. Packaged
prod-delighted-v004 fails unchanged correlation threshold at+.60104; density
151.5 passes. Actual lit/unlit front/side/back and top/underside inspected:
arm/seat strip errors and side/back gradients persist. Rejection retained.
Underside is light brown, not black; do not pursue that unsupported explanation.
Sofa remains held. Do not repeat the same reference-only Paint route.

Recovery helper now accepts --stem and --diagnostics without changing defaults;
two tests cover named/separate outputs and path-stem refusal. Normal fallback
has two actual-builder graph tests. Latest full verify passes175tests+routing,
evidence/verify-20260905-neutral-normal.log. git diff --check passes apart from
line-ending warnings. All new editor/inference helpers exited; only preexisting
Blender MCP service processes remained at final check. No creative app stopped.
Next: warmed native plant review and explicit material-derivative lineage;
sofa mapping repair; merge accepted dressing into v013; final composition
lighting/atmosphere without mountain lowering; fresh cook/playable evidence.

## 2026-09-05 resumed demo completion: accepted sofa and native plant materials

The user asked why work stopped. It was a premature handoff, not an instruction
to pause. Continue to the complete Manny demo; custom Ayric work stays parked.

Sofa `prod-region-v009` now passes texture and four-view native visual review.
Reference-conditioned ImageGen leather is in
`work/sunset-sofa/texture/region-mapping-v005/leather.png`, exact `prompt.txt`
alongside it. Original AI geometry/UV authority is unchanged. V009 uses the new
leather plus retained AI ink and a color-selected pillow region. Accepted art
liberties: subdued teal pillow and leather-covered rear trim. V005/006 halo,
V007 obsolete Blender node error and V008 mask-threshold failure remain retained.
Texture correlation +.125763949; 151.5 texels/cm2. Native sofa LOD0 is
11725 vertices/18000 triangles; all four actual `native-review-v002` frames were
inspected. Published manifest hash
`5f816589dd7536f902ec635717feedb7a81d79f4eaeb70b00a1160472652bc75`.

Plant warmed `native-review-v003` frames pass all four views. Actual UE buffers
prove native-v001 and material-repaired native-v002 identical in all LOD vertex,
index, normal, UV and tangent streams, with unchanged BaseColor/ORM textures.
`validation/native-geometry-v003.json` and `native-material-v003.json` bind this
proof. New explicit native_material_rebind contract records import
`ue5-import-material-v003.json` and matched runtime review without changing the
old rejection. HasNormal=0 uses explicit neutral normal, not Engine DefaultNormal.
Eight new hermetic material-revision tests pass; full verify passes183tests and
routing (`evidence/verify-20260905-material-revisions.log`).

Scene v014 restores independent sofa/two plants and scoped neutral-normal
material instances from v013; mountains untouched. Its review rejects a window
pot outside the desk footprint and crate overlap with the sofa. V016 corrects
the pot and applies final lighting/matte sandstone; V015 failed only a guard
comparing pointer-bearing UE transform strings and was not promoted. V016's
numeric transform assertion proves rocks and moon unchanged. V017 moves
Crate_Storage_East to(360,140,0), proving clearance from the sofa. Actual full
composition review is in progress; do not claim a cooked final from these notes.

`integrations/ue5/RacDemoAudit` is an opt-in native runtime module under build
verification. It will prove programmatic movement and capture actual packaged
frames; it does not claim physical keyboard input or automatically grant any
asset production-ready gate. Official launcher still v008 until final verification.

## 2026-09-05 final delivery — Manny demo v018 complete

Final map `/Game/SunsetWorkshop/L_WorkshopDemo_v018`, SHA
`5698a91d255e54b4f2a6937fca7030c3528306207c7e6d0e9e77b6f7701a8c44`.
Scene inventory169static components. V018 moves only Plant_Window to
(400,-40,92.00140697), with all nine native tabletop-triangle support samples
passing. All six final editor views inspected. Mountains/planet remain at
v008 transforms; v016 lighting/material pass retained. Sofa and plant accepted
native visual receipts remain as above; no custom-character work resumed.

All13 actual v018 PIE checks pass, jump peak219.70cm from floor92.15cm and
sword error0cm. First package v018 cooked cleanly but failed module loading:
Blueprint-only stock game had not linked RacDemoAudit. Retained rejected.
Added explicit RacValidate Game/Editor targets and minimal primary module;
v018-r2 clean build/cook/archive59sec, zero cook errors/warnings. Actual packaged
audit then passes12checks with eight1600x900frames, all visually inspected.
Movement is engine-native programmatic input, not physical keyboard testing.
Audit exits itself normally. Normal launch has no audit flag and stays playable.

Final archive `output/sunset-workshop-demo-v018-r2/Windows`:48files,
1,131,307,068bytes. `evidence/final-demo-v018.json` hashes the entire package,
map, audit sources, logs and frames. Panel `evidence/final-demo-v018.html` uses
only actual cooked scene screenshots. Launcher updated to v018-r2/mapv018.
README, PIPELINE, SUNSET_WORKSHOP, completion contract and DECISIONS updated.
Latest full verify183tests+routing passes; no git commit/push or cleanup made.
Scene-demo completion does not silently mark gallery asset cook gates production
ready. Keep all old packages/authorities/rejections and the parked Ayric work.

## 2026-09-05 — atmospheric night and user-corrected dust: v026

Latest map `/Game/SunsetWorkshop/L_WorkshopNight_v026`, SHA
`9c6275ad0234c279939c2f8f942691a19e7bbed6410ab224c508356be2988e5c`.
Original daytime v018 map/package unchanged; all 169 original static actors
retain meshes/materials/collisions/transforms. One non-colliding Engine sky
sphere is added. Custom character work remains parked; Manny and sword retained.

User requested atmospheric night, stars, then explicitly rejected tall domed
dust. V026 uses very faint ground-weighted dust, zero radial density, local
UI falloff1200 (actual shader12), density0.5, centerZ=-280 over sandZ=-400.
Stock star-texture v023 was rejected; final stars use a direction-space shader
with horizon fade/exposure compensation, layered over SkyAtmosphere. No model
downloads, new bitmap, or AI geometry generation. See docs/SUNSET_NIGHT.md.

Final package `output/sunset-workshop-night-v026/Windows`:48files,
1,132,895,624bytes. Build/cook/archive83.3sec, zero cook errors/warnings.
Actual packaged run passes12programmatic checks and writes9frames, all inspected.
The optional RacDemoAuditSky flag adds a skylight view and ends at82game seconds;
default audit remains8views/73seconds, normal play inert. Source and installed
plugin hashes match45c40c992eba705a5276602e6c26e677237eb4d535cf14c754fc4881d0ef9101.
Physical-keyboard proof and human visual approval are not claimed.

`evidence/night-review-v026.json` binds package/map/logs/checks/images/source;
`evidence/night-review-v026.html` shows actual cooked frames, the retained day
comparison and the rejected tall-dust editor view. `night-v026-invariants.json`
proves identity; `night-v026-dust.json` records settings; the user's correction
and screenshot hash are in `night-dust-user-correction.json`. Fresh verification
183tests+routing passes (`verify-night-final.log`). Launcher defaults Night,
with explicit `-Lighting Day` retaining the old demo. The user's day game stayed
open; the separate night audit exited itself. No commit/push or cleanup.


### 2026-09-05 (Claude) — Ayric body textured, rigged, imported, and driving the workshop demo

Ayric asked for the character texture Codex could not finish, then for the
rigged Ayric to replace Manny in the workshop with the base UE5 locomotion.

**Texture.** Diagnosis: the body paint (6 views, 512 px, full-body scale) gave
the head about fifty pixels per view; every later face repair was a patch on
that. A head-detail paint pass was built and run twice on the body's own head
faces with their exact UVs (`texture/head-transport-v001`, paints
`hy3d21-head-v001` and `-v002`). v001 is rejected: the reference crop kept a
strip of gorget and the painter spread armour colour over the head. v002 painted
skin, hair, eyes and beard at ten times the resolution but the views disagreed
about where the face was on this shallow head; the bake has doubled eyes.
Rejected under the landmark rule; `rejection.json` in both folders, tooling
kept (`scripts/blender/extract_head_transport.py`, `scripts/composite_head_paint.py`).

The shipped candidate is `prod-calibrated-v001`: Codex's held `collar-pbr-v001`
artwork (illustrated face v006, neck/nape/collar repairs) with region-bounded
scalar calibration only: head and neck metallic to 0 and roughness floor 0.55
(`texture/skin-hair-pbr-v001`), everything else roughness floor 0.40
(`texture/armor-pbr-v001`; the painter's median 0.25 at metallic 0.9 rendered
as mirror chrome). Base colour is byte-identical to collar-v001. Fixed views and
face close-ups are in `prod-calibrated-v001/turn` and `face-review-v001`. The
texture gate still fails baked-light correlation -0.24 against 0.12 (density
301 passes; 272 islands advisory). **No ledger promotion**: the production
recipe carries a waiver marked PROVISIONAL in Ayric's name pending his
in-engine review, and `texture_approval` stays pending until he confirms.

**Rig.** Portable landmark route on the calibrated FBX,
`rig/landmark-v001`: 86 ue5_manny bones, heat weights, 100% coverage, gate and
five-pose deformation passed. Finger bones 02/03 carry no weights (gloved,
fused digits); crotch landmark fell back to Manny proportion.

**Compile and UE.** `recipes/sunset-ayric-v2-production.json` compiled to
`out/sunset-ayric-v2-production` (RAC_COMPILE_OK). Headless import verified:
185.0 cm, one material sampling three textures, three LODs, texture settings
correct (`work/ue5-verify-ayric.json`).

**Player swap.** `scripts/ue5/swap_workshop_player.py` (new) built
`/Game/SunsetWorkshop/AyricPlayer/v034/`: IK rigs, limbs-aligned retargeter,
`ABP_Unarmed_Ayric` plus retargeted `BS_Idle_Walk_Run` and 20 sequences with
pelvis rescale and root-track strip (ancestor scale 100), `BP_WorkshopAyric_v034`
(capsule 92.5, mesh yaw -90, sword re-fitted to spine_03 with the inverse
100x root scale), `BP_WorkshopGameMode_Ayric_v034`, level `L_WorkshopNight_v034`
from v026. Attempts v027 to v033 are retained failures of the script, not of
the asset (no ABP in batch results; graphs not reflected to Python; registry
not rescanned; SCS socket lookup; v033's sword inherited the 100x scale and
filled the camera). PIE walkthrough evidence with screenshots:
`evidence/walkthrough-ayric-v031/` (no sword), `-v033/` (giant sword),
`-v034/` (correct). Cooked archive: `output/sunset-workshop-ayric-v034` via
`scripts/cook_workshop_level.ps1`; launch with
`scripts/play_workshop_demo.ps1 -Lighting Ayric`.

**Open.** Ayric's decisions: texture waiver (confirm or revoke), face quality in
engine, hand roll under the retargeted idle. The head-detail paint route needs a
head with real sockets or a single registered front image to place features.

## 2026-09-06 — Rig repaired; face correspondence concern remains open

User requested rig first, then at most two hours on the face. Existing dirty
work and Claude's calibrated payload are preserved. New anatomical-v002 rig
corrects coat-biased hips, wrists and splayed fingers; UE v036 maps palm and
finger frames and separates root travel before stripping ancestor tracks.
v035 is rejected for pelvis drift of about two metres during a stride.
v036 passes rig/deformation checks and the cooked movement/collision/jump/
landing/sword audit. All 16 walk/jog tracks remain in place. Default Ayric
launcher now targets v036, with the unchanged Claude face. Originals remain.

Face experiment `texture/face-repair-20260906` under sunset-ayric-v2 contains
three geometry-bound imagegen donor edits, six registration preflights and
three mapped candidates. v001 fringe leakage and v002 hard boundaries are
rejected. v003 improves paint but is **held, not fixed or user-approved**.
User correctly raised artwork/3D-surface mismatch; current clay confirms
shallow eye/mouth geometry. Painted feature anchors on a surface do not prove
anatomical correspondence. Stop further donor variants; no blind painter retry.

v037 material/BP/map/cook exists solely as a comparison candidate; same v036
rig and ORM, new BaseColor only. It is not the default or a ledger promotion.
Both cooked audits pass mechanics, not face aesthetics. Full verification
passed after adding seven CPU tests. Details, research, paths and retained
failures: `docs/AYRIC_REPAIR_2026-09-06.md`. Face budget began 13:55:30 UTC;
no further texture generation after the third candidate and user's correction.

## 2026-09-06 — Separate detailed head, repeatable neck transfer, playable v051

The user's geometry-fit follow-up reused the existing image-conditioned detailed
head instead of repainting the shallow original. They liked the face and asked
for the neck transition to be fixed and made repeatable. They explicitly accept
a separate head and useful added vertices when reviewed for game use.

Latest review candidate: `/Game/SunsetWorkshop/L_WorkshopNight_v051`, packaged in
`output/sunset-workshop-ayric-v051/Windows`. Launch with
`scripts/play_workshop_demo.ps1 -Lighting Ayric`; `AyricLegacy` retains v036.
The default Night/Manny variant is unchanged. The detailed face images and original
body images are byte-unchanged. Latest neck appearance awaits human approval;
do not promote the ledger or describe the close-up collar edge as fully welded.

Native body: `/Game/SunsetWorkshop/RigRepairs/neck_transfer_v012/ayric_body`.
Source derivative: `work/sunset-ayric-v2/rig/neck-transfer-v008`. Head remains
`/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production`.
Shared v036 skeleton and animations; head socket fit measured in reference pose.
Body 12,574 vertices / 16,039 triangles; head 12,740 / 19,988; sword 11,123 / 18,000.
Total actual cooked LOD0: 36,437 vertices / 54,027 triangles across three parts.

Evidence: `head-assembly-v051.json`, `head-assembly-v051-motion/review.json` (15
views/poses, no errors, head/sword attachment errors zero) and
`cooked-ayric-v051/audit.json` under `work/sunset-workshop/evidence`. All 18 cooked
checks pass, including movement, collision, jump/landing, actual native mesh
budgets and attachments. Eleven actual packaged frames retained. Scene-lit
close-ups are dark; the separate native lit fixture is the appearance authority,
not those dark gameplay frames alone. No physical-keyboard claim.

Canonized workflow: `docs/CHARACTER_HEAD_AND_NECK.md`, two source-hash-pinned
recipes under `recipes/assemblies`, `scripts/run_neck_transition.ps1`, Blender
fit/transport/subset/replay scripts, UE material adapter and
`integrations/ue5/RacEditorBridge`. Final independent replay passes exact semantic
equality at `work/sunset-ayric-v2/rig/neck-final-replay-v002/replay-verification.json`.
219 CPU tests and Python syntax checks (now including UE scripts) pass. No GPU
inference used for this fit/neck stage. Prior dirty work and rejected candidates
are preserved. Full reasons: `docs/AYRIC_REPAIR_2026-09-06.md`.

Important retained failure: v050 looked better but unnecessarily split 28,908
body vertices by storing unused per-corner normal data over the whole body.
Its cooked budget failure is genuine; do not relabel it passed. v051 bounds
auxiliary data to the neck and passes. This is not useful extra head detail.
The next visible decision is the user's approval or rejection of the v051 neck.

### 2026-09-06 — README native showcase (no character asset changes)

Added three actual UE studio stills and a 24-frame, 1.5-second walk GIF under
`docs/images/ayric-v051`, with hash-bound `provenance.json`. Source capture:
`work/sunset-workshop/evidence/readme-showcase-v004/showcase.json`. Native
attachments pass 0.1 cm tolerance; both foot bones move; GIF duration is 1500 ms.
README distinguishes editor animation from the separate 18-check cooked audit,
retains the collar approval caveat, and folds superseded progress into history.

Reproduce with `configs/showcase/ayric-v051-editorial.json`,
`scripts/ue5/capture_character_showcase.py` and
`scripts/package_character_showcase.py`; see `docs/CHARACTER_SHOWCASE.md`.
No source map, mesh, material, rig or texture saved; no AI inference. Retained
v002 receipt failed duplicate records; v003 failed frozen-frame checks. v004
fixes screenshot callback reentry and sets animation time before immediate
pose evaluation. Nine packaging regression tests cover these failure gates.
Full `scripts/verify.ps1` passes. Media and documentation are local workspace
changes, not a claim of GitHub publication or final texture approval.

### 2026-09-06 — User correction: glamour belongs in the workshop

README showcase now targets `docs/images/ayric-workshop-v051`, with the actual
v051 room, staged idle character, moon/window portrait, room-wide composition,
workbench angle and in-scene in-place walking GIF. No studio-background substitute.
Recipe: `configs/showcase/ayric-workshop-v051.json`; fixture:
`scripts/ue5/showcase_workshop_fixture.py`. All source assets and saved lighting
remain unchanged. A disclosed temporary 3-lumen rectangular fill makes the face
readable under the existing exposure; no texture repainting or image retouching.

Evidence series: `work/sunset-workshop/evidence/workshop-glamour-v004`.
v001 lacked facial fill; v002 and v003 were too bright. They are retained, not
promoted. The new recipe hash is captured at load time to prevent later edits
from changing a running capture's provenance. Studio captures remain historical.
The previous master/main publishing clarification remains unresolved; this
entry does not claim a remote push or final neck approval.

## 2026-09-11 — Reliability maintenance, v0.1.1

User selected a reliability-first maintenance release for the existing
Codex-operated workflow, and requested a GitHub release with plain-English notes.
No UI, new geometry, new paint, or historical authority migration is part of it.

Three reproduced failures are corrected: an audit with omitted pending stages
reported production-ready; a failed prop normalization could reuse an old report
and publish a manifest without a fresh FBX; a built/installed wheel lacked its
adapter registry. Canonical intake-derived stage validation now guards both
audits and promotions, independent of JSON key order. Malformed ledgers fail
without repair or writes; JSON writes replace complete files atomically.

Prop compiles use unique retained attempt folders, input/output hashes, explicit
Blender exception exit codes, and whole-directory publication into a new output
destination. The operator and packager resolve the published normalization report
through its manifest-bound receipt; legacy reports retain their original paths.
PNG naming/encoding is preserved for downstream texture discovery.

The doctor supports ledger/geometry/texture/ue/all profiles with consistent text
and JSON readiness and exit codes. Optional add-ons do not block other routes.
Verification wrappers share one Python test/lint/syntax/build/isolated-install
sequence with CI, and select one explicit or discovered compiler interpreter.

Validation evidence is in `output/reliability-validation/`: the Python 3.11/3.12
verification logs and `native-prop-v003/smoke.json`. The native synthetic fixture
passed scale, triangles, FBX reimport, input/payload hashes and refusal to replace
an existing output. It is a file-export test, not artwork or an asset approval.
The GPU remains owned by the user's other project; no inference was launched.
No existing source references, generated authorities or visual approvals changed.

Follow-up work remains the separately scoped AI setup installer, agent status/
resume improvements, skeleton unit-scale export, semantic UVs and retarget roll.
Release publication is verified against the GitHub release/tag and CI when shipped;
this implementation record alone is not remote-publication evidence.
