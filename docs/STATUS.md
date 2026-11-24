# Current status

*Type: reference*

Last updated: 2026-11-23. This file holds the current state only and is
rewritten in place. History is in [HANDOFF.md](HANDOFF.md) (append-only,
dated); failures and retained lessons are in [DECISIONS.md](DECISIONS.md);
scoped open work is in [AGENT_TASKS.md](AGENT_TASKS.md). The stage names below
are the ledger stages listed in [PIPELINE.md](PIPELINE.md#ledger-stages).

Every `work/`, `out/` and `output/` path here is on the development workstation
and ignored by Git. Nothing in this repository is production-ready; the
checked-in cohort snapshot (`docs/evidence/v1-cohort-audit-current.json`)
truthfully reports 0 of 7 assets ready.

<!-- clanker-sentry-regular-rac-v001:start -->
### Sentry: Rodin rig review Pending (2026-11-13)

<!-- rodin-sentry-rig-v002 -->
**2026-11-13: Rodin split and rig review delivered, Pending.** User approved the replacement modeling. Fourteen rigid objects, friendly Gate glass eyes, new measured Route B landmarks bound to production `3a9c08840e4f9aa80867d41e6894df5b0708a166eb47be148395dbd6776302b0`. Both looks are Framewright v4 with 11 embedded clips, skeleton overlay and five-pose sheets. 110 cm to antenna tips, elite 58,048 triangles, 4K/2K maps. FBX reimport and rigid-weight checks pass. Armour collisions at extreme poses and head nod limit remain explicit review items. Framewright generic 20k budget flags the elite payload; no missing/unexpected bones. See C:\Users\Ayric\Documents\Unreal Projects\ClankerHeroes-art\sentry\rac\rodin-v002\README.md. Unreal follows acceptance; no import yet. All local build/render work CPU; zero additional credits.

<!-- clanker-sentry-regular-rac-v001:end -->

<!-- clanker-knight-hero-rac-v001:start -->
**Clanker knight RAC, 2026-11-13 - ROUTE A RIG REVIEW, awaiting Ayric.**
Workspace `work/clanker-knight-hero-rac-v001/`. Model, retopology, UVs and all 13 parts unchanged (59554 triangles). Ayric explicitly authorized rigging while texture rework/approval remains open.
Route A `rig/route-a-v001/`: `run_rig_candidate.ps1 -Backbone landmark -Landmarks` with Claude production-bound `knight-landmarks-ue5_manny.v009.json`, payload SHA256 `4c1560b83606d931d9c266a796907c841acc771e187b8eaeba6b0d74828c7ff9`. No auto placement. Added opt-in source-bound rigid-part support to RAC; legacy single-mesh path regression passes.
Skeleton gate and five-pose suite passed. 86 bones plus root armature node; 13 one-hot weighted rigid shells. Forbidden finger/metacarpal/twist/IK bones remain non-deforming in native rig/unweighted in FBX. Mitten hands follow hand bones; thumb_01 deform-enabled but unweighted. Whole boots follow calves (no separate ankle flex).
Delivery `C:/Users/Ayric/Documents/Unreal Projects/ClankerHeroes-art/knight/rac/v001/rig-review-v003/`: start `REVIEW.html`. `SK_Clanker.fbx` uses centimetres, binary UnitScaleFactor 1 and root local scale 1; native `.blend`, metre FBX, 2K placeholder maps, overlay, five poses and joint close-ups included. Actual delivery round-trip preserves topology, UVs, parts and weights. v001/v002 packaging failures retained and labelled.
**Visual issues for review:** large bends open knee and waist joins; helm nod opens neck join. All shells stay rigid within 0.01 mm, but this does not imply acceptable joint coverage. `rig_and_skin` and `deformation_validation` are in progress pending human review; no production-ready claim.
Texture review remains separately open: `textures/review-v009`, Framewright Clean / Wear A-D revision 2 Pending, delivery `texture-review-v002/`. No new material work in this rig task.
CPU only, 0 credits, no Unreal project writes/import, no animation clips. Full RAC verify and 3 real-Blender regressions passed. STOP at rig review.
<!-- clanker-knight-hero-rac-v001:end -->

<!-- remora-airship-20261106:start -->
**Remora airship hero, 2026-11-06 - clean tunic and canonical surface workflow.**
Work: `work/remora-airship-20261106/`. User delegated modeling, topology and
texture visual gates, selected **B - Braided knot**, and likes the outfit/body/
hands and new hair. Preserve those approvals. Original face concept remains
the likeness authority: graphic stylization, blue-grey eyes, one scar through
the anatomical LEFT eyebrow. No overall AAA or production-ready promotion.

Current review delivery: `delivery70/Remora_Tunic_Clean.glb`, SHA256
`09a154930aed5655fadaea06f1e64e3dcff2b57cc869491960f0c9ade62019cd`.
Packed/reopened Blender copy is adjacent. Framewright asset
`7f906337-1900-4cbf-9115-0bf94b518642` has the same content hash and is open in
Director Mode. Front and both quarter closeups are retained in
`framewright-review70.json` and `delivery70/remora70-*.jpg`; orbit/zoom work.
This is actual model-inspector lighting, not a saved Scene or cooked runtime.
Previous face/collar64 delivery and consumer evidence remain retained.

Tunic68 diagnosis proves the pale S curves are paint ghosts on continuous clay.
A retained AI edit conditioned by exact color/clay guides and the outfit concept
removes their outlines/shadows. Tunic69 missed the upper slope and is rejected;
tunic70 corrects measured depth bounds, repairs 29,260 atlas texels above 50%
blend and softens obsolete relief. All geometry, morphs, UVs and weights, plus
all non-outfit materials/maps remain exact. New generic operating standard:
[CHARACTER_SURFACE_WORKFLOW.md](CHARACTER_SURFACE_WORKFLOW.md). The actual RAC
recipe is `examples/polish/remora-tunic-ghosts.json`; `replay71` matches the final
GLB byte for byte. See [canonization evidence](evidence/remora-surface-canon-20261106.json).

Latest fixes: `diagnosis59` separates color, clay and object/component IDs.
`repair60` removes five verified detached old-scan hair remnants (297 triangles)
from the body, keeping every retained vertex attribute and triangle exact.
Teeth/tongue had all 34 expressions set to 1; resetting them to neutral removes
the chin protrusion while preserving all morph targets. Bounded underjaw
relaxation moves 522 welded vertices by at most 3 mm, with no turned triangles.
`skin62` retains the two registered AI guides and exact prompts; `skin64` repairs
nostril paint and adds restrained cheek warmth, with softer skin/neck response.
Broad `skin63` projection is rejected for pale jaw fringe. Hair, scalp cap and
eyes remain exact. See `delivery64/verification.json` and `checkpoint67.json`.

Hair lineage: approved B conditioned head-supported Pixal34; donor face was
support only. Connected extraction39, dense clearance, conservative shell51,
26k reduction and rebake yield the accepted braid/knot. Consumer material58
uses hair normal strength 0, roughness .62, base factor .25 and specular .2.
Earlier disconnected/collapsed/missing-scalp attempts remain rejected evidence.
Dedicated eye55 repair retains recessed globes and tightly registered lashes.
Original body topology/UV fixes13 and registered outfit14 maps are retained.

Repeatability: `scripts/replay_acquired_hair.py` and
`examples/polish/remora-braided-knot.json` are the hash-bound CPU hair route.
`replay57` reproduces the hair mesh and base color byte for byte; its normal
map differs at three pixels by one 8-bit level (map currently disabled).
The local face/collar replay is `replay65/replay.py --out <new-directory>`;
`replay66/receipt.json` proves the final delivery GLB is byte-identical.
New characters still require reviewed component selections and AI references.

Repository verification: **1007 passed, 39 skipped, 198 subtests**, lint,
344 stage-file syntax checks and wheel/installed-wheel checks passed again
(`verify-canon70.log`). Canonization adds documentation/routing and a real
registered polish recipe; no core algorithm changed in this pass. Scoped tunic
repair is accepted under the delegated visual gate. User can inspect the open
model; inherited neckline/armhole and facial geometry remain outside this patch.
Full-character topology, rig/deformation and cooked-runtime acceptance remain open.
**Eye detail approved and formalized, 2026-11-06.** Mark approved eyes73
(`eyes73/run/Remora_Eye_Detail.glb`, SHA256 `93afce20...faf752a`, Framewright
`4fe48374-aa25-4df7-9bec-4771cb75a38a`): lid-margin lashes + eye occlusion,
append-only over delivery70. Now the registered `eye-detail` polish stage with
`pronounced`/`subtle`/`none` lash presets ([EYE_DETAIL.md](EYE_DETAIL.md)).
`rac polish examples/polish/remora-eye-detail.json` replays it byte for byte
(`eyes74/replay`). Subtle/none variants for comparison: `eyes74/{subtle,none}`.
Evidence: [remora-eye-detail](evidence/remora-eye-detail-20261106.json). Next face
gates: skin (emissive map currently bound on `skin`), brows, hairline. No rig,
cook or production claim.

**Skin response candidate skin75/sweep02 (pending Mark).** Diagnosis: uniform
roughness 0.675, flat normal map, uniform specular (the bound emissive map is inert:
no emissiveFactor). `material-sweep` with a landmark-placed zone mask (skin, lips,
brows) and `skin75/remora-skin-profile.json` adds zoned response and pore normals.
sweep01 rejected in Framewright (nose-bridge zone stripe, wet lips). Base colour is
unchanged and still reads flat orange; that needs a registered AI skin repaint.
Receipt `skin75/review.json`; Framewright `f0092204-7d88-4019-a4e6-1cf590daa805`.

**In the game, 2026-11-07 (game86 -> game90).** Remora plays as the player in The Aether Wars
(session-only swap; Character02 stays the saved default). Mark picked face D in game, and passed
the mesh with the healthy-skin repaint v2 (`face89/skin/Remora_Skin.glb`, jaw seam fixed). Hair
read a little plastic: Unreal hair shading along a baked flow map (`hair_flow_soft`)
was the fix: Mark liked the soft look, now the default (V6 also sways the front locks in play).
The route is now the paved [game review road](GAME_REVIEW.md):
`scripts/run_game_review.ps1` with `game90/game-review.json`; attempts in `game90/attempt0N`
(03 and 05 are recorded failures). The body was envelope-weighted (heat failed); step 02b
rebinds by heat on a voxel stand-in; step 02a fits the hand joints to the hands (V5, attempt07). V7/V8 sampled every player animation (attempt09/10); Mark: the animations do not pass yet (revisit after the face). Face (V9-V11, attempt12-14, `-Face`): corrected lip-sync gain name, teeth at the game's brightness, blink smear repainted, teeth seated and tongue on the jaw; Mark passed the face in game (V11), and both face fixes are road defaults. Animations, 2026-11-09: V12 (attempt15, Character02's pre-reset library set)
ran hunched with flung arms; V13 (attempt16) is the game's Manny-first base with her own retarget calibration and
Mark's pick F, a subtle feminine gait (`unreal.retarget_pose` / `gait_style`; candidates in
`work/remora-run-20261109`). V14-V22 followed Mark's play sessions the same day: shoulder weights, glider grip, a
frame-by-frame clip review, boots, jog hands, the backward walk and fall, then the hips from behind and the
trousers through the tunic. Mark on V22 (attempt26): "Looks right ... that looks really good, thank you"; the hip
release and layer follow are road defaults. V23 (attempt27, 2026-11-10) is the same build with her own climb reach
(`unreal.climb_reach`): on the game's rewritten climbing every climb and ledge move works for her, but on the hero's
numbers her fists sat 13 cm under a ledge's lip; hers (193.5, 74.5, 57) put her hands on it (Mark: "Yes, add them";
`work/parkour-revamp-20261109/sheets/remora_07_game_review.jpg`). On the new climbing her shimmy goes hand over
hand, so that review finding is closed. V24 (attempt32, 2026-11-10): Mark saw "an extra bone" in her arms; the
rig's elbow joint sat 8 and 4 cm below her elbow and the wrist joints off her wrists, on an arm mesh of normal length.
`arm_joints: measured` finds both on the arm (elbow at the centreline's bend, wrist past the thinnest girth, both
arms alike), the hand fit lands all 24 finger joints inside each hand, her climb reach was found again (191, 76,
55.5) and the idle, walk and jog arm tweaks tuned on the old joints are gone
(`work/remora-arms-20261110/sheets/`, `work/parkour-revamp-20261109/sheets/remora_08_arms.jpg`). V25 (attempt38; rig attempt33,
2026-11-10) answers Mark's "shoulder ... just bending wrong": the shoulder joints are found in her shoulders
(`arm_joints: measured_shoulder`; they were 2 cm low and 2-5 cm too far out) and the tunic round the armhole stays
with the torso (`bind.armhole_hold_cm`), so its shoulders no longer stand out when she hangs
(`work/remora-shoulder-20261110/sheets/`). Mark played V25 on 2026-11-10 and passed the shoulders ("Looks right"); measured arm joints and the armhole hold are now the road's defaults. Her climb
reach was found again on the V25 arms (195, 75.5, 56.5; final build attempt38; gym check
`work/parkour-revamp-20261109/sheets/remora_09_v25_reach.jpg`). Open: the upper arm's roll landing at the shoulder, the death fold, and her attacks are stand-ins
until her rapier exists.
No rig, cook or production claim.

<!-- remora-airship-20261106:end -->

**Raider ear alignment, 2026-11-06.** Candidate06 is now the current ear-review
derivative: `work/raider-polish-20261105/review-candidate06/Raider.glb` and
packed `Raider_Native.blend`. The stamped outline came from painted landmarks
offset from the acquired ear contours; interior and upper-fold pinches also
needed bounded cleanup. Clay-led AI references were registered back onto both
ears. Rendered vertex movement is at most 4.001mm; indices, UVs, weights, morph
deltas, skeleton and held clip are unchanged. Outfit/eye/mouth materials and
images are identical. Candidate05 and Field Pouch authorities are preserved.

`examples/polish/raider-ears.json` replays the retained references through RAC.
`ear-alignment-20261106/finish04/` has thirteen fixed/light/closeup views;
`replay05/` reproduces the exact final GLB with review rendering omitted.
The geometry region choices remain asset-specific; new AI generations still
need review. Guide capture now supports explicit opaque material subsets,
recording omitted surfaces rather than silently skipping transparency.
Verification: **992 passed, 39 skipped, 198 subtests**, lint, 343 parsed files,
isolated wheel, exported held-pose and 24-image packed reopen checks.
[Ear evidence](evidence/raider-ear-alignment-20261106.json) retains sources,
prompts, rejected attempts, both consumer profiles and the replay. Artist
acceptance is pending; no AAA, natural-motion or cooked-runtime claim.

**RAC surface finishing port, 2026-11-06.** `rac polish-init` and `rac polish`
now create and run retained finishing recipes. Six shared stages add surface
inspection, POSITION bounds, acquired-face restoration, UV/map transport,
registered reference capture and packed CPU review. They compose with existing
reference-patch, material-sweep and prune-payload. Explicit concept-bound AI
requests pause with exit 3 and resume from verified checkpoints; no image
generation is dispatched automatically. See [finishing workflow](POLISH_WORKFLOW.md)
and [example recipes](../examples/polish/README.md).

Two final runs, `work/raider-polish-20261105/rac-replay03/` and `rac-replay04/`,
reproduce the exact Candidate05 GLB hash. Resume leaves all completed files
untouched. Open `rac-replay04/steps/review/Review.html` for eleven fixed/light/pose
views and the packed GLB-import review copy; the authored native master remains
the authority. `rac-cuff-replay03/` proves map transport on an earlier cuff:
917 triangles retain position/normal/skin data exactly, and matched front/back
renders retain stitching/wear/highlights. Existing source defects are not approved
away. `rac-ai-handoff02/` demonstrates a prepared real four-view request only;
it is intentionally waiting, with no inference job running.

Port baseline verification: **991 passed, 39 skipped, 198 subtests**, lint, 343 stage
parses and isolated installed-wheel replay/resume. The approved Candidate05
GLB/native and Field Pouch GLB hashes are unchanged. Retained failures include
xatlas collapsing thirteen tiny acquired triangles (resolved with bounded chart
isolation) and hidden bone-display geometry skewing the first review framing.
[Port evidence](evidence/raider-polish-pipeline-20261106.json) binds the inputs,
toolchain, repeated outputs, render checks and original-authority hashes.
Full upstream anatomy/weight editing still includes asset-specific decisions.
The port itself did not promote a ledger gate or import a new model; the later ear review above does import Candidate06.

**CH-03 Raider quality pass, 2026-11-06 — review checkpoint, no AAA acceptance.**
The original approved Field Pouch remains unchanged. Current work is
`work/raider-polish-20261105/review-candidate06/Raider.glb` and packed
`Raider_Native.blend` in that directory. Candidate04 and its review page remain.
The artist approved candidate04 appearance except a small collar hole.
Candidate05 restores 12 exact acquired triangles and registered cloth detail;
all existing surfaces and maps remain unchanged. Replay was byte-identical,
the ten-edge hole is closed, and all 50 exposed-skin samples in it are gone.
Static collar checks, exported held pose and packed native reopen pass.
See [polish explanation and replay](RAIDER_POLISH_REPLAY.md).
Registered outfit/skin/cuff references, material response, fitted sleeve borders,
collar lining, repaired facial and torso weights, mouth controls, and a relaxed
held stance are retained. A damaged ear was replaced from the opposite acquired
ear, welded at its root, isolated in UVs, and repainted from a registered
AI-edited side reference. Earlier ear attempts are retained as rejections.

The native rig, exported pose and packed reopen checks pass. Static diagnostic
poses and moving-light Blender renders are retained; they are not natural motion
or consumer acceptance. Repository verification passes 992 tests, 39 skips and
198 subtests, plus lint, syntax and isolated-wheel replay checks. Reusable `reference-patch` and
`prune-payload` stages have tests and [workflow documentation](REFERENCE_PATCH.md).
The complete polish pass still includes asset-specific geometry and skinning work.

**Framewright is working, 2026-11-06.** Explicit launch escalation succeeded.
Restored 34 missing static web files from a hash-matched local package. Current
candidate is imported as **Raider - Quality Candidate 06 - Ear Alignment** and open in Assets
Director Mode at http://127.0.0.1:5191/. Orbit and zoom were exercised with the
relaxed held pose selected. Its served SHA-256 is
`490a543d835c5e6cca9f8fc131abf1b339f291fb0f289a038ebf6da0f6b8fd28`.
Candidate04 import required missing POSITION bounds on accessor 277; the derivative
adds only computed min/max metadata, preserving every binary byte. The original
candidate, native file, Field Pouch asset and saved scene remain unchanged.
Launch and bounds receipts remain in `work/raider-polish-20261105/framewright-review-20261106/`.
Current import, served bytes, native reopen and ear profile/quarter screenshots are
in `work/raider-polish-20261105/review-candidate06/`.

