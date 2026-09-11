# Sunset workshop

*Type: chronological log*

Requested on 2026-09-04: a playable, modular UE5 scene inspired by the supplied
sunlit illustrated workshop. Individual tools, circuit boards, cups, instruments,
furniture, and plants should remain independently placed objects.

## Artistic contract

Latest lighting derivative: [night v026](SUNSET_NIGHT.md), with a starry sky
and corrected very faint low dust, is separately packaged and verified.
`scripts/play_workshop_demo.ps1` now defaults to Night; Day preserves v018.

- Source: `work/sunset-workshop/references/workshop-source.png`.
- SHA-256: `3cc21ace04d1851d558b440e183bebbde36a498e1cf65de1bfae47ffc913e072`.
- Warm ochre industrial interior, inked edges, chipped paint, teal instrument
  displays, trailing greenery, soft desert colors through a large window.
- Clear walking space around the central worktable and between benches.
- A separate UE map; the existing asset gallery remains available.

## Acquisition and scene assembly

The source directly conditions generated object references and surface artwork.
Object references then condition the existing Hunyuan geometry route. Blender
is used downstream for geometry cleanup, UV transport, and export. Reference
artwork is never substituted by manually sculpted approximate hero objects.

Architectural surfaces use reference-conditioned AI surface artwork on modular
scene construction pieces. Distinctive furniture and handheld tools use separate
AI-acquired meshes. Scene placement, collision, lighting, and the player controller
are authored in UE5. The earlier panorama is retained in historical scenes;
the latest user feedback requires real-depth exterior geometry before completion.

Working scene candidates remain review candidates; this scene does not grant
human approval to new asset ledgers or label a render as cooked-runtime proof.

## Completed local Manny demo: v018, 2026-09-05

Run `./scripts/play_workshop_demo.ps1 -Lighting Day`. The verified package is
`output/sunset-workshop-demo-v018-r2/Windows`:48files,1,131,307,068bytes
(about1.13GB decimal). The saved scene is
`/Game/SunsetWorkshop/L_WorkshopDemo_v018`, map SHA-256
`5698a91d255e54b4f2a6937fca7030c3528306207c7e6d0e9e77b6f7701a8c44`.
WASD moves, mouse looks, Space jumps, Alt+F4 exits. The packaged executable
needs no Codex, ComfyUI, model server or Unreal Editor.

The scene retains169 separately placed static-mesh components, including
architecture, sofa, plants, tables, cups, instruments, circuit boards, tools,
crates and stools. The rug lies flat. A storage crate clears the restored sofa;
the window pot's support was verified at nine native tabletop-triangle samples.
Final lighting softens the sun and reduces overly strong local fills. Rocks
receive matte textured sandstone and distance haze. Their transforms and the
liked moon are preserved, not lowered. Five depth-separated rock instances
replace the old flat panorama; the vista is scenic, not a traversable open world.

Verification:183compiler tests and routing pass; all13 actual PIE gameplay
checks and12 cooked programmatic gameplay checks pass. The cooked audit checks
Manny possession, spawn, walking, east collision, jump/landing and sword carry,
then captures eight actual1600x900 frames. All were visually inspected by Codex
under the user's explicit demo delegation. Physical keyboard input is not
claimed tested. Motion frames retain real engine motion blur.

Review panel: `work/sunset-workshop/evidence/final-demo-v018.html`.
Hash-bound package/evidence: `final-demo-v018.json` in the same directory.
Cooked frames/checks: `cooked-v018-r2-audit/`; independent object inventory:
`final-v018-inventory.json`. This is a completed local scene demo, not an
automatic human approval or production-ready stamp on all separate asset ledgers.
Custom Ayric face/body/rig work stays parked and preserved.

Sofa uses unchanged approved AI geometry/UVs, reference-conditioned leather
mapping and retained AI ink/pillow regions. Accepted liberties: subdued teal
pillow and leather-covered rear trim. Built-in ImageGen leather source and exact
prompt: `work/sunset-sofa/texture/region-mapping-v005/{leather.png,prompt.txt}`.
Plant uses its accepted multiview AI geometry and a separately verified neutral
normal material correction. No Auto-Rig Pro pass was needed for existing Manny.
The art style comes from illustrated materials, not a full-screen outline shader.

