# Decisions, failures, and retained lessons

This is a concise experiment record for future agents. It captures the useful
rationale behind the current workflow so rejected paths are not repeated.

## Accepted decisions

### Authority first

Every asset starts with an explicit approved image or turnaround. Visual
identity, proportions, construction, and style are judged against it. A
plausible generic asset is not a successful reconstruction.

### Isolated AI challengers

Pixal3D, Hunyuan3D, TRELLIS.2, AniGen, and similar tools are candidate
producers, not automatic winners. Preserve versions, settings, seeds, logs,
and outputs independently. Promote only after fixed-view comparison.

### Image-conditioned geometry is mandatory

For reconstruction from an image, the approved image must be an actual input
to an AI geometry or mapping stage. Blender may clean, retopologize, unwrap,
bake, rig, deform, and verify that AI-derived candidate. It may not replace a
failed AI acquisition with an eyeballed manual or procedural approximation.
When acquisition fails, retain the rejection and repair or reroute that stage.

### Modeling before texture before rig

Trying to correct broken geometry through projection or skinning produced
confusing regressions. Each stage now has a hard approval boundary.

### Voxel fallback for damaged reduction

Direct vertex cutting/reduction created visible arm cuts and faceting. The
user preferred the voxel-based fallback because it produced a smoother,
cleaner form. Keep the high-resolution authority and compare any reduction in
fixed views; voxel remeshing is a fallback, not blanket permission to erase
garment detail.

### Skeletons are runtime contracts

Humanoid success requires compatibility with the chosen UE skeleton and its
animation set. A random autorig that happens to deform is insufficient. The
fox correctly uses a separate mascot skeleton profile.

## Rejected approaches

### Eyeballed procedural Blender reconstruction

The source-locked guitar diagnostic manually interpreted the reference and
procedurally authored a cleaner replacement. Its visible structure was better
than the melted generated mesh, but the image never conditioned geometry. The
user rejected that method. Its scripts and approval evidence were retired; do
not repeat or revive it as an authority candidate.

### Primitive or manually approximated replacements

Simplified handcrafted substitutes lost proportions and source-specific
detail. They are useful only as diagnostic controls, never as authority
challengers when fidelity is the goal.

### Front-view-only approval

Several candidates looked convincing from the front while sides showed broken
depth, limbs, waist continuity, or clothing. Require front, three-quarter,
side, and back review under fixed cameras.

### Flat facial stamping

Repeated face projections caused doubled eyes, displaced noses, seam lines,
double scarf contours, and an uncanny U-shaped region beneath the chin. The
texture must be fitted to topology and semantic landmarks, with seam-aware
blending and separate base-color/PBR inspection.

### Coarse eye geometry or paint

Early eye repairs created white specks, star shapes, temple artifacts, or
invisible one-sided polygons. The ninja's authored face-forward axis is `+Y`,
not the assumed `-Y`. The retained V24 solution used smooth head-weighted eye
patches, correct ray direction, and reversed fan winding for UE one-sided
culling. Do not reintroduce the coarse material-paint approach.

### Texture-only guitar repair

Painting over poor geometry did not produce credible frets, fretboard,
headstock hardware, pickups, or material response. The resulting bright specks
and rudimentary silhouette were rejected. Structural features must exist in
geometry before texture polish.

### Unchecked visible-part counts

The fox briefly acquired a duplicate tail. Exact visible-part counts are now a
mascot modeling gate and must agree with the authority image and skeleton.

### Import equals production-ready

A successful FBX/UE import proves only that the payload is readable. It does
not prove animation compatibility, deformation quality, persistence in the
map, collision, scale, or cooked runtime behavior.

### Gates that measure one surface at a time

