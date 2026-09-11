# Ayric face: paint repair is insufficient

*Type: escalation*

2026-09-05. User feedback: "Man, face texture isn't great, definitely needs
work. Everything else is great though." Keep the body and scene unchanged.

The held `work/sunset-ayric-v2/prod-collar-v001` package is unchanged.
Built-in ImageGen edited actual unlit side, opposite-side and front head
renders to create cleaner hair/ear donors. Original photo remains identity
reference. Exact prompts and project copies are in
`work/sunset-workshop/character-art/*detail*` and `*front-hair*`.
Donors are not mesh renders. Ear placement drift required camera landmark
registration for downstream UV transport, not geometry editing.

## Actual outcomes

- `texture/side-detail-preview-v001`: clearer sideburn and ear, but an abrupt
  old/new hair-color mismatch toward the front. Rejected.
- `texture/head-wrap-preview-v001`: three donors transported sequentially.
  Hair strands and ears are sharper, but skin-colored patches and dark breaks
  remain in the left fringe. Eye/mouth shallowness is unchanged. Rejected.

Both native bindings preserve 9,790 vertices / 19,588 triangles, face order,
UV authority and 1.85 m scale. Original base-color/FBX hashes are verified
unchanged; metallic and roughness are byte-identical. Each mapping checks exact
outside-support/gutter preservation. No UE, rig, or ledger changes.

## Causal limit and next route

Actual existing runtime clay at
`retopology/projected-v002/closeups-v001/face-front.png` shows very shallow eye
and mouth structures. Sharp painted landmarks improve readability but do not
repair that geometry. This is a visual diagnosis, not a measured anatomical
metric. Do not repeat full-face stamps, intrinsic-lighting estimator trials,
or further hair-only donors as a solution to the face complaint.

Image-conditioned head acquisition now has a successful dense component (see
the update below). Preserve the body. Any head replacement
must be an AI-acquired derivative, pass a fresh modeling gate, and then
topology/UV/deformation checks. Do not manually sculpt an approximation, waive
existing gates, or silently replace a ledger authority.

## Evidence

`work/sunset-workshop/evidence/ayric-head-detail-review-v001.html` compares
current held and both rejected candidates across five actual camera views,
unlit and lit. Matching JSON binds 89 files including clay, current payload,
donors, prompts, correspondence, mapping, binding, render receipts and drivers.
Reviewer is Codex, human_visual_review=false. The panel is not a promotion.

The independent body lighting hold also remains. Full demo goal stays active;
this investigation is not completion or permission to change other assets.

## Update: head acquisition passed, reduction did not

New isolated job `work/sunset-ayric-head-v1` directly conditions Hunyuan3D-2mv
on a high-resolution front head reference derived from the supplied identity
photo, with built-in ImageGen inferred left/back guidance. Exact prompts and
image lineage are retained under `references/`. These guidance images are
not renders of a completed model.

Dense head/neck component modeling and semantic cleanup passed delegated
review. Actual neutral clay has much clearer eyelids, eye volume, lips,
nostrils and ears. This does not approve a whole-character replacement.
No manual sculpting or reference tracing generated the mesh. Outer-silhouette
IoU is 0.931675 and centroid distance 10.142 px after correcting the source
mask's bright-skin holes; the failed initial mask diagnostic is retained.

Both reductions are rejected in `retopology/rejections-v001.json`:

- `quad-v001`: 11,136 triangles, four boundary edges, flattened facial detail.
- `voxel-quad-v002`: 4,030 triangles, six boundary edges, severe loss of eyes,
  lips and hair clumps. It completed normally and failed guards; not a crash.

Matched CPU clay fixtures confirm geometric loss, not a lighting difference.
Do not merely close the holes, repaint these reductions, or repeat blind
global remeshing at lower counts. Next diagnostic: feature-preserving
surface reduction to distinguish geometric budget limits from quad-remesher
smoothing. Articulated quad/deformation gates remain mandatory afterward.
The body-region budget probe is a read-only estimate, not an approved cut.

