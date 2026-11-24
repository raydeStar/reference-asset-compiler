# Decisions, failures, and retained lessons

*Type: chronological log*

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

## 2026-09-11 — Maintenance integration needs real producers and a runnable fixture

The inherited maintenance branch passed 325 unit tests while its stricter
texture validator still lacked matching production-builder fields. A new
integration test runs the builder with bounded stand-ins and then passes its
real receipts through the ledger. Source hashes alone also left the exported
FBX substitutable; payload reports now bind that FBX, maps and gate result.

The first public crate fixture used a different color per face. Its native bake
failed the baked-light correlation check, despite the unit suite being green.
Use a neutral synthetic texture for this mechanical fixture; retain the failed
attempt, and do not weaken a production gate to admit a demo.

A Windows fixture publication returned WinError 5 while renaming a complete
staging directory. The lock owner was not identified. Publication now permits
a short bounded retry of that rename for Windows access/sharing errors, checking
each time that the destination is still absent. It never retries the compiler
or inference. A new fixture passed the complete route and refusal checks; the
original staging directory remains evidence of the failure.

## 2026-09-15 — Browser scene memory, tree debris, and painter exit evidence

- Include the running Three.js preview in GPU ownership accounting. It can use
  enough VRAM to make the 21-GiB paint preflight refuse a launch. Release this
  task's render context before the next paint job; preserve other desktop apps.
- A valid GLB export does not prove it lacks disconnected geometry. The user's
  tree screenshot exposed 92 detached fragments left by acquisition/reduction.
  Check components, retain the rejection, and prove the cleaned final painted
  GLB still has one connected trunk/crown after merging UV-only vertex splits.
- Blender export validation removed degenerate faces after decimation; report
  triangle counts from the exported GLB, not from the pre-export mesh object.
- This Windows painter emitted valid reports and GLBs before repeated native
  access-violation exits. Record process failure and artifact validation as
  separate facts. Independently load/render/compare the saved payload, preserve
  the execution receipt, and do not claim a clean run or silently rerun inference.
## 2026-09-15 — Scene grounding is separate from mesh validity

A clean, connected tree mesh can still appear to float when its lowest root tip
is placed at a single analytic terrain height. Seat the root area against the
rendered triangles after instance scale and rotation. A dock position can also
become stale when the shore changes; bind the landward plank surface to the
shore and verify actual deck/terrain overlap. Keep the accepted mesh unchanged.
Use independent random seeds for object groups so environment dressing edits
do not unexpectedly move every tree and invalidate placement evidence.

## 2026-09-15 — Measure the initial transfer before changing model loading

Stillwater's inspector already reused the scene's model library. There was no
second eager download of seven GLBs to eliminate. The original thumbnail strip
instead loaded roughly 16.3 MB of source PNGs. Small WebP thumbnails and 1K
texture derivatives reduced the controlled initial wire transfer from 51.6 to
11.4 MB while every geometry/UV/normal buffer remained byte-identical. Preserve
the accepted original download authorities and bind derivatives to their hashes.

The in-app browser exposed viewport control but no network-throttle capability.
A local aggregate bandwidth server made the before/after comparison repeatable;
use its wall-clock milestone receipts, because hidden-tab performance timestamps
in an early probe did not reflect actual transfer duration. A viewport override
applied after navigation can already have initialized desktop-visible panels.
Reload after setting mobile dimensions to verify deferred renderer creation.

## 2026-09-16 — Deterministic capture is separate from real-time playback

For the Stillwater short, advance the actual scene at fixed 1/30-second steps
and encode browser frames at 30 FPS. A slow capture must not slow the film or
create duplicate motion frames. Validate the encoded timestamps and decoded
frames separately from the browser's playback-quality counters. Reframe the UI
only in the private capture context; keep scene and asset authorities unchanged.
Vite can inject the app stylesheet after head styles, so apply capture overrides
after the app has loaded and inspect representative frames before rendering.


## 2026-09-22 — Scene candidates expose assumptions hidden by isolated props

- Height is world Z after import, not the longest bounding-box dimension. A
  wide table or long cat must not be shrunk to the requested height as width.
- The dominant-component cleanup is useful for isolated generated solids but
  can discard real plates or mugs in an assembly. Preserve-components is an
  explicit remesh option; the old default remains available.
- Dense room Laplacian smoothing can cost far more than QEM. An explicit zero
  preserves architectural edges and skips that solve; all topology checks remain.
- glTF skinning ignores the mesh node transform. Bake uniform placement into
  mesh vertices and rest joints so raw bounds and skin consumers agree. Exclude
  importer-created bone widgets from measurement and export.
- A 50k browser budget has its own named profile. Do not weaken a 20k production
  profile or invent an approval waiver to make a browser candidate pass.
- More paint views did not recover the room's flat floor detail. Apply a
  reference-conditioned tile only to selected existing upward floor faces, with
  a receipt and fixed-view review; never silently replace the room geometry.
- A Python child of PowerShell Core inherits a PSModulePath incompatible with
  Windows PowerShell 5.1. Clear that one inherited variable for PowerShell child
  runners, preserving all other configuration.

## 2026-09-22 — Compare resolved Windows paths in launcher tests

The hosted runner uses an 8.3 TEMP path while stage inputs are deliberately
resolved. A string comparison failed on the same directory (`RUNNER~1` versus
`runneradmin`). Resolve the expected path rather than weakening launcher
normalization or changing the runner environment. No model execution is needed
to verify the subprocess handoff.

## 2026-09-22 — Partition proof does not prove a clean architectural asset

The old room's floor could be retained, but extracting its post and beams left
open cuts, dark holes and long boundary triangles. Broader regions and a bounded
clipping/capping derivative still failed assembly review. Keep those attempts;
replace the timbers with independently acquired, reference-conditioned models.
A partition's polygon conservation and UV proof do not certify its silhouette.

Removing the built-in fixtures also exposed recesses down to the old floor's
underside. The measured fix reused 1,783 acquired underside triangles as infill
at 0.222 m, just below the existing approximately 0.225 m surface. It reused the
same reference flagstone material and world UV projection. This is an explicit
geometry derivative, not part of the partitioner's unchanged-source claim.

GPU ownership can begin before VRAM rises: another painter loaded CPU weights
while a preflight still reported free memory. Refuse recognized live Hunyuan
Python workers before accepting VRAM/queue checks. This is not an atomic lock.
Stop only an identified owned attempt when overlap occurs; preserve unrelated
workers. Separately, a 768-pixel bar paint spilled about 14 GB into shared GPU
memory and was stopped after 19 minutes. A fresh 512-pixel-view attempt with the
same 4K atlas passed. Keep failed receipts and diagnose before choosing a fresh
attempt; never turn a retry into an unrecorded success.

## 2026-09-22 — Empty furniture and separate stock expose smaller repair boundaries

The fused tavern cabinet's vessels were weak even after the architecture was
split. Acquire the empty shelf, counter and four stock masters separately from
source-derived references. Review vessel mouths and handles from above as well
as fixed side views; paint alone cannot make a filled mouth hollow. Fit each
instance against measured shelf triangles rather than assuming a perfectly flat
deck or accepting floating props in a distant room render.

Horizontal shelf paint retained stretched grey/orange stripes. A versioned
material derivative maps a source-conditioned oak albedo onto selected existing
horizontal faces, including undersides when requested. Preserve the raw paint,
geometry/transforms and unselected UVs/material slots; do not call the changed
UV regions unchanged. Real Blender regressions check those boundaries.

GPU previews can consume the remaining paint headroom. Here, leaving the scene
view initially helped; later both saved preview tabs had to close after the user
authorized unused-app closure. Keep the 21504 MiB paint threshold intact and
check fresh free memory. Firefox's per-process graphics counters overstated the
memory actually released, so process accounting alone is not admission evidence.

Windows PowerShell errors can wrap the real reason before many owner lines or
begin without a script-name prefix under `-File`. Preserve that message before
the location/metadata trailer; returning the last owner or a wrapped metadata
fragment hides the refusal. The parser now covers both observed forms and keeps
ordinary Python stderr behavior. The read-only live refusal was retained locally.

## 2026-09-22 — Regional paint needs continuous transports and protected joins

The shipped innkeeper had 1,321 UV charts and shading discontinuities at 8,720
of 8,721 duplicated positions. Averaging normals on UV-split indices reproduces
the atlas seams as shading. Use an exact-position proxy for normal calculation
and transfer corner normals back without welding the rigged authority. The
painter's organic mode also needs vertex-normal conditioning explicitly.

A regional OBJ with a unique `vt` per corner became disconnected triangles on
Trimesh load. Share exact position/UV pairs; preserve actual seams. The first
head paint is rejected and retained. Its files existed before its launcher was
stopped, so do not describe it as an attempt that produced no output.

Fewer UV charts alone do not prove a usable unwrap. Large generated clothing
folds produced collapsed triangles or overlaps; broad projection repairs then
exploded fragmentation. Check all three and reject regressions. The selected
layout combines anatomical head/skin seams with an xatlas clothing candidate:
2/4/511 islands. This is useful progress, not a hand-authored garment unwrap.

Separate painters do not agree perfectly at region boundaries. A horizontal
head cut includes vest shoulders: head/neck bone weights protect those faces.
Clothing paint fades to original paint near atlas joins using surface distance;
otherwise cuffs and collar show a visible sawtooth colour boundary. Retain the
raw paint and both rejected combined reviews. Enlarging a sheet or smoothing
normals cannot repair original finger or facial geometry.

The 12-view 768-pixel clothing attempt had no output after 16 minutes and
allocated 22.4 GiB dedicated plus 18.0 GiB shared GPU memory. Only its identified
worker was stopped. A fresh explicit six-view attempt kept the 4K atlas and
completed its maps in about four minutes. Both selected painters later exited
with native access violation -1073741819 after successful geometry/UV validation.
Keep those execution failures, independently load/render the maps, and do not
retry inference merely to obtain a clean process exit.


## 2026-09-22 — Preserve the head when acquisition cannot preserve its anatomy

Innkeeper head replacement and nearest/radial shape transfer passed some
mechanical gates but failed visual review at the neck, eyelids, cheeks and nose.
A coherent isolated bust is not a compatible rigged-character replacement.
Reject those derivatives and retain their evidence; do not ship an automatic
replacement helper on numerical tests alone.

Full-head repainting also hallucinated additional faces in the hair. The selected
repair instead starts from the actual camera-aligned unlit head render, requests
an AI correction with fixed landmarks, and transports that donor through the
existing UVs. Normal-based fade missed grazing hair surfaces and left old
skin-colour bands. A bounded hair-only pass with per-pixel depth visibility
repairs these without relaxing occlusion or stamping facial landmarks onto
side/back surfaces. A left-camera hair patch covers the last front-occluded fold.
The original coherent head unwrap and all rig data remain unchanged.

See INNKEEPER_FACE_STUDY.md for the selected revision, rejected trials and honest
limits. This improves colour; it does not create separate eyeballs, eyelid
geometry or a facial rig. No new automatic generation default is implied.


## 2026-09-22 — An animated bind pose is not an idle

The user rejected all four initial tavern clips. The human idle added small
rotations around the asset A-pose, then keyed identity at both loop endpoints.
Skeleton compatibility, nonzero joint motion, playback/export tests and a green
repository gate all passed while the intended resting stance was still absent.
That is an authoring and review failure, not evidence that the user needs to
provide a more detailed brief.

Require an explicit held stance first; preserve the bind pose separately. Review
four views, including hands and clothing, then inspect the exported clip in the
consumer. Movement comes after the stance. The new exported standing-idle check
rejects the original clip and passes the arms-down replacement, but deliberately
keeps visual review required and human approval false. Read CHARACTER_ANIMATION.md
before future clip work. Do not generalize the humanoid stance to cats or other
pose contracts. The user's rejection supersedes prior technical success wording.

## 2026-10-03 — Aether asset and native-effect evidence lessons

- A flat plinth cannot be repaired by sandstone colour alone. The replacement
  conditions new geometry on a visibly seamed reference, then uses feature QEM
  and a bounded micrograin multiply that retains the painted masonry joints.
- Check QEM `status` and `failures`, not only an optional `ok` field. The coin
  pile inherited one 4e-11 m2 degenerate fin: removing that diagnosed face and
  its loose vertex closed the surface without changing visible coin geometry.
- Very thin floor/carpet assets need a useful paint-space height before UV
  transport. Apply requested world dimensions and carpet rotation after paint.
- Niagara Initialize Particle can overwrite direct spawn colour/size values.
  Native captures exposed white motes and heartbeat despite successful saves.
  PackV3 sets size in Initialize and colour/velocity through dedicated modules.
- Full-editor Python is required for Cascade-to-Niagara conversion; the headless
  commandlet lacks required Slate state. Native capture scripts need
  `set_keep_python_script_alive(True)`, post-tick callbacks and a reentry guard.
  Capture calls can reenter Slate while actors are being spawned.
- A transmission material assigned to coarse pane faces produces jagged frame
  boundaries. Lantern v4 bakes a UV transmission mask from acquired pale glass
  paint within measured pane regions; iron framing retains its painted finish.
- Keep GPU preview rendering out of paint runs. The same paint job slowed with
  browser/EEVEE VRAM competition. CPU Cycles review uses twelve samples, OIDN on
  CPU and eight threads while single-GPU inference continues.
- Original synthesized WAV loops are valid audio deliverables, but numeric
  checks and successful playback do not establish listening quality. This
  session cannot hear returned audio; auditory review must stay explicit.

### 2026-10-03: acquisition axes and material-pattern checks

- Inspect source axes before applying independent dimension factors. The crown
  moulding source ran along Y; scaling it as X made an intact cove resemble a
  huge missing bite. Rotating the acquired mesh before sizing preserves it.
  The same audit corrected the abyss bridge's finish orientation.
- A successful texture receipt does not prove source pattern fidelity. The
  carpet atlas lost its red/gold heraldry; direct source-art projection and CPU
  UV baking restored it without regenerating the cloth geometry.
- Blender engine enum availability is not evidence of the active renderer.
  CPU review wrappers explicitly select CYCLES and log the selected device.
- Framewright custom posters must be below 512 KiB. Render an actual-model
  512-pixel poster when larger review PNGs exceed that limit.


## 2026-10-03 — final Aether review corrections

- Framewright supports revision families for Image/Model, but rejects Video
  revisions with HTTP 400. Import the new native preview and archive the old
  take through the ordinary recoverable API; retain original media evidence.
- Nested glTF transmission made the condenser's enclosed quartz invisible in
  the browser. kit-v4-browser disables transmission only on that enclosed core
  in the GLB; the packed native Blend retains physical crystal transmission.
- Native wall decal captures need roll 90 with projection half sizes ordered
  (depth, height, width). Review light intensity 200 overexposed the texture;
  V3 uses 5 and preserves all earlier captures as evidence.
- Generated dense coin piles can fuse coins into soft geometry. The repaired
  pile uses one newly acquired/painted coin and 120 rigid settled copies; source
  coin stays construction evidence rather than inflating the review count.
- Native core-material capture saved every frame/receipt, then UE crashed on
  shutdown. Separate valid artifact evidence from a clean-process-exit claim.

## 2026-10-04 — a ceiling is not a target: triangle budgets by role and size

- Every static object in the Aether Wars commission was cleaned to the
  static-object profile's 100,000-triangle `maximum_triangles`, because nothing
  else proposed a number. Pipes, flanges and handholds cost what 6 m doors did:
  14.2M triangles across 121 models where a role/size budget gives about 2.1M.
  `profiles/triangle-budgets.json` and `rac budget` now decide, and
  `remesh`/`reduce-mesh` default to `auto`.
- Keyword roles need a shape check: "chain" names kit pieces, but a chain winch
  is a machine. Kit pieces must also be long and thin.
- Notes may promote a role but never demote one: notes mention neighbours
  ("stands on a plinth") far more often than names do.
- Reducing after paint smears the paint. A 120k floor brazier collapsed to
  5k-17k kept its silhouette (p99 3-9 mm) and still lost its crisp bands and
  rivets at every rung; transferring the dense normals did not fix it, because
  the damage is UV drift, not shading. Budget before paint, or re-bake.

## 2026-10-04 — notes promote only through unambiguous words, and heroes only when big

- Keyword promotion from notes misfired: the temple door frame's notes say
  "Independent leaves", and "leaves" is a vegetation keyword, so a frame was
  budgeted as huge vegetation (30k) instead of a huge prop (20k). Found by the
  re-bake session.
- Notes describe neighbours and parts, not what the asset is. Roles now carry
  `notes_keywords` (no leaf, leaves, root, tree for vegetation; no throne for
  hero, since a throne names itself) and the hero role a `notes_min_size` of
  large, so a brazier "beside the throne" or a lamp "lighting the statue" stays
  a prop while a 4.5 m "toppled statue head" is still a hero piece. Names
  classify as before.

## 2026-10-04 — paint that slid is baked back, and judged by eye

- Re-baking from the dense original undoes the smear. The floor brazier
  re-baked at 15k and 16.8k triangles scores 0.95-0.96 lit and 0.97-0.98 unlit
  SSIM (worst of four views) against the delivered GLB; the same reductions
  without a re-bake score at most 0.80 and 0.93. Surface deviation could not
  tell the two apart; the fixed views can. `rebake-maps` is the stage.
- On the brazier the eye and the surface gates agree: 15k is the lowest rung
  both accept, and 11.2k passes neither. Below that, what fails the views is the
  geometry (a kinked strap, a faceted rim), not the bake.
- A scripted bake cannot rely on switching a material's active output: in
  Blender 5.2 `is_active_output` stayed on the original output, the bake read
  the untouched BSDF of an unlit scene, and every map came back black while
  the run reported success. Rewire the active output's Surface socket instead,
  and restore it afterwards.
- A bake's alpha cannot measure its coverage: after `bake(use_clear=True)` a
  normal map is opaque on every texel, reached or not, and the margin makes
  opaque every miss within its width. A white emission pass can, baked
  without a margin. Baked with one, it counts the misses the margin covered as
  reached: the brazier at 15k read 100% that way, while its rays reached
  99.74% (the throne at 40k: 99.98% against 99.96%). The maps are the same
  either way; only the reading was wrong. `retopo_bake.py` read its coverage
  from alpha too; see the next entry.
- Compare masks at one resolution. Islands rasterised at 1024 and checked
  against a 4096 coverage mask, picked every fourth texel, sample 1.5 texels
  off their own centres; at island borders that lands in the gutter, which is
  black without a margin. It read 96.9% and 95.7% for those 99.74% and 99.96%,
  and was reported as such for a commit before the cause was found.
- Each map's `texels_filled` counted every texel the coverage mask left
  unwritten, gutter included: 5,059,706 on the brazier's base colour, which the
  fill had not touched. It now counts the painted texels the fill actually
  repaired: 39.
- Appending one .blend into another renames clashing node groups: "glTF
  Material Output" became "glTF Material Output.001", and the throne's
  occlusion silently stopped being found. Match by the name before the suffix.
- `review-views` renders with EEVEE, which needs the GPU. Cycles on the CPU with
  a fixed seed is deterministic: the dense .blend and the delivered GLB of the
  same prop rendered identically (SSIM 1.000), which is the gate's noise floor.
- Windows PowerShell 5.1 hands an argument to a native program without
  escaping the double quotes inside it. Aether Wars notes quote their socket
  names, and cut at 400 characters three of them had an odd number of quotes:
  on the way to Blender they swallowed `--runtime-derivative`, and those props
  were reduced as production authorities (holes filled, judged as closed;
  crypt-frame refused for it). Names, roles and notes now travel without double
  quotes, switches first, both in `stages.py` and in the launchers.
