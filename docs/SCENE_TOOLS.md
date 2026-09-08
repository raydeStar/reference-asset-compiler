# Reusable scene tools

The workshop exposed expensive repetition: per-version Python replacements,
opaque fog units, unchecked property setters, and evidence pages that blurred
technical success with approval. These tools extract those mechanics without
copying the experiments wholesale or changing asset promotion gates.

The night scene is **awaiting human approval**. Test success does not change that.

## 1. Plan atmosphere in physical units (CPU only)

```powershell
python scripts/scene_tools.py plan examples/scene-atmosphere.json
```

No engine launch, writes, inference, or downloads. The example refers to the
local workshop; other users replace map names/hash and actor labels with their
own. It is a recipe, not a bundled UE project or a promise the map exists in a clone.

Each named, existing local fog volume declares a radius, ground elevation,
height above ground, density, linear albedo/emission, and an e-fold height in
centimetres. Density falls to about 37% after rising by that height; it is not
a hard clipping plane. Radial density is deliberately zero for low ground haze.

The UE 5.8 adapter implements:

```text
actor Z = ground Z + height above ground
uniform actor scale = radius_cm / 500
UI height falloff = 100 * radius_cm / e_fold_height_cm
```

For a 24m radius and 2m e-fold height, UI falloff is 1200, not 12. UE multiplies
the UI value by 0.01 inside its normalized sphere shader. Unsupported engine
versions, non-finite/bool numbers, unsafe map paths, duplicate labels, unknown
fields, source overwrite and unsupported falloffs fail rather than clamp silently.
Changing a radius therefore does not silently change the requested dust height.

## 2. Dry-run or apply in a dedicated UE process

Do not run this in an interactive editor. Preserve existing creative sessions.
Set `$editorCmd` to your installed `UnrealEditor-Cmd.exe` and `$project` to your
own `.uproject`. Start with a fresh output directory and a nonexistent target map.

```powershell
$env:RAC_SCENE_DEDICATED_EDITOR = '1'
$env:RAC_SCENE_RECIPE = (Resolve-Path examples/scene-atmosphere.json).Path
$env:RAC_SCENE_OUTPUT = Join-Path (Get-Location) 'work/scene-check-001'
$env:RAC_SCENE_APPLY = '0'
$sceneScript = (Resolve-Path scripts/ue5/apply_scene_atmosphere.py).Path
& $editorCmd $project "-ExecutePythonScript=$sceneScript" -unattended -nosplash
```

Dry-run loads the hash-pinned source in that dedicated process, resolves all
labels/types, checks the protected scene and writes `result.json`; no map is
created or saved. **Read `result.json.ok`; editor exit code alone is insufficient.**

For an explicitly requested change, choose another fresh output directory and
set `RAC_SCENE_APPLY=1`. The runner uses `new_level_from_template`, never generic
World duplication. It sets only named fog parameters/transforms, reads values
back, compares all static-mesh component transforms/meshes/material paths/collision
profiles plus the game mode, saves the new map, reopens it, and verifies again.
The receipt hashes source, recipe and saved derivative. Human review stays pending.

No actor creation/deletion, prop editing, texture generation, cooking, process
killing, automatic retry, or approval is performed. It is a **fog-only adapter**,
not a universal level editor. Its snapshot checks references/state, not every
byte of every referenced material or Blueprint. Failures retain evidence and any
partial derivative; use a fresh target after diagnosis, never overwrite it.

The planner uses only the standard library so Unreal's embedded Python does
not need Pillow. The review bundler below uses the repo's ordinary Pillow dependency.

## 3. Build a portable review from actual existing receipts

```powershell
python scripts/scene_tools.py bundle work/sunset-workshop/evidence/night-review-v026.json `
  --root . --output work/night-review-portable-001
```

This version adapts the existing `scene-lighting-review.v1` receipt format,
including its RacValidate Windows package layout. It is not an arbitrary-JSON
or arbitrary-engine attestation tool. It checks:

- every bound file's SHA-256 and optional byte count;
- nonempty, explicitly true checks matching the bound cooked `audit.json`;
- exact map identity/hash and matching ordered capture paths;
- distinct readable PNG captures;
- the exact package inventory and byte total, including both bootstrap and
  nested game executables; only runtime `Saved` directories are excluded;
- path containment, escaped HTML, UTF-8, fresh output, and copied-image hashes.

It creates `index.html`, `review.json`, and relative `frames/*.png` files. Copy
or zip the **whole folder** to share it; no absolute desktop paths are needed
to view it. It does not upload anything, copy the executable, or launch a new
engine run. The root explicitly defines allowed source files. On another machine,
existing source receipts must resolve under that machine's supplied root.

The page always says **awaiting human approval**, even if the source receipt
claims a prior visual pass. It attributes the prior reviewer without turning
that judgment into a new approval. Rehashing existing evidence is not independent
proof of capture provenance, physical keyboard input, or production readiness.

## 4. Retain the opt-in cooked gameplay audit

[`RacDemoAudit`](../integrations/ue5/RacDemoAudit/README.md) is now checked-in
source rather than an untracked local tool. It is a **Manny/workshop-specific**
runtime fixture, not a universal character test. It is inert without its audit
flag and includes an optional skylight camera. Build/link it through an explicit
code-based game target; staging a plugin descriptor is not sufficient.

## Verification

Hermetic tests cover recipe validation/units, numeric comparisons, optional
dependencies, changed/extra/missing evidence, conflicting receipts, package
layout, HTML escaping and approval boundaries. These fixtures are not labeled
as real engine runs. The operator was separately exercised against UE 5.8 and
the actual local night receipt; generated scenes, packages and screenshots stay
out of Git. No model acquisition or changes to the scene's approval occurred.
