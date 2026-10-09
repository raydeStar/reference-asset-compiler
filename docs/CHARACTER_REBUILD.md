# Rebuilding a character from frozen inputs

*Type: reference*

`scripts/rebuild_character.py` turns a frozen acquisition (a conformed head, an
acquired outfit, the source pictures and their landmarks) into a rigged,
groomed, painted review character and its game exports. Every output stays a
**candidate**: the build never sets `production_ready`. Ennix is the first
character built this way; [ENNIX_REBUILD.md](ENNIX_REBUILD.md) is his case
study (what each recipe changed, the reviews, the remaining gates).

The tooling is generic. What belongs to one character lives in data:

| Data | Holds | Example |
| --- | --- | --- |
| Frozen input bundle (`--inputs`) | the binary inputs, outside Git | `work/ennix-character-v1/rebuild-inputs/` |
| Recipe (`--recipe`) | input hashes, triangle counts, groom, face paint, tier, UE5 options, and which character profile to use | `recipes/ennix-open-review-20261011.json` |
| Character profile | names, object names inside the inputs, the character's measurements | `profiles/characters/ennix.json` |
| Outfit-paint profile | where each garment can be on the body | `profiles/outfit-paint/ennix.json` |

## Run it

From the repository root, into a **new** output directory (the runner refuses
an existing one):

```powershell
py -3.12 scripts/rebuild_character.py `
  --inputs work/ennix-character-v1/rebuild-inputs `
  --recipe recipes/ennix-open-review-20261011.json `
  --out work/ennix-character-v1/my-fresh-rebuild `
  --blender 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --device CPU `
  --manny-dir work/ennix-character-v1/rig-ue5