- "Leaves" is not always foliage. A door frame's notes said "Independent
  leaves" (door leaves), and notes may promote a role, so it was budgeted as
  huge vegetation (30k) rather than a huge prop (20k). Harmless here -- more
  triangles, not fewer -- but promotion by keyword in notes needs a guard.

## 2026-10-04 — a bake's alpha does not say which texels its rays reached

- `retopo_bake.py` reported bake coverage as the share of the whole sheet with
  alpha above 0.5, and let the same alpha decide what `fill_unbaked` repaired.
  Measured on Blender 5.2.2 (CPU Cycles, `use_clear=True`, margin 24
  `ADJACENT_FACES`): a NORMAL bake returns alpha 1 on every texel, reached or
  not. On EMIT and AO bakes a missed texel keeps alpha 0 only until the margin
  gets to it: the margin writes alpha 1 and a neighbour's colour into every
  missed texel within its width. Outside the islands, alpha changed between
  two identical bakes (100% vs 90.5% of the gutter opaque). The opaque
  `generated_color` fill plays no part: `use_clear` overwrites it.
- So the receipt overstated reach, and the fill ran only where alpha happened
  to be 0. A holed sphere baked onto a prebuilt light mesh reported 93.7%
  (Normal 100%, nothing filled) while its rays reached 52% of the island
  texels, and 9.6% of the island texels shipped black. Most of those misses
  were not the holes but the default 3 mm extrusion falling short of the
  ~5 mm gap at the light mesh's quad centres -- a failure the old receipt
  could never have shown.
- Coverage now comes from two white-emission bakes through a view-layer
  material override, which also covers faces with no material and leaves the
  materials untouched: margin 0 gives what the rays reached, the passes' own
  margin gives what the passes will write. Island texels come from rasterising
  the light mesh's UVs (`scripts/blender/bake_coverage.py`); that agrees with
  Blender's own island texels to 0.03%. `bake_coverage_pct` is now the reached
  share of the islands, `texels_filled` the island texels the fill repaired,
  and `bake_coverage` puts every missed texel in exactly one bucket: written by
  the margin, filled, or left unbaked. On the same sphere: 52.35% reached, and
  15,144 texels left unbaked, which is exactly the number of black island texels
  in the delivered maps (half what shipped before). Both passes took 0.8 s at
  1024.
- Measure reach without a margin. A coverage mask baked with one counts the
  misses the margin covered as reached; use that mask only to decide what to
  fill.
- `bake_coverage_pct` in reports written before this change is an alpha
  reading, not a measurement (the office-chair canary's 100.0, the 99.78% in
  `DEFECTS-CLOSEUP-REVIEW.md`). `build_production.py` now takes reach only
  from a report that carries `bake_coverage`.

### 2026-10-04 - Ennix: local surface repair does not recover anatomy

Unsharp/Laplacian detail amplification on the raw marching-cubes face turned
triangulation into visible wrinkles and spikes even at a 1.5 mm displacement
cap. Reject that V2 result; V3 restores the original facial positions. Smooth
normals improve display but cannot create modeled eyelids, lips or sockets.

A boolean cut can leave a manifold surface while failing to separate fingers
when cutter normals are inward. Correct outward cutter normals and validate
actual open gaps plus distal connected components, not just manifold counts.
V3 has four distal components per hand, but those flat slotted fingers still
fail anatomical fidelity. Keep technical geometry checks separate from visual
acceptance and rig readiness. Sources and closeups live in the Ennix V3 repair
directory; no blind whole-body regeneration or gate promotion followed.

### 2026-10-05 - Ennix part acquisition gains and limits

The runner's left slot sees the front image's right side, confirmed against
installed preprocessor mapping and actual official example images. For dorsal
hand front with thumb image-right, use radial/thumb edge as left; palm as back.
Retain unused ulnar guidance under supplementary_views, not the required exactly
three-entry derivation views list. Request preflight caught that metadata issue
before inference; original invalid metadata is retained as evidence.

Detailed isolated head guidance improves facial volume but does not ensure usable
eyelids or clean hair. Dense closed geometry is not anatomical approval. The hand
acquisition is useful for measured placement; overlapping capped wrist surfaces
still need a joined deformable topology. Record that distinction explicitly.
Do not silently reduce a raw head to fit Framewright's model review limits or
claim the unmodified original GLB equals Blender's import triangle count.

## 2026-10-07 — repeatability and actual consumer checks for Ennix

- Blender helper teeth are fitting cages, not visible dental assets. Use the
  corresponding CC0 MakeHuman system meshes with MHCLO barycentric fitting;
  transport expression deltas through the same correspondence.
- Unrelated guide curl phases look like tangled wire. Seeded spatial phases
  produce coherent neighbouring locks; preserve source hair-envelope conditioning.
- Mirroring a side witness invents the one-sided red sash on the opposite leg.
  Restrict that witness and restrict end-on arm projection to the torso region.
- Freeze coordinates and inspect body landmarks: an asymmetric sash can drag a
  naive torso centreline away from the actual torso. Original finger landmarks
  also missed the repaired flat hands; corrected measurements precede weighting.
- BMesh edge sets and extrusion face order are not byte-stable. Sort traversal;
  compare canonical polygon winding/UV/material data in addition to coordinates,
  bones, weights and morphs. Do not call two .blend hashes repeatability proof.
- Blender Alembic preserves strand geometry but drops custom strand_colour.
  Retain native colour authority and explicitly report the UE material fallback.
- UE GroomFactory creates an empty groom; HairStrandsFactory imports Alembic.
  Hair needs the AlembicHairImporter plugin, correct handedness conversion, and
  a bound skin-cache-enabled component. The editor animation-update switch is
  transient: apply it to the spawned instance, then capture on a later tick.
- A scene capture does not request texture mips like the live viewport. Force
  mip residency for the bounded review; do not mistake blurry streamed mips for
  a bad bake. Explicit base-colour/roughness materials avoid FBX emission/Phong
  conversion differences. Never promote a character merely because import passes.

## 2026-10-07 — Bone heat is not a weighting strategy for scanned outfits

Blender's bone heat, and its voxel remesh used as a watertight proxy, both
fail on open, layered clothing scans: the remesh returns hundreds of
fragments. `rig_from_landmarks.py` then fell back to envelope weights without
failing the stage. Use `fit_ue5_manny_rig.py`'s slice-filled voxel solid,
with inverse-distance weights only toward bones each vertex can see through
the solid. Treat any envelope fallback as a failure.

## 2026-10-07 — Face paint: measure against the picture, not its lighting

- The front guidance's own blush is as red as the texture's (a* about 10 over
  plain cheek), so matching it calms nothing; the render's lights and skin
  emission make it read as blotches. Cap it at a share of the measured redness
  and spread it so patches lose their edges.
- Taking out a* alone leaves a brown stain: the guidance's blush is also darker
  (-0.45 L* per a*). Remove it along that measured direction.
- DWPose points 0-3 and 13-16 outline the cheeks, not the jaw, and seen from the
  front their depth wanders: the right jaw end sat 2.7 cm forward of the left,
  so a sideburn drawn from it cut across the cheek. Take the jaw's ends from
  the template's ear group.
- A jaw height looked up by azimuth round the head folds behind the jaw angle
  and patterned the neck. Use signed distance across the jaw line.
- The guidance's under-jaw darkness (-19 L*) is cast shadow; painted in, the
  render doubles it into a smear. Measure the neck at mid-neck.
- A smooth field read back per vertex creases along the coarse side-of-face
  triangles; smooth it again in texture space. Replacing a low-pass keeps old
  band edges as detail; clamp detail where it is replaced.
- The paint's lips do not sit on the guidance's landmarks (the surface stage
  blends in the painting's mouth), so a landmark-shaped moustache over
  front-painted texels greyed the upper lip and blotched the corners. Where the
  front picture painted squarely its stubble already matches (moustache L* 56.5
  against 56.0): fill only where it did not.

## 2026-10-07 — characters are budgeted by tier; find where a scan's triangles are before cutting

- The skeleton profiles' flat 20,000 held the playable hero to a villager's
  ceiling, so Ennix failed the strict gate at 136,595 triangles with every other
  check passing. Characters now have tiers by screen time in
  `profiles/triangle-budgets.json` (hero 60-80k, boss 50-80k, elite 30-40k,
  regular enemy 15-25k, NPC 10-20k; LOD0, groom strands excluded), and
  `gate_rig.py --tier` gates at the top of the range. Without a tier the flat
  number stays, so nothing gains triangles until someone says what it is.
- Ennix's "120k outfit" was mostly hands. The acquisition's preserved hands are
  890,490 of its 1,326,239 triangles (beyond |x| 0.80 m the density jumps from
  about 130 to 6,800 vertices per centimetre slab), so the uniform collapse
  left 28,920 on the hands and 91,173 on everything else. Measure the regions
  first, then give each its own count.
- To hold a region still in Blender's collapse, give it weight 0 in the
  Decimate modifier's vertex group with factor 1000: that adds edge length x 2 x
  1000 to its edges' cost. Weight 1 leaves an edge to quadric error alone.
  Without the hold, a pure quadric pass over the garment took the 6k hands on
  down to 3.2k.
- A fold/hem/outline weight did not help. The modifier's weight term is a
  length in metres times the factor, while quadric costs are squared metres
  (about 1e-8 to 1e-6 here). At factor 20 the weight swamped the error: the
  garment came out 1.07 mm from the source at p99, worse than a uniform 54k
  (0.38 mm) in its folds too. At 1e-4 it measured the same as no weight
  (0.32 mm). Quadric error alone already keeps the density at folds and hems
  (233 against 145 triangles per dm² on flat cloth, the ratio the 120k body
  had). So the hold is the only weight used.
- Gating only the proxy FBX hid a failure in the file that ships: the UE5
  export carries Manny's `interaction` and `center_of_mass` bones, which the
  `ue5_manny` profile did not list. They are optional now, and the rebuild gates
  both files.

## 2026-10-08 — a groom's gaps are fill, and are judged in the game's look

- In game Ennix's hair read as flat bright clumps over near-black gaps, with a
  crown edge of see-through tips. Groom render settings (stable rasterization,
  lighter self-shadow) changed nothing in a same-session A/B. The cause was the
  strands: each lock was a flat ribbon at its own random depth in the envelope,
  and its children were near-copies of their nearest guide (inverse-square
  weights over 3 guides) pulled to a point from mid-length (`clump * u^2`).
  From outside, a deep lock between two outer ones is a crevice.
- The review render hid it. Cycles' hair BSDF scatters light through the hair,
  so the inside of the groom is lit and the gaps read brown. The game's deep
  shadows and dark root colour make the same gaps nearly black. A **game look**
  (`render_painted_head.py --strand-width --strand-gradient --light sun
  --hair-shader diffuse`): the game's strand width and root-to-tip colour, one
  hard sun, no light through the hair. It reproduces the in-game failure, and
  `build_groom_review.py` measures it: crevice share (hair darker than half its
  surroundings) and how ragged the dense mass's crown outline is.
- Measure the outline on the dense mass. A first measure counted background
  held inside the closed silhouette, and it rated v10 worse than v9: closing
  bridges every fine flyaway, so a soft edge scored as see-through and clumped
  spikes scored as clean. Blurring at strand scale before thresholding drops
  lone flyaways and keeps spiky lock tips.
- More strands alone are not the fix, and raising `--children` is the wrong way
  to add them: it changes the root draw count, so every lock moves (a tall tuft
  appeared on the crown). `--extra-children` roots more strands from an
  independent seed; every guide and lock stays where it was.
- What filled the gaps: each child blends 6 guides with Gaussian weights
  (`--blend-sigma` 1 cm), so the hair between two locks belongs to both. Locks
  gather late (`--clump-power 3`) and have depth through their layer
  (`--lock-thickness` 3.5 mm). Smoothing lock depths across neighbours
  (`--depth-smoothing`) measured no better and is not used.
- Too much fill reads as fur in the review look (Cycles' denoiser blurs fine,
  unclumped strands). Clump 0.75 (gathered late) keeps lock definition while
  the gaps stay filled. The review radius is scaled down with the strand count;
  the game sets its own width.
- Every new option defaults to the old behaviour. Recipe `20261010`'s groom
  still reproduces `rebuild-v9/strands.npz` byte for byte.

## 2026-10-09 — Mesh hair in the build: the planner's "largest mesh" and the hair budget

- `plan_ue5_joints.py` took the largest mesh (by vertices) as the body and the
  height over every mesh. A hair mesh breaks both: character-02's reduced hair
  has more vertices than his outfit, and it stands above the crown, which would
  have scaled every proportional joint. Name objects to ignore rather than
  guessing from size (`--ignore`, passed by the rebuild for mesh hair).
- A scalp cap probe that is a ball over each scalp vertex reaches sideways as
  far as it reaches out, so the cap ran about 1.5 cm past the hair's edge. A
  narrow column along the normal, then closing over the skin's neighbours,
  puts the cap under the gaps between locks and ends it at the hair.
- Sampling the baked hair texture at UV corners hits the bake margin and the
  black texels of missed bake rays (28% of character-02's triangle centres are
  black): sample at triangle centres and skip pure black.
- Hair in the skeletal mesh counts against the character tier; a groom never
  did. 56k triangles of hair put character-02 at 127k against the hero tier's
  80k. That is a policy decision for the owner, not a gate to loosen.

## 2026-10-09 — what a mesh hair's triangle count costs, and how an overrun is accepted

- fast-simplification collapses a thin blade's two sides onto the same three
  vertices; Blender's mesh validation then drops the copy at the bake. A
  receipt that reports the reducer's count overstates the shipped mesh by
  about 10% (40,000 requested, 36,587 shipped). Count what ships.
- Below about 27k triangles character-02's scanned hair degrades in the ways
  that read as mess: a lone shard on the forehead, bake paint banding in the
  crown, blades merging into facets, and at 18k a fringe collapsed to a
  straight hairline. Silhouette metrics and the scalp-gap count did not flag
  any of it; the close crops did.
- An accepted overrun belongs in the recipe with the approver, the date, the
  owner's words and a ceiling, not in a gate flag: a waiver without a ceiling
  would quietly cover a heavier mesh later.

## 2026-10-09 — mesh hair goes where the scan's face goes, not where its conformed skin went

- A template conformed to a stylised scan takes the scan's skull but not
  always its face: character-02's came out squashed (brow to chin 10.0 cm
  against 13.5 cm). Hair carried with that skin keeps the scan's absolute
  height and scale. Placing it by the scan's own upper face (brows, nose
  bridge, eyes) on the character's put it 20 mm lower and 13% smaller.
- Push hair out of the skin after reducing it, not before: a per-vertex push
  lays neighbouring blades onto one offset shell, and the quadric collapse
  stops (36,442 triangles for a 30,000 request).
- conform_head_template.py's NPZ keeps the scan in template metres while its
  front render saw it in scan units: bind pixels on the scan carried back
  through the alignment, then read the points off the template-metre copy.

## 2026-10-12 — preserve export axes when transplanting hands; review the final source

- `EditBone.head/tail` aiming rotated the fitted finger frames away from the
  Manny animation convention. Good-looking static template hands then collapsed
  under the recorded game poses. Move the original bone matrix's translation;
  retain its orientation. Measure the float32 round-trip error and fail above
  5e-5 per matrix component. This fixes a convention error, not all articulation.
- Whole-triangle deletion at a cuff leaves pointed remnants. Bisect the bounded
  cuff region with interpolated UVs/weights, then cap newly blended weights to
  four. The first corrected FBX was properly rejected for six influences;
  preserve that failure (`seams-20261012/release-v1/`). Do not loosen the rig gate.
- The full rebuild's `pose/` and rig-fitting `poses/` renders precede replacement
  hands. They cannot validate the final character. `game-review/` now reads the
  finished game blend, including coat weights when present. Checks cover both
  source selection with and without coat chains and deformation on real files.
- Pulling the cuff inward and restoring the acquired neck both produced new
  visible tears. Strong collar smoothing introduced spikes. Preserve those
  rejected variants; do not repeat them as supposed fixes. The bounded 8 mm
  collar pass is a review candidate and still fails the AAA appearance target.
- Six sampled native poses and an FBX skeleton gate do not prove consumer
  animation, contact, materials, natural fist shape or human visual acceptance.
  Exact hashes and rejection reasons: `evidence/character-02-seams-20261012.json`.

## 2026-10-12 — distinguish capture mip failures from source paint and topology

- Tiny per-face UV islands can turn a low-res resident mip into tan shards.
  Test prestreaming/residency before repainting. Full UV precision and forced
  LOD0 were negative controls here; disabling mipmaps offered no benefit.
- A detached scene capture is not a reliable texture-streaming viewpoint.
  Record camera, actual bone positions, fixed pose/time and image hashes; an
  export-success flag cannot prove framing or appearance. Include elevated 3/4.
- Front and back guidance can place the arms at different heights despite
  sharing frame dimensions. Register sleeve silhouettes independently before
  extending their paint around the acquired surface. Broad harmonic fill and
  averaging unrelated folds both erase detail.
- A voxel union can pass distance/rig-preservation gates while damaging painted
  surface quality. The surface-v3 candidate was visually rejected. Keep the
  mesh/rig immutable for a texture-only defect; numeric gates never overrule
  the pixels or a user's rejection.

## 2026-10-12 — fit animation clearance to the actual mesh bind and coat

- A Skeleton asset can retain older reference joints after mesh replacement.
  Character02's actual mesh component reference agrees with its native bind;
  the Skeleton reference does not. Reject that mismatch, retain its receipt and
  use the mesh reference for source-bound deformation measurements.
- A valid T-pose does not guarantee a suitable idle. The acquired coat needs
  more hand clearance than the Manny animation supplies. Shoulder lowering alone
  still clips; establish a held pose visually before applying its local matrices
  to the original moving tracks. Preserve the bind and update hand IK markers.
- Keyframes alone missed one blended contact. A skirt-only collision region
  also missed higher contacts in rightward jog and first attack. Include the
  torso through the collar and sample idle/movement, adjacent directions and
  walk/jog blends. Retain the rejected v3 and v5 evidence; do not soften the gate.
- Isolated moving contacts need smoothly entered corrections; a per-frame
  collision solver with discontinuous offsets would introduce elbow pops.
  The accepted v6 uses a short plateau and smooth fades, with cyclic wrapping
  for locomotion. This finite check still cannot certify every gameplay blend.
- Install absolute local keys and hash-pin the original animation dump, native
  mesh and imported FBX. Reapplying the packet is safe; dumping corrected clips
  as a new baseline would double-apply the posture and must be rejected.


## 2026-10-16 — A database-backed HTML ledger is not its requisition export

The supplied Artiss Tomb HTML contains the UI, an empty `rows` array and a
Claude shared-database subscription. It embeds no requisition records. Its
brief exporter includes only rows whose status is `Approved to build`, so an
empty Markdown table does not identify an asset collection. Preserve the HTML
by hash, request actual rows or access to the live ledger, and do not reconstruct
IDs, measurements, priorities or approvals from nearby design prose. The new
Framewright project may be prepared while this intake dependency is pending.

### 2026-10-16 — Review bronze at its intended specular response

The Artiss lens's matte finish concealed UV-seam normal and uneven annular surface
artifacts. Raising metallic to 1 and reducing roughness exposed them. Preserve the
metal response and repair the acquired surface/normals as a new derivative; do
not treat a flattering matte render as proof of smooth geometry. Pin measured
apertures, restrain decorative plates, retain UV correspondence, and inspect the
actual viewer while orbiting. The lens retained its 60 cm glass and 11,764 total
triangles through this cleanup. Also inspect generated metallic maps: the pillar
and emitter maps barely identified their bronze. A semantically bounded data mask
can correct those regions, but colour alone is not a universal material classifier.

