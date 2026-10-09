# Mesh hair from a scanned head

A stylised character's hair as sculpted mesh locks, cut from a generated head
scan, instead of a strand groom grown from parameters. The groom never
reproduced the reference's locks and read as fur in a painted world; the scan
already has them. On character-02 (2026-10-09) a Pixal3D single-view scan of
the head picture gave Arcane-like blade locks with their own painted colour
(near-black brown, caramel highlights); Hunyuan3D-2mv gave a mop of thin
tendrils, which as a mesh reads as dreadlocks.

Status: the stages below run end to end on the CPU in about 15 seconds, and
`rebuild_character.py` builds a character with them (section 4). character-02's
rebuild-v11 (2026-10-09) is the first, built on the CPU in 6.5 minutes and
installed in The Aether Wars in place of his strand groom.

## 1. Scan the head (GPU, about 2 to 4 minutes)

Use the head's front picture as a cut-out (the Hunyuan request's
`prepared/front.png` is one). Pixal3D needs about 20 GiB of free VRAM; from
Git Bash set `MSYS_NO_PATHCONV=1`.

```powershell
python scripts/generate_geometry.py $C-head-pixal3d <prepared/front.png> --seed 42 --resolution 1024
```

## 2. Conform the template to the scan (CPU, under a minute)

Pixal3D delivers figures facing +y: turn the arrays 180 degrees about z before
conforming (x and y negated), and pass the same `--yaw-deg 180` to step 3.

```powershell
& $B -b --factory-startup --python scripts/blender/export_mesh_arrays.py -- <scan.glb> $W/hair/scan.npz
py -3.12 -c "import numpy as np; z=dict(np.load('$W/hair/scan.npz')); z['verts'][:, :2] *= -1; np.savez('$W/hair/scan-r.npz', **z)"
& $B -b --factory-startup --python scripts/blender/render_mesh_view.py -- "<abs>\scan-r.npz" "<abs>\acq-front.png" "<abs>\acq-front-camera.json" --arrays
& $Torch scripts/detect_face_landmarks_dwpose.py $W/hair/acq-front.png $W/hair/dw-acq-front.json --model $DW
python scripts/conform_head_template.py $Ref/template/hm08-male.npz $W/hair/scan-r.npz $W/hair/conform.npz $W/hair/conform.json `
  --picture-landmarks $W/head/dw-front.json --template-landmarks $Ref/landmarks/dw-template-front.json `
  --template-camera $Ref/landmarks/template-front-camera.json `
  --acquisition-landmarks $W/hair/dw-acq-front.json --acquisition-camera $W/hair/acq-front-camera.json
```

## 3. Build the hair (CPU, about 15 seconds)

```powershell
py -3.12 scripts/build_mesh_hair.py --template $Ref/template/hm08-male.npz --scan <scan.glb> `
  --scan-conform $W/hair/conform.npz --scan-receipt $W/hair/conform.json `
  --head $W/head/finish/head.npz --out $W/hair/mesh --blender $B --yaw-deg 180 --triangles 30000
```

It runs, in order:

- `classify_scan_hair.py`: scan triangles outside the conformed skin, over the
  scalp or far out; never the ears, inside layers or the neck.
- `blender/cut_scan_hair.py`: those triangles, minus any the scan's texture
  paints as skin close to the skin (an ear scrap), welded, in template metres,
  with the scan's base colour.
- `transfer_mesh_hair.py`: carried onto the character's own head (`--head`),
  which is conformed from the same template: each vertex follows the skin
  under it. On character-02 the hair moved 17 mm (median) from the Pixal3D
  head onto his Hunyuan-built head. The same step puts one character's hair
  on another's head.
- `reduce_mesh_hair.py`: fast-simplification (MIT, optional dependency:
  `pip install fast-simplification`) to `--triangles`. It keeps the blades at
  60k where Blender's collapse decimator turned them into shards at 134k. The
  collapse lays some thin blades' two sides onto each other (the same three
  vertices twice, about 10% at 30-40k); those copies are dropped here, so the
  count it reports is the count that ships. A count more than 2% off the
  request is a WARNING, here and in the receipt.
- `blender/bake_mesh_hair.py`: new UVs and a selected-to-active bake of the
  full-resolution colour and a tangent normal map. The cage reaches 15 mm; at
  4 mm most rays missed the thin blades.

Outputs: `hair-mesh.npz` (verts, tris, loop_uv in the head's template space),
`hair-mesh-basecolor.png`, `hair-mesh-normal.png`, and the receipt
`mesh-hair.json` (`triangles_requested`, `triangles_shipped`, `warnings`).
character-02: 830,860 triangles cut; 30,000 requested, 26,990 shipped (the
first build asked for 60,000 and shipped 56,032).

Review: `render_painted_head.py` without `--strands` draws `hair-mesh.npz` as
a textured mesh (pass it as the hair NPZ, the base colour as the hair
texture).

## 4. The build and the game

### Freeze it with the character's inputs

`freeze_character_inputs.py --hair-mode mesh` requires the three outputs as
bundle inputs and writes `"hair": {"mode": "mesh"}` into the new recipe (a
template recipe that already says so carries its mode and `cap` block over):

```powershell
python scripts/freeze_character_inputs.py --bundle $W/rebuild-inputs-mesh-hair --hair-mode mesh `
  --recipe-from recipes/$C-open-review-<date>.json --recipe-out recipes/$C-mesh-hair-<date>.json `
  --character profiles/characters/$C.json <the usual NAME=PATH inputs> `
  hair-mesh.npz=$W/hair/mesh/hair-mesh.npz hair-mesh-basecolor.png=$W/hair/mesh/hair-mesh-basecolor.png `
  hair-mesh-normal.png=$W/hair/mesh/hair-mesh-normal.png
