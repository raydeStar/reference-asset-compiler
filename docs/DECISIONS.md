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
