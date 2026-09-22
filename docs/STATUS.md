# Current status

*Type: reference*

Last updated: 2026-09-22. This file holds the current state only and is
rewritten in place. History is in [HANDOFF.md](HANDOFF.md) (append-only,
dated); failures and retained lessons are in [DECISIONS.md](DECISIONS.md);
scoped open work is in [AGENT_TASKS.md](AGENT_TASKS.md). The stage names below
are the ledger stages listed in [PIPELINE.md](PIPELINE.md#ledger-stages).

Every `work/`, `out/` and `output/` path here is on the development workstation
and ignored by Git. Nothing in this repository is production-ready; the
checked-in cohort snapshot (`docs/evidence/v1-cohort-audit-current.json`)
truthfully reports 0 of 7 assets ready.

## Moonlit tavern scene candidates (browser, outside the UE cohort)

The user commissioned a complete scene before creative approvals. Ten reference-
conditioned assets are generated and textured: innkeeper, quadruped tabby, room
shell, table, chair, bench, lantern, tableware, rug and a static hearth insert. A source-conditioned
flagstone tile repairs the painter's plain floor on the existing room surface.
The original 22-instance scene is retained as a fallback. The modular rebuild
now holds 62 editable instances with warm/cool local lights. No human
approval or UE production certification is recorded.

Current artifacts under ignored `work/moonlit-tavern/`:

- `innkeeper/face-v4/projected-final-v3/innkeeper.glb` and `.blend`: texture
  authority from browser revision 4, 48k triangles and the original 86-bone body rig. Separate
  4096 head/clothing PNG atlases, 2048 exposed skin, repaired shading normals
  and feathered atlas joins. Camera-aligned face/hair colour repair in v4.
  Original `final-v2/innkeeper/` remains preserved;
  its five body stress poses passed. Simplified fingers and facial silhouette
  still need geometry refinement for detailed articulation and close shots.
- `final-v2/tabby/tabby.glb` and `.blend`: 48k triangles, 30-bone quadruped rig;
  all ten limb, spine, head, tail, ear and jaw stress poses pass. Final guides
  and evidence are in `tabby/rig-prep-v3` and `tabby/rig-v3`.
- `final-v3/room-shell/room-shell.glb` and `.blend`: 100k triangles, 4k room
  paint, explicit planar flagstone material. Geometry retained.
- `final/<table|chair|bench|lantern|tableware|rug|hearth>/`: textured GLB/native pairs.
  Tableware uses `remesh-v2` and `uv-v2`, preserving all three source components.
- `BRIEF.md`, `assembled-scene.json`, `studio-import.json`, source images and
  per-stage receipts retain the local construction trail and review state.

The current environment uses **`modular-v1/` plus `shelf-stock-v1/`**, not the
original room shell. Seven isolated source-derived references conditioned separate
AI geometry and paint: fireplace, stairs, stocked bar, window, wall bay, braced
post and beam. The acquired floor is retained with 1,783 underside triangles
copied as shallow flagstone infill beneath recesses exposed by the old fixtures.
Its original 8,227 triangles remain unchanged. The eight architectural masters
formed the earlier 43-instance assembly. The fused stocked bar has since been
replaced by an empty shelf, separate counter and individually acquired stock.

- `modular-v1/final/<flagstone-floor|stairs|bar|window|wall|support|beam>/`:
  packed native/GLB masters. Fireplace uses `final/fireplace-finished-v2/`,
  with a measured soot material on the formerly streaked firebox interior.
- `modular-v1/assembly-final-v1/tavern.blend`: assembled native scene with
  shared master data and independently placed objects.
- `modular-v1/scene-after.json`, `library-import.json`, `layout.json` and
  `review-binding.json`: Framewright scene v8, 43 placements, actual imported
  hashes, and working shot v4. `browser-review.png` is the actual browser still.
- `modular-v1/fallback-scene.json`: original room scene retained separately.
  `reference_manifest.json` retains source lineage and rejected timber cuts.

The latest bar update is **`shelf-stock-v1/`**:

- `final/<shelf-finished|counter-finished>/`: empty oak furniture, source-bound
  horizontal wood material repair with unchanged geometry. Raw paint is retained.
- `final/<bottle|tankard|jar|pitcher>/`: four separate textured GLB/native masters,
  repeated as 18 independently editable stock instances. The jar lid is static;
  the bottle material is opaque. No rig is needed for these props.
- `layout.json` records measured shelf contact under each item and adjusted
  heights for the two retained counter settings. `stock-clearance-final.json`
  reports no stock bounding-box overlaps; it is not an exact mesh collision test.
- `scene-after.json`: Framewright scene v10, 62 available instances. The user
  inspection camera, lighting, character poses and unrelated objects are retained.
  `fallback-before-stock.json` preserves the previous fused-bar scene separately.
- `review-binding.json` and `detail-review-binding.json`: actual browser room
  shot v5 and shelf-detail shot v2, both bound to scene v10 at 1536x1024.
  `browser-review.png` and `browser-detail.png` are the corresponding stills.
- `assembly-final/tavern.blend`, individual masters, references/prompts,
  `visual-review.json`, `runtime-review.json` and `delivery-validation.json`
  retain the local review and export evidence. Framewright's local delivery
  directory contains `SHELF-STOCK-HANDOFF.md` and versioned project/native ZIPs.

Shelf and jar paint attempts were refused before inference for insufficient
VRAM; fresh admitted attempts are explicit `texture-v2` derivatives. The tankard
painter faulted after writing validated output; independent reload and fixed-view
review passed, but this is not a clean painter-process exit. Human gates remain open.

The preceding regional UV update is retained under **`innkeeper/detail-v3/`**:

- `uv-v16/uv-report.json`: 1,321 original UV islands become 517 across three
  sheets: head 2, exposed skin 4, clothing 511. Occupancy is 47.40%, 53.04%
  and 49.42%, respectively. Finite/noncollapsed UVs and sampled overlap under
  0.1% of occupied pixels pass; clothing fragmentation is reduced, not solved.
- `head-paint-attempt002/` and `clothing-paint-attempt002/`: fresh source-crop
  AI paints with unchanged geometry/UV receipts. Both faulted during native
  teardown after validated PNGs were written. Independent reload, bake, export
  and fixed-view review passed; the failed execution receipts remain failed.
- `combined-v2/`: selected GLB/native, maps, paint receipt, ten face close-ups
  and twelve full-body views. SHA256 of GLB:
  `0b16accdce3c5e36bbca9eb8f0a3c5dee5fe51a479756f0fae5d582f709513ef`.
  It is 35,007,904 bytes. `export-audit.json` proves source/export position and
  skin-weight triangle correspondence, joint order, rest transforms, hierarchy,
  inverse bind matrices and mesh world transforms unchanged.
- `library-revision.json`, `imported-model-profile.json`, `scene-after.json`
  and `delivery-checks.json`: Framewright asset
  `93693a46-c933-49f3-b08f-a0fe295def40`, revision 3, scene v11. All 62 placements,
  camera and lights retained; only the innkeeper's asset binding changed.
  Browser rig profile still passes all 86 bones, bind and 40,184 split-vertex
  weights. Prior shot stills retain their scene-v10 snapshots.

The latest innkeeper update is **`innkeeper/face-v4/`**. Its selected
`projected-final-v3/innkeeper.glb` and packed native change only head BaseColor.
All vertex attributes/indices, UVs, normals, rig and other five embedded images
are unchanged. GLB SHA256:
`5c0c4949e9e5e8d6553a7d605c3ae5eb36e5bda5fcb876c5fdbd36fa33d83dbc`.
It is 33,751,708 bytes. A camera-aligned AI donor softens facial lines, improves
skin/beard detail and repairs false skin bands in the hair. Front, both
three-quarter, side, back and body views are retained. Framewright uses asset
`d8a5560a-772d-4b74-87aa-9febcf3816dd`, revision 4, scene v12, 62 placements.
Earlier revisions remain intact. The [face study](INNKEEPER_FACE_STUDY.md)
records rejected geometry/full-head paint candidates, exact evidence paths,
working delivery, and remaining geometry/facial-rig limitations.

The reusable [regional texture route](REGIONAL_CHARACTER_TEXTURES.md) lives in
this compiler. It is an explicit operator workflow for the supported rigged
humanoid authority, not a new automatic Framewright generation default. No
human acceptance, facial rig upgrade or UE certification is implied.

The user rejected the cat's original face. `tabby/head-replacement-v3/` is
**not promoted**: facial features improved, but the replacement bust still has
an abrupt neck join and oversized silhouette. Its rejection receipt names the
next gate. The live scene keeps the original rigged cat pending a proper repair;
do not describe the face as fixed. Both neutral character poses are unchanged.

The room is a working cutaway, not a photoreal reconstruction. Windows retain
opaque painted panes; no exterior or glass-transmission claim is made. Human
creative approvals remain deferred. See [MODULAR_SCENE_ASSETS.md](MODULAR_SCENE_ASSETS.md)
for the reusable extraction, source-binding and inspection workflow.

Both final character GLBs pass Framewright's skeleton, bind and weight checks
against explicit 50k **browser** profiles. Canonical 20k profiles are unchanged.
These are animation-capable working assets, not approved character designs.

The user **rejected all four `animation-v1/` clips** on 2026-09-22. The innkeeper
idle moved around the A-pose and returned to identity at the loop endpoints.
Its mechanically valid animation was not a usable idle. The old human revision 5
and cat revision 3 remain as rejected evidence; their library notes say so.
The cat's binding is unchanged pending separate work, and its face remains rejected.

The active correction is **`idle-v2/candidate3/held-pose.glb` and `.blend`**,
Framewright innkeeper revision 6 (`10dbd3ac-ed4a-443b-8cd1-a191c2f58f8a`), scene
v14. It contains only `Innkeeper_Relaxed_Idle`: a two-second **held pose**, with
arms down, softly bent elbows, palms inward and light finger curl. Breathing and
other animation are deliberately deferred until the stance has been reviewed.
The v4 mesh, UVs, texture bytes, weights, hierarchy, rest transforms and inverse
bind matrices are unchanged. Other scene instances, placements, camera and lighting
are preserved. The native and reimported GLB each received four-view inspection;
the real consumer shows the same pose at the start and end. Human approval pending.

`scripts/blender/author_held_pose.py` and the hash-bound innkeeper recipe reproduce
the pose. `check_relaxed_idle.py` checks the exported clip: the rejected v1 fails;
all 49 samples of the replacement pass. These are mechanical stance checks,
not automatic visual acceptance. See [CHARACTER_ANIMATION.md](CHARACTER_ANIMATION.md)
and `docs/evidence/innkeeper-held-idle-v2.json`. The full RAC gate passes 608 tests,
7 skips and 169 subtests. Neither character has a facial rig, and detailed fingers
remain limited. `rac export-animations` still packages chosen clips or none;
both paths were checked on the served revision without changing its base payload.

## Stillwater lakeside village (Three.js demo, outside the UE cohort)

Finished showcase video: `out/stillwater-showcase-2026-09-16/Stillwater-showcase-1080p.mp4`.
23.5 seconds / 1920 × 1080 / 30 FPS / 705 frames / silent H.264 fast-start MP4,
28,113,175 bytes. SHA-256:
`3e4f73d3d11973bf1c819d03c6c724016676c3ffa01f3f5300119b6546ddb21e`.
An optional cover JPEG is alongside it. Actual Three.js browser renders show
the finished world, supplied source, cabin rotation, real wireframe/reference
controls and a shortened four-stage workflow. Capture automation is under
`apps/lakeside-village/video/`; evidence under
`work/lakeside-village/evidence/showcase-video-v1/`. All 705 frames decode with
constant timing; moving segments contain no repeated frames. Browser playback
completed in 23.508 seconds with no stalls/errors (1 reported dropped playback
frame). No site deployment or LinkedIn posting occurred for this video task.

Companion thumbnail: `out/stillwater-showcase-2026-09-16/Stillwater-thumbnail-1080p.jpg`
(1920 × 1080, 530,220 bytes), with original generated PNG and saved prompt alongside.
This is an AI-composed promotional image based on actual world and wireframe
captures, with enhanced sunset lighting and typography; it is not an unaltered
browser screenshot. The original video cover remains available.

Published showcase: **https://markbhall.dev/stillwater/**, deployed through the
existing `raydeStar/markbhall.dev` GitHub Pages site. Latest site commit:
`185c150a4edde6a2fe8896381885af9f04c1508e`; successful deployment run
`35014189812`. The main website links to Stillwater from its shared navigation
(including mobile) and a screenshot feature above Latest writing. The showcase
has a 1200 × 627 real-scene social card with Open Graph and Twitter metadata.
The page identifies Reference Asset Compiler, credits Mark Hall
and Codex, explains the reference/geometry/cleanup/paint/assembly workflow, and
links to this public repository and its pipeline/playbook. It distinguishes
the compiler's verification role from AI generation and the browser presentation.

The public release has 60 files / 68,302,900 bytes. Every actual public HTTP
response matched the published file's SHA-256, including all seven accepted
original GLBs, seven smaller browser derivatives and social/homepage images.
Homepage HTML and committed stylesheet bytes also match. Desktop and 375px
layouts, all seven selections, independent inspector orbit, wireframe, original
download destinations and on-demand references passed; the public scene loads
7/7 with no console errors. LinkedIn Post Inspector redirects to sign-in;
the user chose to handle LinkedIn manually. Its preview refresh is unverified;
no LinkedIn post was created.

The browser derivatives use 1024px WebP textures: 32,468,236 original GLB bytes
become 12,504,896 runtime bytes. All non-image buffer bytes, mesh/accessor/node
definitions and material parameters are independently verified unchanged.
Originals remain the full-resolution download authorities. Thumbnails total
56,560 bytes; the homepage teaser is 52,442 bytes. The inspector reuses the scene
library, initializes when visible, and offscreen panels stop rendering.

A controlled local 2 Mbps / 150 ms, no-cache, gzip transfer pass at a 375px
viewport measured 51,636,362 -> 11,350,757 wire bytes; full scene readiness
222.531 -> 53.782 seconds. The new poster arrives in 2.282 seconds, before
the interactive world is ready. Measurements use server-observed wall time on
the desktop GPU, not a physical phone or CPU throttle. Before/after used the
same navigation-then-resize procedure; a separate fresh mobile reload proves
the inspector has no canvas until scrolled into view. Evidence:
`work/lakeside-village/evidence/performance-v1/`; prior publication evidence:
`work/lakeside-village/evidence/pages-2026-09-15/`.

Editable local scene and independent asset inspector:
`apps/lakeside-village/`, served at `http://127.0.0.1:5178/`.
Run `apps/lakeside-village/start.ps1` to reopen from source. The static build is
`apps/lakeside-village/dist/`; fonts, models and images are bundled locally.
Preserved pre-publication bundle: `out/stillwater-threejs-cleanup-v3-2026-09-15.zip`
(60,330,214 bytes; SHA-256
`194360d28fb2e475a10d86ca030cd8fc27d1b8012da95bfe76d830e1f4c60e2f`).
The original and composition-v2 bundles remain preserved.

Seven separate reference-conditioned AI assets: timber cabin, round cottage,
pine tree, dock, rowboat, shore stones, and barrel/crate supplies. Each has a
downloadable textured GLB. The scene has orbit controls, three camera presets,
reflective animated water and gently moving boats. The second viewport supports
independent orbit/zoom, auto rotation, wireframe and source-reference inspection.

Ayric explicitly accepted all seven delivered assets on 2026-09-15; the hash-bound
receipt is `work/lakeside-village/evidence/user-asset-acceptance-2026-09-15.json`.
The composition pass reshapes the inlet and foreground path, adds forest density,
low ground cover, warm porch lights and chimney smoke, and calms water reflections.
Scene tree instances have narrower X/Z scales; original GLBs and inspector
geometry retain their accepted proportions. **Reference view** is the default and restores the saved position,
target, FOV and zoom after exploration. It interprets the supplied composition;
fine pine branches, mountain detail and painterly clouds remain differences.
Scene-pass evidence: `work/lakeside-village/evidence/composition-v2/`.

Final cleanup: all 188 trees are seated by their root area against the rendered
terrain, preserving their horizontal arrangement. Both dock landings now overlap
dry ground; independent rays through actual planks and terrain measure 3.3/3.6 cm
surface gaps. The left dock moved toward its bank, with its boat given clearance.
Dock approaches are cleared, cabin lights softened, and mountain ridges varied.
Evidence: `work/lakeside-village/evidence/cleanup-v3/`; CPU diagnostic:
`apps/lakeside-village/audit_placement.mjs`. The seven accepted GLBs remain unchanged.

Evidence and exact hashes: `apps/lakeside-village/asset-manifest.json` and
`work/lakeside-village/evidence/`. All seven actual browser GLBs passed the
artifact audit: 247,795 unique triangles, complete UVs and embedded albedo,
maximum symmetric triangle-center difference from the UV inputs
`6.956712961492162e-7`. The served painted tree has one connected component.
The user's floating-tree correction removed 92 detached fragments / 101
triangles; rejected geometry and the cancelled pre-inference paint plan remain.

Original authorities and receipts: `work/lakeside-<asset-id>/`.
Texture authority is `paint-v1/painted.glb`, except tree `paint-v2/painted.glb`.
Ayric explicitly delegated this demo's visual reviews; hash-bound receipts are
under each asset's `demo-reviews/`. These are demo judgments, not a certification
of the UE production contracts. The formal workspaces have `generate_candidates`
recorded; further Three.js work is documented separately from UE ledger stages.

The painter repeatedly returned Windows exit `-1073741819` after writing its
final success message and geometry/UV report. All seven retained artifacts were
independently loaded and rendered from four views. No crashed inference was
retried, and clean process exit is not claimed. No inference remains running.

## Ledger cohort (`configs/v1-cohort.json`)

| Asset | Kind | Passed through | Next unresolved gate | Waiting on |
|---|---|---|---|---|
| `orange-adventurer-cat-ai-v2` | mascot | `ue5_import` (rig, deformation and headless UE import recorded; idle retargeted in the gallery) | `ue5_motion_review` | **Mark, in the engine.** Then `cook`. |
| `office-chair-ai-v2` | static_prop | Modeling, retopology and texture passed by Ayric; UE import passed (`docs/evidence/office-chair-ai-v2-ue-import-v1.json`) | `ue5_runtime_review` | **Mark, live editor and frame.** `cook` stays blocked until then. |
| `field-scout-female-ai-v4` | humanoid | `semantic_cleanup` | `production_retopology` | A guide- or landmark-aware quad route; every challenger so far is rejected (`docs/evidence/field-scout-female-v4-retopology-trials-v1.json`). Texture is a separate open rejection. |
| `field-scout-male-ai-v2` | humanoid | `generate_candidates` (Hunyuan multiview source hash-bound) | `modeling_approval` | **Mark**, on the fresh 70k derivative. The legacy runtime FBX has no receipt chain and stays regression evidence. |
| `ninja-man-ai-v3` | humanoid | `generate_candidates` | `modeling_approval` (rejected: mask, vest, wraps, boots, hands and feet lost) | A new image-conditioned acquisition. Do not rebuild the details in Blender. |
| `weathered-longsword` | static_prop | intake and route | `modeling_approval` | A formal pass through the static gates; the earlier candidate was "generally acceptable" but never ratified. |
| `sunburst-guitar-ai-v2` | static_prop | intake and route | `generate_candidates` | GPU. The earlier geometry and paint were rejected as rudimentary. |

The checked-in cohort snapshot predates the cat's membership (it still names
`fox-mascot-ai-v3`, retired by Ayric on 2026-09-01) and the chair's texture and
import receipts. Refresh it on the workstation with
`rac cohort-audit configs\v1-cohort.json --workspace-root work` before quoting
per-stage numbers. Exit 0 means every member is production-ready, 1 means the
cohort is intact but incomplete, 2 means usage error or `RAC_ERROR`.

