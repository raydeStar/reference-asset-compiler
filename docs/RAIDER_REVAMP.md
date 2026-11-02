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
| MakeHuman system assets (`makehuman_system_assets_cc0.zip`, 280,737,770 bytes, sha256 `b542127a…0107`) | Eyes, teeth, tongue (installed into MPFB's user data, not this repository) | CC0 |
| MediaPipe face landmarker (ComfyUI's PyTorch port) | 478 face landmarks for the face wrap | Apache-2.0 |
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
  Mark passed the new head's shape ("new is really good").
- 2026-11-01: head painted (`evidence/raider-head-painted-v1.jpg`).
  - Paint mesh: the candidate reduced by QEM collapse to 100k triangles,
    Smart UV Project, exported with a material
    (`head_paint_prep.py`, `work/raider-head/modeling/raider-head-paintmesh-100k-v2.glb`).
    Attempt 1 failed before inference: exported without a material, the
    painter's loader dropped the UVs (`ColorVisuals has no uv`). Retained, not
    retried.
  - Attempt 2: `run_hy3d21_texture.ps1 -Views 12 -Resolution 768 -RunnerKind
    studio -Atlas 4096` with the head crop as reference. The topology/UV gate
    passed (geometry delta 1.7e-7, UV delta 0). The process then exited
    abnormally (-1073741819) during teardown, after writing its outputs;
    receipt retained.
  - Result: unlike the shallow Ayric head (2026-09-05, doubled eyes), this
    head's modeled sockets let the views agree. One pair of eyes sits in the
    sockets; brows, nose, beard, mouth and ears land where the reference has
    them; the hair is painted round the back.
  - The painter's roughness left the skin wet-looking (5th percentile 0.30).
    `clamp_region_roughness.py` now reads the studio runner's PNG maps (test
    added). With a whole-atlas mask and a 0.6 floor, the lit skin reads matte
    (`textures/paint-attempt002-rough60`). Small light specks remain on the
    back of the collar and a dark mark at the top of his left ear.
  Mark passed the painted head ("significantly better than before").
- 2026-11-01: body painted and head placed (`evidence/raider-textured-v1.jpg`,
  `work/raider-revamp/assembled/raider-v3.glb`).
  - Paint mesh: the 16 reduced parts joined and triangulated, one Smart UV
    atlas (`body_paint_prep.py`). The acquired face, beard and hair stay in,
    so the painter sees the whole character the reference shows.
  - Attempt 1 (12 views, 768, 4096 atlas) gave coherent colour, but the
    default scaled pack margin left 88% of the atlas empty across about 10k
    islands (UV area 0.115). A fixed fraction margin (0.001, 4 px) packs to
    0.46. Attempt 2 repainted with that layout and is visibly sharper on the
    pouches, buckle, straps and plates. Both runs passed the topology/UV gate
    and exited abnormally in teardown after writing outputs.
  - The painter left cloth, skin and leather partly metallic (mean 0.088), so
    the trousers read as steel. `calibrate_pbr.py` sets metallic to zero and
    raises roughness to a 0.6 floor inside a non-metal mask, rasterized from
    each painted face's part (`part_uv_mask.py`, nearest reduced part; the
    glTF export drops one degenerate face, so face order is not trusted).
    Plates and buckle are untouched.
  - Head placement (`place_head.py`): body face, beard and hair faces are
    dropped. The painted head is aligned on the nose tip, with the scale from
    nose-to-crown height and ear width (0.242 and 0.247, mean used). Two
    geometric bust cuts were rejected: a plain 2 cm distance cut left a ragged
    neck, and an outside-the-cloth test misread the collar's inner face. The
    kept cut uses the head's own paint: below the jaw, teal-jacket faces go,
    and so do leather faces below the beard; skin and beard stay. The neck
    now runs cleanly into the open collar.
  - Still rough: a dark notch at the back of the collar where the body's neck
    faces were dropped; the plate on the back is not in the reference (it
    came from the acquisition); faint seams may show at the ~10k UV islands
    up close; not yet rigged or speaking.
  Mark passed textured v1 ("Yes, rig him") and asked for a hand check first.
