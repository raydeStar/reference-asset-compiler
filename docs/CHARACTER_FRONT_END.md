# From reference pictures to a frozen input bundle

*Type: how-to*

The generic path from a character's reference pictures to the frozen input
bundle and recipe that `scripts/rebuild_character.py` builds from
([CHARACTER_REBUILD.md](CHARACTER_REBUILD.md)). Every step is a script in this
repository; per-character values live in `profiles/characters/<id>.json` or in
arguments. Each step is marked **CPU** or **GPU**. Only the Hunyuan scans, one
template render (only for a new template) and some review renders need the GPU.

Ennix, the first character, went through this path partly by hand;
[ENNIX_REBUILD.md](ENNIX_REBUILD.md) is his case study.

## What you start with

| Picture | Frame | Notes |
| --- | --- | --- |
| the painting (`original.png`) | the source frame: the same orthographic frame as the body guidance | the artistic authority; the head is placed against its face |
| body guidance, front / left / back | the source frame, one size | full figure, both hands free in a T- or A-pose (no separate hand scan) |
| head guidance, front / left / back | its own frame | a close-up of the head, for the head scan, the conform and the head paint |

The examples use PowerShell from the repository root. `py -3.12` is the
runner's Python (NumPy 2.1.3, SciPy 1.15.1); the other steps run on any Python
with NumPy, SciPy and Pillow.

```powershell
$C  = 'character-02'                      # the data id
$W  = "work/$C"                           # working folder (outside Git)
$B  = 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
$Comfy = 'C:\...\ComfyUI_windows_portable'  # or set RAC_COMFYUI
$Torch = "$Comfy\python_embeded\python.exe" # Python with torch, for DWPose (CPU)
$DW = "$Comfy\ComfyUI\custom_nodes\comfyui_controlnet_aux\ckpts\hr16\DWPose-TorchScript-BatchSize5\dw-ll_ucoco_384_bs5.torchscript.pt"
$Ref = 'work/ennix-character-v1'          # the hm08-male template files (see step 6)
```

## 1. Start the profile (CPU)

Copy `profiles/characters/ennix.json` to `profiles/characters/$C.json` and set
`name`, `asset_prefix` and `inputs.body_object`
(`<asset_prefix>_Garment_And_Wrists_Preserved`). Delete
`face_proportions` and `body_paint.unmirrored_red` unless the new source has a
lifted mouth corner or a one-sided red garment. The later steps fill in the
measured values.

## 2. Cut out the body guidance (CPU)

Background removal only; the diffusion model is not loaded. It runs in the
Hunyuan environment (`$env:RAC_LEGACY_ROOT\.venv-hy3d`). Its remover may pick
CUDA when onnxruntime-gpu is installed: `$env:CUDA_VISIBLE_DEVICES=''` keeps it
on the CPU.

```powershell
& "$env:RAC_LEGACY_ROOT\.venv-hy3d\Scripts\python.exe" workflows/geometry/hunyuan3d/run_hy3d_multiview.py `
  --front $W/guidance/body-front.png --left $W/guidance/body-left.png --back $W/guidance/body-back.png `
  --output $W/prepare/unused.glb --report $W/prepare/preparation.json --prepared-dir $W/prepare/body --prepare-only
```

`$W/prepare/body/{front,left,back}.png` are the bundle's `body-front.png`,
`body-left.png` and `body-back.png`. Check each alpha by eye: the bake paints
whatever the alpha keeps.

## 3. Measure the source frame (CPU)

```powershell
python scripts/measure_source_frame.py --front $W/prepare/body/front.png --side $W/prepare/body/left.png `
  --back $W/prepare/body/back.png --height-m 1.8 --profile profiles/characters/$C.json --write