field-scout-male's eyeballs shipped 6 cm in front of his face through every
gate the compiler runs. Both surfaces were individually valid -- correctly
wound, wrapped and textured -- and deviation, silhouette IoU, UV coverage and
bake coverage each measure one surface on its own. Relative placement between
two valid surfaces is a defect class none of them can see, and only a
three-quarter close-up found it. See `docs/DEFECTS-CLOSEUP-REVIEW.md`.

### Editing mesh vertices on a mesh that has shape keys

With shape keys present, `mesh.vertices[].co` is not what the object shows.
Entering edit mode writes Basis back over it, so a geometry repair applies,
reports success, and silently does nothing. field-scout-male carries a Basis
plus four corrective elbow blendshapes; the other three characters carry none,
which is exactly why the repair looked correct when tested in isolation.

### Repairs aimed by geometry alone

"A small shell sitting outside the body it belongs to" describes
field-scout-male's floating eyeballs, ninja-man's shoulder plates and
fox-mascot's flat eye decals equally well. The first two-thirds of that list
is wrong. Geometric repairs of this kind are opt-in per asset, with the
magnitude measured rather than configured.

### A cooked build that logs clean

`M_RAC_CharacterMaster` shipped a packaged build in which every character
rendered flat grey, with correct geometry and correct normals, while a static
prop in the same frame was fully textured. The material had never declared
`used_with_skeletal_mesh`, so that shader permutation was never cooked and the
engine fell back to its default material. The editor hides this completely --
it sets the flag and compiles the shader on demand -- and the cook, the import
verification and every asset gate all passed, because none of them is wrong.

A packaged build is not verified by its log. It is verified by a frame taken
from inside it.

### Texture evidence rendered through a filmic transform

The cat's attempt006 atlas was rejected as washed out and salmon pink. The atlas
was fine; the fixed-view renderer used Blender's factory AgX transform and a
light rig that clipped a third of the subject, and the OBJ importer read the
metallic and roughness data as sRGB with doubled specular. Beauty evidence for a
texture decision must use a neutral transform at calibrated exposure with data
maps read as data. `render_turnaround.py`'s `calibrated` profile does this; the
`factory` profile is retained only to reproduce historical evidence, which is
not comparable and must not be mixed into a texture verdict.

### Retopology guides reused as rig pivots

The cat's fitted joint rings were accepted as retopology support guides, and
the fitter had moved the two shoulders by different amounts (0.17 m apart after
mirroring) on a payload that is bilaterally symmetric. Reused verbatim as bone
pivots they would have produced a lopsided skeleton. Ring centers are a good
source-bound starting point for joints, but limb pivots must be mirrored about
the measured midline and the raw values kept for audit.

### Compiled skeletons carry a 100x root scale

Every character the compiler exports arrives in UE with bone offsets in metres
under a root bone (or armature node) scaled by 100, while the mesh binds and
measures correctly in centimetres. It is Blender's FBX unit handling under
`apply_scale_options="FBX_SCALE_ALL"`, and it is invisible in bind pose and to
every gate. It surfaced the first time an animation was retargeted onto these
skeletons: the IK Retargeter's pelvis-motion and IK ops write component-space
centimetres into that metre-scaled local space, and all nine gallery
characters were hoisted 50 to 90 metres into the sky, reading as "not visible".
`scripts/ue5/setup_gallery_playable.py` measures the ancestor scale, omits the
IK ops, and rescales the pelvis track afterwards. The durable fix is to export
skeletons with unit root scale and centimetre bone offsets, which touches the
verified compile path for every asset and is deliberately deferred.

### Retarget-pose alignment is not a global switch

Auto-aligning every target bone to Manny scored best on segment direction and
looked worst in the level: legacy faces pitched down because their head and
spine bones tilt differently from Manny while the faces already look forward.
Limbs are aligned, because limb rest poses differ legitimately between
skeletons; spine, neck and head keep the reference pose. A direction metric
cannot see this, so the choice is policy and the metric is only recorded.

### Heat weights on layered clothing

