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
- 2026-11-01: parts separated on the dense acquired mesh, first pass
  (`evidence/raider-parts-v1.jpg`, `parts-v1/raider-parts-dense.blend`, 16
  part objects, 663,532 triangles). Method (`proto/project_parts.py`):
  - The crossing harness straps were added to the 2D map with Segment
    Anything point prompts.
  - Front and back are told apart by the boot toes; the front orthographic
    view matches the reference silhouette at IoU 0.864.
  - Faces turned toward the camera (normal facing it at more than 0.35) take
    labels by per-pixel ray cast; the rest grow along the surface, where
    concave creases cost 25 times more.
  - Equipment may only reach a set distance around the body. Hidden faces
    otherwise take the cloth or body part seen at the same screen position,
    with the equipment removed from the map. Above the beard line, faces
    turned backwards or upwards are hair.
  - Rolled sleeves count as jacket.

  Known rough spots: the hair and skin edge at the temples, the back of the
  collar partly labelled hair, the belt band at the back partly jacket, and a
  small knee-pad spill on his left thigh.
- 2026-11-01: the workstation blue-screened (bugcheck 0x00020001) during a
  projection run. The i9-14900K has logged corrected machine checks
  ("internal parity error") on the same core, APIC ID 33, on 12, 20 and
  30 October. That is a hardware-stability signal, not a script fault: the
  same run had completed five times. Runs save their results as they go.
- 2026-11-01: modeling gate v2 (`evidence/raider-parts-v2.jpg`,
  `parts-v2/raider-parts-v2.blend`, `parts-v2/raider-head-v1.blend`; scripts
  in `scripts/revamp/raider/`).
  - Labels: above the shoulders, hair, face, beard and collar are regrown
    from sure seeds along creases; the beard may not climb above the nose. The
    belt band runs round the back; boxes standing proud of the belt are
    pouches; knee pads stop at the top of the pad and at 60 degrees round
    the leg; islands under 250 faces join their neighbours.
  - Capping every opening flat was tried and rejected: caps on large, curved
    openings cut through the face and chest. Instead, cloth continues under
    each overlay (the covered area is relaxed into a smooth membrane), every
    overlay (straps, plates, belt, buckle, pouches, knee pads, boot straps,
    hair) is a closed thin shell, and each cloth part's open edge folds a
    short skirt inward so no hole shows between parts.
  - Reduced from 663k to 120k triangles, each part to its own budget.
  - Head: the MPFB MakeHuman head (male, CC0 assets) is aligned on eye, mouth
    and nose landmarks (vertical and width scales agree within 2.5%), then
    takes a smooth low-frequency offset field, so it keeps MakeHuman's
    eyelids, lips and nostrils. Mean distance to the acquired head is 0.004
    (p95 0.009, head height about 0.25). It carries teeth, tongue and 34
    expression shape keys; mouth open, smile, "oo", blink and brows are shown.
    MakeHuman's lids close over the socket, so its helper eyes were replaced
    with eyeball spheres seated by depth.
  - The acquired beard is retired as geometry: a shell over a talking mouth
    cannot follow it. The beard is a `beard_mask` vertex group on the head for
    the paint stage.
  - Still open: gloves are the acquired shape (jointed MakeHuman hands come
    with the rig, since they must be posed to the glove); hair is the acquired
    lumpy shell (cards at paint); the eyes are placeholder spheres; the
    MakeHuman system assets (CC0 eyes, brows, lashes) need a download.
- 2026-11-01: Mark rejected the v2 face ("face is a fail"); the body parts
  were not rejected. The low-frequency fit gave a generic MakeHuman face with
  sunken placeholder eyes, untextured. Tried next (`fit_head_v2.py`): a tight
  pass snaps the skin onto the acquired head except the eyelids, lips and ears
  (residual mean 0.0038 to 0.0026). To judge likeness, the reference picture
  was projected front-on as colour onto both heads and the acquired head
  (`face_preview.py`, `evidence/raider-face-options.jpg`). With colour, all
  three read as the reference from the front. The acquired head (A) looks
  most natural but cannot blink or talk. Both MakeHuman fits (B loose,
  C tight) show spectacle-like rings where the lids meet the eyeballs.
  Mark rejected all three ("they are all bad").
- 2026-11-01: diagnosis: every option starts from the head cut out of the
  whole-body acquisition, which gives the head a small share of the
  generator's resolution. Its hair is lumps, its eyes are shallow dents, and
  no fit or projection can add structure that is not there. That matches the
  2026-09-05 decisions ("head paint cannot replace facial structure"; "head-only
  acquisition restores detail"). New head-only acquisition: the reference head
  is cropped and upscaled 4x with Real-ESRGAN (`head_crop.py`), registered as
  workspace `work/raider-head` (`rac new`, kind humanoid), and run once through
  the single-view launcher (`configs/generation/raider-head-attempt001.json`,
  seed 42, 50 steps, octree 512; 1.55M triangles in 16 s, 5.2 GB VRAM peak).
  In clay it has hair strands with volume, eyelids, brow ridges, lips, ears
  and relief for the beard and collar (`evidence/raider-head-old-vs-new.jpg`).
  This is a candidate only, waiting on Mark's modeling gate.
- Next, if the new head passes: place it on the body; wrap MakeHuman topology
  tightly onto it for blinks and speech; paint it with registered front
  colour plus the painter for the sides and hair.
