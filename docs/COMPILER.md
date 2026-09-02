# The asset compiler

One command, no MCP server, no interactive application:

```powershell
.\scripts\compile_all.ps1
```

It compiles every recipe in `recipes\` into a gated UE5 package under
`out\<asset_id>\`, and prints a pass/fail matrix. A failing asset does not
block the others.

## What it does and why each step exists

| Stage | Script | Why |
|---|---|---|
| Stage textures | `compile_asset.ps1` | Copies textures under their shipped names *before* export, so the FBX carries a working relative reference |
| Resolve profile | `compile_asset.ps1` | Folds the asset's tri-budget waiver into the declared skeleton profile so the gate has one file to read |
| Normalize | `blender\normalize_ue5.py` | Bakes uniform scale and origin into mesh and armature *data*, rebuilds materials from declared texture paths, applies optional repairs |
| Gate | `blender\gate_rig.py` | Hard asserts against the skeleton profile. Exit 1 on violation |
| Turnaround | `blender\render_turnaround.py` | Fixed front / three-quarter / side / back, beauty and clay |
| Deformation | `blender\deform_test.py` | Poses the rig and proves the skin follows the correct side |
| Texture gate | `gate_texture.py` | Measures baked lighting, texel density, UV fragmentation |
| Package | `compile_asset.ps1` | Copies FBX and textures, writes `<asset>.ue5import.json` |

The gate runs against the **exported** FBX, not the pre-export scene. The FBX
round trip is exactly where scale and skinning quietly change, so gating the
scene you are about to export proves nothing about the file you ship.

## Skeleton profiles

`profiles\skeletons\*.json` declare the bone contract: required bones, expected
parents, permitted extras, influence cap, triangle budget.

| Profile | Spine | Twists | Fingers | Used by |
|---|---|---|---|---|
| `ue5_manny` | `spine_01..05`, `neck_01/02` | 2 per segment | 30 | field-scout-male |
| `ue4_mannequin` | `spine_01..03`, `neck_01` | 1 per segment | 30 | ninja-man |
| `mascot_biped_tail` | `spine_01..03`, `neck_01` | none | none | fox-mascot |

`ue5_manny` is used by both field-scout characters.

Bone *names* are not the contract. `expected_parents` is checked too, because a
bone called `upperarm_l` hanging off the pelvis is a coincidence, not a rig.

## The facing check

`gate_rig.py` verifies three things that no still render can show you:

1. **Skeleton facing** — the toe joint must sit ahead of the ankle in −Y.
2. **Mesh facing** — eye-material geometry must sit ahead of the head bone.
   Eyes are used because unlike a nose they survive hoods, masks and muzzles.
3. **Agreement** — if the mesh faces one way and the skeleton the other, the
   rig is 180° out: `_l` bones drive the visually right side and knees bend
   backwards. This is invisible standing still and fatal in a walk cycle.

`ninja-man` failed exactly this check. See its `repair` block.

## Tri budget waivers

An asset over its profile budget fails the gate unless the recipe records a
`budget_waiver` with a `reason` and an `approved_by`. The waiver downgrades the
failure to a warning and is copied verbatim into the shipped manifest, so an
over-budget asset is always visibly over budget rather than quietly passing.

## Adding an asset

Write `recipes\<id>.json`:

```jsonc
{
  "asset_id": "my-character",
  "kind": "humanoid",
  "skeleton_profile": "ue5_manny",
  "source": { "authority_fbx": "<absolute path to the immutable input>" },

  // One texture set per material. A body atlas plus a separate face
  // projection is common; the older single-material "textures" block plus
  // normalize.textured_material still works.
  "material_textures": {
    "M_MyCharacter_Body": { "BaseColor": "<path>", "ORM": "<path>" }
  },

  "normalize": {
    "target_height_m": 1.8,          // null to leave height alone
    "recenter": true,                // root bone to world origin, feet to Z=0
    "sk_mesh_name": "SK_MyCharacter",
    "material_renames": { "Material.001": "M_MyCharacter_Body" }
  },

  // Only for an asset whose mesh faces +Y while its skeleton faces -Y.
  "repair": { "flip_mesh_180_z": false },

  // Required if the asset exceeds a profile threshold. Both fields must be
  // present or the gate fails.
  "budget_waiver":  { "reason": "...", "approved_by": "..." },
  "texture_waiver": { "reason": "...", "approved_by": "..." }
}
```

Then `.\scripts\compile_asset.ps1 -Recipe recipes\my-character.json`.

## Importing into UE5

`scripts\ue5\import_asset.py` consumes the manifest inside the editor's Python
environment. It applies the texture settings that are easy to get wrong by
hand: sRGB off and `TC_Normalmap` for Normal, sRGB off and `TC_Masks` for ORM.

Verified against **UE 5.8.2** on 2026-08-30, headless:

```powershell
$env:RAC_ROOT = (Get-Location).Path
& "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" `
    .\work\ue5-validate\RacValidate.uproject `
    -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\import_and_verify.py" `
    -unattended -nop4 -nosplash -stdout