Cat artifacts: recipe `recipes/orange-adventurer-cat-ai-v2-production.json`,
package `out/orange-adventurer-cat-ai-v2-production/`, ledger
`work/orange-adventurer-cat-ai-v2/state.json`, evidence
`docs/evidence/orange-adventurer-cat-ai-v2-*.json`. It carries Ayric's
texture waiver for texel density (about 20 texels/cm²) and confetti UV islands.

Chair artifacts: `work/office-chair-ai-v2` (1.019 m, 18,000 triangles, 4096
BaseColor parent at 427.8 texels/cm²), placed in `/Game/Compiled/L_RacGallery`.

## Sunset workshop and Ayric (scene demo, outside the cohort ledger)

Launcher: `scripts/play_workshop_demo.ps1 -Lighting <Night|Day|Ayric|AyricLegacy>`
on the workstation with its saved packages. Night (v026) is the default.

| Item | Current candidate | State | Waiting on |
|---|---|---|---|
| Ayric character | v051: `/Game/SunsetWorkshop/L_WorkshopNight_v051`, package `output/sunset-workshop-ayric-v051/Windows` | All 18 cooked checks pass (movement, collision, jump, attachments, native budgets). Body 12,574 v / 16,039 t; head 12,740 / 19,988; sword 11,123 / 18,000; LOD0 total 36,437 / 54,027. | **Mark: approve or reject the v051 neck.** A collar edge is visible close up; do not call it welded. `AyricLegacy` keeps v036. |
| Ayric body texture | `work/sunset-ayric-v2/prod-calibrated-v001` via `recipes/sunset-ayric-v2-production.json` | Fails baked-light correlation (-0.24 against 0.12); shipped under a waiver marked PROVISIONAL in Ayric's name. `texture_approval` is pending in the ledger. | **Mark: confirm or revoke the waiver** after in-engine review. Face/surface correspondence concern remains open; no further blind painter retries. |
| Ayric head | `/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production` | Image-conditioned head; texture gate passed without waiver (agent-delegated, head-only); native UE import and static review passed. | Nothing separate; judged as part of v051. |
| Ayric body mesh | `/Game/SunsetWorkshop/RigRepairs/neck_transfer_v012/ayric_body`, source `work/sunset-ayric-v2/rig/neck-transfer-v008` | v036 anatomical rig and animations shared; neck transfer replays exactly (`docs/CHARACTER_HEAD_AND_NECK.md`). | Hand roll under the retargeted idle is a known open item. |
| Manny demo | Day v018 (`output/sunset-workshop-demo-v018-r2/Windows`), Night v026 (`output/sunset-workshop-night-v026/Windows`) | Both cooked; 13 editor and 12 packaged checks pass. No physical-keyboard test is claimed. | Complete as a local demo. |
| Plant | `out/sunset-plant-production`; native-v002 material fix in `/Game/SunsetWorkshop/Optimized/` | Texture passed (delegated); native-v001 import receipt passed but is visually rejected for a bumpy normal; native-v002 removes it but is not a ledger revision. | A warmed native review and an explicit material-derivative lineage. |
| Sofa | `work/sunset-sofa` `prod-region-v009` | Passes texture and four-view native review; `prod-delighted-v004` rejected. | Nothing open for the demo. |
| Sword (scene) | Attached to Ayric in v051 | Native import (1.35 m, 11,123 LOD0 vertices) and six-frame static review passed; attachment error zero in the cooked audit. | Nothing open for the demo; the cohort `weathered-longsword` ledger is separate. |
| IntrinsicAnything albedo challenger | `workflows/texture/intrinsicanything/` | Stopped after three bounded failures (`docs/ESCALATE-sunset-lighting.md`). | Not to be resumed without a different method. |