Current review panel:
`work/sunset-workshop/evidence/ayric-head-geometry-review-v001.html`.
Head/body assembly, final UVs/textures, rigging and UE replacement remain
unimplemented. Existing whole-character lighting hold is not waived.

### Surface-preservation follow-up

Six further actual mesh diagnostics are retained in
`work/sunset-workshop/evidence/ayric-head-surface-review-v002.html`.
Generic QEM weighting, zero-weight control and two facial-priority strengths
do not yield acceptable5k topology. A20k intermediate improves detail and
passes generic surface-distance checks, but introduces an under-eye pit.
The accepted dense cleanup has no pit in the same clay fixture. A downstream
5k reduction preserves828 facial vertices exactly and inherits that defect;
it appears before and after triangle pairing. Pairing is not its cause.

Next diagnostic is intermediate QEM surface displacement versus normals,
possibly bounded projection back to the dense authority. Do not keep tuning
importance strength or promote the20k intermediate from distance metrics.
The protected5k variant also has only42.69%quads and coarse ears/neck.
All trials remain rejected for runtime; no texture or rig gate advanced.

### Normal diagnosis supersedes the under-eye geometry-only assumption

`projected-intermediate-v010` does not remove the dark under-eye pit despite
bounded dense-surface projection. `normal-intermediate-v011` removes that
darkness with dense-source vertex normals and exactly unchanged geometry.
The intermediate has no inherited custom normals. This demonstrates a shading
contribution; it does not prove all reduced geometry is faithful.

Full-head normal transfers on5k meshes (`normal-priority-v012` and
`normal-protected-v013`) remain rejected. v013 improves the face but creates
objectionable neck/rear-skull shading and retains coarse ears/42.69%quads.
If pursued, limit normal transport to the face; keep coarse-body normals
untouched. Do not repeat global normal transfers or projection-only attempts.
Topology, allocation and deformation gates still apply. Evidence panel:
`work/sunset-workshop/evidence/ayric-head-normal-review-v003.html`.

### Active route: localized shading and a separately verified rigid head

Face-only normal transfer succeeds as a bounded shading diagnostic. The20k
`normal-face-only-v016` candidate retains substantially better ears, neck and
hair than the5k cases. Native roundtrip geometry is exact; valid outside
normals remain within6.8e-7, but24 original zero normals remain cleanup debt.

Continue in **`work/sunset-ayric-rigid-head-v1`** at UV/texture preparation.
Exact dense AI acquisition is reused; modeling, cleanup and static topology
now pass. The accepted native head is
`retopology/face-normals-v006/normal-transfer.blend` (19,988 triangles).
Eleven collapsed components were restored directly from dense AI geometry;
all31 components remain, zero undefined normals, closed native surfaces.
Four actual clays and source overlay pass. This is a rigid head-bone attachment with a fresh component
ledger, not a deforming facial rig or a promotion of rejected old topology.
Each component keeps20k/15k limits; assembled body/head/sword target60k is
explicit and must be measured. See `assembly-contract.json` and the updated
demo completion contract. Neck seams, old-head overlap, motion and cooked
attachment proof remain mandatory. Body material and rig holds stay active.

Panel: `work/sunset-workshop/evidence/ayric-modular-head-review-v002.html`.

### Current texture evidence after topology acceptance

Use `work/sunset-ayric-rigid-head-v1/texture/uv-v004` as the next mapping
candidate:229 islands, one continuous central face, unchanged geometry,
nondegenerate native/OBJ UVs and11,290 estimated split corners. This estimate
is not UE native verification. Read HANDOFF tail for retained earlier layouts.