```

Writes the profile's `source_camera`: the picture size, `px_per_m` (the front
figure's pixel height over `--height-m`), and the front and side figure-box
centres, where the centred body's origin lands. The side shares the front's y.
A side or back figure more than 2% taller or shorter than the front's is a
warning: the pictures disagree on scale, and the bake will smear. Update the
block's `_comment`, which still describes the copied profile.

## 4. Scan the body and the head (GPU)

Hunyuan3D-2mv, multiview, one request each. The request format and the
derivation report it needs are in [AI_STAGES_SETUP.md](AI_STAGES_SETUP.md),
"Geometry from one image, or from three". Multiview needs 18 GiB of free VRAM.

```powershell
./scripts/run_hy3d_geometry.ps1 -Request configs/generation/$C-body-attempt001.json
./scripts/run_hy3d_geometry.ps1 -Request configs/generation/$C-head-attempt001.json
```

Each attempt writes `candidate.glb` in its output directory. Review the clay
views before going on.

**The body from Pixal3D (MIT, single view, WSL).** With only a front picture
of the body, Pixal3D's candidate is the sharper one: on character-02 it kept
the boot laces and straps, the holster, the cuff buttons, the collar's edges
and separate fingers, where Hunyuan3D-2's single view fused the fingers and
softened the outfit. It needs about 20 GiB of free VRAM (close the editor),
takes about 2 minutes at 1024, and delivers the figure facing +y:

```powershell
$env:RAC_WSL_PIXAL3D_PYTHON = "/home/you/ai/envs/pixal3d/bin/python"; $env:PIXAL3D_ROOT = "/home/you/ai/Pixal3D"
python scripts/generate_geometry.py $C-body-pixal3d $W/guidance/body-front.png --seed 42 --resolution 1024
```

Then prepare it with `--yaw-deg 180 --centre-y-on-neck` (step 5). From Git Bash, set
`MSYS_NO_PATHCONV=1` or the WSL paths are rewritten into Windows ones.

## 5. Prepare the body scan (CPU)

First set the profile's `neck_overlap` for this figure: `above_z_m` is the cut
height (metres above the feet) and `ellipse_m` the neck column inside which the
scan's neck is removed; the assembly later cuts any collar skin left inside the
same ellipse. Ennix's (1.49 m, 0.072 x 0.061 m) are for a 1.8 m figure. Keep
`oral_anatomy.neck_m`'s second value (how far down the template head's neck
reaches) below the cut, or there is a gap; the stage warns.

```powershell
& $B -b --factory-startup --python-exit-code 1 --python scripts/blender/prepare_body_scan.py -- `
  <body attempt>/candidate.glb $W/front-end/body-acquisition.blend --height-m 1.8 `
  --profile profiles/characters/$C.json