The first v018 archive is retained but rejected: its Blueprint-only executable
did not link the new audit module. V018-r2 explicitly builds RacValidate's Game
and Editor targets and passes the actual packaged run. Its clean build/cook took
59seconds, with zero cook errors/warnings. Previous previews and rejected asset
candidates remain intact. Historical sections below are superseded by this one.

## Historical: actual Manny and real-depth exterior, 2026-09-05

Current working derivative: `/Game/SunsetWorkshop/L_WorkshopDemo_v008`, with
real rock meshes at five depths, horizontal mapped ground, UE sky/height haze
and a distant sphere carrying reference-conditioned planetary surface artwork.
The flat panorama is absent. v006 actual paired camera images prove parallax
but were too dark; v007 fixes exterior lighting, and v008 refines the composition.
The v008 paired and wide editor captures have been visually inspected: rock
overlaps change across a 2.2 m camera baseline, with a softer horizon and pale
planet. See `work/sunset-workshop/evidence/exterior-depth-review-v001.html`.
This is accepted editor window-depth evidence, not yet cooked gameplay proof.

Manny is now explicitly `SKM_Manny_Simple`, with the independent sword attached
to spine_03. All13 v005 PIE movement/collision/jump/attachment checks passed;
evidence is `work/sunset-workshop/evidence/manny-demo-v005-play/`. The original
ThirdPerson template actually used Quinn; earlier "Manny" descriptions of that
unchanged template were incorrect. The current derivative corrects the mesh.

Rock geometry is Hunyuan image-conditioned, then cleaned/reduced in Blender.
Large scenery uses repeating reference-conditioned material mapping, not a
claimed Hunyuan-Paint atlas. Actual UE seam splits exceeded the vertex ceiling
on the first import; a separate native LOD derivative passes at14499vertices
and14400triangles. The failed original survives. Texture thresholds were not
relaxed; native appearance and instance-scale material density remain distinct
from the unscaled asset checks. The planet uses an existing Engine sphere with
AI-derived mapping, not an AI-generated planet mesh. Exact prompts/art remain
under `work/sunset-workshop/art/exterior-v001/`.

The launcher now opens v008 with the new exterior and corrected Manny/sword.
The separate Windows archive is 1,048,623,348 bytes across 48 files; package/cook
succeeded with zero errors/warnings in 55 seconds. Live packaged logs confirm
the v008 map loaded with BP_WorkshopGameMode_v005. All 13 v008 PIE checks also
pass. Do not label the full demo complete: physical cooked input/parallax review,
sofa and potted-plant holds remain open. Package/map-load evidence is
`work/sunset-workshop/evidence/demo-v008-package-load.json`.
Custom Ayric work stays parked. Latest automated verification:171tests pass.

## Retained cooked v002 preview (historical)

The user stopped custom Ayric character work and explicitly requested Manny
instead. Do not resume the head, body textures or custom rig. All candidates
are preserved. The new scene is `/Game/SunsetWorkshop/L_WorkshopDemo_v002`.

This revision adds nine layered masked ivy cards, two mapped engineering
displays, a mapped kilim rug, independent shelf/worktop clutter, modular trim,
continuous architectural wall mapping and revised lighting. The desert panorama
is correctly reframed instead of the earlier extreme zoom. Distinctive props
remain their actual AI-acquired meshes. No sofa or potted-plant hold was waived.

Windows BuildCookRun succeeded. Local package:
`output/sunset-workshop-demo-v002/Windows` (1,040,835,859 bytes at archive time).
Run `scripts/play_workshop_demo.ps1` to open that old template preview (Quinn). WASD moves, mouse
looks, Space jumps, Alt+F4 exits. An explicit map argument is important: the
validation project's default map remains the older gallery.

The packaged game opened, but a Windows firewall prompt paused hands-on input
verification. The agent did not operate security UI; choose Cancel for this
local-only demo. Do not claim movement was verified in this cooked revision
from the older v004 PIE test. Current review:
`work/sunset-workshop/evidence/manny-demo-review-v002.html` and JSON.