- 2026-11-01: hands checked before rigging (`hand_views.py`,
  `evidence/raider-hands-check.jpg`). They are not good enough to rig. The
  fingers are fused for most of their length and part only at the tips;
  they are short and stubby against the reference's long, slim gloved
  fingers; the flared gauntlet cuff is a thin band. The paint is right. The
  hands came from the whole-body acquisition, which gave them as little
  resolution as it gave the old head. Rigging is held until the hands are
  replaced.
- 2026-11-01: hands replaced by a hand-only acquisition; Mark made detail
  acquisition (heads and hands) a standing pipeline step
  (`docs/WORKFLOW_PLAYBOOK.md`, "Detail acquisition"; `scripts/detail_crop.py`).
  - Right glove cropped from the reference (box 51,565 to 220,811, squared,
    15% margin) and upscaled 4x; workspace `work/raider-hand-r`; one
    single-view run (`configs/generation/raider-hand-r-attempt001.json`,
    873k triangles). In clay the fingers are long and separate to the
    knuckles, and the flared gauntlet and cuff strap are modeled.
  - Painted alone (60k-triangle paint mesh, 12 views, 768, 4096); topology/UV
    gate passed; teardown exit as usual.
  - Attached by `place_hands.py` (`assembled/raider-v13.glb`,
    `evidence/raider-hands-v2.jpg`). Size from the crop: the hand's
    silhouette in reference pixels through the label projection's mapping
    (x and z estimates 0.171 and 0.181). Things that failed on the way, all
    kept in the script's history:
    - Placing by the reference position alone left the hands hanging below
      the wrists; the body's arms are not where the reference draws them.
      Each hand is now lined up with its own old glove's axis and wrist
      (11 and 12 degree turns).
    - A per-face paint cut shredded the gauntlet (leather highlights read as
      skin). The forearm is now cut by one plane where the skin starts.
    - Keeping the largest piece kept one UV island: the painter splits
      vertices at seams, so they are welded first.
    - The forearm skin's ragged lower edge (the old glove/skin label
      boundary) poked out above the gauntlet. The gauntlet is now seated
      3.5 cm further up the arm, and body faces under the opening are
      cleared.
    - Old glove fingertip slivers and specks are removed by proximity to the
      old glove surface and by a loose-piece sweep.
  - Still rough: the strip of bare forearm the reference shows above the
    gauntlet is now mostly covered; one small sliver remains by his left
    fingertips in some views.
  Mark passed the hands ("Yes, rig him").
- 2026-11-01: body rig (`evidence/raider-rig-v1.jpg`,
  `work/raider-revamp/rig/attempt004/rebind8/raider_hero_rigged.fbx`).
  - Production mesh (`prep_production.py`): body, head and hands joined at
    1.82 m, reduced to RAC's hero tier (76k triangles: head 18k, hands 6k
    each, body 46k) instead of waiving the 20k profile budget. A hero-tier
    profile (`prod/ue5_manny-hero.json`) carries `character_tier: hero`.
  - Open-source landmark route, `ue5_manny` skeleton, 86 bones. Three joint
    finder faults fixed in RAC (crotch, arm order, midline; see
    `docs/DECISIONS.md`), and fingers measured from the mesh
    (`measure_finger_landmarks.py`).
  - Weights by `rebind_layered.py`. Tried and rejected, in order: envelope
    (pouches flew with the arms), nearest-bone (the same, A-pose), surface
    spread (straps carried the shoulder onto the chest), limb radius 10 cm
    (jacket side followed the forearm), 7 cm (sleeves left behind). Kept:
    limb regions spread along the welded surface; 36 small pieces made rigid.
  - Gate passed (86 bones, 76k triangles, 4 influences, 0 unweighted);
    deformation suite passed 5 poses. Painted close-ups (`pose_closeups.py`)
    show arms raised, elbow, knee, fist and spread holding together.
  - Still rough: thin threads at the armpits from the shoulder strap with
    the arms raised. No face rig yet.
  Mark rejected rig v1 ("theyre all fails. stretching mesh, weird bends").
  The rule-based weights kept the gear on but bent limbs as stiff segments
  with hard creases.
