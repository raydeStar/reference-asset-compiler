# Ennix: open-tool review build, 2026-10-07

This is an editable review candidate, not a production character. The original
illustration remains the artistic authority. Existing Hunyuan acquisition is
explicitly permitted by Mark; all new asset processing in this pass uses open
tools. No Auto-Rig Pro, InsightFace, new image generation or model inference is
needed to rebuild. Unreal is the existing delivery target, not an open-source
dependency or a geometry-generation tool.

## Selected files

Workspace: `work/ennix-character-v1/rebuild-proof-v3/`.

- `rigged/Ennix_Rigged.blend`: packed editable body, 86-bone skeleton, 34 facial
  controls, eyes, actual teeth/tongue, and native strand hair.
- `pose/Ennix_Held_Inspection.blend`: relaxed held inspection pose. The two-second
  action is held still, **not a moving idle**; bind data stays intact.
- `rigged/Ennix_Body_Face.fbx`: skeletal body and facial controls; hair travels
  separately in `export/Ennix_Groom.abc`.
- `pose/held-*.png`, `pose/face-*.png`, `assembly/{front,side,back,top}.png`:
  fixed views and facial stress checks.
- `visual-validation/reference-comparison.png`: original beside the candidate.
- `build-receipt.json`, `repeatability.json`, `semantic-canonical.json` and
  `export/`: hashes, commands, build/deformation/import evidence.

The second final rebuild is `rebuild-proof-v4`. Earlier `finish-v*`, `character-v*`
and `rebuild-proof-v1/v2` are retained experiments, not the selected delivery.

## Rebuild offline

Verified tool versions: Blender **5.2.2 LTS d13f752e3b9c**, Python **3.12.7**,
NumPy **2.1.3**, SciPy **1.15.1**, Pillow **10.4.0**. The render workstation used
an RTX 4090 and OptiX. The Blender scripts use factory startup, not installed
commercial add-ons. GPU rendering is configured explicitly in the scripts;
`rebuild_ennix.py --device CPU` renders every review image on the CPU instead,
which is slower but leaves the GPU free. `rebuild-v10` was built that way in
390 s (v9 on the GPU: 339 s).

The frozen input bundle is `work/ennix-character-v1/rebuild-inputs/`: 26 files
(85.47 MiB) for recipe `20261009`, which added the left head guidance
(`head-left.png`) for the face-paint review. It includes the acquired body, conformed template, original
reference, retained inferred witnesses, landmarks, and CC0 oral meshes. Large
inputs are deliberately outside Git. Keep the bundle alongside the repository
or take it from the local delivery package; a source-code checkout alone is not
a claim that these binary inputs can be reconstructed from nothing.

From the repository root, choose a **new** output directory:

```powershell
py -3.12 scripts/rebuild_ennix.py `
  --inputs work/ennix-character-v1/rebuild-inputs `
  --recipe recipes/ennix-open-review-20261007.json `
  --out work/ennix-character-v1/my-fresh-rebuild `
  --blender 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
```

The runner checks every input hash before starting. It rewrites only disposable
path pointers, reduces the acquired outfit **before** painting, registers and
paints from the retained images, repairs the head/neck, grows seeded hair, binds
the measured skeleton, exports, and retains the gates. Per-stage logs, versions,
script hashes, arguments and output hashes are saved. It refuses an existing
output directory. A recorded budget failure can coexist with a completed
**review** build; it never makes `production_ready` true.

`scripts/build_ennix_review.py` is the historical head-only experiment. It is not
the current full-character entry point.

## Face-paint refinement (recipe `ennix-open-review-20261009`)

`scripts/refine_ennix_face_paint.py` runs right after `refine_ennix_surface.py`
when the recipe has a `face_paint` block, and the head renders, `head.blend` and
everything after it use `face-paint/head_basecolor.png`. The surface stage's
`paint/head_basecolor.png` stays as the "before". The guidance pictures cap the
face's detail; this pass changes colour and shading only.