Four actual v002 editor views were inspected. v001's new wall material had a
missing ComponentMask input and rendered checkerboards; it remains rejected.
v002 uses a checked connection to the unnamed input and renders the mapped
walls correctly. Original preview and both revisions remain separate.

Remaining: cooked movement/collision/jump evidence, sofa restoration, potted
plant or independently reviewed replacement, sword carry on Manny, and further
lighting/composition polish. The full demo is not yet certified complete.
The historical chronological notes below are superseded by this section where
they describe custom-character requirements or an uncooked-only scene.

## Current execution (historical)

- Existing UE5.8 Third Person project and player controller verified present.
- Local Blender 5.2.1 and Auto-Rig Pro preflight pass.
- Current compiler verification: 91 tests pass.
- At intake, LM Studio's idle `qwen3.8-27b` owned most GPU memory. The user
  authorized proceeding after reporting LM Studio broken. A fresh check found
  no loaded model and 22,218 MiB free; no forced termination was needed.
- The initial seven source-conditioned images are saved in `work/sunset-workshop/art/`:
  workbench, radio, sofa, wrench, mug, wall surface, and desert vista. Exact
  prompts, source/output hashes, and original generated paths are recorded in
  `art/lineage.json`. These images are not finished 3D assets.
- Nine separate operator workspaces now contain successful image-conditioned
  geometry attempts: `work/sunset-{workbench,radio,sofa,wrench,mug,circuit-board,crate,stool,plant}`.
  Ayric approved the eight non-rejected modeling candidates in the next turn
  ("yeah broski, these all look great!!"). The plant is rejected in the review
  evidence for torn leaves and floating fragments; its original files remain intact.
- Architectural study saved in the existing UE project as
  `/Game/SunsetWorkshop/L_WorkshopShell_v004`: 106 individually placed modules,
  collision profiles, actual window/skylight openings, corridor, player start,
  and source-conditioned surface mapping. Built with `-nullrhi` (CPU assembly),
  then captured in a real rendering editor session. Appearance was inspected;
  player movement is **not yet verified**. Furniture, foliage, circuit board,
  lighting polish, and finished scene remain pending.
- Builder: `scripts/ue5/build_workshop_shell.py`, with `RAC_ROOT` set to the
  repo. Each build requires a fresh `RAC_WORKSHOP_LEVEL` under
  `/Game/SunsetWorkshop/`; existing maps are refused, not overwritten.
- Evidence: `work/sunset-workshop/evidence/L_WorkshopShell_v004.json`,
  `shell-build-v004.log`, and `shell-review-v002/`. The failed v001 build is retained: UE5.8 did not
  expose the old directional-light component attribute. v002 uses typed
  component lookup and completed without Python errors.
- Repaired the geometry launcher/doctor mismatch: both now inspect the
  repository's pinned runner rather than stale studio copies. Existing
  studio files were not changed. Tests: 75 pass; doctor passes; CPU-only
  single-view mug preparation passes (optional pymeshlab plugin warnings).
- Live guarded-launch check stopped before inference at 1,982 MiB free versus
  12,288 MiB required. No process was killed/unloaded and no attempt directory
  was created. That resource blocker was cleared on the next user turn.

## Generation checkpoint

All nine props now have actual
single-view Hunyuan3D-2 geometry, normalized FBX derivatives, and four clay
views. Ayric's modeling approval is recorded against the eight non-rejected
authorities. `work/sunset-workshop/evidence/modeling-review-v003.html`
compares their references and fixed views. The adjacent JSON hashes every
image and candidate mesh. It is a review page, not an approval receipt.
The eight original candidates have human modeling approval; the plant has an agent rejection for
damaged right-side foliage. This rejection is retained in the review JSON,
not misrepresented as a human gate decision. All nine workspace audits pass
hash/stage integrity, but correctly report `production_ready: false`.