The first detailed-head Hunyuan paint (`texture/paint-v001`) completed its maps
and geometry/UV validation but crashed during teardown. No inference retry.
Its original scalar maps produce chrome-like skin; shader-only metallic0 /
roughness floor0.72 improves this without changing any BaseColor bytes.
Eye-edge paint artifacts and pale temple/cheek transitions remain visible
unlit, so the material improvement is not a texture pass.

Front-priority rebaking of the retained AI views onto the improved UV layout
has exact six-camera position correspondence, but broad facial replacement
introduces cheek/beard transition boundaries. Reject that route as currently
implemented. Diagnose/repair facial landmark correspondence and consistent
skin/hair art in the source paint views; do not repeat whole-face priority or
rerun the crashed painter unchanged. Body, geometry, rig and UE remain intact.

Current working panel:
`work/sunset-workshop/evidence/ayric-head-texture-working-v001.html`.

### Donor-mapping follow-up / still not texture-approved

Built-in ImageGen repairs of actual front and40degree head renders, guided
by matching clay and identity artwork, produce cleaner source art. Source
images and exact prompts are retained under the rigid-head `texture/` folder.
The head-only camera exporter now provides actual perspective/depth UV
correspondence. No new geometry or Hunyuan inference retry.

`eye-donor-v001` improves the two irises; keep as partial evidence, not a pass.
`angle-donor-v001` improves most of the near-side pale cheek but leaves a
brow-side wedge and introduces a small eye mark visible from the front.
Reject that combined candidate. The opposite-side band, forehead/skin
transitions and neck/mouth paint remain unresolved. Pixel visibility probes
show the inner-eye artifact is not solely caused by frontal occlusion.

Stop accumulating local patch boundaries. Use the retained coherent AI
artwork to plan complete visible skin coverage with measured landmark
registration and opposite-view evidence. Do not restart the old whole-face
priority bake with its inconsistent source paint or retry the crashed painter.
Actual16 candidate views, failure receipt, hashes and findings are in
`texture/donor-appearance-review-v001.json` and
`work/sunset-workshop/evidence/ayric-face-donor-review-v001.html`.

### Coherent three-view mapping / preferred working v003, still held

Current panel: `work/sunset-workshop/evidence/ayric-coherent-face-review-v001.html`.
Current candidate: `work/sunset-ayric-rigid-head-v1/texture/coherent-skin-v003`.
Its geometry, UVs and custom normals exactly preserve uv-v004. One new
built-in ImageGen opposite-three-quarter edit supplements the retained front
and40degree artwork; acquisition inputs, exact prompt and hashes are retained.
Fifteen shared surface landmarks replace independently chosen target landmarks.
Simultaneous linear-color blending repairs both pale cheek bands and aligns eyes.

v001 false self-occlusion caused stripes behind ears/neck. Exact subpixel
triangle visibility fixes the steep-surface synthetic control from61/500 to
500/500 visible samples while preserving foreground occlusion; actual v002/v003
renders confirm striping removal. v002's hard grazing boundary is softened in
v003, with donor-background exclusion. These are job-local CPU changes, not
a shared-pipeline promotion. All36 candidate frames inspected.

Unresolved: conspicuous gray rear hair/neck fade, remaining ear-rim and chin
transition review, and existing static_prop baked-light correlation failure
+0.36124097915777215 >0.35. No threshold relaxation, waiver or texture approval.
Density is provisional at0.33m head height, not final assembly sizing. Next:
image-condition the missing rear artwork and map with the same correspondence
authority; diagnose material-color/lighting contributions without gaming the
metric. Retain current coherent front sources. Do not restart the crashed
Hunyuan painter, change accepted topology, or claim the front renders prove360
quality. Body, rig, UE and full cooked-demo requirements remain unchanged.

### 2026-09-05 — Head component texture hold resolved

`work/sunset-ayric-rigid-head-v1/prod-texture-v001` now passes unwrap/bake and
delegated component texture approval. This supersedes the preceding head-only
texture hold, not the body-lighting or full-avatar requirements.