- 2026-11-01: rig v2 (`evidence/raider-rig-v2.jpg`,
  `rig/attempt004/mhskin4/raider_hero_rigged.fbx`). Weights now come from a
  MakeHuman body (MPFB 2 `game_engine` rig, hand-made CC0 weights) by
  `scripts/blender/skin_from_makehuman.py`:
  - the MakeHuman skeleton is posed onto his joints (trunk left as is;
    limbs, fingers and head moved, turned and stretched, parents first;
    0 mm joint error). An earlier pass that also turned the trunk bones
    swung the hips and shoulders 15-44 cm off, and scaling the rig and the
    parented body together double-scaled the body; both fixed;
  - every vertex copies the weights of the body surface under it;
    MakeHuman bones are shared among the Manny bones of the same region;
  - inside the hands the hand-and-finger share is redistributed over his
    measured finger bones (MakeHuman's closed fingers tore a fist into spikes);
  - 13 small pieces ride one bone.
  Gate passed (86 bones, 76k triangles); deformation suite passed 5 poses.
  The full pose sheet (`pose_sheet.py`, 8 poses, painted and clay, two
  angles) holds for arms out, elbows, lunge, twist and fists. Limits: arms
  overhead bunch the sleeves and push the shoulder plate toward the head; a
  deep squat pushes the jacket hem into the thighs.
  Mark passed rig v2 ("Pass, do the face").
- 2026-11-01: face rig v1 (`evidence/raider-face-rig-v1.jpg`,
  `rig/face-v3/raider_hero_rigged.fbx`). The painted head is one closed
  surface (painted eyes, a painted mouth line), so it cannot blink or speak.
  MakeHuman's head (eyelids, eyeballs, split mouth, teeth, tongue, 34
  expression shapes) is wrapped onto it:
  - `scripts/face_landmarks.py` (migrated from the studio tree; ComfyUI's
    MediaPipe port, Apache-2.0) finds 478 landmarks on straight-on renders
    of both faces (`face_front.py`); 476 pair up.
  - `wrap_face.py`: similarity, then a thin-plate warp through the
    landmarks (inner-lip points dropped; trusted only near the landmarks),
    then the skin is projected onto a lightly smoothed copy of the painted
    surface along each vertex's normal, from the vertex both ways, only
    where the surfaces face the same way, outside the eye openings. What is
    not projected (mouth cavity, inner lips, eyelid rims) follows the
    nearest projected skin in space. Residual 0.8 mm mean, 2 mm p95.
    Rejected on the way: a global warp flattened the back of the head;
    nearest-point snapping and rays started behind the vertex folded flaps
    around the mouth; graph-based fills peeled or tore the face; a strongly
    regularised warp broke the solve.
  - `bake_face.py`: the paint baked as emission (a diffuse bake multiplied
    it by the painter's slight metalness); hair kept as its own piece from
    the painted head; real eyeballs aimed at MediaPipe's iris centres with
    the painted iris colour; a quarter of MakeHuman's blink folded into the
    rest shape so the lids match his heavier ones. One bake run crashed
    Blender with an illegal-instruction fault; the identical re-run passed
    (no WHEA event logged that time).
  - `attach_face.py`: the old head faces leave the body; face, hair and eyes
    enter production space (0.2 mm nudge) with applied transforms, the face
    on the head and neck bones by height, hair and eyes rigid on the head.
    Rig gate passed: 86 bones, 75k triangles, eyes confirm facing.
  - Still rough: a jagged light line across the throat where the painted
    neck ends; scribbled front hair strands; a pale patch at the back of
    the collar. Not done: driving the shapes from speech audio (Rhubarb Lip
    Sync, MIT) and a check inside Unreal.
  Mark: "mouth fails, neck seam fails, eyes look a bit weird but are much
  better than before. Floating faces all around the character, and there is
  some black thing sticking out the back of his neck."
- 2026-11-01: face fixes (`evidence/raider-face-fixes-v1.jpg`,
  `rig/face-v15/raider_hero_rigged.fbx`; `inspect_views.py` lists every
  loose piece and renders the neck and mouth up close).
  - Found: removing the old head also removed the neck skin in the open V
    and at the nape, leaving see-through holes in the collar; about 150 hair
    specks floated round the head and about 2,100 slivers from reducing the
    body's shells; the throat seam was the body's original painted neck skin
    lying in front of the new neck (the face's own neck was clean); the
    tongue sat high and did not move with the jaw; the teeth arch was wider
    than his lips and showed at the corners; the back of the mouth was open.
  - Fixed: the face's neck reaches 12 cm into the collar; the lower neck is
    repainted from the clean skin just under the chin (`fix_neck_paint.py`;
    Pillow cannot blur float images, so OpenCV); body faces lying on the new
    neck, and skin-painted body faces within 3 cm of it, are removed (a
    colour-only rule and a 5 cm reach both shredded leather straps); loose
    pieces swept (1,127 to 99); teeth and tongue scaled to 75% of the lip
    width and moved as one piece, the tongue seated low and carried with the
    lower teeth in every shape, a dark matte backing behind the teeth; eyes
    get one smooth shader (sclera, darker iris edge, iris, pupil by angle
    from the front) instead of colour by face.
  - Rig gate passes (86 bones, 72k triangles). Still not right: a lighter,
    ragged patch remains in the open V on his right where the collar meets
    the neck; the lower teeth corners still show pale; MakeHuman's helper
    teeth and tongue are simple shapes (proper ones are in MakeHuman's free
    CC0 asset pack, which needs a download).
  Mark approved downloading MakeHuman's CC0 system asset pack.
- 2026-11-01: face v2 (`evidence/raider-face-v2.jpg`,
  `rig/face-v20/raider_hero_rigged.fbx`).
  - The pack was downloaded from MakeHuman's primary mirror (the community
    site announced its services were shutting down on 2026-10-21; the file
    was still served), checked to hold only data files, and extracted into
    MPFB's user data, which then reported the system assets installed.
  - `wrap_face.py` adds the CC0 eyes (high-poly, grey iris), teeth
    (`teeth_base`) and tongue (`tongue01`) with MPFB's fitter after the wrap,
    and refits each one per expression shape so the mouth parts move with
    speech. The helper eyes, teeth and tongue are dropped. Replacing the eye
    material outright turned the eyes black (its texture alpha makes the
    cornea clear), so only the iris texture is swapped. Eyelashes were added
    and then left out: Mark found them weird at this style.
  - The throat: the last skin-painted sliver in the open collar survived
    because the colour test brightened already-display-space pixels, washing
    skin out under the saturation cutoff while darker leather passed. With
    the colour read correctly, bright warm skin within 5 cm of the new neck
    is removed and the straps stay intact.
  - Rig gate passes (86 bones, 77k triangles). Still rough: a few skin
    flecks on the collar edge; the hair's front strands are scribbled.
- Next: Mark's look at face v2; then lip-sync and the Unreal check. (open-source UE skeleton,
  MakeHuman face wrapped onto the painted head for blinks and speech,
  carrying the paint by bake).