The wrench, mug, and circuit board additionally have `modeling/surface-views/`: overhead,
underside, and elevated views. The renderer's optional `surface` argument
preserves the original four cameras and adds these views. It addresses the
edge-on blind spot for flat props; the mug's elevated view confirms a hollow
interior and open handle. The wrench normalized to roughly 41 cm long and
4 cm thick, with both open jaws intact.

The single-view checkpoint download completed: 4,928,151,562 bytes for the
FP16 safetensors plus 1,604 bytes for config. All nine AI calls completed
without inference crashes. These high-resolution meshes still require reviewed
reduction and texture before they are runtime assets.

Additional image-conditioned references are saved for the circuit board,
crate, stool, and potted plant (`art/lineage-extra-v001.json`), plus floor and
chalkboard surface artwork (`art/lineage-surfaces-v001.json`). Built-in image
generation was used; the manifests retain the full prompts and hashes.

The v004 room study uses dedicated floor plates, a mapped chalkboard, corrected
panorama-plane orientation, size-aware wall UV density, movable lights, and an
exposure-compensated unlit vista. Four actual UE viewport screenshots are in
`evidence/shell-review-v002/`. The earlier v003 screenshots are retained in
`shell-review-v001/`: they revealed overexposure, stretched mapping, and preview
shadow labels. v004 fixes those observed defects. This is still an empty-room
study, not a finished workshop or cooked-runtime verification. Repetitive wall
panels and square framing still need art direction as the furnishings arrive.
The user explicitly prefers a lightweight exterior: keep the desert a distant
backdrop and spend detail on the interior. It is not walkable exterior terrain.

## Next gate

Ayric approved the eight reductions in `retopology-review-v001.html` with
"approved. lets go". All eight `production_retopology` stages now record
Ayric's explicit review. The next gate is texture review; this approval does
not authorize unseen textures. Repair or
replace the plant's AI acquisition, retaining attempt001; do not manually
reconstruct the damaged leaves. No generation, paint, Blender, or dedicated
review-editor process was left running at this checkpoint.

## Reduced-mesh checkpoint

All eight approved props have passed semantic cleanup and have separate
voxel/QEM reduction candidates under `retopology/operator-attempt001/`.
Each is 18,000 triangles (8,988–9,002 vertices), with zero boundary or
non-manifold edges in the reduction report. The original authorities remain
unchanged. Hash/stage audits passed for all eight after modeling promotion.

`work/sunset-workshop/evidence/retopology-review-v001.html` compares approved
and reduced rows, including supplemental overhead/interior views for the
wrench, mug, and circuit board. Its JSON binds both sets of images, the
reduced meshes, and their reports. The stool retains four legs and its foot
ring; the mug remains hollow; the board retains chips and mounting holes.
At the end of that reduction checkpoint these were agent observations only.
Ayric subsequently approved the linked reductions; see the next-gate note above.

The first operator resume exposed a format-handoff defect after successful
workbench cleanup: `describe_mesh.py` refused `.blend`. Native read support
was added without changing the cleanup authority, then execution resumed.
The under-budget passthrough also now consumes the producer's actual `verts`
field. Regression tests cover native import dispatch and topology review
hashing; the full suite passes 84 tests. The workflow doctor passes when
`RAC_LEGACY_ROOT=C:/Comfy/blender-reference-studio` is supplied; the optional
historical ComfyUI nodes remain absent and were not installed.

## Texture checkpoint

Ayric's topology approval is recorded for all eight props. All eight first
Hunyuan3D-2.1 paint attempts completed output/geometry/UV validation; each
process then exited abnormally with `-1073741819`. This is retained as a
teardown failure, not described as a clean inference exit. No paint was retried.
The launcher now records execution identity, timestamps, hashes and exit code
separately from mesh/UV validation for subsequent calls.

Review: `work/sunset-workshop/evidence/texture-review-v001.html` and its
hash-bound JSON. These are actual FBX renders, with lit and unlit rows and
extra overhead/interior views for wrench, mug and circuit board. Six candidates
passed the mechanical texture gate and await human texture review:

| Asset | Package | Current decision |
| --- | --- | --- |
| Radio, wrench, mug, circuit board, stool | `prod-v2` | Ready for human texture review |
| Crate | `prod-v3` | Ready for human texture review; original 4K bake recovered |
| Workbench | `prod-v2` | Held: smeared cavity paint and 23.3 texels/cm2 |
| Sofa | `prod-v3` | Held: baked-light correlation +0.619 exceeds 0.35 |

These materials are glossier than the illustrated reference. Inspect the
unlit rows as well as the highlights before approving the style. No texture
approval, UE import or cook was granted. The plant remains rejected geometry.

The upstream painter enhances its generated views, bakes at 4096, then exports
2048 maps. `scripts/recover_fullsize_paint_maps.py` recovers retained 4096
diagnostic bakes without inference or upscaling. It checks geometry/UV
validation and downsampled correspondence against all three exported maps,
preserves original albedo, and splits authored R-metallic/G-roughness. Hashes
bind source, reference, transport and outputs in `recovery.json`.

Crate and sofa retain both failed `prod-v2` and recovered `prod-v3` packages;
maps live in `texture/fullsize-recovery-v001/`. Crate density rose from 72.8
to 291.4 texels/cm2 and passed. Sofa density rose to 151.5, but baked lighting
still failed. More pixels do not remove painted-in shadows. The workbench
needs a paint/mapping repair, not merely a larger version of its smeared atlas.

For future crate resumes, retain the original command/recipe parameters and
add `--texture-package-name prod-v3 --paint-map-directory
work/sunset-crate/texture/fullsize-recovery-v001`. Do not grant texture approval
until Ayric reviews this exact package. The workbench uses `--uv-attempt 2`;
its failed attempt001 is retained. Other successful UV attempts are 001.
The UV tool now explicitly accepts triangulated static GLBs via an opt-in
flag, rejecting armatures/non-triangles and retaining geometry drift checks.

All eight post-texture audits report integrity OK and production readiness
false (`evidence/audit-sunset-<name>-post-texture-v001.json`). The full suite
passes 97 tests. Paint and Blender jobs finished; existing MCP services were
left alone. UE is still the architecture-only v004 study. Imported vertex
budgets, collision, player movement and cooked runtime remain unverified;
UV-split interchange vertex counts must not substitute for runtime evidence.

## Interior repairs and first approved imports

Ayric approved everything except the workbench recess and mug interior.
Recorded texture approval for radio, wrench, circuit board, crate and stool
after rehashing their exact `texture-review-v001` payloads. Sofa appearance is
approved in conversation, but the failed baked-light gate remains held; this
is not a waiver and no passing texture ledger entry was created for it.

The cup has a modeled bottom. Unlit inspection confirmed black/streaked paint
inside it. `scripts/repair_workshop_interiors.py` now performs opt-in,
geometry-bounded UV material transfer from quiet samples of each approved
reference: green enamel on bench inner panels and teal enamel inside the mug.
No geometry/UV edits or new inference. Outside the region and its unused-UV
padding, all three input maps are bit-identical. Workbench inputs are its
recovered original 4096 maps; mug inputs are the retained 2048 maps.

Latest candidates for both: `prod-interior-v002`, sourced from
`texture/interior-repair-v002/`. `repair.json` binds the mesh, triangle-position
export, reference, sample coordinates, selected faces, mask and maps. The
interior roughness is calibrated to 170/255 and metallic to zero; the mug's
transition below the lip is spatially feathered. This is an enamel material
repair, not another AI paint run or an upscaler. The exterior logo/rim remain.

Review: `work/sunset-workshop/evidence/interior-repair-review-v002.html` plus
hash manifest. Both mechanical texture gates pass: workbench density 93.4,
lighting correlation -0.210; mug density 1473.6, correlation +0.210. Human
approval of these repaired textures is still pending. `prod-interior-v001`
is retained/rejected: bench donor included ochre trim; mug had a saw-tooth
rim transition. See `interior-repair-rejected-v001.html` and its hashes.

