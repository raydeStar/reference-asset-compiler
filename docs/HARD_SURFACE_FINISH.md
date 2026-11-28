# Finishing hard surfaces

*Type: workflow reference*

Two stages paint a static, hard-surface part from its own geometry: ironwork, plate, machine housings, kit pieces. `bake-surface-maps` asks Blender what every texel's surface is like. `hard-surface-finish` paints from the answer on the CPU. The part leaves with a base colour, a tangent-space normal and a packed occlusion / roughness / metal map.

This is surfacing for geometry that is already approved. It acquires nothing. The rule in `CLAUDE.md` stands: image reconstruction begins with image-conditioned AI geometry, and Blender does not rebuild a reference by script. See [the note on the first kit](#the-kit-this-was-first-used-on).

For characters, use the [character surface workflow](CHARACTER_SURFACE_WORKFLOW.md) and the [material sweep](MATERIAL_SWEEP.md) instead. Those keep an approved paint and change how it answers light. This stage replaces the surface.

## Run it

The part needs a unique UV0 inside 0..1 and should be triangulated the way it will ship.

```powershell
$env:RAC_BLENDER = '<path to blender.exe>'
rac run-stage bake-surface-maps --source part.glb --textures maps-recipe.json --output maps.npz --report maps.json
rac run-stage hard-surface-finish --source part.glb --textures finish-recipe.json --output part-finished.glb --report part-finished.json
```

`maps-recipe.json`:

```json
{"schema": "rac.surface-maps-recipe.v1", "source_sha256": "<of part.glb>", "resolution": 4096}
```

`finish-recipe.json`. The class names on the left are the ones `maps.json` lists under `class_names`; the ones on the right come from the profile:

```json
{
  "schema": "rac.hard-surface-recipe.v1",
  "source_sha256": "<of part.glb>",
  "maps": "maps.npz",
  "maps_sha256": "<of maps.npz>",
  "classes": {"M_Deck": "tread_plate", "M_Panel": "old_teal_paint", "M_Rail": "palm_rail"},
  "seed": 4283,
  "masters": true
}
```

Both stages refuse an existing output and write a receipt with the hashes of everything they read. Open the result in the consumer and under a moving light before promoting it. A receipt says what was encoded, not how good it looks.

## What the bake records

For every texel, in the part's own space and in metres: where it is, which way it faces, how open it is at 30 cm, 12 mm and 6 cm, how near an edge it is, and what it is made of. The class is the face attribute `cls` if the mesh has one, otherwise the material slot.

The bake accepts a `.glb` or a `.blend` (name the mesh with `"object"`). A mesh may carry three optional annotations, which only a `.blend` can hold:

| Attribute | Domain | Meaning |
| --- | --- | --- |
| `axisv` | face, vector | Which way the member runs: the grain of a rolled section. |
| `rnd` | face, float | 1 on tubes and domes, which have no rim to wear. |
| `dome` | vertex, float | 0 at a rivet's foot, 1 at its crown. |

Without them the painter works these out per UV island: an island whose normals disagree is round, its longest direction is its grain, and a small round island is a fastener head.

Small loose parts that bulge are listed as fasteners. Rain picks rust up there and lays it down the upright face below.

## What the painter does

Every layer is a function of the baked maps, in physical units, so wear follows the geometry and nothing follows a UV seam.

- **Layers in order.** Bare iron, red-oxide primer, paint with real thickness at the chip edge, then rust, grime, dust and handling marks.
- **Rust is a crust.** It stands proud of the metal, scabs and pits, and the normal map carries that. Scabs are never smaller than three texels.
- **Noise sized to the texel.** A face painted at low density is given noise it can hold. It goes soft there, not grainy.
- **Marks that look made.** A scratch is a few centimetres long and lies at its own angle. Polish follows hands, feet and wheels and varies along the way.
- **Plain values.** A surface is metal or it is not. What is in between is a layer over it.

The profile [`profiles/materials/hard-surface-ironworks.json`](../profiles/materials/hard-surface-ironworks.json) holds the palette and the classes. Each class has one of six kinds:

| Kind | For |
| --- | --- |
| `tread_plate` | Plate that is walked and driven on. Takes `tread` options from the recipe. |
| `plain_plate` | Smooth plate that is walked on. |
| `palm_rail` | A rail or rung a hand rests on. |
| `worn_iron` | Unpainted iron fittings and fastener heads. |
| `bronze` | Bronze fittings, with tarnish and verdigris. |
| `coated` | Paint over primer over iron. Names a `coat` and a `faded` colour and a `level` of wear. |

A different kit gets a different profile: copy the file, change the palette and classes, and name it in the recipe with `"profile"`.

### Recipe options

| Key | Meaning |
| --- | --- |
| `seed` | Two parts with different seeds never wear alike. Give every part its own. |
| `tread.pattern` | `lozenge` (default) or `none`. |
| `tread.wheel_lines_y_m` | Where wheels run, along +X. Their strength repeats over the part's length, so the same plate laid end to end joins up. |
| `tread.stamp` | `{"text", "origin_m"}`: a foundry die struck into a plain panel. |
| `fasteners` | `[[x, y, z, nx, ny, nz, radius], ...]` in the maps' space, in place of the ones the bake found. |
| `encode` | `png` (default) or `review`: JPEG colour and mask with a lossless normal, for a consumer with a size ceiling. |
| `masters` | Also write the three maps as PNG files beside the output. |

## What a mesh has to do for this to work

These are the UV author's decisions, not the stage's. Each was learned on the first kit.

- **Lay UVs out in metres.** One island per face or tube at one scale. A face scaled to fill an atlas tile is stretched, and the stretch shows as streaks.
- **Share texture space only between fasteners.** Two members that share an island wear identical marks, and side by side that reads as a copy.
- **Give buried faces almost nothing**, and cut long members into several islands, or one long strip sets the scale of the whole atlas.
- **Model the rivets.** A normal-mapped rivet has no depth in stereo.

## Limits

- One atlas, one material. Tiled and trim-sheet UVs are refused.
- Static meshes only. Skins and morphs are not carried.
- The maps are in Blender's axes (Z up). Gravity effects assume the part is modelled upright.
- Dry. Rain and wetness belong to the scene.
- A texel is as fine as the atlas allows. At arm's length in a headset a 4K part still wants a tiling detail-normal layer in the engine material.
- The painter uses `torch` for its noise lookups when it is installed and SciPy when it is not. The two agree to within rounding, not bit for bit.

## The kit this was first used on

The stages were written for the Frastown West Berth kit on 23 November 2026 and reproduce its published textures exactly. That kit's geometry was built by script from scene measurements, not acquired from an image. The owner reviewed the work the same day and said the pipeline had been skipped. The kit is evidence that the surfacing works. It is not a precedent for how geometry is made. See [DECISIONS.md](DECISIONS.md) and the [measured record](evidence/frastown-surface-pass-b02-20261123.json).