- 2026-11-01: cleanup, finals and speech (`evidence/raider-final.jpg`,
  `evidence/raider-rig-final.jpg`, `rig/final/raider_hero_rigged.fbx`,
  `speech/raider-speaking.mp4`).
  - Cleanup: the extracted hair piece and the eyelashes are left out of
    `attach_face.py`; skin-painted body faces near the new neck are removed
    out to 8 cm, tested in display space with no gamma (hue 8 to 38,
    saturation above 0.3, value above 0.55; the gamma step washed the
    saturation out and missed the old neck skin); loose fragments swept
    again after welding.
  - Gate passes: 86 bones, 74,350 triangles (hero tier, 80k). Deformation
    suite: 5 poses pass. Known limits: arms overhead bunch the sleeves and
    the head reads sunk; a deep squat pushes the jacket hem into the thighs.
  - `final_renders.py`: four full perspective views and face close-ups.
  - Speech demo (`speak_demo.py`): the line is spoken by Windows' built-in
    SAPI voice "Microsoft David Desktop" (no download), whose VisemeReached
    events give 22 mouth shapes with times. Those times ran about 1.4x long
    against the 22,050 Hz WAV, so they are rescaled onto the WAV's measured
    speech span (0.11 to 6.32 s, scale 0.7161). Each viseme maps to a mix of
    MakeHuman expression shapes (open, retraction, pursing, protrusion,
    compression, ...) keyed at 0.9 on the face, teeth, tongue and eyes, with
    two blinks and a small head nod; EEVEE frames muxed with ffmpeg. This is
    demo lip-sync from a synthesized voice only: arbitrary recorded audio
    needs a phoneme aligner such as Rhubarb (MIT, needs a download).