```

`import_and_verify.py` imports every package in `out\`, then inspects what the
engine actually built and writes `work\ue5-verify.json`. Checking the imported
payload rather than the import call's return value is the point: an import that
"succeeds" and produces a mesh at the wrong scale, or with the material
unassigned, is a failure this project has already shipped once.

Measured result, all four passing:

| Asset | Imported height | LODs | Material slots |
|---|---|---|---|
| field-scout-female | 200.0 cm | 3 | Body + Face |
| field-scout-male | 199.9 cm | 3 | Body x5 |
| fox-mascot | 199.4 cm | 3 | Body x5 |
| ninja-man | 180.0 cm | 3 | Body x2 |

Every height matches its manifest exactly, which validates the whole normalize
chain end to end. sRGB and compression verified correct on every texture.

Two engine traps this cost, both now handled:

- `FbxSkeletalMeshImportData` in 5.8 has no `use_t0_as_ref_pose` or
  `preserve_smoothing_groups`; setting either raises.
- Iterating `SkeletalMesh.materials` yields **copies** of the struct. Mutating
  them and writing the same list back is a no-op, and the mesh silently keeps
  `WorldGridMaterial` — a white character that reads as a broken export. Build
  fresh `SkeletalMaterial` structs and assign a new array instead. The
  verification also treats a default engine material as *not* assigned, because
  accepting any non-null value is how an all-white character passes a check.

### Cooking

```powershell
& "<engine>\UnrealEditor-Cmd.exe" .\work\ue5-validate\RacValidate.uproject `
    -run=Cook -targetplatform=Windows -map=/Game/Compiled/L_RacGallery `
    -unattended -nop4 -nosplash -stdout