Blender's heat-based automatic weights solved the single-shell cat at 100%
coverage and failed outright on the eight-shell field-scout male, even on a
welded proxy. The free landmark rig therefore falls back to envelope weights
there and says so in its receipt. That is the honest boundary between the free
route and Auto-Rig Pro's pseudo-voxel binding, and the reason the rig driver is
either-or rather than one or the other.

### Multi-view paint needs geometry it can read

Painting a character's head by itself, with its own UVs, is a clean way to
buy resolution: the transport is a face subset, the atlas rectangles are
unchanged, and the composite is a bounded blend. On the Ayric body it
produced convincing skin and hair and a face with two pairs of eyes. The
multi-view diffusion localizes features from the normal and position
controls; a low-detail head with shallow sockets gives it nothing to lock
onto, so each view guessed differently and the bake averaged the guesses.
Feature placement therefore comes from a registered single front image on
such meshes, and the painter is reserved for material and hair. The
orientation was checked and exonerated first: the same export axes as the
body transport, vertices identical to the body's head region.

### A launcher must not die on its child's stderr

Windows PowerShell 5.1 turns a native command's redirected stderr into
ErrorRecords, and under `$ErrorActionPreference = 'Stop'` the first
harmless warning becomes a terminating error. `run_hy3d21_texture.ps1`
aborted a paint at model sync the moment its caller added `*> log.txt`,
before any receipt existed. Every launcher now relaxes the preference
around the native call, as `compile_asset.ps1` already did; the exit code
and the validation JSON are the signal, never the stream.

## Operational lessons

- Disk growth from reproducible generations can exhaust hundreds of GB.
  Retain authorities, accepted derivatives, manifests, logs, and compact
  rejection evidence; remove rejected reproducible bulk periodically.
- Preserve open Blender, ComfyUI, and Unreal sessions. Inspect ownership before
  using GPU or locked files.
- Do not auto-retry crashed inference. Diagnose once and retain the failure.
- Use neutral review lighting. Overexposure and dramatic black backgrounds
  concealed defects and made texture judgments unreliable.
- Never overwrite an accepted candidate. Repairs are versioned derivatives.

### Workshop paint: retain the full bake, but do not waive bad lighting

The installed Hunyuan3D-2.1 pipeline bakes 4096 maps and downsamples its final
exports to 2048. Retained post-inpaint diagnostics contain the full albedo and
authored R-metallic/G-roughness maps. Recover only after validating source
geometry/UVs and map correspondence; record hashes and create a fresh package.
This recovered the workshop crate's density without another inference call.
The same recovery fixed sofa density but not its baked-light failure. The
workbench also has visibly smeared cavity paint: increasing resolution cannot
turn either failed appearance into an approved texture. Preserve rejections
and repair paint/mapping rather than waiving the gate.

### UE world copies must use the level operation

The workshop's first preview build used generic `EditorAssetLibrary.duplicate_asset`
followed by `load_level`. UE 5.8 aborted with a WorldMemoryLeaks fatal error:
the duplicated standalone World remained alive during the world transition.
Retain `work/sunset-workshop/evidence/preview-build-v001.log`. Replaced that
route with `LevelEditorSubsystem.new_level_from_template`, which creates and
loads the copy as one level operation; v002 and v003 builds passed. Never
retry the failed generic-duplication route or delete the source shell.

Dedicated editor startup can overwrite a camera set immediately by Python.
The first preview's overview captured a restored close-up. Set the review
camera after startup through a bounded Slate callback, warm the scene, and
inspect the actual screenshot before treating it as the requested view.

### Source projection cannot recover details without enough samples

Ayric v2's first whole-body AutoRemesher derivative met the numerical budget
but erased much of the nose/brow. Snapping its existing vertices to the dense
AI surface still left too few face samples. Both candidates were rejected.
Subdividing only existing front-head faces and projecting the new samples onto
the AI authority restored the shape at 19,588 triangles. This is downstream
source-conforming retopology, not manually invented facial geometry. Keep the
native quad authority separate from GLB review transport and require closeups;
four full-body renders alone hid the original facial detail loss.