- 2026-11-01: shoulders v4 (`evidence/raider-shoulders-v4.jpg`,
  `rig/shoulder-v4/raider_hero_rigged.fbx`, `fix_shoulders.py`).
  - Mark found arms-out and arms-overhead weird. The skin-coloured flaps at
    the armpits in the overhead pose were the face mesh's neck: it reaches
    into the collar and flares out to 0.28 m either side at chest height,
    weighted to the neck alone, so lifting the jacket off it exposed it.
    Below 1.54 m it now takes the nearest body vertex's weights, blending
    into its neck weights over 4 cm, and stays under the jacket.
  - Chest skin beside the armpit carried up to 0.8 upper-arm weight; the
    arm's share is now capped inside the shoulder joint (none 6 cm in) and
    weights near the joint are averaged across the layered shells.
  - Tried and dropped: moving the clavicle's share out to the upper arm
    (put more arm weight on the chest; no visible gain) and making the
    pauldron rigid at half clavicle, half upper arm (its inner layer poked
    through as white streaks).
  - Gate passes (86 bones, 74,350 triangles); deformation suite: 5 poses
    pass. The pose sheet's overhead test lifts the collarbones only 15
    degrees, which is what makes the head look sunk; at a natural 30 degrees
    it reads normally. Arms-out is nearly unchanged apart from a small skin
    patch at the left armpit, now gone.
- 2026-11-01: speech demo v2 (`speech/raider-speaking-v2.mp4`, on
  `rig/shoulder-v4`). The first demo's mouth barely opened (shapes at 0.9
  times the viseme mix) and the blinks turned the eye area dark. Rendered
  with `RAC_SPEAK_GAIN=1.5 RAC_SPEAK_BLINK=0 RAC_SPEAK_DIST=1.0`. The blink
  shape still needs fixing before blinks go back in.
- 2026-11-01: mouth v1 (`evidence/raider-mouth-v1.jpg`,
  `rig/mouth-v1/raider_hero_rigged.fbx`, `fix_mouth.py`,
  `speech/raider-speaking-v3.mp4`).
  - Mark: the lips look jagged and "the teeth aren't in place". Measured:
    MPFB's per-shape refit bent both arches in the open-mouth shape (side
    teeth swung into the gap, front teeth stayed apart); the upper incisor
    edges sat above the lip line, and the open-mouth shape also pulls the
    upper lip down, so the upper lip buried them.
  - Now the teeth are rigid: the upper row stays with the skull and follows
    the upper lip's edge down (never up); the lower row and tongue follow
    the chin and lower lip as one solid piece (a best-fit rigid motion per
    shape: 25 degrees at full open). Teeth drop 5.3 mm so the incisor edges
    sit 3 mm under the lip line. Rows are told apart by how far each tooth
    dropped in the original refit (by centre height, long front teeth
    landed in the wrong row); the 52 gum faces joining the arches at the
    back are removed.
  - The demo caps the mouth shapes at 0.7 (`RAC_SPEAK_MAX`): past that the
    face's mouth corners tear. Still rough: dark streaks baked onto the
    inner edge of the lower lip.
