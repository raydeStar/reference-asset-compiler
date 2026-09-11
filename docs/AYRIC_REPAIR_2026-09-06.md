# Ayric rig and bounded face repair, 2026-09-06

*Type: chronological log*

User scope: repair locomotion first; then spend at most two hours on facial
texturing, including its research. Preserve Claude's calibrated artwork and
the v034 character/demo. This is candidate work, not a texture waiver or a
 production-ledger promotion. The rig stage preceded the bounded face stage.

Face budget starts 2026-09-06 13:55:30 UTC, conservatively including the earlier
face-history read. Hard deadline 15:55:30 UTC (09:55:30 Mountain). At most three
mapped appearance candidates; no unbounded geometry or model-install detour.
Research: Tencent's [actual paint pipeline](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dpaint/textureGenPipeline.py)
conditions multi-view synthesis on normal/position maps before baking. Our
retained full/head painter trials already failed identity or doubled features.
The bounded alternative edits actual rendered views, then uses measured
camera/surface visibility and landmark registration, protecting other regions.
True unlit repair inputs use emission-only Standard exposure zero, avoiding
rebaking the old -1.5 display exposure into BaseColor. No new geometry.

## Face outcome and user correction

Three imagegen edits used actual front/+40/-40 degree renders, then a new
source-hashed mapper located shared facial surface points, rejected folded
registration, blended linear color, and protected hair/body regions. Six
registration files include failed preflights; only three textures were built.
v001 is rejected for skin leakage into fringe and feature softening. v002 is
rejected for a hard protected-region color boundary. v003 adds measured
skin-tone calibration and a feathered protection boundary. It improves paint
coherence, but **is not a fixed or approved face**.

At 14:18 UTC the user identified the recurring stamp/mesh mismatch. Inspection
of actual untextured facial geometry supports a shallow-feature limitation.
The mapper's anchors come from existing painted landmarks projected onto the
surface; they do not prove anatomical eyelid/lip alignment between anchors.
AI artwork still invents detail the geometry cannot fully support. More
attractive source images and valid UV transport are insufficient acceptance.
Stop further texture variants. No automatic promotion, no head replacement,
and no assertion that this is merely a lighting issue.

Preferred next task requires explicit direction: diagnose anatomical landmarks
against depth/normals and, if the geometry cannot support them, select/repair
an AI-acquired head under its own geometry/topology gates. A new portrait
stamp or blind Hunyuan retry is not the next step.

All face evidence lives in
`work/sunset-ayric-v2/texture/face-repair-20260906/`. v003 BaseColor SHA256:
`8e5fa8b9953025a5fbbe91aa04d4a3afce4f438c730ee316176a92d973572253`.
The v037 native material/BP/map and cooked archive are isolated comparison
artifacts, **not** the default launcher. v036 with Claude's original face is
the playable rig handoff. Body atlas outside facial support/gutters is exact;
sampled unchanged render regions differ by at most one 8-bit code value, so
render bit-identity is not claimed. No model installation or local AI inference.

## Rig research and diagnosis

- Epic's [IK Rig Retargeting](https://dev.epicgames.com/documentation/en-us/unreal-engine/ik-rig-animation-retargeting-in-unreal-engine)
  explains matching retarget poses and explicit chains. Local UE 5.8 source
  `IKRetargeterPoseGenerator.cpp`, `GetChainTangent`, explicitly refuses the
  end of a chain. Thus requesting direction auto-alignment for `hand_l/r`
  at an arm-chain endpoint does not align the palm.
- Local `IKRetargetProcessor.cpp` applies each pose rotation as
  `ReferenceLocalRotation * Offset`. The palm correction uses that convention,
  reconstructs the posed parent transforms and matches anatomical frames
  from the wrist, middle, index and pinky joints, not arbitrary bone axes.