The first character Hunyuan paint then failed independently: side-panel
correspondence defects, excessive gloss and facial style drift remain visible
in both raw painted OBJ and packaged FBX. Original 4K map recovery preserves
more detail but still fails density (199.8 versus 200) and directional-light
correlation (-0.244 versus absolute 0.12). Do not treat recovered resolution as
an appearance repair, shrink the character to game the threshold, or weaken
the profile simply to make this candidate pass.

### Facial donor composition is not camera correspondence

The first ImageGen face donor improved illustrated identity but moved the
eye line and hair silhouette despite a camera-lock prompt. Never directly
stamp it onto the mesh. Registered facial landmarks and geometry-bound UV
transport preserve the existing AI-acquired shape and non-face artwork.
The first transfer exposed original UV gutters as thin cracks; nearest-edge
padding only into unoccupied atlas space removed them without touching other
islands. Sparse mouth landmarks exaggerated the smile into a V; explicit
lip-corner and center registration corrected it in `prod-face-v003`.
Retain v001/v002 and all three-view lit/unlit comparisons. This preferred
face-only result still fails the independent whole-character texture gate.

### Recover UV space before increasing image dimensions

Ayric's existing 4K islands occupied about 37% of the atlas. A concave repack
and emission transfer raised occupancy to 56% and density from 199.8 to 301.3
at unchanged scale and resolution. Corresponding-surface samples bound the
resampling error, and native geometry hashes matched after reopening. No
extra source detail was generated. Blender UV selection synchronization must
be explicit in a headless repack, and the layer reference reacquired after
edit mode; the initial no-op was correctly rejected before baking.

The texture gate's median-of-bounding-rectangle sampler can include neighboring
paint, confirmed by a synthetic thin-triangle test. Surface-only sampling on
Ayric still measures -0.229 baked-light correlation, so it does not excuse this
candidate's lighting hold. Diagnostic only; gate/profile were not changed.

### Protected face pixels do not protect the neighboring lighting transition

Official Hunyuan delight successfully processed Ayric's retained six painter
views. Geometry-checked backprojection and high-resolution luminance-gain
transport improved correlation only from about -0.242 to -0.214, still failing
the unchanged .12 limit. Although the repaired face pixels were excluded,
changed neighbors made a dark forehead boundary more conspicuous. Reject
`prod-delighted-v001`; retain `prod-repacked-v001` as preferred. Do not repeat
whole-body delight merely to pursue the number. Review surface transitions
in actual lit and albedo closeups, not just donor images or mask invariance.
The texture failure message no longer falsely asserts that delight was
skipped; a correlation measurement cannot establish execution history.

### Native UE vertex budgets need native derivative evidence

Disabling generated lightmap UVs left the board at 15,973 vertices. A separate
native LOD0 reduction reached 14,534 without changing the original imported
asset. Retain both reports; this does not justify changing the budget or
overwriting the prior immutable import receipt. Two real UE views show the
candidate, but an occluding wrench makes the comparison provisional. Complete
unobstructed visual review and versioned native import/runtime evidence before
using this engine derivative in the final scene.

### Extend facial coverage without changing the preferred expression

The old donor region ended mid-forehead. Expanding its registration removed
the paint band but changed the surrounding Delaunay triangles and stretched
brow tails. Restricting the output to the forehead was insufficient: the
donor sampling still included eyebrow pixels, producing detached ghosts.
Explicit skin-only correspondence along the lower boundary fixed that in
`face-transfer-v006`, applied over the preferred v003 atlas. Retain both
failed variants. A target mask and a donor sample domain are distinct checks.

