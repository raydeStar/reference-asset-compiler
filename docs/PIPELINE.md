# Pipeline and promotion gates

*Type: reference*

## Ledger stages

This is the canonical stage list. The names are exactly those in
`src/reference_asset_compiler/contracts.py`: every workspace has the eight
`BASE_STAGES`; articulated assets (humanoid, mascot, creature,
mechanical_articulated, or `--articulation required`) add `ARTICULATED_STAGES`,
static assets add `STATIC_STAGES`. "Human gate" is `HUMAN_STAGES` in
`workspace.py`: an automation identity (`codex`, `claude`, `agent`, a script
name) is refused there unless a hash-bound user delegation receipt accompanies
it. The receipt schema is what `validate_passed_stage_contract` requires before
the stage can be marked passed; where no schema exists yet, the ledger still
requires evidence files, a note and a reviewer.

| Stage | Route | Human gate | Required receipt / evidence | Recorded by |
|---|---|---|---|---|
| `intake` | both | no | none; passed when `rac new` copies and hashes the reference | `rac new` |
| `route` | both | no | none; passed by the routing decision at creation | `rac new` (`rac plan` previews it) |
| `generate_candidates` | both | no | `reference-asset-compiler.geometry-candidate.v1`, bound to the source hash and an allowed geometry adapter | `scripts/run_hy3d_geometry.ps1` writes it; `scripts/crank_from_image.py` or `rac promote` records it |
| `modeling_approval` | both | **yes** | a mesh (`.fbx`/`.glb`), `matcap-front/three-quarter/side/back.png`, and `reference-asset-compiler.modeling-derivative-lineage.v1` bound to the generated candidate | `rac promote`; `crank_from_image.py --approve-modeling-by` |
| `semantic_cleanup` | both | no | `reference-asset-compiler.semantic-cleanup.v1` with a `semantic-cleanup-topology.v1` report bound to input and output | `rac cleanup-receipt` (driven by `scripts/run_semantic_cleanup.ps1`), then `rac promote` / `crank_from_image.py` |
| `production_retopology` | both | **yes** | `reference-asset-compiler.production-retopology.v1` with a `production-retopology-candidate.v1` report, budgets, closed manifold, 80% quads for articulated kinds, four views | `rac retopology-receipt`; `crank_from_image.py --approve-retopology-by` |
| `unwrap_and_bake` | both | no | `retopo.json` binding the approved retopology or its UV transport, and every baked map by hash | `crank_from_image.py` |
| `texture_approval` | both | **yes** | `*_production.fbx`, baked PNG maps, `retopo.json` binding source mesh, production FBX, maps and passing `gate-tex.json` by hash, plus `beauty-front/three-quarter/side/back.png` | `rac promote`; `crank_from_image.py --approve-texture-by`; `scripts/compile_from_image.py` |
| `rig_and_skin` | articulated | no | `reference-asset-compiler.rig-and-skin-evidence.v1` | `scripts/record_rig_and_skin.py` |
| `deformation_validation` | articulated | no | `reference-asset-compiler.deformation-evidence.v1` | `scripts/record_deformation.py` |
| `collision_optional` | static | no | one static `*.ue5import.json` explicitly declaring `ue5_import.generate_collision` | `scripts/promote_production.py` |
| `static_validation` | static | no | one static import manifest plus its actual FBX and declared textures, all retained by hash | `scripts/promote_production.py` |
| `ue5_import` | both | no | `reference-asset-compiler.ue5-import-evidence.v1`, manifest-bound, within the intake budgets | `scripts/record_ue5_import.py` (also `--native-revision` for a saved native derivative) |
| `ue5_motion_review` | articulated | **yes** | `reference-asset-compiler.ue5-motion-review.v1` | `scripts/record_ue5_motion_review.py` |
| `ue5_runtime_review` | static | **yes** | `reference-asset-compiler.ue5-runtime-review.v1` (or the `ue-static-multiview-review.v1` report described below) | `scripts/record_runtime_review.py` |
| `cook` | both | **yes** | `reference-asset-compiler.cooked-runtime-evidence.v1` | `scripts/record_cook_evidence.py` |

