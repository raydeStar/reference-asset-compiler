# Sunset demo completion contract

## Night lighting follow-up complete — 2026-09-05

Separate night v026 is now built and verified, including stars and the user's
corrected very faint low dust. Twelve packaged checks pass and nine actual game
frames were inspected. The launcher defaults to Night; pass `-Lighting Day` for
the preserved v018 below. See [night details](SUNSET_NIGHT.md) and
`work/sunset-workshop/evidence/night-review-v026.html`. No custom-character work
was resumed, and the original 169 objects remain unchanged.

## Completed under the Manny scope — 2026-09-05

The local v018 scene demo is complete. The user-requested custom-character
work remains parked, not completed. The final archive is
`output/sunset-workshop-demo-v018-r2/Windows`; launch with
`scripts/play_workshop_demo.ps1 -Lighting Day`. See `docs/SUNSET_WORKSHOP.md` for the exact
map/package identity and `work/sunset-workshop/evidence/final-demo-v018.html`
for the review panel. All displayed scene frames there come from the cooked game.

Accepted final scope: independent dressing including sofa/two plants, contact
corrections, final lighting/atmosphere, unchanged mountain placement and moon,
real-depth window parallax, Manny with separate sword, editor and cooked
programmatic movement/collision/jump evidence.13PIE and12cooked checks pass;
183compiler tests pass. This is not a physical-keyboard test claim or a blanket
asset production-ready certification. The historical open items below remain
useful lineage, not current demo blockers.

## Latest user scope change — 2026-09-05

Latest correction, 2026-09-05: after walking over to the mountains, the user
identified their apparent floating as lighting, not placement. Stop further
mountain-placement changes now. Handle exterior lighting, shadows and atmosphere
in the final composition pass. Preserve the liked moon. Lowering trials v009/v010
are separate experiments, not a required or accepted correction; do not promote
them by assuming the earlier diagnosis still holds. The v008 archive and its
launcher are unchanged. A later process check found the user's game no longer
running; it was not stopped or automatically relaunched by the agent.

The rug and other props still require a support-contact audit. The rug's roll/yaw
mix-up is a confirmed geometry-placement defect independent of the mountain
lighting correction. Keep its flat-floor fix, plus verified table/shelf contacts.

Additional acceptance requirement, 2026-09-05: the user says the view through
the window still looks like a painting and explicitly requests that this be
resolved before finalizing. The current flat panorama is insufficient. Build
a simple real-depth exterior with reference-conditioned rock geometry, mapped
ground and distant sky; verify parallax from separated walking-camera positions.
Preserve the working Manny scene. Do not label an upgraded flat picture as this
fix or finalize the demo before checking the window view in motion.

The user explicitly stopped custom-character work: "Let's just stop there and
move on. I'll keep at it later. I want to finish this demo off. Do everything
else, then create the scene and show me with the Manny instead."

For the current demo, use the existing Manny player and animations. Ayric's
face, body repair, custom rig, collar/head assembly and associated character
gates are parked, not blockers and not completed. Preserve every candidate.
The three new cel-face donor images are retained but their prepared mapping,
binding and rendering drivers were NOT run before this pivot. No head job is
live. Do not resume custom-character work without a new user request.

The full workshop, independent props, attractive simple vista, playable
collision, lighting, cooked runnable proof, launch instructions and review
panel remain required. Keep the separate sword available; test its existing
back-carry requirement on Manny if feasible without custom-character work.
This explicit change supersedes the custom-avatar requirements below for
this demo only; those requirements remain historical for later resumption.

## User direction, 2026-09-04 continuation

Finish the entire beautiful, polished demo, judge visual gates autonomously,
and provide a browsable review panel at completion. This supersedes waiting
for a fresh human response at every visual gate for this demo only. It does
not waive mechanical checks or permit calling an agent's review a human review.

The character must derive from the attached image of Ayric, in the workshop's
cel-shaded style. Preserve his recognizable face, swept hair, cobalt/gold
armour and cyan accents. The sword must be its own mesh, carried diagonally
on the back and following the animated character. Sword drawing is out of scope.

## Completion evidence required

- Polished workshop matching the warm illustrated reference, not a bare tiled
  box. Separate movable/selectable props, restored sofa, circuit board,
  attractive foliage and dressing, readable displays, composed lighting,
  and a convincing simple window vista from walking camera angles.
- Reference-conditioned Ayric geometry, reviewed from four fixed directions;
  runtime topology with deformation evidence and faithful textured identity.
- Declared UE-compatible skeleton, tested walk/idle/jump deformation, no gross
  armour/body/sword intersections, no inherited Manny visual substitute.
- Independent sword mesh and persistent back attachment in real gameplay.
- Valid spawn, circulation, collision, correct native payload budgets and
  materials, saved scene, and verified frames from a cooked runnable build.
- A polished review panel showing actual assets and gameplay evidence, with
  clear controls, launch instructions and honest accepted/rejected lineage.
- Updated README/handoff and tests. Do not label an interim reference image,
  shader test, import or sparse preview as the completed demo.

## Starting evidence and next gates

Previous goal turn: **progress**, not completion. It approved/imported the
interiors and produced an early six-type, 18-actor playable preview, with real
PIE movement/collision evidence. It did not complete this contract.

Current authoritative starting map is `L_WorkshopPreview_v003`. Sofa retains
its baked-light failure, board its 15,973-vertex failure, plant its rejected
geometry. No cooked completion exists. The new character and sword are new
image-conditioned jobs, not replacements for those unresolved scene tasks.

On fresh preflight no Unreal/DCC/inference process was running, about 22 GiB
of VRAM was free, and 102 tests passed. Existing MCP services are preserved.
Do not assume these process/resource facts remain current at the next launch.

## Modular avatar implementation decision, 2026-09-05

Use a separately verified rigid head attached to the animated UE head bone,
not a claimed deforming facial rig. This preserves more reference detail than
forcing the new head into the approximately5k allocation left by the existing
body. The new component workspace is `work/sunset-ayric-rigid-head-v1`;
`assembly-contract.json` records the exact original identity source and checks.
The old integrated-head topology attempts remain rejected, not reclassified
or promoted in place. The rigid component has its own fresh gate ledger.

Each component retains its20,000triangle/15,000vertex ceiling. The combined
body + head + sword target is60,000triangles; measure and report the actual
sum, never describe the assembled result as a20k character. This does not
change the separate seven-asset benchmark cohort or its budgets.

Completion still requires the full requested custom avatar: no Manny visual
substitute, no visible old-head overlap, clean high-collar neck transition,
head motion following the declared skeleton in idle/walk/jump, separate
back-carried sword, and actual cooked runtime proof. Rigid-head static import
alone cannot satisfy these assembled-character requirements. Body material,
rig/deformation and scene holds are not waived by component acceptance.
