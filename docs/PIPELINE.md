# Pipeline and promotion gates

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
automation identities are refused. UE import, runtime review, and cook require
their schema-bound per-asset receipts. A generic `rac promote` call cannot turn
empty or token evidence into `production_ready: true`.
