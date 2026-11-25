# Generation workflow playbook

*Type: reference*

This is the missing operational bridge between an approved picture and the
compiler. It is deliberately explicit about what runs where.

## The short instruction for another AI

Do **not** send texture work to ComfyUI on this workstation. The preserved
ComfyUI graph was the user's image-to-3D geometry workflow. For existing-mesh
PBR texturing, use the isolated Hunyuan3D-Paint 2.1 runner. TRELLIS.2 is a
tested challenger, not the production default. The compiler does not generate
geometry, repaint an atlas, or author a fresh humanoid rig; it normalizes,
gates, packages, imports, and verifies assets that already exist.

If the requested task is “fix these textures,” begin at Stage 4 below. Do not
reinstall random ComfyUI nodes or describe a hypothetical ControlNet pipeline.

## Stage 0 — preflight

```powershell
.\scripts\workflow_doctor.ps1
```

The doctor is read-only. A missing optional challenger is not a reason to
install anything. Before GPU work, also inspect `nvidia-smi`; preserve open
Blender, ComfyUI, and Unreal processes and never kill them automatically.

## Stage 1 — authority intake

Use `rac new` to copy and hash the approved image. Do not substitute a prompt,
generic asset pack, or manually approximated primitive. Pre-segment a reviewed
RGBA cutout for Pixal3D/TRELLIS paths.

## Stage 2 — geometry candidates

### Default: guarded direct Hunyuan3D runner

Use a checked-in request under `configs/generation/`. One wrapper,
`scripts\run_hy3d_geometry.ps1`, hash-pins and runs the repository copy of the
runner under `workflows/geometry/hunyuan3d/`; the request's `mode` selects it.
A request without `mode` runs the multiview runner (Hunyuan3D-2mv, three
guidance views bound to the source by a derivation report). Write
`"mode": "single_view"` explicitly when only the approved picture exists; see
*Geometry from a single image* below. The preflight hash-binds the immutable
intake image, every conditioned view, the multiview lineage report, model
parameters, and a brand-new attempt directory. The launcher then checks the
exact runner hash, GPU owners and free VRAM (18,432 MiB multiview, 12,288 MiB
single view), and any live ComfyUI queue before running exactly once:

```powershell
.\scripts\run_hy3d_geometry.ps1 `
  -Request .\configs\generation\fox-mascot-ai-v3.json
```

The launcher never kills a process, overwrites an attempt, or auto-retries a
failure. A successful run emits `candidate.glb`, the upstream generation
report, an attempt receipt, and a ledger-compatible candidate receipt. That is
still only an AI geometry candidate; stop for fixed-view modeling review.

### Historical ComfyUI path

Import `workflows/geometry/comfyui/hy3d_final_cut.json`. It is the original
64-node, 83-link graph supplied by the user. Its own notes describe the camera
mirroring/multiview bake, ReActor option, delighting, vertex inpaint, UV wrap,
and postprocess face budget.

On the current installation, the graph's Hunyuan3DWrapper and ReActor nodes
are absent. Preserve the graph; do not silently replace nodes. If its exact
dependencies are restored, use it for geometry and stop at `Hy3DExportMesh`.
Bypass the legacy texture branch unless the task explicitly asks to compare it.

### Pixal3D path

Run the included wrapper inside the verified isolated Pixal3D WSL environment:

```bash
export PIXAL3D_ROOT=/path/to/Pixal3D            # your WSL checkout
python workflows/geometry/pixal3d/run_pixal3d.py \
  --image /path/to/authority-cutout.png \
  --output /path/to/candidate.glb \
  --resolution 1024 --seed 42 --extra-targets 100000