Albedo improvement does not fix scalar PBR mistakes. The geometry-bound
face mask contained metallic values up to 255 and roughness as low as 33.
`calibrate_pbr_region.py` calibrates lossless PNG scalar channels locally,
unlike the older OBJ/JPEG-specific helper. Preserve color and all outside-mask
texels exactly, and inspect lit views separately. Neither this calibration nor
the preferred forehead repair resolves the whole-character lighting hold.

### Visible folds need fragment visibility, not only a triangle-center test

Neck/collar donor mapping exposed limitations of midpoint occlusion and
interpolated vertex-normal fades. The optional pixel-depth route projects
surface samples with perspective-correct barycentrics and checks frontmost
camera depth. Disabling the normal fade is allowed only with that depth check;
it is useful for bounded concave neck folds, not permission to project through
the mesh. Keep the ordinary route unchanged for existing receipts. Separate
NumPy raster helpers from Pillow-dependent paint scripts so Blender's bundled
Python can generate correspondence without new packages.

One repaired three-quarter view hid the untouched opposite neck. The second
side now has actual geometry-bound mapping and lit/unlit closeups. Optional
opposite-side evidence must be a complete four-frame bundle in the review
panel. The bilateral donor improves paint but does not eliminate every collar
rim/nape artifact or solve the independent whole-body lighting correlation.

### 2026-09-04: Falsify lighting heuristics without granting an art waiver

A synthetic unlit multicolored cube scores +0.9839 against the Lambertian
normal fit, showing that authored palette and orientation can confound the
test. Ayric nevertheless retains substantial within-chromaticity covariance;
the control alone cannot clear its texture. Keep the existing gate enforced
and retain the read-only diagnostic. Do not manufacture flat paint to satisfy
a score or mistake coarse chromaticity bins for true material segmentation.

Matched native board review must use identical placement/camera/LOD with
occluders removed only in a copied fixture. The 14,534-vertex derivative
preserves the design in high/grazing comparisons, but visual acceptance of a
candidate is not authority to overwrite the original immutable import receipt
or promote a stage still bound to the 15,973-vertex original.

### Side-view nape donors must not silently replace the ear

The bounded ImageGen nape donor removed pale/cyan skin contamination but also
redesigned the ear. Use only its plain skin/lining samples, registered to the
existing side geometry; keep the changed ear outside the sample domain. The
first transfer left a pale diagonal because the support stopped on the defect
itself. A bounded expansion with donor-side skin controls removed that edge;
the opposite side needs its own asymmetric target controls and actual depth
visibility, not a mirrored mesh. Calibrate scalar PBR separately so repaired
skin does not retain metallic glints. Preserve both failed and preferred views.
These local appearance repairs barely affect whole-body lighting correlation
and do not justify an automatic texture pass.

### A collar region must include the raised rim in geometry, not just its picture

The first collar transfer selected triangles only below .83 of character
height. That cut through the raised rim, even though the camera-space polygon
covered it, leaving a hard triangular boundary in actual renders. The retained
v002 correspondence extends the eligible bound to .87 while the image polygon
still excludes skin, face, shoulders and the chest gem. Extending the lower
polygon past the damaged gold edge also avoids blending back into the defect.
Both constraints matter; a generous screen mask cannot override excluded
surface triangles. Collar-only roughness calibration reduces mirror glare
without changing metallic values or the rest of the armor. This improves the
front and both three-quarter views, not the independent lighting gate.

### 2026-09-04 — inspect sword lighting without altering approved materials

The original workshop fixture was too dark for a sole material verdict; three
neutral RectLights at1800 overexposed blade edges. Both trials are retained.
The separate v003 fixture at180 permits six-view static inspection without
modifying mesh, maps or the playable v004 level. Static acceptance does not
certify animated back attachment or cooking. All frames and native import
counts are now bound by the recorder and rechecked by the ledger audit.