- **Regions** come from the front guidance's 68 DWPose points, mapped onto the
  conformed head through the conform registration (each landmark is the
  nearest texel the front picture sees). The jaw line runs through points 4-12;
  its ends come from the template's ear group (the jaw angle under each lobe,
  then up in front of the ear), because points 0-3 and 13-16 outline the cheeks.
  Lines are corner-cut so bands along them have no kinks.
- **Colours** are measured at landmark probes on the guidance and on the texture
  alike: blush against plain lower cheek, stubble against plain skin, hair
  against forehead, ears and mid-neck against plain cheek. Every measurement
  lands in `face-paint/face-paint-receipt.json`.
- **Blush:** low-pass a* above plain cheek is spread over 8 mm and soft-capped at
  `blush_keep` (0.6) of the guidance's measured cheek redness, along the
  guidance's own blush direction in L*a*b*, only for hues redder than skin.
- **Stubble:** moustache, soul patch, chin, jaw, under-jaw and sideburns darken
  to plain skin times the guidance's measured stubble tint where the paint is
  lighter. Where the front picture painted squarely its own stubble is already
  there and stays (`front_keep`); the paint's lips need not sit on the
  picture's landmarks. Beyond the front-projected face the low-pass is replaced,
  so old hard-edged bands go, and a seeded 3D hair grain (zero mean; `grain`
  amount 0 turns it off) gives those areas the picture's stipple.
- **Hairline:** the groom's own root rules (`hairline_above_eyes`,
  `temple_behind_eyes`, `sideburn_roots` mirror `grow_hair_groom.py`) plus a ray
  test against the hair shell find the scalp under the roots. It takes the
  guidance's hair colour, fading out across a rounded hairline.
- **Ears and neck:** one L*a*b* offset each. The neck is measured at mid-neck,
  clear of the jaw's cast shadow, which the render lights in again.

Review sheet: the same groom, geometry, lights and camera, rendered with each
texture beside the guidance (front, painting for three-quarter, left):

```powershell
py -3.12 scripts/build_face_paint_review.py work/ennix-character-v1/<build> `
  work/ennix-character-v1/<build>/face-paint-review `
  --blender 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
```