```

**585 packages, 0 errors, 0 warnings.** All 24 project packages — 4 skeletal
meshes, 4 skeletons, 5 materials, 10 textures and the gallery map — appear in
`Metadata/ReferencedSet.txt`.

A cook only reaches your content if a map is configured. The first attempt
reported success while cooking nothing but engine shader archives, because the
project declared no `MapsToCook`. `work\ue5-validate\Config\DefaultGame.ini`
now names the gallery map and `/Game/Compiled`. UE 5.8 writes cooked output
into the **Zen store** (`zenfs.manifest`), not loose `.uasset` files, so verify
by reading `ReferencedSet.txt` rather than by listing directories.

### In-engine screenshots

`scripts\ue5\capture_gallery.py` does **not** work from a commandlet:
`SceneCapture2D` needs a live render thread and gets none, so every frame comes
back black. The script grid-samples its own output and refuses to write black
frames rather than leaving misleading evidence on disk. Run it from an
interactive editor session (Window > Python console) for engine screenshots.
The numeric verification in `work\ue5-verify.json` needs no viewport and is the
stronger proof regardless.


## Is everything on the UE5 skeleton?

Not uniformly, and the difference is deliberate:

| Asset | Skeleton | Manny animation |
|---|---|---|
| field-scout-male | UE5 Manny (86 bones) | direct, no retarget |
| field-scout-female | UE5 Manny (86 bones) | direct, no retarget |
| ninja-man | UE4 Mannequin (75 bones) | needs the stock UE4→UE5 IK Retargeter |
| fox-mascot | custom 26-bone mascot | IK Retargeter, tail excluded from the chain map |

The ninja was exported from Auto-Rig Pro with the UE4 preset: `spine_01..03`,
one twist joint per segment, `neck_01` only. UE5 imports that skeleton as a
first-class citizen, and Epic ships the UE4-Mannequin-to-Manny retargeter, so
this is a supported configuration rather than a defect.

Converting it to Manny would mean inserting `spine_04`, `spine_05`, `neck_02`
and the second twist joints, then redistributing the existing spine weights
across the new chain. That is real rig surgery with a real chance of quietly
degrading deformation, in exchange for skipping a retargeter asset that already
works. It has deliberately **not** been done. Say the word if you want strict
uniformity and it can be built as a gated, deformation-verified transform.

`retarget_note` in each manifest states which case that asset is.

## Texture quality

`gate_texture.py` measures four things and records them in the manifest:

| Measure | What it catches |
|---|---|
| baked-light correlation | Directional shadow painted into the albedo (rule I7) |
| texel density (texels/cm²) | An atlas too coarse for the subject's surface area |
| texel density ratio | A sharp face on a blurry arm |
| UV island count | Per-patch confetti layouts, where every island edge is a seam |

A fifth number, `skin_chroma_on_clothed_fraction_advisory`, is reported but
never gates: it cannot tell a face stamped on a trouser leg from a character
who simply wears earth tones, and the fox reads 34% purely because orange fur
resembles an orange face.

Thresholds live in the skeleton profile. Every current asset needs a
`texture_waiver` in its recipe to pass, which is the point: the debt is visible
in the shipped manifest instead of silently absent. See
[ESCALATE-textures.md](ESCALATE-textures.md) for what is actually wrong and
what fixing it requires.

## LODs

LODs are generated by **UE5's own mesh reduction** at import time, driven by
the `lods` block in the manifest (LOD0 100%, LOD1 50%, LOD2 25%). Blender's
Decimate modifier is never used: it produces long skinny triangles, which are
the direct cause of the faceted shading this pipeline exists to eliminate.

## Diagnostics

Not part of a compile run; reach for these when something looks wrong. The
debugging order in the brief is the right order to use them in.

| Script | Answers |
|---|---|
| `blender/render_matid.py` | Which material is on this polygon? |
| `blender/render_closeup.py` | beauty / albedo / checker / clay around one bone |
| `blender/render_uv_debug.py` | Which atlas coordinate does this pixel come from? |
| `blender/diagnose_material_regions.py` | Where on the body does each material land? |
| `blender/export_uv_regions.py` | Per-triangle UV, region, normal, area as `.npz` |
| `blender/measure.py` | World bounds and bone positions |
| `inspect_texture.py` | Atlas statistics and a downscaled preview |

`render_closeup.py`'s albedo pass is the fastest way to separate a texture
problem from a lighting one: if a shadow is visible there, it is painted in.
Note that `render_uv_debug.py` writes an sRGB-encoded PNG, so linearise the
channel values before treating them as UV coordinates.

## Production stage: making an accepted asset game-ready

The assets in `out/` are correct likenesses and poor game assets: ~70k
triangles of near-uniform density, no normal map, and an atlas of 300-900 tiny
UV islands. `scripts/build_production.py` keeps the likeness and fixes the
rest, then re-runs every gate the source asset already passes so a regression
cannot ship quietly. Nothing in it generates art — the albedo is the accepted
albedo, resampled.

```powershell
python scripts\build_production.py field-scout-female
python scripts\promote_production.py field-scout-female
```

`promote_production.py` writes `out/<asset>-production/` as a sibling of the
authority, never over it, so both import into UE5 and can be compared.

### Heal before you judge

An exported FBX splits a vertex at every UV and normal seam, so re-importing
one reads as hundreds of disconnected shells. field-scout-female imports as 664
components with 17,740 non-manifold edges; welding at 0.1 mm makes her a single
closed manifold with none. Every earlier "this mesh is too broken to
retopologise" verdict was measuring the import artifact, not the mesh.

Weld first, then judge, then repair — in that order. Welding harder is not
better: at 1 mm the male gains 67 edges shared by three or more faces, because
distinct surfaces get merged.

### Remesh per shell, and repair only on refusal

QuadriFlow signals refusal as a log warning plus `CANCELLED`, never an
exception, so the only reliable check is whether the topology actually changed.

Whole-mesh remeshing only works on characters that heal into one shell.
field-scout-male splits into 11 and ninja-man into 29 — eyes, buttons, paired
straps that were never joined to the body — and QuadriFlow refuses the lot. Per
shell it accepts nearly all of them.

Two rules matter as much as the split:

- **Repair is a rescue, not a preparation step.** Hole-filling, surplus-face
  removal and bowtie tearing are only applied to a shell QuadriFlow has already
  rejected. Running them first is actively harmful: fox-mascot remeshed cleanly
  at 69,545 -> 23,002 triangles until the repair ran ahead of it, after which
  QuadriFlow refused its body outright.
- **Small shells are never remeshed.** Below the floor a shell is kept
  verbatim. These are the eyes, buttons, straps and hair cards: small in area,
  large in what the eye reads, and a proportional budget rations them to
  nothing. Remeshing fox-mascot's eyes into forty quads is what turned them
  into speckled fur.

A shell that is still refused after repair is kept at full density rather than
dropped or decimated, and the triangles it costs are recorded rather than
hidden.

### Bake rays must be short

The transfer bakes from the original onto the retopo with
`use_selected_to_active`. The ray offset only has to cover the gap between the
two surfaces, which is millimetres. The 2 cm default was far enough for a ray
leaving the remeshed scalp to pass straight through the hair and land on the
skull — which is why ninja-man baked a pale blotchy head and fox-mascot baked
fur across its eyes. 4 mm of extrusion and an 8 mm maximum ray distance fix
both.

### Weight the UV charts at the face

`pack_islands` rescales every island by one common factor, so relative island
sizes set *before* packing survive it. Scaling a region's UVs by `s` multiplies
its texel density by `s²`, and the cost is shared by every other region through
that common factor — so it matters enormously which region you aim at.

A uniform pack hands every region the same texels/cm², so the head gets area in
proportion to its face count while the shipped art came from a dedicated 1024
head projection at roughly 721 texels/cm². Rendered close up, the result has no
mouth, no nose, and smeared blue blobs where the eyes belong.

Weighting the bone-derived `head` region costs a fortune: skull, hair and neck
all weight to `head`, which is 37.6% of the sheet. The facial skin is already
authored as its own material, and reading the region from there makes the
target 5.9% of the sheet — the same boost, six times cheaper. Assets with a
single body atlas have no `face` region to aim at and fall back to a gentler
`head` weight.

### Clamp bone influences in Blender, not in the engine

Interpolating weights from the original blends every source vertex the transfer
samples, so vertices near joints pick up seven or eight bones where the
original never exceeded four. UE5 imports four and renormalises the rest away
silently — changing the deformation *after* it was tested. Clamp and
renormalise in Blender so what is tested is what ships. Unweighted vertices are
a hard failure.

### Traps

- `Image.save()` resolves a relative `filepath_raw` against Blender's own
  working directory, not the shell's, and writes nothing when that misses —
  while still returning success. The stage reported three baked maps and
  produced none. Resolve output paths up front.
- fox-mascot carries non-finite vertex coordinates in its small shells.
  Whole-mesh remeshing used to erase them as a side effect; preserving small
  shells keeps them, and they poison everything downstream — the silhouette
  grid casts NaN to int, and the KD-tree returns `None` for the nearest vertex
  to a NaN point, surfacing as a `TypeError` a hundred lines later. Strip them
  during healing.

### Bake each material from what it actually uses

Only the body is textured. Every character builds its eyes out of flat-coloured
materials -- fox-mascot has four (`EyeOutline`, `EyeIris`, `EyePupil`,
`EyeHighlight`), field-scout-male has four, ninja-man has one -- and there is no
eye texture on disk because none is needed.

That leaves two ways to get it wrong, and the pipeline hit both:

- Handing every material "the only texture there is" bakes body fur onto the
  eyeballs. The eyeball geometry survives the remesh perfectly; it just arrives
  painted with flank fur.
- Leaving an untextured material alone bakes it black, because an `EMIT` pass
  through a Principled BSDF emits nothing.

Each material is now baked from whatever it actually uses: the mapped texture,
else its own image node, else its Principled base colour. `retopo.json` records
which, per material.

### Three ways to build one, and how the stage picks

Not every character can be reduced, and pretending otherwise ships something
worse than the input.

1. **Whole mesh.** One continuous quad field across the character, and the best
   result when QuadriFlow accepts it. field-scout-female and fox-mascot take it
   and drop by two thirds.
2. **Per shell.** For a character that heals into many disconnected shells and
   is refused whole. field-scout-male takes this.
3. **Passthrough.** Keep the geometry AND the UV layout exactly as authored,
   and do everything else: transfer the art, bake ambient occlusion, clamp the
   weights. For a character whose every reduction measures worse than its
   original. ninja-man takes this, by explicit decision recorded in
   `STRATEGY` in `scripts/build_production.py`.

Passthrough keeps the original UVs on purpose. Re-unwrapping a mesh that was
not remeshed is a regression -- the semantic layout is built for a quad field,
and on triangle soup it cost ninja-man half his texel density. It also skips
the normal map, because with no denser surface to capture there is nothing to
put in one, and it bakes the mesh against itself rather than selected-to-active,
which against a coincident copy bakes fully-occluded AO and a black albedo.

### Results, 2026-08-31

| Asset | Triangles | Mode | Deviation p99 | Influences | Maps |
|---|---|---|---|---|---|
| field-scout-female | 70,000 -> **40,232** | whole | 1.8 mm | 7 -> 4 | BaseColor, Normal, AO |
| field-scout-male | 67,907 -> 67,939 | passthrough | 0.5 mm | 8 -> 4 | BaseColor, AO |
| fox-mascot | 69,545 -> **48,042** | whole | 3.4 mm | 7 -> 4 | BaseColor, Normal, AO |
| ninja-man | 54,220 -> 54,341 | passthrough | 0.04 mm | 7 -> 4 | BaseColor, AO |

Two geometry repairs run inside this stage, both opt-in per asset because the
geometric description of each fits assets that are correct as they are:

| Asset | Repair | Measured |
|---|---|---|
| field-scout-male | eyeballs set back until they stop breaking the head's silhouette | 46.5 mm |
| fox-mascot | eye plates held out of the remesh, then boundary loops capped | 960 tris held, 181 -> 0 boundary edges |

Both were reported by a reviewer at close range and were invisible to every
gate here; `docs/DEFECTS-CLOSEUP-REVIEW.md` has the evidence and the two false
starts that preceded each fix.

Static props go through this same stage with `--kind static_prop`, which turns
off weight transfer, the influence cap, the armature modifier and the semantic
UV charts, and leaves healing, unwrapping, atlas sizing, baking and export
alone. `docs/PROPS.md` covers the route and what differs; the first asset
through it is `office-chair`, 6 materials and 5,464 triangles in, 1 material
and 5,336 out.

All four pass the retopology, texture, rig and deformation gates, and all four
are promoted to `out/<asset>-production/`. The authorities are untouched.

Verified in **UE 5.8.2**, headless, beside the originals: eight packages, zero
failed checks, every height within tolerance, 3 LODs each, and one material
slot per production asset against two to five on the authorities. Cook: **546
packages, 0 errors, 0 warnings**, with 23 production packages in
`Metadata/ReferencedSet.txt`.

### The face gets a chart sized by what it costs

`pack_islands` rescales every island by one common factor, so relative sizes
set before packing survive it, and scaling a region by `w` multiplies its
density by `w²` while growing the sheet by `share*(w²-1)`.

Fixing `w` gets that backwards. field-scout-female's face is 9.7% of her
triangles and ninja-man's is 1.6% of his, so one number either bankrupts her or
does nothing for him. Fixing the COST instead -- `w = sqrt(1 + 0.12/share)` --
gives her 1.50 and him 2.63, and every other region pays about 6% of its
density either way.

Finding the face at all needs two mechanisms. Where it is authored as its own
material, use that. Where it is not, sample the accepted albedo at each head
triangle and test for skin: red strongest, blue weakest, desaturated. Colour
alone is not trustworthy -- fox-mascot is orange from nose to tail -- so the
result is only used when it selects a MINORITY of the head. On ninja-man that
is 706 of 25,432 head triangles; on fox-mascot the test reports nearly all of
them and is discarded.

### Never magnify past what the source holds

Texel density is not a number to maximise. Give a region more texels than its
source has and the result is not more detail, it is the source's own pixels
enlarged -- which reads exactly as "this has been upscaled".

Two ceilings, both measured from the accepted art rather than chosen:

- **The face chart** is boosted only where the art has more detail on the face
  than on the body. field-scout-female's face comes from a dedicated 1024
  projection at 721 texels/cm2 against a 306 body, so 2.2x more really is there
  to recover. field-scout-male's face and body share ONE uniform 4096 atlas at
  313, and the same boost put his head at 456 -- half again more than the
  source has -- while dropping his torso to 198 to pay for it. With the ceiling
  applied his head sits at 287 and his body at 241-318, all under the source.
- **The atlas itself** steps down when the requested size cannot be filled.
  fox-mascot's albedo is a 2048 map over a large furry surface -- 43
  texels/cm2 -- and a 4096 sheet would have delivered 198, magnifying his art
  fourfold for four times the memory. He ships at 2048 and 13.5 MB instead of
  27 MB, with the same picture.

For a passthrough the atlas simply matches the source texture's own size.
Estimating density from an original UV layout is not safe: those layouts
overlap and mirror charts, which inflates the summed UV area. That reading made
ninja-man look like he was being handed 482 texels/cm2 when the gate measured
146, and stepping him down on it cost three quarters of his resolution.

### A crashed stage used to report success

Blender exits 0 even when the script it was handed raised. The driver saw a
zero exit, read the `retopo.json` left behind by the PREVIOUS run, and reported
PASS with stale numbers -- which is how a build that died on an
`UnboundLocalError` looked healthy. The report is now deleted before the stage
runs and required back afterwards, and stderr is scanned for tracebacks.