```

- Joins and welds the GLB's meshes, scales them to `--height-m` about the
  origin, and keeps the centring Hunyuan delivers (z is re-centred only if the
  box is more than 1 mm off; x/y are left alone). `body_lift_m` is -min z.
- Removes the faces above the cut inside the neck column, everything above a
  head level (`--head-above-cut-m`, 0.12 m above the cut), and whatever is left
  floating above the cut. A collar that rises above the cut outside the column
  (at the back, say) is kept, so a tilted collar survives.
- With `neck_overlap.face_box_m` [|x|, y] (or `--face-box-m`) it also removes
  everything above the cut within that |x| and in front of that y. A scan whose
  chin and lower face are wider than the neck column and sit below the head
  level (under a high collar) otherwise keeps them, and they stand in front of
  the placed head: character-02's painted grin showed through his face from
  the side. His box is [0.10, -0.02]; check the front of the prepared body
  above the cut before going on.
- `--yaw-deg` turns the scan about the vertical axis first, so its front
  faces -y (Pixal3D: 180). The receipt records it.
- `--centre-y-on-neck` centres depth on the body in the 10 cm below the cut
  (|x| < 0.12 m), where step 7 puts the head's neck ring (y = 0). A coat that
  flares behind moves the box centre off the neck: Pixal3D's character-02 sat
  6 cm forward of it, and the head's neck stood out behind his collar.
- `--cut-z-m` and `--neck-ellipse-m` override the profile; `--measure-neck`
  measures the column on the scan instead (it fails when a collar hides the
  back of the neck, as Ennix's does). The measurement is in the receipt either
  way.
- Names the object `inputs.body_object` (or `<asset_prefix>_Garment_And_Wrists_Preserved`)
  and writes `body-scan-receipt.json` beside the blend: the source hash,
  triangles before and after, the scale, bounds, the cut and the column, and
  `body_lift_m`. Set the profile's `body_lift_m` to it.

Then set, from the prepared body (the receipt's bounds, or open the blend):

- `body.hands_beyond_abs_x_m`: where the hands begin along the arms (\|x\|).
  The body stage gives the hands their own triangle count past it.
- `neck_weight_blend_m`, `review_views`: heights on this figure (Ennix's are
  for 1.8 m).

## 6. The head (CPU)

The template is MakeHuman's hm08 (`scripts/blender/export_human_template.py`,
CPU). Ennix's male template and its landmark files are reused as they are:

- `$Ref/template/hm08-male.npz`, its front render's DWPose landmarks
  `$Ref/landmarks/dw-template-front.json` and the render's camera
  `$Ref/landmarks/template-front-camera.json`;
- `profiles/head-templates/hm08-male-face-landmarks.json`, the same landmarks
  bound to the template's surface (for step 7).

A different template (another export) needs its own front render
(`scripts/blender/render_mesh_view.py`, Workbench: **GPU**), DWPose on it, and a
new binding (`fit_head_placement.py --save-binding`, step 7).

```powershell
# The head scan as arrays, and the guidance's landmarks (DWPose on the CPU)
& $B -b --factory-startup --python scripts/blender/export_mesh_arrays.py -- <head attempt>/candidate.glb $W/head/acquisition.npz
& $Torch scripts/detect_face_landmarks_dwpose.py $W/guidance/head-front.png $W/head/dw-front.json --model $DW --overlay $W/head/dw-front.png
& $Torch scripts/detect_face_landmarks_dwpose.py $W/guidance/head-left.png $W/head/dw-left.json --model $DW --overlay $W/head/dw-left.png

# The scan's own face: a front render (Workbench, GPU; absolute paths, Blender drops relative ones) and DWPose on it
& $B -b --factory-startup --python scripts/blender/render_mesh_view.py -- "$PWD\$W\head\acquisition.npz" `
  "$PWD\$W\head\acq-front.png" "$PWD\$W\head\acq-front-camera.json" --arrays
& $Torch scripts/detect_face_landmarks_dwpose.py $W/head/acq-front.png $W/head/dw-acq-front.json --model $DW --overlay $W/head/dw-acq-front.png

# Conform the template onto the scan, held to the guidance's features (about 15 s)
python scripts/conform_head_template.py $Ref/template/hm08-male.npz $W/head/acquisition.npz `
  $W/head/conform.npz $W/head/conform.json --picture-landmarks $W/head/dw-front.json `
  --template-landmarks $Ref/landmarks/dw-template-front.json --template-camera $Ref/landmarks/template-front-camera.json `
  --acquisition-landmarks $W/head/dw-acq-front.json --acquisition-camera $W/head/acq-front-camera.json

# Hair: what stands off the conformed skin, as a closed shell
python scripts/extract_hair_region.py $W/head/conform.npz $W/head/hair-raw.npz
& $B -b --factory-startup --python scripts/blender/build_hair_shell.py -- $W/head/hair-raw.npz $W/head/hair-shell.glb $W/head/hair-shell.npz

# Stylised (inked) guidance only: take the ink off the skin before it is painted on (seconds, CPU)
python scripts/clean_line_art.py $W/guidance/head-front.png $W/guidance/clean/head-front.png --landmarks $W/head/dw-front.json
python scripts/clean_line_art.py $W/guidance/head-left.png $W/guidance/clean/head-left.png --landmarks $W/head/dw-left.json
python scripts/clean_line_art.py $W/guidance/head-back.png $W/guidance/clean/head-back.png