```

Strands stay the default: a recipe without a `hair` block builds exactly as
before (Ennix's recorded commands are pinned by a test).

### What the build does with mesh hair

- No `grow_hair_groom.py` and no `export_groom_alembic.py` (neither Alembic).
- `mesh_hair_scalp_cap.py` makes the dark scalp cap on this build's head
  (below), then `render_painted_head.py` draws the hair mesh with its base
  colour and normal map over the cap (`--scalp-cap`, `--hair-normal`; no
  `--strands`). The saved head blend holds the `hair` and `scalp-cap` objects.
- `assemble_character.py --mesh-hair` brings the `hair` object onto the body.
  `bind_assembly_to_rig.py` and the UE5 fit weight it 100% to `head`.
- `rig_ue5_character.py --plan-ignore <prefix>_hair`: the joint plan leaves
  the hair out of its measurements. character-02's hair has more vertices
  (26,100) than his body (24,731), so the plan would have taken it for the
  body; and the character's height, which sets every proportion, would have
  included hair standing above the crown. With it ignored, rebuild-v11's plan
  measured 1.727 m (v10: 1.729) and every joint landed within 3.8 mm of v10's.
- The two maps are copied beside the game FBX:
  `export/hair-mesh-basecolor.png`, `export/hair-mesh-normal.png`. The FBX's
  hair slot is the material `hair`.
- The receipt records `hair` (mode, cap, maps).

### The scalp cap

The locks have gaps, and through a gap the head's skin paint reads as bare
scalp. `mesh_hair_scalp_cap.py` (numpy and scipy, under a second) makes the
cap the strand groom makes, under the same NPZ keys: the template's `scalp`
vertex group where hair lies over it (hair within `--reach` 3 cm out along the
normal, searched in a column `--probe-radius` 6 mm wide, so the cap ends near
the hair's edge), closed over the gaps between locks (`--close` 2 passes over
the skin's neighbours), ended `--front-inset` 15 mm behind the face, lifted
2.5 mm and coloured with the median of the hair's paint (black bake misses
skipped). Options come from the recipe's `hair.cap` block (keys are the option
names, e.g. `{"front_inset": 0.035}`).

character-02: 442 triangles (the strand cap had 444), colour linear (0.0056,
0.0044, 0.0044). In review renders it cut the skin visible between locks by
44% from the front and 61% at three-quarter; under the fringe it reads as dark
roots, not bare scalp.

### The game (The Aether Wars)

`Tools/Characters/<Name>.json` says `"hair": {"mode": "mesh"}`, names the two
maps in `build` (`hair_mesh_basecolor`, `hair_mesh_normal`) and maps the role
`hair_mesh` to the FBX slot `hair`. `CharacterInstall.py` then skips the groom,
imports the maps (the normal map with its green flipped: Blender bakes
OpenGL), builds `M_<prefix>_HairMesh` (two-sided, default lit: the root colour
under the paint, the luminance capped at `look.hair_mesh_tip_luminance` so
light tips stay caramel in a low sun, a little saturation, a low rough sheen),
removes any groom component from the player and audits all of it. See the
game's `Docs/CharacterPipeline.md`.

### Triangles

The hair is in the skeletal mesh, so the rig gate counts it; groom strands
never were. character-02's first mesh-hair build (rebuild-v11) carried 56,032
triangles of hair, 127,192 in all, against the hero tier's 80,000.

Choosing a count: the same views (front, three-quarter, side, back, top-back,
plus close crops of the fringe and the crown) at each count, judged for
shards and jagged blades, scalp showing through and a smeared bake.

| Requested | Shipped | Seen |
| --- | --- | --- |
| 60,000 | 56,032 | the first build |
| 40,000 | 36,587 | clean |
| 30,000 | 26,990 | clean: fringe, tips and silhouette hold; the crown's paint a little softer (as at 36,587) |
| 24,000 | 21,326 | a stray shard on the forehead, banded smears in the crown's paint, blades merging into facets |
| 18,000 | 18,053 | the fringe is lost (a straight hairline); the reduction stops at 20,467 before the copies go |

Scalp showing between locks did not grow at lower counts (the merged blades
cover more), and the bake's black texels fell (27% at 56k, 20% at 27k).
character-02 ships 26,990 (rebuild-v12).

Over the tier, the gate fails unless the recipe records the owner's
acceptance, `budget_waiver` (CHARACTER_REBUILD.md): Mark accepted
character-02's total on 2026-10-09 ("cut the hair to what is reasonable and
accept that"), up to 100,000 triangles.