`rac audit <job>` verifies hashes and stage order for one workspace and
`rac cohort-audit <manifest>` for a release cohort. `audit` exits 0 for an intact
ledger, including an incomplete one; read its separate `production_ready` field.
`cohort-audit` exits 0 only when every asset is complete. Both exit
1 when the audit or cohort fails, 2 for usage errors or `RAC_ERROR`. Only a
fully passed ledger reports `production_ready: true`.

Texture payload reports bind `source_uv_authority_sha256` to the approved
retopology, directly or through retained UV transport receipts. They also bind
`output_fbx_sha256`, `baked_sha256` and `gate_texture_sha256` to the actual
export, maps and passing gate report. Old filenames alone do not satisfy these
checks. Historical receipts with missing bindings fail audit until the missing
evidence is supplied and reviewed; the compiler does not migrate approvals.

`rac promote --replace` snapshots the previous ledger before replacing a passed
stage. Replacement must preserve the validity of downstream passed stages.
State updates are locked, and retained receipt publication cannot overwrite a
concurrent recorder's evidence.

## 1. Intake

The approved image or turnaround is the artistic contract. `rac new` copies it
into the asset workspace and records its SHA-256 hash. Do not replace that file
in place. A changed brief is a new intake revision.

Record enough intent to route safely:

- asset kind;
- articulation requirement;
- primary view and any additional views;
- runtime vertex and triangle budgets;
- candidate adapter allow-list;
- explicit skeleton profile for nonstandard articulated assets.

## 2. Candidate acquisition

Run geometry systems in isolated directories with frozen versions, settings,
seeds, logs, and source hashes. A crash is evidence; do not silently auto-retry
or overwrite the failed run. Candidate acquisition must preserve the user's
open Blender, ComfyUI, and UE sessions and inspect GPU ownership before local
inference.

## 3. Modeling approval

Texture and rigging cannot repair incorrect geometry. Review neutral clay
renders from fixed front, three-quarter, side, and back cameras. Silhouette
metrics are useful regression signals, not approval.

Humanoids additionally require explicit review of identity, proportions,
head/neck continuity, garment construction, hands, elbows, waist closure, and
feet. Mascots require exact visible-part and tail counts. Props require correct
dimensions and modeled structural detail rather than painted substitutes.

Promote the selected high-resolution mesh as an immutable authority. Retopology
and cleanup are derivatives; never overwrite the authority.

## 4. Production topology

Repair disconnected components and non-manifold debris before reduction.
Preserve distinguishing parts and deformation loops. Compare every reduction
against the authority in the same cameras. A lower triangle count that damages
the approved read is a rejection.

## 5. Texture approval

Texture only an approved topology. Existing-mesh texturing systems must restore
the exact geometry and face order after inference. Review base color separately
from material response, then review the complete PBR result.

Hard failures include duplicated or stamped features, displaced eyes/nose,
atlas seam lines, baked shadow holes, projection outlines, random bright
specks, and material regions that do not follow modeled parts.

## 6. Rigging and deformation

Humanoid output must use the declared UE skeleton contract, not merely a
similar-looking bone hierarchy. Verify chain names, finger completeness,
maximum influences, scale, bind pose, and clean FBX reimport. Review elbows,
wrists, fingers, shoulders, neck, waist, knees, and ankles under representative
poses.

Nonhumanoid rigs require a named skeleton profile and their own deformation
suite. Do not route spiders, quadrupeds, or mechanical assemblies through a
humanoid profile for convenience.

## 7. Runtime proof

Import into a clean UE destination, bind to the expected skeleton, assign the
actual materials, and inspect the native imported payload. Evidence includes:

- engine version and import settings;
- vertex, triangle, section, bone, influence, and UV counts;
- fixed camera screenshots in the target map;
- representative animation poses;
- map-check results;
- packaged or cooked runtime result.

Only a fully passed ledger may claim production readiness.

The ledger enforces this contract centrally. Every passed stage after intake
and routing requires immutable evidence and a note. Modeling and texture passes
require their full fixed-view payloads and an identified human reviewer;
automation identities are refused by default. UE import, runtime review, and cook require
their schema-bound per-asset receipts. A generic `rac promote` call cannot turn
empty or token evidence into `production_ready: true`.

Explicit user-delegated demo exception: when the user expressly asks an agent
to judge visual gates without stopping, the ledger can accept `codex` with a
`review-delegation.v1` authorization and a `delegated-review.v1` receipt. The
authorization names the consenting user, quotes the instruction and scopes the
reviewer, source-image hash and stages. Each review hashes that authorization
and every inspected artifact and states `human_visual_review: false`. Missing,
changed or out-of-scope evidence fails. All ordinary stage/geometry/mechanical
requirements still run. Without this explicit receipt the default human gate
continues to reject automation. This exception is not a mechanical waiver or
permission to stamp a user's name onto an agent's visual judgment.

### Native static-mesh revisions

UE can split vertices or change bounds during its own LOD build. Static import
verification now measures built vertex/triangle/section counts for every LOD
and checks texture color-space settings as well as scale and material sampling.
Missing native measurements fail rather than being silently skipped.

For a separately saved native reduction, `scripts/record_ue5_import.py <asset>
--report <native-report.json> --native-revision <revision-id>` records a new
immutable import receipt and retains the complete previous ledger. It requires
the same manifest/materials, hash-bound original and derivative `.uasset`
files, transformation receipts, and built counts within the intake budgets.
Passed or active downstream work prevents replacement. A blocked runtime review
is deliberately not advanced by this import operation.

An explicit `native_material_rebind` revision is also supported. This is not a
geometry-reduction waiver: a read-only UE buffer probe must prove identical
vertices, indices, normals, UVs and tangents for every LOD and section, and
unchanged source textures. Bind both mesh packages, old/new material instances,
the new master and the probe by hash. Native counts, texture settings and the
normal-fallback policy must pass. The later matched visual review is still a
separate gate. This route repaired a plant material without laundering its
rejected original native appearance or changing its approved geometry.

The versioned `M_RAC_CharacterMaster_v002` uses an explicit `(0,0,1)` tangent
normal when `HasNormal=0`; only an authored normal sets `HasNormal=1`. Do not
assume an Engine asset named `DefaultNormal` is a neutral normal map. Existing
masters and their consumers are preserved rather than edited globally.

The later static runtime review may bind two matched original/derivative camera
pairs, forced to LOD0, with all four frame hashes and the new native import
receipt. Explicit agent delegation remains required for an agent verdict.
These editor views do not prove scene collision or cooked runtime. The original
FBX, imported mesh and prior evidence are not overwritten.

For source-locked modular character head fitting and bounded neck colour/normal
transport, see [the repeatable character workflow](CHARACTER_HEAD_AND_NECK.md).
The seam step uses existing AI-acquired surfaces, adds only colour/auxiliary UV
data, and preserves original UV0, geometry, weights and skeleton by fingerprint.
It is a candidate adapter, not an automatic human approval or ledger promotion.

Static props without a native revision can instead bind an explicit
`reference-asset-compiler.ue-static-multiview-review.v1` report. It requires
front, three-quarter, side and back at forced LOD0, distinct camera positions,
valid camera targets, unique hash-bound image files, exact imported mesh and
built LOD counts, and the immutable import receipt hash. Optional reduced-LOD
frames are retained too. Both recorder and ledger audit validate every bound
frame; the primary image cannot substitute for missing opposite views. This
certifies only delegated static editor appearance, not attachment or cooking.
