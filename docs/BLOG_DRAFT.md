# I gave an AI one drawing of a cat and asked for a UE5 character. Here's what it actually took.

*Type: draft*

*Draft. Images are in `docs/images/` of the repo; swap the relative paths for
wherever you host them. Cut freely.*

![From one image to a skinned skeleton in UE5](images/hero-cat-image-to-ue5.jpg)

Every image-to-3D demo I've seen ends at the same frame: a GLB spinning on a
turntable, lit from the front, looking great. Nobody shows you the side view.
Nobody shows you the back. Nobody shows you what happens when you try to put
bones in it and walk it around in an actual engine.

So that's what I set out to do: one concept image in, a rigged, textured,
walkable Unreal Engine 5 character out, and a receipt for every decision along
the way so I could do it again tomorrow with a different picture. This is the
build log. The repo is open source (MIT) at the bottom.

## The rules I set for myself

I've been burned by "AI pipelines" that are really a person doing the work and
the AI doing the screenshots. So the rules were strict, and they're written
into the repo's agent instructions:

1. **The image is the contract.** The reference picture is hashed at intake and
   never touched again. Everything downstream has to trace back to it.
2. **The AI generates. I don't sculpt.** If the geometry model gets the tail
   wrong, I fix the input or the model, not the mesh by hand. A convincing
   Blender reconstruction that the image didn't condition is a failure, even
   if it looks good.
3. **One gate at a time.** Modeling is approved before texturing starts.
   Texturing is approved before rigging starts. Each approval is a ledger entry
   with the SHA-256 of exactly what I looked at and my name on it.
4. **Numbers before eyes.** Every stage writes a JSON receipt: hashes in, hashes
   out, measurements, and why. If a stage fails, it says which bone, which
   texel, which millimetre.
5. **No silent retries.** A crashed inference is recorded, not rerun until it
   happens to work.

Those rules made the project slower and the result honest. They also caught
the bugs I'm about to describe, none of which I would have found by looking at
a turntable.

## The subject

An orange adventurer cat. Scarf, backpack, belt with pouches, boots, striped
tail. Chibi proportions. Big round eyes. The kind of thing you'd hand a
character artist and get back in a week.

## Stage 1: geometry