- 2026-11-01: short forearms found (`evidence/raider-forearm-check.jpg`).
  At the same figure height the model's hands end at the belt, about 9% of
  his height above the reference's. The reference has a stretch of bare
  forearm and a long gauntlet cuff between the rolled sleeve and the hand;
  the model has neither. The hand placement followed the whole-body
  acquisition's glove, whose forearm was already short, and the gauntlet
  sits inside the sleeve. Needs a modeling fix and a re-rig.
- 2026-11-01: forearms v2 on the production mesh (`evidence/raider-forearm-check-v2.jpg`,
  `evidence/raider-forearms-v2.jpg`, `prod/raider_hero_production-v2.glb`,
  `lengthen_forearms.py`). Measured on the reference at 1.25 mm a pixel:
  shoulder to fingertip 64 cm (58 cm here), elbow to wrist 24 cm (18.8 cm
  here), about 6 cm of bare forearm and an 8.7 cm gauntlet cuff under a
  sleeve ending about 8 cm past the elbow (15 cm here).
  - Each hand moves 5.2 cm out along the forearm (shoulder to fingertip now
    63 cm); the rolled cuff lifts 3.5 cm as one piece, the plain sleeve above
    it compressing; a skin tube fills the sleeve opening and narrows to the
    wrist (curved taper; a straight one read as a funnel); a 4 cm flared
    leather cuff rises from 3.5 cm inside the glove. Tube and cuff are
    painted from one real texel each (the arm's skin, the glove's cuff): a
    median of UV coordinates landed between islands, and jittered texels
    read as a patchwork. 76,766 faces before the face swap.
  - Tried and changed: a 5 cm cuff lift opened the cuff; sleeve centres
    from a 1.5 cm slab put the forearm against the sleeve's edge; parts of
    the cuff beyond 10 cm from the axis stayed behind and tore.
  - The forearm is one flat skin tone; the reference's has painted shading.
- 2026-11-01: forearms v3 (`evidence/raider-forearm-check-v3.jpg`,
  `evidence/raider-forearm-closeups-v3.jpg`, `evidence/raider-forearms-v3.jpg`,
  `prod/raider_hero_production-v3.glb`). Mark on v2: "not attached to the
  rest of the arms correctly", and the forearm was a flat tone.
  - The forearm and gauntlet cuff now carry the reference's own painting of
    those parts: strips along his right forearm in the reference, copied
    into unused hand-atlas space (u 0.69-0.88, v 0-0.125, with matte
    roughness), wrapped so the front shows the front and mirrored for the
    left arm. The glTF exporter kept embedding the imported originals until
    the saved PNGs were loaded as fresh images on the material.
  - The join: the forearm starts 1 cm inside the cuff's slanted edge per
    direction, at 78% of the sleeve's inner radius there, and a dark lining
    spans the opening from the sleeve wall to it. Tried and dropped: a round
    tube (poked out one side, showed the hollow sleeve on the other); a top
    ring sized to the rolled cuff (wider than the sleeve above it, so it
    poked through); squeezing the top ring to the sleeve wall by ray casts
    (crumpled it). A sliver of lining still shows at the left cuff's edge.
- 2026-11-01: forearms v4 (`evidence/raider-forearm-square-v4.jpg`,
  `evidence/raider-forearm-check-v4.jpg`, `evidence/raider-forearms-v4.jpg`,
  `prod/raider_hero_production-v4.glb`). Mark on v3: "still isn't aligned
  quite properly". Square-on renders of each forearm showed the forearm
  leaving the cuff off-centre and running at an angle into the gauntlet.
  - Measured: the sleeve's own centreline (centres of two slices of its
    lower part, re-sliced square to the estimate four times) runs about 12
    degrees off the landmark forearm, and the hand-only acquisition's glove
    top sat 4.8 cm (left) and 6.1 cm (right) off it, pointing 14-16 degrees
    away. Moving the hand along the landmark line kept that offset.
  - Each hand now turns about its glove top and moves onto the sleeve's
    centreline, 5.2 cm further out. Its side-to-side line follows the
    sleeve; its forward tilt stays the landmark arm's, so the forearm hangs
    in the front plane as in the reference (following the sleeve fully, 16
    degrees towards the camera, foreshortened it). Turns: 3.8 (left) and
    9.3 degrees (right).
  - Measuring the sleeve with a principal-axis fit of one slice picked the
    direction across the cuff, not along it.
  - Still visible: the left glove's thumb sticks out as a flat bar (the
    left hand is the right one mirrored); a sliver of lining at the left
    cuff.