One built-in ImageGen rear edit conditions the exact rear camera's geometry-bound
mapping. Brown clipped hair replaces the gray nape. Retained three-quarter
artwork supplies both side-hair regions. `hair-bilateral-v001` is rejected for
a copied skin crescent above the near ear; v002 constrains both the donor sample
domain and target region above the ear. The short-hair fade is retained as a
styling choice. No facial features, geometry, UVs or source normals changed.

Native twelve-view and exported eight-view lit/albedo review passes for this
component. Central frontal face ROI differs at most one8bit code value over94
of133225pixels; do not call the actual render bit-identical. The failed strict
equality check happened before any ledger write and is retained separately.
Existing texture gate on exported FBX data passes correlation-0.2526853229014294
against absolute0.35; no waiver or threshold adjustment. Full167tests pass.

Panel: `work/sunset-workshop/evidence/ayric-head-texture-review-v002.html`.
Scope-bound review: `prod-texture-v001/delegated-texture-review-v001.json`.
Next is independent body-material resolution and complete avatar assembly:
fitted collar/neck, old-head removal, animation-following head and sword,
native UE measurements and cooked runtime. Do not resume cosmetic front-face
patches or imply static head approval proves the complete character.

### 2026-09-05 — Native UE head import and appearance passed

Published the exact accepted FBX and BaseColor at
`out/sunset-ayric-rigid-head-v1-production`; manifest SHA
983f86092c6f5a64903379d9215cb76fada39601b0ac86a9a6f48a94aad9d1ee.
Native UE5.8.2 LOD vertices12740/7134/3507, triangles19988/9994/4996,
one section each, height33cm. All seven import checks pass. The static head
collision policy is explicitly disabled; the eventual avatar capsule owns it.

v001 inspection fill washed the hair/skin pale. An exported UV audit confirmed
one correct UV_RAC_AI_Paint channel; it was not a wrong-channel defect.
v002 removes added fill, rotates only the fixture actor180degrees to correct
front/back handedness, and adds two explicit unlit BaseColor controls. All ten
actual engine frames inspected; accepted static component appearance. The
ordinary rear frame is shadowed; albedo confirms its paint is intact. Forced
LOD2 visibly facets the nose at portrait distance and is distance-only0.15.

v001 also failed its completion callback because Unreal removes __file__ before
asynchronous callbacks. Eight images and the failure log are retained, not
treated as a valid completed capture. v002 uses an explicit callback path and
ended normally. No source texture, UV, mesh or imported material repair needed.

Current panel: `work/sunset-workshop/evidence/ayric-head-ue-review-v002.html`.
Component audit and delegated UE review pass; cook remains pending. Body
material, head/collar fit, rigging, sword attachment and full cooked workshop
remain required. Do not reopen this resolved face texture merely because the
separate body-material gate is still held.

### 2026-09-05 — User explicitly reopens face quality

The user now says: "Man, face texture isn't great, definitely needs work.
Everything else is great though." This supersedes the preceding instruction
to leave the face alone: the reason to reopen is direct user feedback, not the
body-material hold. Earlier technical and delegated review receipts remain
historical evidence, not proof of current user acceptance.

Inspected the actual UE v002 albedo-front and three-quarter frames against
references/primary.png. Skin/stubble read more photographic than the painted
reference; the warm UE lighting further reduces readable facial definition.
These are visual observations, not a newly proven UV or material-binding bug.

Next is a separate reference-conditioned face-only texture revision preserving
identity, geometry, UVs, hair, and all other work. Target cleaner painted skin
and beard detail plus clear aligned eyes, brows and mouth. Require matched
front/oblique/both-side unlit and lit actual-mesh evidence, then UE close-ups.
Do not silently promote another attractive front image as a finished texture.
No replacement has been generated for this feedback yet. Durable review hold:
`work/sunset-ayric-rigid-head-v1/evidence/user-face-revision-v003.json`.
