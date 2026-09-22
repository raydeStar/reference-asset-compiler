# Character pose and animation review

*Type: reference*

A playable clip is not necessarily a usable animation. Start with the character's
intended stance, then add movement. Read this document before authoring, retargeting,
or delivering character clips, including browser-only demos outside the UE ledger.

## Pose first

1. State the intended action in plain language. A relaxed standing idle has arms
   beside the torso, softly bent elbows, palms turned toward the thighs, relaxed
   fingers, supported weight and planted feet. A-pose and T-pose are rig setup
   poses, not standing idles. Seated, working, armed and quadruped idles need their
   own explicit stance; never force them through the standing-human contract.
2. Preserve the accepted mesh, UVs, material images, weights, joint hierarchy,
   rest transforms and inverse bind matrices. Pose the existing rig in a new
   action. Do not apply that pose as a new rest pose or deform the source mesh.
3. Establish a held baseline pose before breathing, swaying, looking, gesturing,
   or making a batch of other clips. Review front, three-quarter, side and back,
   including shoulders, armpits, forearms, hands, garment clearance and feet.
   Small rotations around an outstretched bind pose do not solve the stance.
4. Keep all loop endpoints on the authored idle baseline. Never key identity
   transforms as shorthand for "neutral" unless identity is that actual stance.
   Sample the interior as well: the loop can return to an A-pose halfway through.
5. When the user asks to fix only a pose, deliver that pose for review and stop
   before additional motion. Call a held pose a held pose, not a breathing idle.
   Follow the user's approval policy; don't invent extra approval gates, and
   don't record an agent's review as human acceptance.

## Export and consumer checks

- Compare the final GLB's original mesh accessors, index buffers, embedded images,
  materials, skins, joint hierarchy and bind transforms against the source. Pose
  work should add animation payload only. Preserve an audit bound to both hashes.
- Reimport the **exported** GLB and explicitly select the intended clip. Native
  Blender screenshots alone do not establish what the consumer will display.
- For an arms-down humanoid standing idle with the canonical humanoid joint names,
  run the check below before presenting it in the library. Nonzero exit blocks
  delivery as a corrected idle. Retain failed receipts; fix the pose or explicitly
  choose a different, justified pose contract. Do not relax thresholds merely to
  accept an obvious A-pose.
- Render four views of the reimported clip. Check the start, an interior time and
  the loop seam. For moving clips, inspect playback over at least two loops in
  the actual consumer and check for pops, sliding feet, drift and intersections.
- Check clip selection, scrubbing and exporting with/without the intended clip.
  No-animation export should retain the original asset pose and rig. Name it
  accordingly; do not silently bake a preview frame into the rest geometry.
- Passing tests, skeleton fingerprints, channel counts, rig motion, GLB imports,
  browser playback and absence of console errors establish mechanical behavior.
  None establishes natural motion or artistic acceptance. Record those separately.

```text
blender -b --factory-startup --python-exit-code 1 --python scripts/blender/check_relaxed_idle.py -- candidate.glb Innkeeper_Relaxed_Idle new-pose-check.json --height 1.82
```

The check evaluates the delivered clip at 24 samples per second (at least nine,
including both endpoints). Bone names must match `idle_pose.JOINTS`; unknown
skeletons and missing clips fail closed. Blender world coordinates are Z-up;
the package's pure function also accepts an explicit up axis for other consumers.

The standing-idle checks require upper arms within 20 degrees of down, elbow bends
of 3–35 degrees, wrists within 9% of character height horizontally from shoulders
and no more than 6% above the pelvis, pelvis/foot drift within 0.3% of height,
loop joint-position gaps within 0.1%, and loop orientation gaps within 0.5 degrees.
These checks catch gross stance failures. They **do not** prove mesh clearance,
hand orientation, deformation quality, continuous collision freedom, naturalness,
or complete ground contact. Fixed-view and consumer review remain necessary.
This is an opt-in authoring check, not yet a mandatory gate on arbitrary studio imports.

## Reproducing the innkeeper's held pose

`scripts/blender/author_held_pose.py` applies a hash-bound recipe to an existing
native rig. Aims are applied parent first in rig coordinates, followed by local
finger rotations. It refuses source hash mismatches, constrained control rigs,
missing UV layers and output overwrites. It writes one two-second **held pose**
action, native/GLB outputs and a receipt. It does not author breathing or other
motion, and never marks approval.

```text
blender -b --factory-startup --python-exit-code 1 --python scripts/blender/author_held_pose.py -- work/moonlit-tavern/innkeeper/face-v4/projected-final-v3/innkeeper.blend recipes/moonlit-tavern-innkeeper-held-idle.json work/moonlit-tavern/idle-v2/fresh-attempt
```

The recipe is specific to the innkeeper v4 rig. Do not copy its angles onto other
characters as a universal idle. Existing twist-bone and finger weighting still
need visual review; detailed hand performance remains limited by this mesh.

The original four tavern clips under `animation-v1/` were **rejected by the user**
on 2026-09-22. Their valid payload/rig checks are retained, but they are not accepted
animations. The human idle added small deltas around an A-pose and keyed identity
at the loop endpoints. New work must start from a deliberately authored stance.

Record the source and candidate hashes, exact clip, pose intent, sample receipt,
four-view paths, consumer asset/revision, review status, limitations, and next gate.
An explicit rejection must survive into STATUS and HANDOFF, not disappear behind
an older green technical test result.