```

`--extra-targets 100000` also writes `candidate-v100000.glb`: the same model,
simplified by Pixal's own exporter (the skiff came to about 98k triangles). Use
it as the game mesh rather than reducing the dense one with `remesh` or
`reduce-mesh`; both lose Pixal's hard edges. Level both with one transform
(`scripts/blender/level_pair.py`), then bake the dense shape onto the game mesh
after painting with `bake-shape`. A single picture leaves hidden parts to the
generator, so generate a few seeds (about 2.5 minutes each) and pick by fixed
views: seed 42 of the skiff left a hole in the floor that seed 45 did not.

The RGBA alpha mask is mandatory. Promote neither path until neutral fixed
front, three-quarter, side, and back clay views pass identity, anatomy,
construction, visible-part count, hands/feet, and side-depth review.

## Stage 3 — topology and UV contract

Promote one high-resolution geometry authority without overwriting it. Derive
the runtime mesh. Preserve meaningful loops and use coherent islands per body
part. The legacy per-patch xatlas layouts produced hundreds of tiny islands,
seams, specks, and face pixels on clothing; do not reproduce them merely
because an older script exists.

Run `scripts\run_semantic_cleanup.ps1` first. It accepts only the exact
human-approved modeling mesh, writes a separate native Blender derivative, and
requires identical topology after reopening the file. GLB is review transport,
not an editable topology authority: it may split shared vertices at face-corner
normals. Cleanup can weld coincident vertices, remove degenerate or loose
geometry, and recalculate normals; it cannot invent or remove semantic parts.

The V1 cohort contract is unwaived: no more than 15,000 vertices and 20,000
triangles per runtime asset. A mechanically under-budget remesh is still a
rejection if fixed clay views lose the approved silhouette, face, hands, or
construction details.

### Generated surfaces are rebuilt, not collapsed

An AI geometry surface is marching cubes. It has no edge loops, no flat regions
and nothing an edge collapse can hold on to, so collapsing it directly does not
remove its noise -- it compresses it into slivers and spikes. Measured on the
Trial Lantern (2026-09-20): a direct feature-QEM collapse to 20,000 triangles
came back visibly creased and pocked across the roof and shoulders, and its
wireframe was a soup of slivers. `scripts\run_voxel_qem_reduction.ps1` on the
same staged mesh gave 9,000 vertices and 18,000 triangles in fourteen seconds,
with an even wireframe and a surface the artist accepted on sight. The budget
was never the problem, and raising it would not have helped.

So: **rebuild a generated surface before collapsing it.** Reach for the
feature-QEM challenger only where a person chose the topology and rebuilding
would throw their choices away.

`scripts\run_feature_qem_reduction.ps1` is a one-shot diagnostic challenger
for an approved native cleanup authority. It protects high-curvature and dense
detail regions during collapse, refuses to overwrite an attempt, and measures
symmetric surface deviation. Its output is not automatically production
retopology: fixed-view appearance and deformation-aware edge flow retain veto
power. The female V4 trial proved that low surface error can still leave a
faceted, all-triangle mesh unsuitable for humanoid deformation.

After a materially acceptable candidate exists, create the immutable approval
receipt before promoting `production_retopology`:

```powershell
rac retopology-receipt <workspace> <cleaned.blend> <runtime.blend> <report.json> `
  --view <matcap-front.png> --view <matcap-three-quarter.png> `
  --view <matcap-side.png> --view <matcap-back.png> `
  --topology-view <wireframe-front.png> `
  --topology-view <wireframe-three-quarter.png> `
  --topology-view <wireframe-side.png> `
  --topology-view <wireframe-back.png> `
  --deformation-topology-reviewed `
  --approved-by <human-name> --note <review-note>
```

`--deformation-topology-reviewed` is the reviewer's explicit attestation that
joint edge flow was inspected in the wireframe views; the command refuses an
articulated kind without it, and static props omit it. When the user has
expressly delegated the visual gate to an agent, pass `--authorization
<review-delegation.v1.json>` alongside an automation reviewer name; the ledger
then requires that hash-bound delegation (see the delegated-review exception in
`docs/PIPELINE.md`).

The ledger revalidates the receipt instead of trusting the command that wrote
it. It requires exact semantic-cleanup lineage, the workspace vertex/triangle
budgets, a closed surface, hash-bound fixed views, and identified human review.
Articulated assets additionally require at least 80% quads and four hash-bound
wireframe views for explicit deformation-topology review; an all-triangle
proximity result or a percentage-only face-pairing result cannot pass.

The user preferred the voxel fallback over destructive direct vertex cutting
when the ninja arm became faceted. Use it only as a reviewed repair derivative.

### Geometry from a single image

When you have only the approved picture, write the request with
`"mode": "single_view"` and one `primary` input whose hash equals the source
authority; `scripts\run_hy3d_geometry.ps1` then hash-pins and runs
`run_hy3d_single_view.py` (Hunyuan3D-2, `hunyuan3d-dit-v2-0`). The multiview
route remains preferable when consistent front/left/back guidance exists,
because a single view infers the far side. Both routes stop at the same
fixed-view modeling approval. See `docs/AI_STAGES_SETUP.md` for the request
shape and VRAM needs.

### Detail acquisition: heads and hands (every humanoid)

A whole-body acquisition gives the head and the hands a small share of the
generator's resolution. On CH-03 Raider (2026-11-01) that meant lumpy hair,
shallow eyes and a generic face that no fit, projection or paint could rescue,
and gloves whose fingers were fused to the tips. Acquiring each detail alone
from a close crop of the same reference fixed both: modeled eyelids, lips,
ears and hair strands; long fingers separate to the knuckles and the gauntlet
cuff. Treat it as part of Stage 2 for every humanoid, after the body passes
its silhouette review and before texture:

1. Crop and upscale the detail from the approved reference. The crop writes a
   lineage JSON binding the box, the upscaler and the source hash:

   ```powershell
   & C:\Comfy\python_embeded\python.exe scripts\detail_crop.py <reference.png> `
     <work>\<asset>\detail\<asset>-hand-r-crop-x4.png --box X0 Y0 X1 Y1
   ```

   Frame the head from crown to collar; frame one hand with its cuff. Acquire
   one hand and mirror it for the other unless the two differ in design.
2. Register it as its own workspace (`rac new <asset>-hand-r <crop> --kind
   humanoid`) and run one single-view request through
   `scripts\run_hy3d_geometry.ps1` (seed 42, 50 steps, octree 512). Review it
   in clay from the front, back, side and, for hands, from below the
   fingertips: fingers must be separate to the knuckles.
3. Paint it alone with `scripts\run_hy3d21_texture.ps1` against the same crop
   (12 views, 768, studio runner, 4096 atlas), after reducing and unwrapping
   it with a material on the mesh. Unlike the shallow heads of 2026-09-05,
   the detailed geometry lets the views agree on where the features are.