- [Auto-Rig Pro game export guidance](https://lucky3d.fr/auto-rig-pro/doc/ge_export_doc.html)
  distinguishes bone naming/axes from actual retargeting. The installed ARP
  is operational, but changing rig backbones is not necessary to test the
  observed landmark failures.

Observed on the source-bound landmark-v001 overlay: hip X about +/-0.35 m
lies in coat panels; wrist and closed-template finger pivots miss the splayed
gloves. The original native idle visibly spreads the legs and leaves the
palms open. Capsule movement in Claude's walkthrough does not prove the
deformation correct.

Candidate anatomical-v002 preserves the existing mesh and UVs through the
landmark binding fingerprint, fits explicit anatomical XZ joint anchors with
depth measured from the existing mesh, and regenerates weights. All 86 bones
now have their expected coverage (no unweighted deform bones); the rig gate
passes, max four influences, 19,588 triangles, no unweighted vertices.
Human approval is not claimed for agent-selected candidate pivots.

UE derivative v035 imports into a fresh RigRepairs folder, reuses the exact
existing native material, maps fingers/twists and aligns palm frames before
finger chains. Old mesh, animations, blueprints, levels and packages remain.
v035 is rejected: the corrected pose fixture exposed roughly two metres of
forward pelvis travel, despite stripping the root track. v036 adds Epic's
root-motion generation operation before export so root travel is separated
from the pelvis before ancestor tracks are removed. See Epic's
[operation stack](https://dev.epicgames.com/documentation/unreal-engine/retargeting-operation-stack-in-unreal-engine-5-8).

v036 cooked successfully and the packaged audit passed all 13 checks:
possession, expected character, floor/collision, moving legs, travel,
jump/landing and sword attachments. These are programmatic gameplay tests,
not a physical-keyboard claim. Actual native front/side idle and two stride
poses were inspected. Saved walk pelvis XY ranges stay below 7.83 cm;
all eight jog tracks also stay below 7.52 cm. No mesh leaves its capsule by
metres. This is a usable demo rig, not a facial animation or cloth simulation.

Evidence: `work/sunset-workshop/evidence/cooked-ayric-v036/audit.json`,
`animation-tracks-v036.json`, `rig-candidate-v036-motion/` and the immutable
package `output/sunset-workshop-ayric-v036/Windows`. Original v034 remains.

## Follow-up authorization: geometry fit, halt at 10 a.m. Mountain

The user authorized the geometry-fit repair after the stamping diagnosis,
with a hard halt of 2026-09-06 16:00 UTC (10:00 America/Denver). This supersedes
the earlier stop on texture-only variants; it does not approve a new appearance.
The detailed, image-conditioned `sunset-ayric-rigid-head-v1` component already
has actual modeled facial features and its own UV/material/native evidence.
It is being fitted as a separate rigid head following the existing head bone,
not presented as a newly sculpted face or a facial-animation rig.

`scripts/blender/assemble_workshop_head_candidate.py` creates a versioned body
subset from the exact anatomical-v002 rig. `verify_workshop_body_subset.py`
compares every surviving polygon's positions, UVs and weights, and all bones.
The current head-assembly-v006 passes these exact checks; restored custom
normals differ by at most 0.00007582 per component after Blender encoding.
Body is 16,040 triangles; the separate AI head remains 19,988 triangles.
Original FBX, maps, v036 rig, and playable fallback remain unchanged.

Retained fit failures: v001 height trim left chin pieces and reversed the head;
v002 omitted small facial UV islands; v003 retained old neck skin; v004's warm
colour filter caught gold collar trim and is rejected; v005 fixed the selection
but exposed custom-normal recalculation. v006 restores source split normals.
Selection is source-hash guarded; neck skin islands 2800 and 3324 are measured
separately from the blue collar, avoiding a broad colour-based deletion.

UE build v038/v039 failed because private SCS fields are not readable through
Python. The installed RacEditorBridge provides an explicit socket setter.
v040 assembled successfully but matched native views reject its reversed head
orientation. v041 corrects the local facing. New level and BP only, shared
verified v036 skeleton/animations, separate head static-mesh component and
unchanged persistent sword. Motion/appearance/cooked checks are still pending.

Research: Epic's [FBX skeletal mesh pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine)
and [skeleton documentation](https://dev.epicgames.com/documentation/unreal-engine/skeletons-in-unreal-engine)
support preserving a compatible skeleton across mesh derivatives. Local
SubobjectData/SCS code and the installed editor bridge establish persistent
socket assignment; private field access is not an API contract.

## Earlier retained diagnostic failures

- First editor launch used a relative project argument; Unreal resolved it
  incorrectly and exited before executing Python. Absolute paths correct it.
- rig-baseline-v001 captured the bind pose repeatedly: setting transient
  animation data alone did not force evaluation. These are not motion proof.
- v002 explicitly tried `refresh_bone_transforms`, which is not reflected to
  Python. Local engine inspection proves `override_animation_data` already
  evaluates and refreshes. However v003 and initial v035 only prove idle:
  switching sequences also requires `set_animation` before the override.
  Corrected `*-motion` fixtures select and record the actual sequence.
- Initial deformation output used relative paths and Blender wrote images
  to `C:/work/sunset-ayric-v2/rig/anatomical-v002/deform`. Retained; rerendered
  into the workspace with absolute paths as `deform-native`.

## Detailed head and reusable neck transition

v042 fixes the bind-pose fitting error in v041. It uses the existing detailed AI
head, unchanged face texture, the exact source-preserving body subset and the
v036 skeleton/locomotion. Its 15 native views passed attachment checks and its
cooked package passed all 18 technical checks. The user liked the face but
requested a softer neck transition and explicitly asked to canonize the method.
They subsequently authorized a separate head and increased vertex count when
reviewed in the context of a video game; no universal polygon-count waiver is
inferred from that preference.

The reusable implementation is documented in `CHARACTER_HEAD_AND_NECK.md`, with
hash-pinned head-fit and neck-transition recipes, a CPU-only PowerShell runner,
Blender transport/subset/replay checks, native material adapter, persistent socket
bridge, and read-only native colour-buffer probe. It transports existing head
colour and surface-normal direction into a narrow body neck mask. It does not
redraw the face or edit the original texture images, UV0, mesh positions, skeleton
or skinning weights. Two auxiliary normal UV channels and a corner-colour layer
are new derivative data. No GPU inference was launched for this assembly/repair.

Retained neck trials: head-assembly-v007 removed more collar faces without a good
result; v008 flat lining changed too much collar design. Neck-transfer-v001 had
a JSON numpy-integer serialization error, v002 spilled onto trim, v003/v004 added
pixel guards. Sparse corner classification still missed interior skin texels;
v005 moves colour classification to the pixel shader. Native v043-v045 exposed
API reflection/output-pin differences; v046 rendered a grey fallback because
PreSkinnedPosition was used in pixel space. v047 adds VertexInterpolator;
v048 improves mask coverage; v049 tests neutral neck normals. Colour alone still
left a lighting mismatch. Normal transfer adds the actual head direction.

Blender neck-transfer-v006 rejected `calc_tangents` on the approved ngons; v007
derives tangent frames from loop triangles without triangulating the mesh.
Native v050 looked better and passed motion/attachment, but its cooked audit
correctly failed the body vertex budget: unused auxiliary normals split 28,908
body vertices. v050 is **rejected**, despite 17 other passing runtime checks.

Neck-transfer-v008 stores constant normal data outside the blend's support.
Native v051 retains the appearance at 12,574 body vertices (749 above the old
11,825) with 1,307 nonzero-alpha native colour entries. The separate head is
12,740 vertices / 19,988 triangles. The native builder now rejects missing colour
coverage and an excessive body split count before creating a new player.
The local body derivative is `work/sunset-ayric-v2/rig/neck-transfer-v008`;
the native body is `/Game/SunsetWorkshop/RigRepairs/neck_transfer_v012/ayric_body`.
The head remains `/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production`.

Independent final recipe replay `neck-final-replay-v002/replay-verification.json`
passes exact semantic equality of generated colours/UVs, protected geometry,
source/recipe/implementation hashes. The head-fit recipe also independently
replays and passes its subset verification. These are actual executions, not
documentation-only recipes. The latest neck remains pending human visual approval;
there is still a small geometric collar edge under an extreme close-up. No facial
deformation, cloth, physical-keyboard test or production ledger promotion is claimed.

### Final technical verification before the 10 a.m. halt

v051 native review retains all 15 head/pose images with no script errors and zero
head/sword attachment error. `output/sunset-workshop-ayric-v051` cooked successfully.
`work/sunset-workshop/evidence/cooked-ayric-v051/audit.json` passes all 18 checks,
including exact meshes, locomotion, wall collision, jump/landing and the modular
avatar budget. Actual cooked totals are 36,437 vertices / 54,027 triangles across
body, head and sword. Eleven rendered gameplay frames are retained. These scene-lit
views are dark; neck appearance was judged in the separate lit native fixture.

`scripts/play_workshop_demo.ps1 -Lighting Ayric` now opens that review package only
when its matching cooked audit passes. `AyricLegacy` retains the unchanged-face
v036 fallback. The default Night/Manny choice is not changed. All our render/game
processes self-exited after evidence collection. Final verification: 219 tests
pass, including new seam validation/colour-space/bounds tests, and syntax checks
cover Blender and UE Python adapters. No commit/push or human approval is claimed.