For the character's independent lighting hold, stage IntrinsicAnything as an
isolated challenger, not another unmodified Hunyuan Delight retry. Its pinned
15,458,840,153-byte albedo checkpoint is locally hash-verified; runtime and
inference are still unproven. CLIP ViT-L/14 loads separately, so checkpoint
size alone is not total installation size. No new character candidate exists
from this tool yet; do not relax the lighting threshold or promote the held
texture based on a successful download.

### 2026-09-05 — intrinsic inference works, direct face substitution does not

The isolated official IntrinsicAnything base run completed on Ayric's actual
unlit body and face renders. Its256px diffusion softens identifying detail.
The documented high-resolution overlapping guided pass restores some detail
and cleans broad armor shading, but leaves rectangular transitions on the
forehead/cheek. Both are retained; neither is an approved atlas. Future use
must preserve original facial linework and use only justified illumination
information, with opposite-view and mapped-mesh review. No gate waiver.

The existing calibrated review exposure-1.5 is a display choice, not raw
albedo. The new inference input renderer uses emission only, Standard sRGB
exposure0 and real object alpha, without editing any authority file.

Taming's non-editable wheel was empty (namespace directories + find_packages).
Repair is a pinned source import, not changing the neural model. Retain v001
failure and v002 bytecode-only preflight refusal; v003 is the separately
recorded working baseline. Checkpoint-only download size understated the
installation: measured tool/runtime/source directories plus CLIP/HardNet total
22.48GB logical files, before interpreter and uv caches. Model capacity,
runtime viability and texture acceptance are separate conclusions.

### 2026-09-05 — stop the intrinsic orbit route after three bounded failures

Front-only success did not generalize. Exact side images collapsed to black;
oblique60/300-degree cameras repaired one side but not the other. Unguided
vertical crops restored side color but introduced horizontal bands and black
leg/foot patches. None is trustworthy illumination evidence. Do not clamp or
average these invalid outputs into a body atlas, rerun seeds blindly, or claim
synthetic transfer tests prove a repaired character. Source images, all output
hashes and verdicts are retained in the orbit-rejections panel. Actual atlas
transfer was stopped before execution. See ESCALATE-sunset-lighting.md.

### 2026-09-05 — multiview guidance repairs plant acquisition, not reduction shading

One Hunyuan3D-2mv attempt using original front authority and built-in ImageGen
inferred left/back guidance resolves the single-view plant's torn outer
leaves. Seven actual clay directions support delegated modeling acceptance.
Secondary views are approximate and must not be described as measured rotations.

The subsequent voxel512/QEM18k surface retains foliage but facets the pot.
Neither dense-source custom-normal transfer (modifier or explicit barycentric
BVH) nor a600-edge measured-error refinement to19.2k triangles removes those
visible artifacts. All are rejected for topology appearance despite passing
mechanical counts. Do not re-run these normal-only variants or claim that a
normal-transfer report proves polished shading. Diagnose curved-surface
reduction/normal sampling or change the reduction method. The dense modeling
authority stays accepted; the runtime topology gate stays rejected.

### 2026-09-05 — head paint cannot replace facial structure

On renewed face feedback, three bounded AI hair/ear donors improve detail in
two retained map-only previews, but color transitions and fringe breaks
prevent acceptance. Actual runtime clay also shows shallow eyes/mouth. Do
not equate a crisp frontal face painting with modeled identity. Reconsider
image-conditioned head acquisition with close head guidance, preserving the
body. Geometry replacement needs fresh modeling/topology gates. Current
held package and scene assets remain unchanged. See ESCALATE-sunset-face.md
and the hash-bound ayric-head-detail-review-v001 panel.

### 2026-09-05 — head-only acquisition restores detail; global remesh loses it

Close identity-conditioned front plus inferred left/back guidance produces
a dense head with clearly modeled eyelids and lips. Component modeling can
pass without implying assembled-character approval. Preserve the existing
body and reject downstream candidates independently.