**Next gate:** artist confirmation of the ear alignment, then Scene-lighting comparison, natural
motion/equipment behavior and the required cooked UE result. Assets viewer
visibility is verified; it is not AAA or production acceptance. Shared `repair-bounds` now runs in the finishing recipes and new
surface accessors include POSITION bounds. Unrelated legacy exporters have not
been retrofitted. [Checkpoint evidence](evidence/raider-quality-20261106.json)
retains the previous launch rejection and Candidate05 import identity; the current import is bound by the ear evidence above.

**CH-03 Raider material review, 2026-11-03.** The saved **Raider material review**
scene in Framewright now opens on the right thigh pouch of **Raider - Field Pouch**
(scene v5). The artist liked the previous fitted repair; it remains in the library as
**Raider - Continuous Outfit**. The new derivative uses concept-derived broad
and end views on the same fitted geometry. The artist liked the new pouch finish.
The next visual check is the whole outfit at shot distance, followed by a look
at the pouch and straps in the saved stride pose. The delivery folder includes
`Raider_Full_Character_Review.jpg` with four Framewright Scene views.
Open `work/raider-pouch-20261103/delivery/Review.html` for
12 before/after cameras in each lighting setup or open `http://127.0.0.1:5191/` and
choose Scene. [Pouch references and method](RAIDER_SEAM_REPAIR.md#outer-thigh-pouch) ·
[pouch evidence](evidence/raider-pouch-20261103.json) · [previous fitted repair](RAIDER_SEAM_REPAIR.md#fitted-outfit-for-framewright) ·
[repair evidence](evidence/raider-continuous-20261103.json) · [material workflow](MATERIAL_SWEEP.md) ·
[Framewright evidence](evidence/raider-framewright-20261103.json) · [studio finish](evidence/raider-material-sweep-20261103.json).

**CH-03 Raider shoulder and pouch, 2026-11-03:** a separate fitted derivative
of Opus's finished v7 is in `work/raider-seams-20261103/delivery/`. Open
`Review.html` for ten matched exported views or `Raider_Seam_Repair.glb` for
Framewright; `Raider_Seam_Repair.blend` has the packed editable source. The
geometry cut crossed both pieces in the user's screenshots. The revision
restores their continuous acquired surfaces and retains a closed portion of
the front-left pouch where the underlay is missing. The shoulder and rear
pouch are integrated surfaces, not independently detachable accessories.
The user liked this repair and requested the material sweep above. See [repair notes](RAIDER_SEAM_REPAIR.md)
and the [artifact receipt](evidence/raider-seams-20261103.json). No change to
Opus's checkout, the Framewright catalog, game packages or the production ledger.

**Current manual gameplay selection, 2026-10-23 20:39 MDT:** Character02 is open
in-game at normal 500 cm/s movement with its existing saved mesh, animation
graph, contact/transition/combat fixes and equipment. Left Alt selects its
calibrated walk; Shift retains 840 cm/s sprint. No Ennix override or RAC plugin
opt-in is used. All 215 protected files match after launch. Receipt:
`work/character02-turn-contact-20261023/gameplay-20261023-203913/ready.json`.

**Ennix sharp-turn correction, 2026-10-23:** the separate `TurnV1` AnimBlueprint
uses RACAnimation's optional character-specific plant envelope and pelvis reach
compensation. Actual eight-case game panels at 30/60 Hz reduce maximum declared
plant ankle XY excursion from 10.445/9.414 cm to below 0.001 cm, with no negative
observed sole gaps (+0.347/+0.365 cm minimum). The capsule path and leg lengths
remain unchanged. Maximum pelvis lowering is 1.937/3.031 cm; sampled hand/body
checks pass at both rates. Four camera views, turn-to-idle/walk/reversal movies
and a slowed foot close-up are at
`work/ennix-turn-contact-20261023/presentation/review.html`. Evidence:
`docs/evidence/ennix-turn-20261023.json`. The user rejected the current Ennix
character during manual gameplay and requested Character02 instead. Preserve
Ennix's artifacts as a rejected candidate; no further Ennix polish is requested.
No cooked or performance claim. Foot rotation remains free during pivots.

Manual gameplay review relaunched on request at 20:35 MDT using `TurnV1`, a
visible game window and the normal 500 cm/s travel speed (the previous 105 cm/s
inspection cap was too slow for gameplay). Hold Left Alt for the calibrated
105 cm/s walk, release for normal movement; existing Shift sprint remains
840 cm/s. A session-only callback reads the user's walk modifier; it generates
no movement. Receipt:
`work/ennix-turn-contact-20261023/gameplay-20261023-203542/ready.json`.
Character02 remains the saved default; 215 protected files, including the
TurnV1 asset and RAC plugin DLLs, match after launch. The manual session ended
normally at 20:37; its walk callback logged a controller-loss error during exit
and overwrote its earlier readiness receipt. The log retains the successful
startup. The launch does not extend the prior 105 cm/s contact benchmarks.

All 212 checked original game files match, including Character02's assets, Aether
solver, game DLL, default player, previous Ennix candidates and project settings.
The new plugin is explicitly disabled by default; a fresh ordinary startup has
neither RAC class loaded. Review launches enable it with `-EnablePlugins=RACAnimation`.
Fresh saved-graph reload and isolated plugin build pass; 936 tests, 39 skips,
198 subtests, lint, 325 script parses and isolated-wheel checks pass. New work
remains local/uncommitted. Native source, idle/walk clips and exports are unchanged.

**Ennix idle/walk baseline, 2026-10-23:** the reusable native workflow
now has an Ennix polish profile: quieter idle, hand/scarf clearance, calibrated
leg frames, 4 cm swing and a 105 cm/s walk. Exported idle pose, exact model
preservation, all-frame FBX/GLB reimport and independent native motion replay pass.
The engine adapter transports skin deformation through the actual SkeletalMesh
bind frames; fresh reload verifies the saved clips, markers and 105 cm/s rows.
Guide: [ENNIX_ANIMATION_POLISH.md](ENNIX_ANIMATION_POLISH.md); portable evidence:
`docs/evidence/ennix-polish-20261023.json`; local comparison:
`work/ennix-idle-walk-20261023/presentation/review.html`.

Actual owned game tests cover eight start/stop/left/right/reversal cases at 30
and 60 Hz (1,695/3,390 frames). Baseline worst observed penetration is 11.000/
10.682 cm; final minimum observed gaps are +0.347/+0.365 cm, with no negative
observed samples. Ground hit coverage is 99.836/99.847%, never a wholly unobserved
foot frame. Hand/non-arm-body samples pass at 6 Hz (339 poses per rate), compared
with four intersecting baseline poses at 30 Hz. Straight flat-support intervals
remain locked. **Sharp-turn plant excursion still reaches 10.445/9.414 cm**;
this V8 baseline's turn excursion is corrected by the separate TurnV1 result
above. Human moving-view acceptance remains open. No cooked or
performance acceptance, human approval or production promotion is claimed.

New assets are isolated under `/Game/Ennix/AnimationPolish/20261023/V6` (clips)
and `V8` (final blend space/AnimBlueprint). Original Ennix configuration and
Character02 default player remain intact: all 195 preservation hashes match.
The native source is unchanged; new RAC work is local and uncommitted. Rejected
bind-frame, arm-pose, contact and stale-BlendSpace trials remain in the case folder.
The review movies decode and have sampled frame inspection; browser automation
blocked local `file:` navigation, so interactive page playback was not verified.

**Reusable animation workflow verified, 2026-10-23:** integrated upstream through
`3b54047`, retained the Character02 repair history, and added explicit portable
profiles plus `rac animation init`. The complete Blender runner inspects,
derives, measures, exports/reimports FBX and GLB, checks exact model preservation
and packages evidence. Optional MIT Unreal contact modules build independently
of TheAetherWars and accept measured samples and character-specific bone chains.
Guide: [ANIMATION_REUSE.md](ANIMATION_REUSE.md); generated evidence index:
`docs/evidence/animation-reuse-20261023.json`.

An independent clean clone at code revision `a11bdcb` passes 929 tests,
39 optional skips, 198 subtests, lint, 318 script parses and an isolated-wheel
end-to-end animation contract run. Real Character02 and Ennix idle/walk profiles
pass baseline/candidate exports, all-frame reimports, exact model comparison and
four-view rendering. Two independent Ennix library bakes have identical motion.
The examples use a one-degree head alternative; they are not artistic upgrades.
Clean UE 5.8 host build, repeated installation and fresh-process saved-graph
reload pass with 191 Ennix sole samples. Imported-mesh warnings remain recorded;
this is not runtime acceptance of the renamed plugin.

All 48 original dirty RAC files have hash-verified backups; unrelated local
commission history and review images remain outside these commits. The 13 checked
game source/configuration/AnimBP/DLL files are unchanged. Work and failed attempts
are retained at `work/animation-reusable-20261023/`. Next gates: per-character
visual/contact tuning, destination runtime/cooked tests and contact-node cost.
No human approval or production promotion; no model downloads or inference.

**Open-source animation methodology, 2026-10-22:** implemented the portable
`rac animation` recipe/edit/measure/review commands and checkout adapters for
existing calibrated library replay, preserved-rig Blender exports, surface audits,
and owned Unreal baseline probes. Guide: [ANIMATION_WORKFLOW.md](ANIMATION_WORKFLOW.md).
Evidence index: `docs/evidence/animation-workflow-20261022.json`; retained artifacts:
`work/animation-methodology-20261022/`. Verification: 788 tests, 15 skipped,
198 subtests, lint, 243 script parses and isolated installed-wheel checks passed.
All 19 baseline clips passed GLB/FBX round trips; baseline/candidate exported model
payloads match. The source character is unchanged; the installed packet was
subsequently replaced by the idle/contact repair below.
Game baseline checks passed at 30/60/120 FPS caps, observed averages 29.6/58.0/77.7.
This is editor `-game`, not cooked or sustained 120 FPS proof.

**Character02 idle/contact repair installed, 2026-10-22:** seven clips and seven
walk aliases first used `Saved/LibraryAnims/Character02/ual-v22-idle-contact-20261022T202926Z`
in TheAetherWars; the walk is now superseded by v23 below. Exact prior assets/configuration are retained under
`Saved/AnimationContactRepair/20261022T202926Z/`. The relaxed idle now passes its
exported pose contract: elbow bend 19.5–20.2 degrees (was 46.0–48.7), pelvis drift
0.293 cm (was 0.976), with planted feet and matching loop endpoints. Source-skin
hand/coat contacts fell from 192 to zero observations across 575 poses; no sampled
thumb/finger contacts in that source panel. Timing, root tracks, events, geometry,
UVs, weights, materials and bind data are preserved. All 19 clips pass GLB/FBX
round trips; fresh saved-asset audit and installed locomotion runtime pass.

Actual input reached all three combat sections in owned Unreal `-game` tests at
30/60 FPS caps. Attack 03's sampled soles did not penetrate the tested dungeon
collision (minimum right-boot gap 0.087 cm before, 1.16–1.24 cm in repeat runs).
Attack 03 was left unchanged; the earlier -2.254 cm source-plane finding was not
reproduced as that gameplay defect. These are sampled, location-specific checks.
The old game already had a runtime arm-clearance layer: both before/after game
samples have zero hand/coat contacts. A brief Attack 01 thumb/finger overlap and
small post-combo resting-foot penetration on uneven tiles remain in both versions.

Review: `work/character02-idle-contact-20261022/presentation/` (labeled before/after
idle and walk, side idle, real game combo capture); four views/two repeats are in
`review-before/` and `review-after/`. Evidence:
`docs/evidence/character02-idle-contact-20261022.json`. Final verification: 788
tests, 15 skipped, 198 subtests, lint, 246 stage parses and isolated wheel checks.
Rejected repair attempts and the earlier timing demonstration are retained.
The user subsequently rejected the walking leg motion; see the diagnosis below.
Complete terrain, interruption and cooked-build coverage remain open. No human
approval or production promotion.

**Character02 grounded walk installed, 2026-10-22:** selected packet is now
`Saved/LibraryAnims/Character02/ual-v23-grounded-walk-20261022T221205Z` in both
library and animation-flow configuration. Corrected source/target segment alignment
replaces the signed-reference error identified in the rejected walk. A 1.10-second
cycle at the existing 89.18 cm/s uses moderate 5 cm swing clearance, rolling
support and a coupled pelvis solve. Source knee bend is 12–43 degrees, previously
35–99; evaluated 30 Hz game walk is approximately 12–57, previously 36–104.
The exported geometry, weights, UVs, materials and bind data are exactly preserved.
Other packet clips, including the earlier idle/coat repair, remain unchanged.

GLB/FBX round trips and all 34 source-pose surface checks pass. Eight saved walk
aliases have retimed sync markers; idle and walk aliases have explicit flat-support
curves. A new final game skeletal-control node uses measured boot skin and current/
predicted collision samples after the existing floor rig. Owned rendered Unreal
`-game` tests at 30/60 Hz cover starts, two stop phases, walk/jog changes, turns and
a reversal. Sampled soles remain above tested collision (minimum 0.37 cm at 30 Hz,
0.34 cm at 60 Hz); measured declared flat-support windows drift at most 0.093 cm.
Earlier acquisition of blended support reduces the measured 30 Hz start drift to 0.08 cm.
Jump/landing releases were exercised at 60 Hz. The separate 1.88 cm attack-recovery
toe dip observed here is addressed by the subsequent recovery repair below.
These are fixed-step simulation tests, not real-time performance or cooked proof.

Saved assets, markers, support curves and the final node reload correctly. C++ full
build and RAC verification pass (791 tests, 15 skipped, 198 subtests); final changed
scripts also pass lint and targeted calibration tests, with all 255 stage files parsed. Review:
`work/character02-walk-repair-20261022/presentation/review.html`; evidence index:
`docs/evidence/character02-walk-repair-20261022.json`. Backups are in game
`Saved/WalkRepair/20261022T221205Z` and the retained `sole-*` install directories.
Earlier diagnosis and failed candidates remain evidence. Next gate: user judgment
of the installed walk and transition feel; full terrain/combat/cooked coverage is
open. No human acceptance or production promotion has been inferred.

**Character02 attack recovery installed, 2026-10-22:** retained the v23 packet,
native character and earlier idle/coat/walk corrections. The final sole node now
reads the current evaluated slot state, restores contact in the first blend-out
frame and accounts for the horizontal lock on sloping ground. The existing floor
rig ramps in with the montage's remaining weight. A bounded reachable lock
replaces the hard reset at its correction limit. Active strikes and airborne
motion retain their authored trajectories. Game configuration and AnimBP wiring
are installed; fresh saved-asset audits pass. Clips, montage, blend space and
mesh hashes match the prior installation audit.

Paired rendered `-game` tests at fixed 30/60 Hz cover single attack and all three
combo sections into idle/walk, plus movement cancellation. At 60 Hz, single-attack
idle/walk recovery minimum gaps change from -1.88/-6.78 cm to +0.65/+0.64 cm;
combo idle/walk from -2.88/-2.97 to +0.65/+0.63 cm. Movement cancellation improves
from -7.94 to -0.024 cm (one 0.24 mm penetration sample); at 30 Hz all five
recovery cases have positive sampled clearance. Largest 60 Hz pelvis step falls
from 6.64 to 1.44 cm; combo-to-walk right-foot step from 13.57 to 2.01 cm.
All 669 compared active-strike frames match exactly; paths and montage states
match too. A fresh 60 Hz locomotion/jump regression retains positive sampled
clearance and at most 0.092 cm declared flat-support drift.

Review: `work/character02-attack-recovery-20261022/presentation/review.html`
with five side-by-side game clips, boot close-ups and four installed views.
Evidence: `docs/evidence/character02-attack-recovery-20261022.json`.
Backups: game `Saved/AttackRecoveryRepair/20261022T230601Z` and task `baseline/`.
C++ build passes; preflight RAC suite passed 791 tests, 15 skipped, 198 subtests,
lint and wheel checks; final lint and 260 stage parses pass. The active-combo
penetrations found in this panel are addressed by the subsequent repair below.
Finite samples on the tested tiles are not all-terrain, performance or cooked
proof. Next gate: user's visual/feel review; human acceptance and production
promotion remain false.

**Character02 active-combo contact installed, 2026-10-23:** the configured combo
now receives upward leg contact correction capped at 3 cm, with active foot
orientation and horizontal pivoting preserved. Source sequences, native character,
mesh, weights, montage timing and selected v23 packet remain unchanged. Runtime
terrain queries use up to 16 spatially distributed points per boot plus predicted
positions (64 traces maximum), while the independent probe traces all 149 retained
sole vertices. This also fixes an existing later-walk toe dip after Attack 02
that the previous lowest-world-Z measurement missed.

Rendered paired 30/60 Hz tests stop after each of the three attacks and return
to idle or walking: all six complete cases have positive measured clearance,
minimum 0.559/0.578 cm. Attack 03's 60 Hz walk-exit active minimum improves from
-1.184 to +0.583 cm; the later Attack 02 walk sample from -3.213 to +0.639 cm.
Comparison of 856 active frames preserves foot XY/orientation to numerical
precision; upper body, pelvis, coat, hand targets, pawn path and montage timing
match across all paired frames. Four-view combo/recovery checks also have
positive clearance. Straight walking, stops, speed changes and jump/landing pass
the expanded contact check; declared flat-support drift remains under 0.092 cm.

That installation's separate turn/reversal regression had a 2.072 cm toe intersection.
Reconstructed earlier toe coordinates give 3.782 cm against the same freshly
traced floor, so this is a pre-existing limitation, not a passing regression.
No claim of all-terrain, continuous contact, cooked or performance acceptance.
Trace misses are retained as unknown clearance rather than counted as passes.

Review: `work/character02-active-combo-20261022/presentation/review.html`;
evidence: `docs/evidence/character02-active-combo-20261023.json`. The task folder
retains its start date. Backups: game `Saved/ActiveComboRepair/20261022T233205Z`
and task `baseline/`. The user-paused run, superseded candidates and diagnostic
commandlet failure are retained. Final C++ build passes; resumed RAC verification
passes 791 tests, 15 skipped, 198 subtests, lint, 262 stage parses and isolated
wheel checks. Saved-asset audit reloads the combo reference and 3 cm limit;
only the AnimBP changes among audited asset files. Next gate: user's visual/feel
review of the active attacks and exits; turning contact is repaired below.
Human acceptance and production promotion remain false.

**Character02 turn/reversal contact repaired and installed, 2026-10-23:**
After the user's authorized resume, bidirectional terrain prediction plus inner
and padded-footprint query grids resolved the missing floor coverage. A separate
frame required 9.31 cm correction: the locomotion limit is now 10 cm, while the
opted-in combat limit remains 3 cm. The temporary upper-plane heuristic was
removed. The source character, mesh, weights, clips and selected v23 packet are
preserved. Runtime terrain traces are bounded at 192 per character, previously
64; crowd-scale cost is unmeasured.

Seven paired rendered game cases at both 30/60 Hz cover the original sequence
and left/right/180-degree turns into idle or walking. All exit states pass;
all sampled clearances are positive, minima 0.148/0.608 cm. The original sequence
improves from -2.734/-2.072 cm to +0.606/+0.608 cm. Across 3,915 paired frames,
upper body, pelvis, path, transition state and foot orientation are preserved.
Six walking/jump cases and six combat exits retain positive contact; declared
flat-support drift remains below 0.092 cm. The combat comparator's old upward-only
flag remains false because the changed cache permits 0.038824 cm less vertical
correction; contact remains positive and unaffected performance channels match.

Four camera views and 33 videos are available at
`work/character02-turn-contact-20261023/presentation/review.html`; evidence index:
`docs/evidence/character02-turn-contact-20261023.json`. Saved graph, marker and
asset-hash checks passed in a fresh normal editor after a commandlet crashed
during RigVM startup before Python; both receipts are retained. Resumed RAC
verification passed 791 tests, 15 skipped, 198 subtests, lint and isolated-wheel
checks; final C++ build and all runtime panels pass. Current DLL SHA:
`e4029ef320e3e2ce89d0f408fc1b9ddc716c68816dbbe8262ba24b6c5fda12a8`.
Config/AnimBP backups: game `Saved/TurnContactRepair/20261023T160400Z/`;
pre-task sources: task `baseline/`. Rejected candidates and the earlier pause
checkpoint remain historical evidence. Next gate: user review of the animation
and gameplay feel. Finite collision sampling and fixed-step editor-game tests
do not establish all-terrain, cooked-build or real-time performance acceptance.
Human acceptance and production readiness remain false.

**Current authorized Artiss review scope completed on 2026-10-18:**
**26 prepared / zero active unfinished / four held requisitions.** CH-01,
CH-02, CH-03 and DH-03 remain held; all character work waits for Mark's design
refinement. Existing candidates and frozen packages are preserved. Earlier
counts and character next steps in the asset history below are superseded by
this checkpoint and `work/artiss-tomb-2026-10-16/commission.json`.
Prepared means available for review, not human-approved or production-ready.
No TheAetherWars import occurred during that isolated review checkpoint;
publication, push and human approval remain absent. Mark subsequently authorized
game integration and new-map work; the current map checkpoint is below.

**Authorized Unreal map pass, 2026-10-18:** continued the live Drift Well in
`C:/Users/Ayric/Documents/Unreal Projects/TheAetherWars`, saved as
`/Game/Artiss/Maps/L_ArtissTomb_DriftWell`. Repaired vault hinges, material
bindings, first-lens placement and branch access; added timber recovery, pool
steps, floating wooden cache and survey-glass dressing. Actual blade/bomb,
four-ramp traversal, puzzle wiring and all seven timber-board landings plus
the island jump have evidence in `Saved/DriftWellReview/`. Details and limits:
game `Docs/DriftWell.md`; receipt `checkpoint-final-v1.json`. All characters
remain held; named people are staging markers. Combat balance, save/load,
cooked runtime and final human review remain open. Claude's UX/C++ work and
the older maps were preserved. That checkpoint's editor PID was 43716;
the active prototype checkpoint below supersedes its process status.

**Ennix Loading Bay prototype, 2026-10-18:** implemented the authorized
dangerous-improviser experiment in the same game project, separately at
`/Game/Artiss/Prototypes/L_Ennix_LoadingBay`. Two waves (2 light, then 2 light
and 1 heavy), bombable gallery, movable prestige timber/cache, recovery floors,
and complete rehearsal resets are implemented. Two opt-in enemy properties
add 35 collision/wall pressure; prototype stagger is 3 seconds at 1.6x with
no per-hit escalation. Campaign persistence is isolated; Drift Well's file
matches the session baseline. Authoritative build and 151/151 native tests
pass; ordinary-resource PIE combat, breach, tow, jumps, restart, death and
boundary recovery have receipts in game `Saved/LoadingBayReview/`.
Current guide: game `Docs/LoadingBay.md`; final index `checkpoint-final.json`.
No new characters, publication, push or human approval. Physical control feel,
fresh-player comprehension/replay verdict, cooked runtime and performance are
still human/integration gates. Do not carry the rules into later encounters
yet. That checkpoint's editor PID was 40784; the newer feedback pass is below.

**Blade feedback candidate, 2026-10-19:** after Mark's playtest reported weak
feedback despite correct throws, added per-blade HUD locations/states, offscreen
arrows, confirmed hostile-hit/return-hit accents and separate catch pulses.
Damage and audio are unchanged. Game/editor builds and 152/152 native tests pass;
evidence is game `Saved/BladeFeedbackReview/`. Live capture v1 had incorrect
probe camera rotation; v2 overlapped Mark's input, so neither is complete visual
acceptance. Automated control has stopped; editor PID 32932 is handed back for
Mark's playtest. No new characters or human approval. Details: `Docs/LoadingBay.md`.

**The last four native review packages are complete.** Paths below are relative
to `work/artiss-tomb-2026-10-16/`; each package includes an isolated editable
UE 5.8 project, a portable ZIP, review media and manifest:

| Requisition | Current package | Independent packaged reopen |
| --- | --- | --- |
| FX-01 dampening field | `assets/FX-01/review-native-v1/` | 23 native assets resolved; 29 archive files |
| FX-02 Spark Bomb | `assets/FX-02/review-native-v2/` | 18 assets; 26 files; cap yaw 45 degrees at 0.2 s |
| FX-03 gyrosphere lock | `assets/FX-03/review-native-v1/` | 29 assets; 35 files; all 11 bindings and 0.5 s clock verified |
| TA-01 thin ink / optional smear | `assets/TA-01/review-native-v1/` | 25 assets; 32 files; matching extended-luminance setting |

All three eight-second FX videos (192 native frames each) played to completion
in Framewright. TA-01 includes native grade/ink/smear and distance/quality
comparisons. Distant and low-quality differences remain within repeated-control
variation; no pixel-identical or GPU-budget claim. Its multi-mode capture wrote
all outputs but crashed during teardown; that failed execution is retained.
The separate packaged reopen exited 0. FX-02 v1 remains rejected binding
evidence. Earlier FX-01 steady-field dropout claims were disproven by pixel
comparison (`effects/fx01-steady-state-correction-v1.json`).

Framewright has **464 current items: 278 models, 173 images, 10 audio and three
videos** (538 records including revision history). These are library records,
not 464 distinct requested models. Package hash/ZIP integrity evidence is
`evidence/native-review-final-audit-v1.json`; the current transfer guide is
`work/artiss-tomb-2026-10-16/HANDOFF_TO_CLAUDE.md`.

Next gates are human review, remaining integration/runtime checks,
and future design decisions for the four held requisitions. No task-owned
inference, render or export remains running. Framewright PID 12728 and the
user's then-unrelated TheAetherWars editor PID 44552 were left running at the
isolated asset checkpoint; the current prototype editor is PID 32932. The one-time
midnight shutdown already ran at 01:00 Denver and has no next run.

## Character02: open-library animation, cleaned coat paint, measured skin (2026-10-14), not production-ready

The user retired the 2026-10-12 baked posture packet (it moved the motion by a few
degrees; renders in `work/character-02/anim-review-20261013/`). Locomotion now comes
from Quaternius UAL (CC0) retargeted onto the character's own rig
(`scripts/anim/`, `profiles/animation/`, [CHARACTER_LIBRARY_ANIMATION.md](CHARACTER_LIBRARY_ANIMATION.md)):
idle, walk, jog, a new sprint row and jump, with baked coat-follow so coat panels
clear the legs. Installed in The Aether Wars by its `library` step
(`Saved/LibraryAnims/Character02/ual-v2`); the user liked the motion. Open: clenched
hands and a wide "ready" idle stance (user, 2026-10-14), combat/dash/traversal still
on earlier clips, no starts/stops/pivots (100STYLE mocap downloaded for that).

The spotty coat came from projection paint at ~3 texels per triangle; re-UV fails on
this scan mesh. `scripts/clean_garment_paint.py` filters it on the body surface
([CHARACTER_GARMENT_PAINT_CLEAN.md](CHARACTER_GARMENT_PAINT_CLEAN.md)); build
`work/character-02/coat-clean-20261014/build-v6/` is installed texture-only. The user
called the clothing "decent" and open to more iterations.

Play-test fixes (2026-10-14, evening): 100STYLE motion matching is switched off for
Character02 (the idle picked up gesture takes and raised his hands; game key
`_motion_matching_off`, AnimBP restored). The walk "glide" was mostly a game-side bug:
the blend space's runtime triangulation was never rebuilt after its samples were
rewritten, so the walk played at jog speed; planted-foot slip at the 500 cm/s jog fell
from ~360 to ~20 cm/s after the rebuild. Drawn blades now switch the idle to UAL
`Sword_Idle` (`anim-ual-20261014/swordidle-v1`, game packet `ual-v6`, step `blade_idle`).
Open: user play acceptance; the sword ready stance is deep and wide.

Skin: the game's skin material gained opt-in look keys (`skin_shading`,
`skin_saturation`, `skin_tint`); measured with `scripts/measure_skin_tone.py` against
the portrait, normalised by the shirt. The installed look (v7) is tan, hue 58 deg vs
the painting's 56.5. In-game Play-in-Editor stills: game `Saved/GameShots/final-20261014/`.

## Character02 (2026-10-12, superseded above): sleeve and posture repairs

2026-10-12 posture follow-up: the existing source already has a T-pose. The
animation-only repair lowers the shoulders 3 cm, opens their spacing by 2.5 cm
per side, straightens the torso slightly and moves the hands clear of the coat.
Selected bake: `work/character-02/posture-20261012/bake-v6-clearance/`; recipe
`recipes/character-02-posture-20261012.json`. All 1,113 recorded frames in 19
clips and 960 sampled locomotion blends pass the palm/finger versus torso/coat
intersection check. Rightward jog and attack 01 also receive bounded, smoothly
entered arm separation. Mesh, bind, weights, paint and facial data are unchanged.
UE installation reads every changed key back and measures zero lower-body
position drift. See [CHARACTER_POSTURE_REPAIR.md](CHARACTER_POSTURE_REPAIR.md).
User play/appearance acceptance and unsampled combat/traversal remain open.

2026-10-12 consumer follow-up: The Aether Wars has the `release-v2` FBX
installed (its import receipt matches the hash below). The current texture-only
derivative is `work/character-02/sleeve-repair-20261012-release-v2/`, rebuilt with
`scripts/repair_character_sleeves.py` and
`recipes/character-02-sleeve-continuation-20261012.json`. Its FBX, rig, head,
mask, normal tiles and hair maps are byte-identical to release-v2. Sleeve circumference detail is continued from the retained paintings; it is inferred
paint on unseen surfaces, not new acquisition. Other garment surface texels
remain unchanged. See `docs/CHARACTER_SLEEVE_REPAIR.md` for the exact command,
source hashes, candidate comparisons and rejected experiments.

The UE installer now keeps this hero's body albedo and garment mask resident,
with normal mip filtering. Detached scene captures previously showed coarse
mips as tan shards. Residency removes that failure but cannot repair blurry
source paint or collar geometry. The subsequent posture pass addresses sampled
hand/coat intersections; human acceptance and cooked gameplay remain unresolved.

Current review derivative: `work/character-02/seams-20261012/release-v2/`.
Editable game source: `Character02_UE5_coat.blend`; export:
`export/Character02_UE5.fbx`. Reproduce with
`recipes/character-02-seam-repair-20261012.json` and
`scripts/repair_character_seams.py` (command in CHARACTER_REBUILD.md).
The original v23 and the currently installed Unreal asset are preserved.

Fixed the hand transplant's rotation of Manny finger axes and trimmed the
acquired wrist's protruding triangles with a UV-preserving plane cut. The
161 cut vertices that gained excess influences are capped and normalized to
four. Conservative collar fairing moves only a measured region, at most 8 mm.
Head, hair, eyes, oral meshes, hand geometry, their UVs/weights/morphs and
transforms match the v23 final-hand source exactly in the native regression.

Technical checks: six sampled Manny poses, both hands; worst per-hand 99th
percentile edge stretch falls from 7.409x to 1.751x. The FBX reimport gate passes:
112 bones, 98,097 triangles, max four influences, zero unweighted vertices,
under Mark's existing 100,000-triangle waiver. Receipts: `repair.json`,
`hand-verification.json`, `gate-rig.json`. Views in `review/` include front,
three-quarter, side, back, neck and both wrists; `attack-review/` adds close-ups.

**Next unresolved gate: visual seam/deformation acceptance.** The collar still
has pointed tears and the cuff has a visible inner rim. The later posture pass
clears the measured first-attack hand/coat contacts; other actions remain
unvalidated. The stretch checks catch gross collapse; they do not establish
natural hand articulation or universal collision freedom. Hair, surface
detail and material quality also remain below the requested AAA standard.
Unreal import and editor-render evidence now exist in the game project's
`Saved/CharacterInstall/Character02/` and `Saved/PosedCloseups/`; neither is
play-test or cooked-runtime proof.
Earlier `pose/` and `ue5/fit/poses/` images predate the final hand transplant;
do not present them as evidence for the exported v23 character.

## Artiss Tomb commission (30 requisitions; 26 active, four held)

Mark commissioned a separate Framewright review project on 2026-10-16:
**The Aether Wars — Tomb of King Artiss**, project
`45863b1c-3352-4eea-bfc5-70a22ddeb40a`, available at `http://127.0.0.1:5179/`.
Artiss is currently active again after inspecting the older
**The Aether Wars — Realistic Asset Review** project for reuse.
Its saved World settings contain the painterly, slightly gritty direction,
limestone/bronze/teal/amber palette, driftglass and rare timber rules, dimensions,
axes, pivots, separate parts, pre-fracture and budget conventions. This direction
supersedes the October 3 photoreal brief for the new commission only.

The corrected Markdown and JSON exports agree on all **30 requisitions**:
nine P0, seventeen P1 and four P2. They are retained as `COMMISSION.md` and
`requisitions-source.json`; `commission.json` tracks the full scope and source
hashes. Mark explicitly said **hold CH-01, CH-02 and DH-03; build the other 27**.
The source records remain Draft; commissioning is not human visual approval.
Framewright now has one ID-labelled collection per requisition, including the
three holds, and the project World settings reflect the corrected intake.

AR-01 survey lens: current `assets/AR-01/review-delivery-v9/` contains metallic off/on
assemblies, separate bezel and glass exports, packed editable Blender, FBX,
maps and the emissive mask. Both assemblies were visually checked in the actual
Framewright viewer. GLB/FBX measurements agree; the glass is 60 cm and both
parts pass closed-surface and nondegenerate-face checks (11,764 triangles total).
The current Framewright working revision is v3 (smooth bronze), following
Mark's requests for stronger metal response and cleanup of the surface artifacts
it exposed. The acquired bronze was faired and its annular normals regularized;
UVs, maps, the 60 cm glass and 11,764 total triangles remain. Fixed views and
live OFF/ON inspections passed the operator review. The earlier 15 m / 6 m
distance proof remains available; no new distance render is claimed. The
paint runner produced validated artifacts but crashed during teardown; its
failed execution is retained, with no inference retry. Human approval is pending.

Mark extended the metallic response to all bronze. The saved Framewright World
direction and `commission.json.material_direction` carry that instruction for
future candidates. `evidence/bronze-finish-batch-v1.json` records 24 local painted
derivatives with revised bronze masks and editable Blender/FBX companions.
Eight model candidates are staged: four DH-01 ring/assembly versions, HC-04
pillar, TW-01 wall and arch, and GV-04 emitter. Bronze-only map changes preserve
the original geometry, UV, normal and animation bytes; non-bronze texels remain
unchanged. DH-01 v2 animation played in Framewright; its review set and AR-01's
are prepared, not approved. Clay modeling candidates still await their paint
stage. Other kits and the overall 27-requisition commission remain incomplete.

HC-04 and HC-06 now have complete review sets in `assets/<ID>/review-delivery-v1/`.
The pillar includes intact, slight-lean and exposed-rib variants, ten individually
exported closed fragments, the assembled fracture set and an exploded inspection
model. All 15 GLB/FBX pairs agree on bounds; base pivots and 5.5 m intact height
were checked. The carved relief is 4.2 x 2.6 x 0.3 m, back at x=0, with 40,000
triangles and a plain stone rear face. Both were inspected in Framewright.
AU-01's ten audio files decode in the browser; gimbal playback advanced to
10.59 s and was paused. Human listening is pending. Thirteen requisition sets are
prepared for review: AR-01, DH-01, GV-01, GV-02, HC-01, HC-02, HC-03, HC-04,
HC-05, HC-06, GV-04, AU-01 and TW-01.

TW-01's complete six-module review package is `assets/TW-01/review-delivery-v1/`:
6 m wall, arch, pilaster, floor, coffered ceiling and wall-to-floor trim, with
exact staged GLBs, packed Blender files, FBXs and portable texture maps. All
six actual GLB/FBX pairs pass closed-surface, UV, origin and dimension checks;
maximum paired bounds difference is 0.000000525 m. Every companion resolves
its maps locally. The floor FBX includes matching visible-surface UCX collision;
961 rays agree, and the four-tile inspection model has zero join gap/height
step and matching opposing-edge UVs. All six modules and the floor grid were
inspected in Framewright. The ceiling's warm limestone falsely triggered the
generic bronze mask; v4 confines metal response to measured crossed ribs while
retaining AI albedo, geometry and UVs. Floor/ceiling paint teardown failures and
rejected derivatives remain recorded, with no inference retries. Native walking
and cooked runtime validation remain outside this review commission. Fourteen
authorized requisition sets remain unfinished; three held sets remain empty.

GV-01's `assets/GV-01/review-delivery-v1/` is prepared for review: 35 cm
gyrosphere assembly, three individually exported bronze rings, smoky amber
driftglass core, static base-pivot pickup and transparent 1024 px inventory
image. The assembly contains four separately centred parts and 7,598 triangles.
The inner ring carries a built-in ImageGen feather motif CPU-baked into its
existing UVs. Six actual GLB/FBX pairs passed closed-surface, nondegenerate-face,
UV, centre/base-pivot and dimension checks, with zero nonadjacent self/interpart
intersections at rest. Maximum paired bounds delta is 0.00000006333 m. All eight
native/FBX companions resolve local maps; the 45-file package is 47,025,176 bytes.
All six models and both images were inspected in Framewright. Source-derived
cuts/fairing/remeshing, rejected overlap/shading trials, paint shutdown failure
and corrected Save As map-path failure remain recorded. No inference retry or
human approval. `evidence/phase-eleven-review-state.json` records 132 total,
111 current assets (34 images, 67 models, ten audio), twelve prepared sets and
fifteen unfinished. Rigging/gameplay/runtime work remains outside this review
package; the three held collections remain empty.

GV-02's `assets/GV-02/review-delivery-v1/` is prepared for review. The painted
61-part cradle contains three separate 5/7/9 m bronze rings with click teeth,
six limestone counterweights, three ceiling chain/yoke runs and the actual
35 cm GV-01 in its central holder. Eleven GLB/FBX pairs and a packed editable
master retain explicit pivots, local maps and source lineage. The assembly is
226,478 triangles; each ring is 12k and the standalone counterweight is 9,980.
The inner ceiling mount is angled 11 degrees to clear the ring. All 22 actual
interchange files pass closed-surface, nondegenerate-face, UV, dimension/pivot
and self/interpart-intersection checks at rest; paired bounds differ by at most
0.000000477 m. Actual modeling checks establish adjacent chain interlock.

Fixed views and all eleven actual Framewright models were inspected. Earlier
contact-cut scraps/disconnected links, a reflective tooth fold, incorrect stone
metal mask and ceiling-eye defects remain recorded. The final eye uses the clean
acquired link fitted into the retained acquired plate, with CPU-rebaked paint.
All three AI paint jobs saved geometry-preserving validated output but crashed
during teardown; no retries. The delivery has 101 hashed files, 145,401,854 bytes.
Current assembly revision: `2c50272e-50ac-483f-a6fa-02e638208ae2`. Phase twelve
records 147 total / 125 current assets (37 images, 78 models, ten audio),
thirteen prepared sets and fourteen unfinished. Three held collections remain
empty and human approvals remain zero. Motion/physics/gameplay and Unreal import
are not performed; these are review candidates. TW-02 remains the unfinished P0
requisition, with the fourteen remaining sets still in the full commission scope.

TW-02 has its first three material-only repaints prepared in
`assets/TW-02/review-group-01-v2/`: the 4.6 m throne, separate canopy and plinth.
Exact source mesh, UV, normal and topology bytes remain in the staged GLBs;
a rigid +90-degree Z parent changes the old -Y front to +X. No remodeling.
Each retains its original 40,000 triangles. Three GLB/FBX pairs and editable
Blender companions pass surface, dimension and local-map checks; maximum paired
surface-vertex delta is 0.000000430 m. Four-view surfaces, companion appearance
and all three actual Framewright models were inspected. Bronze responds as metal,
stone stays matte and micro-normal maps are removed. Source pivots remain.

The throne's stretched inner-arm decoration and rear motif were replaced with
an ImageGen limestone swatch mapped onto existing surfaces. Rejected metallic
masks and the first ochre plinth remain recorded. The selected plinth uses a
distinct pale-ivory reference and paint attempt. All four AI paint processes
saved validated outputs then failed during teardown; no automatic retries.
At the end of group 01, `group-review.json` deliberately did not close TW-02:
118 model variants and 13 decal/inlay images remained. `repaint-progress-v1.json` records the complete
121-model / 13-image inventory; the earlier count of 90 means accepted old
polygon reductions, not the full repaint scope. Six existing static guardian
statues are copied and their four-view source renders inspected for group 02;
their differing UV layouts require separate mapping. All six now have verified
OBJ paint transports in `<stem>-uv-v1/`; every triangle matched on reimport,
source hashes remain exact, and maximum normalized coordinate/UV deltas are
0.0000009261 / 0.0000007165. The receipt is
`assets/TW-02/source-group-02/transport-summary-v1.json`. These transport receipts
remain source-lineage evidence for the completed group 02 material reviews below.
The statues are within TW-02, distinct from the three held requisitions.

TW-02 group 02 is now prepared in `assets/TW-02/review-group-02-v2/`: six existing
static guardians, kneeling at 2/6 m, shield at 2.5/8 m, sword at 2.5/7.5 m.
Kneeling/shield material v2 limits bronze to fittings; sword v3 also retains the
original dark helmet eye slit, which AI paint omitted and the actual browser
inspection exposed. The small feature is recovered from each acquired source
texture through its original UVs. All source geometry/UV/normal/topology bytes
remain intact, with the same rigid +90-degree Z orientation parent as group 01.
Source heights are within 2.3 mm of nominal; source triangle counts are retained.

Six actual Framewright models, all four GLB views each, and 24 actual FBX views
were checked. Exported Blender/FBX companions resolve local maps, with maximum
paired surface-vertex delta 0.0000003372 m. The FBX renders differ from their
GLB views by less than 0.000844 mean sRGB byte value (maximum single-channel
delta 6). Rejected warm-stone metal masks, missing-eye-slit revisions and all six
AI paint shutdown failures remain in the evidence; no inference retries.

`evidence/ar02-label-state-v1.json` records
**410 total / 347 current assets** (125 images, 212 models and ten audio),
**14 prepared sets / 13 unfinished**. Nine reused cave models now join the
driftglass, stonework, doors, specialties and mechanical models; three furnishings
and the three common-chest models now follow, plus six royal/relic chest parts
and assemblies, three ceramic urn variants, five traversal props, then the
Artiss carpet, climbing vines and iron parkour beam.
Current counts exclude history.
TW-02 is **121/121 models and 13/13 surface images prepared for review**, with
**no unprepared surface items**. Mark explicitly authorized separate corrected alternatives
for ceiling rubble, winch and coin pile on 2026-10-17; preserve their originals.
The 1/3/6 m chains retain an inherited coplanar-link
layout issue, and the old swing ring retains its one-piece mount; material
review is not assembly validation. Three held collections
remain empty and human approvals remain zero. No game import, publishing or push.

TW-02's corrected coin alternative is in `assets/TW-02/review-group-19-coins-v1/`,
Framewright model `bd2a14c7-18e0-4a45-96b0-4deda240fdf8`. It is a curated treasury
mound of touching stacks, 49.3 x 43.6 x 20.5 cm with a base-centre pivot. The
original 2.7 cm scatter remains intact. One original acquired coin was extracted,
automatically reduced from 12k to 2k before fresh AI paint, then reduced to 1k and
CPU-rebaked for 614 shared instances (614k evaluated triangles). Rebake worst-view
SSIM is .97302 lit / .97354 unlit; the detailed construction master is retained.
Gold is metallic 1, roughness .38, with no normal map. Actual GLB and FBX pass
closure, nondegenerate and self/interpart-intersection checks; maximum companion
vertex delta is 2.1400163e-8 m. Four GLB/FBX views and actual Framewright model and
reference were inspected. The compact GLB is about 3.1 MiB, but this remains a
detailed review asset: LODs, gameplay collision and runtime performance are open.

Freefall layouts were rejected for expense and an unsettled/lopsided result;
loose vertical-placement experiments left implausible voids. Selected v4 uses
actual-surface contact placement in irregular-height stacks, without a dynamics
claim. One paint attempt produced validated maps then failed during shutdown
(-1073741819), with no retry. AI paint retains crowns but omits the reference's
small lower mint mark; currency symbolism remains unapproved. Package: 110 files /
67,062,699 bytes, manifest SHA256
`79f72fc4074b7d2eece68fe81be7655f23c592b4298d2aae032137a39e0c1948`.
AR-02's cabinet is prepared in `assets/AR-02/review-cabinet-v3/`, current Framewright
model `e3604082-f255-444e-912d-98c8b7a9e81f` (v2). The 2 m cabinet has 15,266
triangles across body, two hinge-pivot doors and two parented smoky survey-glass
panes. Metallic bronze, pale limestone and satin panels retain AI albedo, with
no micro-normal map. Source-derived planar cleanup preserves the acquired form;
the crown/plinth retain chunky wear. An eight-second OpenClose preview reaches
95 degrees. Both actual GLB and FBX pass closed/nondegenerate surface checks and
193 motion frames without interpart intersections. Maximum FBX vertex delta is
5.9604645e-8 m and hinge-matrix delta is 3.5017729e-7. Fixed closed/open views,
portable maps and live Framewright playback were inspected. FBX glass is an
explicit opacity approximation; GLB/Blender retain transmission. Paint saved
validated maps then failed shutdown (-1073741819), retained without retry.

The first painted GLB's descriptive `extras.pivot` caused NaN loaded bounds in
Three.js; the current metadata-only revision renames it `pivot_description`,
preserving all binary bytes. Its predecessor remains available. The sealed
package has 126 files / 37,188,209 bytes; manifest SHA256
`1978da59f90912b24d467a6efa79902d6d229e3327056d40820c738956c4cd19`.
AR-02's map chest is prepared in `assets/AR-02/review-map-cabinet-v4/`.
Current Framewright assembly `45877279-b7a7-4a32-8ebb-d163bd4be2b9`, frame
`d95eb159-918d-41dd-8332-e0355111077d` and reusable tray
`9d1bb5e8-1be3-49ef-b31d-987cc645a181` preserve separate base pivots and
three sliding drawers. Approx. 125 cm wide x 80 cm deep x 75 cm tall;
36k evaluated / 18k shared unique triangles. Iron, bronze and limestone, no
timber. Eight-second DrawerOpenClose preview translates each tray 43 cm.
Actual GLB/FBX closure, UV, nondegenerate and self/interpart checks pass,
including all 193 motion frames. Four closed/open export views and live
Framewright playback were inspected. Interior UV cleanup samples one clean
contiguous region of the existing AI-painted atlas; texture bytes, exterior
UVs, geometry, normals and animation remain unchanged. Earlier striped and
triangular interior projections remain rejected evidence. Both paint jobs
saved validated outputs then failed shutdown (-1073741819), without retries.
182 files / 98,783,684 bytes; manifest SHA256
`b82dda6049a42d14f3c8a50f963308fd046ab7fc32b1460a09722378583070cd`.

AR-02's scroll rack is prepared in `assets/AR-02/review-scroll-rack-v2/`,
Framewright model `9c15c2c5-04db-4a9d-8453-85da57f28d33`. The empty three-trough
rack is 150 cm high x 90 cm wide x 40 cm deep, 8,904 triangles, with a base-centre
pivot, black iron and selective bronze. No timber or micro-normal map. Acquired
foot flash and one small inherited upper-post fold were repaired before paint.
Actual GLB/FBX closure, nondegenerate faces, UVs, dimensions and self-contact
checks pass; maximum companion vertex delta is 0.00000005373 m. Four-view,
elevated interior and actual Framewright inspections passed operator review.
The lower-shelf projection stripes were removed by UV sampling of a clean
contiguous dark region in the existing AI atlas, preserving its bytes and all
geometry/normals. Rejected surfaces and failed paint shutdown (-1073741819)
remain recorded, without inference retry. Package: 113 files / 39,015,988 bytes;
manifest SHA256 `fe643f92bc1d99f724d917fd3328e07779f04f6b4a66e7c875428062fdbfcfbd`.

AR-02's label plaque is prepared in `assets/AR-02/review-label-plaque-v1/`,
Framewright model `41a8b990-69af-40a9-9285-ecdd6955a179`. One image-conditioned
acquisition followed by cleanup yields 1,758 triangles / 881 shared vertices,
30 cm wide x 18 cm high x 3 cm deep, wall-mount origin at X=0. Rear background
flash and an overlapping rear skin were removed while retaining the front
relief, two rivets, blank limestone inset and bronze border. Four clay and
painted GLB/FBX views, actual exported topology/UV/dimension checks, local maps
and live Framewright front/side views passed operator inspection. Maximum FBX
vertex delta is 0.00000001311 m. Bronze metallic 1 / roughness .30; limestone
metallic 0 / roughness .78; no micro-normal map. AI albedo bytes and inspected
geometry/normals are retained. Paint saved validated outputs then failed
shutdown (-1073741819); no retry. Package: 89 files / 26,333,712 bytes; manifest
SHA256 `4fcf1d83589bfb443f5bef2d92a29e55e8796fcc9905bf7a2b15eb37e6789c88`.
Exhibit-specific lettering remains separate. AR-02 is partial: the sextant-like
instrument, strapped crates and cargo tags remain. Across the commission, roughly 50 individual
models/variants remain to finish (45-60 depending on reuse), excluding effects,
post-processing and the three held items; repeated instances count once.

The final four AR-02 base props have image-conditioned acquisitions and
reduced geometry: `astrolabe`, `sextant`, `strapped-crate` and `cargo-tag` under
`assets/AR-02/`. Their four design references are hash-verified in Framewright;
their actual library cards were inspected. The active old-project catalogue
was checked for reuse first (`evidence/ar02-catalogue-reuse-audit-v1.json`).
The crate uses iron and canvas, and the tag uses fired clay with an iron ring.

The astrolabe is prepared in `assets/AR-02/review-astrolabe-v3/`, Framewright
model `8e8f075d-7ee6-4859-bf11-a1a37247903b`. It has 14,062 triangles / 7,033
shared vertices across cradle, dial and sighting arm, 55 cm high / 48 cm wide /
12 cm deep, base and explicit axle pivots. Acquired cradle clearance and a .86162
YZ fit of the acquired arm resolve earlier dial/arm collisions. Both actual GLB
and FBX pass closed, nondegenerate, UV, connected-component, self-contact,
dimension and 24 sampled part-fit checks (-30 to +30 degree arm rotation;
-10 to +10 degree dial tilt, tested separately). Static exhibit; no animation
clip or survey-accuracy claim. Native companion exact; maximum FBX vertex delta
2.2351742e-8 m. Metallic bronze and dark iron retain AI albedo and inspected
normals, roughness .30/.35/.40, no micro-normal map. Paint saved validated output
then failed shutdown (-1073741819); no retry. One microscopic collapsed UV face
was restored from the exact pre-paint UV authority without geometry or image
changes. Four GLB/FBX views and actual Framewright default/front/detail views
were inspected. Package: 113 files / 36,947,171 bytes; manifest SHA256
`7a96964d5b94d708bcc2fa17ae9b83f00809afd63839dd98d74db5feaac41dde`.

The sextant is prepared in `assets/AR-02/review-sextant-v1/`, Framewright
`7fa07e29-b039-43ca-86d5-27c6ec5adfa2`: 32 cm high / 38 cm wide / 12 cm deep,
10,486 triangles / 5,239 shared vertices. Four separate acquired parts retain
base/axle pivots: frame/sight tube, index arm and two mirror mounts. Warm bronze,
dark iron and smoky coated mirrors, roughness .36/.30/.22, no micro-normal map.
Actual GLB/FBX closure, connected components, UV triangles, dimensions and
static fit passed. Static catalogue exhibit; no animation, swept-clearance or
functional optical-accuracy claim. Exact pre-paint UVs and original inspected
geometry/normals retained; AI albedo unchanged. One paint pass saved validated
maps then failed shutdown (-1073741819); no retry. Four GLB/FBX views and live
Framewright default/detail views inspected. Packed Blender exact; maximum FBX
vertex delta 1.6763806e-8 m. Package: 94 files / 34,284,079 bytes; manifest
`e2e2ce48722921e8e06261f884c49105f2c6df5ac78a8b1fb99e7b8524391a3c`.

The packing crate is prepared in `assets/AR-02/review-strapped-crate-v2/`,
Framewright `8e9a82b5-3227-408c-96b3-fba71a7b6059`; raised-lid inspection copy
`ab76704c-dbc1-4a21-ac1a-ac0c550699cf`. Dark iron and canvas, no timber;
60 x 90 x 60 cm, 8,876 triangles / 4,442 shared vertices. Ground skirt removed,
hollow body and lift-off lid separated. Actual GLB/FBX topology, UVs, dimensions
and fifteen sampled 0-35 cm lid lifts pass. Flat cut normals remove diagonal
cavity shading; scalar iron on the cavity/rim avoids unobserved paint streaks.
Source AI exterior albedo preserved, metallic map retained, broad roughness
.35-.75, no micro-normal. Exact packed Blender and FBX surface transport pass.
Closed/open four views, elevated cavity, actual FBX and both live Framewright
models inspected. Package: 155 files / 76,675,139 bytes; manifest
`19125ac0f457a19d497e56783974a6748dccdc6b4587bc2039baa341982aba12`.
The open copy is the same lid raised 35 cm for inspection, not another design
or a levitation claim. No strap-release animation or gameplay validation.

The cargo tag is prepared in `assets/AR-02/review-cargo-tag-v2/`, Framewright
`bc30f36d-7cf0-4e2a-8dcd-5872387797b2`. Acquired clay plate and iron split ring,
16 x 8 x 2.5 cm overall, 2,740 triangles / 1,372 shared vertices. Actual GLB/FBX
closure, component count, UVs, dimensions and static fit pass. Clay metallic 0 /
roughness .75; iron metallic 1 / roughness .42, no micro-normal. Four GLB/FBX
views and live Framewright default/front-detail inspected. The first painted
front feather was doubled; CPU bake transfers the single acquired reverse
feather to the original front UVs without geometry/normal/UV changes. Original
paint and rejected views remain evidence. One inference pass saved valid maps
then failed shutdown (-1073741819), no retry. Package: 103 files / 28,160,869
bytes; manifest `44ce62259ba7850585a907fb21e7d55963551886713816930bc86ae737be9763`.
Static ring only; no swing/attachment simulation or lettering claim.

**AR-02 is prepared for review:** the full eight-design inventory is verified in
`assets/AR-02/catalogue-kit-review-v1/requirements-audit.json`, SHA256
`4d0b64bba563f2bc9171b92ba6b7c514791cc3eaf071d6023868f4a86fb8499d`.
Cabinet, map chest, scroll rack, label plaque, astrolabe, sextant, packing crate
and cargo tag each have verified package manifests, actual export audits and
matching served Framewright bytes. Reusable parts and the raised-lid inspection
copy are not counted as extra designs. Human approval remains pending.

Live state `evidence/ar02-catalogue-complete-state-v1.json`: **419 total / 356
current assets**, including **217 models, 129 images and ten audio**. **Fifteen
prepared sets / twelve unfinished**, three held empty, zero human approvals.
The remaining authorized requisitions are AR-03, CH-03, DH-02, DN-01, FX-01,
FX-02, GV-03, HC-07, RC-01, FX-03, HC-08 and TA-01.

Next commissioned work: HC-07 excavation camp reuse audit, then the other unfinished
requisition sets. TW-02's inherited mechanical
issues remain explicitly flagged; surface-review preparation does not clear them.

AR-03 modeling followthrough (2026-10-17): four exact older temple records and
source hashes are verified in `evidence/ar03-reuse-audit-v2.json`; v1's empty
case-sensitive database result is superseded, not treated as a successful live
inventory. Keep those differently shaped temple doors in TW-02. The acquired
AR-03 gate now has three clean closed parts in `assets/AR-03/gate-modeling-v5/`
(23,576 triangles): frame, positive-Y leaf and negative-Y leaf. The 6 x 10 m
envelope and base are restored; hinge axes are explicit, rear meeting edges are
relieved to avoid crossing during opening, and exact AR-01 lenses fit at 6 m.
Both closed/open four-view sheets were inspected. Actual GLB re-import checks
all 101 one-degree positions through 100 degrees with no moving contacts
(`export-fit-audit-v1.json`). This is operator modeling evidence, not approval.
AR-03 is now prepared for human review in `assets/AR-03/review-gate-v2/`:
three reusable gate parts plus the animated fitted-lens assembly. The current
assembly is `c26bfa6c-5e9a-41bf-9931-e09ba6560c7d`; previous matte previews remain
as earlier revisions. Exact geometry/normals survived painting; a source-albedo
bronze mask corrected the AI metallic prediction while keeping limestone rough.
Both actual GLB and FBX clips passed all 193 frames of an eight-second,
0–100-degree opening/closing cycle. Four-view exports and live Framewright
closed/open playback were inspected. Package: 201 hashed files, 166,503,826
bytes; manifest `a479a9331eb63ce932e4a412a75bfee62caefb7dc57c9f278a42e443c94ff949`.
The paint process saved validated maps then failed during shutdown; no retry.
`evidence/ar03-gate-complete-state-v2.json` records 427 total / 360 current
assets (221 models, 129 images, ten audio), **16 prepared / 11 unfinished**
requisitions, three held empty and zero human approvals. Repo verification:
757 passed / 15 skipped, lint, syntax and installed wheel checks passed.

The dense 543,979-vertex implicit smoothing attempt was deliberately cancelled
after over 19 CPU minutes (`gate-remesh-v1/operator-cancellation.json`). A
zero-smoothing voxel/QEM revision plus bounded explicit fairing completed; local
backtracking removed inverted faces/self contacts before cutting. Earlier
separation probes and their rejection reasons are retained. No inference retry.

GV-03 reuse check also advanced while the gate job ran:
`evidence/gv03-reuse-audit-v1.json` verifies the old wheel, flange and pedestal.
`assets/GV-03/station-modeling-v7/` fits the existing painted six-spoke 60 cm
wheel at 1.2 m on the acquired station, with a separate axle. Its 14,204
triangles are closed, without degenerates or self contacts; 73 native rotation
samples through 360 degrees clear the pedestal/axle. Four views and a close-up
verify the lower cut opening repaired using an adjacent acquired front-wall
patch. Earlier whole-depth patches caused self contacts and are rejected.
`pedestal-paint-reference-v1.png` is a built-in imagegen edit removing the wheel
from the conditioning image. The selected 9,000-triangle pedestal alone passed
UV transport (58.601% atlas occupancy). First actual paint attempt is
`pedestal-texture-v2/pedestal-paint-attempt001/`; v1 extraction failed before
paint, and the first v2 UV launcher lacked PYTHONPATH (corrected log retained).
The paint process saved validated maps then failed during shutdown (-1073741819),
without retry. Exact geometry/normals and AI albedo were restored; v3 semantic
material correction separates reflective bronze, rough limestone and amber glass.
GV-03 is now prepared in `assets/GV-03/review-station-v2/`: three rigid parts
(9,000 / 5,000 / 204 triangles), plus three source-face emissive display layers
(1,034 triangles). The ten-second `AlignmentThreeClicks` clip advances through
30/60/90 degrees and lights one window per click. All 241 actual GLB and FBX
frames pass clearance, pivot and indicator-state checks. Four static states,
packed Blend/FBX companions and local maps are included; live Framewright play
and 0/1/2/3 light states were inspected. Current assembly:
`9bf4a270-3888-4064-a50f-81e8a4cb93d9`. The existing wheel/paint remain unchanged.
Package: 340 hashed files / 203,613,603 bytes; manifest
`443f8216db2e329dfb2c3a7e72b4c1eac185e501824b8b6f4ca8a111bc69d375`.
`evidence/gv03-station-complete-state-v1.json`: 432 records / 365 current assets
(225 models, 130 images, ten audio), **17 prepared / 10 unfinished** requisitions,
three held empty, zero human approvals. Remaining: CH-03, DH-02, DN-01, FX-01,
FX-02, HC-07, RC-01, FX-03, HC-08 and TA-01. Audio/gameplay hooks and engine
integration remain separate; the commission is still active.

HC-07 is prepared in `assets/HC-07/review-camp-v1/`: **11 models**, packed
Blend/FBX companions, local maps, source/export fixed views and live Framewright
proof. Reused iron rack, cleaned charcoal lantern, three iron/canvas crate sizes
(60/90/120 cm wide) and their checked stack preserve the originals. The new
3 m scaffold has 14,970 triangles; the iron ledger table uses 18,000 after the
10,000-triangle option lost frame quality. Iron pickaxe/shovel have 10,000/8,000
triangles; patched 3 x 2 m canvas tarp has 15,000. Connected shovel acquisition
debris and local scaffold/table/tarp contacts were corrected before paint.
Five single paint attempts saved validated maps then failed during shutdown
(-1073741819), with no retries. All selected geometry, exact UVs and AI albedo
were retained through export. Lantern FBX uses an explicit opacity approximation;
GLB/Blend retain true glass transmission. Cheap camp furniture uses no fine wood.
Package: 507 hashed files / 380,203,857 bytes; manifest
`4fffeadc09016e3c897678bc311c0d57279599ee9f1af433240127fbf7f53583`.
`evidence/hc07-camp-complete-state-v1.json`: 447 records / 380 current assets
(236 models, 134 images, ten audio), **18 prepared / 9 unfinished** requisitions;
three held collections empty, zero human approvals. Remaining: CH-03, DH-02,
DN-01, FX-01, FX-02, RC-01, FX-03, HC-08 and TA-01.

HC-08's prior review package is `assets/HC-08/review-ennix-gear-v1/`: six distinct component
models and four additional assemblies, all staged and inspected in Framewright.
The 45 cm canvas pack, 70 cm short sword, 12 x 2 cm iron disc and 50 cm brass case
use image-conditioned acquisition and paint. Existing sextant and portable-scale
astrolabe are separate derivatives, preserving originals. The case has a hollow
interior, separate hinged lid and clasps, and holds exactly three discs. The full
gear layout includes two swords and all survey equipment (86,638 triangles across
20 mesh parts). Case panels were cleaned; the selected 22,170-triangle case and
6,272-triangle disc retain acquired detail. Actual GLB and FBX each pass the
106-position lid sweep and 73-position cap turn. Four paint runs saved validated
maps then failed on shutdown; none retried. Worst FBX four-view mean RGB byte
delta is 0.0626. Case interior UV streaking and static pack straps are documented;
FX-02 effects remain separate and unfinished. Package: 583 hashed files /
826,416,846 bytes; manifest
`8e9dea7e06030a4330e450a7c8e9b675cae450371f69255b432fd42431cd1b3a`.
`evidence/hc08-gear-complete-state-v1.json`: 461 records / 394 current assets
(246 models, 138 images, ten audio), **19 prepared / 8 unfinished** requisitions.
Held CH-01/CH-02/DH-03 collections remain empty, zero human approvals. Remaining:
CH-03, DH-02, DN-01, FX-01, FX-02, RC-01, FX-03 and TA-01.
Mark subsequently reopened HC-08's hero swords: remove the crossguard entirely,
use visible canvas wraps, and match the simpler short-sword silhouette of his
supplied Suikoden IV cover. The reference is operator-selected for new AI
acquisition; the prior individual sword, pair and full layout remain preserved
through the revised geometry, close-up material review and portable exports.
The hero revision is now prepared; current scope is **19 prepared / 8 unfinished**.
Latest steering adds a longer squared polished-black collar and matching black
pommel/upper band; canvas and steel blade remain. Mark reaffirmed Arcane-ish
style. Selected reference is `hero-short-sword-reference-v3.png`; new AI geometry
v2 succeeded once. `hero-short-sword-modeling-v5` retains 13,998 triangles at
70 cm nominal height, with squared/levelled acquired collar, zero topology
defects and inspected full/close-up views. Paint v1 saved validated maps then
failed at shutdown (-1073741819); no retry. Material v2 adds AI-conditioned
canvas weave while preserving painted wrap edges, desaturates the black fittings,
and retains original steel blade albedo. Current single/pair/layout revisions
passed live Framewright inspection and source/FBX comparisons (worst mean RGB
byte delta 0.00776). `assets/HC-08/review-ennix-gear-v2/` freezes ten models with
645 hashed files; manifest `aede3ce7f97a6c94518c199d14c4030adff2abef95949432ad3f695ca33ea799`.
The new sword/pair/layout contain 13,998/27,996/104,634 triangles; seven other
models remain byte-identical. Rejected collar fits v2/v4 and prior package remain.
Live snapshot: 471 records, 400 current assets (248 models, 142 images, ten audio),
three held collections empty, zero human approvals. See
`evidence/hc08-gear-complete-state-v2.json` and `assets/HC-08/browser-v2/`.
DH-02 is prepared in `assets/DH-02/review-fallen-gear-v1/`: five individual props
(dented helmet, scorched shield, torn ledger pack, reused blade and salvaged
iron torch) plus three arrangements. Pack v4 clears its last contact with a
bounded 2 mm fold separation. All three new paint attempts saved validated maps
before the known shutdown failure, with no retry. Three v2 arrangements retain
40,792 triangles each and zero intergroup contacts; packs rest on their sides
after rejecting v1's strap-supported poses. Eight live Framewright proofs and
32 source/FBX comparisons pass; worst mean RGB byte delta 0.1554. Portable
delivery: 506 hashed files, 563,999,790 bytes, manifest
`6c592f3ff40ed06e650279c96595b9d257b337ee6fd69e4c1c94b4f4a65797aa`.
DH-02 checkpoint `evidence/dh02-gear-complete-state-v1.json`: 477 records,
406 current assets (254 models, 142 images, ten audio), **20 prepared / 7 unfinished**.
Remaining CH-03, DN-01, FX-01, FX-02, RC-01, FX-03 and TA-01. Three holds empty,
zero human approvals. No fine wood, game import, push or publication.

DN-01 is prepared for review in `assets/DN-01/review-passage-kit-v1/`:
12 library models plus nine individually exported ceiling-fragment GLBs.
The earlier seven-model `review-passage-progress-v1/` remains preserved.
Four UV-preserving TW-01 derivatives provide straight, 10/20-degree descending
and 90-degree passages, each with 3 m clear width and 4 m vertical clearance.
The sloped segments use vertical shear to preserve vertical connector planes.
Each has separate walls/floor/ceiling and 43,766 triangles. Actual GLB/FBX floor,
ceiling and connector probes pass; interior and four-view appearances inspected.
New image-conditioned vent/canvas acquisitions yield a 100 x 60 x 18 cm vent
(14,930 triangles), 40 cm top-pivot cloth strip (5,000), and six-part fitted
assembly (39,930). Five approximately 32 cm strips follow measured openings;
only the concealed pinning bands contact the lintel. Arcane-ish pale limestone,
selective warm bronze and matte canvas are retained without micro-normal maps.
Two paint attempts saved validated maps before shutdown failures; neither retried.

Five further models complete the kit: sliding wall slab (47,604 triangles),
3 m rotating bronze floor ring with limestone foundation (12,344), nine-part
collapsible ceiling and exploded inspection (25,162 each), and skinned canvas
vent (39,930, twenty bones). These reuse acquired painted meshes; only fracture
caps are new surfaces. Wall, ring and cloth each have an eight-second preview
clip, played in Framewright. Actual GLB/FBX motion samples clear fixed geometry;
all 193 cloth frames in Blend/GLB/FBX retain fixed pins and clear hanging bodies.
Maximum exported cloth deformation delta is 0.000000210 m. Nine closed ceiling
fragments reconstruct the 3 x 3 x 0.5 m section within 2e-6 m; install its top
at 4.5 m for at least 4 m walking clearance. The wall needs a +Y pocket.

All twelve live models and 48 source/FBX appearance comparisons pass; worst mean
RGB byte delta 0.119517. Initial breeze FBX included an imported bone-display
helper and was rejected; selected `review-breeze-v3` excludes it and verifies
the exact six production meshes. Portable kit: 852 hashed files / 508,035,408
bytes, manifest `99c786de1ce1f5171fe866208ced05f2cfbb5c88fec564f2a72bf8e0c8da63ad`.
`evidence/dn01-frozen-package-audit-v1.json` rechecks every file and twelve live
served hashes; its visual addendum supersedes only the frozen cloth-detail
receipt's generation-time pending status. No frozen bytes were edited.
Latest `evidence/dn01-passage-complete-state-v1.json`: **491 records / 420 current
assets** (266 models, 144 images, ten audio), **21 prepared / six unfinished**.
Remaining: CH-03, RC-01, FX-01, FX-02, FX-03, TA-01. Three holds remain empty,
zero human approvals. Gameplay, Chaos,
cloth simulation and native engine integration remain separate from this review.

RC-01's complete review set is now frozen in `assets/RC-01/review-cell-kit-v1/`:
seven models, portable GLB/Blend/FBX/maps, seven reference/decal images, six
interior views, source/FBX comparisons and live Framewright evidence. The set
contains a stone bench, separate hinged barred doors, shackle fixture with four
separate links, small emitter pair, cell shell, complete furnished cell and
inspection cutaway. All seven actual GLB/FBX exports pass surface checks; both
animated exports pass all 193 opening-cycle frames with zero checked contacts.
The cell is 6 x 6 m inside, 4 m clear at 961 points, with a 2.3 x 2.8 m doorway.
Bench is matte limestone; no cheap timber. The full room has 198,260 triangles
across 28 meshes; the inspection-only cutaway has 157,116 across 23 meshes.

Selected derivatives are recorded in `rc01-delivery-v2.json`: components v1,
door/shackle fittings v2, architecture v3, emitter pair v11 and room/cutaway v3.
The emitter's inherited frame/glass contacts were resolved on copies by bounded
frame repair, measured glass Boolean trim, local fairing and a 0.995 radial fit.
Actual GLB/FBX frame/glass and self-contact checks are now zero; the original
GV-04 source remains untouched. Tally marks sit on a clear stone panel. Door
world rotation reaches 100 degrees; both clips played in Framewright and were
captured open at four seconds. The cutaway retains the tally wall.

The frozen package contains **655 hashed files / 494,981,554 bytes**; manifest
SHA256 `ac11ac73270ca00f98f9ae0b1f11889cb64d11a61d81f5c19b5f87c8076a30df`.
All 34 source/FBX appearance comparisons pass (worst mean 0.164 RGB byte units).
FBX glass uses an explicit opacity approximation; GLB/Blend retain transmission.
Paint teardown failures and rejected geometry/motion derivatives remain recorded;
no inference retry. Human review, gameplay/collision and native engine checks
remain separate. The actual dampening field is still pending under FX-01.

Latest `evidence/rc01-cell-complete-state-v1.json`: **511 records / 440 current
assets** (273 models, 157 images, ten audio), **22 prepared / five unfinished**.
Remaining: CH-03, FX-01, FX-02, FX-03 and TA-01. Holds remain empty; zero human
approvals. No render/inference/export process remains running at this checkpoint.
Observe the timed stop above; the goal is still active until closeout time.

**CH-03 base-rig progress (2026-10-17 23:45 MDT; set still unfinished).**
`assets/CH-03/review-raider-base-progress-v1/` freezes 126 files / 93,827,199
bytes; manifest `481946a7b61193a356370aa45bae483470b24dfdf5bc9a29056eb242a46c7fdc`.
Current Framewright model `03f12088-0e3b-4f7e-a1ff-d1c613763e73` is revision 3,
**Raider base — rigged, relaxed held pose**, SHA
`56d4c32ed3d634cc30d8e0e98ddfab953d7d0e96a403243e49b381bacc8ce38f`.
The painted source and first rig remain earlier revisions. Four-view image
`13938f74-0bf8-4264-9356-385594f4a5ba` is current beside the source reference.

The 1.82 m NPC has 17,269 triangles, 87 Manny bones including explicit root,
at most four influences and zero unweighted vertices. Source-bound measured
glove joints, local linear subdivision and isolated weights fix curl spikes;
the painted surface/UV field and image pixels are preserved. Native ARP controls
are retained. Unit-scale normalization fixes the first GLB's misleading 2 cm
static bounds. A scoped Manny profile adds its already-required root to the
checker's bone-name allowlist; required bones, hierarchy and budgets are unchanged.
Actual static/held FBX companions pass; PBR channels match exactly and held skin
differs by under 20 micrometres. Review GLB/Blend face +X; FBX explicitly uses
the repository's -Y Blender to +X Unreal skeletal transport.

`Raider_Relaxed_Held_Pose` is a two-second held stance, not breathing or locomotion.
It passes 49 exported stance samples and four-view review. Framewright playback,
scrubbing at 1.0 s and exports with/without the clip were checked; the base
geometry/rig/images remain identical. The UI reports 1.82 m. Its independent
rig badge remains Unknown skeleton because the compiler profile path is not
configured; this is recorded, not treated as animation certification.

`evidence/ch03-base-rig-progress-state-v1.json`: **515 records / 441 current**
(273 models, 158 images, ten audio), still **22 prepared / five unfinished**.
At that checkpoint CH-03 still needed the additional armour looks, weapons and
Bulwark; the component progress below supersedes that inventory. FX-01, FX-02,
FX-03 and TA-01 also remain.
Three holds remain empty; no human approval, game import, push or publication.
The scheduled 00:45 MDT closeout is now reached; see the top-of-file checkpoint.

**CH-03 outfit/weapon progress (2026-10-18 00:32 MDT; set still unfinished).**
`assets/CH-03/review-unrigged-components-v1/` freezes **386 files / 305,689,361
bytes**; manifest `7010497471718b7f3a6b9a07e4875ea26530d8dbdfcd26d547d30a15631e15a8`.
Five new models are visible in Framewright: Bulwark (2 m, 14,996 triangles), olive
scout (look 2, 1.82 m, 14,998), field guard (look 3, 1.82 m, 14,999), a reused
clean steel blade (70 cm, 5,000) and short carbine geometry (65 cm, 7,500).
The three new bodies are **unrigged**. The original base rig remains intact.
The clean blade retains the earlier raider crossguard geometry; it is separate
from Ennix's new guardless hero weapon.

Separate source-conditioned AI acquisitions precede cleanup. Distinct head
mapping passes repair the eye regions; bounded face-only atlas masks retain
original hair/collar/body pixels, geometry and UVs. NPC faces/gloves remain coarse
in close-up. Body paint processes crashed only after validated maps were saved;
failed exit receipts remain. **Carbine paint crashed before any maps or validation**
and was not retried; mesh/UV CPU checks passed, native cause unresolved.

Painted models include exact GLBs, packed Blender, FBX and local scalar maps.
Actual companion reimports retain geometry within 0.06 micrometres; all four FBX
view sets and all five live Framewright models were visually inspected.
Evidence: `assets/CH-03/browser-components-review-v1/` and
`evidence/ch03-components-progress-state-v1.json`.
Latest inventory: **529 records / 455 current** (278 models, 167 images, ten
audio), still **22 prepared / five unfinished**. CH-03 needs Manny rigs,
deformation/held poses for scout/guard/Bulwark and weapon-specific grips; carbine
also needs paint-failure diagnosis, separate moving parts, muzzle +X and grip
pivot. Remaining effects: FX-01, FX-02, FX-03, TA-01. Three holds empty; zero
human approvals. No game import, push or publication.

**Next-rig preparation (2026-10-18 00:39 MDT):** source-bound -Y rig transport
and measured glove views are saved for all three new bodies in
`{scout,guard,bulwark}-rig-transport-v1/` and `*-hand-surface-probe-v1/`.
Scout/guard each have 42 ray-measured draft hand joints and inspected overlays in
`*-hand-landmarks-v1/`; body markers and binding remain pending. Bulwark's
middle/ring glove digits are joined even in the dense AI acquisition: increasing
the reduction budget alone will not fix that. See `bulwark-dense-hand-probe-v1/`
and `outfit-rig-preflight-review-v1.json`; its live Framewright notes include the
finding. Resolve source-guided glove separation before independent finger binding.
These are new working files outside the frozen progress package.

`evidence/native-effect-reuse-audit-v1.json` identifies seven unchanged native
source files from the previous isolated AetherEffects review project, matching
its frozen delivery hashes. Ember, mist and pulse graphs are useful starting
points; none already satisfies FX-01/02/03, and no matching TA-01 post-process
was found in that selected inventory. No Unreal editor was launched or source
effect modified. Continue in a new isolated review project after the timed pause.

TW-02's corrected chain winch is prepared in `assets/TW-02/review-group-18-winch-v3/`,
current Framewright model `18f331d7-26ba-4ddb-ae75-4d00c6772a6f` (v2). Mark's
October 4 veto required a new acquisition: the old mechanism remains intact.
The new iron/bronze mechanism is nominally 2.4 m wide, 1.2 m deep and 1.8 m tall,
with separate frame, axle-centred drum and crank/gear. Forty-one rigid copies
of an existing acquired link form two wraps and a short tail. Automatic budgets
selected 15,000 mechanism triangles and 2,000 per shared link: 97,000 evaluated
triangles, 17,000 shared geometry triangles. The link was rebaked; worst-view
lit/unlit SSIM was 0.992/0.995. Actual GLB and FBX each pass closed-surface,
nondegenerate-face, self/interpart-intersection and all 40 adjacent-link checks.
Maximum companion vertex delta is 0.0000002181 m; worst four-view FBX mean RGB
byte difference is 0.001609. Imported flat normals were corrected; localized
QEM folds beneath the frame and behind the gear were faired by at most 6/2 mm,
then the reviewed smooth normal field was restored. Rejected fits and exports,
the failed paint shutdown (-1073741819), and the original source are retained.
No inference retry. The 133-file / 75,246,257-byte package manifest is
`8a0af55abf1012f20163185db69299eb8b3db012196b37b17c8858feb1ff3894`.
Four views, actual FBX and live Framewright model/reference were inspected.
This is a static review assembly; chain payout, gameplay, collision/runtime
validation and human visual approval remain open.

TW-02's separate corrected ceiling alternative is prepared in
`assets/TW-02/review-group-17-ceiling-v1/`: 6 x 6 x 1 m, top-centre pivot and
`SOCKET_Ceiling`, 19,994 triangles and one closed component. A new image-conditioned
acquisition replaces the rejected flat underside with connected hanging blocks;
the original GLB remains intact and is copied into the package. Automatic QEM
selected 20,000 triangles before paint. Actual GLB inspection then found three
detached single triangles that the Blender topology report did not expose;
cleanup removed only those remnants and restored the declared dimensions.
The painterly limestone has zero metallic response and no normal map. Four
fixed views, underside and unlit top, six actual FBX comparisons and live
Framewright model/reference views were inspected. Both GLB/FBX are closed and
retain the mounting socket; maximum companion vertex delta is 0.0000003372 m.
One paint attempt produced validated maps then failed during shutdown with
exit -1073741819; no retry. The 129-file / 81,209,989-byte package manifest is
`a4f2737d39957658f855e801792a36d420c692eaf1fc5cf575dc2ac7960f072d`.
Human review and collision/runtime checks remain open.

TW-02's `assets/TW-02/review-group-16-images-v1/` contains six environmental
decals, a ritual inlay, three seals and three murals. Built-in ImageGen edited
the older images into the Artiss direction; the murals reuse HC-06's portrait
and feather/ring heraldry. Original compositions remain illustrative candidates,
not newly confirmed lore. All 13 RGBA images passed alpha diagnostics against
pale limestone and dark teal and were inspected in Framewright. The first
cobweb had fabric-like membranes; its retained rejection led to a thinner silk
revision. The package has 97 hashed files / 68,750,538 bytes, manifest SHA256
`3b3b65a0818efb8966a6e9b704e4dda6f5aeeb7d414dbfbea6a41849c0458ad1`.
Prompt sets, original sources, 26 diagnostic composites and 13 browser captures
are included. Human review and in-engine decal filtering/placement remain open.

Mark's 2026-10-17 floating-cache supplement is prepared separately in
`assets/FLOATING-CACHES/review-delivery-v3/`. Framewright collection
**Floating caches and traversal - source reuse** contains seven reused models:
two wooden treasure chests, three stone ledges at 150/250/400 cm top elevation,
a stone handhold and an iron swing ring. All three ledges span 150 cm; their
numbers describe elevation, not length. Original wood/metal surfaces remain as
requested. These rare buoyant-timber valuables coexist with the common iron
chest; ordinary cheap equipment still does not default to wood. DH-03 stays held.

Both chest GLBs retain their original hinges, sockets and seven-second
`OpenClose`, with new twelve-second `FloatHover`, `FloatRoute` and `FloatAndOpen`
clips. Preview values: 1 m altitude, +/-12 cm bob, 4 m out-and-back travel.
All seven models were inspected in Framewright, including actual chest playback
and open poses. Seven packed Blender files reopened correctly; thirteen
clip-specific/static FBX exports passed sampled transform and local-map checks.
Export-only UV transport fixes the alternate-UV lid interiors; authored neutral
specular tint is represented as scalar strength in FBX. Representative paired
GLB/FBX views differ by at most .2221 mean RGB byte value. Maximum transform
delta is 0.0000004769 and surface-vertex delta is 0.0000001333 m.

The bundle has 333 hashed files / 1,324,753,690 bytes; manifest SHA256
`af410074564019f7604398d336acc9684a2964e2a2b217e05e3ca114a3aec73d`.
The royal chest's inherited interior-corner texture blemish and source chest
densities near 200k triangles remain explicit review/runtime follow-ups. This
source-reuse supplement does not increment TW-02's painterly completion count.
Puzzle notes reference existing ropes/anchors without duplicating them; proposed
access puzzles and preview motion are not implemented gameplay or canon physics.

TW-02 group 03 is prepared in `assets/TW-02/review-group-03-v1/`: intact/tattered
banners at 1.5 x 6 m and 2 x 9 m, bronze rods at 1.8/2.3 m and a wall bracket.
Five distinct AI mapping jobs preserve their geometry/UV authorities. Torn cloth
shares mapped RGB with its exact normalized-OBJ donor and retains original 4096
alpha pixels, MASK cutoff .5 and double-sided flags. The initial paint squashed
the feather motif; selected cloth v3 projects the intact AI reference through
existing UVs after AI acquisition, retaining mapped borders and fringe. v1/v2
rejections remain. Cloth is matte; hardware uses metallic 1 and roughness .26-.36.
Rigid parents preserve the original nodes/pivots: cloth/bracket +90 Z for +X
front, rods -90 Z for local -Y length. All original geometry bytes remain intact.

Seven actual Framewright models, 28 GLB views and 28 actual FBX views were checked.
Blender/FBX reopen with local maps; maximum surface-vertex delta is 0.000000170 m.
Opaque FBX appearance differences are below .001 mean RGB byte value. Tattered
companions use explicit cutoff opacity maps; small filtering differences remain
at edges (maximum mean .200 RGB byte value), with original GLB alpha unchanged.
Bundle: 300 hashed files, 226,021,651 bytes; manifest SHA256
`c9bc4b1a83f5ae9a37b35270720599670dc56f484f00420eefc814556c99a858`.
All five paint child processes again failed at teardown after validated output;
failures are retained, no inference retries. Every process is terminal.

TW-02 group 04 is prepared in `assets/TW-02/review-group-04-v1/`: 3.16 m stair
panel, 3/6 m curbs, 3/6 m balustrades, post, end cap and sloped rail. Six generated
references condition eight distinct mapping jobs. All original mesh/UV/normal,
node, local pivot and topology bytes remain intact. Linear runs use a rigid
-90 Z parent to run along local -Y; symmetric post/cap use +90 Z. Stone has
metallic zero, roughness .74-.84 and no normal/emission map. The stair panel
now carries feather-in-rings motifs. No remodeling or density reduction.

The 6 m curb/rail each preserve two nodes sharing their original 78,000-triangle
mesh (156,000 scene triangles). Generic one-object transport refusal is retained;
explicit shared-instance transport v2 passed. An incorrect 3.16m reference alias
was rejected by CLI before any inference; fixed paths were validated before the
first actual job. All eight AI jobs saved validated output then failed teardown
-1073741819; failures retained and no inference retries. All processes terminal.

All eight actual Framewright models, 32 GLB and 32 FBX beauty views were checked.
Local maps resolve on Blender/FBX reopen. Maximum companion surface-vertex delta
is 0.000000894 m. FBX image differences are below .000781 mean sRGB byte value,
maximum individual channel 7. Shared-instance FBX material-slot warnings remain
in the export log; both repeated sections match in actual renders. The delivery
has 332 hashed files / 284,466,709 bytes; manifest SHA256
`a869360560b21009193fbcb31009295807d763fb77236433ae05b531d8e66313`.

TW-02 group 05 is prepared in `assets/TW-02/review-group-05-v5/`: floor/standing
braziers, hanging lantern and wall torch. Four distinct image-conditioned paint
attempts saved validated output and failed at teardown; no inference retries.
All jobs are terminal. Bronze uses metallic 1 and broad roughness .38-.46, dark
metal .48-.58, with the original noisy normal maps and doubled specular removed.
That bundle's three non-lantern props preserve original geometry/UV/normal bytes;
their newer user-requested refinements are described below. Wall torch uses a rigid
180 Z parent for +X physical front; other props +90 Z, keeping local pivots.

Mark requested smoother lantern surfaces and comparison with the earlier project.
Current lantern material/cleanup v10 (Framewright revision 6, asset
`aa77a865-083c-41f7-aef5-a3b1bbe8a905`) fairs acquired bronze by at most 3 mm and
filters normals. All 10,000 triangles, UVs, maps and pivots remain; glass positions
are frozen. Orientation/area guards prevent new inverted or collapsed triangles.
The earlier project was inspected in Framewright and rendered locally. Simple
normal recalculation and dense-source transfer were insufficient/rejected; v9
surface cleanup was superseded after a geometric check found 26 rotated faces.
V10 backtracks affected vertices. Slight handmade edge undulations remain.

Lantern original transmission and glass RGB remain. Opaque bronze and thin glass
use separate draws of the original triangle multiset to avoid transparent sorting
artifacts. Rejected pale panes, whole-mesh alpha, border classification and cleanup
versions remain. Actual Framewright, four GLB views and four actual FBX views per
model were inspected. Blender/FBX reopen with local maps. FBX uses an explicit
opacity approximation without refraction; lantern interior is slightly brighter
(maximum mean RGB byte difference .715). Other props differ by under .00108.
Group manifest SHA256:
`eb2b211ba5ca8005f6fdc55992cfd5d8ff186817385d4ff5e47ea3adb5fc7d7f`.

Mark subsequently requested smoother lighting props, explicitly allowed more
faces, and favoured blackened metal with warm brass. This direction is saved in
Framewright World and `commission.json.quality_direction`. Current floor brazier,
standing brazier and wall torch are in `assets/TW-02/review-lighting-smooth-v1/`:
14,995 -> 24,733, 15,000 -> 24,900 and 10,000 -> 16,600 triangles respectively.
Adaptive subdivision of the acquired meshes, fairing bounded to 5 mm and filtered
normals reduce triangular highlights. Base/mount vertices stay fixed; original UV
vertices, maps, materials and pivots remain, with interpolated UVs on new faces.
Per-face ancestry is retained, with no new inverted/collapsed or degenerate faces.
Minor acquired edge waviness remains. Black-and-brass material design is unchanged.

All three current Framewright revisions (v2) and four GLB/clay/actual-FBX views
per model were inspected. Six Blender/FBX companions reopen with local maps;
maximum paired vertex difference is 0.00000008430 m and maximum FBX mean RGB-byte
difference is .003399. Bundle: 171 hashed files / 271,234,123 bytes; manifest SHA256
`f3fad245c2a9e9bac09a886aaac3e2c692bd887c08921a58a32796b25371c030`.
Earlier revisions and the four-prop group05-v5 bundle remain intact. These are
cleanup revisions, so they added no inventory items. No new AI
inference, human approval, game import, publication or push.

TW-02 group 06 is prepared in `assets/TW-02/review-group-06-v1/`: ceiling anchor,
20 cm single iron link, and nominal 1/3/6 m chain variants. Exact binary and UV
identity established that one mapped link serves all four chain files; anchor
uses its own mapping. Source geometry, UVs, normals, instances and local pivots
remain unchanged, with one rigid parent for +X front and local -Y chain runs.
Dark forged iron and brass anchor fittings use broad roughness, without the
old noisy normal map. Both AI jobs saved validated output then failed teardown
(-1073741819); those failures are retained and no inference was retried.

Five GLB/FBX sets and actual Framewright views were inspected. Ten companions
resolve local maps; maximum paired vertex difference is 0.00000054483 m and
maximum FBX mean RGB-byte difference .002607. Bundle: 198 hashed files /
202,898,340 bytes; manifest SHA256
`bf69bef2be108715c40ad5f303a24a12182d7a52797682b1560a1316c0db0c8a`.
Known source limitation: the 1/3/6 m link instances are coplanar and overlap,
rather than alternating as a physically interlocked chain. Preserved for this
material-only repaint, flagged in Framewright, inventory and package README;
assembly correction remains open. No human approval or production certification.

Mark then requested checking the other project and corrected the broad brass
interpretation. Live inventory in **The Aether Wars — Realistic Asset Review**
(`bff69ad8-3084-4321-aebc-95a73e0971e1`) confirms all 13 mechanical sources and
all four lighting sources already exist, with exact hashes matching our inputs.
Reuse suitable existing models/material divisions; adapt only identified Artiss
mismatches. Brass is selective, not required on every fitting. Preserve the
completed smoother lighting variants and the metallic response of actual bronze.
World and `commission.json` now contain this corrected direction.

Important exception: the existing chain winch has Mark's 2026-10-04 SEND BACK
feedback requesting new acquisition, not another repair. Exclude it from reuse
or repaint. The condenser also retains legacy quartz-core semantics; check the
Artiss driftglass requirement before carrying it forward. Existing axes, pivots,
materials and low-poly suitability still need per-asset convention checks.

Before the correction, eleven group07 references and all 13 UV transports were
prepared. Cog2/4m do NOT share identical geometry/UVs. Three separate cog paint
jobs saved validated maps then failed teardown (-1073741819), with no retries;
these remain unselected, and no group07 model was imported. The serial coordinator
was stopped during cog6m; that child finished and wrote its terminal receipt.
Unstarted pipe jobs were removed from the executable queue, with the original
queue preserved in the audit. No inference is running. Evidence and next reuse
dispositions: `evidence/mechanical-existing-project-audit-v1/`. The other project
was inspected without changing any asset or project content. Goal remains active.

Ten of those mechanical models were first staged in Artiss as **reuse comparison
candidates**, preserved in `assets/TW-02/review-group-07-reuse-v1/`: 2/4/6 m cogs,
1/2/4 m pipes, elbow, tee, flange and valve wheel. Original geometry, UVs, normals
and every texture image byte remain exact. Normal map strength is .12 and the
source's doubled specular color factor is removed. A rigid parent supplies +X
axle-piece facing and local -Y pipe runs; source pivots remain, with sockets
recovered from original construction metadata. No new acquisition or repaint.

All ten GLB four-view sets and actual Framewright models inspected. Twenty
Blender/FBX companions reopen with local maps; maximum paired vertex difference
is .00000059605 m. All 40 FBX views compared with GLB (maximum mean RGB-byte
difference .001886); cog6m/elbow/valve FBX sets also visually inspected. Bundle:
368 hashed files / 1,254,204,123 bytes, manifest SHA256
`e08b174665c0c3b8372f03b8dbb6187a5559a32e7d0aa7ee63ec725fbc1df2d3`.

Those initial comparisons retained fine photographic rust/speckling, especially
on the elbow. The selected derivatives now live in
`assets/TW-02/review-group-07-surfaces-v2/`: three cogs, six pipe pieces and the
valve wheel. Seven corrected built-in ImageGen references and ten distinct
locked AI mapping attempts preserve the original material division: iron pipes,
iron cog teeth/spokes with brass central hubs, brass valve rim/spokes and dark hub.
Original geometry, UVs, normals, pivots and recovered socket nodes remain exact.
Normal maps are disabled; metallic response uses broad roughness shifts.

The cog mappings spilled brass onto inner iron spoke sidewalls. An unlit check
confirmed the colour was in the albedo. Those v2 candidates were rejected;
v3 uses a CPU material-node bake on the acquired mesh/UVs to restrict brass to
the hub, preserving broad painted wear. All ten mapping children wrote validated
outputs then failed teardown (-1073741819); failure receipts remain, no retries.
Original flange/bolt/rim irregularities remain visible under strong reflections;
this material pass is not a geometry cleanup or human approval.

All ten GLB four-view sets and live Framewright viewers were inspected. Twenty
portable Blender/FBX companions resolve local maps, maximum paired vertex delta
0.00000059605 m. All 40 actual FBX views numerically match GLB (maximum mean
RGB-byte difference .001534); cog6m/elbow/valve export sheets also visually checked.
Bundle: 412 hashed files / 453,271,888 bytes, manifest SHA256
`822391793a582ef421be2a7d109aae6a037346498b1018cb34222674f3d1af5d`.
At that checkpoint TW-02 had 43/121 surface candidates prepared.

The reused gauge/condenser are now packaged in
`assets/TW-02/review-specialties-v1/`: 112 hashed files / 163,123,134 bytes,
manifest `c3ad22fc0f039741d46d64967572b7135a6f38bb134b27eaca7da008aa9070f5`.
Gauge retains its accurate dial and clear glass; condenser retains inner iron
and window, with a non-emissive teal driftglass insert. Dark iron bodies and
selective brass trim preserve the old material divisions. Original geometry,
UVs, normals, nodes, pivots and sockets remain exact, plus a rigid +X orientation
parent. Source densities (100,380 / 175,124 triangles) remain under the explicit
repaint-only scope; automatic reduction proposals were not applied.

Both four-view GLB and selected actual FBX sets, and both live Framewright
viewers, were inspected. Four portable companions resolve their local maps;
maximum paired vertex delta 0.00000016859 m. GLB/Blender retain true glass;
FBX uses documented opacity approximations. Use `aether-condenser-v2.fbx`:
the rejected original FBX lost colours behind vertex-colour multiply nodes.
V2 bypasses only multiplication by verified all-white vertex colours; the
original GLB and packed Blender stay unchanged. A constant window needs no UVs;
the package validator now permits only verified untextured scalar parts.

The overnight condenser run stopped without output or a terminal receipt.
The user explicitly resumed work in the morning; a fresh v3 mapping preserves
the interrupted v2 evidence. Gauge v1 and condenser v3 wrote validated results
then failed teardown (-1073741819), retained with no crash retries. The local
Framewright service was restored from the existing published executable and
original database, at loopback port 5179. Recovery evidence is recorded; no
configuration, provider, model or database replacement was performed.

TW-02 group 08 is prepared in `assets/TW-02/review-group-08-v2/`: crypt and temple
animated assemblies, two separate frames and four separate leaves. The eight
sources were freshly hash-matched to the older review project. Exact geometry,
normals, UVs and animation accessor bytes are retained, with rigid +X parents.
Assemblies retain seven-second OpenClose clips at 299,999/300,000 triangles;
standalone components retain their original 15k-30k meshes and restored metadata
sockets. Four acquired surface mappings cover mirrored leaves and frames;
shared dense leaf UVs were proven, and six CPU bakes transfer maps to reduced UVs.
Limestone stays matte, crypt rails are iron, temple panels are dark iron with
selective bronze. Original-albedo masks corrected crypt panel boundaries after
three rejected trials. All four mapping processes failed teardown after writing
validated output; receipts retained and no inference retried.

GLB/Blender/FBX geometry checks passed, maximum paired vertex delta 7.748604e-7 m.
Sampled FBX hinge matrix delta is at most 4.418358e-7. Blender adds one frame by
default on FBX import: use anim_offset=0 to inspect stored frames 1-168 at 24 fps.
All eight GLB and actual FBX four-view sets plus live Framewright viewers were
inspected, including assembly open/closed scrubs and playback. Worst mean FBX
image difference is 0.002246 sRGB byte value. Unreachable old images were removed
losslessly to fit Framewright's existing upload limit; every visible map and
geometry/animation accessor byte was verified. Source binary-prefix identity is
not claimed for this compact storage. One CPU crypt-right bake crashed in NumPy;
a separate v2 with AVX2/FMA3 disabled completed, with crash evidence preserved.
Package: 372 hashed files / 667,420,925 bytes; delivery.json SHA256
`7c295d88810a8a8ba73ab1871e5286077d88febd753ade1252e49a955bcbb31b`.

TW-02 group 09 is prepared in `assets/TW-02/review-group-09-v4/`: floor border,
pillar base/capital, sandstone cornice, crown and skirting. Six existing meshes
retain exact source geometry, UVs, normals and original local nodes. Pale matte
limestone replaces the overly amber first surface pass. Four linear modules
use a rigid canonical wrapper: +X front, rear/base endpoint pivot, Start to End
along -Y for 6 m. Existing reduction overshoot is recorded, not flattened.
Selected materials are v3; four linear files use v4 metadata-only repair because
the installed Three.js loader interpreted descriptive `extras.pivot` text as a
coordinate vector, producing NaN bounds. `pivot_description` preserves the
full binary, materials and transforms; actual Framewright displays now pass.
All six GLB and actual FBX four-view/close sets and browser views were inspected.
Maximum companion surface-vertex delta is 0.0000010942 m; worst mean FBX RGB byte
difference is 0.003431. Six AI mapping jobs wrote validated output then failed
teardown; no inference retries. Rejected surfaces, CPU bake setup failure,
placement assertions and blank-viewer evidence are retained. Source triangle
counts remain inherited under repaint-only scope, without runtime acceptance.
Package: 311 hashed files / 206,083,437 bytes; delivery.json SHA256
`7955ad61ed95f48d24435350dfb312136412aed00a63b9cc0ab58986aa8acbfe`.

TW-02 group 10 is prepared in `assets/TW-02/review-group-10-v4/`: 27 driftglass
variants reused from the older project. Clusters 1/2 m, hero growths 6/8 m,
shards 0.3/0.6/1 m and wall growths 3/5 m each have cyan, blood-red and violet
options; use one accent per space. Twelve hero/wall inventory entries were stale:
the current source revisions already removed floating fragments and were selected
by live record/hash, with the old selections retained. Every target keeps exact
source mesh/accessor/UV/normal bytes and local nodes, plus canonical orientation.
Inherited buried-foot pivots and source polygon counts remain unchanged.
Four image-conditioned mapping jobs wrote validated maps before failed process
teardown; no inference retry. Three smaller UV layouts received CPU map transfer.
Selected v3 preserves mapped albedo and uses optical frosting at the foot, zero
metal/emission, no normal, maximum transmission .48 and IOR1.47. V1 base gloss
and V2 horizontal grey-band comparisons remain rejected. Actual GLB and FBX four
views and all 27 Framewright viewers were inspected. FBX v3 lost base colour
behind identity white vertex-colour multiplication; v4 bypasses only verified
RGBA1 for FBX export. True glass remains in GLB/packed Blender; FBX uses an
explicitly inspected opacity approximation, with no optical-equivalence claim.
Maximum companion vertex delta: 0.0000004054 m. Package: 1,077 hashed files /
1,324,362,736 bytes; delivery.json SHA256
`03706583926aecc816efa38b5b80ab8857fb5d47091732162deceadb3e89531a`.

TW-02 group 11 is prepared in `assets/TW-02/review-group-11-v1/`: ceiling
fissure, stalactites 1/3/6/10/15 m, abyss bridge, fallen column and crowned head.
Five built-in ImageGen references conditioned five existing-mesh mapping jobs;
all produced validated maps before failed teardown, with no retries. Four
smaller stalactites received CPU projection into their separate original UVs.
All surfaces are matte limestone with zero metallic and no micro-normal.
Eight models retain exact source geometry/UV/normal/node data; the head has
one explicitly user-requested cleanup exception. Head v2 removes eight detached
acquisition fragments (134 triangles), leaving 14,866 triangles. Every surviving
position, UV, normal and tangent is bit-identical; bounds, pivot and original
fallen pose remain. Original source and rejected v1 evidence are retained.
Current head revision: `238faf0e-893b-4220-a9e8-cb13c67c45f1`.
GLB, packed Blender and FBX companions, four fixed views, player-facing close
views and all nine actual Framewright models were inspected. Maximum companion
vertex delta is 0.0000010663 m; worst FBX mean RGB byte difference is .001726.
Package: 447 hashed files / 482,776,362 bytes; manifest SHA256
`997423d87f828d48f29dbd9623f4fc75e0518745016d92256342061560cee0ae`.

Next: remaining existing-library surfaces, then geometry repairs for the
rejected winch, ceiling rubble and coin pile. Ceiling rubble still has the old
flat underside and was excluded from group 11. Seventeen furnishing sources
were checked against current old-project records and copied to
`assets/TW-02/source-group-12/`; fixed source views and supplemental chest
interior/lid-underside, carpet-top and urn-interior views now exist. The coin-pile
source is a 3 cm scatter, not the requested 15–25 cm
mound (120 instances of a 12,000-triangle coin); retain its SEND BACK status.
Chests need preserved hinges/animations and independent source-UV transfers.
The common chest must lose its default oak material, including the interior.
Mark corrected the material economy on 2026-10-17: wood is scarce prestige,
not a cheap default. `evidence/material-economy-correction-v1.json` records
the local lore/requisition evidence and the verified Framewright World update.
Weapon-rack wood reference v1 is rejected and was never mapped or imported;
iron-only v2 is staged. The ornate timber lectern is an Archive prestige piece,
not the HC-07 Raider ledger table. Cheap camp furniture/storage use iron,
sheet metal, canvas and salvage; DH-03 remains held. Three selected surface
references (rack, lectern, pedestal) and their three reviewed models are staged.
`assets/TW-02/review-group-12-simple-v1/` has exact GLBs, packed Blender, FBX,
portable maps, four views, beauty/unlit closeups and actual Framewright evidence.
Rack v2 fixes tan side-wall mapping streaks using a generated neutral iron swatch
projected through the existing UVs; rejected v1 remains. The lectern retains
prestige timber and selective bronze; pedestal stone stays nonmetallic. Original
geometry, UVs, normals and base pivots remain unchanged. All three mapping jobs
wrote validated artifacts then failed teardown; no inference retry. Maximum
companion vertex delta is 0.0000001333 m; worst FBX mean RGB byte difference is
.001156. Package: 184 hashed files / 161,007,642 bytes; manifest SHA256
`3e96c282dedf76fb21ecde9fe35d880b917bf565023b629f7bc94c268508394a`.
TW-02 has 107/121 prepared models; 14 models and 13 images remain. The blanket-
brass queue stays empty. Source optimization and inherited chain assembly
issues remain open. Framewright stays running,
Artiss active, with human approvals still zero.

The common chest now follows in `assets/TW-02/review-group-12-common-v1/`:
base v3, lid v4 and animated assembly v1. Common timber is replaced by dark
iron inside and out. Two built-in ImageGen references conditioned existing-mesh
mapping; both wrote valid artifacts and failed teardown, with no inference retry.
Base interior streaks and lid material-boundary fringes were rejected. Selected
CPU derivatives use the neutral AI iron swatch through original UVs, with smooth
black lid straps. The 200k assembly has independent UVs: three CPU transfers
carry the selected parts' maps without changing geometry, sockets or OpenClose.
The first panel bake failed on the original TEXCOORD_1 material; its log remains,
and a temporary UV0 carrier fixes the transfer without altering final mesh data.
Four views, interior/unlit and complete open-pose renders, actual FBX appearance,
all format pivots/dimensions and Framewright playback were checked. Maximum
companion vertex delta is 0.0000001265 m; maximum hinge-matrix delta is
0.0000001478; worst FBX mean RGB byte difference is .000363. Package: 335
hashed files / 230,449,698 bytes; manifest SHA256
`b4ec8f7b9869760834bec30b1856c99cd66781b5967890052ad7a2faa4e28ac3`.
Source counts remain 10,000 / 33,800 / 200,000 triangles, not a runtime-budget
endorsement. Assembly `0611a3a8-cd64-4b8b-83ba-350c8a4d765e` remains available
in Framewright. Prestige timber must not become the common camp-material default.

The royal/relic surface pass is now packaged in
`assets/TW-02/review-group-12-prestige-v1/`: royal base v3, royal lid v1,
relic base v4, relic lid v1 and both animated assemblies v1. Royal surfaces use
rare timber, black iron and selective bronze; relic surfaces use pale stone and
bronze. Four built-in ImageGen references conditioned existing-mesh mapping.
All four jobs wrote validated artifacts then failed teardown; no inference retry.
AI timber/stone swatches correct stretched base interiors through the existing
UVs. Rejected discontinuous corner sampling and a relic mask that crossed the
rear crest remain recorded. The selected relic cavity mask uses measured offset
bounds rather than assuming symmetry.

Original mesh/accessor/UV/normal bytes, sockets, pivots and seven-second OpenClose
clips remain exact under the canonical +X parent. Royal lid panels retain their
original UV1 surface frame: the reduced standalone donor failed the CPU bake's
geometry guard, so the guard stayed intact and the matching analytic UV1 frame
was reused directly. Other assembly surfaces were CPU-baked. Canonical Blender
retains material UV1 sampling, including metallic/roughness; the FBX export copy
transports only affected polygon-loop coordinates into UV0.

All six actual Framewright models and both clip playbacks were inspected. Four
GLB views plus interior/unlit/open-pose evidence and eighteen paired actual FBX
views passed surface review. Maximum companion surface-vertex delta is
0.0000001686 m; maximum sampled hinge-matrix delta is 0.0000001478. Worst paired
mean RGB byte difference is .002836. The package contains 431 hashed files /
490,366,464 bytes, manifest SHA256
`4745b918b1027a9bad7cfd05db2f02f1b2d39184dc8f8c006d959a281cb96ded`.
Relic assembly `b8f1a2e5-99df-4ad2-aa5a-808bfad4a56f` is available in
Framewright. Its inherited lid-to-hinge gap remains a geometry follow-up;
successful playback is not mechanical acceptance. Source counts of 10k to 200k
triangles remain surface-review densities, not accepted runtime budgets. Prior
floating-cache variants remain unchanged. Human approval remains zero.

The ceramic urn pass is packaged in `assets/TW-02/review-group-12-urn-v1/`:
intact v2, fractured assembly v1 and broken arrangement v1. Ivory slip,
terracotta wear and teal Artiss feather-in-rings pigment replace the old surface;
the original unglazed interiors and fracture clay remain. One built-in ImageGen
reference conditioned existing-mesh mapping. Its runner wrote validated outputs
then failed teardown with exit -1073741819; no inference retry. V1's duplicated
rear emblem and stray inner-lip pigment are rejected. V2 uses an AI ceramic
swatch only on the rear belly and extends the original clay over the inward lip.

CPU baking transferred that exterior to the original eight-piece rest-shell
atlas, shared only after verifying identical fragment vertices, normals, UVs
and indices in the assembled/broken sources. Final geometry, UVs, pivots and
fragment arrangements remain exact beneath the canonical +X parent. Three
GLBs, packed Blender files, FBX and portable maps passed placement and source
integrity checks. Four-view sets, interior/unlit views, nine paired actual FBX
views and all three Framewright assets were visually inspected. Maximum
companion vertex delta is 0.0000002404 m; worst paired mean RGB byte difference
is .000323. The package contains 176 hashed files / 192,409,089 bytes, manifest
SHA256 `c5976b37a8b3e0b18a96623548869f5b206218f8057593f6e320a4fbeb9ff984`.
Source densities 22,500 / 114,544 / 114,544 triangles remain for surface review;
runtime optimization and human review are open. The main user tab was left
alone; verification used a temporary background tab after a user navigation
changed one capture to the lectern. That rejected capture is clearly labelled.

The traversal surface pass is packaged in
`assets/TW-02/review-group-15-traversal-v1/`: stone ledges at 150/250/400 cm
top elevation, stone handhold and dark iron swing ring. All ledges remain 150 cm
wide. Three built-in ImageGen references conditioned the existing geometry;
three mapping jobs produced validated outputs then failed teardown, without
retries. Direct ledge atlas sharing was rejected because the independently
reduced meshes and UVs differ. CPU bakes from the inspected 150 cm finish into
each target atlas passed placement checks (centre offset zero, size ratio 1.0).
Only temporary bake copies were translated; final mounting elevations remain.

Five GLB/packed Blender/FBX packages retain original vertices, UVs, normals and
mount pivots under the +X orientation parent. Twenty fixed beauty views, ten
close/unlit views, ten paired actual FBX views and five Framewright models were
inspected. Initial cropped ledge closeups are retained as rejected; selected
views show the full ends. Maximum companion vertex delta is 0.0000001333 m;
worst FBX mean RGB byte difference .001620. The sealed package contains 248
hashed files / 238,023,575 bytes, manifest SHA256
`006c1583d747eb78c7adfd03a83e83fa64b99c127c6e6679fb430927feaad0cd`.
Original counts remain 4,198 triangles per ledge and 5,000 per handhold/ring.
The swing ring is an inherited static one-mesh mount/ring: moving-part separation
and swing mechanics remain open. No timber or brass was introduced. Prior
floating-cache reuse variants remain unchanged; human approval remains zero.

The carpet, climbing vines and parkour beam are packaged in
`assets/TW-02/review-group-15-misc-v1/`. The 3 x 10 m oxblood runner carries
Artiss's feather and rings in ochre thread, with a quiet woven reverse. Living
vines remain matte olive/sage vegetation. The ordinary 3 m traversal beam is
dark forged iron; scarce timber stays reserved for prestige pieces and the
separate floating chests. All three retain exact original geometry and UVs.

Three built-in ImageGen references conditioned existing-mesh mapping. Each
runner saved validated output then failed teardown (-1073741819); zero retries.
Carpet v1 lost the feather and distorted its border. CPU projection of the
generated reference into original top UVs restored the design; v3 also replaced
the distorted reverse border with a muted crop of its quiet woven field.
Rejected/superseded views and both transfer receipts are retained.

Four views per model, seven close/unlit views including the carpet underside,
seven paired actual FBX views, original pivots/dimensions and all three actual
Framewright candidates were inspected. Portable packed Blender and FBX resolve
local maps; maximum companion vertex delta 0.0000009611 m and worst FBX mean
RGB byte difference .000414. Package: 191 hashed files / 117,141,643 bytes,
manifest SHA256
`ef2eb8708c180285d44b864c5ea6caabed7aada28d86421abccda1f795cabd66`.
Source densities remain 20,000 carpet / 30,000 vines / 6,500 beam triangles;
these are material-review candidates, with runtime optimization and human
review still open. The temporary verification tab was closed; user tab preserved.


HC-05's `assets/HC-05/review-delivery-v2/` now contains blocked and partly dug
collapsed-arch assemblies, separate canonical feather keystone, 22 individual
fragments with placement matrices, editable Blender, FBX/UCX, GLB and dust.
The original arch is 4 m wide/high; the fallen stones spread to approximately
5.33 x 5.29 x 1.94 m in the blocked state. The partly dug state removes five
front/upper stones and keeps the other 17 at their exact poses. Both retain
blocking rear rubble. Three GLB/FBX pairs, all fragment closures/UVs/pivots,
convex hull containment, companion map paths and 61 straight standing-capsule
sweeps per state passed CPU checks. Native physics/navigation remains untested.
Both states, keystone and transparent dust were inspected in Framewright.
The dust uses built-in ImageGen; prompt: `assets/HC-05/dust-source-v1/prompt.json`.
Rejected temporary-wall settles, first collision hulls and the exact-hash
companion-path repair remain recorded. The package has 50 hashed files;
`evidence/phase-eight-review-state.json` confirms 107 records, 90 current:
29 images, 51 models and ten audio. Human approval remains pending.

HC-03: `assets/HC-03/review-delivery-v1/` contains 20, 28 and 35 cm forged-iron
cleats (5,000 triangles each), packed Blender, paired GLB/FBX files, UV maps
and a separate transparent chipped-limestone collar decal. The failed local
paint attempt remains untouched. A distinct built-in ImageGen swatch/decal
route followed by CPU UV baking supplied the surface. All three meshes pass
closed-surface, back-at-x=0, width and GLB/FBX checks; four views were inspected.
The standard cleat was orbited in Framewright and the decal inspected there.
Exact prompts are in `assets/HC-03/material-source-v1/prompts.json`.

HC-02's complete five-state family is `assets/HC-02/review-delivery-v1/`:
3 m hanging, 1.3 m burnt/frayed, retained tight floor coil, ring-threaded and
cleat-tied hemp. All share nominal 16 mm gauge. Attached ropes have separate
exports plus hardware assemblies, for seven GLB/FBX pairs, packed Blender and
portable maps. The package has 51 hashed files. The coil retains its 5.22 turns,
30.6 x 33.3 cm footprint and 15,270 triangles. Hanging/burnt states have top
pivots and 6 cm frays; attachments use their hardware's mounting origins.

Selected `cleat-fit-v13` uses CPU contact relaxation of the source deformation
path, then adaptive source-face refinement: 15,392 rope triangles and zero
rope/hardware or nonadjacent self intersections. It makes a compact crossing
hitch around the acquired 35 cm cleat horn. `ring-fit-v3` follows the offset
upper envelope of the actual lower-ring cross-section, retaining a 3 m
centreline and 14,994 triangles. Earlier loose/colliding hitch trials and the
buckled gravity drape are retained as rejected evidence. Both attachments are
static review models, not dynamic rope or load-bearing certification.

All seven actual GLB/FBX pairs pass closed-surface, UV, bounds, pivot and contact
checks. Four-view sheets, fray/hitch/contact close-ups, all seven live models
and three inspection images were examined in Framewright. Lazy packed glTF
maps initially failed companion portability; explicit decoding/local PNGs
fixed them, preserving prior companions. Burn vertex tint is also CPU-baked
into the Blender/FBX albedo; an actual FBX four-view render was checked.
The earlier thick hanging/burnt models remain as revisions; the tight coil's
current asset is reused. `evidence/phase-ten-review-state.json` confirms 124
total records, 104 current (32 images, 62 models, ten audio), eleven prepared
sets and sixteen unfinished. Three held collections remain empty.

CH-03's original 14,993-triangle painted base is preserved as revision 1.
Its 17,269-triangle normalized rig/held-pose derivative is revision 3; see the
base-rig progress entry above. Armour looks, weapons and Bulwark remain open.
Its paint and HC-02's distinct paint attempt produced validated artifacts but
exited abnormally during teardown; failures are retained without retries.

HC-01's `assets/HC-01/review-delivery-v1/` contains light/aged assemblies,
separate ring/collar and six-second fractional-motion clips: eight GLB/FBX
pairs, packed editable Blender and maps, with 44 hashed package files.
The circular ring band is 1.2 m excluding axle bosses; the collar is 1.6 m
wide with a top-mount pivot. The ring has its centre pivot and retained rope
groove; the assembly has 10,838 triangles. Selected `swivel-fair-v7` preserves
source topology with bounded fairing. Bronze is metallic, collar stone remains
nonmetallic, and a built-in ImageGen score decal is baked onto the existing
collar. Both distinct Hunyuan paint passes produced validated maps but crashed
during teardown; failures remain recorded, with neither retried.

All eight actual GLB/FBX pairs pass closure, UV, bounds, pivot and motion checks;
all companion map paths resolve locally. Six four-view sheets and all eight
models were inspected in Framewright; both six-second clips played and paused.
The authored motion is +/-2 degrees about the ring's bearing axis; 33 source
poses pass band clearance. A wider-range shoulder contact failure remains,
and intentional axle-seat contacts are separate from the band check. This is
fractional give, not a free-spin or physical-bearing simulation. FBX retains
geometry/animation, while complete native PBR material setup remains separate.
At that gate, `evidence/phase-nine-review-state.json` recorded 115 total records,
97 current (29 images, 58 models, ten audio); ten prepared sets and 17 unfinished.
Human approval remains pending.

Other work remains incomplete. GV-01 needs part separation, pivots and paint.
AR-03 needs separate leaves/frame and paint. GV-04's complete review set is now
`assets/GV-04/review-delivery-v2/`: 4 m and 2 m emitters, each in floor and
outward-facing wall-socket configurations, with separate faint driftglass cores.
All four 18,788-triangle GLB/FBX pairs were re-imported: closed parts, preserved
UVs, correct long-axis dimensions/socket origins and bounds agreement within
0.000000582 m. Four views for every variant, glass detail views and actual
Framewright floor/wall inspections passed operator review. The earlier master
is retained as a revision; the paint teardown failure remains recorded without
retry. FX-01 field interaction remains separate unfinished work.
GV-03 station, HC-07 scaffold and HC-08 case have normalized/reduced models and
four-view surface-cleanup comparisons. AR-02's cabinet has since advanced to the
partial review package described above. Generic fairing and dense-normal transfer
did not sufficiently clean the case; those experiments remain local and are not
selected for paint. Continue source-preserving planar/feature cleanup and
moving-part separation for the remaining mechanisms. HC-03's original paint execution failed with exit
-1073741819 before any validation report; it remains a recorded failure, while
the distinct generated-swatch/CPU-bake route now supplies its review set.
`commission.json`, per-attempt logs and receipts are authoritative for current
counts and running work. Do not mistake a reference or an intact mesh for a
completed kit, pre-fractured asset or articulated mechanism.

Workspace: `work/artiss-tomb-2026-10-16/`. `Open-Artiss-Review.ps1` starts the
existing saved Framewright runtime without generation workers. The source HTML,
database backup, project request, API readbacks and
`evidence/review-project-receipt.json` are retained. Browser inspection confirmed
the project and saved World settings; existing project data is unchanged apart
from active-project selection. RAC verification passes (757 tests, 15 skips,
198 subtests), and all-profile workflow discovery passes without inference.
Reference images, modeling candidates and AR-01 painted review exports are
currently staged. No human approval, Unreal
import, publication or push is recorded.

## Ennix character: reproducible review, not production-ready

Selected build: `work/ennix-character-v1/rebuild-v9/`, recipe
`ennix-open-review-20261010` (hero tier), built with `--manny-dir work/ennix-character-v1/rig-ue5`.
[Rebuild and review guide](ENNIX_REBUILD.md) gives the exact command, the frozen
26-file input bundle (85.47 MiB, outside Git), licenses, paths and limitations.
Editable file `rigged/Ennix_Rigged.blend`; game export `export/Ennix_UE5.fbx` on a
Manny-conformant skeleton (`scripts/rig_ue5_character.py`) with
`export/Ennix_Groom_UE5.abc`; held review `pose/Ennix_Held_Inspection.blend`.

Head, groom strands, body and both head paints reproduce byte for byte across
independent builds (rebuild-v5..v8); the face-paint stage
(`scripts/refine_face_paint.py`) is deterministic and measured against
the guidance: blush capped, stubble filled, scalp shaded under the groom's
roots, ear and neck tone evened. Review sheet:
`rebuild-v8/face-paint-review/face-paint-sheet.png`, before/after beside the
guidance at front, three-quarter and side. Containers (FBX/blend) and rendered
pixels are not claimed byte-identical; canonical audits compare their content.
The strict rig contract passes with no waiver. Characters are budgeted by tier
(docs/COMPILER.md, "Character tiers"), and Ennix is gated as a hero: 70,748
triangles against 80,000, on both `rigged/Ennix_Body_Face.fbx` and the UE5
export. The garment is 48k and the hands 6k (v8: 91k and 29k). The painted
before/after review shows no visible loss on the coat:
`rebuild-v9/outfit-review/` (ENNIX_REBUILD.md, "Hero-tier budget").

The playable game character lives in the Aether Wars UE project (rigid groom,
exact Manny retarget); the older editor review is
`/Game/EnnixReview/20261007/V5/BP_Ennix_Review`. Existing Hunyuan acquisition is
allowed by Mark; all new processing uses open tools, with no new inference or
generated images. Still open: face detail is capped by the guidance pictures'
resolution, human likeness/texture approval,
expression polish and UE facial playback, and cooked-runtime acceptance.

## Aether Wars realistic commission (creation complete; awaiting Mark review)

All 150 environment review items are created and staged in Framewright: 121
models/parts/variants, 13 decals, nine native Niagara systems with video previews,
and seven original DSP audio loops. Covers all 18 required categories; optional
boss/enemy characters are outside this environment batch. Every human approval
remains pending. No assets were imported into the game project.

Workspace: `work/aether-wars-2026-10-03/`. Framewright is running at
`http://127.0.0.1:5179/`, project **The Aether Wars — Realistic Asset Review**
(`bff69ad8-3084-4321-aebc-95a73e0971e1`; the Tomb project is now active).
Source references appear alongside final
items and are excluded from the 150 count. Old V3 effect videos are archived.

Final bundle: `work/aether-wars-2026-10-03/delivery/AetherWars-Review-v1/`.
Contains self-contained review GLBs, 121 packed editable Blender files, masks,
metadata, native UE dependency closure, final media, references/prompts and proof.
On 2026-10-04, all 121 current model audits passed; all 18 category counts passed;
728 packaged files (6,704,354,969 bytes) passed read-back hash verification.
`evidence/delivery-completion.json` binds this receipt to the exact current
Framewright selection and bundle manifest. `DELIVERY-VERIFIED.json` accompanies
it. GPU inference and the owned cleanup helper are stopped; no generation queue
remains. Framewright was restarted and the selection rechecked after shutdown.

Runtime derivatives (2026-10-04, `rebake-maps`, branch `feat/rebake-maps`): of
105 single-mesh models, 90 were reduced, re-baked from their dense originals
and passed the fixed-view appearance gate (8.68M -> 1.51M triangles); 15 keep
their delivered source (6 crystal heroes already near budget, 6 crystal walls
and the single chain link refused by the gate, pillar capital and relic chest
base refused by reduce-mesh's surface gates). The 90 are revisions in
Framewright, current by the API's default, with the originals kept beneath
them; Mark's approval is pending on each. Assemblies (16) were not reduced.
Outputs: `work/aether-wars-2026-10-03/rebake-derivatives/` (`summary.md`).

Final repairs: coin-pile `kit-v2-coins` uses 120 rigid copies of one acquired
heraldic coin. Chain-winch `kit-v4-worn` was rebuilt LAST, after the other items:
new acquired empty-drum mechanism, three separate mechanical parts, 61 rigid
acquired chain links. Its actual Framewright model was checked after restart.
Condenser `kit-v4-browser` makes enclosed quartz visible in the browser while
its native Blend retains physical transmission. Seamed plinth, throne/canopy,
27 quartz variants and the remaining kits retain their final selections in
`evidence/delivery-ledger.json`; use those paths rather than older revisions.

Native effects are `/Game/AetherReview/PackV4`; decals and pulse functions are
`/Game/AetherReview/SurfaceV1` in the isolated AetherEffects project. Nine effects,
13 decal projections, and both time-varying core functions were visually checked.
Core capture wrote all frames/receipts but UE crashed on shutdown; this is
recorded honestly in `effects/native-final-review.json`. Framewright chest/door
animation, condenser glass, banner alpha, coin/winch models and media playback
were checked. Audio decode/format/levels/loop boundaries pass; listening remains
Mark's review. Gameplay collision, Chaos, doors/loot/climbing wiring, final
quartz shader integration, game-project import, play tests and cooking await
individual approvals and the later port. No production-ready flag is set.

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

## 2026-11-12 - Clanker bolt representative locally approved; engine review pending

`work/ch-pickup-bolt-v002/` is the single replacement RAC representative after
`ch-weapon-sword` exhausted its authorized local/cloud attempts. Bolt concept
hash `aae626daf96783bf6d61c65e3864bc1d62235a0e6472bfc9b37857668c36c352`
conditioned Hunyuan seed43; measured auto reduction produced1800tri at12cm.
Modeling, retopology and texture reviews passed under explicit Codex delegation.
Actual exported FBX was inspected in four fixed views plus1.5m/4.5m CPU views;
source hashes, UV/material links, packed save/reopen and floor pivot passed.
Finish is more polished/orange-gold than concept; macro thread facets remain.
Approved for the small pickup role, not a large hero close-up.

Published manifest: `out/ch-pickup-bolt-v002-production/ch-pickup-bolt-v002-production.ue5import.json`.
FBX SHA256: `10ed4510478edc692174879e85037e26d744c0cc85dcf3cb3973f3c591d93c1b`.
4096 BaseColor and ORM, no tangent Normal. Published bytes and all ORM channels
match reviewed authorities. Ledger integrity passes; engine import/runtime/cook
are pending, so production_ready is false. Floor origin0; spin-center offset+6cmZ.
The inherited five-spoke collision_note is inapplicable; deliberate pickup overlap
and collision need engine readback. No engine acceptance is claimed.

Painter exited0xC0000005 after emitting complete maps/OBJ/GLB. Original failure
remains retained. Explicit CPU-only continuation independently checked complete
PNG/GLB and every ordered position/UV corner before packaging; no inference retry.

Detailed evidence and handoff are in the authorized sibling workspace
`C:/Users/Ayric/Documents/Unreal Projects/ClankerHeroes-art/`, especially
`BOLT_IMPORT_HANDOFF.md`, `ART_LOG.md`, `validation/bolt-v002-publication-verification.json`
and `validation/bolt-v002-fbx-review-v001/`. Opus owns game import/code. The tested
approval/hash and production-name intake guard is staged there as review-only v002;
it remains unapplied. Temporary GPU_FREE handoff is active. No batch until actual
representative engine review.53 RAC and27 Rodin rows remain queued.


<!-- frastown-west-berth-b01-20261123 -->
### Frastown West Berth batch 01 · review candidate (2026-11-23)

17 editable modular pieces plus an Unreal 5.8.4 verified import. The 100× import-scale defect is corrected in the kit exporter. Framewright review remains Pending and headset checks are open. See [the measured record](evidence/frastown-west-berth-b01-20261123.json).

<!-- frastown-surface-pass-b02-20261123 -->
### Frastown West Berth surface pass B02 · review candidate (2026-11-23)

The same 17 pieces resurfaced with the new `bake-surface-maps` and `hard-surface-finish` stages ([guide](HARD_SURFACE_FINISH.md)): UVs in metres with nothing stretched, maps baked off the mesh, layered paint, rust and wear, modelled rivets. Each part and the test assembly are the newest Framewright revision, Pending. FBX files are exported and checked in Blender; the Unreal import script has not been run and nothing has been seen in a headset. The geometry is still batch 01's scripted blockout, which the owner does not accept as the route for final assets. See [the measured record](evidence/frastown-surface-pass-b02-20261123.json).


<!-- frastown-west-berth-production-review-20261123 -->
### Frastown CT-03 · source and modeling review open

Four image-conditioned facade derivatives were reduced, cleaned to 4 m by 3 m modules and reimported. The shop doorway and display opening pass 21 ray tests. The corner cavity passes 12 vertical rays. The 1.65 m eye-height test prompted exact aperture cuts and confirmed fused door hardware as a remaining issue. Keep all four at modeling review. Three separate dry PBR surface sets (4K) validated in Blender and UE 5.8. No facade bake, gate promotion or production review upload. See [CT-03 measured evidence](evidence/frastown-ct03-metric-and-material-review-20261123.json).

Framewright Quick Review fell from 160 to 18 current assets. The approved bowl and 17 B02 steel revisions remain. Staging and duplicate exports were archived reversibly. The scene still resolves all 124 asset instances. CT-03 development is local. Its early shopfront and worker-house meshes require modeling review. See [cleanup and acquisition evidence](evidence/frastown-west-berth-production-review-20261123.json).


<!-- frastown-ct03-glazing-and-hardware-20261123 -->
### Frastown CT-03 glazing and hardware · modeling review

CT-03.1 gains separate shop and transom glass. CT-03.3 now has true three-pane transoms and discrete door hardware. 128 perimeter and 32 pane-fit probes pass, and GLB replay keeps all eight 8 mm panes and the module datums intact. Close-up review still shows facets in the acquired frame and leaf relief. PBR assignment, human approval and VR runtime remain open. See [geometry and review evidence](evidence/frastown-ct03-glazing-and-hardware-20261123.json).


<!-- frastown-86-model-production-20261123 -->
### Frastown · 86-piece Models production cohort

West Berth production now tracks all 86 numbered parts, including the three optional parts, with one current Models entry per part. Audited 18 current cards and found 17 bound normal maps. No member currently passes all release gates. Recorded verified machine acquisition on the existing high-res candidates. AC-04.2 linen cover, CT-09.3 tray and DK-04.4 seat reached metric modeling review from new pinned local GPU runs. The exact approved bowl asset used for fit has an 81 mm height. Human modeling review remains pending before paint. No new Models cards were added. See [production and fit evidence](evidence/frastown-86-model-production-20261123.json).


<!-- frastown-production-direction-20261123 -->
### Frastown · production route from 24 November

Pieces are made through Framewright: a reference picture in the project library that the owner has approved, model generation queued from it, review in Framewright. The acquisitions recorded above came from pictures that were never put in Framewright. Each picture goes in front of the owner before its mesh is used. Operating instructions are in `AGENTS.md` in the Frastown workspace folder. See HANDOFF, 2026-11-23, "why the pipeline was skipped".


<!-- paint-sections-20261124 -->
### paint-sections · proven on one model, owner review open

New stage for large models (over 1.2 m). Proven on the Frastown DK-04.2 mast: six sections, the head-pass seam gone, about 1.3 mm a painted pixel instead of 3.2. Hero props generated through Framewright carry the head-pass seam until they are painted in sections. Framewright support is in its own pull request. See HANDOFF 2026-11-24.
