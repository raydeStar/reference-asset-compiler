# Open tasks for agents and contributors

Well-scoped work with acceptance criteria, so a Claude Code or Codex session can
pick one up without chat history. Each task names what it touches, what "done"
means, and whether it needs a GPU. Record outcomes in `docs/HANDOFF.md`; add a
lesson to `docs/DECISIONS.md` if something surprising happened.

Read `CLAUDE.md` and `AGENTS.md` first. The non-negotiables there (image
conditions AI, one gate at a time, receipts with hashes, never auto-retry a
crash, never kill GPU processes) apply to every task below.

## No GPU needed

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
- **Done when:** `workflow_doctor.ps1` reports every `hy3d21.*` and `hy3d2mv.*`
  route `[OK]` on a machine that started with none of them. Network and about
  40 GB of disk; no GPU until the first run.

## GPU needed

### 7. Second character through the whole route
- **Why:** the cat is one data point. A humanoid from an image would exercise
  the free humanoid rig on generated geometry and the Manny retarget.
- **Done when:** a new asset id has every stage through `ue5_import` passed in
  its ledger with the same receipt discipline, and the differences from the cat
  are written up in `docs/HANDOFF.md`.

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
  `texture_approval`, `ue5_motion_review`, `cook`.
- Prefer a versioned derivative over an in-place fix.
- Run `scripts\verify.ps1` before committing; CI also runs ruff on `scripts/`.