# Neck, hair trim, paint, groom and review renders (Cycles on the CPU; --skip-render to skip them)
python scripts/finish_template_head.py --template $Ref/template/hm08-male.npz --conform $W/head/conform.npz `
  --conform-receipt $W/head/conform.json --hair-shell $W/head/hair-shell.npz `
  --front $W/guidance/clean/head-front.png --side $W/guidance/clean/head-left.png --back $W/guidance/clean/head-back.png `
  --side-landmarks $W/head/dw-left.json --template-landmarks $Ref/landmarks/dw-template-front.json `
  --template-camera $Ref/landmarks/template-front-camera.json --out $W/head/finish --groom --blender $B --device CPU

# Hair the pictures showed in front of the skin (a lock past the jaw) off the skin texture
python scripts/clean_skin_paint.py --template $Ref/template/hm08-male.npz `
  --binding profiles/head-templates/hm08-male-face-landmarks.json `
  --texture $W/head/finish/paint/head_basecolor.png --out $W/head/finish/paint/head_basecolor_clean.png --mask $W/head/skin-blots.png
```

**Why the scan's own landmarks.** Without `--acquisition-landmarks` the
similarity alignment starts from the scan's frontmost point, which is the nose
only on a bare face. On character-02 a fringe spike stood in front of it: the
face fit settled into the hair at half scale (10.06 against 5.54), the eyes sat
in the fringe, the template skull stood 4.6 cm out of the top of the hair (a
bald crown and a band-only groom of 16.5k strands) and the jaw was painted a
hand's width below the chin. With the scan's landmarks the picture's features
start 2.6 mm off instead of 7.5 mm and the groom fills the hair (76.8k strands).
The receipt's `alignment.seed` records which start was used.

Review `$W/head/finish/render/` (and the overlays, and `skin-blots.png`) before
going on. Freeze `head_basecolor_clean.png` as the bundle's `head-basecolor.png`,
and the cleaned pictures as `head-front.png` and `head-left.png`.

## 7. Place the head on the body (CPU)

```powershell
py -3.12 scripts/fit_head_placement.py --head $W/head/finish/head.npz --transport-receipt $W/head/finish/head.json `
  --binding profiles/head-templates/hm08-male-face-landmarks.json --profile profiles/characters/$C.json `
  --reference $W/guidance/original.png --detect --torch-python $Torch --dwpose $DW --out $W/front-end/placement
```

- `--detect` crops the painting's head (0.34 x 0.31 m from just above the
  figure's top, from `source_camera` and `body_lift_m`; `--reference-crop`
  overrides), upscales it and runs DWPose on the CPU:
  `reference-head-crop.png` and `reference-landmarks.json`, which are the
  bundle's `original-head-crop.png` and `original-landmarks.json`.
- `--transport-receipt` first moves the head's lower face to the painting's
  proportions (`transport_face_proportions.py`, with the profile's
  mouth-corner lift), as the build does before placing it, and fits that head
  (`head-transported.npz`).
- The fit projects the head's landmarks (the template's DWPose points, bound to
  its surface) through the profile's `source_camera` and `body_lift_m`, and
  solves scale and x/z by least squares on the 12 stable points (eye corners,
  nose, mouth corners and centres; `--landmarks` picks another set). Depth puts
  the head's neck ring over the body's centre line (y=0; `--body-neck-y` or
  `--location-y` override). It refuses an rms above 3 px (`--max-rms-px`).
- `placement.json` holds `scale` and `location` (what `assemble_character.py`
  reads) and the fit's receipt: the landmarks, each one's residual in picture
  pixels, the crop, and where depth came from. `--compare` adds how far the face
  and the whole head move from another placement.

On Ennix, from his bundle's own painting landmarks, it lands his face within
0.8 mm mean (1.3 mm max) of his hand-fitted placement in x and z, and the
whole head within 1.1 mm mean (3.3 mm max); scale is 2.0% smaller, rms 1.33 px
(his fit: 1.38). From his raw pictures (fresh crop and detection, then
transport): face 1.1 mm mean (1.7 max), head 1.5 mm mean (4.5 max). Depth
differs by 5.5 mm: his was set by eye.

## 8. Freeze the bundle and write the recipe (CPU)

```powershell
python scripts/freeze_character_inputs.py --bundle $W/rebuild-inputs `
  --recipe-from recipes/ennix-open-review-20261011.json --recipe-out recipes/$C-open-review-<date>.json `
  --character profiles/characters/$C.json `
  template.npz=$Ref/template/hm08-male.npz `
  head.npz=$W/head/finish/head.npz head.json=$W/head/finish/head.json hair.npz=$W/head/finish/hair-smooth.npz `
  head-basecolor.png=$W/head/finish/paint/head_basecolor.png hair-basecolor.png=$W/head/finish/paint/hair_basecolor.png `
  head-front.png=$W/guidance/head-front.png head-left.png=$W/guidance/head-left.png front-landmarks.json=$W/head/dw-front.json `
  original.png=$W/guidance/original.png original-head-crop.png=$W/front-end/placement/reference-head-crop.png `
  original-landmarks.json=$W/front-end/placement/reference-landmarks.json placement.json=$W/front-end/placement/placement.json `
  body-acquisition.blend=$W/front-end/body-acquisition.blend body-front.png=$W/prepare/body/front.png `
  body-back.png=$W/prepare/body/back.png body-left.png=$W/prepare/body/left.png `
  makehuman=$Ref/rebuild-inputs/makehuman --rig-landmarks-optional
```