## Workstation-bound facts

- The GPU was owned by the user's other project on 2026-09-11; no inference
  was launched for the maintenance release. Check `nvidia-smi` before any AI
  stage. Thresholds are MiB: 21,504 for paint, 12,288 single-view, 18,432
  multiview geometry.
- AI stages need the studio tree named by `RAC_LEGACY_ROOT`
  (`docs/AI_STAGES_SETUP.md`). Run `scripts\workflow_doctor.ps1 -Profile
  geometry|texture` to see what is present without launching anything.
- The head fit and neck transfer used no GPU; they replay on CPU with
  `scripts/run_neck_transition.ps1`.
- Open interactive Blender, ComfyUI and Unreal sessions may own files under the
  studio tree. Preserve them.

## Decisions that need the user (Mark / Ayric)

1. v051 neck: approve or reject.
2. Ayric body texture waiver: confirm or revoke.
3. Cat `ue5_motion_review` in the gallery.
4. Chair `ue5_runtime_review` in the gallery.
5. Female retopology route and male modeling approval on the 70k derivative.

Until those land, no ledger promotion, no "production-ready" wording, and no
relabelling of a retained failure as a pass.

## Release state

`v0.1.2` completes the follow-up maintenance review; notes in
[releases/v0.1.2.md](releases/v0.1.2.md) and the
[completion checklist](MAINTENANCE_REVIEW_2026-09-11.md).
`v0.1.1` was the first reliability maintenance release, and
`workshop-2026-09-06` carries the workshop showcase. Root `CHANGELOG.md` links them.

The follow-up maintenance review strengthens receipt requirements. The asset
matrix above summarizes recorded history, not a fresh certification under those
requirements. Re-audit a workspace before resuming it; missing legacy bindings
must be resolved with evidence, not by relabeling the old record as passed.