`scripts/preview_head_texture.py` shows head textures unlit on the conformed
head (front, three-quarter, side, and the front in the guidance's own frame) in
seconds, for tuning a paint stage between renders. Its bald views are tuning
aids, not review images.

## Hero-tier budget (recipe `ennix-open-review-20261010`)

Ennix is gated as a **hero** (profiles/triangle-budgets.json: about 70,000, at
most 80,000 at LOD0, groom strands excluded) instead of the skeleton profile's
flat 20,000. Recipe `20261010` names the tier (`character_tier`) and replaces
the uniform `body_review_triangles: 120000` with a `body` block: garment 48,000,
hands 6,000, hands beyond |x| 0.80 m along the T-pose arms. Everything else
(inputs, head, groom, face paint, rig) is unchanged from `20261009`.

- **Where the triangles were.** The acquisition's preserved hands are 890,490 of
  its 1,326,239 triangles; past |x| 0.80 m the density jumps from about 130 to
  6,800 vertices per centimetre slab. The uniform 120k left 28,920 on the hands
  and 91,173 on the garment.
- **How it is cut.** `prepare_ennix_body.py --hand-triangles` collapses the
  hands to their count while the garment is held still, then the garment while
  the hands are held still, both by quadric error alone. The receipt
  (`body/body-preparation.json`, `reduction`) records the counts and, with
  `--measure-samples`, the distance from 40,000 source vertices per region.
- **Measured on the CPU** (the same stage, outside a full build): hands 5,761,
  garment 48,238. At p99 the garment sits 0.32 mm from the source (folds and
  hems 0.35 mm, outline 0.33 mm, maximum 0.69 mm); the 120k body was 0.16 mm and
  a uniform 54k 0.38 mm. The head parts are 17,028 (head 8,748, teeth 7,120,
  tongue 448, scalp cap 432, eyes 280), so the character should land near
  70,500 before the neck overlap is cleared. Body paint coverage is unchanged
  (70.5% against 70.3%).
- **Gates.** `rebuild_ennix.py` passes the recipe's tier to `gate_rig.py` and now
  gates the UE5 game export (`export/gate-rig-ue5.json`) as well as
  `rigged/Ennix_Body_Face.fbx`.
- **Built: `work/ennix-character-v1/rebuild-v9`** (the runner's default recipe
  since then), with `--manny-dir work/ennix-character-v1/rig-ue5`, 339 s. It has
  **70,748 triangles**: outfit and hands 53,720 (garment 48,238, hands 5,761),
  plus the unchanged 17,028 head parts.
  - Both strict gates pass at the hero tier with no failures or warnings:
    `export/gate-rig.json` (`rigged/Ennix_Body_Face.fbx`) and
    `export/gate-rig-ue5.json` (`export/Ennix_UE5.fbx`).
  - All five deformation checks pass.
  - The UE5 joint plan matches v8's to within 2 mm.
  - Front silhouette IoU against the painting is 0.7974 (v8: 0.7975).
- **Outfit review** (`rebuild-v9/outfit-review/`): the same painted, groomed
  close-ups from v8 and v9 differ by 0.13-0.37 of 255 on average, and at most
  0.17% of pixels by more than 16. The largest differences are single pixels
  on the sash's torn tip and a lapel edge. At full resolution the collar,
  shoulder folds and torn sash edges hold their shape.
  - `outfit-wire.png` shows where the triangles went: fewer on flat panels,
    dense along seams, hems and the sash.
  - The sheets are `outfit-sheet.png` (full figure beside the body guidance),
    `outfit-details.png` (close-ups with a difference column) and
    `outfit-wire.png`.
  - To compare two builds:

```powershell
py -3.12 scripts/build_outfit_review.py work/ennix-character-v1/rebuild-v8 `
  work/ennix-character-v1/<new build> work/ennix-character-v1/<new build>/outfit-review `
  --blender 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
```

It renders the same painted, groomed close-ups (jacket front and back, sash and
belt, sleeve and hand, trousers and boots, the back three-quarter outline) from
both assemblies with a difference column, the full figure beside the body
guidance, and the outfit's triangle edges over its paint.

## Groom fill (recipe `ennix-open-review-20261011`)

In game the hair read as flat bright clumps over near-black gaps, and the crown
edge broke into see-through tips. The groom's render settings made no
difference, so the fix is in `grow_hair_groom.py`. Recipe `20261011` changes
only the groom. Inputs, head, face paint, body, rig and tier are those of
`20261010`, and every 20261010 guide and lock is kept.

- **Why the gaps.** Each lock was a flat ribbon at its own random depth in the
  envelope. Its children were near-copies of the nearest guide (inverse-square
  weights over 3 guides), clumped to a point from mid-length. Seen from
  outside, a deep lock between two outer ones is a crevice.
- **Fill options.** Each defaults to the old behaviour, and recipe 20261010
  still gives `rebuild-v9/strands.npz` byte for byte.
  - `--extra-children 60`: more strands per guide (77,550 to 110,550), rooted
    from an independent seed. Raising `--children` instead moves every lock.
  - `--blend-guides 6 --blend-sigma 0.01`: Gaussian blending over the
    neighbouring guides, so the hair between two locks belongs to both.
  - `--clump 0.75 --clump-power 3`: locks stay broad and gather near the tip.
  - `--lock-thickness 0.0035`: depth through the layer, a full lock rather
    than a ribbon.
  - `--depth-smoothing` is there too. It measured no better and is not used.
  - `strand_radius` 0.16 mm keeps the review render's coverage at the new
    count. The game sets its own strand width.
- **The game look.** Cycles' hair BSDF lights the inside of the hair, so the
  review render hides these gaps.
  - `render_painted_head.py` can draw strands as the game does: `--strand-width`
    (Unreal's width, root and tip scale), `--strand-gradient` (the hair
    material's root-to-tip colour), `--light sun`, `--hair-shader diffuse` (no
    light through the hair) and `--id-pass`.
  - That look reproduces the in-game failure on the v9 groom.
- **Built: `work/ennix-character-v1/rebuild-v10`**, on the CPU
  (`--device CPU`) in 390 s, with `--manny-dir work/ennix-character-v1/rig-ue5`.
  - 70,745 triangles: the scalp cap lost 3 at its thin edge. Both strict gates
    pass at the hero tier with no warnings, and the deformation checks pass.
  - Head, body and every paint texture are byte-identical to v9.
  - `export/Ennix_Groom_UE5.abc` round-trips 110,550 curves and 4,190,591
    points.
- **Review** (`rebuild-v10/groom-review/`):
  - `groom-sheet.png`: the review look beside the references.
  - `groom-game-look.png`: close-ups in the game look, with two measures.
    `crevice` is the share of hair darker than half its surroundings.
    `outline_ragged` is how far the dense mass's crown outline departs from a
    smooth one.
  - v9 to v10: crevice 5.3/6.2/5.3% to 3.3/4.2/4.6% (front, three-quarter,
    top); ragged outline 1.6/2.1/2.4% to 1.3/1.6/1.7%.
  - In the review look v10 is fuller and smoother, and a little softer than
    v9's ropey curls.

```powershell
py -3.12 scripts/build_groom_review.py work/ennix-character-v1/rebuild-v9 `
  work/ennix-character-v1/<new build> work/ennix-character-v1/<new build>/groom-review `
  --blender 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --device CPU `
  --game-look profiles/groom-looks/unreal-aether-wars.json --name Ennix
```

A groom-look profile (`profiles/groom-looks/`) says how a game draws strands:
its strand width with root and tip scale, and its hair material's root-to-tip
colour. `unreal-aether-wars.json` mirrors TheAetherWars `Tools/EnnixPlayer.py`
(`make_groom`, and the hair material in `make_materials`), so change it with
the game. `--reuse-renders` redraws the sheets only.

## Outfit paint for game garment materials

In game the painted outfit read as blotchy rubber (the jacket) and red
camouflage (the scarf). The multiview bake carries the painting's light and
print, and the unseen-texel fill leaves faceted blotches.
`scripts/refine_outfit_paint.py` runs right after `paint_ennix_body.py`
and writes `<build>/outfit-paint/`:

- `garment_mask.png`: R is leather, G cloth, B red fabric; skin is the rest.
  Each triangle is classified by its painted Lab colour, gated to where the
  garment can be. The gates are the character's, in a profile
  (`profiles/outfit-paint/ennix.json`: skin only on the forearms, hands and
  neck; cloth only on the torso front). A neighbour vote follows.
- `body_basecolor.png`: per garment, a 6 cm low-pass weighted to the painted
  coverage. The baked light is compressed toward the median, and the
  garment's mean stays the painting's. Detail under 6 mm (buckles, buttons,
  seams) is kept at 0.65, and the blotch band at 0.25-0.3. Unseen texels are
  pulled to the garment's colour. Skin texels are copied unchanged, so the
  hands and neck still match the face.
- `leather_normal.png` and `weave_normal.png`: tileable detail normals made
  with numpy (Worley pebble grain, plain weave), with no third-party maps.
- `outfit-paint.json`: the parameters, the classes, and the measured UV scale.
  The game tiles the detail from it: a 12 cm leather tile and a 6 cm weave
  tile.

TheAetherWars' `Tools/EnnixPlayer.py` imports the folder with
`import_textures(build)`, and `make_materials` builds the garment material:
roughness and specular per garment, and the face's contrast curve on skin
only. To run the stage on an existing build:

```powershell
python scripts/refine_outfit_paint.py <build>/body/body.npz <build>/body/paint/body_basecolor.png `
  <build>/body/paint/coverage.png <build>/outfit-paint --params profiles/outfit-paint/ennix.json
```

## Repeatability evidence

Two independent final builds reproduce the head NPZ, strand NPZ, body NPZ and
both baked base-colour maps byte for byte. Canonical native audits match every
mesh's coordinates, topology/winding, UVs, material assignment, weights, facial
shapes and transforms, plus every rest bone and the groom. BMesh can reorder
equivalent polygons or rotate their first loop; the audit normalizes only those
representations. Raw Blend/FBX containers and rendered pixels are not claimed
byte-identical. Both the raw comparison and canonical comparison are retained.

## Unreal review

Enable the existing `HairStrands` and `AlembicHairImporter` plugins. The importer
plugin needs an editor restart; no C++ change was required. In editor Python,
add this repository's `scripts/ue5` directory to `sys.path`, then call:

```python
import import_ennix_review
import_ennix_review.main(
    r"C:\path\to\rebuild\rigged\Ennix_Body_Face.fbx",
    r"C:\path\to\rebuild\export\Ennix_Groom.abc",
    "/Game/EnnixReview/MyFreshReview",
    r"C:\path\to\rebuild\export\unreal-import.json",
)
```

Use a fresh destination. The checked local import is
`/Game/EnnixReview/20261007/V5/BP_Ennix_Review`. It combines the skeletal mesh,
groom and binding; it does not replace the player or edit the game map.
`review_ennix_import.setup(...)`, `use_blueprint(...)`, then `capture(...)` on a
later editor tick make the temporary review stage. Call `cleanup()` afterward.
The helper explicitly enables animation updates on the **spawned editor
instance** so the bound hair renders. This preview switch is transient.

The import retained all 34 morph targets and 77,550 hair curves, and built
bindings for 77,550 render roots / 7,755 simulation guides. UE resamples curve
points; its point count differs from the source by design. Blender Alembic drops
the custom per-strand colour attribute, so UE uses a recorded brown hair material
while the native file retains its varied source colours. The import script
corrects coordinates and builds explicit base-colour/roughness shaders instead
of relying on FBX's Phong/emission conversion. Hair simulation remains off.

## Remaining gates

- Source silhouette IoU **0.802**, below **0.900**; bounding-box centre error
  **3.61 px**, within the **12 px** limit. Jacket/arms/legs still differ from the
  illustration. Hair has less loose wispy volume; face and painterly clothing
  still need artistic approval.
- Triangles: **70,745**, within the hero tier's **80,000** (recipe `20261011`,
  `rebuild-v10`; v9 had 70,748). Both strict rig gates and all five exported deformation checks
  pass without warnings. Earlier builds (136,587 against the flat 20,000) are
  superseded.
- Blinks and mouth extremes need facial polish. The original is a painted
  reference, and hidden surfaces use inferred witnesses; they are not recovered
  ground truth. The eyes remain simple meshes without a production cornea setup.
- UE retained the 34 facial target names, but `set_morph_target` editor captures
  did not yet demonstrate the expected mouth/blink deformation. Native Blender
  expression renders pass data through the controls; UE facial playback remains
  a separate unresolved gate, not an import success claim.
- No exported moving idle, animation retarget, gameplay, collision/physics or
  cooked-runtime acceptance is claimed. Human approvals remain pending.

New oral assets come from the official [MakeHuman CC0 system asset pack](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html).
Headers and source/download hashes are retained. Repository code is MIT;
Blender is GPL, Python PSF, NumPy/SciPy BSD and Pillow HPND. Existing acquisition
and image inputs retain their own provenance; they are not relabelled MIT/CC0.