It copies each NAME=PATH under the name the runner reads, refuses a missing
one, never writes into a non-empty bundle or over a recipe, and writes the
recipe from the template recipe with the new hashes. Review the recipe's
`body` counts, `groom`, `face_paint` and `character_tier`: they are the
template recipe's starting point.

**Rig landmarks.** `rig-landmarks.json` is the measured skeleton, measured on
the skinning proxy of the assembled character, which only the build makes.
Leave it out of a first bundle (`--rig-landmarks-optional`): the build then
derives the joints from its own proxy (`derive_humanoid_landmarks.py`, CPU with
`--no-overlays`) and says so in its receipt. Review the rig, and freeze
reviewed landmarks into the next bundle.

Also write an outfit-paint profile (`profiles/outfit-paint/<id>.json`, where
each garment can be on the body) and point the character profile's
`outfit_paint_params` at it.

**A long coat.** If the character wears a knee-length coat (or anything the
game should simulate below the belt), add a `coat` block to its profile; `{}`
gives four chains (front and back, each side) of three bones from just under
the belt to the knee. Set the hem (`hem_above_knee_m` or `hem_z_m`) to the
garment's, and `open_front: true` for a coat worn open. After the first build,
read `export/<prefix>_UE5.coat.json`: every chain should say `hem_found: true`;
if not, its `coat_bottom_z_m` says where the coat ends there (a scanned coat
often ends above the knee). The build then adds the
chains after the UE5 export; `export/<prefix>_UE5.fbx` is the coated FBX. See
CHARACTER_REBUILD.md, "A long coat". Without the block nothing changes.

## 9. Build (CPU, with GPU stages)

```powershell
py -3.12 scripts/rebuild_character.py --inputs $W/rebuild-inputs --recipe recipes/$C-open-review-<date>.json `
  --out $W/rebuild-v1 --blender $B --device CPU --manny-dir work/ennix-character-v1/rig-ue5
```

`--device CPU` renders the Cycles reviews on the CPU. Three stages still render
with EEVEE (**GPU**): `rig_ue5_character.py`'s orthographic views (with
`--manny-dir`), its animation test, and `deform_test.py`.

## Still by hand

- Reviewing every intermediate: the cut-out alphas, the scans' clay views, the
  conform and head renders, the placement's residuals, the first build.
- The profile values that are shapes on this figure rather than measurements
  of a picture: `neck_overlap`, `neck_weight_blend_m`, `review_views`,
  `oral_anatomy` (in template-head space, so the copied values are close on the
  same template; check the mouth box against the conformed head), and the
  outfit-paint profile.
- What CHARACTER_REBUILD.md lists under "Still tuned to the first character".
