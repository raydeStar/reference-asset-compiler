# Open tasks for agents and contributors

*Type: reference*

Well-scoped work with acceptance criteria, so a Claude Code or Codex session can
pick one up without chat history. Each task names what it touches, what "done"
means, and whether it needs a GPU. Record outcomes as a dated entry in
`docs/HANDOFF.md` and update `docs/STATUS.md` in place; add a lesson to
`docs/DECISIONS.md` if something surprising happened.

Read `CLAUDE.md` and `AGENTS.md` first. The non-negotiables there (image
conditions AI, one gate at a time, receipts with hashes, never auto-retry a
crash, never kill GPU processes) apply to every task below.

## No GPU needed

### Frastown West Berth follow-ups (2026-11-23)
- **Acquire, do not script.** The kit's geometry was built by script from scene measurements. The owner wants assets to
  go through the normal route: reference image, image-conditioned geometry, then cleanup and surfacing. Start with the
  pieces a viewer stands at (gunwale, deck plates). The scripted kit gives the dimensions, pivots and sockets to hold
  the acquired pieces to. Needs a GPU for the acquisition itself. Done when a piece acquired that way passes the same
  bounds, socket and collision checks and the owner's review.
- **Unreal import of surface pass B02.** `Unreal/import_batch.py` in the kit folder follows batch 01's verified script
  and has not been run. Done when it writes `ue-import.json` with every assertion passing in UE 5.8.4.
- **Headset review.** Look for shimmer on the tread and rivet edges under head movement. The import script folds
  normal variance into roughness for this; confirm it took effect.
- **Arm's-length sharpness.** The rail is 0.66 mm a texel at 4K. Add a tiling detail-normal layer in the engine
  material and judge it at 30 cm.
- **One painter.** The kit folder still has its own copy of the painter. Point its runner at the registered stages
  (the ladder already reproduces texel for texel) and delete the copy.

### Game review road follow-ups (2026-11-07)
- **Delivered:** `scripts/run_game_review.ps1` ([GAME_REVIEW.md](GAME_REVIEW.md)): recipe to playable review in The
  Aether Wars with in-game face/body closeups, named looks, a pose sheet and before/after sheets. Remora's attempts:
  `work/remora-airship-20261106/game90/`.
- **Hand landmarks:** delivered as road step 02a (`fit_hand_landmarks.py`); Remora 18/24 and 15/24 joints inside,
  right pinky still ~1 cm out. Remaining: per-finger refinement for the pinky, and a hand closeup angle that the
  attack's crossed forearm does not hide. Done when Mark passes the hands in game.