4. Attach it to the painted body: drop the body's own detail faces, align by
   measured landmarks (head: nose tip, ear width, nose-to-crown; hand: size
   from the crop's silhouette in reference pixels, then the old glove's axis
   and wrist), and cut the detail's extra bust or forearm. The Raider
   prototypes are `scripts/revamp/raider/place_head.py` and `place_hands.py`;
   their lessons are in `docs/RAIDER_REVAMP.md`.

The detail is a candidate like any acquisition: it waits for its own modeling
and texture gates, and the assembled character waits for the four-view review.

### Automatic part map (every geared humanoid)

The layered build (overlay shells over continuous cloth, rigid armour, the
material classes) starts from a 2D map of the reference: which pixel is jacket,
plate, strap, belt, pouch, glove, face. The Raider's map was clicked by hand
(`scripts/revamp/raider/sam_parts.py`). `scripts\auto_part_map.py` makes it
automatically from the vocabulary in `profiles\segmentation\humanoid-gear.json`:

```powershell
& C:\Comfy\python_embeded\python.exe scripts\auto_part_map.py <reference.png> <out-dir>
```

It writes `parts.npy` and the projection inputs (`part-ids.npy`,
`body-ids.npy`, `part-names.json`, `landmarks.json`), plus `review.jpg` and
`detections.json`, which lists every candidate box and why it was kept or dropped.
In the Raider build, `build_raider.ps1 -From labels -To labels` runs it and
then `project_parts.py` onto the dense acquisition, and `-From parts` picks the
run's labels up from there.

Models (open source; download once, outside the repository):

