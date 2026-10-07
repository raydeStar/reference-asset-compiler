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
commercial add-ons. GPU rendering is configured explicitly in the scripts.

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
- **136,587 triangles** exceed the strict **20,000** profile ceiling. The separate
  120k outfit review budget is not a waiver. Every other strict skeleton/weight/UV
  check passes; all five exported deformation checks pass without warnings.
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
