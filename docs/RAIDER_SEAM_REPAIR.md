# Raider: when to recut equipment

The November 3 v7 repair is a local review candidate. Start in
`work/raider-seams-20261103/delivery/`: **Review.html** has matched lighting,
four full-body views, four close-ups, and two posed close-ups. The **GLB**
is the portable skinned character; the **Blender file** has packed images and
face selections `Review_ArmouredShoulder` and `Review_RearPouch` on the body.
Opus's original GLB remains the correct starting point for detachable gear.

### What the pictures show

The front reference was used for the original acquisition; SAM-derived labels
were projected onto the dense mesh. In this build they are not individually
generated, complete 3D articles. A wrong mask outline became a thick wall
through the outer plate and rear pouch. The paint looked relatively continuous
unlit, but the shell sides caught the studio light. A seam in both a clay
render and a part-ID view is good reason to stop changing the texture atlas.

### What changed

The derivative uses the v7 assembled bounds to register the original dense
acquisition to the rig. It restores the affected torso/strap/waist support,
subdivides locally, and transfers surface positions and smooth normals from
the acquisition. It retains a closed front-left pouch section over an actual
hole in the original backing. Visible paint is sampled from v7 along acquired
surface normals onto a local atlas. The pauldron gets a neutral steel finish
sampled from the approved front reference, and the leather keeps its existing
flap and stitch marks. Micro-normal detail is baked in the new tangent frame.
The two photographed surfaces run continuously with the body. Do not use this
as an instruction to flatten every article on future characters.

The rear pouch follows one blended spine/pelvis weight set across its face,
with a transition into the jacket. Skin influences are limited to four, as in
the original shipped GLB; the original *native* Manny finished file had up to
seven. The delivered native rig passes the hero gate (88 bones, 76,154
triangles, zero unweighted vertices). The GLB's skeleton, inverse bind matrices,
face, eyes, teeth, tongue, mouth cavity, and all 34 facial shape names match
the Framewright baseline. All nine existing image payloads remain byte-identical.
This reuses the user's existing acquisition and paint; no inference was run.

### The check to reuse

Run a small material-independent depth comparison on the real before/after
exports. The configuration names cameras, thresholds and pixel resolution.
Red is a missing surface or a depth loss on a previously continuous visible
area; it is an inspection aid, not an approval. Example from the repository:

```powershell
$job = 'work/raider-seams-20261103'
& $Blender -b --factory-startup --python-exit-code 2 --python scripts/blender/compare_surface_crops.py -- `
    "$job/Framewright-v7-input.glb" "$job/delivery/Raider_Seam_Repair.glb" `
    "$job/depth-cameras.json" "$job/depth-review-new"
```

The largest recessed front-pouch area fell from **22.6%** of tested pixels
in the rejected candidate to **0.59%** in the delivery. The same check still
flags the shoulder outline (2.65% connected). In the flagged pixels common
to all three meshes, median absolute depth error against the acquired surface
is 16.57 mm for v7 vs 0.89 mm for the repair; 22 flagged pixels still have
acquisition coverage but no candidate coverage. The output deliberately
continues to request inspection there.

The shoulder is smoother and rounder than the concept; some side leather
remains smeared. The strong raised-arm test shows the same collar opening in
both models. Four posed GLB probes are bounded skin tests, not gameplay.
No game package, shared Framewright catalog, rig animation, or human gate was
updated. The GLB has no baked animation clip, like the v7 review export.

The **Opus_Replay.zip** in the delivery includes the asset-specific fitting
scripts, replay command, camera configuration and diagnostic. Run it only on
the matching finished v7 inputs. A fresh replay completed; mesh triangulation
and packing may vary, so identify the reviewed outputs by the
[receipt](evidence/raider-seams-20261103.json), not a rerun's filename.

## Fitted outfit for Framewright

The artist's next three close-ups showed a ridge at the thigh strap, a cut
through the buckle, and a wide band on both jacket tails. The v7 part builder
inset the support surface and thickened the selected regions. That created a
wall even when the original acquisition already contained the piece. A UV
seam or a true stitched hem does not need such a wall.

