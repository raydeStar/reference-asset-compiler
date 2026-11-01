# Raider revamp: a modular, speaking, AAA-grade character

CH-03 Raider base is the test character for raising RAC's character quality.
The target is one cohesive character: separate parts that each carry their own
UVs and textures, one skeleton that drives them all, a face that can speak,
and motion that holds up from every side. Each improvement lands in RAC as a
reusable step, so the next character is easier, not just this one better.

Working folder: `work/raider-revamp/` (ignored by git). The sources in
`work/raider-revamp/sources/` are copies of the CH-03 files with hashes in
`sources.sha256`; they match the hashes Framewright recorded. The originals in
`work/artiss-tomb-2026-10-16/assets/CH-03/` are never written.

## Rules for this work

- **Open source only.** Every tool, model, template and motion clip must be
  under an open licence, and is recorded in the ledger below. The one current
  exception is Hunyuan3D (geometry and paint), which Mark has allowed until he
  refactors it out. Auto-Rig Pro, Mixamo, Epic's sample content and other paid
  or proprietary sources are out.
- The approved reference image is the artistic contract. The acquired AI
  geometry is the shape authority; Mark judged the model itself fine.
- Each stage ends with the same labelled reference-vs-model sheet, regenerated,
  plus close-ups and, once there is motion, motion sheets. Mark gates every
  stage; operator review is evidence, not approval.
- Repairs are versioned derivatives. Failures are recorded, not silently retried.

## Diagnosis of v0 (2026-11-01)

The v0 sheet is `work/raider-revamp/evidence/raider-v0-baseline.jpg`.

- **Texture.** The 2048 atlas is cut into 821 UV islands, 559 of them four
  faces or fewer, and half the atlas is unused. Colour shifts at every seam;
  that is the blotchy camouflage look. The head, hair and neck together get
  3.1% of the map. No normal
  or occlusion map was baked from the 663k-triangle acquired mesh, so the low
  poly model shows none of its folds, stitching or plate edges.
- **Face.** The 15k-triangle reduction left the head a few flat planes; the
  face is a painted picture on them. There is no mouth, eye or teeth geometry,
  so it cannot speak or blink.
- **Hands.** The gloves are mittens: the fingers are fused in the acquired
  geometry as well, so reduction alone cannot separate them.
- **Shape.** The silhouette, outfit and equipment read well. One plate on the
  back is not in the reference.
- **Rig.** The v0 rig came from Auto-Rig Pro, which is not open source. It is
  replaced, not reused.

## Target part layout

| Part | Source of shape | Notes |
| --- | --- | --- |
| Head | MakeHuman CC0 base head fitted to the acquired head | Face loops for speech; eyes, teeth, tongue; beard painted |
| Hair | Acquired hair shell, separated | Later: alpha fringe cards |
| Hands (gloves) | MakeHuman CC0 hands fitted to the acquired glove volume | Separate fingers for grips |
| Jacket | Acquired, separated | Rolled sleeves, collar |
| Trousers | Acquired, separated | |
| Boots | Acquired, separated | |
| Equipment | Acquired, separated | Shoulder plate, chest plates, knee pads, belt, buckle, pouches, harness, thigh pouch; rigid pieces ride one bone each |

Each part gets its own UV set at a consistent texel density, a normal and
occlusion bake from the acquired dense mesh, and its own material.

## Stages

1. **Separate (modeling gate).** Segment the acquired mesh into the parts
   above; cap the openings; reduce each part with its own budget (more on the
   head and hands). Fit the head and gloves.
2. **UV and bake.** Hand-placed seams per part, few large islands, then bake
   normal, occlusion and curvature from the dense acquisition.
3. **Paint (texture gate).** Colour from the reference and AI paint, transported
   onto the new UVs; material-specific roughness and metal. Face landmarks must
   line up with the modeled eyes, nose and mouth.
4. **Rig (deformation gate).** One open-source UE-named skeleton for every part;
   rigid equipment on single bones; jaw and eye bones; facial shape keys for
   blinks, brows and speech mouth shapes.
5. **Animate (animation gate).** Held stance, idle, locomotion and speech, from
   open-source motion and RAC's polish and contact checks.
6. **Engine.** Cooked UE5 result in motion, then fix only what it shows.

## Open-source ledger

| Item | Use | Licence |
| --- | --- | --- |
| Blender 5.2 | All modeling, UV, bake, rig, render work | GPL-3.0 |
| MPFB 2 (MakeHuman for Blender) | Base head and hands, expression targets | GPL-3.0 (tool), CC0 (assets) |
| Segment Anything (ViT-B) | Part masks on fixed-view renders | Apache-2.0 |
| Rhubarb Lip Sync | Mouth shapes from speech audio | MIT |
| Quaternius Universal Animation Library | Locomotion source motion | CC0 |
| Real-ESRGAN | Paint upscaling | BSD-3-Clause |
| Hunyuan3D 2 / Paint 2.1 | Geometry and paint, temporarily allowed | Tencent licence (not open source) |

Add every new item before it is used.

## Progress

- 2026-11-01: sources copied and hashed; v0 diagnosed; plan written.
- 2026-11-01: part separation, first pass. Labelling the rigged v0 by skin
  weights separates head, gloves, boots and belt cleanly; labelling cloth and
  equipment by v0 paint colour fails (muddy grey cloth reads as metal), so the
  v0 paint is not used for segmentation
  (`evidence/seg-proto/colour-rule-labels-rejected.jpg`). Segment Anything
  ViT-B on the reference instead: automatic masks plus point and box prompts for
  the dark jacket, glove, thigh pouch and harness, and a hem-line split between
  jacket and trousers, give an 18-part front map
  (`evidence/reference-part-map-v1.png`). Known gap: the crossing harness
  straps under the chest plate merged into the jacket. Prototype scripts are in
  `work/raider-revamp/proto/`.
- Next: project the part map onto the dense acquired mesh from the reference
  camera, grow labels to hidden and back faces along concave creases, then
  check the result from four views.
