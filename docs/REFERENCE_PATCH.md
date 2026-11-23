# Registered reference repairs

*Type: reference*

For the complete operating sequence and review checklist, start with the
[canonical character surface workflow](CHARACTER_SURFACE_WORKFLOW.md).

`reference-patch` maps reviewed, image-conditioned repairs onto an acquired GLB.
`prune-payload` then removes abandoned embedded images and materials without
re-encoding the images still in use. Both are CPU stages in `rac run-stage`.
They produce candidates and evidence; neither approves an asset.

## Repeatable repair loop

1. Start with the approved acquired mesh. Diagnose the defect in albedo, neutral
   clay, material IDs and lit views. A material boundary is not necessarily a
   geometric boundary. Do not extrude every segmentation edge.
2. Capture registered orthographic guides from that exact mesh. Include enough
   front, side and reverse coverage to cover the entire repair, with margin
   beyond the visible area. Retain camera coordinates, hit/depth arrays and hashes.
3. Use the concept and those registered guides to acquire edited references.
   Retain prompts and image hashes. Keep silhouettes and registration fixed.
4. Check the UV footprint before baking. More atlas pixels do not help when the
   relevant island occupies a tiny corner. Repack and rebake an isolated region
   if needed, retaining per-triangle position and weight correspondence.
5. Project a bounded repair. Review every affected side, then use
   [material-sweep](MATERIAL_SWEEP.md) when semantic surface classes need their
   own response. Check under moving lights and in the actual consumer.
6. Preserve the candidate and rejection reasons. Recheck the packed native
   source, exported pose and deformation before advancing the next asset gate.

```powershell
rac run-stage reference-patch --source acquired.glb --output patched.glb `
  --report patch-receipt.json --textures patch-recipe.json
rac run-stage prune-payload --source patched.glb --output review.glb `
  --report payload-receipt.json
```

Use new output and report paths. The source, recipe and every donor/guide are
SHA-256 bound. A recipe cannot silently apply to a different source revision.
The implementation requires NumPy, SciPy, Pillow and OpenCV. Blender is used for
guide capture and visual review, not for these two CPU mapping commands.

## Recipe and guide contract

The recipe schema is `reference-asset-compiler.reference-patch-recipe.v1` with
`source_sha256`, a nonempty `acquisition_provenance` description, and `patches`.
Each patch identifies a unique material name and an atlas `size` (16–8192).
All patches on one material must use the same size. Optional controls:

| Field | Meaning |
|---|---|
| `bounds` | Two mesh-local XYZ corners restricting the repair. |
| `feather_m` | Distance over which the repair fades at those bounds. |
| `mirror_x` | `-1` or `1`: sample that side's donor for both sides. Review intentional asymmetry first. |
| `two_sided` | Allow a registered donor on inward-facing acquired triangles. |
| `retain_normal` | Fraction of the previous normal slope retained in the repair. |
| `response` | Optional `roughness`, `metallic`, `specular` values in 0–1. |

Every view supplies `image`, `image_sha256`, `guide`, `guide_sha256`, `center`,
`axis`, and `width`. Paths are relative to the recipe. `axis` points from the
subject toward the camera; `up` defaults to mesh-local Y. `width` is the square
orthographic camera span. Coordinates and distances are in the mesh's local
metre convention, not Blender world space. Bake or explicitly account for
transforms before capture; this stage does not infer node transforms.

A guide is an NPZ with same-shaped `hit` and `depth` arrays. `hit < 0` means no
surface. Valid depth is `(surface_position - center) dot normalized(axis)`.
Image rows run top to bottom. The view's optional `visibility_tolerance_m`
defaults to 0.006. It should accommodate raster precision, not unrelated layers.
`relief_m` defaults to 0.00004 and derives modest normal detail from the donor's
high-frequency luminance. This is an art-directed approximation, not measured
surface depth. Inspect printed markings and shadows before retaining that relief.

For skin-only guides against a neutral backdrop, optional per-view
`foreground_chroma_min` rejects pixels whose maximum-minus-minimum RGB channel
is below that threshold (0..255). `foreground_dark_max` can retain dark brows
and lashes below its maximum-channel threshold. Rejected donor pixels take
the nearest valid donor color; the camera and depth visibility remain fixed.
Both default to zero. Do not enable this on neutral-colored garments or metal.

A whole-material patch can specify `fill_unseen_m`: projection gaps take the
nearest confidently observed surface color only within that many metres.
The default zero preserves existing color in unseen regions. Scoped patches
with bounds cannot enable this fallback; it must not leak across a deliberate
repair boundary. Neither option fixes displaced facial landmarks: review the
registered images and four-view model after mapping.

Core, embedded textures, triangle geometry, normals and untransformed UV0 are
required. Use unique UV islands for independent detail. Mapped materials are
resampled to the requested size; untouched materials are retained. Normal maps
and roughness/metalness/specular response are linear data. Specular strength is
stored in response alpha through `KHR_materials_specular`. The stage retains
geometry, accessor data, skinning, facial morphs and clips unchanged, and checks
those structures before writing. Its receipt leaves visual acceptance pending.

`prune-payload` keeps accessor indices, sparse morph bytes and all retained
buffer views intact. It supports a conservative extension allowlist and rejects
unknown extensions, external buffers and non-core embedded image formats rather
than guessing their references. It is payload cleanup, not mesh reduction or
texture compression.

## Raider exercise, November 5–6, 2026

The current work is under `work/raider-polish-20261105/`. The original Field Pouch
authority is preserved. `tailoring-recipe.json` records the sleeve/cuff repair;
`cuff-recipe.json` supplies four views after the isolated cuff UV repack. The
repack increased occupied cuff texels from 21,389 to 1,383,168 while preserving
triangle positions and skin weights. These local work recipes include their
actual source and donor hashes; generated atlases are not repository fixtures.

The earlier `finish-assignments.json` and `finish-profile.json` describe the
upstream material sweep. They cannot be rebound blindly to the later cuff UVs.
Head, mouth, collar and skin-weight repairs remain recorded asset-specific steps;
the entire polish pass is not an unattended one-command character generator.

`ear-recipe.json` is a second regional exercise of the same mapping stage. The
damaged ear was replaced with the intact acquired opposite ear, its root fitted
and welded, and its UVs separated before painting. The built-in `image_gen` edit
uses registered color and clay guides. Its saved output is
`work/raider-polish-20261105/references/ear-right.png`; the complete prompt is
`references/ear-right.prompt.txt` under that work directory. `ear-patch03`,
`ear-uv01`, `ear-paint01`, and `ear-finish02` retain the geometry, UV, mapping and
local material-response receipts. Geometry cleanup remains necessary when a
painted seam is actually a folded surface.

Current checkpoint: `review-candidate04/Raider.glb` and packed
`review-candidate04/Raider_Native.blend`. See the
[quality-pass evidence](evidence/raider-quality-20261106.json) for exact hashes,
checks, retained failures and next gates. Studio renders and static diagnostic
poses are evidence for further review. Current Framewright lighting, natural
motion and cooked UE acceptance remain open. No AAA or production-ready status
has been assigned.


The [Raider replay guide](RAIDER_POLISH_REPLAY.md) records the demonstrated
byte-identical candidate05 collar repair and distinguishes reusable RAC mapping
from asset-specific surface restoration and weight correction.