The five approved props now exist separately under `/Game/Compiled/` with
`Sunset<Name>Production` folders. Scoped import report:
`evidence/ue-import-approved-five-v002.json`. All passed material, scale and
three-LOD import checks. A separate read-only native vertex audit found:
radio 13,239; wrench 10,748; board 15,973; crate 12,402; stool 12,840 LOD0
vertices. **The circuit board exceeds 15,000** and has a recorded blocked
runtime-review gate; its appearance approval does not waive the budget.
The normal import verifier does not check this count, so do not infer runtime
readiness from its passing report. Preserve the approved source and create a
reviewed optimization derivative. Other imports still need visual runtime,
collision/walkthrough and cook evidence. No furnished map or playable scene
was claimed. v004 architecture remains unchanged.

The first UE launch failed before opening the project because its project
path was relative; retained v001 log, corrected absolute paths in v002.
One supplemental Blender render similarly refused relative paths before
writing images. These were launcher errors, not inference crashes.
102 tests pass, doctor passes, audits retain production readiness false.

## Completion evidence

The target is a saved level, individual object actors, functioning player spawn,
collision and movement, and screenshots from the running UE scene. Record the
actual result and any remaining limitations here after the walkthrough.

### 2026-09-04: approved interiors and early furnished walkthrough

Ayric's "approved. lets go" on `interior-repair-review-v002.html` approved
both exact `prod-interior-v002` packages. Rehashed review evidence, recorded
texture approvals, published workbench/mug production derivatives, and passed
scoped imports (`evidence/ue-import-interiors-v001.json`). No new inference.

Saved `/Game/SunsetWorkshop/L_WorkshopPreview_v003` in the local validation
project, preserving the architecture-only v004 and previous preview. It has
18 separately selectable prop actors from six approved, imported types:
workbench, mug, radio, wrench, crate and stool. The builder refuses missing
texture/import gates or an imported LOD0 count above 15,000 vertices. Small
tabletop props have no blocking collision; furniture blocks movement. This is
placement of the approved AI-acquired meshes, not replacement geometry.

`scripts/ue5/furnish_workshop_preview.py` creates a fresh level from the saved
shell; `scripts/ue5/probe_workshop_walkthrough.py` runs a dedicated editor PIE
probe. Evidence under `work/sunset-workshop/evidence/walkthrough-v002/`:

- `walkthrough.json`: possessed ThirdPerson character, floor spawn, roughly
  4.9 m forward movement, then stable position against blocking geometry;
  all six checks passed. Input was `Character.add_movement_input`, not physical
  keyboard automation. The check named `blocked_by_wall` does not identify the
  particular blocking actor.
- `overview.png`: actual furnished UE viewport, not an AI concept render.
- `player-window.png`: actual PIE character and window view.

Launch the local saved map without Codex:

```powershell
./scripts/play_workshop_preview.ps1
```

WASD/mouse/Space are the existing ThirdPerson template controls; Alt+F4 closes
the game window. The launcher opens editor `-game` mode, not a cooked build,
and does not change the project defaults. Assets/project are local generated
outputs, not distributed with a fresh clone. Override `RAC_UNREAL_EDITOR` if
needed; the launcher uses the repository tool resolver and Python 3.12.

The v003 visual pass turned radios inward, reduced task-light glare and
exposure, and widened the distant image card so its edge is not visible in
the tested window view. The backdrop remains flat/soft at close range, and
the room is sparse and more repetitive than the target illustration. Further
set dressing, lighting/material polish and camera-angle review are needed.
Sofa remains held for baked lighting, circuit board for its vertex budget,
and plant for rejected geometry. No production-ready or cooked-runtime
approval was granted. Full suite: 102 tests passed.

### Full-demo continuation: character work in progress

The user subsequently requested autonomous visual judgment and a complete,
polished demo with an Ayric-derived playable character and separate back-carried
sword. See [SUNSET_DEMO_COMPLETION.md](SUNSET_DEMO_COMPLETION.md) for the actual
completion contract and the chronological HANDOFF tail for exact artifacts.
The early v003 walkthrough is not the final deliverable.