```

- The build needs only `--inputs` and the recipe. Every input's SHA-256 is
  checked against the recipe before anything runs. The recipes' `source`
  fields are provenance (where an input was frozen from); nothing reads them.
- The recipe names its character profile (`"character"`); `--character
  profiles/characters/<name>.json` overrides it. Recipes older than
  `ennix-open-review-20261011` predate the profile and need `--character`.
- `--device CPU` renders the Cycles review images on the CPU. Three stage
  scripts still render with EEVEE, which needs a GPU: `render_ortho_views.py`
  and `pose_ue5_anim_test.py` (both inside `rig_ue5_character.py`; the
  orthographic views feed DWPose) and `deform_test.py`.
- `--manny-dir` (Epic's Manny dumps from `scripts/ue5/dump_manny_reference.py`,
  kept out of Git) adds the Manny-conformant game rig and its exports.
- The receipt (`build-receipt.json`) records the recipe's, the character
  profile's and the outfit-paint profile's hashes, the tool versions, every
  command, its log and return code, and every output's hash.

Verified with Python 3.12.7 (NumPy 2.1.3, SciPy 1.15.1, Pillow 10.4.0) and
Blender 5.2.2 LTS. Run with that Python: another NumPy/SciPy moved six pixels
of the outfit albedo by one level (ENNIX_REBUILD.md, "Repeatability
evidence").

### Tools outside the repository

| Tool | How it is found |
| --- | --- |
| Blender 5.2.2 | `--blender` (`rig_ue5_character.py` also reads `RAC_BLENDER`) |
| Python with torch, DWPose TorchScript weights (UE5 rig keypoints) | `rig_ue5_character.py --comfyui DIR` or `RAC_COMFYUI`: a ComfyUI portable install with `comfyui_controlnet_aux`. `--torch-python`/`RAC_TORCH_PYTHON` and `--dwpose`/`RAC_DWPOSE` override each piece. With `RAC_COMFYUI` unset it falls back to the original workstation's path. |
| Manny reference dumps | `--manny-dir` |

## The stages

In order, as the runner issues them. "Profile" is what each stage takes from
the character profile; the runner passes it as arguments, so each stage also
runs on its own.

| Stage | Does | Profile |
| --- | --- | --- |
| `transport_face_proportions.py` | moves the conformed head's lower face to the painting's proportions | `face_proportions`; zones tuned, see below |
| `reproject_face_paint.py` | reprojects the painting onto the face; continuous neck paint | (tuned, see below) |
| `refine_face_paint.py` | measured blush, stubble, hairline, ear and neck tone (recipe `face_paint`) | |
| `blender/grow_hair_groom.py` | seeded strand groom (recipe `groom`) | |
| `blender/render_painted_head.py` | head review renders; saves the head blend | |
| `blender/fit_oral_anatomy.py` | CC0 teeth and tongue, mouth interior, neck extension | `asset_prefix`, `oral_anatomy` |
| `blender/prepare_body_acquisition.py` | reduces the acquired outfit (recipe `body`), UVs it | `inputs.body_object`, `body` |
| `paint_body_from_views.py` | bakes the source pictures onto the outfit | `source_camera`, `body_paint` |
| `refine_outfit_paint.py` | garment mask, cleaned albedo, detail normals | `outfit_paint_params` |
| `blender/assemble_character.py` | places the head on the body, cuts the collar overlap, review renders | `asset_prefix`, `body_lift_m`, `source_camera`, `neck_overlap` |
| `blender/export_skinning_proxy.py` | joined body+head proxy for rigging | `asset_prefix` |
| `blender/rig_from_landmarks.py` | rigs the proxy from the measured landmarks | |
| `blender/bind_assembly_to_rig.py` | transfers the proxy's weights to the editable assembly | `asset_prefix`, `neck_weight_blend_m`, `neck_overlap` |
| `blender/export_groom_alembic.py` | groom to Alembic, with a round-trip count check | `asset_prefix` |
| `rig_ue5_character.py` (with `--manny-dir`) | Manny-conformant game rig | `asset_prefix` |
| `blender/export_ue5_character.py`, `export_groom_alembic.py` | game FBX and groom | `asset_prefix` |
| `blender/pose_character_review.py` | held pose, head turn, expressions | `asset_prefix`, `review_views` |
| `blender/audit_semantic_fingerprint.py` | the semantic fingerprint (below) | |
| `validate_silhouette.py` | front silhouette against the painting | |
| `blender/gate_rig.py` | strict rig and triangle gate (recipe `character_tier`) | |
| `blender/deform_test.py` | deformation checks | |

## The character profile

`profiles/characters/<name>.json`. Keys starting with `_` are comments. Lengths
are metres in character space (x across, y front-negative, z up, feet on z=0;
x < 0 is the character's right), millimetres where the key ends in `_mm`;
pixels are the source pictures'.

| Key | Meaning |
| --- | --- |
| `name` | the character's name, for logs and the receipt |
| `asset_prefix` | prefixes every object, material and output file (below) |
| `inputs.body_object` | the outfit's object inside `body-acquisition.blend` |
| `face_proportions.mouth_corner_lift_mm` | optional: how far to raise the mouth corner on the character's right and on its left (straight up), restoring a source's lifted corners; absent, no lift |
| `source_camera` | the painting's orthographic frame: `image_px`, `px_per_m`, and the pixel the body's origin lands on in the front (`front_origin_px`) and side (`side_origin_px`) pictures |
| `body_lift_m` | raises the acquired body (centred on z=0) onto the floor |
| `body.hands_beyond_abs_x_m` | where the acquired outfit's hands begin along the T-pose arms (\|x\|); needed when the recipe gives the hands their own count. Recipes 20261010 and 20261011 also carry it; if both do, they must agree |
| `body_paint.side_band_abs_x_m` | the side picture paints fully within the first \|x\| and fades out by the second |
| `body_paint.unmirrored_red` | optional: a red garment on one side only, kept out of the mirrored side view (R/G, R/B, below pixel row, grow px) |
| `outfit_paint_params` | the outfit-paint profile |
| `oral_anatomy` | `mouth_box_m` (\|x\|, min y, z range of the mouth interior); `neck_m` (open neck boundary below, extended down to) |
| `neck_overlap` | the acquired collar's duplicate neck patch: `ellipse_m` radii and `above_z_m` to cut, the cut rim (`rim_above_z_m`, `rim_abs_x_m`) to smooth, where the binding also lets the body differ from the proxy |
| `neck_weight_blend_m` | head weight rises from 0 at the first height to 1 over the second |
| `review_views` | what the posed review renders look at |

### Output names

With `asset_prefix` `P`: `assembly/P_Character_Review.blend`,
`rig-input/P_proxy.fbx`, `proxy-rig/P_proxy_rigged.{fbx,blend}`,
`rigged/P_Rigged.blend`, `rigged/P_Body_Face.fbx`, `export/P_Groom.abc`,
`ue5/fit/P_UE5.blend`, `export/P_UE5.fbx`, `export/P_Groom_UE5.abc`,
`pose/P_Held_Inspection.blend`. Objects are `P_Outfit_And_Hands`, `P_head`,
`P_eyes`, `P_teeth`, `P_tongue`, `P_scalp-cap`, `P_groom`; materials include
`P_Source_Outfit`, `P_Mouth_Interior`, `P_teeth`, `P_tongue`. Paint outputs keep
fixed names: `face-paint/head_basecolor.png`, `body/paint/body_basecolor.png`,
`outfit-paint/`. A game importing a build relies on these names.

## A new character

1. Freeze the inputs into a bundle and write a recipe listing their hashes
   (copy the newest recipe's shape).
2. Copy `profiles/characters/ennix.json`, set the names, and measure the
   source pictures' frame, the body's lift and where its hands begin. Drop
   Ennix's mouth-corner lift and unmirrored red unless the new source has them.
3. Write an outfit-paint profile for its garments.
4. Re-tune what is still the first character's (next section), then build and
   review.

## Still tuned to the first character

These stay in code, marked `Per-character (Ennix-tuned)`, because moving them
is not mechanical: they are many interlocking zone shapes on Ennix's conformed
head or framing choices, and a second character should derive them (from its
head's landmarks, its height) rather than copy numbers.

- `transport_face_proportions.py`: the lower-face deformation zone (above
  z 1.50 m, front of y -0.04 m) and where a mouth-corner lift lands
  (z 1.625 m, |x| 0.03 m).
- `reproject_face_paint.py`: the face, mouth, neck and forehead blend zones
  (z 1.525-1.746 m, with their widths) and the forehead colour probe at
  z 1.739 m.
- `blender/render_outfit_review.py`: the outfit close-up cameras (jacket,
  sash, rolled sleeve, boots).
- `blender/pose_character_review.py`: the ortho frame widths (2.05, 0.45 and
  0.37 m) that go with `review_views`.

## Determinism

What reproduces byte for byte between two builds with the same tool versions:
the head, strand and body NPZs, every paint texture (`paint/`,
`face-paint/`, `body/paint/`, `outfit-paint/`), and the stage receipts once the
build directory in their paths is normalised.

What does not, by design, and how it is checked instead:

- `.blend`, `.fbx` and `.abc` containers carry timestamps and pointers. Their
  content is checked by `audit_semantic_fingerprint.py`, which hashes every
  mesh's coordinates, topology/winding, UVs, materials, weights, facial shapes
  and transforms, every rest bone, and the groom (`semantic-audit.json`).
- Rendered pixels (Cycles, EEVEE).
- The proxy rig's automatic (heat) weights: Blender solves them in parallel, so
  the outfit's weights move in the last digits between runs and its `weights`
  fingerprint differs even between two builds of the same inputs (v9 and v10
  did too). Every other fingerprint matches.
- The receipts' hashes of the rewritten input pointers (`front-landmarks.json`,
  `head.json`) and of the containers above, since those hold the build's path.
- `proxy-rig/rig-report.json`'s geometry fingerprint of the imported proxy
  (it differed between v9, v10 and the 2026-10-08 verify build, while the
  bound meshes matched).

The 2026-10-08 check of this tooling against `rebuild-v10` is in
[ENNIX_REBUILD.md](ENNIX_REBUILD.md), "Repeatability evidence".

## Renamed stages

These stages carried the first character's name until 2026-10-08. Older
recipes, handoff entries and receipts keep the old names.

| Was | Now |
| --- | --- |
| `rebuild_ennix.py` | `rebuild_character.py` |
| `refine_ennix_proportions.py` | `transport_face_proportions.py` |
| `refine_ennix_surface.py` | `reproject_face_paint.py` |
| `refine_ennix_face_paint.py` | `refine_face_paint.py` |
| `refine_ennix_outfit_paint.py` | `refine_outfit_paint.py` |
| `paint_ennix_body.py` | `paint_body_from_views.py` |
| `validate_ennix_visuals.py` | `validate_silhouette.py` |
| `blender/finish_ennix_anatomy.py` | `blender/fit_oral_anatomy.py` |
| `blender/prepare_ennix_body.py` | `blender/prepare_body_acquisition.py` |
| `blender/assemble_ennix_character.py` | `blender/assemble_character.py` |
| `blender/export_ennix_rig_proxy.py` | `blender/export_skinning_proxy.py` |
| `blender/bind_ennix_assembly.py` | `blender/bind_assembly_to_rig.py` |
| `blender/export_ennix_groom.py` | `blender/export_groom_alembic.py` |
| `blender/pose_ennix_review.py` | `blender/pose_character_review.py` |
| `blender/audit_ennix_repeatability.py` | `blender/audit_semantic_fingerprint.py` |
| `ue5/import_ennix_review.py` | `ue5/import_character_review.py` |
| `ue5/review_ennix_import.py` | `ue5/review_character_import.py` |
| `build_ennix_review.py`, `package_ennix_review.py`, `refine_ennix_landmarks.py` | `experiments/` (historical one-offs) |

`ue5/review_character_import.py`'s `capture()` uses The Aether Wars' private
editor plugin (`aether_mcp_tools`); its other functions need only Unreal.