- 2026-11-02: forearm and hand reconstruction (`scripts/revamp/raider/place_hands.py`,
  `scripts/revamp/raider/prep_production.py`, `scripts/revamp/raider/lengthen_forearms.py`,
  `assembled/raider-v13.glb`, `prod/raider_hero_production.glb`,
  `evidence/raider-forearms-v4.jpg`, `evidence/raider-forearm-check-v4.jpg`,
  `evidence/raider-forearm-square-v4.jpg`, `evidence/raider-hands-v2.jpg`).
  - Mark rejected forearms v4 ("this looks so wrong still"). Root-cause
    audit traced the defect to a two-stage failure chain:
    1. **Stage 1 (`place_hands.py` caused T-Rex arms):** the hand-only
       acquisition (`raider-hand-r.glb`) already contained the full 8.7 cm
       sculpted leather gauntlet welt (`T in [-0.067, +0.015]`) and bare
       forearm (`T in [-0.140, -0.067]`), but the script's HSV skin detector
       misclassified bright highlights on the brown leather gauntlet as
       "skin". Taking `np.percentile(t[skin], 8)` (`T = +0.0327`) sliced off
       the entire 8.7 cm leather gauntlet and bare forearm right above the
       wrist strap, and `WRIST_OVERLAP = 0.035` then pushed that truncated
       wrist 3.5 cm inside the rolled sleeve—shortening both arms by ~6 cm
       and burying the wrists inside the cuffs.
    2. **Stage 2 (`lengthen_forearms.py` broke the geometry trying to patch
       Stage 1):** instead of restoring the sculpted gauntlet and forearm in
       `place_hands.py`, `lengthen_forearms.py` pulled the rolled sleeve cuff
       up (`SLEEVE_UP = 0.035`), pushed the truncated hand out, and bridged
       the gap with two procedural `tube()` cylinders. That left the rolled
       sleeve hollow and torn, the bare-skin cylinder off-centre and too
       thin, the gauntlet cuff a floating grey cylinder with a skin gap above
       the palm, and a flat bar spike on the left pinky where vertices beyond
       `r = 0.12 m` were left behind during hand rotation.
  - Fixed directly in `place_hands.py` and `prep_production.py`:
    - `place_hands.py` now cuts `raider-hand-r.glb` at `T_CUT_H = -0.105`
      (preserving 100% of the gloved fingers, wrist strap, 8.7 cm flared
      leather gauntlet welt, and bare forearm), scales by `S = 0.195`,
      aligns each hand coaxially (`15.71` and `15.04` degree turns) with the
      unbiased forearm axis measured from non-boundary outer forearm slices,
      removes the synthetic 6 mm inward boundary skirt on `raider_body`'s
      `skin` part (`fn . r_hat <= +0.47`), inserts planar crease rings at
      `tb = -0.1180`, `-0.1165`, and `-0.1145`, and smoothly morphs the bare
      forearm (`t_rel in [-0.038, 0.0]`) into the 360-degree rolled sleeve
      cuff bore with a clean circular shadow crease under the cuff lip.
    - `prep_production.py` welds coincident UV-seam vertices
      (`remove_doubles(dist=1e-5)`) before `DECIMATE` and recalculates face
      normals afterward, eliminating UV-seam splitting cracks on the 75,996-face
      hero-tier production mesh.
    - `lengthen_forearms.py` is updated to verify the reconstructed forearm
      and hand dimensions (`shoulder_to_fingertip_m = 0.735`,
      `hand_and_forearm_span_m = 0.402`) without destructive cylinder surgery.