Hunyuan3D 2.1 (Tencent's open image-to-3D model) generates the shape. The
first version of the cat came back with the tail curled into a closed loop.
Under rule 2, I didn't fix the tail in Blender; I fixed the *reference* with an
AI image edit that opened the tail into a trailing curve, re-hashed it as a new
authority, and regenerated. The loop was gone. The receipt for that decision
lives in the repo as a rejection, not a footnote.

Modeling review is four fixed clay renders: front, three-quarter, side, back.
The cat passed on the second lineage.

## Stage 2: retopology

The raw generation is dense and noisy. Feature-aware quadric decimation took it
to 20,000 triangles at 80% quads, with joint-ring guides fitted to the AI
surface at the neck, shoulders, elbows, wrists, hips, knees, and ankles. The
receipt records 4.96 mm p99 deviation from the dense authority, 11.6 mm max.
Whole-surface remeshers were tried and rejected: they erased the eyes,
whiskers, and costume. Recorded, not repeated.

## Stage 3: texture, and the bug that wasn't

Hunyuan3D-Paint 2.1 paints PBR maps onto the *exact* retopologized mesh with
its UVs locked (the topology gate refuses more than one micrometre of drift).
First paint: the eyes came out as a pinched teardrop and a narrow slit. A
region-bounded reprojection of an eye-corrected reference fixed them without
repainting the body.

Then I looked at the review render and my heart sank. The fur was salmon pink.
The whole thing looked washed out. Four days of a previous attempt had ended in
exactly this feeling.

![The same atlas under two display transforms](images/cat-texture-review-calibration.jpg)

It was the renderer. Blender's factory view transform (AgX) plus a hot
three-light rig was clipping a third of the subject and desaturating the
oranges into pink. The *unlit albedo* of the same atlas was saturated and
reference-like all along. Under a calibrated Standard transform at -1.5 EV,
the forehead fur landed within a few percent of the reference colour.

Lesson one, and the biggest of the project: **judge textures on a calibrated
display transform, or you will reject good work.** The review renderer now has
a `calibrated` mode and the factory mode is kept only to reproduce old evidence.

## Stage 3b: the eye that wasn't painted

One eye had a hard white shape over the iris in every lit render. The unlit
albedo showed a clean eye with the small painted glint the reference has. So it
wasn't paint. It was the roughness map: the AI had left both eyes at roughness
0.11 on a head that's otherwise 0.95, and the key light was mirroring off the
slightly lumpy eye geometry.

![Eye roughness before and after](images/cat-eye-roughness-fix.jpg)

The fix is a 120-line script that lifts glossy texels inside a geometry-derived
region to a floor, records the mask and the texel count, and touches nothing
else. Base colour, metallic, mesh, UVs: byte-identical. Roughness on 4,235
texels: 0.11 to 0.7. I rendered 0.35, 0.5 and 0.7 and picked the one that
matched the matte painted-glint style of the reference.

Lesson two: **when a lit view shows something the unlit view doesn't, check the
material channels before blaming the art.**

## Stage 4: a rig without the paid add-on

I own Auto-Rig Pro. Most indie devs don't want to buy a $50 add-on to try a
pipeline. So the rig stage is either-or: one command probes Blender for
Auto-Rig Pro and uses it if it's there, otherwise it derives the skeleton from
the mesh itself.

For the cat (a 26-bone mascot skeleton with a tail), the joints come from the
reviewed joint-ring guides carried into the payload frame, cross-section
centroids for the spine, surface reach for hands and toes, and a binned
centreline for the tail. Heat weights bound all 10,008 vertices at 100%
coverage with no fill.

![Skeleton overlay and the five-pose deformation suite](images/cat-rig-review.jpg)

The gate is numeric: bone names, parents, and count against the profile, max
four influences, zero unweighted vertices, and a five-pose deformation suite
(arms forward, one arm only, elbows, knees, spine twist) with front and side
renders. The one-arm pose has to move only the +X half of the body; that's how
a mirrored rig gets caught without eyes.

For a humanoid I tested the free route on an existing character with its
armature stripped: 86 bones, passes the Manny-compatible profile, passes all
five poses. Heat weights failed on that eight-shell layered mesh and fell back
to envelope weights, which is exactly the quality gap Auto-Rig Pro's voxel
binding closes. The README has a table saying so.

![Landmark-derived Manny-compatible skeleton on an unrigged humanoid](images/humanoid-landmark-rig-overlay.jpg)

## Stage 5: Unreal, and the characters that weren't there

Compile to FBX plus PNG maps plus an import manifest. A headless UE 5.8 import
verifies what the engine actually built: 180.0 cm tall, the material samples
all three textures, three LODs, correct texture settings. Then a gallery level
with every character on a floor, Manny's idle retargeted onto every skeleton
through IK Rigs built from bone names, and the Third Person template character
so you can walk the line.

First launch: chairs. Just the chairs. Every character invisible.

Two bugs. The small one: I'd copied the Blueprints from the *C++* third-person
template, which reference a compiled module; the Blueprint template's assets
fixed that. The big one took a while: every compiled skeleton arrives in UE
with a **100x scale on its root bone and bone offsets in metres**. It's a
Blender FBX unit artifact. The mesh renders correctly in bind pose. Every gate
passes. Nothing notices until you retarget an animation onto it, at which point
the IK Retargeter writes the pelvis height in centimetres into a metre-scaled
local space and hoists each character 50 to 90 metres into the sky.

I found it by composing poses from the animation data by hand and printing
where the pelvis ended up. The fix compensates in the retarget step and is
recorded in the decisions log; the durable fix (export in centimetres with unit
root scale) is the first item in the open-tasks list.

Lesson three: **"passes every gate" means "passes every gate you wrote."**
Write the gate for the thing that just bit you.

## Stage 5b: the metric was right and the faces were wrong

With the characters visible, every legacy human had its face pitched down and
the ninja's hands twisted. I'd auto-aligned every bone of each target skeleton
to Manny's retarget pose. By the numbers that was the best choice: 0.3 to 1.6
degrees of segment mismatch versus Manny. By eye it was the worst, because
those skeletons' head bones tilt back while their faces look forward, so
matching bone direction rotates the face down.

Limbs genuinely need alignment (the ninja rests near a T-pose). The spine and
head don't. The policy is now limbs-only, the metric is recorded for all three
variants, and the doc says why the metric doesn't get the final say.

![The playable UE5 gallery](images/ue5-gallery-playable.jpg)

## What it cost, honestly

- One working day for the cat from image to walkable gallery, most of it
  review. Two human approvals that can't be automated: modeling and texture.
- A 24 GB GPU for the two AI stages. Everything else runs on CPU.
- About 5 GB of disk without the AI stages, about 60 GB with them. (I wrote
  200 GB in the first draft of the docs. Then I measured. Measure.)

## What's still owed

- Texel density is 19.5 texels/cm² on a Manny-scale body against a 120 floor,
  and the UV layout is 783 confetti islands. Both are measured on every build
  and carried as a named waiver, not silently passed.
- The 100x root scale, compensated but not yet fixed at export.
- Hand roll under the retargeted idle: chain alignment can't fix roll about
  the bone axis.
- Windows only for the drivers. The Blender stages are plain Python.
- The cat is one data point. A second character is the next real test.

## Why I'm publishing it anyway

Because the discipline is the product. Anyone can get a spinning GLB. What I
didn't have, and now do, is a pipeline where a picture goes in, two humans
decisions come out, and every other step is a script with a receipt that a
stranger (or a coding agent) can rerun cold. The repo's docs are written for
that stranger: what you need, what runs without a GPU, what failed and why so
you don't repeat it, and a task list with acceptance criteria if you want to
help.

Repo: https://github.com/raydeStar/reference-asset-compiler

If you try it, tell me what broke. That's the whole point of the receipts.
