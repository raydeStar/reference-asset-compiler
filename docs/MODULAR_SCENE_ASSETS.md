# Modular architecture from acquired assets

*Type: workflow reference*

A single generated room shares its geometry and texture budget across all its
architecture. For editable scene work, acquire important pieces as isolated,
reference-conditioned masters and assemble them as independent instances. Keep
the original scene as a fallback. Derived references and mechanical passes do
not constitute human approval.

Blender may partition, clean, unwrap, fit and export acquired geometry. It must
not replace image-conditioned acquisition with an eyeballed primitive room.
Framewright owns library records, scene instances, review and project exports;
the compiler owns the assets and their verification.

## Separate stocked furniture from its contents

Acquire empty shelving and a separate empty counter. Acquire each bottle,
tankard, jar or pitcher as its own reference-conditioned master, then reuse
those masters as independent scene instances. A cabinet full of fused vessels
spends its geometry and texture budget on silhouettes that cannot be repaired
or rearranged individually. Keep the earlier assembly as a fallback.

Review open vessel mouths from above as well as the fixed four views. Check
handle openings in geometry before painting. Normalize each master to a real
height, then ray-cast its base footprint onto the acquired shelf deck. Check
stock-to-stock bounding-box overlaps and inspect the assembled result; an
isolated asset render does not prove shelf contact or headroom.

If the painter stretches colour bands across horizontal boards, retain that
attempt and derive an albedo swatch from the source reference with the image
model. `scripts/blender/texture_horizontal_surfaces.py` applies it only to
existing upward faces, optionally also downward faces. It checks geometry and
unselected UV/material slots before export, refuses rigs and existing outputs,
and emits a hash-bound receipt. This is downstream material repair, not fresh
geometry acquisition or human approval.

```powershell
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/texture_horizontal_surfaces.py -- `
  acquired-shelf.blend repaired-shelf.glb material-repair.json reference-oak.png `
  --minimum-up 0.65 --include-down --tile-metres 1.3
```

Inspect the derivative from all four directions. The mapping uses world XY
metres, Z up, and intentionally leaves vertical faces on their original paint.
Keep the image-generation prompt and lineage beside the material receipt.

## Extract retained modules

`scripts/blender/partition_static_asset.py` takes a triangulated static `.blend`,
a measured recipe and a fresh output directory. The recipe pins the source's
actual SHA256. Boxes use **Blender world XYZ metres, Z up**. The first matching
box owns each polygon by centroid; an explicit remainder retains everything else.

```json
{
  "source_sha256": "<actual source SHA256>",
  "parts": [
    {"name": "floor", "bounds": [[-4, -5, -0.01], [4, 5, 0.29]]},
    {"name": "support-post", "bounds": [[-0.4, -1.12, 0.29], [0.65, 0.4, 2.8]]}
  ],
  "remainder": "retained-remainder"
}
```

These are example bounds measured for one room, not architectural defaults.
Measure another source rather than silently updating a mismatched source hash.

```powershell
$blender = 'C:/path/to/blender.exe'
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/partition_static_asset.py -- `
  C:/work/room.blend C:/work/recipe.json C:/work/modules-v1
```

Each GLB has a local floor/footprint pivot. `partition.json` records its matching
**glTF placement, Y up**, to recompose the source. `modules.blend` contains the
named objects at their original placements. The helper carries UV corners,
materials and transformed corner normals, checks positional and UV error, and
records source polygon IDs to prove every polygon is accounted for exactly once.

The helper refuses rigs, modifiers, shape keys, colour attributes, nonpositive
transforms, multiple UV channels and nontriangulated sources. It preserves whole
triangles, so long triangles can cross measured boundaries. Cuts remain open;
this is not watertight remeshing or collision certification. Inspect isolated
modules and the assembly, then record any downstream clipping or capping as a
separate derivative with its own receipt. Never carry an earlier partition's
unchanged-geometry claim over a later cleanup.

With `RAC_BLENDER` set, `tests/test_static_partition_blender.py` imports actual
exports and verifies positions and UVs against a transformed source. A changed
source hash must fail before an output directory is published.

## Acquire and fit replacements

1. Retain the original scene, source-derived isolated images, exact prompts and
   hashes. Generate each architectural master independently.
2. Inspect front, side, back and three-quarter geometry after bounded remeshing.
   Hard architectural edges generally need zero broad smoothing.
3. Unwrap, paint, and check geometry/UV preservation. Retain and diagnose failed
   attempts. An output file alone is not success.
4. Use `normalize_browser_asset.py` for real master heights, then fit scene
   instances against measured room dimensions. Repeated walls/windows share
   masters. Preserve character poses and unrelated scene edits.
5. Review joins, floor contact, counter heights, stair clearances and camera
   framing in the assembly. Verify imported profiles and content hashes, then
   test independent browser selection and export a new editable project.

## GPU ownership while loading

VRAM may still look free while an existing worker loads CPU weights.
`assert_gpu_available.ps1` also refuses recognized live Hunyuan geometry/paint
Python workers during that interval. It ignores a shell merely mentioning a
runner filename. No process is stopped by the guard; ComfyUI queue and VRAM
checks still apply.

This preflight is not an atomic scheduler. Run owned GPU stages sequentially and
recheck after other work completes. If overlap is discovered, retain the failed
attempt and its cause before starting a fresh candidate after the owner finishes.

## Off-centre face inspection

Small full-body renders can conceal facial defects. The close-up helper accepts
paired `--target X Y Z` and `--extent` arguments in Blender world metres, plus
`--front-angle` relative to -Y. `--opposite` adds both sides. Existing humanoid
defaults remain unchanged; the receipt records the target and source hash.

```powershell
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/review_character_texture_closeups.py -- `
  C:/work/cat.glb C:/work/face-review-v1 `
  --target 0.0407 -0.224 0.307 --extent 0.18 --front-angle 40 --opposite
```

Measure these values for the actual asset. A rig pass cannot certify the
appearance of eyes, nose, muzzle or whiskers. Human acceptance remains pending.