`sunset-ayric-v1` geometry is rejected for fused fingers. `sunset-ayric-v2`
has passed modeling and reviewed source-conforming topology at 19,588 triangles;
its first texture candidate is rejected for mapping/material defects and failed
density/lighting checks. Recovered original 4K maps also retain the numeric
failures; no waiver, upscale or repeat inference. The first two reduction candidates
are retained for facial detail loss. `sunset-sword-v1` has passed texture and
static publishing, but is not yet imported or attached in gameplay. Reviews
are honestly labeled agent-delegated rather than human approvals. 109 tests
pass; no existing sofa/board/plant hold has been waived.

Latest face repair: `work/sunset-ayric-v2/prod-face-v003` is the preferred
illustrated face derivative, checked in actual FBX front/three-quarter/side
lit and unlit renders. Hair, armor, geometry, UVs and other material channels
are preserved. Browse `work/sunset-workshop/evidence/ayric-face-review-v003.html`.
This is still a held texture candidate (lighting/density checks), not a
rigged/imported character or completed demo. 119 tests now pass. Exact AI donor
prompt and bounded mapping provenance are in the HANDOFF tail.

Latest UV derivative: `prod-repacked-v001` retains that face and body artwork
while recovering atlas space. Density now passes (301.3 texels/cm2, same 4K
maps and character height); lighting still fails. The character remains held
before rigging. `work/sunset-workshop/evidence/ayric-repacked-review-v001.html`
contains the new fixed views. Full suite: 122 tests.

The subsequent official Hunyuan delight experiment is **rejected**: lighting
still fails and the forehead transition became worse. Preferred character
remains `prod-repacked-v001`; the separate rejection panel is
`work/sunset-workshop/evidence/ayric-delight-review-v001.html`. Nothing has
advanced to rigging. Full suite: 126 passing tests.

A separate native UE circuit-board reduction now meets the vertex cap at
14,534 vertices. Actual UE comparison images and hashes are under
`work/sunset-workshop/evidence/board-reduction-review-v001/`. This is a review
fixture, not a new demo release: the partly obscured comparison and versioned
import/runtime receipts still need completion. The original board runtime
hold and saved v003 preview remain unchanged.

Latest face candidate is now `prod-face-v006`: the mid-forehead paint band is
removed while retaining the preferred expression, and bounded skin PBR
calibration softens the highlight. Actual packaged views:
`work/sunset-workshop/evidence/ayric-face-review-v006.html`. Two intermediate
registration attempts were rejected for brow distortion/ghosts. Whole texture
still fails lighting (-0.23890); neck/side defects remain. No rigging or UE
character promotion. Integrity audit passes; 129 tests pass.

Latest held character package: `prod-neck-v001`. A source-conditioned neck
donor and per-pixel depth projection improve both sides of the neck while
preserving the preferred face and outside-mask artwork. Review now includes
both three-quarter and side directions:
`work/sunset-workshop/evidence/ayric-neck-review-v001.html`. Collar-rim/nape
artifacts and the whole-body lighting hold remain; no rig/UE promotion.
Exact donor prompt and saved-image provenance are in
`work/sunset-workshop/character-art/neck-donor-lineage-v001.json`.
135 tests pass. The full playable/cooked demo is still unfinished.

Latest verification checkpoint: 138 tests plus 3 subtests pass. A read-only
lighting diagnostic demonstrates a synthetic palette false positive, but does
not clear Ayric's actual texture hold. No character artwork or gate threshold
changed in this diagnostic pass. Matched native UE board comparisons are in
`work/sunset-workshop/evidence/board-matched-review-v001/`; the reduced mesh
keeps the approved design at 14,534 LOD0 vertices. Formal versioned import and
runtime binding remain pending; this is not a cooked-demo completion claim.

Board update: native v002 now passes import and delegated static UE visual
review, with immutable original/revision evidence. Uniform scale normalization
restores its declared 6 cm height; LOD0 is 14,534 vertices / 15,300 triangles.
`L_WorkshopPreview_v004` adds it as an independent table prop while retaining
v003. Cook is still pending, and Ayric's texture hold is unchanged. Current
test count is 149 plus 3 subtests. See the latest handoff for exact receipts.

