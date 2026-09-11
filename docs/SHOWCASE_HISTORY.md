# Showcase and status history moved out of the README

*Type: chronological log*

These paragraphs were in `README.md` until 2026-09-11. They are status
statements from their dates, kept verbatim so the README can stay short without
losing the record. The current state is in [STATUS.md](STATUS.md); the dated
operational log is [HANDOFF.md](HANDOFF.md).

## Recently added (as of 2026-09-08)

- Scene utilities: [physical-unit atmosphere recipes, protected UE derivatives,
  and portable pending-approval reviews](SCENE_TOOLS.md). Start with
  `python scripts/scene_tools.py --help`; planning needs no editor or GPU.
- Character repair: [source-locked head fitting and repeatable neck blending](CHARACTER_HEAD_AND_NECK.md).
  `./scripts/run_neck_transition.ps1 -Output work/my-neck-review-v001` replays the
  local pinned recipe on CPU; native appearance and human approval remain separate.

## What made the texture work repeatable (v051 showcase notes)

- Match painted features to modeled eyes, nose and mouth; better paint cannot
  repair the wrong facial geometry.
- Keep the face's coherent UVs and approved artwork intact. Correct the narrow
  body/neck transition instead of stamping over the entire character.
- Review albedo separately from roughness, metallic and normal response, then
  inspect both sides in the actual engine.
- Measure socket placement in the reference pose and verify real deformation
  and native vertex counts—not just bone names or capsule movement.

## Sunset workshop demo status (2026-09-05 to 2026-09-06)

Visual review is human-led by default. An expressly user-delegated demo can
record agent judgments with source-, stage- and artifact-bound consent receipts;
these are labeled as agent reviews and never waive mechanical checks. See
[pipeline gates](PIPELINE.md). The
[Sunset workshop demo](SUNSET_DEMO_COMPLETION.md) is a verified local
Windows demo. `scripts/play_workshop_demo.ps1 -Lighting Day` opens v018: Manny with a separate
back-carried sword, restored sofa and plants, independently placed props, a flat
rug, corrected support contacts, composed lighting and a real-depth window vista.
All 13 editor and 12 packaged-game programmatic movement/collision/jump/attachment
checks pass. Eight actual cooked frames were visually reviewed, including a
2.2m paired window baseline. No physical-keyboard test is claimed.
The package is 1,131,307,068 bytes across 48 files; no Codex, model server or editor
is needed to play. Review panel: `work/sunset-workshop/evidence/final-demo-v018.html`.
Custom Ayric now has a repaired locomotion rig and a source-locked detailed-head
candidate; see [current repair evidence](AYRIC_REPAIR_2026-09-06.md).
This scene demonstration does not
silently certify every asset's separate production-ready gallery gate. See
[current scene status](SUNSET_WORKSHOP.md).

The launcher defaults to the separate **night v026** variant: warm work
lights, cool moonlight, small stars through the window and skylight, and very
faint ground-weighted desert haze. The tall dust dome was rejected. All 169
original objects are unchanged; one non-colliding sky sphere was added.
Night passes 12 packaged programmatic checks with nine inspected game captures.
Its local package is 1,132,895,624 bytes across 48 files. No additional models
or downloads are required. Use `-Lighting Night` or `-Lighting Day` to choose.
See [night lighting and evidence](SUNSET_NIGHT.md).

## Superseded pre-v051 status (retained for provenance)

The notes below describe earlier stages, not the current assembled demo.

Current scene experiment: [Sunset workshop](SUNSET_WORKSHOP.md) tracks
the modular, reference-conditioned room study and separate prop jobs. The
local early walkthrough has 19 independent prop actors, with player spawn,
gameplay movement and blocking collision checked in UE PIE. It remains work
in progress, not a cooked release. The optimized circuit board now passes its
native import and static UE visual review and is separately placed in preview
v004. Sofa, foliage, the custom character and overall scene polish remain
unfinished. On the workstation with the saved project, launch it with
`./scripts/play_workshop_preview.ps1` (no Codex dependency).

The separate sword has passed native UE import (1.35 m, 11,123 LOD0
vertices) and a delegated six-frame static editor review, including all three
LODs. Animated back attachment and cooked proof remain pending. Actual UE
frames: `work/sunset-workshop/evidence/sword-review-v003.html`.
Ayric's latest held texture package is `prod-collar-v001`, with a
cleaner face/collar transition. It still fails the lighting gate and has not
advanced to rigging. The workstation review is
`work/sunset-workshop/evidence/ayric-collar-review-v001.html`.

An optional IntrinsicAnything albedo challenger now runs in an isolated local
environment; it is not the default pipeline or an approved texture replacement.
Its pinned checkpoint is exactly 15,458,840,153 bytes (15.46 GB decimal).
The measured local tool directories plus auxiliary models total 22.48 GB of
logical file bytes, excluding the interpreter and download/build caches.
The first base inference completed but softened facial detail. See
[the challenger setup and size breakdown](../workflows/texture/intrinsicanything/README.md).
No character texture has been replaced by this experiment.
The subsequent six-view tests failed: side estimates collapsed or tiled
estimates introduced bands. This route is stopped, not promoted; see
[the retained lighting escalation](ESCALATE-sunset-lighting.md).

