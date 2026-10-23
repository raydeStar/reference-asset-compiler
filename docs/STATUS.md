# Current status

*Type: reference*

Last updated: 2026-10-23. This file holds the current state only and is
rewritten in place. History is in [HANDOFF.md](HANDOFF.md) (append-only,
dated); failures and retained lessons are in [DECISIONS.md](DECISIONS.md);
scoped open work is in [AGENT_TASKS.md](AGENT_TASKS.md). The stage names below
are the ledger stages listed in [PIPELINE.md](PIPELINE.md#ledger-stages).

Every `work/`, `out/` and `output/` path here is on the development workstation
and ignored by Git. Nothing in this repository is production-ready; the
checked-in cohort snapshot (`docs/evidence/v1-cohort-audit-current.json`)
truthfully reports 0 of 7 assets ready.

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
`http://127.0.0.1:5179/`, active project **The Aether Wars — Realistic Asset Review**
(`bff69ad8-3084-4321-aebc-95a73e0971e1`). Source references appear alongside final
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