AutoRemesher3000 and minimally smoothed voxel512/QuadriFlow2500 both flatten
the acquired eyes/lips and remove hair detail in matched CPU clay. The first
also exceeds its trial budget; both retain boundaries. Closing holes alone
is not a face repair. Do not continue blind lower-count global remeshing or
paint either reduced mask. Test feature-preserving reduction to distinguish
allocation limits from remesher smoothing, then satisfy actual articulated
topology and deformation requirements. Evidence: head-geometry-review-v001.

### 2026-09-05 — surface-distance checks do not certify the face

The20k unweighted QEM intermediate passes its generic distance thresholds
but creates an under-eye dent absent from dense cleanup. A5k derivative
preserving828 facial vertices exactly simply inherits the dent, including
in its unpaired native triangle render. Reject visual defects independently
of distance/count passes. Diagnose intermediate displacement/normals before
further protected reduction; do not repeat generic importance-strength
tuning. Triangle pairing also leaves42.69%quads and is not an articulated
topology solution. All evidence retained in head-surface-review-v002.

### 2026-09-05 — distinguish a normal artifact from a physical hole

The head's under-eye darkness survives nearest-source projection but goes
away after dense-source normal transfer with zero geometry movement. Do not
describe the render as proof of a physical hole. Other simplification remains.
Global normal transport onto coarse5k neck/back creates new bad shading;
all runtime candidates still rejected. Face-only transport is the next
bounded diagnostic if this route continues. Never turn a better frontal
shading result into a whole-head, topology or deformation approval.

### 2026-09-05 — absent UE normals must not inherit tiled-wall relief

Plant native inspection exposed pebbled relief absent from its Blender bake.
Read-only export of the installed Engine/EngineMaterials/DefaultNormal proves
a noisy tiled-wall normal map, not a flat fallback. The new importer master
M_RAC_CharacterMaster_v002 selects explicit tangent normal(0,0,1) unless an
authored Normal slot sets HasNormal=1. Old master and native assets are retained.
Two actual-builder graph tests cover missing and supplied normals; full175
tests/routing pass. Plant native-v002 four-view diagnostic confirms removal of
the unwanted relief, but first-frame fine albedo visibility needs warm-up review.
Material replacement is not a same-material native LOD reduction: do not bypass
that revision validator or describe the pending derivative as runtime-approved.

### 2026-09-05 — a de-lit sofa reference alone does not repair correspondence

One new Hunyuan Paint run from an ImageGen de-lit derivative preserves geometry
and UVs, but prod-delighted-v004 still fails luminance-correlation(+0.60104,
limit0.35). Native-size maps improve parts of the front while leaving arm/seat
strips and broad side/back gradients. Retain the rejection; do not repeat this
prompt/reference-only Paint method. Actual underside albedo is light brown,
not a black void, so the black-underside explanation is not supported. A future
repair must address mapping/correspondence with source-bound material regions.

### 2026-09-05 — final dressing must pass contact checks, not just height checks

V014 restored the independently reviewed sofa and two plant instances. Its
window pot had the correct Z but was outside the desk's XY footprint, and a
preexisting crate overlapped the sofa. V017 clears the crate. V018 puts the pot
inside the desk and probes nine support samples against actual UE LOD0 tabletop
triangles (91.65–91.95 cm), then sets its bottom to92.0014 cm. Actual close-up
confirms the contact and separation from the radio/tools. A bounds-bottom match
alone is not proof that an object is supported.

The final lighting derivative keeps every rock transform and the moon's
transform/material unchanged. Compare numeric UE transform values, never
`str(Transform)`: the string includes a temporary pointer and caused v015's
false guard failure. V016 uses numeric values and passes; old attempts retained.

### 2026-09-05 — cooked plugin code must be linked, not merely staged

RacDemoAudit's standalone Win64 plugin build succeeded, but a Blueprint-only
v018 game package staged its descriptor without linking its Runtime module.
The actual executable correctly failed to load; the clean cook was insufficient.
Explicit RacValidate Game/Editor targets and a minimal primary game module are
the correction, rebuilt to a separate v018-r2 archive. The audit is inert without
its command-line flag and records engine-native programmatic movement, not
physical keyboard input. Do not promote this package until that actual run passes.