| Model | Licence | Where | Weights SHA-256 |
| --- | --- | --- | --- |
| Grounding DINO base (`IDEA-Research/grounding-dino-base`, run by `transformers`) | Apache-2.0 | `C:\Comfy\rac-models\grounding-dino-base` or `RAC_GROUNDING_DINO` | `5548f844…ed21` (full sums in the folder's `SHA256SUMS`) |
| Segment Anything ViT-B (`sam_vit_b_01ec64.pth`) | Apache-2.0 | ComfyUI's `models\sams` or `RAC_SAM_CHECKPOINT` | already on the workstation |

How it decides (each rule was measured against the Raider's hand map; the
reasons are in `docs/DECISIONS.md`, 2026-11-03):
- one joint query with every part's phrase, so parts compete for each box, plus
  each part's own fuller prompts ("a shoulder pad" finds shoulder plates);
- a box bigger than its part can be, or centred outside the part's height zone, is dropped;
- weak duplicates of an overlapping box of the same part are dropped, and a
  part the character has one of keeps only its best box;
- SAM masks are clipped to their box, and a thin part (strap, belt) keeps only
  the thin parts of its mask;
- a paired part found on one side only is looked for in the mirrored box and
  kept when the mask there is a similar size and colour;
- higher layers win overlaps, except that a smaller part nested in a bigger
  mask at most one layer above it wins inside it;
- cloth pixels with the face's colour that touch the face or skin are bare skin.

Measured 2026-11-03: 0.889 pixel agreement with the Raider's hand map
(it was 0.548 with one query per part). Gloves, hair, beard, buckle, knee pads,
pouches, face, trousers and the thigh holster are above 0.89 IoU; straps
(0.34) and plates (0.60) are the weak parts. The CH-03 Guard, Scout and
Bulwark looks, never used for tuning, came out with their chest plates,
harnesses, pouches, knee pads and gloves in place
(`docs/evidence/auto-part-map-raider-20261103.jpg`,
`docs/evidence/auto-part-map-looks-20261103.jpg`, numbers in
`docs/evidence/auto-part-map-20261103.json`).

Known gaps: there is no bracer part, so bracers read as jacket or strap; a
cloth wrap on a forearm reads as skin; a second shoulder plate unlike its twin
can be missed; a strap crossing a plate goes to the plate. The map is a gate:
look at `review.jpg` and `project_parts.py`'s four `parts-*.png` views before
`-From parts`. To add a part, extend the vocabulary and the downstream scripts'
palettes and part sets (`docs/AGENT_TASKS.md`, item 9).

## Stage 4 — existing-mesh PBR texture

Follow the [canonical character surface workflow](CHARACTER_SURFACE_WORKFLOW.md)
for diagnosis, registered repair, material identity and consumer replay. After
removing or replacing geometry, inspect the newly exposed paint and normals
for surviving outlines/shadows before calling that region finished.

For scoped finishing of an already acquired character or prop, start with
[`rac polish-init` / `rac polish`](POLISH_WORKFLOW.md). This route captures
registered references, pauses explicitly for AI editing, then resumes mapping,
material response and packed review. It can also restore reviewed donor faces
or repack one primitive while transporting its maps and rig data. The Raider
examples replay frozen inputs without new inference. Whole-mesh acquisition
and fresh PBR generation still use the routes below.

If a material edge stands proud, first compare the pre-cut acquisition with the
export at a grazing angle. Where a strap, buckle or hem already has the right
shape on the acquisition, keep the selected labels on one surface. Reproject
the labels for material response; do not extrude them a second time. Use the
[fitted surface recipe and inspection boxes](RAIDER_SEAM_REPAIR.md#fitted-outfit-for-framewright).
Real detachable pieces still need their own complete geometry and backing.

If the paint and topology are already approved and only the surfaces react
incorrectly to light, use the CPU [material sweep](MATERIAL_SWEEP.md). It
accepts part masks on a shared atlas; it does not require repainting or a new cut.

For large natural scenery, a reference-conditioned repeating surface material
is also an explicit mapping route after AI geometry and topology approval.
Do not stretch a small unique atlas over a twelve-metre formation or shrink
its declared dimensions to pass density. `package_character_texture.py
--address-mode repeat` measures the actual repeated material with wrapped
within-triangle sampling and unwrapped UV-edge island counts; legacy atlas
sampling remains the default. This changes no profile thresholds. Preserve
the geometry/UV derivation and material-source hashes, identify constant data
channels honestly, and inspect all lit/unlit views plus native vertex splits.
It is not Hunyuan-Paint output and must not be described as such. Check scene
instance scaling separately; scaled-up instances reduce world texel density.

### Default: Hunyuan3D-Paint 2.1

The tested local environment remains under the legacy studio. Use the wrapper
from the compiler repository; it verifies the exact legacy runner hash, checks
VRAM, and requires a topology/UV report without auto-retrying:

```powershell
.\scripts\run_hy3d21_texture.ps1 `
  -Mesh <approved-runtime-mesh.glb> `
  -Reference <front-reference.png> `
  -OutputObj <output.obj> `
  -Views 6 -Resolution 512
```

The bundled Python file is a provenance copy. The PowerShell wrapper invokes
the identical, hash-verified runner beside its tested `upstream/` and `models/`
directories in the legacy studio. Do not invoke the bundled provenance copy
directly or edit its path logic ad hoc mid-experiment.

It requires at least 21 GiB free VRAM and refuses face-order, geometry, or UV
drift beyond `1e-6`. The studio runner releases stages by default, needs
10.5 GiB (a 12 GB card) at every setting up to 12 views × 768 and an 8192 sheet. Its maps differ invisibly
from a resident run; `-KeepStagesResident` reproduces older attempts. See
"Painting with less VRAM" in `AI_STAGES_SETUP.md`. A validation JSON is required even if upstream teardown
returns an error. Never auto-retry.

For a new, specifically justified diagnostic attempt, pass
`-DiagnosticsDir <new-directory>` to `scripts/run_hy3d21_texture.ps1`.
It captures the normal and position controls, raw AI multiview PBR images,
enhanced views, bake coverage, and pre/post-inpaint atlases. This is for locating
a correspondence failure before changing the method; it does not turn a repeat
of a visibly rejected candidate into useful evidence.

Retained full-size bake buffers can be recovered without enlarging the smaller
exported JPEGs. `scripts/recover_fullsize_paint_maps.py <paint-dir> <new-output>`
defaults to `painted.*` and `<paint-dir>/diagnostics`; use `--stem plant` and
`--diagnostics <separate-dir>` when the run used another basename/layout. It
checks geometry/UV validation and downsample correspondence before copying the
original albedo and splitting the authored data channels. This is not an
inference retry, and it does not erase an abnormal process-exit receipt.

### Head-detail paint pass (same UVs, second paint)

A full-body paint at 512 px gives a 1.85 m character's head about fifty
pixels per view. `scripts/blender/extract_head_transport.py` cuts the head
and neck faces out of the UV authority with their exact UVs, so a second
`run_hy3d21_texture.ps1` run on that transport fills every view with the
head; `scripts/composite_head_paint.py` then bakes the recovered head maps
onto the body's (possibly repacked) layout and blends them over the body
maps inside the geometry-derived head region, byte-preserving everything
else. The reference must show only head and neck: a crop that kept a strip
of armour made the painter spread armour colour over the whole head.

Measured result on `sunset-ayric-v2` (2026-09-05): the pass paints skin,
hair, eyes and beard at ten times the earlier resolution, but on that
shallow-featured 19.6k-triangle head the views disagreed about where the
face was and the bake carried doubled eyes. Rejected under the landmark
rule. The tooling is validated; the method needs a head with real sockets
and a nose, or a single registered front image, to place features.

Hunyuan3D-Paint was the strongest full-body PBR base, not an accepted face
solution. It improved clothing and material response while degrading facial
identity. Review unlit albedo and lit PBR separately.

### Large models: paint again in sections (same UVs)

The painter sees a whole model through twelve 768-pixel views whatever its
size. Measured on the Frastown pieces (2026-11-24): a 45 cm dock claw gets
about 0.6 mm of surface a painted pixel and reads as immaculate; a 2.2 m
skiff gets about 3 mm and reads as smeared and grainy up close; a 15 m hull
gets about 2 cm. The 4096 sheet and the upscaler only stretch what the
painter saw, so a bigger atlas does not help.

`paint-sections` (`scripts/paint_sections.py`) cuts the painted model's
bounding box into a grid of sections no wider than `--section` (0.6 m, grown
to fit `--max-sections`, 12 by default), paints each section alone with the
reference cropped to where its faces fall in the picture, and lays the
sections over the first paint on the same UVs. Run it straight after the
whole-model paint, before surfaces are changed: it refuses a model with more
than one material.

```powershell
rac run-stage paint-sections --source painted.glb --output sections.glb --report sections.json `
  --reference approved.png --views 12 --resolution 768 --atlas 4096
# look first, paint nothing: the sections, their crops and the receipt
python scripts\paint_sections.py -- painted.glb sections.glb plan.json --reference approved.png `
  --cutout approved-cutout.png --plan-only
```

- Every face is painted at section scale; none keeps the first paint beside a
  section's. That boundary is a seam: the hero route's head pass leaves one on
  every prop it is run on (a 2.2 m mast, 2026-11-24: the top 22% crisp and the
  picture's dark iron, the pole below flat light putty). On a prop, paint in
  sections instead of the head pass; the head pass is for figures.
- The design comes from the first paint (`--keep-colour 0.01`, the default):
  its colour is kept exactly as painted, and the sections add only their light
  and dark finer than 1 cm. The first paint is never blurred, because a blur on
  the flat sheet reaches into unrelated neighbouring islands. With a 3 cm blur,
  the skiff's teal chips smeared and its stern went grey in wedges. A section's
  painter sees too little to
  tell iron from wood: on the AC-01.1 skiff in 45 sections, the red fins, iron
  straps and teal paint all came back as wood, and keeping the design brought
  them back with the sections' grain, nail holes and wear on them. The owner
  called the result impressive (2026-11-24).
- `--keep-colour 0` takes the sections' own colour, scaled so neighbours agree
  where both painted. That is for a single-material model whose whole-model
  paint is wrong: on the DK-04.2 mast it was light putty where the close paint
  was the picture's dark iron. Neighbours overlap by `--overlap` of a section
  and their weights sum to one on every face either way.
- The atlas padding is refilled from the nearest painted texel, so mip levels
  do not outline the islands in the first paint's colour.
- Which way the model faces in its picture is found by matching its outline
  against the figure's in every axis-aligned frame; the generator's frame
  (+X right, +Y up) is kept unless another fits clearly better. The receipt
  records the scores.
- A model shorter than `--min-length` (1.2 m) on every side is passed through
  byte for byte, with `painted: false` and `reason: shorter_than_min_length`
  in its receipt; every receipt carries `whole_model_mm_per_pixel`.
- One painter run a section, about 2.5 minutes each on the 4090 (the stage
  listing carries this as `estimate`), each needing 10.5 GiB free; a section that
  fails fails the stage, and no half-painted model is delivered.
- `--max-sections` counts sections that are painted; a cell of the grid the
  model does not reach costs nothing. Crops fit the model's extremes to the
  figure's on each axis, and are never smaller than a fifth of the figure.
- How fine: the defaults (0.6 m sections, a cap of 12) roughly halve the
  surface a painted pixel on a 2 to 3 m prop. To reach a small prop's 0.6 to
  1 mm, cut finer and overlap less: `--section 0.45 --overlap 0.2 --context
  0.05 --max-sections 48` put a 2.2 m skiff at about 0.7 mm in 45 sections.
- Each section's views are shrunk to about a texel a pixel before they are
  baked (`--bake-scale 1`, the default; 0 bakes them as upstream does). A
  section seen far finer than the sheet holds otherwise breaks its grain into
  single-texel specks. For detail that holds up at arm's length, paint the
  first paint and the sections on an 8192 sheet (`--atlas 8192` on both
  stages): a 2.2 m skiff goes from 1.75 mm to about 0.9 mm a texel at the same
  painting time. Compress for a browser afterwards; the maps are large.
- The stage gets four hours from `run-stage` unless `--timeout` says otherwise;
  every other stage gets one. A pass that was stopped anyway resumes with
  `--reuse-sections <the stopped attempt directory>`: a section the painter
  already finished from the same mesh, the same crop and the same settings is
  taken as it is, and only the rest are painted. A stage that runs out of time
  stops everything it started, so nothing is left painting on the GPU.

Finish a section-painted model with the detail bake, relief calibrated to a
steepness rather than a strength: `rac run-stage bake-detail ... --resolution
2048 --relief-tilt 6`. The same `--relief-from-paint 1` that suits a calm paint
tilted the section-painted mast's normals 41 degrees at the 90th percentile
(orange peel); `--relief-tilt 6` gave 1.3 / 6 / 23 degrees at the median, 90th
and 99th percentiles, against 1.1 / 4.5 / 19 on the finished dock claw. Edge
wear needs a curvature map as large as the base colour, so leave it off on a
4096 paint.
- Above about 4 m one 4096 sheet cannot hold the detail however well it is
  painted (a 15 m hull is about 4 mm a texel). Split such a piece into
  modules at acquisition instead.

### A hard-surface prop from Pixal3D, end to end

The route that took the 2.2 m Frastown skiff (AC-01.1) from a picture to wood
grain that holds up at arm's length. Times are from an RTX 4090.

```powershell
# 1. Geometry: a few seeds (about 2.5 min and 7.7 GiB each, in WSL), picked by fixed views.
#    A seed picks the design, not exact triangles: Pixal3D is not deterministic.
#    --extra-targets also writes the game mesh, from the same generation.
python workflows/geometry/pixal3d/run_pixal3d.py --image cutout.png --output pixal.glb `
  --resolution 1024 --seed 45 --extra-targets 100000

# 2. Level the dense mesh and the game mesh with one transform, at the real length
#    (the model's longest side). A tall piece (lantern, ladder, column) needs --up longest,
#    a panel standing on its edge --up middle; --flip turns one standing on its head.
blender -b --factory-startup --python scripts/blender/level_pair.py -- `
  2.2 level.json pixal.glb dense.blend pixal-v100000.glb low.blend

# 3. UVs, then the first paint on an 8192 sheet (about 3 min).
rac run-stage uv-unwrap --source low.blend --output uv.obj --report uv.json
rac run-stage texture --source uv.obj --output painted.glb --report painted.json `
  --reference approved.png --views 12 --resolution 768 --atlas 8192

# 4. Find the parts (a few minutes: 24 renders, then Grounding DINO and SAM on the GPU),
#    and look at labels-review/ before going on: every face in its part's colour.
rac run-stage label-parts --source painted.glb --output labels.npz --report labels.json `
  --vocab skiff-parts --reference approved.png

# 5. Paint by parts: each part alone, from the picture with the other parts masked out,
#    laid on its own faces (about 3.5 min a piece; the skiff is hull, seat, fins).
rac run-stage paint-parts --source painted.glb --output parts.glb --report parts.json `
  --parts labels.npz --reference approved.png --views 12 --resolution 768 --atlas 8192

# 6. Sections at the finer cut, over the parts (about 4 min each at 8192; the skiff had 32).
rac run-stage paint-sections --source parts.glb --output sections.glb --report sections.json `
  --reference approved.png --views 12 --resolution 768 --atlas 8192 `
  --section 0.45 --overlap 0.2 --context 0.05 --max-sections 48

# 7. Relief from the paint, then the dense shape under it (a few minutes each).
rac run-stage bake-detail --source sections.glb --output detail.glb --report detail.json `
  --resolution 2048 --relief-tilt 6
rac run-stage bake-shape --source detail.glb --output shape.glb --report shape.json --dense dense.blend

# 8. A browser copy: specular reset, then 8192 JPEG (the skiff came to 51 MB).
rac run-stage browser-payload --source shape.glb --output payload.glb --report payload.json
rac run-stage compress-textures --source payload.glb --output packed.glb --report packed.json `
  --colour-size 8192 --data-size 8192 --quality 92 --texture-format jpeg
```

Keep `payload.glb`, with lossless 8192 maps, for Unreal. A section pass that is
stopped resumes with `--reuse-sections <its attempt directory>`, and a change
that only affects how sections are laid (for example `--keep-colour`) reuses
every painted section and costs minutes, not hours. Sections depend on the mesh
and their crop of the picture, not on the base under them, so sections painted
over the first paint are reused over the parts too; `paint-parts` likewise
takes `--reuse-parts <its attempt directory>`.

**The part vocabulary.** `profiles/segmentation/skiff-parts.json` names the
skiff's parts: a base part that every unclaimed face belongs to (the hull,
with its struts and iron straps), and the parts to find, each with the phrases
the detector is asked, the largest share of the model's box one may take, and
whether its pieces are painted `together`. For another model, copy it and name
its parts. Only name a part the detector finds in most views: the skiff's
struts and straps were found unreliably and paint well with the hull. A part
that repeats and is thin (the skiff's two fins) is painted together; painted
one at a time, one fin came back pale and the other marked.

`label-parts` needs, besides Blender, a Python with torch, transformers and
segment_anything (ComfyUI's portable one), Grounding DINO base and SAM ViT-B,
both Apache-2.0. Name them with `--torch-python`, `--detector` and `--sam`, or
`RAC_TORCH_PYTHON`, `RAC_GROUNDING_DINO` and `RAC_SAM_CHECKPOINT`;
`rac run-stage --list` says what is missing. The labelling is a candidate: look
at the review views in `labels-review/` before painting. A fin labelled as hull
would be painted from the hull's picture.

What painting by parts fixed on the skiff, against revision 8 (sections over
the first paint): the strut that carried the fin's red is wood, the seat has
the iron edging and rivets of the picture, and the fins are red, cream and red
as drawn. One fault remains: the hull's teal paint is solid bands where the
picture has chipped paint over wood. The hull is painted whole at 2.2 m, too
coarse for chips, and the sections add only light and dark.

### Challenger: TRELLIS.2

```bash
cd /mnt/c/path/to/reference-asset-compiler       # your clone, seen from WSL
source /path/to/envs/trellis2/bin/activate      # your TRELLIS.2 environment
export PYTHONPATH=/path/to/TRELLIS.2
python workflows/texture/trellis2/run_trellis2_texturing.py \
  /path/to/approved-runtime-mesh.glb \
  /path/to/authority-cutout.png \
  /path/to/trellis-candidate.glb \
  --resolution 512 --texture-size 2048 --seed 42
```

The full-body trial was technically topology-safe but visually rejected for
facial bands, identity loss, and triangular speckling. Use only as an isolated
challenger or bounded semantic donor. The ninja's best legacy texture combined
a Hunyuan body with a constrained TRELLIS head donor; that does not justify
unmasked whole-body replacement.

### Final material pass (every character)

The painter gives every surface one kind of paint, so up close metal, leather and cloth all read as painted
plastic. Every character mesh gets the material pass before texture review:

```powershell
& $blender -b <rigged.blend> --python scripts\blender\finish_materials.py -- <out.blend> <maps-dir> `
  --face-parts <face-parts.json> [--profile profiles\materials\character-finish.json] [--object <body>] [--material <painted>]
```

`face-parts.json` names each body face's part; the profile maps parts to material classes (metal, leather, cloth,
skin) and gives each class its relief, roughness, metalness, edge wear and grime. Patterns are evaluated in 3D, so
there are no seams at UV island edges, and the painted colours are modulated, never replaced. It writes a base
colour, a packed occlusion/roughness/metal map and a tangent-space normal map, wired into the material. A normal
map needs its own texture asset in the engine import (on the Raider it first shared the roughness/metal asset's
name and turned the whole body into metal). Review it with back-face culling, in Blender studio light and in the
engine.

This pass and the CPU [material sweep](MATERIAL_SWEEP.md) overlap, so pick one per revision. The material pass works on
the rigged blend, reads edges and creases from the geometry and may modulate the paint. The sweep works on an already
packaged GLB whose paint is approved: it changes only how each surface answers light and leaves base colour, geometry
and UVs byte for byte. Running the sweep over maps this pass wrote lays a second relief on the first.

### Texture acceptance

Render beauty evidence with the `calibrated` display profile:

```powershell
& $blender -b --factory-startup --python scripts\blender\render_turnaround.py -- `
  <painted.obj|glb> <new-fixed-views-dir> 1024 albedo smooth calibrated
```

The factory AgX transform at exposure 0 washed the cat's saturated fur to
salmon pink and clipped a third of the subject; it is kept only as `factory`
for reproducing old evidence and must not decide a texture gate.

If a lit view shows a hard highlight that the unlit albedo does not, check the
roughness map before blaming the art. `scripts/clamp_region_roughness.py`
lifts glossy texels inside a geometry-derived region mask to a floor as a
versioned derivative; it never touches base color, metallic, mesh, or UVs.

Once the reviewer passes the lit views, package an unrigged character with
`scripts/package_character_texture.py` (props use
`scripts/package_accepted_texture.py`). It stages the accepted maps as PNG,
binds them to the unchanged UV authority, applies only a recorded uniform
height and floor-origin transform, runs the texture gate against the skeleton
profile, and renders calibrated fixed views. A gate waiver must name the human
who accepted the measured debt. Then record `unwrap_and_bake` and
`texture_approval` with `rac promote` and the exact evidence files.

Reject displaced/stamped eyes, doubled scarf lines, a U under the chin, face
pixels on trousers, random bright specks, baked lighting, projection outlines,
and atlas seams. Facial landmarks must align to the modeled eye sockets, nose,
mouth, jaw, and hairline. The female remains the canonical failing example.

## Stage 5 — rigging

For a new humanoid, the preferred authoring tool is the user's licensed
Auto-Rig Pro installation in a compatible Blender. The extension is not bundled.
Live preflight on 2026-08-31 proved Auto-Rig Pro 3.74.40 operational in Blender
5.2.1, including Smart detection, Match to Rig, Bind, and the UE5 spine/neck/twist
controls. Run `scripts\workflow_doctor.ps1` to repeat that check without saving
preferences or changing an asset. The remaining blocker is a portable,
asset-neutral production driver. A candidate-only A-pose driver now lives at
`scripts\run_arp_rig_candidate.ps1`; it preserves rest geometry, uses explicit
checked-in body marker ratios, requires source-hash-bound and reviewer-approved
wrist plus per-digit joints, binds through a welded proxy, caps influences at
four, and refuses overwrite. The retained legacy driver still contains
field-scout-specific hand, clothing, material, and corrective assumptions that
must not leak into this generic stage. Deformation, ARP game export, Manny FBX,
and UE gates remain mandatory before promotion.

```powershell
.\scripts\run_arp_rig_candidate.ps1 `
  -InputMesh <approved-existing-mesh.glb> `
  -HandLandmarks <reviewed-source-bound-hand-landmarks.json> `
  -OutputDirectory <new-empty-candidate-directory>
```

The landmark file follows `schemas/hand-landmarks.schema.json`. It is not a
convenience hint: its source hash and reviewer approval are promotion evidence.

The single entry point for the rig stage is either-or:

```powershell
.\scripts\run_rig_candidate.ps1 -InputMesh <approved_mesh.fbx> -Profile ue5_manny|mascot_biped_tail `
  -OutputDirectory <new dir> [-Backbone auto|arp|landmark] [-HandLandmarks <reviewed.json>] `
  [-RingProfile <fitted-profile.json> -BindingReport <texture-payload-binding.json>]
```

It probes Auto-Rig Pro, takes it for humanoids when operational and reviewed
hand landmarks are supplied, and otherwise derives landmarks
(`derive_humanoid_landmarks.py` from the mesh and Manny's proportions,
`derive_mascot_landmarks.py` from the reviewed ring guides), builds and binds
with `rig_from_landmarks.py`, and runs `gate_rig.py` and `deform_test.py`.
`rig-route.json` records the route. The individual scripts below remain
callable when you need one step.

For a mascot on `mascot_biped_tail` (the `blender_custom_rig` backbone), the
portable route is landmark-first:

```powershell
& $blender -b --factory-startup --python-exit-code 1 --python scripts\blender\derive_mascot_landmarks.py -- `
  <prod>\<asset>_production.fbx <retopo>\joint-guides-*\fitted-profile.json `
  <prod>\texture-payload-binding.json <work>\rig\mascot-landmarks-v1
& $blender -b --factory-startup --python-exit-code 1 --python scripts\blender\rig_mascot_biped_tail.py -- `
  <prod>\<asset>_production.fbx <work>\rig\mascot-landmarks-v1\mascot-landmarks.json `
  profiles\skeletons\mascot_biped_tail.json <out>\<asset>_rigged.fbx <out>\rig-candidate.json
```

Every joint is derived from reviewer-passed ring centers and payload
cross-sections; review the overlay renders before trusting the bones. Then run
`gate_rig.py`, `record_rig_and_skin.py`, `deform_test.py`, and
`record_deformation.py` exactly as for a humanoid.

AniGen is included only as a challenger. It generates a replacement mesh and
skeleton from the authority image; it does not skin the topology that already
passed modeling and texture approval:

```bash
python workflows/rigging/anigen/run_anigen_candidate.py \
  --upstream /path/to/AniGen \
  --image /path/to/authority.png \
  --output-dir /path/to/candidate \
  --seed 42
```

A generated skeleton must pass the named profile, parent chains, maximum four
influences, side/facing, deformation, FBX round trip, and UE import gates. Do
not accept a random hierarchy because it poses once.

## Stage 6 — compile and UE5 proof

Once an authority FBX and material textures exist:

```powershell
.\scripts\compile_asset.ps1 -Recipe .\recipes\field-scout-male.json
# or the complete retained cohort
.\scripts\compile_all.ps1
```

Then follow `docs/COMPILER.md` for UE import, exact payload verification, map,
and cook.

To review characters in motion, rebuild the gallery and give every placed
skeleton the Manny idle:

```powershell
$env:RAC_ROOT = (Get-Location).Path
& UnrealEditor-Cmd.exe .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\build_gallery_level.py" -unattended -nop4 -nosplash -stdout
& UnrealEditor-Cmd.exe .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\setup_gallery_playable.py" -unattended -nop4 -nosplash -stdout
& UnrealEditor.exe .\work\ue5-validate\RacValidate.uproject -game -windowed -ResX=1920 -ResY=1080 -NoTextureStreaming
```

The second script builds IK Rigs from bone names, exact-maps chains (a
mascot tail stays unmapped), batch-retargets `MM_Idle`, and writes
`work/ue5-gallery-idle.json`. The project's default game mode is the Third
Person template, so `-game` drops the reviewer in as Manny. The compile path is verified; it should not be replaced by ComfyUI.

### Native material fallback check

If unwanted relief appears only in UE, inspect the actual material graph and
fallback textures before regenerating the atlas. On UE 5.8.2 the installed
`/Engine/EngineMaterials/DefaultNormal` contains noisy tiled-wall relief; it
is not a neutral tangent-space normal. The v002 importer master uses an
explicit `(0,0,1)` normal when `HasNormal=0`, and samples an authored normal
only when that manifest slot is supplied. The old master is preserved;
existing accepted assets are not automatically migrated. Versioned material
repairs need their own native visual/lineage review, not the same-material
LOD-reduction revision gate.

## Historical character texture task decision

The retained character texture defects below are upstream atlas/projection
defects; that diagnosis is not a blanket claim about every UE material. The
custom character is currently parked in favor of the Manny demo. If resumed,
the next experiment is:

1. coherent semantic UV islands on the final-scale runtime mesh;
2. de-lit source/reference and base color;
3. Hunyuan3D-Paint 2.1 body PBR candidate;
4. head-only, UV-aware identity projection constrained to head geometry;
5. fixed unlit face/body/edge review;
6. only then compile and UE verify.

Do not patch the female by another whole-face stamp or image-space heuristic.

## Reusing a detailed AI head without another portrait stamp

The Ayric workshop follow-up validates a separate existing image-conditioned head
with real facial geometry, source-bound body trimming, reference-pose socket fit,
and bounded neck colour/normal transport. The approved face remains untouched.
Use `CHARACTER_HEAD_AND_NECK.md` and its recipes/runner rather than copying values
into an ad-hoc Blender script. Different characters require new measured bounds
and source hashes. Inspect native views and cooked gameplay; a semantic replay
or vertex budget alone does not approve appearance. Keep auxiliary normal data
constant outside its support to avoid unnecessary native vertex splits.

## Building editable architectural modules

See [MODULAR_SCENE_ASSETS.md](MODULAR_SCENE_ASSETS.md) for source-bound extraction,
independent architectural acquisition, measured fitting and full-room review.
The extraction receipt proves polygon accounting; it does not approve a cut,
cap a seam or certify a usable room. Review the actual assembled scene.