## 2026-10-16 — Audit isolated scraps and judge surface cleanup visually

The painted rope GLB contained three tiny disconnected single-triangle scraps,
not three holes in its main surface. A boundary-edge count alone cannot tell
those apart: inspect connected faces before filling. Removing those exact scraps
left the hemp mesh closed; rejected CPU attempts were retained. Similar scraps
were removed from scaffold/case normal-transfer experiments. Audit the actual
interchange geometry, not only an upstream native reduction report.

Generic bounded Taubin fairing and dense-source normal transfer were not enough
to clean the archive cabinet and gauge case's broad planar surfaces. Passing
closed-surface and coordinate-preservation checks did not make those experiments
visually suitable for polished metal. Keep them as comparisons and use
feature-specific cleanup before paint. The successful annular lens cleanup
should not be treated as a universal smoothing recipe for every prop.

## 2026-10-16 — Preserve grooves and verify physical attachment, not just closedness

Repeated cross-section averaging can collapse a grooved ring while every
manifold test still passes. HC-01 v2 lost substantial ring volume and visibly
thinned the lips. Keep the rejected views and prefer a restrained derivative;
measure the band separately from axle bosses before claiming its diameter.
A negative partition may also extract disconnected slivers from a neighbouring
part; inspect components and all four views after the cut.

For rope attachment, a closed positive-volume mesh does not prove a valid knot.
Check nonadjacent self-intersections and rope/hardware triangle intersections,
then inspect whether it actually reads as a tie-off. Nearest-surface projection
of a dense centreline produced discontinuous folds and excessive path length;
zero hardware intersections in a loose loop was still a visual rejection.
The staged hanging rope's physical gauge was too large for small cleats, so
family-wide gauge and contact need explicit review before replacing it.

## 2026-10-16 — Refine before bending instead of smoothing away rope detail

A nonlinear coil bend can make coarse triangles cross even when the source
surface is closed and has no self-intersections. Radial clamping worsened the
crossings; local smoothing moved small features excessively without clearing
them. HC-02's successful compact coil instead split only affected source
triangles with UV interpolation, then applied the same bend. Two refinement
passes removed all detected crossings with only 276 additional triangles.
Re-import both GLB and FBX and check self-contact again. A floor coil also
requires top, underside and elevated views: four horizontal views alone show
only its shallow profile and cannot verify turn spacing.

## 2026-10-16 — Audit the emitter orientation and internal cut cost

Imported glTF objects may retain quaternion rotation mode after transforms are
applied. Writing Euler angles alone then leaves a wall variant vertical. Set
the intended rotation mode explicitly and assert actual world bounds; re-import
GLB and FBX to verify the consumer sees the correct long axis and socket pivot.
For an internal core partition, a 96-sided cutter created unnecessary hidden
triangles. A 32-sided cut retained the visible source silhouette and reduced
the assembly from 21,884 to 18,788 triangles. Radial normals on the acquired
glass core improved its highlights without smoothing away its geometry.


## 2026-10-16 — Architectural normals, paint masks and complete map packages

Boundary loops are not necessarily holes: TW-01's arch had nine tiny detached
triangles, not missing surface. Remove measured debris instead of bridging it.
For dense architectural voxel cleanup, optional Laplacian smoothing consumed
over thirteen minutes on one attempt; that owned CPU process was cancelled
and recorded. A distinct zero-smoothing cleanup completed in about fifty
seconds. Apply transforms and clear imported custom split normals before
assigning flat cut caps; face flags alone did not remove the old shading.

Warm limestone fools an HSV bronze mask. On the ceiling, use measured material
regions from acquired mesh/paint to build the technical metallic mask; keep
AI colour unchanged. Four horizontal views cannot validate a flat floor or
ceiling: inspect top, underside and lighting from the visible side as well.
For portable companions, extract packed image bytes even when lazy images
report no pixel data, then reopen Blender/FBX and verify every map path inside
the package. Successful geometry export alone does not prove texture closure.


## 2026-10-16 — Rubble support, canonical fragments and collision checks

A stable rigid-body solve can still be visually wrong when temporary walls
support pieces above ground. HC-05's second settle had zero drift but retained
that support. Remove the temporary walls for the final distinct settle, then
inspect the actual exported pile, including side/elevated views.

Do not assume Blender-generated hull triangles form trustworthy convex
planes. HC-05's first hulls violated containment; 38-direction support planes
and verified halfspace intersections produced conservative enclosing hulls.
After canonicalizing a standalone stone, recompute its hull in those axes:
rotating an already conservative hull can create a needlessly large AABB.
Export fragments in canonical orientation with explicit assembly matrices.

Canonical companion creation can reintroduce old texture paths even when
the assembled package is portable. Reopen every Blender/FBX companion and
verify paths after the final derivative. Bind by exact map hash, retain old
companions, and rerun only the affected export/map checks.


## 2026-10-16 — Swivel band measurement, small motion and painted scores

Measure a circular ring's requested diameter on the band, excluding axle
bosses. An overall bounding box silently undersizes the band. Keep source
grooves through restrained fairing; wider profile reconstruction can smooth
away the functional channel even when ray coverage succeeds. Select from
actual fixed views, not a displacement or watertightness number alone.

Small exported motions require actual action-range checks. Blender's FBX
import may offset the starting frame, and default simplification can attenuate
fractional rotations. Sample the imported action range and disable curve
simplification when the exported travel fails the intended amplitude.

When an AI paint pass omits tiny requested scores, use a separate AI-acquired
surface source and downstream UV projection/baking. Bind that source and
prompt explicitly. Preserve geometry and painted wear; keep metal response
separate from limestone. Validated artifacts from a crashed child process do
not make the execution successful: preserve both the validation and failure,
and never silently retry the inference.


## 2026-10-16 — Rope contact needs both path and painted-triangle checks

A clearance-safe centreline does not guarantee its coarse mapped surface
clears hardware. HC-02's v12 cleared self contact but retained 24 hardware
triangle pairs; source-face splitting around both classes of contact removed
them without changing the acquired surface or painting a replacement rope.
Refining distant strand crossings only multiplies the failure: diagnose arc-
length separation first and correct the path before local face refinement.

Uniform gravity on a pinned rope path can buckle its lower endpoint while
the band contact looks better. Retain the failure. For the static threaded
state, a measured cross-section and offset convex upper envelope give a
bounded, inspectable drape; do not call it a dynamic rope solve.

Blender glTF images can be packed but lazily undecoded. has_data false is not
proof of an absent texture. Access pixels before materializing local maps,
then re-import every FBX and reopen every Blender companion to check paths.
An embedded GLB render alone cannot prove companion portability. Vertex-tint
burning needs a direct baked-albedo companion when FBX cannot carry its node
graph; retain the original GLB, colour data and pre-bake companions.

Repackaging an exact current asset can create a second import receipt with
the same Framewright id. Count unique asset ids, not receipt files. Preserve
all receipts and prefer the latest metadata for the current manifest.

## 2026-10-16 — Small reflective rings need source cleanup before paint

GV-01's fused clay needed separate part cuts and re-centering, but preserving
the acquired joint stumps made adjacent rings overlap. Tighter negative cuts
and uniform per-ring fitting removed crossings without replacement artwork.
Bounded fairing on the original irregular triangles still exposed wavy
highlights. A median cross-section normal attempt made dark discontinuities;
retain it as rejected. Uniform CPU remeshing of each acquired part, bounded
smoothing and a measured 7.6k total prop budget produced the selected result.

When copying a packed Blender file to a delivery directory, assigning `//map`
before Save As with its default relative remapping can silently point FBX back
at the previous directory. The GV-01 actual FBX map-locality audit caught this.
Save the newly local paths with `relative_remap=False`, then export FBX and
reimport it. The selected GLB bytes remained unchanged during this repair.

## 2026-10-16 — Chain clearance must retain the link and its interlock

GV-02's first field partition separated the acquired fused links, but contact
caps still crossed. Subtracting clearance volumes could pass closure checks
while cutting away nearly all of one link. Compare part volume and silhouette,
then inspect the actual export; a watertight scrap is still a rejection.

A later thin-link fit had zero intersections but placed the loops too far
apart to interlock. Reuse the clean acquired link, fit its cross-section from
measured source medial samples, and constrain spacing to the interlinked range.
Verify actual adjacent-loop linking as well as surface clearance. GV-02 v8's
fixed views and the full assembly's Gauss linking checks confirmed the result.
Small boolean/decimation slivers can disappear during GLB serialization; use
scale-appropriate cleanup and re-import the actual file before claiming closure.

## 2026-10-16 — Inspect separated hardware close up and bake metal albedo explicitly

GV-02's full assembly hid jagged acquired contact cuts in the ceiling eye.
Standalone fixed views exposed them even though closure and clearance passed.
Positive smoothing collapsed the thin lower eye; Taubin smoothing retained the
bad notch. Reusing an intact acquired chain-link surface to repair the acquired
plate, followed by a source-paint rebake, produced a clean separate fitting.
Preserve failed derivatives; geometry checks do not replace close-up review.

A diffuse-only COLOR bake from fully metallic sources can produce black.
Temporarily make source material copies nonmetallic for albedo transfer, keep
the target texture disconnected during bake, and restore the delivered metallic
response separately. The source AI albedo remains the authority. For mixed
limestone/bronze, prefer its validated AI material mask over coarse coordinate
slabs that can falsely turn entire stone side faces into reflective metal.


## 2026-10-16 — A repaint must preserve surface exceptions as well as geometry

TW-02's selected old throne had a separate plain inner-arm material. Applying
one new atlas indiscriminately restored stretched decoration that the source
had deliberately suppressed. Retain that material boundary and map a plain
AI-conditioned stone swatch there. Inspect backs as well as fronts: an AI paint
job can invent a rear motif even when every geometry/UV gate passes.

AI metallic maps can miss bronze entirely. Albedo-based calibration helps, but
warm stone may share bronze colours; constrain the mask to the intended acquired
regions and inspect its ends. A hard coordinate threshold clipped the throne's
vertical inlay, despite unchanged geometry. The actual browser also revealed
that the first plinth was too ochre beside the pale throne; a separate pale-ivory
reference/mapping revision resolved the mismatch. Preserve rejected candidates.

For material-only GLB delivery, append maps and replace material metadata while
retaining the original binary payload, geometry accessors and local nodes. A
new rigid parent can correct old front-axis conventions without remodeling.
Existing usable UVs need no new unwrap: reversible OBJ transport preserved all
120,000 triangle corners on each of the first three meshes. Different sized
old guardian variants have different reduced topology/UVs; direct atlas copying
needs proof and cannot be assumed from their matching silhouettes.


## 2026-10-16 - TW-02 metallic masks, small texture details and banner opacity

- Warm ivory/amber paint can satisfy a bronze color mask. The guardian v1 masks
  metallized cloak and plinth highlights; preserve AI albedo and constrain PBR
  metal response to measured source fitting regions. Four-view v2 and actual
  Framewright verified matte stone and localized bronze.
- A full-body 512px review can hide lost small texture details. The actual
  Framewright sword statue exposed a missing helmet slit. Restore only that
  acquired feature from the exact original atlas/UV authority; do not redraw
  it or remodel the helmet. Sword v3 retains the source slit within a bounded
  frontal helmet mask. Record the rejected v2 and the source-image lineage.
- The old banner torn variants use alpha masks, not different mesh silhouettes:
  normalized OBJ hashes equal their intact counterparts per size. Reusing mapped
  RGB is valid for those exact UV authorities, but replacing RGBA with opaque
  paint would erase the tears. Keep each original 4096 alpha mask and MASK/
  cutoff/double-sided settings. This is an inspected invariant, not yet a banner
  repaint completion. Evidence: TW-02/source-group-03/material-invariants.json.


## 2026-10-16 - Banner heraldry and portable cutout materials

- An AI repaint can preserve topology while squashing a graphic emblem. Inspect
  actual banner views. After image-conditioned AI mapping, transfer the intact
  AI reference through existing UVs; keep source geometry immutable. A bounded
  upper-cloth patch showed a lighting transition, so selected v3 extends the
  same reference cloth within mapped borders. Retain both rejected derivatives.
- glTF MASK imports to Blender through alpha math nodes that FBX does not carry
  reliably. Export a direct cutoff opacity texture for FBX and verify actual
  reopened FBX renders. Retain exact original RGBA alpha in the GLB and maps;
  quantify edge-filter differences instead of claiming image-byte equivalence.
- A GLB may have one mesh but multiple instances. The 6m railing/curb sources
  share one 78k mesh between two nodes. Do not flatten or reduce a material-only
  repaint: transport one shared UV authority and retain every original target
  node/transform. Record the generic one-object guard rejection separately.


## 2026-10-16 TW-02 reference aliases and shared-mesh FBX warnings

- Do not infer a 6m reference alias from endswith("6m"): it also matches
  stair-panel-3.16m. The initial CLI refused the nonexistent 3.13m reference
  before inference (empty executions). Use explicit stem mappings and verify
  every input before launch; retain the rejected invocation.
- A shared-mesh FBX material-slot warning is neither proof of success nor proof
  of loss. Group04's two-node curb/rail exported with the warning, but actual
  FBX renders matched both original GLB sections (<.000180 mean sRGB-byte delta).
  Reopen and render actual companions before deciding whether to repair export.
- A view labelled front is a camera convention, not a mounting-normal guarantee.
  Group05 wall-torch plate is edge-on at old -Y and normal to X; measured faces
  establish physical -X front. Use an explicit rigid 180 Z orientation and keep
  source nodes/pivots; do not apply the usual +90 Z without checking.

## 2026-10-16 - Metallic lantern exposes acquired mesh shading defects

Strong metal response revealed facets and uneven edges that the earlier rough
material hid. Weighted normal recomputation alone barely helped; blindly projecting
normals from a denser source produced local artifacts. Compare fixed views and the
actual consumer before selecting either approach. For Mark's explicit smoothing
request, bounded acquired-geometry fairing plus filtered normals worked, with UVs,
triangle indices, glass positions and pivots protected. A visually better candidate
still rotated26small faces: enforce per-face orientation/area guards and backtrack
local displacement before delivery. Never call normal-only changes sufficient from
metrics alone, or expand a per-asset cleanup exception across a material-only batch.

Single-material glass/metal glTF can look opaque or sort incorrectly in Framewright.
Retain the original transmission mask and split original face indices into opaque
and thin-glass draws without changing topology. Mask-border sampling matters. FBX
cannot carry this glTF transmission through the current exporter: supply an explicit
opacity fallback and inspect actual exported views, documenting the appearance delta.

## 2026-10-16 - Selective density increases for reflective acquired surfaces

Mark explicitly broadened cleanup authorization to lighting props and allowed
more faces where curves and highlights benefit. Subdivision alone preserves the
same facets; combine selective edge subdivision with bounded surface fairing and
normal cleanup. Interpolate UVs within the original triangles, retain original UV
vertices/maps and per-face ancestry, freeze bases/mounts, and guard orientation
and area after smoothing. Floor/standing braziers and wall torch improved at
24,733/24,900/16,600 triangles while preserving the preferred black-and-brass
design. This is selective cleanup authorization, not a universal triangle target
or human asset approval. Some acquired handmade waviness remains.

## 2026-10-16 - Repaint preservation can preserve a source assembly flaw

The TW-02 single-link and 1/3/6 m chain sources share exact geometry, UVs and
material bytes, so one AI-mapped link legitimately supplies all four repaints.
However, identical link instances do not prove physical assembly: all source
nodes had translation only, placing overlapping links in one plane. Four-view
and Framewright inspection exposed this. Preserve the explicitly material-only
scope, but flag the inherited layout issue in the asset notes and inventory;
never imply a successful paint/export check validates interlocking or collision.

## 2026-10-16 - Inspect existing feedback before repainting; brass is selective

Mark corrected the assumption that liking one black-and-brass design calls for
repainting every mechanical fitting. All 13 mechanical and four lighting inputs
already matched current models in the older Framewright project. Reuse useful
models and existing material divisions, changing only identified mismatches with
the new brief. Preserve metallic treatment on actual bronze; keep iron and other
materials distinct. A source-path/hash check alone missed the winch's prior SEND
BACK note. Read live review feedback and revision status before acquisition or
mapping. A previously rejected source cannot become suitable merely by repainting
it. Reuse also does not waive new canon, orientation, budget or production checks.


### 2026-10-16 - Locked mapping can still spill a material across inner sidewalls

The Artiss cog reference deliberately kept brass on the central hub, yet all
three v2 locked-mesh paint outputs placed gold on some recessed iron spoke
sidewalls. Exact geometry and UV validation passed. Four-view beauty inspection
caught it; an unlit diagnostic confirmed colour in the albedo rather than a
physical reflection. Do not treat a topology/UV pass as material-region proof.

Retain those v2 outputs as unselected evidence. The v3 correction used a CPU
material-node bake on the same acquired mesh and UVs: preserve the central hub,
remove warm spill outside its boundary, and preserve the mapped broad wear.
No new geometry or inference was used for the correction. The final GLBs retain
every original geometry, normal, UV, pivot and socket byte. Four corrected views
and the actual Framewright models were inspected. Source and editable node
recipes are in work/artiss-tomb-2026-10-16/bake_cog_material_boundary_v3.py and
assets/TW-02/cog-{2m,4m,6m}-material-boundary-v3/ beneath that work folder.
The paint processes failed at teardown after validated output, as recorded;
the correction is not a silent inference retry or a human approval.


## 2026-10-17 - Validate scalar glass and actual FBX material graphs

An untextured constant glass window legitimately has no UV layer. Do not invent
UVs or fail a material-only reuse solely for that absence: verify every assigned
material contains no image-texture node, record the scalar part, and preserve
source geometry. Textured parts still require finite UVs.

The condenser GLB/Blender looked correct while FBX lost all housing colours.
Its imported base colour passed through a vertex-colour multiply node that the
FBX exporter did not support. Reopening an FBX and finding some textures was
insufficient; metallic/roughness maps were present but albedo was omitted.
Four-view appearance inspection caught the failure. All effective colour
attributes were verified RGBA1, so the export-only repair removed that identity
multiplication and wired the existing texture/constant directly. Preserve the
rejected export and exact GLB/Blender. Nonconstant colour multiplication needs
a real bake, not this shortcut. FBX glass remains an explicit opacity approximation.

## 2026-10-17 - Door material boundaries, lossless GLB packing and FBX time

Crypt door AI paint made limestone panels gold and partly metallic. Rectangular
position masks crossed iron rails or left gold strips. A CPU bake using the
original albedo's material boundaries separated the surfaces reliably; preserve
mapped luminance while correcting stone chroma and metallic response. Four
distinct mapping jobs produced validated output then failed teardown; retain
those receipts and do not call the processes clean successes or retry inference.

Appending textures left unreachable old maps in the animated door GLBs and
exceeded Framewright's upload limit. Remove unreachable images and deduplicate
identical payloads in a versioned derivative. Verify every accessor buffer and
visible image byte, meshes, original nodes and animation definitions. A compacted
file cannot claim its entire original binary prefix is unchanged, although all
geometry and animation data can remain exact. Do not raise service limits for
avoidable dead payloads.

Blender's default FBX anim_offset=1 adds one frame on import. The door export
check initially measured a 0.04269 hinge matrix mismatch; anim_offset=0 restored
the stored frames 1-168 at 24 fps with 2.4e-7 maximum matrix error. Inspect stored
timestamps before changing animation curves. Preserve explicit animation baking
for animated assemblies; a static export check does not prove retained motion.