- 2026-11-02: rebuild v2, reproducible (`scripts/revamp/raider/build_raider.ps1 -Run v2`,
  `build/v2/final/raider_hero_rigged.fbx`, `evidence/raider-v2-final.jpg`,
  `evidence/raider-v2-rig.jpg`, `evidence/raider-v2-face.jpg`).
  - Mark passed Argon's forearms on the model and asked for everything on
    main, looking good and reproducible. Argon had written the assembled and
    production meshes in place, so the rig, face, shoulder and mouth fixes,
    the finals and the speech demo were still on the old arms, and
    `prod/raider-landmarks-fingers.json` was bound to an intermediate mesh.
  - Rerunning `place_hands.py` and `prep_production.py` from the recorded
    inputs reproduces both meshes vertex for vertex with identical textures
    (the GLB bytes differ only in packing).
  - `build_raider.ps1` now runs the whole chain from those inputs into one
    run folder and overwrites nothing outside it: hands, production mesh,
    landmarks, fingers, rig, MakeHuman skin, face (`face/bake-v15`),
    shoulders, mouth, gate and deformation, renders and speech. The speech
    line and its alignment, until now one-off commands, are
    `speak_line.ps1` and `align_visemes.py` (same 59 visemes, same 0.7161
    scale).
  - Run v2: gate passes (86 bones, 76,581 triangles, hero tier 80k, 4
    influences, 0 unweighted); deformation suite 5 poses pass; the new
    forearms and gauntlets bend with the elbows and fists close as before.
    Known limits unchanged: the overhead test pose lifts the collarbones only
    15 degrees, so the head reads sunk; the lower lip's inner edge is rough.
  - The repository's lint now covers these scripts: one statement per line
    (split mechanically, kept only where the parsed program was identical),
    and `scripts/revamp/*` gets the Blender stages' E402 allowance.
- 2026-11-02: look v4 (`build_raider.ps1 -Run v4`, `evidence/raider-v4-before-after.jpg`,
  `evidence/raider-v4-face.jpg`). Mark: "there are some obvious flaws still".
  Found by side-by-side with the reference, in paint and clay:
  - Chrome plates and lacquered skin: `obj_to_glb.py` wired every metallic
    or roughness map as a packed glTF map, so the greyscale roughness map
    from `calibrate_pbr.py` (wired last) set metallic too. The body was 71%
    and the head 80% metallic. Fixed at the source (separate maps drive
    their own input), and `fix_pbr_maps.py` rebuilds the packed map from
    the calibrated pair for meshes packed before (it checks the pair's
    roughness matches the material texel for texel): 6% and 10% now.
  - Plates painted near-white: `tone_metal.py` tones plate and knee-pad
    texels (and the back plate, which the part map labelled jacket: its
    light grey texels) to the reference's iron, darkened 20% for render
    light, keeping each texel's relative brightness (scratches, rivets)
    and the leather rims' colour; roughness and metallic 0.55 there.
  - A 16 cm slit in the jacket below the back of the collar (from the head
    placement; the face's neck showed through): `fill_holes.py` closes the
    open loops in that box with UVs fitted from the loop's own. A dark lip
    from the old paint remains along it.
  - Glowing cyan eyes: the iris was MakeHuman's pale grey; `look_face.py`
    blends the CC0 grey and light-brown eye textures and darkens the iris.
  - Red, over-saturated skin and orange ears (hue 19 against 22 degrees,
    saturation 0.64 against 0.50): skin-like texels of the baked face are
    desaturated 20%, turned 3 degrees and lifted 8%; the face material goes
    from roughness 0.6 to 0.8 (a grey sheen sat on the dark hair).
  - Run v4: gate passes (86 bones, 76,664 triangles), deformation 5 poses
    pass. `build/v3` is a stale rerun of the v2 chain and can be ignored.