The launcher now opens v004. Its new `evidence/walkthrough-v004/` proof passes
all six PIE spawn/movement/floor/wall checks; actual overview and player-window
frames were inspected. This is still Manny, still an uncooked preview, and
still a visibly sparse room—not the polished reference-matching demo.

Latest character candidate: `prod-nape-v001`, reviewed in
`work/sunset-workshop/evidence/ayric-nape-review-v001.html`. Bounded AI-donor
mapping removes the large pale/cyan nape patches on both sides, preserves front
facial features and outside-region artwork, and removes the repaired skin's
metallic glint. This remains a held texture candidate: collar/hair-edge details
and whole-body lighting (-0.24011 versus absolute .12) are unresolved. No rig
or character UE promotion. Exact built-in ImageGen donor prompt and hashes are
in `work/sunset-workshop/character-art/nape-donor-lineage-v001.json`.

Latest held package is now `prod-collar-v001`, with continuous front collar
trim and cleaner blue paint in actual front and bilateral three-quarter views.
Panel: `work/sunset-workshop/evidence/ayric-collar-review-v001.html`.
Face and outside-region artwork are preserved. Side/back collar and other
body paint issues remain; lighting is -0.23785 against absolute .12. No rig or
character UE promotion. Built-in donor and exact prompt are saved under
`character-art/ayric-collar-donor-v001.png` and `collar-donor-lineage-v001.json`.

The separate sword now passes native UE import: 135 cm, 11,123 / 6,429 /
3,647 vertices and 18,000 / 9,000 / 4,500 triangles across three LODs, one
section each, correct material texture settings. Receipt:
`work/sunset-sword-v1/validation/ue5-import.json`. Native visual review, animated
back attachment and cooked proof remain pending. Preview v004 is unchanged.

The sword now also passes delegated static editor review in a separate
`L_SwordReview_v003` fixture: front, three-quarter, side, back and two reduced
LOD captures, all bound to the native import. Browse
`work/sunset-workshop/evidence/sword-review-v003.html`. Underlit v001 and
overbright v002 inspection trials remain retained, not substituted silently.
No animated attachment or cooked proof. Ayric remains held at `prod-collar-v001`.

Albedo challenger comparison:
`work/sunset-workshop/evidence/intrinsic-review-v001.html`. This shows actual
unlit input renders beside low-resolution and guided-high-resolution AI image
estimates. The tool now runs, but direct face replacement is rejected for
softening and patch boundaries. These are not mapped 3D assets. Current
character texture, rig hold and scene state are unchanged.

Plant acquisition update: original single-view attempt001 remains rejected
for torn foliage. New `sunset-plant/candidates/hy3d-mv-seed42-attempt002`
passes delegated modeling review of seven actual clay directions. Original
intake directly supplies the front input; built-in ImageGen left/back views
are approximate inferred depth guidance, not exact orthographic rotations.
Exact prompts/hashes: `sunset-plant/references/multiview-v001/lineage.json`.
Conservative cleanup also passes; no manual reconstruction occurred.

The 18k reduction retains the leaves but introduces visible pot facets and
angular leaf undersides. Modifier-normal, explicit BVH-normal and 19.2k
error-guided edge-refinement derivatives are retained as rejected; no topology
or texture approval. Browse the original, improved dense model and all four
topology trials in `evidence/plant-repair-review-v001.html`. Ayric's texture
hold and preview v004 remain unchanged. No new inference is left running.

## 2026-09-06 custom-character review update

The latest custom-character package is Ayric v051: repaired locomotion, a separate
existing AI-acquired detailed head and source-locked neck colour/normal blending.
`scripts/play_workshop_demo.ps1 -Lighting Ayric` opens it; `AyricLegacy` preserves
v036. Night/Manny remains the default. All 18 packaged runtime checks pass.
The user approved the improved face but the newest neck still awaits visual
approval. This is not a facial-animation rig or production-ledger promotion.
See `CHARACTER_HEAD_AND_NECK.md` for reproducible commands and `HANDOFF.md` for
exact latest paths, counts and retained rejected variants.