One CPU crypt-right bake crashed inside NumPy with EXCEPTION_ILLEGAL_INSTRUCTION.
Preserve its crash log; the underlying cause is unproven. A separate CPU v2 with
NPY_DISABLE_CPU_FEATURES=AVX2,FMA3 completed. This is a bounded CPU recovery,
not a repeated AI acquisition or a reason to alter the global workstation.


## 2026-10-17 - Descriptive GLB extras can collide with loader semantics

Blender fixed views and exports passed, yet four TW-02 linear trim GLBs loaded
with NaN bounds and a blank Framewright viewport. The installed Three.js
GLTFLoader reads extras.pivot as a numeric vector and adjusts node/child
translation. A descriptive string in that key poisoned transforms. This is a
loader compatibility failure, not insufficient GPU memory or broken geometry.

Use pivot_description for prose. V4 renamed only that JSON key, preserving
full binary data, material fields and numeric transforms. An actual-loader CPU
check reproduced NaNs for all four v3 files and finite bounds for their v4
replacements; actual Framewright screenshots proved visible recovery. Retain
rejected blank screenshots. Blender-only proof cannot establish viewer compatibility.
Evidence: work/artiss-tomb-2026-10-16/assets/TW-02/group09-three-bounds-v4.json
and group09-pivot-metadata-repair-v4.json. Do not patch the app to mask malformed
asset metadata when a versioned metadata-only asset repair suffices.

For repaint-only reuse, compare exported extents to the verified source. An
absolute 1mm base check rejected inherited cornice geometry extending 1.0886mm
below its nominal pivot. Preserve the source and record that deviation rather
than flattening it to satisfy an overly strict new assertion.


## 2026-10-17 — Reused driftglass source selection and material export

- Refresh the current old-project revision before trusting the initial inventory.
  Twelve hero/wall source records had newer geometry cleanup already completed.
  Retain exact current target bytes; do not reconstruct or rescale a shared donor
  to replace them merely because UV/index layouts match. Small tangent, normal
  and scaling-roundoff differences are real source differences.
- For glass on a rough foot, keep optical roughness/transmission masks separate
  from colour masks. A height-based grey albedo mix produced a visible horizontal
  stripe; v3 restored the image-conditioned albedo and confined height grading
  to optical properties.
- Blender's FBX export lost Base Color through a MULTIPLY node combining the
  texture and white vertex colour. Bypass only after proving every used vertex
  colour is RGBA1. Keep the exact GLB and packed Blender graph unchanged. Inspect
  the actual FBX, and label opacity conversion as a transmission approximation.


## 2026-10-17 — Repaint reuse does not excuse visible acquisition debris

The older fallen head's source notes said its shape was acceptable, but Mark
identified a floating fragment in the new material viewer. A strict repaint-only
copy carried that defect forward. Treat the later user correction as the
narrow cleanup authorization: keep the acquired connected sculpture, remove
unsupported fragments, preserve UV/normal/tangent values and original pose,
and retain the rejected source/revision. Do not keep claiming exact topology
once faces have been removed. Connectivity analysis may weld seam positions
for classification; it must not weld or rewrite the surviving attribute data.
Head v2 removed134triangles across8islands and retained14,866triangles.

For face-up fallen or downward-facing ceiling assets, four ordinary orbit views
can emphasize the wrong surface. Add a face/underside view. A temporary rigid
mapping frame can improve image conditioning while original UVs transport the
paint back to the untouched source pose. Verify the mapping round trip and
inspect the actual delivered orientation separately.

## 2026-10-17 — Reuse geometry without inheriting the wrong material economy

Mark clarified that cheap objects should not default to wood. The local Artiss
redesign quotes the World Bible's scarcity/wealth rule, and HC-07 explicitly
requires metal, canvas and salvage. The old wooden weapon rack was therefore
the wrong material reference even though its acquired geometry was reusable.
Reject that reference before mapping; replace its surfaces with utilitarian
iron. Reserve timber for explicitly prestigious Archive/royal/relic use, and
evaluate common-chest interiors as well as the outside. Reuse preserves geometry
and evidence, not every old material decision. Do not infer new buoyancy canon
from older seed documents; DH-03 remains held.

## 2026-10-17 — Inspect unlit side paint before accepting a metallic finish

An iron reference did not prevent the painter from smearing tan horizontal
bands over the weapon-rack sidewalls. A beauty view could confuse that with a
reflection. The unlit close view exposed the map defect. Reject the mapped
candidate, then project an AI-generated neutral iron swatch onto the affected
acquired surfaces through the existing UVs. Retain front/rear detail and original
mesh attributes, and inspect the revised beauty/unlit views plus actual FBX and
Framewright. Increasing metallic response alone does not correct wrong albedo.


### 2026-10-17 — Chest atlas transfer must respect the material's UV set

The common chest assembly's panel material samples TEXCOORD_1, while the
retained mesh also has UV0. The first CPU panel bake treated it as an unsupported
slot and failed. Use a temporary UV0 texture carrier only on the isolated bake
target, and bind the resulting maps to the exact original assembly. Preserve both
UV accessors, animation and hinge nodes. Do not misdiagnose this as a scalar-only
oak material, or rerun an already-successful hardware bake.

A warm-colour mask across irregular acquired material regions created teeth in
iron lid straps. Continuous object-space sampling of the same AI iron swatch
across both original materials, with smooth measured strap bands, removed that
surface defect without changing geometry or UVs. Inspect the unlit result too.

### 2026-10-17 — Preserve alternate UVs and equivalent specular when reusing GLB in FBX

Source wooden chests sample their lid-interior material from TEXCOORD_1. Blender
imports that choice, but FBX reimport lost the material-specific UV node and
sampled UV0, visibly rotating the grain. For the FBX export copy only, transport
the affected polygon-loop coordinates into UV0 and remove that material's UV-node
override. Retain canonical GLB/Blend geometry, both UV sets and source maps.

The source also stores neutral glTF specular tint (2,2,2). FBX loses that tint;
carry its neutral multiplier into scalar specular strength. Appearance comparison
must preserve the authored strength: the calibrated helper resets scalar strength
to .5 but leaves the glTF tint intact, so applying it during this comparison
creates an artificial mismatch. Selected authored-material paired views differed
by at most .222015 mean RGB byte value after UV transport, versus 4.53 earlier.
Keep earlier comparisons and state that the selected check preserves authored
specular. This is export verification, not a reason to silently change sources.

Read asset bounds before interpreting dimensional filenames: the old grab-ledge
150/250/400 cm variants all span 150 cm and instead encode top elevation relative
to the original floor/wall datum. Preserve those pivots and label the elevations.

### 2026-10-17 — Chest interiors need measured masks and continuous sampling

Prestige chest mapping stretched the interiors. Dominant-face-axis projection
of a generated swatch introduced grain changes across corner triangles; smooth
triplanar weights from the existing normals corrected that without changing
mesh geometry or UVs. A symmetric bounding-box cavity mask then leaked onto
the relic chest's rear crest. Its acquired cavity is offset: measure the actual
interior wall planes and use those bounds. Always inspect the rear and unlit
interior before selecting the repair. Earlier failed derivatives remain evidence.

The reduced royal lid panel and dense assembly panel are not identical enough
for the CPU bake guard (size ratio .968). Do not widen that guard just to finish
the batch. Here the original analytic UV1 frame is shared and provides a direct
texture reuse route; verify the UV formula against both sources and record its
residual. Preserve the exact final assembly geometry and animation. Propagate
the material's UV link to split metallic/roughness textures before saving the
canonical Blend; only the FBX export copy needs per-loop UV1-to-UV0 transport.

Four paint jobs again wrote validated outputs and failed during teardown with
exit -1073741819. Independent output inspection can select a review derivative,
but it does not convert failed process receipts into successful executions.
No automatic inference retries were made. Source OpenClose playback likewise
does not resolve an inherited visible lid-to-hinge gap; record that separately.

### 2026-10-17 — Preserve clay interiors and fracture correspondence

An urn exterior mapping duplicated its emblem onto the rear and painted the
inside lip. Inspect rear and elevated interior before accepting a surface.
A generated motif-free swatch can repair the rear through unchanged UVs; use
measured height/angular masks and original inward-facing normals for the clay
lip. Preserve original unglazed interior and fracture materials where they are
already correct. Do not paint degenerate scalar-material UVs as if they were
an exterior atlas.

The unlit helper handled textured materials but skipped scalar ones, making
clay appear black in the diagnostic. Optional scalar base-colour emission fixes
the diagnostic; it is not a reason to alter the actual ceramic material.

For shared intact/broken paint, bake onto the original assembled exterior only,
excluding internal caps in a temporary bake target. Before sharing that atlas
with scattered fragments, verify every fragment's vertices, normals, UVs and
indices are identical. Keep final cap materials and fragment transforms exact.
A successful material transfer does not approve the old high triangle count or
make the original scattered arrangement into a physically settled simulation.

### 2026-10-17 — Ledge height variants do not imply shared reduced atlases

The 150/250/400 cm ledges share source shape and dimensions but were reduced
independently. Neither direct index-byte equality nor per-triangle geometry/UV
correspondence supported sharing one map blindly. Align only temporary bake
copies by the measured elevation offset, retain the CPU bake placement guard,
and bake into each original UV set. Here both transfers passed with centre
offset zero and size ratio 1.0. Bind only the resulting maps back to unchanged
source GLBs so their floor/wall datums and mounting elevations survive.

A material-only reuse pass also cannot prove swing mechanics: the original
ring and upper mount are a single mesh. Keep that mechanical separation gate
explicitly open even when the smooth metallic surface and portable exports pass.

### 2026-10-17 — Flat textile motifs need overhead and reverse inspection

Standard four-view cameras can show a thin rug almost entirely edge-on. Add
an overhead beauty/unlit pair and an underside view. A rigid temporary upright
paint frame exposes the top to AI mapping without changing final geometry, but
mapping can still erase an emblem or distort a narrow border. Do not accept
that from a distant side view. After image-conditioned acquisition, CPU-bake
the generated design into the existing top UVs; keep rejected evidence. Inspect
the reverse independently and use a quiet generated field there when an ornate
AI border fails. Final GLB geometry/UV bytes must remain exact, and paired FBX
views must include both faces of the textile.

### 2026-10-17 — Inspect RGBA decals through compositing, not hidden RGB

Image previews can expose colored RGB beneath zero-alpha pixels and make a
clean decal appear to have a glow or colored fringe. Inspect alpha statistics,
then composite diagnostically against both a pale limestone color and dark
teal, and inspect the actual consumer. Preserve generated RGBA bytes as the
deliverable; diagnostic composites are evidence only. Conversely, a cobweb
can contain real opaque fabric-like membranes despite having an alpha channel.
That requires an image-conditioned visual correction, not merely relabeling it
transparent. Retain the rejected candidate and verify the corrected gaps.

### 2026-10-17 — Audit exported components after QEM, before paint

The corrected Artiss ceiling's feature-QEM Blender report showed 20,000 triangles
and zero boundary/nonmanifold edges, but the exported GLB contained 19,997 faces:
one closed main component plus three isolated single triangles. Reopening the
actual GLB exposed nine boundary edges and component sizes [9997,3,3,3]. The
three remnants measured 4.318, 0.941 and 0.719 cm across; removing those alone
left one closed 19,994-triangle mesh. Restore declared bounds and pivot before
fresh UV transport, and audit the painted GLB and FBX again. A topology pass on
an intermediate Blender object does not establish the exported file's closure.


## 2026-10-17 — Preserve shading through local topology cleanup and verify chain fit

TW-02's new winch painted GLB carried flat imported custom normals despite smooth polygon flags. Welding geometric UV splits and restoring a smooth normal field removed the visible triangular reflections without changing face positions or UVs. A later localized 2–6 mm fold cleanup disturbed that field again; exact UV-corner normal transfer from the reviewed smooth derivative restored it while keeping the repaired geometry. Do not treat smooth flags alone as proof of smooth exported shading. The selected actual GLB and FBX pass self/interpart-intersection and visual checks.

A chain wrapped along a convincing helix can still intersect every neighbour. Reject by actual triangle intersections, then also measure the Gauss linking number: zero intersections alone can mean disconnected links. The selected winch uses .315 m radius, 34 steps across two wraps and .13 m tail spacing; all 40 adjacent pairs are linked and no surfaces cross at rest. Retain failed searches instead of mistaking them for simulation.

For reduced painted instances, flatten the original parent transforms into vertices before reduction and rebake; a parented link produced a rejected 0.1001 m frame mismatch. The flattened derivative preserves original world geometry, UVs and maps. For FBX only, single-user mesh copies avoid ambiguous material bindings on repeated links; keep GLB/native instances shared and compare actual exported appearance.

## 2026-10-17 — Coin contact, visual stability and aggregate instance budgets

An acquired coin can be instanced into a mechanically nonintersecting arrangement that still looks unsupported. TW-02's freefall experiment was not settled after six simulated seconds (.19585 m maximum motion during the last second); preserve that failure instead of labeling a snapshot a rest pose. Loose vertical-contact placement formed cantilevered voids even with a centre-support heuristic. The selected review alternative uses explicitly curated touching treasury stacks, with no dynamics claim. Inspect all sides and state the chosen layout honestly.

Full acquired-mesh collision setup was expensive at 600 bodies. Temporary conservative contact proxies improved the CPU experiment, but did not establish physical or artistic acceptance. They were never exported. Account for evaluated triangles as well as shared geometry: the selected pile has one 1k-triangle mesh but 614k scene triangles. An attempted 200-triangle reduction was refused by the pipeline's 1k minimum. The 1k derivative required rebaking its painted maps and passed the fixed-view appearance gate; retaining a 3.1 MiB instanced GLB does not prove a game-ready LOD budget.


## 2026-10-17 — Tiny cut faces, UV serialization and evaluated pose proof

A closed Blender polygon mesh can acquire zero-area triangles during GLB triangulation. Audit the actual exported triangles before UV/paint. For the Artiss cabinet, a coarse 50 micrometre collapse introduced a nonmanifold edge; the selected 0.1 micrometre collapse plus coplanar dissolution kept the inspected surface within 13.2 micrometres. Preserve valid microscopic faces rather than relaxing geometry checks.

The stock OBJ writer rounded coordinates to six decimals, collapsing distinct tiny cut vertices even though the UV authority itself passed. The painter correctly refused that input before inference. Serialize sufficient precision and test the exact exported OBJ with the actual loader/normal-proxy validation before launching the distinct corrected attempt. Tiny zero-area UV projections can receive separate minimum-sized charts without moving geometry; visible surfaces must not be hidden behind that exception. Greedy nearest-face UV matching can consume the wrong neighbour in microscopic clusters: use bijective vertex permutations and globally ordered one-to-one triangle matching, with a measured maximum correspondence error.

For articulated previews, verify the evaluated world pose. Imported quaternion-mode objects ignore direct Euler assignment unless the mode/transform is made explicit. glTF export with animation disabled can still export the default frame unless export_current_frame is set. An "open" filename and successful export do not establish open doors. Inspect the actual pose, then audit the exported motion. Continue applying the earlier descriptive-pivot lesson before import: string extras.pivot must be renamed to pivot_description, especially on parented moving parts.

## 2026-10-17 — Interior UV repair must remain within one atlas chart

A mesh can have valid finite UVs and still show bright striped or triangular interior artifacts. On the map chest, sampling corners from different floor triangles and interpolating a new wall chart crossed unrelated atlas islands, including bronze handle paint. Reject that result. Select one clean contiguous region inside a single source triangle, verify its sampled colors, and remap only the affected interior faces. This retained the original AI image bytes and all exterior UVs while repairing the projection; no repaint or geometry inference retry was needed.

Centroid-only face classification can stop short across large shelf triangles and leave jagged bands. Classify complete horizontal faces with their normal and geometric extent, preserve vertical front trim, and inspect elevated unlit as well as PBR views. v3 fixed trays but not whole frame floors; v4 fixed complete interior faces. Retain both negative examples. Actual Framewright playback and an open pose reveal surfaces that closed beauty views conceal.

### 2026-10-17 — A rear-flash cut can expose overlapping acquired skins

The generated label plaque had a paper-thin front plus a backdrop-like rear flange. Cutting the flange and independently capping every loop produced two overlapping closed shells; closure alone passed but actual exported self-contact/component checks failed, and the rear render turned black. Inspect connected-component bounds, retain the acquired front relief shell, and remove the redundant inner/rear skin. Recheck all four views and actual exported topology before UV preparation. Thickness normalization must describe the intended plaque, not the spurious backdrop extent.

### 2026-10-17 — Astrolabe separation must clear more than the rest pose

Subtracting an exactly coincident extracted arm created overlapping dial caps;
using the same clipping volume for intersection and difference avoided that
failure. Tiny cut faces and a detached sight-tab stump still needed explicit
cleanup. V4's actual exported GLB is closed and clear at rest, yet every sampled
nonzero dial tilt collides with the cradle. Static topology is insufficient
evidence of fitted rotating parts. Test the intended axes before paint, preserve
the failed poses, and repair the source-derived separation. For metallic
diagnostics, explicitly assign the diagnostic material to every mesh: changing
an unused material can silently produce a white clay render.

The selected astrolabe v6 clears these sampled poses after a 22.2 cm cradle
clearance cut and fitting the acquired sighting arm within a 21.2 cm radial
extent. The geometry and painted surface remain separate evidence gates.
The stock OBJ export and later paint GLB each collapsed a microscopic UV
triangle despite broad UV metrics passing. Twelve-digit OBJ serialization fixed
the former; restoring the exact pre-paint face UV fixed the latter. Recheck
every actual delivered UV triangle, not only the aggregate validation fraction.

The scroll rack repeated the map-chest interior projection problem: front beauty views looked sound while elevated unlit views revealed bronze stripes in the lower troughs. Include interior angles for open furniture; map repair must stay inside one contiguous clean atlas region while retaining original image bytes and exterior UVs.


### 2026-10-17 — Clearance must follow the acquired part; interiors need planar normals

A simple bar/cylinder cutting volume did not fully clear the sextant's irregular acquired lower shoe. Subtracting a slightly expanded copy of the actual extracted arm resolved the remaining static overlap while preserving the selected silhouette. Widening a separation can expose disconnected slivers: check connected components again. Blender dimension edits made sequentially on a live object can use stale evaluated scale; assign the full dimension vector, update and apply it before the next boolean. Test the actual exported mesh, not only native copies.

Ground-skirt geometry can dominate normalization bounds. Remove it before final dimension fitting. A hollowed crate can be closed and intersection-free while its new interior still shows diagonal shading under interpolated normals. Inspect from above and retain planar normals on those cut surfaces; keep smoothing on the acquired exterior. Preserve the earlier shaded version as negative evidence.


## 2026-10-17 — Hollow acquired props expose unobserved cut surfaces

A closed packing crate painted well, but its newly cut top rim inherited stripes
from exterior projection. The separately inspected cavity uses a quiet scalar
iron material on new cut faces; exterior AI paint/geometry/UVs stay unchanged.
Always inspect an open/interior view before declaring a container review-ready.

A tightly curved swept ellipse used as a cargo-ring separation cutter crossed
itself because tube radius exceeded local curvature radius. Replacing the
throwaway cutter with a closed extruded annulus removed these Boolean artifacts.
The delivered plate/ring remain derived from acquired geometry. Validate the
cutter as well as the resulting parts; preserve the failed candidate.


## 2026-10-17 — Reuse sound source paint before another inference pass

