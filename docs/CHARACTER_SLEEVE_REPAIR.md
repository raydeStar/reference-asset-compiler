# Character02 sleeve repair, 2026-10-12

The installed derivative is a texture-only review candidate. It leaves the
release-v2 mesh, UVs, bones, weights, morphs and all other maps unchanged.
The user's rejected sleeve crop shows sharp painted folds meeting broad blurry
fill. A conservative whole-body rebake reduced streaks but remained blurry;
the selected pass instead extends the retained front/back sleeve detail around
the full sleeve circumference. Each source image's sleeve column is registered
separately because the back painting's arms sit lower in the frame.

This is inferred continuation of existing artwork. It does not claim a new
side-view authority or human visual acceptance. The shoulder emblem, collar
tears, hair appearance and hand/coat intersections remain imperfect.

## Reproduce

Run from rac-character with the retained workstation inputs present:

```powershell
python scripts/repair_character_sleeves.py --recipe recipes/character-02-sleeve-continuation-20261012.json --out work/character-02/sleeve-repair-fresh
```

The driver checks every input hash, requires a fresh directory, snapshots scripts,
records commands and Python/library versions, and copies unchanged dependencies
by hash. No new model inference, commercial add-on or closed image generator is
used. `wrap_sleeve_paint.py` preserves non-sleeve surface pixels exactly and only
extends changed islands into their nearest gutters. Samples outside either
source's eroded foreground are excluded. Rendering uses Blender 5.2.2 LTS,
Cycles, seed 23, 24 samples, AgX, fixed cameras and lights.

Selected build: `work/character-02/sleeve-repair-20261012-release-v2/`.
Body paint SHA-256:
`02fcea5777b8fce514da17b4f646d5ee1395cd08f7d12fc8a16ab5aef7ea4006`.
Unchanged FBX SHA-256:
`f4827fb2b9224d72e9265af1c652cd82c8ee36b4499b9ce1b17aa0440baf6d2e`.
Source native SHA-256:
`4f643761abb8f80c25dde36bd4442903ad8086772d13d62013e9cb2d0b7c0ebb`.

The independent driver output matches `sleeve-wrap-20261012-v9` byte for byte.
Its paired unchanged-source renders are in that attempt's `review/`: `0-*`
is the prior paint, `1-*` is the sleeve continuation. Both use the identical
final native source and recorded Manny idle pose. Views include front, side,
back, collar, elevated 3/4 body and elevated 3/4 shoulders.

```powershell
& $Blender --background --factory-startup --python-exit-code 1 --python scripts/blender/review_outfit_paint.py -- --source work/character-02/seams-20261012/release-v2/Character02_UE5_coat.blend --manny-dir work/ennix-character-v1/rig-ue5 --paint work/character-02/seams-20261012/release-v2/outfit-paint/body_basecolor.png --paint work/character-02/sleeve-repair-20261012-release-v2/outfit-paint/body_basecolor.png --out work/character-02/sleeve-review-fresh --device GPU
```

Set `$Blender` to the installed open-source Blender executable; CPU is also
supported. Add `--reference` for the actual bind pose. The extended
`review_character_seams.py` also includes elevated 3/4 views.

## Engine findings and installation

The Aether Wars installer imported only textures and ran `audit`: zero errors,
34 morph targets, unchanged skeleton/animation references. Character02's skin,
outfit and mask are now configured resident; normal tiles still stream and
mip filtering stays enabled. The body colour and mask have thousands of tiny
islands; coarse residency can mix unrelated garment colours. A cold editor
capture with no prestream/viewport-follow restored detail after the policy save.

Use the game project's `Tools/CharacterInstallHeadless.py` with this build and
steps `textures audit`. The game's `Docs/CharacterPipeline.md` explains the
space-safe wrapper. Do not run a mesh/animation rebuild for this texture change.
Receipts: game `Saved/CharacterTextureRepair/sleeve-install-v2.log` and
`Saved/CharacterInstall/Character02/verification.json`. Editor capture scripts
explicitly record pose/time, cameras, bones, image hashes and `gameplay_verified:
false`. The new final views are prefixed `sleeve-v2-idle-20261012`.

## Rejected and diagnostic evidence

- `Saved/PosedCloseups/codex-baseline-*`, `codex-fulluv-*`, `codex-lod0-*` in
  the game: full-precision UVs and forcing LOD0 did not solve the tan shards.
  Prestream/resident captures did. Disabling mipmaps added no useful benefit.
- `paint-diagnostic-20261012/`: original and processed texture on the final
  native mesh, proving that capture failures and source-paint defects differ.
- `atlas-20261012-v1`: Smart Project increased charts, rejected before baking.
  `atlas-20261012-v2`: xatlas still left 5,591 charts, rejected before baking.
- `surface-20261012-v1`: voxel candidate failed the displacement ceiling.
  v2 passed that check but stopped on a Blender UV collection API error.
  v3 completed (45,999 garment triangles, 1,705 charts) but lost surface detail
  and retained collar defects. **Rejected visually; never installed.**
- `paint-rebake-20261012-v1/`: stricter projection angles reduced streaking but
  erased too much detail. **Not installed.**
- Sleeve attempts v1-v4 stopped on array-shape/foreground guards; logs retained.
  v5 used the overly smooth rebake, v6 was superseded by limiting gutter changes;
  v7 used original body paint but its crown-only repair left flat forearm fill.
  v8 rebaked the full sleeve; v9 narrows the front/back blend to avoid averaging
  unrelated folds across the crown. v9 is the selected local review derivative.
- Original elevated evidence examined:
  `C:/work/character-02/top_views_v22/02_Top_Front_Elevated_Angle.png` and
  `03_Top_Left_Sleeve_Zoom.png`. These show the prior sleeve band in Blender,
  independent of engine streaming. They are older v22 evidence, not final proof.

Validation: new/changed script Ruff and syntax checks pass. Baseline verifier:
887 tests passed, 36 skipped, 198 subtests passed, then seven pre-existing lint
errors in unrelated files. Full verification is not claimed green.