1. Keep the original acquired surface and face labels in matching face order.
   Select the pieces meant to travel together. The CPU fitting helper keeps
   shared vertices across those labels and simplifies only after joining the
   selection. It does not fill holes or reconstruct hidden sides. The example
   assumes an indexed pre-cut mesh, one primitive, and a budget chosen for this
   Raider outfit only. Remove `--largest-component` to retain separate islands;
   inspect the discarded-face count before accepting an outfit.

   ```powershell
   python scripts/fit_segmented_surface.py dense-recut.glb face-labels.npy part-names.json fitted.npz --include belt boot boot_strap buckle jacket kneepad plate pouch sleeve_roll strap thigh_pouch trousers --largest-component --triangles 34700
   ```

2. Register the acquisition to the existing rig, unwrap once, and transfer
   paint and weights in that space. Prefer the previously reviewed paint
   outside the defect. Use the original front reference for the actual metal
   buckle frame and its two pins, the leather band and narrow stitched hem.
   At unobserved angles (particularly the outer thigh pouch) appearance is an
   estimate. Use the [final class assignment](../examples/material-sweep/raider/continuous/finish.json)
   and its sibling mask in the standard `material-sweep` with the
   `framewright-scene` preset. A misplaced material boundary can introduce
   another false seam on geometrically smooth cloth.

3. In areas which should be a single fitted surface, check the **exported**
   mesh for more than one connected piece or open edges. The file specifies
   boxes in mesh-local glTF XYZ. This reports rest topology after joining
   exactly coincident positions; it cannot see paint errors, prove skin
   continuity in motion, or judge intentionally overlapping accessories.
   Choose new boxes for new assets. Use matched depth crops, posed checks
   and an actual lit viewport alongside it.

   ```powershell
   python scripts/check_fitted_surface.py Raider_Continuous_Outfit.glb examples/material-sweep/raider/fitted-surface-regions.json new-continuity.json
   ```

The old / fitted component counts are **2 / 1** at the buckle, **3 / 1** at
the thigh strap and **4 / 1** at the jacket front hem. There are no open or
non-manifold edges in those three fitted boxes. Seven depth crops stayed below
the existing 1% connected-loss alarm. The native hero rig passed with 65,949
triangles, 88 joints, four maximum influences and no unweighted vertices.
Fitted gear cannot be independently removed; preserve v7 for that use.

Open **Raider material review** in Framewright Scene, or open
`work/raider-continuous-20261103/delivery/Review.html` for both lighting rigs
at 14 matched views. The same directory contains the skinned GLB, native
Blender rig and the reproducible finish kit. [Review receipt](evidence/raider-continuous-20261103.json).

### Outer thigh pouch

Scene v5 reviews the finish on the wearer's right outer thigh. The approved
concept sees the bag largely edge-on. Its new broad face is an interpretation:
imagegen used the original design plus a straight-on render of the fitted
surface, captured without the hand. A second conditioned image supplied the
narrow leather gusset. Replaying the finish uses these frozen references.

For a similar accessory, project each reference where the mesh faces its
camera. Wrap the narrow end and underside separately; stretching the final
column of a frontal reference across the turn makes a stripe. Assign
overlapping trim or stitching to just one projection, then keep baked
background shadows off the lower rim. Use local texture space where the detail
is needed. The Raider's existing UV fragments were packed at 2.70 times their
former linear density while retaining their tangent directions. Only the
press stud receives a metallic finish; the leather and stitching remain matte.

The exported position, winding, normal and skin weights match v4 on every
triangle. Controls include a buckle close-up and the original glove angle.
The current scene camera sits below the hand, with the same lighting and
exposure as v4. Open `work/raider-pouch-20261103/delivery/Review.html` for
both Framewright lighting setups, the side references and the posed comparison.
The same folder holds `Pouch_Replay.zip` (commands, frozen references and
region samples), the GLB and the packed Blender rig. [Export and capture receipt](evidence/raider-pouch-20261103.json).