Cargo-tag AI paint doubled the front feather while the reverse carried a clean
single feather. A CPU selected-to-active diffuse-color bake from a temporary
mirrored copy of the acquired reverse face onto the existing front UVs fixed
it. Final geometry, UVs and normals remained exact; other atlas regions were
retained. Four GLB/FBX views and the live consumer confirmed the result. This
is source-paint transport, not a new manually reconstructed model; keep the
rejected paint and hash-bound transfer recipe with the delivery.

## 2026-10-17 — Verify actual motion and constrain reduced-mesh fairing

A Blender object imported with quaternion rotation mode ignored Euler assignments.
A nominal multi-angle collision audit therefore tested the closed gate repeatedly.
The exported open-view render exposed it. Set the intended rotation mode or apply
world matrices explicitly, record measured rotations, then re-import the actual
export and repeat clearance checks. A pass over requested angles alone is weak.

Global angle beveling over irregular acquired triangles created nonmanifold edges
and self intersections. Preserve original bevels and dress only necessary cuts.
For thick double doors, front seam clearance alone is insufficient: the rear
meeting corners can cross during initial swing. Source-derived circular relief
along the real hinge sweep clears this without widening the visible front seam.

Implicit Laplacian smoothing on a roughly 544k-vertex gate dominated CPU time.
Zero dense smoothing followed by explicit fairing on the reduced mesh was fast.
Bounded displacement alone did not prevent skinny triangles inverting: detect
flipped faces/self contacts and locally backtrack affected vertex displacement.
Keep rejected candidates, cancellation evidence and the final actual-export proof.

## 2026-10-17 — Inspect metallic predictions by material, not just file validity

AR-03's AI metallic image was numerically valid but semantically inverted: bronze
samples were near zero while limestone samples were higher. The initial threshold
made the entire derived map zero. A gold albedo alone hid the mistake in some
lighting. Keep raw maps; check known material samples and inspect the actual PBR
consumer. A calibrated mask from the unchanged warm saturated bronze albedo
restored metal response while retaining nonmetallic limestone. Geometry, UVs,
normals and albedo remained unchanged; the earlier matte previews are retained.

GV-03's source wheel removal exposed a thin-wall hole. A transported adjacent
acquired pedestal slab repaired it, but transporting its back wall too introduced
self contacts. Restrict the patch to the front wall and recheck after remesh/QEM.
Increasing the budget alone did not fix the crossing surfaces. Keep close-up
evidence: a whole-prop render can hide small open cuts and isolated dark triangles.

## 2026-10-17 — Camp tools: attached backdrop and budget-sensitive structure

HC-07's acquired shovel included a thin floor-shadow spur connected to its tip;
component-size cleanup could not remove it because the whole shovel was one
component. The first bounded oblique cut left a visible lip. A second recorded
cut removed the spur while retaining a cupped blade, and the actual 8,000-triangle
result passed manifold/self-contact checks and four-view inspection before paint.
Request no ground plane/cast shadow in new isolated geometry references. This
reduces a known acquisition risk; it does not substitute for side/back review.

The ledger table passed numerical reduction at 10,000 triangles but lost too much
frame clarity. Mark's higher-count permission supports a deliberate 18,000-triangle
revision, chosen for appearance rather than the profile ceiling. Increased count
still left 21 local crossing pairs; bounded local repair and another actual mesh
audit were necessary. Keep the lower-detail and rejected normal experiments.

## 2026-10-17 — Imported rotations and parent transforms require actual motion proof

HC-08's case lid appeared to pass a sweep while remaining closed: imported glTF
objects used quaternion rotation, so assignments to `rotation_euler` had no effect.
Set the rotation mode explicitly, verify the resulting pose, and check the actual
exported GLB and FBX. Once the hinge moved, two clasps needed a recorded 3.5 mm
forward fit before all 106 one-degree samples cleared. Preserve the rejected
static sweep and intermediate candidates rather than relabeling their evidence.

Before parenting acquired clasp parts while preserving world transforms, update
the dependency graph after changing their locations. Reading a stale
`matrix_world` teleported the first clasp derivative to the origin. Visual open
and closed views, bounding checks and actual motion all matter independently.

The Spark disc's bounded smoothing left its separate cap intersecting the body
on rotation. Clamping vertices back to cut planes cleared the cap but introduced
three body self-contacts. The selected derivative instead retains the manifold
smoothed geometry, raises the cap rigidly, and applies a shared positive vertical
scale to retain 2 cm total height. Recheck topology and the full cap sweep after
each repair; a clean gap alone does not prove a clean mesh.

## 2026-10-17 — Ferrule fitting must preserve radial ordering

HC-08 hero sword collar fit v2 projected several acquired folds to the same
rounded rectangular surface and introduced 25 nonadjacent contacts. It is
retained and rejected. V3 keeps positive radial dependence (exponent 0.35),
preserving layer order while reducing wobble; its topology passes. Axial lip
compression v4 cleaned the scalloped silhouette but introduced two contacts.
V5 resolves those in one bounded local iteration (0.9535 mm maximum), with
13,998 triangles unchanged and zero holes, degenerates or self-contacts.
Close-up front/side and all four fixed views were inspected before paint.
Do not treat a mathematical surface fit or a cleaner silhouette as topology
proof; retain both visual and contact evidence after each local repair.

## 2026-10-17 — Revision attachment inherits metadata; refresh after linking

Framewright's asset revision endpoint copied the earlier sword's display name
and notes onto the new current model. The new GLB was correct but its notes
still described a brass crossguard and 5,000 triangles. Retain the import
receipt, attach the family, then reapply and read-verify the intended current
label/tags/notes. Verify the served GLB hash independently. HC-08 sword, pair,
layout and image reference are corrected with retained refresh receipts.

For the canvas material, broad five-pixel shading blur erased useful painted
wrap boundaries. One-pixel blur with a 4.5 cm AI weave repeat retains readable
overlap edges at close range. Inspect the hilt separately, including the live
viewer, rather than accepting the whole-sword thumbnail as material proof.

DH-02's touching canvas folds did not separate under local smoothing applied
around both sides (3 mm and 6 mm bounds). A one-sided, weighted two-ring offset
of at most 2 mm cleared the specific contact without replacing acquired
geometry. Topology and four-view inspection, rather than displacement size,
determine the selected candidate.

## 2026-10-17 — Lowest-vertex grounding is necessary but not sufficient

DH-02's first rigid arrangements passed contact and minimum-height checks, yet
the pack's static straps supported its body like stilts. Operator views rejected
those poses. Rotating the intact pack onto its side gives the body a plausible
resting surface without changing painted geometry. Keep the rejected poses,
inspect the full composition from above as well as profile views, and keep
physics/cloth certification separate from visual grounding.

## 2026-10-17 — Measure acquired openings before fitting separate parts

DN-01's five vent openings are not uniformly spaced, and the outer two are
narrower. Equal-spacing guesses placed canvas inside stone or bronze. A ray
survey of the actual acquired vent located each gap, lintel and lower ledge;
individual cloth placements then preserved painted geometry and cleared the
hanging bodies. Include the cloth mesh's offset from its top-pin pivot when
centering it. Allow only the declared concealed pin band to contact the lintel;
an arbitrary overlap allowance can conceal a bad fit.

The acquired cloth was closed but contained 16 handles/pinholes. Closed-edge
checks alone did not establish a usable ribbon. Source-guided voxel repair
introduced three fully enclosed negative-volume cavities; removal preserved the
exterior exactly. Reduction passed its numerical surface gate but transported
dense voxel normals produced visible ripples. Smooth vertex normals and a
bounded contact repair passed the selected four-view gate. Preserve each failure
and distinguish topology, distance, normal-field and visual evidence.

Vertical shear, rather than rigid rotation, gave sloped passage modules the
requested 4 m vertical clearance while preserving vertical connector planes.
Verify actual exported floor/ceiling rays and connector samples; transformed
bounding boxes alone cannot prove a walkable passage.

Explicit UTF-8 is required when reading JSON labels on this Windows host.
Default text decoding silently produced mojibake in otherwise valid receipts
and live asset labels. Repair metadata from exact intended labels and read it
back; do not regenerate or replace correct model bytes to fix text.

## 2026-10-17 — Imported rig display helpers are not production geometry

Blender's glTF import created an 80-triangle icosphere used as a bone custom
shape. DN-01's first breeze package accidentally included it in FBX export and
render bounds: the FBX appeared as a large white ball and the intended model
was framed too small. Retain the rejected package. Clear actual pose-bone
custom-shape references, remove only those identified helper objects, then
verify the expected mesh set before packaging or computing render bounds.
Selected package has six meshes and 39,930 triangles, with source/FBX appearance
and all 193 actual cloth deformation frames checked. Animation equality alone
cannot detect unrelated extra geometry.

Imported UV seams duplicate coincident vertices. A raw-index adjacency test
reported cloth self-contacts at rest despite unchanged geometry. Weld positions
within 1e-6 m in an evaluation-only mesh before testing nonadjacent contacts;
preserve production vertices, UVs and weights. Check the whole animation,
the pinned band and the hanging-body clearance separately.

The shared mechanical packager's inherited Hinge_Left/Hinge_Right defaults
failed for a sliding slab and floor ring. Bind explicit object names per model
and preserve the failed first package, rather than treating successful geometry
export as proof that the intended animation target was packaged.

## 2026-10-17 - RC-01 thin metal and inherited emitter checks

Automatic QEM alone left thin door/cuff folds despite preserving apparent
silhouettes. The selected door and cuff use actual voxel/QEM derivatives with
20k and 6k triangles, then four-view inspection before paint; increasing the
budget without correcting topology was insufficient. Keep the rejected QEM
and bounded-fairing attempts. Texture transport expects GLB, not Blend; CPU
format/name failures must not be mislabeled inference crashes or trigger an AI
retry. Successful paint validation and a later process teardown crash are
separate facts, recorded separately.

An inherited emitter frame had 15 self-contacts despite a prior closed-face
check. Repaired copies passed the stricter test after bounded local fairing
plus two measured one-sided offsets, retaining face/UV arrays and maps. A
per-mesh self-contact pass does not establish clearance between separate frame
and glass meshes; the 504 inherited cross-mesh contacts remain explicitly
pending classification. Do not silently certify or alter the original.

## 2026-10-17 - RC-01 exported motion, precision and glass clearance

Imported glTF objects may retain quaternion rotation mode. Keying Euler
properties alone produced plausible recorded angles but no real exported door
motion. Set the intended rotation mode and audit evaluated world transforms in
the actual GLB/FBX over all 193 frames, including contacts. Retain the failed
Euler-on-quaternion version; property values are not movement proof.

Native surface checks do not guarantee export precision. One fitted wall
triangle became degenerate after GLB quantization and evaluation-only welding.
A local merge/dissolve with normal transfer fixed it with a 3.815-micrometre
maximum vertex shift. Audit the final bytes, not only the source Blender scene.

The inherited emitter contacts were mostly boundary coincidence with a small
real overlap. Expanding a complex frame as a Boolean cutter destroyed almost
all glass, caught by a volume-ratio gate. The unexpanded cutter, tiny inset,
bounded local fairing and 0.995 radial fit retained 98.6582% of glass volume
and passed actual GLB/FBX self/interpart checks. Fairing can reintroduce contact
with a neighbouring mesh; recheck both. Do not blame the rejected expanded
cutter result on dependency-graph timing without evidence.

A projected tally decal crossed a stone joint and visually broke the strokes.
Move the mapped image onto a continuous panel and retain its wall in a cutaway;
removing that wall leaves floating marks. Compare exact exported interior views
as well as exterior fixed views. FBX glass opacity is a documented approximation,
not proof of identical transmission optics.


## 2026-10-17 — CH-03 rig axes, glove weights, scale and review helpers

Manny FBX bone local X can follow the limb, so a generic local-X deformation
suite may twist elbows/knees rather than bend them. A mechanical pass is not
visual bending proof. Derive world hinge axes through current bone matrices,
inspect actual exported skin and retain the misleading exploratory receipt.

Measured finger joints do not make automatic weights sufficient. The raider's
coarse gloves needed local linear subdivision and source-bound digit weights;
limit wrist influence anatomically. Distance fading along the entire finger
left distal spikes; the proximal-only wrist guard worked. Preserve source UVs
and images, audit the refined surface and stay under the NPC ceiling. A compact
curl is still not a verified weapon grip.

Blender glTF import creates an Icosphere in glTF_not_exported for bone display.
It is not in the delivered GLB mesh list. Exclude this helper from geometry
counts, surface audits and camera fitting; otherwise audits find an imaginary
80 triangles and a one-metre surface discrepancy. Do not delete source geometry
to fix an importer helper.

A .01 armature scale can render correctly through skin matrices but give static
consumers two-centimetre bounds. transform_apply on this bound pair shifted skin
by .923 mm; explicit world-space data normalization preserved joints and stayed
within 6.9 micrometres. Check both skin and consumer dimensions. A real root bone
is appropriate for Manny; the base gate currently omits its own declared root
from the allowed-name union, requiring a scoped explicit-root allowlist here.
Do not misreport that as a new skeletal contract or human approval.

FBX bakes object transform channels. Apply comparison-axis transport AFTER each
frame_set, or the animation restores the old orientation and creates a false
large pose discrepancy. Packed GLB metallic/roughness need separate scalar
textures for a portable FBX; decoded channel comparison was exact. Keep failed
checks and their corrections rather than silently changing success criteria.

## 2026-10-18 — CH-03 targeted face mapping and incomplete native paint

At a whole-body paint scale, small eye regions can become black masks. A separate
image-conditioned head pass improves features, but a broad head mask can paint
skin onto hair and collar. A source-geometry face mask limits atlas replacement
to the actual face. Verify unchanged geometry/UVs and byte-identical texels
outside that mask; inspect front and side as well as full-body views. Retain the
rejected full-head result. This does not add face geometry or certify hero-level
close-up quality.

Distinguish a native paint crash after validated artifacts from a crash before
output. The carbine attempt produced no maps or validation and is failed, even
though its input mesh/UV CPU checks pass. Do not infer a root cause from generic
Qt warnings, label an unpainted mesh finished, or retry the same attempt
automatically. Body output validation is separate evidence from native process
exit status; keep both. Subsequent face-only mapping is a distinct scoped task,
not an identical crash retry.

## 2026-10-18 — Judge translucent states from pixels, not file lengths

Equal native PNG lengths and a subtle visual change were mistaken for a missing
steady field. Per-pixel comparisons, particle data and shader-channel probes
showed correct controls and desaturation. Retain the correction receipt and
state captures; measure representative colored regions before declaring an
unresponsive effect. Native resource teardown also needs time to drain: preserve
crashes and avoid immediate manual render-target release plus editor shutdown.


## 2026-10-18 — SaveMap copy is not a live world rename

The native FX-02 sequence saved before a SaveMap-as operation retained references to the old map. Both runtime-player and editor-scrub checks resolved zero actors. Saving the destination map, explicitly loading it, then binding and saving the sequence/current level corrected the issue. Fresh packaged editor scrub proved 45-degree cap yaw at 0.2 seconds. Successful file loads alone do not prove sequencer binding. Original package retained.


## 2026-10-18 — Native Sequencer parameter keys use tick resolution

MovieSceneParameterSection.add_scalar_parameter_key takes native tick-resolution
frame numbers, unlike scripting-channel add_key display-frame behavior. Using
display frames advanced the eight-second FX-03 clock by 0.02 seconds. Convert
seconds using the sequence tick rate (192000 ticks for eight seconds at 24000 Hz).
Fresh packaged scrub at 0.5 seconds then returned exactly 0.5. Retain the failed
zero-frame capture and verify a representative intermediate value, not merely
that keys exist. Source GLB/FBX geometry and UV comparisons matched within
rounding; the rejected UV-flip experiment was not evidence of broken source UVs.

## 2026-10-18 — Manual scene captures need persistent post-process state

SceneCapture2D.always_persist_rendering_state=True was necessary for manual
post-process comparison captures. Without it, OFF and ON images were identical.
Negative Tomb Grade exposure values are EV100 only with extended luminance range
enabled; read the actual game's configuration and reproduce it in the isolated
review project. Otherwise the same values can produce white captures. Use
repeated disabled controls to bound dithering/temporal variation; do not call a
two-level difference an effect when the control varies by three levels.

The TA-01 multi-mode capture wrote all requested outputs but exited 3221225477
during teardown. Preserve that execution as failed. Separate packaged reopening
exited 0 and proved load/capture, without erasing the earlier failure or claiming
cooked runtime/GPU performance certification.

## 2026-10-18 — Door-open static audits do not prove the animated opening

Drift Well's route audit disables intentional gate collision. It reported clear
while the actual fully-open vault leaves still blocked the player because the
pivots were 54 cm from centre instead of the authored outer hinges at about
183 cm. Inspect source bounds, use the real outer hinge and confirm a pawn can
walk through the animated opening. Keep failed traversal evidence alongside
the corrected pass; actor state `open=true` is not traversal proof.

Background editor throttling also reduced automated PIE to about 3 FPS. The
native setting is accessible as `bThrottleCPUWhenNotForeground` on
`/Script/UnrealEd.Default__EditorPerformanceSettings`; the Python snake-case
property name was unavailable. Temporarily change it in memory for input-driven
probes, then restore it and Slate throttling without saving user configuration.
The jump harness must accelerate and settle with ordinary movement inputs:
overly slow steering and unbraked landing velocities caused misses despite
reachable platform spacing. Preserve those misses, not just the later pass.

Final material audits must include newly added actor tags and reused parts,
not just the original builder tag. A wooden chest lid's interior still sampled
DefaultTexture; its original GLB embeds the image on UV1. Restore that exact
binding through a map-local override and retain source hashes. A clean direct
material scan is not a claim about recursively unresolved material instances.

## 2026-10-18 — Loading Bay: verify the combat space in motion

A clear static walk audit did not catch a missing floor underneath a raised
gallery. A real knockback carried the player underneath it and out of the map.
Give accessible undercrofts recovery floors, then verify ordinary movement and
an isolated below-room restart. Keep the failed run as evidence.

The shared enemy StateTree uses a 100 cm centre-distance melee condition.
Scaling a heavy's capsule can make that condition geometrically unreachable,
even with valid navigation, animations and attack tokens. In this isolated
prototype, 1.25x body scale (versus .85x lights) restored attacking; leave shared
assets intact. Verify repeated pushing against a heavy that actually attacks.

Explosion visibility traces target the actor pivot. A wall pivot buried below
a sloped ramp can be occluded despite a bomb visibly landing nearby. Place the
partition on a flat landing above the floor, and verify an actual thrown bomb.
Runtime navigation must be built, and a bombable route needs dynamic updates;
RebuildNavigation alone did not make the initial static Recast data usable.

Interaction owners with an existing OnInteract handler must not be implicitly
signalled first: opening one double-door leaf before Operate runs makes the
stay-open guard skip the linked leaf. Preserve explicit signal targets and let
the native owner callback perform its operation once.

## 2026-10-19 — Blade UI evidence must track real events and operator ownership

A cancelled throw, destroyed projectile or room reset must not produce a catch
pulse. Record catches at successful arrival, and damage confirmation only after
hostile ApplyAttack.Landed; preserve the projectile's existing per-pass hit set.
Behind-camera blade bearings must use camera-space lateral direction, not the
mirrored screen projection. Test portrait, ultrawide and normal viewports.

Use keyword Rotator fields or kit.rot(yaw,pitch,roll) in UE Python probes.
Positional Rotator(-12,90,0) rotated the review camera incorrectly. A completed
probe is not a passed probe: check accepted throws, blade counts and recall.
When owner input starts during review, stop driving the camera and hand control
back; preserve the contaminated captures rather than claiming visual acceptance.


