# Cross-agent handoff: V1 checkpoint

Last updated: 2026-09-01

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