- **Loose garments:** with heat weights Remora's tunic hem reads acceptably; revisit only if a review flags it.
- **Hair look:** delivered; Mark picked hair shading along a baked flow map, now the default `hair_look`.
- **Animations do not pass (Mark, 2026-11-07).** The motion pass shows all 20 player animations deforming without
  tearing, but Mark judged the animations in game and they do not pass. Ask him what fails (timing, poses, blends, the
  powers' Character02 hand-on-hip ending, feet) before tuning; the motion sheet is evidence, not the verdict.
- **Face:** delivered; Mark passed Remora V11's face in game (2026-11-07). The closed-lid repaint and mouth fit are
  road defaults (`auto`). The shut lid still shows the open eye's liner along its bottom
  edge, patchy where painted lash strokes cross it. The game repo's `Tools/Characters/Remora.json` and `Character02.json` still name
  `mouth-parting` (should be `mouth-parling`); fix there only with Mark's go-ahead. Expressions are subtle at the
  game's table weights; a per-face expression gain is not built.

### Surface finishing reuse after the Raider port (2026-11-06)
- **Delivered:** `rac polish-init` / `rac polish`; inspected/restored acquired
  surfaces, UV/map transport, registered guides, explicit AI handoff, material
  finishing, bounds and packed fixed-view review. The real collar replay matches
  Candidate05 byte for byte. Candidate06 ear finishing also replays exactly,
  with retained AI references and explicit guide material subsets. See `docs/POLISH_WORKFLOW.md` and
  `docs/evidence/raider-polish-pipeline-20261106.json`.
- **Second-asset evidence:** Remora has retained AI hair/face lineage, actual
  Framewright review, a reusable acquired-hair runner and a byte-identical
  local face/collar replay (`work/remora-airship-20261106/checkpoint67.json`).
  The exposed-tunic repair now runs through `rac polish`, with retained actual AI
  inputs/prompt, packed multiview review, byte-identical fresh replay and actual
  Framewright acceptance (`docs/evidence/remora-surface-canon-20261106.json`).
  [Canonical surface workflow](CHARACTER_SURFACE_WORKFLOW.md) is the entry point.
  No new generic anatomy inference is claimed by this completed second-asset proof.
- **Next reusable work:** generalize the reviewed Remora component selections
  and bounded anatomy/weight repairs without assuming its mask fits another
  character; keep the frozen local replay as the comparison authority. Keep selection and
  visual acceptance explicit. Do not treat a repaired collar as a full automatic
  character reconstruction.
- **Done when:** a second source has retained acquisition lineage, explicit
  region/camera choices, a completed AI request/response, repeated finishing
  output, and visual review under its actual consumer lighting. No production
  promotion from a successful CLI run or packed render alone. AI generation is a
  separate provider/GPU action; the deterministic finishing and checks use CPU.

### Ennix sharp-turn contact review (2026-10-23; rejected and set aside)
- **User direction:** the current Ennix character was rejected during manual
  gameplay and the user requested Character02 instead. Preserve all evidence;
  do not continue Ennix polish without a new request. The feedback does not
  identify a specific mesh, animation or gameplay defect.
- **Technical status:** correction and paired game panels are complete
  in `work/ennix-turn-contact-20261023/`. TurnV1 has <0.001 cm measured planted
  ankle excursion at both rates, positive observed sole clearance, unchanged
  path/leg lengths and 212 preserved original game files. These measurements do
  not override the user's rejection. Cooked/performance work is separate.
  Evidence: `docs/evidence/ennix-turn-20261023.json`.
- **Why:** the current idle/walk candidate clears observed terrain at 30/60 Hz,
  but its planted ankle yields up to 10.445/9.414 cm during sharp turns. Ground
  clearance and planted-foot sliding are separate acceptance gates.
- **Start with:** `docs/ENNIX_ANIMATION_POLISH.md`,
  `docs/evidence/ennix-polish-20261023.json` and the paired movies in
  `work/ennix-idle-walk-20261023/presentation/`. Human rejection is recorded in
  `work/ennix-turn-contact-20261023/manual-verdict-20261023.json`.
- **Touches:** a separate Ennix turn/transition candidate and its review profile;
  preserve Character02 assets, shared game code and default player.
- **Done when:** approved turning behavior reduces the measured plant excursion
  without introducing knee/hip jumps, ground penetration or hand/scarf clipping;
  fresh saved-asset reload and all eight actual-game cases pass at both rates,
  with four-view/moving evidence and explicit human visual acceptance. No claim
  of completion from the positive sole-gap score alone.

### 1. Export skeletons at unit root scale
- **Why:** every compiled skeleton arrives in UE with a 100x scale on the root
  and bone offsets in metres (`docs/DECISIONS.md`, "Compiled skeletons carry a
  100x root scale"). Retargeting and physics tools that write centimetres into
  that local space break; `setup_gallery_playable.py` compensates today.
- **Touches:** `scripts/blender/normalize_ue5.py`,
  `scripts/blender/bind_texture_payload.py`, `scripts/blender/rig_from_landmarks.py`
  export settings; possibly bake a 100x into data before export.
- **Done when:** a re-exported field-scout male imports into UE with root scale
  1.0 and bone offsets in centimetres (probe with a spawned
  `SkeletalMeshComponent`), `gate_rig.py` and `deform_test.py` still pass, the
  UE import verifier still reports the manifest height, and
  `setup_gallery_playable.py` measures `ancestor scale 1.0` and skips the
  compensation. Update the DECISIONS entry.

### 2. Linux and macOS drivers
- **Why:** the Blender stages are plain Python, but every driver is PowerShell.
- **Touches:** a `scripts/*.sh` twin for `compile_asset.ps1`,
  `run_rig_candidate.ps1`, `setup_ue5_project.ps1`, `verify.ps1`; `rac_env.py`
  discovery paths for Blender and Unreal on those platforms.
- **Done when:** `verify.sh` passes on a Linux runner in CI and the prop route
  compiles a mesh end to end without PowerShell.

### 3. Hand roll offsets in the gallery retarget
- **Why:** chain alignment cannot fix roll about the bone axis; the ninja's
  hands twist under the retargeted idle.
- **Touches:** `scripts/ue5/setup_gallery_playable.py`; the retargeter
  controller's `set_rotation_offset_for_retarget_pose_bone` API.
- **Done when:** a per-skeleton optional offset table (degrees per bone) is
  applied to the target retarget pose, recorded in `work/ue5-gallery-idle.json`,
  and the ninja hands read correctly in the gallery. Needs UE 5.8 headless, not a GPU.

### 4. Tests for the new scripts
- **Why:** `clamp_region_roughness.py`, `package_character_texture.py`,
  `derive_*_landmarks.py` and `rig_from_landmarks.py` have no unit coverage.
- **Touches:** `tests/`. Blender-side code can only be syntax-checked off-host
  (`scripts/check_stage_syntax.py` already does that); the pure-Python parts can
  be tested with synthetic atlases and meshes.
- **Done when:** `verify.ps1` runs at least one test per new pure-Python script
  and the tests fail on a deliberately broken mask or missing input.
- **Status (2026-09-08):** partly done. `clamp_region_roughness.py` is covered
  end to end against a synthetic atlas (`tests/test_clamp_region_roughness.py`);
  the numpy helpers of `derive_humanoid_landmarks.py` and
  `derive_mascot_landmarks.py` run under a stubbed `bpy`
  (`tests/test_landmark_helpers.py`); `package_character_texture.py` has
  argument-contract tests. `rig_from_landmarks.py` is still uncovered: every
  function takes a live Blender object, so it needs a fake-object harness.

### 5. Coherent semantic UVs for unrigged meshes
- **Why:** Smart Project produces confetti islands (783 on the cat), which caps
  texel density and puts a seam every few centimetres.
- **Touches:** `scripts/blender/semantic_uv.py` needs skin weights today; a
  landmark-region variant could use the landmark-derived skeleton from
  `rig_from_landmarks.py` to label regions before the texture stage.
- **Done when:** the cat's UV transport has under 100 islands with the head
  chart at two to three times body density, the geometry-lock gate still
  reports zero vertex motion, and the texture gate's island count passes without
  a waiver. A repaint (GPU) is a separate follow-up.

### 6. Setup script for the AI stages
- **Why:** `docs/AI_STAGES_SETUP.md` describes the studio tree by hand.
- **Touches:** a new `scripts/setup_ai_stages.ps1` that clones the two upstream
  repositories at the pinned commits, creates the two virtual environments,
  applies `patch_hy3d21_windows.py`, and downloads the weights with
  `huggingface_hub`.
- **Done when:** `workflow_doctor.ps1` reports every `hy3d21.*`, `hy3d2mv.*`
  and `hy3d2.runner_exact` line `[OK]` on a machine that started with none of
  them. Network and about 40 GiB of disk; no GPU until the first run.

## GPU needed

### 7. Second character through the whole route
- **Why:** the cat is one data point. A humanoid from an image would exercise
  the free humanoid rig on generated geometry and the Manny retarget.
- **Done when:** a new asset id has every stage through `ue5_import` passed in
  its ledger with the same receipt discipline, and the differences from the cat
  are written up in `docs/HANDOFF.md`.

### 9. The Raider's character build, for the next character
- **Why:** Mark wants the v7 route reproducible on the next test character. The new stages are already
  character-agnostic: `finish_materials.py` with `profiles/materials/character-finish.json`, `recut_labels.py`,
  `build_parts.py --clean-edges --budget-scale`, `part_uv.py`, `rigid_parts.py`, `plate_check.py`, `manny_axes.py`,
  `save_textures.py`. What still ties the build to CH-03 Raider (`scripts/revamp/raider/`):
  1. Part segmentation: done 2026-11-03 with `scripts/auto_part_map.py` and
     `profiles/segmentation/humanoid-gear.json` (Grounding DINO + SAM, both Apache-2.0), wired in as
     `build_raider.ps1 -From labels`. It scores 0.889 pixel agreement with the Raider's hand map and labels the
     Guard, Scout and Bulwark looks without changes. Open: the vocabulary has no bracer part, and a cloth wrap on a
     forearm reads as skin (see `docs/WORKFLOW_PLAYBOOK.md`, "Automatic part map"). Adding a part also means adding
     it to the downstream scripts' palettes and part sets (item 4).
  2. Measured landmarks: `refine_labels.py` hard-codes collar, belt and knee heights in the Raider's normalised
     space. Derive them from `derive_humanoid_landmarks.py` instead.
  3. Reference colours: `tone_metal.py` and `tone_skin.py` carry colours measured on the Raider's reference.
     Sample them from the reference inside each part's 2D mask.
  4. Names: about 17 scripts hard-code `raider`, `painted`, `Material.001` and `raider_body/head/hand`. Move names,
     part vocabulary, budgets and material classes into a character profile (`profiles/characters/`).
  5. One-off fixes: `fill_holes.py` (a box round the jacket's back slit), `place_head.py` and `place_hands.py`
     specifics, the face wrap and bake paths.
  6. The Unreal import and play scripts live in the git-ignored `build/v5/ue` and target the Raider's review slot.
- **Done when:** `build_character.ps1 -Profile <character>` (the Raider build, generalised) runs a second
  humanoid from its dense acquisition, reference and head/hand acquisitions through parts, paint, rig, Manny,
  finish and the UE import with no script edits, the Raider rebuilds identically from its own profile, and the
  differences are written up in `docs/HANDOFF.md`.

### 8. Higher-resolution texture paint
- **Note (2026-09-05):** a head-only second paint on the same UVs is now a
  two-command route (`scripts/blender/extract_head_transport.py`, then
  `scripts/composite_head_paint.py`). It raised head resolution tenfold on
  the Ayric body but doubled facial features on that shallow head; see
  `docs/WORKFLOW_PLAYBOOK.md`, Stage 4. A candidate for the cat, whose head
  has real sockets, remains open.
- **Why:** 19.5 texels/cm² against a 120 floor. Hunyuan3D-Paint supports 768
  and more views; each needs more VRAM.
- **Done when:** one recorded attempt at 768 or 12 views on the cat's UV
  transport, validated by the same topology gate, with its VRAM peak and
  outcome in `docs/evidence/`. Record a crash once; do not retry it.

## Conventions

- One attempt directory per run; never overwrite one.
- Every new script writes a JSON receipt with input and output SHA-256 values.
- Human gates stay human: `modeling_approval`, `production_retopology`,
  `texture_approval`, `ue5_runtime_review`, `ue5_motion_review`, `cook`. The
  full stage table with receipt schemas is in
  [PIPELINE.md](PIPELINE.md#ledger-stages).
- Prefer a versioned derivative over an in-place fix.
- Run `scripts\verify.ps1` before committing; it shares the CI test, lint,
  syntax, wheel-build and isolated installed-CLI checks. No inference is launched.