## 2026-10-22 — Animation export correctness and quality need separate receipts

A fresh Character02 packet can pass 19-clip GLB/FBX pose round trips and actual
baseline locomotion probes while failing its relaxed-standing stance contract
and sampled hand/coat clearance. Keep pose, skin/surface, technical export and
human/gameplay decisions separate. A duration edit does not repair a stance;
compare normalized coverage before treating more intersection samples as a worse
performance. A source-space floor plane is not a measured in-game floor.

Blender imports may contain both Key|root|Clip and root|root|Clip FBX actions.
Resolve the correct armature action explicitly. Prefer exact glTF names: matching
an Idle_ prefix also matches Idle_Swords. Never leave technical_passed true after
an export/check exception. Retain failed attempts rather than overwriting them.

Preserve synthetic root tracks as armature-object animation when that object is
the existing export root. Do not add a native bone or discard travel to make an
export pass. Timing edits must refuse event/transition/root contracts they cannot
update. A foot-sync marker is not a support interval; moving a limb while leaving
its existing IK target behind can undo the correction in the game.

## 2026-10-22 — Inspect the final game pose before attributing source collisions

Character02's previous packet had 192 hand/coat contact observations in 575
source poses, but the runtime clearance layer already removed those in game.
The repaired source is independently clear; preserve the distinction in before/
after captions. Source stance/clearance and consumer behavior require separate
receipts. Moving elbows alone initially worsened thumb/coat contacts: repair the
resting hand pose and measure the skinned surface, including thumb/finger overlap.

Attack 03's -2.254 cm source-space sole height was not penetration against the
actual dungeon floor. Real input through all three combo sections and collision
traces yielded positive sampled sole gaps in baseline and installed repeat runs.
Do not alter an attack's root, foot contacts or timing to satisfy a hypothetical
zero plane. Conversely, post-combo resting-foot penetration on uneven tiles and
brief Attack 01 finger contacts still require their own work; a clean Attack 03
sample is not universal terrain or combat acceptance.

## 2026-10-22 — Diagnose gait calibration before changing skin weights

The user rejected Character02's walking legs after technical locomotion checks
passed. The latest arm/idle repair had not changed its lower-body walk matrices.
The legacy retarget's signed Y-axis leg rotation, intended to adduct this rig,
instead increased reference ankle width to 60.44 cm. Narrowing that gait to a
24 cm foot corridor at the old hip height then forced excessive knee bend.
Source motion was also high-stepping. Correctness of hierarchy, bone lengths,
weight normalization and export round trips does not establish a good gait.

Calibrate from actual source/target segment directions and inspect the resulting
reference stance before solving contact. Do not use a foot-width constraint as
a substitute for reference-pose calibration. A diagnostic candidate recovered
the source's knee ranges with unchanged model payload, but required an 8.13 cm
global height offset; that is not a transition-safe finished repair. Review
source performance and solve support, pelvis and handoff continuity together.

CPU/null-RHI Unreal pose capture must force ALWAYS_TICK_POSE_AND_REFRESH_BONES
and disable update-rate optimizations on the owned test pawn, otherwise an
unrendered mesh may supply stale poses. This enables evaluated runtime evidence
without taking another workload's GPU; it is not rendered gameplay acceptance.
Retain broad weight-leakage screens as limited evidence, not complete rig approval.

## 2026-10-22 — Solve authored contact and final game contact separately

Character02's corrected walk needs segment-based reference alignment and a
coupled pelvis/foot solve. A globally lowered or narrowed source pose does not
repair incorrect calibration. With long strides, a small lift reduction alone
overextends the leg or adds pelvis bob; a shorter cycle at unchanged movement
speed permits a moderate 5 cm swing and 12–43 degree source knee range.

Even that clean exported walk penetrated the game's uneven tiles after the
existing Manny floor rig evaluated. Final contact must inspect the character's
actual boot skin after that rig. The new game node holds only explicit flat
support, preserves foot orientation, and solves the existing knee chain. Its
reach test must include the requested vertical correction, or it releases
reachable support prematurely. Acquiring blended support at weight 0.65, with
release below 0.5, reduced the measured start drift from 1.35 cm to 0.08 cm;
waiting for 0.9 missed part of the contact during the idle blend.
Airborne movement and action montages release
the solver; they retain their separate authored contracts and validation gates.

Terrain queries from the previous pose left a 9 mm swing-toe dip at 30 Hz.
Adding bounded predicted query positions removed that measured dip without
raising every pose by an arbitrary constant. Keep queries on the game thread
and use cached planes on animation workers. Current plus predicted centre,
extrema and lowest-skin queries cost at most 24 traces for this character;
crowd-scale performance has not been benchmarked.

Low height, low angular velocity and low vertical speed can also describe the
apex of a swing near raised terrain. Do not report its horizontal movement as
planted-foot drift. Retain the inferred windows but label which windows are
confirmed by authored support curves; report transition acquisition separately.
Fixed-step game probes must use world simulation time, not Slate callback delta.
The earlier Slate-clock capture and diagnostic instrumentation stall are retained
rejections. Neither is evidence for the delivered result. Successful final
30/60 Hz tests still leave human acceptance and cooked coverage open.

## 2026-10-22 — Restore grounding during evaluated attack blend-out

UE's `IsAnyMontagePlaying()` includes instances that are stopped but still
blending out. Using it to disable contact leaves the recovery ungrounded.
Checking active montage state during game-thread `PreUpdate` is also one
animation update too early. Prepare collision there, then use the public
thread-safe `IsSlotActive` API over current evaluation data to gate correction.
A direct proxy montage-state accessor is protected and failed compilation;
use the supported API, not access workarounds.

The existing floor Control Rig's Boolean zero-to-one switch caused a roughly
6.6 cm pelvis drop at recovery. Blend its alpha with one minus the current
montage weight after the active strike ends. `CalcSlotMontageLocalWeight`
reads the current proxy state; the ordinary getter is buffered. Checking
clearance alone would have missed the resulting body pop.

Discarding the entire horizontal foot-lock correction when its 15 cm/reach
limit is crossed causes a roughly 13.6 cm one-frame foot jump. Clamp/project
that correction into its reachable envelope and let normal support release
finish the handoff. Measure required height again at the horizontally shifted
boot position on slopes. Preserve active strike motion and compare it separately:
the recovery change matched all 669 tested active poses and pawn paths exactly.

Exercise the real movement handler when testing attack cancellation. Direct
`AddMovementInput` misses the gameplay handler's cancellation threshold and
cannot prove that handoff. Retain small residual errors honestly: this repair
still has one 0.24 mm recovery penetration sample at 60 Hz, and the expanded
panel finds separate unchanged active-combo penetration. Fixed simulation
rates, successful saves and clean scripts do not imply cooked, all-terrain,
performance or human acceptance.

## 2026-10-23 — Check floor-relative sole clearance across the footprint

The lowest vertex in world Z is not necessarily the deepest penetration into
uneven terrain. Trace at each retained sole sample for validation and report the
minimum point-to-local-floor gap. The expanded Character02 panel revealed an
existing 3.21 cm later-walk dip after Attack 02 that the older lowest-point check
missed. Preserve ray-hit coverage; a missing floor hit is not a clearance pass.

For the active combo, use a bounded upward-only knee-chain correction, preserve
foot orientation and disable horizontal support locking. Opt in the exact combo
montage, rather than changing every action's contract. Paired input runs must
compare upper-body/weapon-hand motion, pelvis, pawn path and montage timing
separately from the intentionally changed leg contact. All six attack exits were
exercised at 30/60 Hz; 856 active frames preserved those unaffected channels.

The original six terrain landmarks per foot missed a raised tile under an
interior toe vertex. Tracing all 149 runtime points and predicted positions fixed
it but increased instrumented panel time substantially. Farthest-point sampling
across each sole, capped at 16 points per foot plus predictions, retained the
six-case contact result with 64 maximum runtime traces. Keep the independent
all-vertex probe; do not reduce validation to match the cheaper solver. Panel
wall time includes Python instrumentation and is not an isolated FPS benchmark.

The expanded turn/reversal check still finds a 2.07 cm intersection. Reconstructing
the prior pose and tracing its point against the same live game floor gives
3.78 cm there. Keep this separate limitation visible; passing attack exits does
not certify all locomotion. A commandlet editor world returned no physics hit;
the retained failed diagnostic was replaced with a read-only null-RHI game-world
trace, which matched the measured current floor before comparing the older point.

## 2026-10-23 — Turning terrain coverage and correction limits need separate checks

Do not assume a smaller residual is the same original failing frame. After
adding backward predictions and a centre guard, the 60 Hz remainder occurred
at another swing frame: it required 9.31 cm correction and hit the 8 cm cap.
Raising only the locomotion cap to 10 cm fixed that frame; the exact combat
montage retained its 3 cm cap. The temporary upper-plane-neighborhood heuristic
did not solve the defect and was removed.

A passing 60 Hz candidate still had -0.580 cm penetration at 30 Hz when a turn
started. A centre-only 15 cm query guard is not a guard around the actual foot:
the toe rotated outside sampled coverage, and its nearest query was 9.62 cm
away on a lower tile. Expanding only the outer grid then lost inner samples
and introduced another -0.908 cm result. Preserve both scales. The accepted
technical candidate combines 16 distributed samples per boot, bidirectional
predictions, inner and padded-footprint grids, bounded at 192 terrain traces.
This is a correctness result at the tested location, not a crowd-performance
claim; retain the independent all-149-vertex probe and two-rate panel.

Paired comparisons must state their intended invariant. The old combat checker
permits only upward deltas from an already corrected baseline, so its strict
flag becomes false for a 0.038824 cm reduction in correction after changing
terrain queries. Keep that raw flag; separately verify positive contact and
unchanged timing, upper body, path, foot XY and orientation. Never silently
relabel an implementation-shaped comparator as artistic or physical truth.

The final commandlet audit crashed before Python in RigVM/ControlRigPhysics.
Retain its failure receipt instead of retrying the same launch. An owned normal
editor with RHI successfully ran the same read-only saved-asset checks, then
exited. Record that distinct execution route and bind its actual output; runtime
success alone does not prove saved markers or graph settings persisted.

## 2026-10-23 — Portability needs installed-package and real-character checks

A green source checkout does not prove portability. An ordinary independent clone,
fresh dependency environment and explicit external inputs exposed tests importing
the installed package before the checkout. Set pytest's `pythonpath` to `src` for
source tests, then independently test a built wheel with isolated imports outside
the checkout. Do not confuse a mathematical limb fixture with a second character.

Ennix exposed two export-validation errors hidden by Character02: q and -q encode
the same orientation, so compare normalized quaternions using the absolute dot
product and shortest angle. Neutralize animation before exporting static attached
nodes so their default transforms do not depend on the selected action frame.
Keep exact geometry/material/skin fingerprints strict; do not relax them to turn
numerical attachment drift into a pass. Both rejected attempts remain recorded.

An engine plugin is reusable only when its modules build without the originating
game and its configuration uses supplied bones, measured skin and explicit asset
paths. Independent build/install/reload checks establish that boundary. They do
not inherit the source game's runtime acceptance or prove the imported mesh free
of warnings. The contact implementation still costs up to 192 terrain traces per
character and targets human-scale bipeds; destination performance and gameplay
need their own evidence.

## 2026-10-23 — Bind frames, saved blend-space structs and stateful test isolation

Bone names and a shared Skeleton asset do not prove equivalent bind frames.
Ennix's native Blender axes and Unreal axes differ, and the Skeleton reference
pose differs from the installed SkeletalMesh pose. Read mesh-bound GetRefBonePose
using optional_skeletal_mesh, and export the installed mesh for probes. Preserve
the skin operator with animated * inverse(source_bind) * target_bind, rebuild
locals, and set the new sequence's retarget-source asset to the actual mesh.
Verify evaluated keys with retargeting enabled after a fresh-process reload.
Wrong-frame probe and import attempts remain rejected, not silently overwritten.

Python mutations to structs yielded by Unreal reflected-array iteration can fail
to persist even when save succeeds. Copy to a list, assign each changed struct
back into it, set the full property, rebuild BlendSpace triangles, save and reload.
Verify exact clip references and speed rows, then check live support curves during
walking. Ennix V2-V7 had new sequences but stale walk references; V8 corrects this.
Do not publish their after-recordings as proof of the new walk.

Independent runtime cases that teleport to spawn must replace their animation
instance, not merely reinitialize it. World-space foot locks survived the latter
and contaminated the next case. Clear/restore the class, assert object identity
changed, and record resets only between cases. Actual within-case turns remain
uninterrupted and must retain their own state. Ground trace misses are separate
coverage data; never count them as cleared contact or silently fail every panel
without distinguishing partial coverage from a wholly unobserved foot.

No-penetration is not no-sliding. Ennix's final straight support intervals lock,
but a sharp turn yields up to 10.445 cm at 30 Hz under the existing bounded contact
solver. Keep that result visible beside positive sole clearance and pending human
acceptance. Do not alter Character02's shared solver merely to improve a second
character's score; changes to turning contracts need their own scoped acceptance.


## 2026-10-23 — Plant reach is character-specific; plugin isolation must be explicit

A fixed horizontal contact limit cannot fit every gait and body. Ennix's sharp
turn exceeded the 15 cm plant envelope while its support leg approached full
extension. Enlarging the envelope alone cannot create physical reach. Use a
bounded, opt-in pelvis lowering solve for both supporting legs, keep original
segment lengths, retain ground correction and expose actual body displacement in
the receipt. Defaults remain 15 cm offset and zero pelvis compensation. Ennix's
separate profile uses 35/6 cm limits but needs only 1.937/3.031 cm pelvis lowering
in the tested 30/60 Hz paths. Compare positional slide, rotation, ground clearance,
body motion and skin clearance separately; no single score grants artistic approval.

Preserve an accepted game solver by adding a separate plugin/class and derivative
AnimBlueprint rather than overwriting its implementation. Unreal project plugins
with unspecified EnabledByDefault auto-enable: absence of a project-file edit is
not proof of opt-in behavior. Set the descriptor false and verify ordinary startup
has neither class loaded; explicitly enable only the intended review launch. The
Ennix descriptor-only rebuild retained identical runtime DLL bytes. Keep cooked
and performance acceptance separate from these fixed-rate game correctness runs.

## 2026-10-23 — Inspection speed is not the manual gameplay default

The user rejected the perceived slowness of the 105 cm/s Ennix inspection
session. Preserve normal travel at the game's 500 cm/s and make deliberate
walking selectable (Left Alt in the temporary manual review), rather than
globally capping all movement at the authored walk speed. Keep the existing
speed-driven blend graph and contact solver; this change does not certify the
unpolished jog/run clips or higher-speed contact quality.

In this UE runtime, FKey's name is not exposed as a Python property and its
constructor accepts no positional arguments. Use its native text importer and
verify the exported value, as confirmed by InputCoreTypes.cpp and
PyWrapperStruct.cpp. Retain failed launch receipts before a corrected launch.

## 2026-10-29 — Character parts, reference occlusion and native packaging

On a character built with separate wardrobe surfaces, they avoided
projected garment seams and skin contamination. Keep body-to-garment triangle
barycentrics through edge fairing so skin weights follow the same acquired
surface. Anatomical region masks are necessary: a height-only shorts cut also
selects forearms in an A-pose. Preserve the already accepted body.

A multiview facial bake can pass broad coverage checks while duplicating an
eye corner or painting loose hair onto skin. Inspect an actual close-up with
hair temporarily hidden. Front identity projection and harmonic surface fill
over hair-occluded areas removed these defects without changing geometry.
Retain both the defective render and the correction's source registration.

An acquired hair shell can define a useful envelope while remaining a poor
render surface. The existing envelope-based groom improved that character visibly,
but its swept-back ponytail still differs from the reference. Keep native
strands separate from the FBX mesh-hair fallback and state both triangle/curve
counts; neither a nicer groom nor a valid skeleton proves production readiness.

Blender image.has_data is false for some lazy-loaded textures even after a
scene has rendered. Do not use it as the sole packing predicate. Pack all
external files, reopen the saved blend, and check every file image's packed
state. Save the camera after setting the intended delivery view. These checks
catch a scene that renders correctly in-session but opens with missing maps
or a camera at the origin.

## 2026-10-29 — Read the Basis when registering a shape-key character

In one shape-key rig, the original mesh vertex array remained in acquisition
coordinates while the Basis and all expression keys had been grounded by
-9.9033 mm. A face projection that applied inverse grounding to the raw mesh
vertices doubled that correction and displaced eyes/lips. Use the Basis rest
coordinates, record the frame conversion, and inspect a close-up before accepting
material work. Preserve the failed render; do not confuse the failure with a
bad camera or attempt to compensate by moving the head.

An open-eye photograph stretches across a closing lid even when the morph itself
is valid. Review actual closed-lid renders; a driven skin blend can remove the
photographic streaks, but it does not prove likeness or expression quality.

## 2026-11-01 — Acquire heads and hands alone; weight layered characters by limb region

CH-03 Raider's whole-body acquisition gave the head and the hands too little of the generator's resolution:
lumpy hair, shallow eyes and a generic face that no MakeHuman fit, projection or paint rescued (three face
options were all rejected), and gloves fused to the fingertips. A close crop of the same reference, upscaled
4x and acquired alone, gave modeled eyelids, lips and hair, and fingers separate to the knuckles. Detail
acquisition is now part of Stage 2 for every humanoid (`WORKFLOW_PLAYBOOK.md`, `scripts/detail_crop.py`).

Rigging the assembled character exposed three faults in `derive_humanoid_landmarks.py`, now fixed: a strict
empty-centre crotch test ran down to the knees on a stray seam (now a sustained, hip-relative gap); ordering
the arm by sideways reach ended the chain at the thumb (now distance from the shoulder); one-sided gear
dragged the hip-median midline 3.7 cm (now midway between the feet). Template fingers missed modeled
fingers and a fist crumpled them; `measure_finger_landmarks.py` measures each chain from the mesh.

Blender heat weighting failed on the layered mesh, on a welded copy and on a voxel-remeshed copy, so the
rig fell back to envelope weights and the belt pouches flew with the arms. Plain nearest-bone weights fail
the same way in an A-pose (the forearms hang beside the belt), weights spread along the surface carried
shoulder weight down the long straps, and a limb radius cannot separate a baggy sleeve from the jacket side
8 cm away. `rebind_layered.py` labels arm, leg and torso regions by spreading along the welded surface from
sure seeds, lets limb bones weigh only their own region, and puts small rigid gear on one bone. Do not
retry heat on this kind of mesh or tune radii.

Mark rejected those weights too (stiff segments, hard creases, stretching). Clothing is skinned from a
properly weighted body underneath it: `skin_from_makehuman.py` poses MPFB's MakeHuman body and
`game_engine` rig onto the character's joints and copies its hand-made weights onto every garment vertex
from the body surface below. Pose only the limbs, fingers and head onto the target; turning MakeHuman's trunk
bones to match Manny's swings the hips and shoulders. Keep the hand weights on the measured fingers. The face
rig is still open.

## 2026-11-03 — Layered characters: cut parts smooth, reduce once, make armour solid, cut UVs like a pattern