### 2026-09-05 — night dust must not read as a dome

The user rejected the tall rounded dust in the first night pass and explicitly
requested subtle haze around the rock bases, below the clear skyline. Preserve
v019-v021 as historical candidates; do not call their atmosphere approved.
Remove radial fog density, steepen vertical falloff, lower the layer toward the
desert floor (Z=-400 cm), and remove fog emission. Keep original rock and moon
transforms/materials unchanged. Height-only fog still needs actual window review;
small density numbers alone do not prove the desired appearance.

The Engine stock night-sky texture/material candidate v023 produced stretched
stars and an overly bright blue sky. Retain it rejected. V024-v025 use a scene-local
unlit sky shader on the existing Engine sky sphere: direction-space points,
horizon fade and exposure compensation, added to SkyAtmosphere luminance. This is
engine-authored atmospheric shading, not AI geometry or bitmap generation.
No model downloads or changes to approved reference-conditioned objects are needed.
V022 also retains its early script assertion failure: material parameter setters
can set values while returning a false-like result; verify readback instead of
asserting the return alone. `star-material-probe.json` confirms v023 readback.

Further visual checks exposed the UI conversion in UE's
`LocalFogVolumeRendering.cpp`: `SafeFallOff = max(UIValue, 1) * 0.01`.
V026 therefore uses UI1200 for shader falloff12, not UI12. Ground is Z=-400cm;
local fog center is Z=-280cm, zero radial density, height density0.5 and a very
small warm emissive term (0.0001,0.000075,0.000045), far below the rejected dome.
Star antialiasing derivatives are clamped to prevent enlarged specks at grid
boundaries. Preserve intermediate comparisons; the cooked result is the next gate.

## 2026-09-06: Head fit before paint; neck correspondence before cosmetics

The shallow original face did not become anatomically correct by stamping a
better portrait. Reuse the existing detailed image-conditioned AI head, retain
its face/UV authority, remove only source-hash-bound old head/skin islands, and
fit the rigid head in the reference pose. The spawned player's initial idle is
not the reference pose: fitting against it bakes a neck offset into attachment.

For the remaining neck, broad warm-colour deletion catches gold trim; a flat
lining material changes the collar design. Nearest-surface UV colour transport
plus bounded per-pixel classification is safer. Do not classify only mesh corners:
blue corners can surround pale skin texels. Matching colour alone still leaves
different surface lighting, so transport the head normal in auxiliary UV channels
and blend it with the same mask. Preserve original images, UV0 and rig.

UE PreSkinnedPosition is vertex-only; route through VertexInterpolator before
pixel use. Import-commandlet success did not catch the grey fallback in v046;
native rendered views did. Keep rejected v043-v049 diagnostics and use the
source-bound recipes/commands in `CHARACTER_HEAD_AND_NECK.md`, not source edits
or renamed rejected receipts, to repeat the method.

## 2026-09-11 — Missing gates and stale files cannot certify completion

A syntactically valid state file with only intake/route passed made the old
audit return production-ready. Required stages now come from the canonical
intake contract, and routing/state must agree. State-object key order is not
execution order. Invalid records yield failed audits without being rewritten.

A simulated Blender Python failure returned process exit zero while an older
normalization report existed. The old prop driver published a manifest with no
FBX. A fresh attempt now owns its report and output, both bound to current input
hashes; publication refuses existing destinations and retains failures. This
requires updating consumers to resolve new reports without rewriting old ones.

A successfully built wheel could not run the CLI because it lacked the adapter
registry. Packaging now includes that resource and verification installs the
wheel with its declared dependencies in an isolated environment outside the
checkout. An editable-install test is not an installed-package test.
