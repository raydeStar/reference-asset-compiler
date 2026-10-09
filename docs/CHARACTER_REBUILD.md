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
- `rig-landmarks.json` is the measured, reviewed skeleton. A recipe without
  one (a new character's first build) derives the joints from the build's own
  proxy instead; the landmarks, the receipt (`rig_landmarks`) and its limits
  then say they were derived in this build, not measured or reviewed.
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
| `blender/grow_hair_groom.py` | seeded strand groom (recipe `groom`; `cap_front_inset` ends the dark scalp cap that far behind the forehead hairline, so its edge does not show between fringe locks) | |
| `blender/render_painted_head.py` | head review renders; saves the head blend | |
| `blender/fit_oral_anatomy.py` | CC0 teeth and tongue, mouth interior, neck extension | `asset_prefix`, `oral_anatomy` |
| `blender/prepare_body_acquisition.py` | reduces the acquired outfit (recipe `body`), UVs it | `inputs.body_object`, `body` |
| `paint_body_from_views.py` | bakes the source pictures onto the outfit | `source_camera`, `body_paint` |
| `refine_outfit_paint.py` | garment mask, cleaned albedo, detail normals | `outfit_paint_params` |
| `blender/assemble_character.py` | places the head on the body, cuts the collar overlap, review renders | `asset_prefix`, `body_lift_m`, `source_camera`, `neck_overlap` |
| `blender/export_skinning_proxy.py` | joined body+head proxy for rigging | `asset_prefix` |
| `blender/derive_humanoid_landmarks.py` (no `rig-landmarks.json` in the recipe) | derives the joints from this build's proxy into `rig-input/derived/`; `--device CPU` passes `--no-overlays` (the overlays render with EEVEE) | |
| `blender/rig_from_landmarks.py` | rigs the proxy from the measured (or derived) landmarks | |
| `blender/bind_assembly_to_rig.py` | transfers the proxy's weights to the editable assembly | `asset_prefix`, `neck_weight_blend_m`, `neck_overlap` |
| `blender/export_groom_alembic.py` | groom to Alembic, with a round-trip count check | `asset_prefix` |
| `rig_ue5_character.py` (with `--manny-dir`) | Manny-conformant game rig | `asset_prefix` |
| `blender/export_ue5_character.py`, `export_groom_alembic.py` | game FBX and groom | `asset_prefix` |
| `blender/add_coat_chains.py` (profile has `coat`) | coat-tail bone chains for the game's cloth physics; the plain export becomes `P_UE5.nocoat.fbx` (below) | `coat` |
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
| `body_paint.min_facing`, `body_paint.mask_erode_px` | optional: how squarely a surface must face the front or back picture to take its paint (cosine, default 0.05) and how many pixels come off each cut-out's edge (default 1). With no side picture raise both (character-02: 0.35 and 4): a cut-out's halo of the old background otherwise smears across every side surface; the 3D fill paints the sides from their neighbours instead |
| `body_paint.fill`, `body_paint.fill_trust`, `body_paint.normal_smoothing_m` | optional: how unseen outfit is painted. `nearest` (default) copies the nearest painted points in 3D; without a side picture that drags the cut-outs' outline across the coat's sides and shoulder tops as grey streaks. `surface` takes colour only where a picture faces the surface at `fill_trust` (cosine, default 0.6) or better, spreads it as a smooth membrane over the mesh's own edges (it never reaches across a gap), and fades the paint between `min_facing` and `fill_trust` into it. `normal_smoothing_m` judges facing on normals averaged over that many metres (a scan's wrinkle facets otherwise take a picture's outline). character-02: `surface`, 0.6, 0.03 |
| `body_paint.unmirrored_red` | optional: a red garment on one side only, kept out of the mirrored side view (R/G, R/B, below pixel row, grow px) |
| `outfit_paint_params` | the outfit-paint profile |
| `oral_anatomy` | `mouth_box_m` (\|x\|, min y, z range of the mouth interior); `neck_m` (open neck boundary below, extended down to) |
| `neck_overlap` | the acquired collar's duplicate neck patch: `ellipse_m` radii and `above_z_m` to cut, the cut rim (`rim_above_z_m`, `rim_abs_x_m`) to smooth, where the binding also lets the body differ from the proxy; optional `face_box_m` [\|x\|, y]: `prepare_body_scan.py` also cuts the scan's chin and face in front of the neck (CHARACTER_FRONT_END.md, step 5) |
| `neck_weight_blend_m` | head weight rises from 0 at the first height to 1 over the second |
| `review_views` | what the posed review renders look at |
| `coat` | optional: a long coat's bone chains (below); absent, no coat bones |

### A long coat (`coat`)

A knee-length coat cannot follow the thighs; the game simulates it on bones of
its own (The Aether Wars' `Tools/CoatPhysics.py` builds an AnimDynamics
post-process AnimBP from them). With a `coat` block, after the UE5 export the
runner runs `blender/add_coat_chains.py` on `ue5/fit/P_UE5.blend`:

```json
"coat": {
  "chains": {"front_l": 25, "front_r": -25, "back_l": 150, "back_r": -150},
  "bones_per_chain": 3,
  "top_below_pelvis_m": 0.04,
  "hem_above_knee_m": 0.0,
  "leg_clearance_m": 0.12,
  "open_front": false
}
```

Every key is optional; these are the defaults (`"coat": {}` is this block).
`chains` maps `<group>_<l|r>` to degrees round the body from straight ahead
toward the character's left (`side_l: 90` adds a hip chain). The roots sit
`top_below_pelvis_m` under the pelvis joint (just under the belt), the hem at
the knee plus `hem_above_knee_m` (or at `hem_z_m`, absolute; not both).
`leg_clearance_m`: outfit vertices further than this from every
thigh/calf/foot axis are coat; nearer ones (trousers, boots) keep their
weights. `open_front: true` keeps each front panel on its own side's chain.
`top_blend_m` (default one segment) is how far below the roots the coat hands
over from the pelvis/thigh weights to the chains. `scripts/coat_profile.py`
documents and checks the block; a bad one stops the build before it starts.

What the stage does: for each chain it casts a ray out from the body's axis at
the roots' height and at the hem to find the outfit's outermost lower-body
surface, and hangs `coat_<group>_01_<side>` .. `_<NN>_<side>` (parent
`pelvis`, then each other) plus a non-deforming `coat_<group>_end_<side>` leaf
at the hem between those points. Bone X runs down the chain (in UE the child
sits on +X), Z is the coat's outward normal. It skins the coat vertices to the
chains: blended from their own weights over the top band, between neighbouring
bones along a chain and neighbouring chains by angle (smoothstep), at most four
influences, normalized. Other vertices and meshes keep their weights exactly.
It exports with `export_ue5_character.py` itself, so the FBX settings are the
plain export's.

Outputs: `export/P_UE5.fbx` (coated), `export/P_UE5.nocoat.fbx` (the plain
export), `export/P_UE5.coat.json` (chains, bone positions, coat vertex count,
largest weight per chain and bone; whether each hem ray found the garment,
at what height and angle, and `coat_bottom_z_m`: where the coat really ends
within 10 degrees of the chain) and
`export/skeleton-ue5-coat.json`, the skeleton contract plus the chains, which
the UE5 rig gate checks the coated FBX against. The build receipt's `coat`
summarises them.

Limits: the chains are straight lines from root to hem, not bent to the
coat's shape between. A ray that slips through a vent or a crack at exactly
the chain's angle is retried 3 and 6 degrees either side. A hem ray that still
misses, or finds only a trouser leg (a garment shorter than the hem height),
hangs the chain straight down and says so (`hem_found: false`, and a `COAT
WARNING` line in the log with the coat's real end there). A coat that ends
above the knee needs `hem_above_knee_m` set to about its shortest side (the
rays also try 2.5 and 5 cm higher). An open coat needs `open_front: true` and
front chains that land on the panels (angles wider than the opening). Hang
each chain mid-panel, clear of vents: character-02's chains moved from
+-60/90/150 to +-75/110/160 once horizontal sections of the scan showed the
panels and the side-back vents (2026-10-09). Anything else hanging below the belt that
stands off the legs is skinned to the chains too (Ennix's sash, in a forced
dry run). Physics feel is reviewed in the game, not here.

To run it on its own (it never saves the input blend):

```powershell
& $B -b ue5/fit/P_UE5.blend --factory-startup --python scripts/blender/add_coat_chains.py -- `
  export/P_UE5.fbx --profile profiles/characters/<id>.json [--save-blend coated.blend]
```

### Output names

With `asset_prefix` `P`: `assembly/P_Character_Review.blend`,
`rig-input/P_proxy.fbx`, `proxy-rig/P_proxy_rigged.{fbx,blend}`,
`rigged/P_Rigged.blend`, `rigged/P_Body_Face.fbx`, `export/P_Groom.abc`,
`ue5/fit/P_UE5.blend`, `export/P_UE5.fbx`, `export/P_Groom_UE5.abc`,
`pose/P_Held_Inspection.blend` (with a `coat`, also `export/P_UE5.nocoat.fbx`
and `export/P_UE5.coat.json`). Objects are `P_Outfit_And_Hands`, `P_head`,
`P_eyes`, `P_teeth`, `P_tongue`, `P_scalp-cap`, `P_groom`; materials include
`P_Source_Outfit`, `P_Mouth_Interior`, `P_teeth`, `P_tongue`. Paint outputs keep
fixed names: `face-paint/head_basecolor.png`, `body/paint/body_basecolor.png`,
`outfit-paint/`. A game importing a build relies on these names.

## A new character

[CHARACTER_FRONT_END.md](CHARACTER_FRONT_END.md) has the whole path, with commands.

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
  (z 1.525-1.746 m, with their widths) and where the forehead colour is
  sampled (z 1.739 m). Conformed heads share the frame (character-02's eyes
  sit 3 mm below Ennix's), so the zones carry over. Since 2026-10-09 the
  picture-space parts come from each picture's own landmarks: the brow window
  (`--brow-window landmarks`; Ennix's hand-set pixels are within 0.25 px of it,
  `fixed` reproduces them exactly), a forehead colour taken from the skin
  between the eyes and on the cheeks when a fringe covers the probe (the
  receipt's `forehead_colour`), and the painting's mouth kept only when its
  lips are closed (`--source-mouth auto`: inner-lip gap over mouth width at
  most 0.03; a grin's teeth on the lips read as a grin in every expression).
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