The plant's torn single-view geometry has been replaced by a reviewed
Hunyuan3D-2mv acquisition, directly conditioned on the original plant image
and two explicitly inferred ImageGen depth views. Modeling and conservative
cleanup pass. Runtime topology remains held: the 18k reduction and bounded
normal/refinement challengers leave visible pot facets. Actual comparisons:
`work/sunset-workshop/evidence/plant-repair-review-v001.html`. This did not
change Ayric's held texture or the UE scene.

The face repair now has a separate rigid-head component experiment,
`work/sunset-ayric-rigid-head-v1`. It reuses the exact image-conditioned AI
acquisition; dense modeling, cleanup and static runtime topology have passed.
The accepted head has 10,020 vertices and 19,988 triangles, with valid normals
and closed surfaces. Texturing and head-bone attachment remain unfinished.
Actual clay evidence is shown in
`work/sunset-workshop/evidence/ayric-modular-head-review-v002.html`.
This is a modular avatar route, **not** a monolithic 20k character: each body,
head and sword component keeps its own 20k triangle/15k vertex ceiling, with
a 60k combined target. Actual assembled totals and neck/motion/cooked-runtime
proof remain required. Existing body material/rig holds are unchanged.

Head-texture work now has a comparison panel at
`work/sunset-workshop/evidence/ayric-head-texture-working-v001.html`.
The new UV layout keeps the central face continuous and improves atlas use;
the matte material is preferable to the raw AI scalar maps. Eye-edge paint
and skin/hair transitions still prevent texture approval. The panel labels
failed candidates explicitly; it is not a completed character demo.

The earlier partial face-artwork comparison is
`work/sunset-workshop/evidence/ayric-face-donor-review-v001.html`.
AI-guided, geometry-bound eye mapping improves the irises, while an angled
temple repair remains rejected for incomplete transitions and a small eye
regression. The panel separates actual 3D renders from AI source artwork and
includes exact prompts. No face texture approval or completed UE avatar is
claimed; the body and workshop remain unchanged.

The retained coherent-face comparison is
`work/sunset-workshop/evidence/ayric-coherent-face-review-v001.html`.
Three AI artwork views now share surface-derived landmarks; exact subpixel
visibility removes projection striping. Actual front and both angled views
have cleaner eyes and continuous cheeks. The working candidate remains held:
rear hair/neck coloration is gray, and the unchanged lighting-correlation
check measures 0.36124 against a 0.35 limit. All six directions are shown lit
and unlit. This is progress on the face, not a texture pass or UE release.

The head component has since passed its texture gate. Current review:
`work/sunset-workshop/evidence/ayric-head-texture-review-v002.html`.
Image-conditioned rear hair and bilateral hair mapping preserve the repaired
facial features; the 4K, 0.33 m head/neck FBX passes the unchanged static texture
checks without a waiver. Approval is explicitly agent-delegated and head-only.
The complete avatar is still unfinished: body material, collar fitting,
animation, back-mounted sword and cooked UE gameplay require their own proof.

The repaired head now also passes native UE 5.8.2 import and delegated static
appearance review. Actual engine captures:
`work/sunset-workshop/evidence/ayric-head-ue-review-v002.html`.
UE LOD0 is 12,740 vertices / 19,988 triangles at 33 cm; all three LODs are measured.
The panel includes albedo controls, both sides, the shadowed rear and the
retained overbright fixture. This is a separate head inspection, not an
attached or animated avatar. No accepted face artwork was changed for UE.

A new body-brightness-only test did not clear the existing lighting gate and
was not promoted. Its evidence is retained at
`work/sunset-workshop/evidence/body-lighting-canary-v001.html`.

## Earlier README media, still in `docs/images/`

- `ue5-gallery-playable.jpg`: the UE 5.8 gallery level walked as Manny, every
  compiled character looping a retargeted idle, each authority beside its
  production derivative.
- `cat-texture-review-calibration.jpg`: the same atlas under the factory AgX
  transform and the calibrated transform. The first review render was washed
  out by Blender's factory AgX transform and showed a hard white glint that
  turned out to be a mirror-glossy eye, not paint. The accepted attempt007 is
  the same base color under a calibrated transform with the eye roughness
  lifted; that is what shipped to UE5.
- `cat-rig-review.jpg`: skeleton overlay and the five-pose deformation suite.
- `cat-eye-roughness-fix.jpg`: a mirror-glossy eye under the key light before
  and after the roughness floor. The painter had left the eye at roughness
  0.11; one script lifted only the two eye regions to a 0.7 floor and recorded
  the mask, the texel count, and the hashes.
- `humanoid-landmark-rig-overlay.jpg`: the free landmark rig on the field-scout
  male mesh with its armature stripped: 86 bones, passes the `ue5_manny` gate
  and the five-pose suite. Fingers are Manny's layout fitted to the measured
  forearm, not a measurement; check the hand overlay before trusting finger
  deformation.
- `ayric-v051/`: the earlier black-background studio captures, superseded by
  the in-workshop set in `ayric-workshop-v051/` after the user's correction.