Mark found CH-03 Raider "uggo" up close in Framewright: saw-toothed straps and plate edges, spikes, seams across
the plates, and holes in the back. A clay render showed most of it was in the geometry, not the paint; the dense
acquisition itself is smooth. `build_parts.py` cut each part along the dense mesh's triangle edges (per-face
labels), thickened the overlays partly inward, and `prep_production.py` then collapsed the joined closed shells a
second time, spiking their rims. `recut_labels.py` now diffuses each part's share over the surface and splits
triangles where the leading shares are equal, so outlines cross triangles and neighbours share one cut; hair and
beard pieces cut off from the head and islands under 1 cm^2 take the label around them (a 478-triangle hair patch
on the jacket's back became a hole once the head was swapped in). `build_parts.py --clean-edges` grows shells
outward only and without even thickness (it divides by the fold angle and threw vertices metres away), dissolves
slivers, splits bow-tie vertices, pulls each overlay's outline in 0.5 mm, sinks the cloth under each shell 3 mm, and
reports each shell's furthest vertex and collapsed faces. `--budget-scale` with `prep_production.py
--body-budget` reduces once, straight to the production density. Rejected and retained: protecting the open edge
in the collapse (interiors became fans; a pouch tore open) and relaxing the reduced outline (it folded a triangle at
a tooth and the shell flung that vertex away).

Holes in closed shells came from three places, each found by checking the shells after every stage, not by
looking from outside: zero-area triangles dropped on export after the second collapse; `prep_production.py`'s weld,
which fused neighbouring shells along a shared re-cut outline into one piece (fixed by the outline pull-in);
and `attach_face.py`'s neck clean-up, whose "bright warm paint near the neck is skin" rule cut copper highlights out
of the chest plate. That clean-up now never deletes from a closed shell. Viewers like Framewright cull back faces,
so review with culling on and check shells closed (`plate_check.py` counts each shell's open edges).

The armour overlays are closed shells, but their weights came from the cloth below vertex by vertex, so in Manny's
frames the shoulder plate bent 96 mm and the belt 85 mm. `rigid_parts.py` gives each shell one weight set (the
area-weighted mean, twist bones folded into their limb; a shell over a ball joint rides the limb by at least 0.7;
one straddling a hinge is left alone) and locks the surface under it. Three lock rules failed first: the nearest
piece wins (a strap 5 mm between the chest plate and a belt pouch tore 24-fold), a weight-overlap gate (the cloth
under the shoulder plate's inner edge went free), an even blend where pieces meet (cloth lagged under a pouch).
The kept rule gates by body region, blends by pull and lets the covering piece count ten times. Measure poke with a
ray along the bind normal turned with the piece: the posed vertex normal tilts with the cloth around it and finds
the piece's far side. On v7 every shell is closed, torso pieces bend under 3 mm, the shoulder plate squashes evenly
by up to 19 mm instead of folding, and the thigh pouch's poke fell from 34 mm to 1.5 mm.

The body atlas from one Smart UV Project had about 10,000 saw-edged islands, and the painter's views disagree at
every island edge. `body_paint_prep.py --part-uv` (`part_uv.py`) cuts each part like a pattern: at folds over 75°
on shells and only at fold-backs (130°) on cloth, since at 75° the jacket's wrinkles cut it to patches, plus the
cheapest paths joining a tube's open loops, weighted to run down the back and the undersides. About 3,000
islands remain, most of them hidden rims and skirts. Re-baking old paint into a new layout carries its smears
across, so the body was repainted. A paint run was refused before inference when 98 triangles of the acquired face
had two corners at one point (the painter's exact-position normal proxy rejects the mesh); `--clean-edges` now
dissolves those. The painter's smears on surfaces the reference does not show (the shoulder plate's outer face)
remain; better UVs do not fix them.

`build_raider.ps1 -From parts` now runs all of this inside the run folder, then `manny` (Manny axes with the torso on
Manny's exact frames, shoulder re-split, solid armour). The rig gate counts the stand-in acquired head in the
intermediate mesh and the speaking face, eyes and teeth in the final one against the 80k hero ceiling: v7 used
`-BodyBudget 60000 -HeadBudget 17000 -HandBudget 5700` (79,602 triangles).

## 2026-11-03 — Every character gets a material pass after the paint

Mark judged the repainted Raider "A quality, not AAA": metal, leather and cloth all read as the same paint. Better
UVs and a cleaner mesh do not change that; the painter has no notion of a material. `finish_materials.py` bakes one
from a per-face part map and `profiles/materials/character-finish.json`, using procedural patterns in object
space (no UV seams) and Cycles' occlusion and pointiness for grime and worn edges, into a new base colour,
occlusion/roughness/metal map and normal map. Tuned on the Raider: scratches in one direction read as brushing
(they now cross and are sparse); on grey-painted straps, fine leather grain with deep creases read as fur (calmer
grain and creases); a 64-sample bake looked the same as 16, so the fur was the pattern, not noise. On the GPU the
whole pass takes under a minute after Cycles' first kernel compile. In the Unreal import a normal map must get its
own texture asset; sharing the `_MR` name replaced the roughness/metal map and made the body fully metallic.
`build_raider.ps1` runs it as the `finish` stage.

## 2026-11-03 — The part map comes from grounded detection, not clicks

The Raider's 2D part map was clicked by hand on SAM's automatic masks, so the next character could not reuse it.
`scripts/auto_part_map.py` finds the parts of `profiles/segmentation/humanoid-gear.json` with Grounding DINO
(boxes from text) and Segment Anything (a mask per box). Every rule below was measured against the hand map's pixel
agreement and then checked by eye on the CH-03 Guard, Scout and Bulwark looks, which were never used for tuning.

- One query per part: 0.548. "Holster" took the knee pads, "shirt" the whole torso, and a box round the whole
  figure passed every size limit. Comparing box size with the whole picture let the jacket through or killed it;
  each part's `max_box` is now a share of the figure's own bounding box.
- One joint query with every phrase (parts compete for each box): 0.782. It never named the chest plate. Adding
  each part's own prompts gets it, and "a shoulder pad" finds shoulder plates; "a bare forearm" finds the bare skin
  between glove and sleeve, where the joint "forearm" drew round the whole arm.
- SAM spills past a small box into its neighbours: masks are clipped to their box.
- A harness box's mask is the whole chest with the plate in it, and straps outrank plates. Two fixes: a smaller
  part nested in a bigger mask at most one layer above it wins inside it (the Raider's plate, 0 to 0.41), and a
  thin part keeps only the parts of its mask no wider than `max_width` (on the Guard and Bulwark the plate's mask
  was within 17% of the harness mask's size, so nesting alone could not tell them apart).
- Dropping boxes under 0.6 of the part's best score removed junk belts and jackets but also every shoulder
  plate when the chest plate scored high. Now a box is compared only with overlapping boxes of its part, and parts
  a character has one of (belt, face, hair, beard, jacket, trousers) keep their best box.
- Height zones (0 at the crown, 1 at the soles) keep belt pouches out of "thigh holster": pouch IoU 0.47 to 0.97.
- Bare skin by colour: the neck and forearms came out as jacket. Cloth pixels within ΔE 18 of the face's colour
  that touch the face or a skin detection become face or skin (face 0.70 to 0.94, skin 0.21 to 0.89). Taking the
  colour from a detected "forearm" as well turned the Guard's grey sleeves to skin: that box was a cloth wrap.
- The Bulwark's second pauldron was never detected. A paired part found on one side is looked for in its mirrored
  box and kept when the mask there matches in size (0.5 to 2 times) and colour (ΔE 12). The Raider's single
  shoulder plate has teal cloth opposite, so it gets no twin.
- Rejected: labelling SAM's automatic segments with CLIP (0.79 at best, and the beard and face fell to 0.14 and 0);
  CLIP on whole masks calls most large regions "belt". A colour clean-up that hands overlay pixels resembling the
  cloth around them back to the cloth lowered agreement (0.89 to 0.79-0.84): leather, boots and cloth are too close.

Result: 0.889 pixel agreement. Straps (0.34) and plates (0.60) remain the weak parts. The map is a gate; the
`labels` stage of `build_raider.ps1` writes `review.jpg` and project_parts.py's four-view part renders for it.

## 2026-11-03 — A segmentation boundary is not necessarily a part boundary

On the Raider, a SAM mask ended halfway across a single armoured plate and
the middle of one leather pouch. Thickening these masks put real rim faces
there. Pattern UVs and a new material finish left the tear visible in clay.
Compare identical close-ups in clay, unlit albedo and component IDs before
repainting. Restore continuous acquired geometry across an invented cut;
keep an independent shell where the article really separates or where the
backing is absent. Inspect the reverse angle before removing that shell:
the first whole-piece trial uncovered an actual hole in a front pouch.
`scripts/blender/compare_surface_crops.py` detects the resulting loss in
depth even when both foreground silhouettes remain occupied. A grazing rim
can legitimately move after removing a thick overlay; check it against the
original acquisition instead of changing the alarm threshold.

### 2026-11-03 — after paint, assign surfaces inside the atlas

On the Raider, one named face slot also contains painted hair, beard and a
collar; one hand slot contains bare forearm and a leather gauntlet. One
roughness or specular factor per slot cannot represent these boundaries.
Project existing part labels onto the accepted UVs, review those masks on
the model, then bake the independent surface controls. Use the same painted
geometry, camera and exposure for both images and move a studio light: the
steel highlight should stop at a leather rim. A flat-colour check establishes
paint preservation, not this distinction. See [material sweep](MATERIAL_SWEEP.md).

### 2026-11-03 — evaluate worn steel in Framewright Scene as well as Assets

The live asset inspector supplied room reflections. The Scene viewport used
an ambient light and one directional key. In Scene, the original 0.94
metalness shoulder produced a bright glint surrounded by near-black steel.
On this painted, weathered plate the `framewright-scene` target uses 0.67
effective metal coverage and a broader roughness range. The shaded plate
became readable while the highlight still stopped at the leather rim. Check
the actual scene and asset inspector before selecting this finish for another
asset. [Matched measurements and settings](evidence/raider-framewright-20261103.json).

### 2026-11-03 — distinguish a projected material line from an equipment edge

A SAM-derived face label can split a single buckle halfway across its face.
Insetting its backing and extruding the cut creates a real, jagged wall;
roughness, padding and UV painting cannot remove it. On the Raider the original
acquisition already had enough relief. Preserve the shared face indices across
fitted regions, and keep the IDs for paint and material response. The first
continuous bake still showed a false edge when part of a metal frame was
labelled cloth. Check the material IDs against the actual painted trim. For
an independently removable item, reconstruct and inspect its hidden side and
backing separately. [Matched Framewright result](evidence/raider-continuous-20261103.json).

### 2026-11-03 — give the narrow gusset its own reference

Projecting a sharp pouch face across its thin end merely turned blur into
streaks. An edge-on reference aligned to the actual gusset supplied a coherent
fold. Both donor views showed part of the same flange: using both gave a
double sewn edge under a grazing light. Assign the flange to one donor and
use the other for the return. Likewise remove a donor's dark silhouette
shadow before painting the real bottom turn. [Raider pouch comparison](evidence/raider-pouch-20261103.json).

### 2026-11-06 — diagnose the seam in separate surface and geometry views

The Raider's dark knee bands were incorrect metalness on brown fabric, not dark
base color. The last horizontal neckline band was a reference crop boundary;
clamping its last pixel row removed the band but stretched skin grain into
vertical streaks, so that candidate was rejected. Continue registered coverage
beyond the visible garment opening and inspect the resulting normal and response
maps as well as color. The isolated cuffs needed both four-sided coverage and a
larger useful UV footprint; an atlas's nominal dimensions are not texel density.

An intact-looking still also hid inherited face/torso weights: the lower face
followed the neck, and chest straps followed the arms. Static head turns and arm
raises exposed both. A glTF importer's display-bone tail is not a reliable
anatomical aim axis; use actual shoulder/elbow/wrist joint positions. A passed
held-pose or rig check does not establish natural motion quality.

### 2026-11-06 — a closed patch can still be a poor repair

Local smoothing of a folded acquired ear left pinches or damaged its frontal
outline. Copying the intact opposite ear improved the shape, but the first root
bridge overlapped the head despite adding no open mesh border. A subsequent
direct weld had two four-incidence edges and was rejected before writing a GLB.
Fit the root with a manifold boundary correspondence, then inspect front, side,
clay and albedo. Boundary edge counts alone cannot establish visual continuity.

The replacement needed independent UVs: reusing the donor's pixels would couple
future edits to the intact ear. Its old paint still depicted a larger ear behind
the new one. A registered color-plus-clay AI edit removed that false outline.
Repainted hair then inherited skin roughness/specular and appeared as a gray
patch; semantic response classification had to follow the changed paint.

For native delivery, retain the original rig's rest frames and explicitly compare
posed vertex positions to the transport. Filter imported character meshes by
their armature modifier: the glTF importer's helper Icosphere is not a character
part and fails the skin gate if accidentally retained. Pack, save and reopen all
file images. These checks do not replace Framewright or cooked runtime review.


### 2026-11-06 - Validate repaired GLB bounds before consumer import

Blender rendering and rig gates did not detect missing min/max metadata on the
new POSITION accessor 277 in candidate04. Framewright correctly refused import.
The bounds-only derivative computes real extrema without changing binary data;
retain its rejected source and before/after hashes. Add POSITION-bound checks to
the shared export path before claiming repeatable browser delivery. Temporary
app folders also lose static web files: verify index.html and dependency files,
not just the executable or API. Sandbox process inventory is not host inventory.


### 2026-11-06 - Skin-coloured paint is not sufficient evidence to remove a face

Raider neck cleanup classified a garment region as skin and removed 12 acquired
triangles, leaving a ten-edge hole below the intended neckline. Layer raycasts
confirmed missing cloth, not penetration through an intact shirt. Restore the
exact upstream faces with current normals and weights, then repaint isolated UVs
from the registered reference. Do not inflate the whole garment or shrink the
body. Future semantic face removal needs boundary-component review: new closed
loops below the intended opening are defects to inspect, not automatic acceptance.


### 2026-11-06 - Preserve tiny acquired faces when UV packing collapses them

The generic xatlas 0.0.9 cuff replay collapsed thirteen positive-area triangles
to zero-area UVs, although their total surface area was only about 0.001255%.
The first run was retained as a failure. Do not delete faces or keep undefined
tangent frames to force a pass. Repack now isolates at most 128 such faces, totaling
at most 0.01% of surface area, into a reserved narrow atlas strip with exact source
corners. Significant collapse and zero-area geometry still stop for inspection.
Normal maps are transported between old/new frames; weights and morphs are checked
per triangle. Tangent morphs are refused until their deformation-aware transport
exists. Real evidence: rac-cuff-replay03 and the paired cuff front/back renders.

### 2026-11-06 - Review framing must exclude imported bone display meshes

Blender's GLB importer added a hidden Icosphere used as a bone custom shape. Its
hide_render flag alone did not identify it, and including its bounds made the
first automated full-body image too small/off-center. Frame from visible model
meshes, explicitly excluding rig custom shapes. Keep closeup cameras explicit.
The first model output remained byte-correct; the presentation was rejected and
the later fixed reviews retained. A packed GLB-import review copy also does not
replace the authored native skeleton/rest-frame authority.


## 2026-11-06 - An intact-looking donor ear can still carry a displaced painted outline

Compare color, clay and lit closeups before repairing the atlas. The initial
ear reference looked plausible flat but projected hair onto the physical rim.
Using current clay as the primary immutable contour, with color only as a
palette, removed the doubled outline. A separate upper-fold inversion required
a tightly located geometry pass; broad upper-rim smoothing distorted the helix
and was rejected. Both sides and oblique views must survive the mapping review.
For mixed transparent/opaque face meshes, capture an explicit material subset
and retain omitted-material names. Omitted surfaces do not occlude guides.
Do not call an ear donor clean merely because it looks better than its partner.
See `evidence/raider-ear-alignment-20261106.json` and the retained rejected runs.


## 2026-11-06 - Remora: diagnose UV occupancy before repainting

The same skin-on-shirt patches survived replacing the projection with a raw
native-paint rebake. At 2048 sampling, the Smart Project atlas occupied 388,875
texels and 2,273 were multiply covered. A fresh xatlas layout preserved exact
triangle correspondence and occupied 1,643,715 texels with 93 multiply covered
samples; those tiny residuals still require inspection. Rebinding the raw
acquisition paint to that layout removed the large visible bleed. Do not keep
repainting onto an atlas whose islands share pixels. Receipts: Remora body/
unique13 and native13. Earlier attempts remain retained.

The extended template neck had collapsed inherited UVs. Remapping its rim to
nearby old UVs still produced a pale border; separate UV coverage is needed
before independent painting. Portrait assembly reviews also need max(width,
height)/pixels_per_m for Blender AUTO orthographic sensor fit. Finally, a
Blender Multiply tint node did not survive GLB export: the hair image was byte
equivalent and no baseColorFactor appeared. Encode the intended scalar in glTF
and inspect that exported result, not just the native shader graph.


## 2026-11-06 - Dark texels do not identify acquired hair safely

Remora detail21 used dark texels plus a front/height ROI to classify leftover
hair. It also selected collar shadows and made conspicuous black triangles,
while leaving the white strand artifact. Retain and reject this attempt;
isolate geometry/connectivity and inspect the selection before assigning its
material. A bounded nose projection also shifted nostril shading, so narrow
bounds alone do not prove facial registration. The selected predecessor is
review20, with these defects still recorded as unresolved.


### 2026-11-06 - Hair silhouette and eye helpers need separate conditioning

Remora's inflated braid lobes are visible in the original Pixal04 acquisition,
before SDF cleanup. Repeated smoothing cannot recover the approved smaller
braided knot. User approved redesign B; acquire hair separately with consistent
views, preserve the liked body, and review actual silhouette before texturing.
The generic strand groom previously read as fur and is not a braid solver.
Remora's original helper eyes use the whole portrait as planar base colour and
only 144 vertices: painted eyelids/catchlights plus live glare make them read as
stamped facets. Dedicated diffuse irises and smooth helper geometry remove that
confound, but are insufficient for acceptance: align centres to actual bound
eyelid corners and review eyelid paint/exposure separately. Do not label an eye
repair accepted merely because preservation assertions and exports pass.


### 2026-11-06 - Isolated hair extraction and eyelid patch scope

A conform-based scalp mask can reject the real donor crown if the fitted skull
crosses it, while retaining black eyebrows. On Remora's isolated black-hair
head donor, largest connected neutral-colored component removes disconnected
facial marks and preserves the crown. Connectivity is required; color alone
is not semantic segmentation. Thin acquired surfaces still collapse badly
under reduction; UV preservation alone does not repair geometry.
Removing painted sclera exposes a second problem: subdivided helper globes
can protrude through lids. Check actual recessed geometry before adjusting
iris size. Full rectangular skin patches can remove valid lashes and create
color edges; preserve existing facial paint where replacement is unnecessary.


### 2026-11-06 - Diagnose visible fragments and hidden expression state separately

Remora's floating white ribbons were detached remnants in the old body mesh,
not the new hair. Object colors plus component colors prove exact selection;
do not repeat the failed dark-texel classifier. All retained body triangles
and attributes can be checked exactly after selected face removal.
The chin slit was internal teeth exposed by all 34 expression weights being
simultaneously 1. An object-ID pass found the cause without patching a false
skin hole. Reset only the explicitly intended neutral helpers; keep morph
targets and do not zero a deliberately posed character indiscriminately.

### 2026-11-06 - Registered paint still needs strict foreground and view scope

Skin63 demonstrates that mildly warm AI background fringe can pass a chroma24
test and create pale UV-edge streaks. Chroma80, narrower cheek bounds and
leaving the jaw outside the patch remove that regression in skin64. Front and
below-nose references disagree slightly at nostrils, so separate underside
and bridge scopes. An unchanged silhouette or successful projection receipt
does not establish visual success. Keep rejected maps and inspect the actual
consumer. Frozen mapping/material inputs replay exactly; artistic mask choice
and AI reference authoring remain explicit review work.

### 2026-11-06 - Geometry removal must be followed by an exposed-paint check

Removing Remora's old hair remnants left two pale S shapes and a dark dab in the
body atlas. Clay was continuous; remeshing would damage sound cloth. A registered
concept-conditioned AI cloth patch removes the paint and obsolete normal relief.
This inspection is now mandatory in CHARACTER_SURFACE_WORKFLOW after component
removal/replacement. Retain the original and check the consumer, not only the
edited guide. Do not apply a warm-skin chroma filter to ivory cloth.

The first bounded projection69 missed the upper ghost because the shoulder slopes
behind z=.055. Guide depths measured z=.006-.05 there. Correcting only the z bound
to -.04 in70 removes the complete mark; fixed/angled consumer views and exact
replay71 verify the result. Derive bounds from the registered surface depths;
an adequate 2D rectangle does not prove the 3D volume covers that surface.

## 2026-11-06 - Eye detail: root lashes on the forward-facing lid margin

Remora's acquired lids are ~4 mm-deep tubes. Lashes rooted on the aperture edge
were hidden; the most-forward vertex in a radial band was the lid crease. Root on
the nearest vertex beyond the aperture whose normal faces forward. Detect eyelid
holes before welding: a coincident duplicate lid layer closes them otherwise.
Strand widths must survive viewing distance; real-width strands vanished. Lashes
are a per-character taste call: keep `subtle` and `none` presets, never force
`pronounced`. Python stage scripts must strip the runner's leading `--`.

## 2026-11-06 - Remora skin: hard response zones show in Framewright

A hard skin_tzone mask edge with a different specular/roughness range read as a
bright stripe down the nose bridge under Framewright's environment light, though
invisible in Blender studio renders. Keep facial response in one class with its
own spatial variation unless the zone edge falls on a real feature boundary; check
the consumer. Default lips class read wet there. An emissiveTexture without an
emissiveFactor contributes nothing; it is not a glow.

## 2026-11-06 - Pixal3D heads are thin double shells; hair over the jaw keeps the template's face

Pixal3D GLBs are unwelded closed thin shells: about half the face triangles face
inward. The template conform then matches few points (conform04, conform05 failed
at 4.5 mm median). Weld, recalculate outside and strip the inner skin with an
interior ray test (face78/orient_acquisition.py) and the fit converges (0.88 mm).
A converged fit still reads generic when hair locks cover the cheeks and jaw or the
lids are fused: those regions keep the template's shape. Acquire the face shape
from a reference with the hair pulled back before conforming; do not sculpt it.

## 2026-11-06 - Remora face width: hold the picture's jaw harder, not a new scan

Measured on identical clay fronts, the delivered head is ~7% wider than head-front04
(jaw/cheek per face height); its jaw points stayed 2-7 mm outside the picture at the
default jaw weight 1.5. A hair-masked Pixal scan made the face wider, not narrower.
`--jaw-weight 6` on the existing scan03 holds the jaw within 0.4 mm and cuts the
proportion error to 4.5%; weight 3 is in between; adding cheekbone points 1/15
dents the temples. Pulling the jaw creases it; use the bounded underjaw relaxation.

## 2026-11-07 - Game review: heat weights need a clean outer stand-in

The landmark rig's heat bind failed on Remora (hair shell, eyes and mouth inside the head, outfit over body) and on
its welded copy, and silently fell back to envelope capsules; every clip folded the arms and flung the trousers and
tunic. Heat on a voxel-remeshed stand-in still found no solution (0% coverage) until the stand-in was reduced to its
largest connected surface: the remesh also seals pockets between outfit and body whose walls see no bone. Decimating
the stand-in, or scaling it 10x, did not help. Check `bind.method` in a rig receipt before judging animation.

## 2026-11-07 - Hair that reads plastic is a shading model, not a roughness value

Remora's hair is a shell with a flat normal map and one roughness value. Raising roughness and lowering specular only
traded the broad plastic sheen for a dull mass; scaling specular by base brightness made wet patches. Unreal's hair
shading along a flow map (worked out on the mesh, since the UV atlas is hundreds of small charts) is what changed it.
A cloth (fuzz) look cannot be built from Unreal Python: its Cloth amount input (CustomData0) is not exposed.

## 2026-11-07 - Animations with no Manny source: retarget from their owner, then repair the montages

The Aether Wars' player uses three Character02-only montages (push, left push, recall); the Manny route lists them as
cut and those powers played nothing on Remora. Character02's skeleton follows Manny's layout, so a second
retargeter built exactly as the installer builds Manny's (auto chains, one-to-one, IK bones pinned, target pose
offset to the source's reference rotations) carries them over. The batch still empties copied montage segments; the
installer's `repair_montages` must run after it, and the motion pass flags any empty segment that slips through.

## 2026-11-07 - Faces in game: check every morph name, and judge the blink

The game's face component drives morphs by name and skips any the mesh lacks, so a misspelt name fails silently:
Remora's and Character02's lip-sync gains scale `mouth-parting`, but MakeHuman's unit is `mouth-parling`, and the
"less parting" those gains were tuned for never happened. The road's face pass reports every name the component or
the recipe uses that the mesh does not carry.

A face painted from reference views can look right open and smear when it blinks. Remora's dark lid paint (the
reference's lashes and liner) lay on lid skin folded away while the eye is open; the closure morphs unfold it. Lash
cards and the occlusion shell were ruled out by rendering the shut eye with each layer removed: the smear stayed with
skin and eyeballs alone. The repaint (`clear_closed_lids.py`) picks the skin from the mesh (area growth or facing
gained on closing), not from a hand mask. Two dead ends: a lid margin taken from the skin boundary (the skin runs on
into the socket; there is none) and the eye-occlusion shell (it does not touch the skin). Lash-card roots locate the
margin; the area and facing tests then keep everything visible open, so the open eye barely changes.

Teeth and tongue: brightening the teeth (the game's own 1.6x) was not the mouth's problem. With them white, the open
shapes still showed only a lower row, a dark gap and a jagged pink shape; hiding layers one at a time showed the pink
was the tongue, left up by every morph, and the upper teeth were hidden 4.5 mm above the lip line. The fit is measured
from the jaw morph (which teeth move, where the lips split), not set by hand per face. Its first visibility check
counted teeth "in front of" the nearest skin and flagged 971 vertices before any change: inner lip skin faces the
teeth. Rays from the camera positions past the lips are the right test.

## 2026-11-09 - An exact Manny copy is not a calibrated retarget

The game's Manny-first installer verifies its retarget by bone rotation error against Manny (< 0.01 degrees) and
calls that correct. It is exact, and that is the flaw: bodies built differently need their own rest where Manny's
angles misplace them. Character02's collarbones rode about 10 degrees above his modelled rest (a shrug); Remora's
torso leaned 10 degrees in the idle against Manny's 5, with her head jutting. Calibrate the retargeter per character
(`unreal.retarget_pose`: collarbones at their own rest with the arms re-aimed, spine/neck pitch) and judge the result
in fixed views against Manny's own proportions (shoulder height below neck_01 as a share of height; torso lean), not
by rotation error. Do not chase feminine motion by borrowing another character's polished set: copying Character02's
library clips onto Remora (Character02 -> Remora, two hops) produced a 36-degree hunch and flung arms. Style her own
first-generation clips instead (`unreal.gait_style`), subtly; strong hip sway reads as parody in third person.

## 2026-11-10 - A joint in the wrong place looks like a weight problem

Remora's "stringy" arms (V13) were patched with `bind.shoulder_release`, which moved collarbone weight onto the top
of the upper arm. The cause was upstream: the template shoulder joint sat 2 cm low and 2-5 cm too far out, so the top
of the arm really was above the joint and heat gave it to the collarbone. The patch hid part of it, and the shoulder
still "bent wrong" (Mark, V24). Before reshaping weights around a joint, draw the joint on the mesh and measure where
it sits (how far under the surface on each side, how the bone lengths compare with each other); a bone that points
away from the limb it drives, or an upper arm shorter than the forearm, is a placement fault. Fix placement first
(`arm_joints`), then weights.

A fused mesh needs to be told whose surface is whose. Smooth weights cannot keep a sleeveless outfit's armhole on the
torso while the bare arm beside it moves, and geometry cannot tell them apart (the rim sits on the skin). Colour
can: `bind.armhole_hold`. A hard boundary tears; so does a soft one measured along the surface when a groove lies at
the boundary. Soften through space, on the skin side.
## 2026-11-12 - Judge tiny prop reductions at their actual screen size

Clanker bolt macro matcaps exposed real valley facets, but native1280x720 renders
at12cm and4.5m/1.5m showed their practical impact. The earlier v0016120tri pair was
not reliably distinguishable at those distances. The v0021800tri reduction had
scattered close-distance highlights but preserved its small gameplay-pickup role.
Retain macro findings; do not convert them into an unrequested hero-close-up gate.
Use the same physical scale, camera, material and lighting for dense/reduced
comparisons, then inspect the actual production FBX with its real maps. These CPU
checks do not substitute for the actual engine view. All rejected candidates and
failed painter executions remain retained, even when later evidence qualifies a
prior review criterion.


## 2026-11-13 - Clanker retopology: absolute tolerances and rigid part regions

At one-metre scale, QuadriFlow rejected otherwise closed surfaces for edges <=1e-4. Read the strict audit: reversible 1000x solver scaling preserved the dense source without voxel smoothing. AutoRemesher edge_scaling is clamped to [1,4]; requested 0.45 was actually 1.0. retopo_bake.try_remesh can report success after CANCELLED when its input is already quads; verify the operator result and actual counts. Whole-body reduction softened narrow details; user authorized separate regions. Paired caps assigned to the same mitten region must be removed before welding. Reopen the final mesh: bounded projection produced one zero-area head face, caught and removed at 1e-7 tolerance. Native quads and GLB triangles remain separate evidence. No human gate is implied by these technical checks.


## 2026-11-13 - Clanker texture checks and lifetime wear

A pixel-only UV overlap repair exposed new subpixel folds after repacking; exact triangle intersections resolved them without geometry edits. Shared 2K density was 170 texels/cm2; separate head/body 2K atlases reached 378/248 with a fresh dense normal bake. Hunyuan studio runner rejected the wrapper diagnostics flag before inference; the next attempt produced validated outputs then crashed at shutdown. Retain failed execution and independently verified artifacts separately. Warm shadow hue alone misclassified ivory edges as brass; require original metallic-map evidence. Remove fixed paint chips and their tiny residual borders before authoring seeded wear. Keep clean enamel and eligibility separate; choose wear once per body, never each frame. Optical gate rectangle sampling crossed adjacent colours; unchanged thresholds passed with semantic-interior rectangles, with initial diagnostics retained.


## 2026-11-13 - Robot materials need geometry-aware surface response

Flattening AI paint into constant colours and scattering round brown marks made the knight read as a figurine. Keep material identity but remove painted construction lines and fake hardware dots; put brass grain in normals/roughness and chip depth in normals with matching exposed-metal channels. Edge-only wear selection can hide most chips under the jaw or near the crest: constrain representative front visor/toe/cuff regions while varying each part. Regular high-amplitude grain looks ribbed; retain subtle broadband response. Filling a removed black border entirely with ivory makes a new pale border; use nearest surface material across the fitting boundary. GL/DX neutral green 0.5 quantizes to 128 in both, so complementary 8-bit checks need one-code tolerance rather than demanding an impossible exact neutral complement. A finer rasterizer covered samples left as semantic ID zero in earlier masks; these made dark UV-edge lines. Require a nonzero material ID at every occupied texel and inspect the back view. Tiny optical albedo variation can correlate strongly with normals despite little amplitude; optical pigment is now constant and highlights are fully live. Distinct wear bitmap hashes did not guarantee visibly different placement: A/D clustered similarly. Replaced D with seed 314159 and checked pairwise physical-mask overlap before delivery. Framewright software rendering permits actual-consumer review without borrowing the GPU.


## 2026-11-13 - Explicit rigid part rigs need a separate binding contract

Do not join an approved multi-part production payload merely to satisfy the landmark runner, and do not heat-bind rigid armour. The opt-in hash-bound rigid_part_binding profile accepts exact existing part names and deform owners, preserving all geometry/UVs and assigning one weight each. Native use_deform flags do not reliably survive FBX; verify forbidden bones have no weights and retain the native rig/landmarks. Whole shin-and-foot boot shells follow calf, not foot, unless separately approved ankle splitting occurs. Numerical rigidity does not prevent visible gaps at butt joints; require stress-pose close-ups. Blender Save As remaps relative image paths against the previous file unless relative_remap=False; validate reloaded pixels and package paths, not just an FBX write.


## 2026-11-13 - Sentry rigid parts

Surface caps plus Boolean sockets failed; source-derived volume CSG plus Blender collapse preserved closed surfaces. Fast simplification introduced duplicate/nonmanifold faces. A global antenna-height label incorrectly assigned carapace crown geometry to Helm: constrain by depth/width and inspect side/back. Static geometry checks do not imply motion or human visual approval. User promoted this important character to elite tier; regular-tier receipts retained. Status contains pre-existing mixed encoding; byte insertion preserves unrelated content.


<!-- frastown-west-berth-b01-20261123 -->
## 2026-11-23 · Modular FBX needs a consumer-space scale and pivot check

The West Berth control rail imported as 2 cm from a metre-coordinate FBX although its source length was 2 m. Write actual centimetres to both evaluated render vertices and named collision meshes, using unit transforms, then import at 1.0. This follows the existing character exporter’s centimetre bake. Compare signed bounds against the local pivot after the axis conversion and read back native snap locations. Keep connection span and elevation as separate fields. The grating shadow render and per-revision material notes are part of the review evidence. See [the measured record](evidence/frastown-west-berth-b01-20261123.json).


<!-- frastown-close-range-dry-20261123 -->
## 2026-11-23 · Frastown dry close-range first articles

The first batch used a custom atlas. The subsequent RAC paint acquisitions passed the mesh and UV gate but copied fixed orange/blue lighting into both looks. Reject the raw paint if a light or rain highlight persists in isolated base color. The deck then measured about 7 mm/texel from automatic projection. The close-range candidates use dedicated contact-surface UVs, dry authored surface color and relief, and the RAC material-response sweep. Review matched 32–46 cm views for millimetre wear and soft transitions at contact zones. Scene rain stays independent. Both Framewright revisions are Pending. See [the dry close-range evidence](evidence/frastown-close-range-dry-20261123.json).


<!-- frastown-surface-pass-b02-20261123 -->
## 2026-11-23 · A kit built by script is not an acquisition

Frastown West Berth batch 01 was built entirely by Blender scripts from the scene's metre coordinates: boxes, tubes and prisms, no image generation and no image-conditioned geometry. The owner reviewed the resurfaced kit and said the normal pipeline had been skipped. The rule at the top of this file applies to environment kits as it does to characters. Surface pass B02 improved what the kit looks like; it did not change where its geometry came from. Treat the kit as a blockout that proves dimensions, snapping and surfacing, and acquire the pieces a viewer stands next to through the image route before calling them final.

## 2026-11-23 · UVs for a hard-surface kit: metres, and nothing shared between neighbours

Batch 01 scaled every face to fill one atlas tile whatever its shape. A 2 m × 5 cm flange and a 3 mm rivet each got 1024 px, so most of the surface was stretched and read as streaks. Lay each face or tube out in metres at one scale and pack per part.

Sharing one island between identical members to save texture space fails the same review from the other side: both ladder stringers and every third rung carried the same rust in the same places, and the owner saw it at once. Share texture space only between fasteners, in several scattered variants. Give buried faces almost nothing and cut long members into several islands instead.

## 2026-11-23 · Procedural wear: band-limit the noise, give rust height, keep marks short

Three things made generated wear read as generated. Noise finer than a texel aliases into grain on any face painted at low density; sample a coarser copy there. Rust painted as colour alone is a stain; it needs height, in scabs no smaller than three texels, so the normal map can carry it. Scratches and polish drawn along a member's whole length are uniform; a real mark is a few centimetres long, lies at its own angle and gathers where the part gets knocked. Also: review JPEG with subsampled chroma turns rust on dark iron into visible squares, so keep full chroma.


<!-- frastown-west-berth-production-review-20261123 -->
## Keep proxy geometry out of production review

A Framewright model card and a large paint atlas do not establish production admission. Inspect resolved GLB image channels and their UV bindings. Archive layout meshes and superseded exports. Create revisions for an established asset. Check physical proportions and all model faces before paint. The archive and map audit is retained in [the Frastown evidence](evidence/frastown-west-berth-production-review-20261123.json).


<!-- frastown-ct03-metric-and-material-review-20261123 -->
## Check acquired building apertures and rear faces before paint

A square-on source may show an open door or window while the reconstructed candidate fills both with solid faces. Probe the intended clear volume after reduction and metric fitting. Test the actual exported file at human eye height and inspect its rear faces. A closed-manifold check can pass on solid infill and fused door hardware. Verify that normal strength changes lighting response before assessing a painted asset. See [CT-03 measured evidence](evidence/frastown-ct03-metric-and-material-review-20261123.json).


<!-- frastown-production-direction-20261123 -->
## 2026-11-23 · An agent started outside the repository loads none of its rules

The Frastown thread began in an empty workspace folder. The rulebook here is read only by an agent that starts in this checkout, so nothing told it that Blender begins after acquisition. It built by script. When corrected, it built a private image and geometry route beside the real one. Put the operating instructions in the folder the agent starts in, and have them point here. Do not rely on a correction typed into a long thread: this one was compacted twice in a day.

## 2026-11-23 · A gate the owner cannot see is a stall

Meshes held at `modeling_approval` were reported in chat while the owner looked at Framewright, which showed nothing new. Each side waited for the other. A candidate that needs a human decision goes where the human reviews, beside its reference picture, and the report names it. The same holds for the picture: the approved image is the contract, so a picture the owner has not seen cannot start an acquisition.


<!-- paint-sections-20261124 -->
## 2026-11-24 · The painter's detail falls with a model's size

The painter sees a whole model through twelve 768-pixel views whatever its size. Measured on the Frastown pieces: a 45 cm dock claw got about 0.6 mm of surface a painted pixel and read as immaculate; a 2.2 m skiff about 3 mm and read as smeared and grainy up close; a 15 m hull about 2 cm. The 4096 sheet and the upscaler only stretch what the painter saw, so a bigger atlas is not the fix. Paint a large model again in sections (`paint-sections`), and split a piece over about 4 m into modules at acquisition: one 4096 sheet over a 15 m hull is about 4 mm a texel however well it is painted.

## 2026-11-24 · The head pass leaves a seam on a prop, and the first paint is not the tone to keep

The hero route repaints the top 22% of every model at close range, for faces. On a 2.2 m mast (DK-04.2) the owner found a hard line: above it crisp, and the picture's dark iron; below it flat light putty, the whole-model paint. Two lessons. A face left with the first paint beside a closer paint is a seam, so a section pass paints every face. And the whole-model paint is the less trustworthy colour on a large or thin model, so sections keep their own colour and are matched to each other where they overlap, not to the first paint. Run the head pass on figures only.


<!-- relief-tilt-20261124 -->
## 2026-11-24 · A relief strength means nothing across paints; a steepness does

Relief from paint raises the paint's local contrast into a normal map, so the same strength gives a calm surface on a smooth paint and orange peel on a busy one. On the section-painted Frastown mast, strength 1 tilted the normals 41 degrees at the 90th percentile where the finished dock claw tilts 4.5. Ask for a steepness instead (`--relief-tilt`) and measure the result against a model the owner has accepted.
