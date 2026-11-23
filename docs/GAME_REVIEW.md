# Game review road

*Type: reference*

The paved road from a polished character GLB to that character playable in the game, with fixed closeups in the
game's own light. One recipe, one command, a new attempt folder each time. It was paved from Remora's first trip
into The Aether Wars (2026-11-06/07, `work/remora-airship-20261106/game86`), and every fix that trip needed is a
default here.

It is a **review**: nothing here is production-ready, the saved player Blueprint, level and default character are
never changed, and a failed production rig gate is recorded rather than waived. Mark judges the closeups and the play
session; numbers in the receipt support that judgement and never replace it.

## One command

```powershell
.\scripts\run_game_review.ps1 -Recipe .\work\<asset>\game-review.json -OutputDirectory .\work\<asset>\game\attempt01 -Play
```

- `-ReuseFrom <earlier attempt>`: take steps 01-04 from an earlier attempt when nothing they read changed (same
  source hash, materials, bind, head weights, scatter mask, baked morphs). A look-only change then takes minutes.
- `-Compare <earlier attempt>`: also writes `07-closeups/compare.jpg`, BEFORE above AFTER, face and body.
- `-Through finish|export|unreal`: stop early (the Blender half runs while the game is open).
- `-Poses`: also shoot a pose sheet (bind, idle, walk, jog, attack, jump; front, three-quarter, side, back) and
  both hands up close (relaxed, and in the attack's fist) for judging the body rig: `07-closeups/poses.jpg`, and
  pose rows in `compare.jpg`.
- `-Motion`: also sample every animation the player uses (montages split into their clips) at 15/40/65/90% from
  the three-quarter and side views: `07-closeups/motion.jpg`. A montage with an empty clip, which would play
  nothing, is flagged at the top.
- `-Face`: also hold the game's own face component in each expression it plays (none, idle, combat, hurt, climb,
  hang, glide, and the lids shut) and each lip-sync mouth shape (Rhubarb's X and A-H), from the front and the
  three-quarter: `07-closeups/face.jpg`, and `face-compare.jpg` with `-Compare`. Any morph name the face drives (or
  the recipe's gains name) that the mesh does not carry is flagged at the top: the game skips a missing morph silently.
- `-Baseline`: also shoot the game's own hero, unswapped, through the same animations at the same frames, and write
  `07-closeups/motion-compare.jpg`: the hero above the character, clip by clip (implies `-Motion`).
- `-Play`: after the closeups, open the game with the character on the player pawn and leave it open;
  `-PlayLook <look>` plays with a named look's materials. She says the game's lip-sync demo line
  (`VL_LipSyncDemo`) at the face close-up after 9 s, and again whenever **L** is pressed.

The game and editor must be closed for steps 06-07; the script refuses rather than closing them. The first run on a
machine needs Manny's reference pose (Epic's content, kept in `work/`, never committed):

```powershell
UnrealEditor-Cmd.exe <project>.uproject -run=pythonscript -script="scripts\ue5\dump_manny_reference.py work\_unreal"
```

## Steps

| Folder | Script | What it does |
|---|---|---|
| `00` | `reference_asset_compiler.game_review resolve` | Validates the recipe, fills every default, hashes the source: `job.json` is what every step reads. |
| `01-single` | `scripts/blender/game_review_single_mesh.py` | Joins the meshes; bakes glTF rest morph weights (and `bake_morphs`) into the basis, keeping every morph delta. Checks height and skin slots. With `closed_lids.clear`, repaints the lid skin a blink uncovers (`scripts/blender/clear_closed_lids.py`, below). With `mouth.fit`, seats the teeth under the lips and lets the tongue ride the jaw (`scripts/blender/fit_mouth.py`, below). |
| `02-landmarks` | `derive_humanoid_landmarks.py`, then `scripts/blender/fit_hand_landmarks.py` | The landmark route's joints, with the finger and metacarpal joints refitted to the mesh's hands: each hand's frame (fingers, knuckle line, palm), size and centre measured, then Manny's hand placed by a bounded fit that keeps every joint inside the hand without folding the fingers into the palm. Refused (landmarks kept) unless more joints end up inside. `hand_fit: false` skips it. Overlays in `02-landmarks/hands/`. With `arm_joints: measured` the landmark step finds the elbow and wrist on the arm itself instead of placing them by template (below); how each was found is in `humanoid-landmarks.json` and the receipt's `arm_joints`. |
| `02-rig` | `scripts/run_rig_candidate.ps1 -Profile ue5_manny -Backbone landmark` | Landmark skeleton + heat weights. The production gate usually fails on triangles and UVs; that is recorded in `game-review.json` and the review goes on. |
| `02b-bind` | `scripts/blender/game_review_bind.py` | Heat weights on a watertight voxel stand-in of body and outfit (hair, eyes and mouth left out), copied to every vertex from the nearest stand-in surface. Layers that lie together move together. `bind.method: rig` keeps the rig's own weights. |
| `03-manny` | `scripts/blender/manny_axes.py` | Manny's bone axes (torso frames exact), joints and rest mesh unmoved (< 0.1 mm). Without it every Manny clip rolls forearms and knees. |
| `04-finish` | `scripts/blender/game_review_finish.py` | Rigid head and neck blend from the measured chin; under-hair scatter mask; hair sway shapes; `neck-pose.png` (head turned and tilted, rendered at the jaw) and `hair-sway-*.png` (each sway shape at full weight). |
| `05-export` | `scripts/blender/export_game_review.py` | Centimetre FBX with the 100x applied into bones and vertices; textures by slot plus `textures.json`. When a look uses hair shading, also the hair's flow map (below). |
| `06-unreal` | `scripts/ue5/game_review_import.py` | Headless import to `<content_root>/<Name>/<Version>`, materials and look sets, and the animations by `unreal.animation_source`: `player` retargets what the player plays now (the player Blueprint's AnimBP with everything it references, and every montage and traversal slot) from the player Blueprint's own mesh; `manny` retargets Manny's combat AnimBP, montages and traversal clips. Player animations with no Manny source come through a second retargeter from the character that owns them (`unreal.secondary_source_mesh`; for The Aether Wars, Character02's Aether push, left push and recall), built the installer's way in the review's own folder. With `unreal.retarget_pose` the Manny retargeter is built here (the installer's way) and calibrated before the batch; `unreal.gait_style` then rewrites the matching retargeted clips (`scripts/ue5/retarget_calibration.py`, below). |
| `07-closeups` | `scripts/ue5/game_review_play.py` + `scripts/game_review_sheet.py` | In game: idle frozen at 1 s, face front / three-quarter / low per look, body front / three-quarter / side / back; labelled `closeups.jpg`. Both modes put the recipe's lip-sync gains on the player's face component and its `unreal.climb_reach` on the climbing component. |

`game-review.json` in the attempt is the receipt: per-step exit codes, times and logs, the rig gate's failures, the
finish report (chin height, neck chain, what carries the chin, masked vertices), FBX hash, import summary and the hash
of every closeup.

## Recipe

```json
{
  "schema": "reference-asset-compiler.game-review-recipe.v1",
  "name": "Remora",
  "version": "V2",
  "source": "../face89/skin/Remora_Skin.glb",
  "source_sha256": "<optional; refused if it differs>",
  "skin_materials": ["skin", "Remora_Neck15"],
  "looks": {
    "hair_matte": {"hair": {"roughness": 0.72, "specular": 0.1}}
  }
}
```

Optional fields, each with the default that Remora needed:

| Field | Default | Why |
|---|---|---|
| `hair_materials` | names containing `hair` or `scalp` | The scatter mask and hair look follow these. |
| `rigid_head_materials` | `hair scalp eyes Eye_Lashes Eye_Occlusion teeth tongue Mouth_Interior` (substrings) | Ride the head bone alone; expressions are morphs, so nothing is lost. |
| `hand_fit` | `true` | The landmark route drops Manny's hand in by forearm direction alone; Remora's finger joints sat 2-18 mm outside her hands. |
| `arm_joints` | `measured_shoulder` | `measured` finds the elbow where the arm's centreline bends and the wrist just past the forearm's thinnest girth, the same share of the arm on both sides (below). `measured_shoulder` does that and also finds the shoulder joint in the shoulder instead of at a share of the height (below). `template` is the original placement, kept so earlier builds repeat: it put Remora's elbow joint 8 cm below her elbow and her shoulder joint 2 cm below the middle of her shoulder and 2 to 5 cm outside it. Mark passed `measured_shoulder` on Remora V25 and it is the default. A change needs a fresh rig (steps 01-04). |
| `bind` | `{"method": "voxel_heat", "voxel_m": 0.006}` plus the three weight fixes below (hip release, layer follow, armhole hold) | The rig's own heat bind fails on a layered character and falls back to envelope capsules. `method: rig` keeps the rig's weights and none of the fixes below apply. |
| `bind.shoulder_release_cm` | off (0), opt-in | The stand-in heat leaves the top of the upper arm on the collarbone (Remora: 63% in its first fifth, 21% in its second), so a raised arm lumps at the shoulder, sags at the armpit and stretches the upper arm thin ("stringy", Mark on V13). Past the shoulder joint, collarbone and upper-spine weight moves to the upper arm, faded in along the arm over this distance, by how much of the vertex is already arm and by distance from the arm's axis (a hard edge tore the tunic's armhole). Remora V14: 4. Bent elbows are unaffected. Evidence: `work/remora-run-20261109/shoulder/`. **It made up for a shoulder joint placed too low** (the top of the upper arm was above the joint, so it was the collarbone's): with `arm_joints: measured_shoulder` leave it off, as Remora V25 does. |
| `bind.armhole_hold_cm` | 4 (0 turns it off) | A sleeveless outfit modelled in one surface with the body takes the arm's weights around its armhole, so the armhole wings out with a raised arm and the flank tents up after it (Remora hanging from a ledge: the tunic's shoulders stood out like caps). On: the arm's own surface is told from the outfit by colour (what has the tint and brightness of the free upper arm and is joined to it), the outfit gives its arm weights back to the torso, and the arm's own skin is held where it lies against the held outfit and let go over this distance (below). A sleeved arm is detected and left alone. Mark passed it on Remora V25 ("Looks right", 2026-11-10) and it is the default. |
| `bind.hip_release_cm`, `bind.hip_release_take` | 20, 0.75 (0 turns it off) | The stand-in heat gives the buttock to the thigh (Remora: 69-98% thigh from 8 cm above the hip joint down, 6-23% pelvis), so it rides the leg: seen from behind in a run it balloons into a faceted lump when the knee lifts and creases when the leg goes back (Mark on V19; present with no hip sway at all, so not the gait layer). On the back of the hip, `take` of the thigh's weight moves to the pelvis at and above the hip joint, fading out over this distance down the thigh and toward the front of the hip. A 9 cm blend only moved the crease down; 16-22 cm bends smoothly. The release reaches 7 cm ahead of the hip joint (V20 stopped 3 cm ahead and the outer hip still bulged). Mark passed it on Remora V22 ("that looks really good", 2026-11-09) and it is the default. Evidence: `work/remora-run-20261109/hips/`. |
| `bind.layer_follow_mm` | 20 (0 turns it off) | Outfit layers a few millimetres apart get slightly different weights from the stand-in (each samples its own nearest point), and any leg lift pushes the under layer through the upper one: Remora's trousers came through the tunic's front panel as jagged dark triangles in every run frame (Mark on V20; there in V19 too). 11,700 of her outfit vertices sit under another outfit layer at a median 4 mm. On: an outfit vertex whose outward normal meets a covering outfit surface within this distance takes that surface's weights where it meets, so the two move as one. The cover is another connected piece, or the same piece wrapped over itself (her crossover tunic is one piece); the search passes through a flap's own lining and stops at skin. Covered vertices keep up to **eight** influences: trimming the copied blend to four put the marks straight back (V21). Dead ends: the cover riding the layer beneath (a flap has too few vertices to carry what it covers), and tucking covered vertices 3 mm inward (it also sank tunic that sits under the belt). Skin, hair and rigid head parts are left alone. Mark passed it on Remora V22 and it is the default. Test poses and renders: `work/remora-run-20261109/tools/hip_pose_test.py`. |
| `bake_morphs` | `{}` | A face variant picked in review, baked into the basis and removed (`{"rac_lids_soft": 1}`). |
| `head_weights` | head 5 mm, neck_02 35 mm, neck_01 70 mm, untouched 90 mm below the chin (scaled by height / 1.7 m) | The envelope rig hung the chin a quarter on the spine; it stepped whenever the idle tilted the head. |
| `scatter_mask_m` | `[0.02, 0.05]` | No skin scatter within 2 cm of hair, full by 5 cm. |
| `skin_look` | subsurface, saturation 0.82, albedo 0.92, specular 0.35, scatter 1, scatter mask on | Flat orange paint read sunburnt in warm light; the mask stops the hairline glow. |
| `hair_look` | hair shading, roughness 0.55, specular 0.3, scatter 0.5 | Default-lit hair read plastic (and at Unreal's specular 0.5, wet); Mark picked hair shading along the strands on Remora. |
| `hair_motion` | on; sway 3.5 cm, lift 2.5 cm, still within 1 cm of skin, free from 9 cm | Loose hair in front of the ears moves when she does (below). |
| `teeth_look` | albedo 1.6, roughness 0.35, specular 0.45 | The game installer's own teeth for Remora. The stock MakeHuman teeth texture at 1x read grey-brown with black gaps in the game's shadowed mouth. |
| `closed_lids` | `{"clear": "auto"}` | Repaints the lid skin a blink uncovers (below); Mark passed it on Remora. `auto` skips a head without closure morphs and records why; `true` requires it, `false` turns it off. Settings `stretch`, `seen_open`, `lash_band_m`. |
| `mouth` | `{"fit": "auto"}` | Seats the teeth and tongue (below); Mark passed it on Remora. `auto` skips a head without teeth or a jaw morph and records why; `true` requires it, `false` turns it off. Settings `show_m` (incisor edge below the lip line, 1 mm), `tongue_follow` (0.85), `max_shift_m` (8 mm), `rest_tolerance` (0.01). |
| `face` | `{"mouth_morph_gain": {}}` | This face's lip-sync gains (the face component's `MouthMorphGain`, morph -> gain); empty keeps the game's table, which was tuned on another face. Set at runtime, so a gain change reuses steps 01-04. |
| `looks` | none | Named alternatives (`skin`, `hair` or a slot name -> settings), shot side by side; at most six. |
| `height_cm` | `[150, 200]` | Refuses a 1.7 cm or 17 m import before anyone looks at it. |
| `manny_refpose` | `work/_unreal/manny_refpose.json` | |
| `unreal.animation_source` | `manny` | `player` gives the character the game hero's own animation set, retargeted from the player Blueprint's mesh. Since the game's Manny-first reset (2026-11-07) the hero plays Manny's clips too, and `player` falls back to `manny` while Character02's `library_anims` is off. Remora V12 (`player`, built before the reset) wore Character02's old library set copied twice: hunched run, flung arms, twisted walk (Mark, 2026-11-09). |
| `unreal.retarget_pose` | none (the installer's exact copy) | The character's own calibration of the Manny retargeter: `clavicles` (`manny` or `own_rest`), `clavicle_drop` (degrees), `pitch` (spine/neck bone -> degrees, + forward). Remora V13: `own_rest`, no drop, spine_01 -3, spine_03 -3, spine_05 -1, neck_01 -2. Manny source only. |
| `unreal.glider_grip` | `false` | The Sailwing hangs from `spine_03` at the hero's flight offset, placed for Character02's hands; on Remora the hands stopped a few cm under the handles, open, uneven, wrists bent back (Mark on V14). On: the glider is moved for this character (the mean miss between her fist centres and his grip points, in the socket's frame; Remora 8 cm lower) and her glide clip is fitted per frame: her fist centre onto his grip point with his grip orientation (two-bone IK, elbow kept on its side) and his fist relative to the hand. The play script hangs the glider at the recorded offset. Remora V15; evidence `work/remora-run-20261109/glide-v15/`. Her right arm is up to 2.5 cm short at one moment of the loop. |
| `unreal.climb_reach` | none (the hero's numbers) | Where the game's climbing component holds her body so her hands meet walls and ledges: `hang_feet_below_lip` (hero 207 cm), `hang_distance` (82), `wall_distance` (62); any left out keep the hero's (below). Remora V25: 195, 75.5, 56.5 (V24, before the shoulder joints moved: 191, 76, 55.5; V23, on its misplaced arm joints: 193.5, 74.5, 57). Set at runtime, so a change reuses steps 01-04. |
| `unreal.gait_style` | none | Clip name pattern (first match wins) -> `hip_roll`, `hip_yaw`, `hip_shift` (scales, 0.5-3), `narrow_cm` (0-6), `swing_clear` (0-1), `arm_in` and `upright` (degrees), `elbow_bend` (scale, 0.5-1.2). Remora V13 is Mark's pick F (below). Manny source only. |
| `unreal` | The Aether Wars: project, level `/Game/MCP/L_AetherVault_MCP`, content root `/Game/RAC/GameReview`, player Blueprint, pawn class, walk key | Only this game is wired: its installer (`Tools/CharacterInstall.py`), animation slots and traversal clips. `project` defaults to `Documents/Unreal Projects/TheAetherWars/TheAetherWars.uproject` under the signed-in user's home and `engine_dir` to Epic's default UE 5.8 install; `RAC_GAME_PROJECT` and `RAC_UNREAL_ENGINE_DIR` move them for a workstation, and a recipe may name either. |

Look settings: `roughness`, `specular`, `normal_strength` (0 drops the normal map), `saturation`, `albedo`,
`base_tint` `[r,g,b]`, `subsurface`, `scatter` (skin: scatter amount; hair shading: the hair model's scatter),
`scatter_mask`, `roughness_from_texture`, `specular_from_base` (specular scaled by each texel's brightness against
the map's mean, capped at 3x), and `shading: "hair"`.

**Hair shading.** `"shading": "hair"` gives a hair slot Unreal's hair shading model, whose highlights run along the
strands instead of spreading as one broad lobe (what made Remora's hair read plastic). It needs to know which way the
hair runs. The hair is a shell whose UV atlas is hundreds of small charts, so the export works the flow out on the
mesh (outward and down from the crown across the surface, smoothed over neighbours), writes it per face corner in the
UV tangent frame and bakes it into the hair's own UVs as `<slot>__flow.png`. The material flips its green for Unreal,
as with normal maps. A cloth (fuzz) look was tried and dropped: the cloth model's amount input is not reachable from
Unreal's Python, so it built with no fuzz at all.

**Hair motion.** Proper hair physics in Unreal is hair bones with a physics node in the animation blueprint, and
Unreal's Python cannot add nodes to an animation graph. So the road gives the loose hair in front of the ears five
sway shapes (left, right, forward, back, lift; still at the roots, free at the tips), and the play script runs a
damped spring per axis from the head bone's acceleration in the mesh's own axes: the tips lag when she starts,
stops, turns or lands, then settle (about 1.3 Hz, a little bouncy). It runs in the review's play session only, like
everything else here; for the shipped game the same idea belongs in the animation blueprint (hair bones plus a rigid
body or AnimDynamics node). The braid and the hair on the crown stay on the head.

**Face pass.** The game's face component (`UAetherFaceComponent`) drives MakeHuman expression morphs by name: random
blinks, an expression per situation (idle, combat, hurt, climb, hang, glide) and lip-sync from Rhubarb mouth shapes.
`-Face` uses the component itself, not a copy of its tables: an expression goes into its idle slot (the one it plays
at rest), the lids by a blink held open-ended, a mouth shape by a one-cue line a minute long; random blinks and eye
flutter are stopped for the shots. `done.json` records the weights each state settles on. Mouth shapes are shot over
the idle face, as the game speaks over it.

**Closed lids.** A head painted from reference views carries the reference's lashes and liner on the lid margin. Open,
that skin is folded into the crease; a blink unfolds it across the eye and the paint stretches into a dark smear
(Remora V9). `clear_closed_lids.py` (on by default) finds that skin from the mesh: skin triangles that grow when the closure morphs
are at 1 (`stretch`, area shut over open) or that face the camera far more shut than open (`seen_open`, they slide
down edge-on). Their texels are refilled from the unmoving lid skin around them (darker texels such as brows and
liner wings are not sources); a band at the lid margin found from the lash-card roots (`lash_band_m`) keeps its paint.
What shows with the eye open is kept, so liner that shows open still shows shut, along the bottom of the lid. The lash
cards are not touched. It also removes lash strokes painted above the open lash line, which doubled the lash cards.

**Mouth fit.** A template head refitted to a picture keeps the template's teeth where they were. Remora's upper
incisor edge sat 4.5 mm above the line where her lips meet, so in every open mouth shape only the lower row showed,
under a dark gap, and the tongue (which no morph moved) hung under the upper lip as a jagged pink shape.
`fit_mouth.py` (on by default) measures, from the jaw morph itself, which teeth ride the jaw and where the lips part (the upper lip
stays, the lower lip drops), then moves the teeth and tongue by one vertical offset so the upper incisor edge sits
`show_m` under that line, in the basis and every key alike. The tongue takes the lower teeth's motion in every morph
that opens the jaw. It counts teeth and tongue seen past the lips at rest from the front and both three-quarters,
before and after, and refuses (mesh untouched) if the fit shows more than `rest_tolerance` of them.

## Retarget pose and gait style

The game's installer offsets the target retarget pose to Manny's reference rotations bone for bone, so a clip copies
Manny's joint angles exactly (its verification reports under 0.01 degrees). On a body built differently that exact
copy is the flaw: it shrugged Character02's shoulders about 10 degrees above his modelled rest and tipped Remora's
torso about 5 degrees further forward than Manny's, with her head jutting. `unreal.retarget_pose` corrects the
retargeter itself, so every clip, montage and traversal clip carries it:

- `clavicles: own_rest`: the collarbones keep the character's modelled rest (no offset) and the upper arms are
  re-offset so the arms still hang in Manny's direction (Character02's candidate B, 2026-11-07). `clavicle_drop`
  lowers them further. To pick it, compare shoulder joint height below neck_01 as a share of height with Manny's
  idle (-5.2%): Remora's own rest already gives -5.1% (drop 0); Character02 needed 8 degrees.
- `pitch`: tilts spine and neck bones back to Manny's lean. Remora: idle lean 10 -> 5.6 degrees (Manny 5.3), head
  25 degrees ahead of the neck (Manny 23).

`unreal.gait_style` is a per-frame layer on the retargeted clips whose source name matches a pattern, applied after
the blend space and montage repairs. The pelvis' side tilt and turn about their clip mean are scaled (`hip_roll`,
`hip_yaw`) and its side-to-side travel relative to the root (`hip_shift`), with the chest held; the legs are re-solved
by two-bone IK so each foot lands where it did, moved `narrow_cm` toward the midline, sole unchanged; `arm_in` turns
the upper arms toward the body; the IK bones the retargeter pins to hands and feet follow. Keep `narrow_cm` to the
straight forward walk and jog: side, diagonal and backward steps already cross, and narrowing them stacked
Remora's knees and crossed her boots (V15). A planted foot keeps the full offset; the foot in the air swings out by
the same amount as it passes the planted one (`swing_clear`, default 1), so the pair keep their stock gap at the
pass. Judge the gap against the footwear: Remora's boots are about 12 cm across; a constant 3 cm left 5.9 cm
between her feet at the pass (boots through each other), a constant 1.5 cm 8.7 cm, and 2.5 cm with the swing
11.0 cm (V17). `elbow_bend` scales the elbow's bend about its own hinge: Remora's short
forearms carry Manny's jog hands about 4 cm closer to her face than his, and from the front they covered her mouth;
0.85 on every jog puts them 6-7 cm further off, at chest height (V18). Measure before blaming a cause: the hand never
came nearer than 21 cm to her mouth, and `arm_in` was not involved. `upright` stands the chest back up where a stock
clip hunches (her backward walks leaned 10.5 degrees against the forward walk's 6: 4.5 on `MF_Unarmed_Walk_Bwd*`).
`finger_relax` blends the fingers toward the character's own relaxed hand, taken from her retargeted `MM_Idle`:
Manny's spread fingers in the jump and fall read as claws on her (0.7 on `MM_Jump`, `MM_Fall_Loop`, `MM_Land`, with
`arm_in` 14 and 22 lowering upper arms that sat 61-67 degrees off her sides; V19). Each styled clip is tagged
`RACGaitStyle`.

Remora V13, Mark's pick F (2026-11-09), from candidates S (calibration only) and F built and shot side by side in
`work/remora-run-20261109` (sheets, `remora-run-motion.mp4`, `tools/`): walks hips roll 1.8, yaw 1.2, shift 1.5,
arms in 5; jogs roll 1.6, yaw 1.15, shift 1.4, arms in 6; narrow 2.5 cm on the straight forward walk and jog only
(V17; V13-V15 narrowed every direction by 3 and 2.5 cm); idle narrow 2.5 cm, arms in 4.
Her run went from 36 to 18 degrees of lean and 37 to 15 degrees of arm spread; step width 21 -> 6 cm. Real feminine
gait differences are modest: from a third-person camera, a strong hip sway reads as parody. Raise the scales only
after watching it in motion.

The arm operations depend on where the arm joints are. `arm_in` on the idle, walks and jogs and `elbow_bend` on
the jogs were tuned on V13-V18's template arm joints, where the elbow joint sat mid-forearm ("short forearms"
above were a 17.5 cm forearm bone on a 22 cm forearm). With the joints measured (V24, below) the same numbers put
her hands on her thighs in the idle and against her hip in the jog, so V24 drops them on those clips; the jump's and
fall's `arm_in` stay. Shoot `-Poses` again after any change to the arm or shoulder joints, and look from the side
before believing a front view: from the front her forward-swinging jog hand lines up with her stomach while it is
20 cm in front of it.

## Arm joints

The landmark step's original arm placement never looks for the elbow. It takes the wrist as 10.5% of the height back
from the far end of the arm and puts the elbow halfway to a template shoulder. On an A-pose arm that is wrong by
centimetres: Remora's elbow joint sat 8 cm (left) and 4 cm (right) below her elbow, her left wrist joint was in her
palm and her right one up inside the bracer, and the two arms did not match (upper arm 27.5 and 25.5 cm, forearm 17.5
and 16.3; Manny's are 27.8 and 27.3). Every animation bent her forearm while the mesh's own elbow stayed as a fixed
kink above the bend. Mark, playing V23 on 2026-11-10: "like there's an extra bone, or they're just super long". Her arm
mesh is a normal length; only the joints were off.

`arm_joints: measured` (`derive_humanoid_landmarks.py --arm-joints measured`) measures both joints on the mesh:

- The arm is sliced every centimetre from the template shoulder joint to the fingertip, over points sampled across
  the faces (a low-poly limb has too few vertices per slice). Each slice keeps what is joined to the arm's outer
  surface, so the torso or a thigh beside it is left out; slices above the armpit, where there is no gap, are skipped.
- **Elbow:** where the centreline of those slices bends. A generated A-pose or T-pose mesh carries a slightly bent
  elbow (Remora's: 20 and 19 degrees), and the best split of the centreline into two straight pieces lands on it. An
  arm with no bend to find (under 5 degrees) takes a body's proportion instead, 56% of the way from shoulder joint to
  wrist, and the landmark file says so.
- **Wrist:** 1.8% of the height past the forearm's thinnest girth, which is where the hand starts to widen.
- **Both arms the same:** each joint is placed at the same share of its own arm's length on both sides, weighted
  toward the side with the clearer bend. Two separate measurements never quite agree, and unequal left and right
  bones play every animation lopsided.

`humanoid-landmarks.json` and the receipt record, per arm, how each joint was found, the arm's own measurement and
the bone lengths. Remora V24: elbows at 19.4 and 19.6 cm from the shoulder joint, upper arm 20.0 and 20.3 cm, forearm
23.7 and 24.0 cm. The hand fit then starts from a hand that is already close; it now also refines from the incoming
joints and keeps the better result, and all 24 finger joints of each hand ended inside the hand (18 and 15 before).

What `measured` does not do: the shoulder joint is still a template position (Manny's height fraction and width).
`measured_shoulder` is the same measurement with the shoulder found too (next section). Check a new character's arms
with `work/remora-arms-20261110/tools/arm_check.py` (joints drawn on the arm, plus the arm bent 90 degrees and held in
a guard) and look at the overlays.

`measured_shoulder` is the default since Mark passed Remora V25 in the game (2026-11-10: "Looks right"). A recipe
that needs an earlier build's joints says `arm_joints: template` or `measured`; a job written before the setting
existed counts as a template rig, so `-ReuseFrom` will not hand a measured build an old rig. A change of setting
moves joints, so it needs a fresh rig, and anything tuned to the old arm lengths has
to be checked again: `unreal.climb_reach` (below), the gait style's arm operations (above) and the glider grip (the
import recomputes it; look at the hands on the handles). Remora's jogs are the example: the opened elbow that kept
her fists at chest height on the template arms (0.85) was dropped for V24 because it brought her hands to her hip,
and without it the true 24 cm forearm pumped her fists up to her face (knuckles 10 cm from her mouth). V25 refits it:
0.75 on the forward jog, measured in the game against V22, the build Mark passed.

## Shoulders

Mark, playing on 2026-11-10: "there is a very clear issue here on her shoulder. when she raises her arms its more
pronounced. looks like its just bending wrong", and of the ledge hang "its not really supposed to bend like that,
right? and her arm is twisting back unnaturally". Two causes, two settings. Remora V25 uses both; Mark passed it in
the game the same day ("Looks right") and both are now the road's defaults.

**The joint was not in her shoulder.** The template puts the shoulder joint at Manny's share of the height and of the
width. On Remora that was 2 cm below the middle of her shoulder and 2 cm (right) to 5 cm (left) outside it, the left
one 1.5 cm under her skin, at the end of 16.7 cm collarbones. The whole cap of the shoulder was then the collarbone's (it lay above the joint), the arm hinged underneath
it, the upper arm bone (20 cm) was shorter than the forearm (24 cm), and the bone pointed up to 13 degrees away from
the arm it drives. `arm_joints: measured_shoulder` (`--arm-joints measured_shoulder`) finds the joint on the mesh:

- The upper arm's own centreline is fitted through the arm slices between the armpit and the elbow and carried up
  into the shoulder.
- Walking up it, the joint is the point that is **as far under the top of the shoulder as it is in from its outer
  side** (Remora: 5 cm and 5 cm, which is where a shoulder joint sits). A result under 2 cm or over 10 cm deep, or
  more than 8% of the height from the template, is refused and the template kept, with a note.
- Both shoulders are then set to one height and one depth, each at its own width; one that could not be measured
  takes the other's move from its template, mirrored. The collarbones start either side of the middle of the two
  shoulders, so they come out the same length.

Remora V25: shoulder joints 2.2 cm higher and 2.2 (right) and 4.8 cm (left) further in, upper arm 23.6 and 23.1 cm,
collarbones 13.2 cm each (16.7 before; the rig's midline sits 1.3 cm to one side of her arms, and roots left on it
would have made them 11 and 14 cm), and the upper arm bone within 7.5 (left) and 1.9 (right) degrees of the arm's
own centreline (12.8 and 5.2 before). The landmark file and the receipt record `under_top_cm`, `in_from_side_cm`, how far the joint moved and the
template's upper-arm length. Hair or a pauldron lying over the shoulder is read as its top; look at the numbers.

**The tunic took the arm's weights.** Her body, arms and tunic are one surface (a generated mesh), so heat weights
run smoothly across the armhole: its rim and the tunic beside it followed the upper arm, standing out like caps when
she hung from a ledge and tenting up her flank when she reached. `bind.armhole_hold_cm` holds the outfit to the torso:

- **Whose surface is it.** The mesh has one material for arm and outfit, so the arm's own surface is told by colour:
  the base colour's tint and brightness, read through a blurred copy of the texture, compared with the free upper
  arm (45% to 85% of the way to the elbow), and kept only where it is joined to that arm through more of the same.
  On Remora that is her bare skin, cleanly up to the armhole's edge; her face and neck look alike but are not joined.
  On a sleeved arm it is the sleeve and everything the sleeve joins, which the step detects and leaves alone.
- **The outfit gives its arm weights back** to its other bones (the collarbone if it has none): all of them around
  the shoulder, and anywhere else it stands 6 to 9 cm off the arm's bones (the flank beside a hanging forearm). A
  bracer or glove wraps the bones and keeps its weights; a hand beyond a bracer is all arm and keeps them too.
- **The arm's own skin is held where it lies against the held outfit** and let go over the setting's distance,
  measured straight through space. The armpit's skin then stretches as skin does. Two versions failed first: a hard
  edge tore dark spikes out of the armhole, and a band measured along the surface was used up by the groove under
  the armhole's rim and tore the same way.

It runs after the hip release and before the layer follow, so covered layers copy the held weights. The receipt
(`bind.armhole_hold`) gives, per arm, the size of the arm's surface, how many vertices were held and how much weight
moved, or why a side was skipped. `shoulder_release_cm` is the opposite correction for the low joint and is left off.

Test both before a build with `work/remora-shoulder-20261110/tools/`: `shoulder_check.py` (where the joints sit, who
owns the shoulder's skin, and the arm down, back, forward, out and overhead from four sides, same camera for every
rig), `build_rig.ps1` (the road's rig steps on a copy with the shoulder joints at chosen points), `armhole_hold.py`
and `hold_view.py` (the hold on a built blend, and what it holds in colour). Then judge it in the game on the hang,
the climb, the idle and a jog from behind: the pure overhead test pose is close to the hang (the upper arm swings
120 degrees there and the collarbone only 10).

Still open after V25: the upper arm's twist bones take none of its roll (25 to 30 degrees in the hang and climb, all
of it landing at the shoulder), because retargeted clips leave them at rest and her mesh has no post-process
animation. The skin band now absorbs it; spreading it down the arm needs twist keys baked into the clips and the
upper arm's weights re-split along its length.

## Climb reach

The game's climbing component (`UClimbingComponent`, rewritten 2026-11-09) does not fit hands to surfaces. It holds
the capsule at a fixed spot against the wall or under a ledge's lip, and the traversal clips were authored so the
hero's hands land on the surface from there. Three settings carry that match: `HangFeetBelowLip` 207 cm (feet below
the lip in a hang), `HangDistance` 82 (capsule centre off the face in a hang) and `WallDistance` 62 (the same on a
wall). A character's retargeted clips copy the hero's joint angles, so shorter arms and a shorter torso end short of
the surface: on the hero's numbers Remora's fists sat on the bare wall 13 cm under the lip and 7 cm off it in the
hang, the shimmy and the pull-up, and 5 cm off a wall when climbing (hard to see there).

`unreal.climb_reach` gives the character her own numbers. The play script sets them on the player's climbing
component for the session, like the glider's offset, and `06-unreal/ready.json` records the hero's number and the
one in force for each. Nothing is rebuilt or re-imported for a change, and no game file is touched.

Finding the numbers takes one hero run and one character run of the parkour test gym
(`work/parkour-revamp-20261109/tools`; frames are deleted when the sheets are built):

```powershell
.\run_gym.ps1 -Out hero -Scenarios climb_basic,hang_tap_up,hang_shimmy -Stretch 2
.\run_gym.ps1 -Out her -Scenarios climb_basic,hang_tap_up,hang_shimmy -Stretch 2 -Character <attempt>\job.json
python compare_bones.py hero her
```

`compare_bones.py` prints where the wrists, knuckles, elbows, knees, ankles, toes and head sit against the wall and
the lip in both runs. Lower `hang_feet_below_lip` by how far her knuckles hang under his, and the two distances by
how far hers sit further off the surface (knuckles, not wrists: a smaller hand reaches less far past the same
wrist); run her again (the rig reads `climb_reach` from the job, and `-Reach "name=value,..."` tries numbers
without a recipe change) and check two things: hands on the lip through the hang, shimmy and pull-up, and knees
and toes not through the wall, since the whole body moves in with the hands. The hero's own toe joints sit 3 cm
inside a wall and his knees touch it, so his numbers are the reference, not zero. The numbers also set how high a
lip she can reach from the ground, and all 17 gym moves kept their steps with timing within 0.07 s of the hero's.

Remora's first numbers (193.5, 74.5, 57) were matched on V23's wrist joints, which sat in the wrong places; Mark
approved them on 2026-11-10 from `work/parkour-revamp-20261109/sheets/remora_all.jpg` and found the climbing
"feeling good" in play. With her arm joints measured (V24, above) they were found again: 191 and 76 in the hang
put her knuckles within 1 cm of his, and on a wall 55.5 splits the difference between her hands 3 cm further off
it than his (at 57) and her left knee 4 cm closer to it than his (at 54, where her hands matched). With the shoulder
joints measured as well (V25) her upper arm grew from 20 to 23 cm and the numbers moved a third time: on V24's her
knuckles rode 4 cm above his in a hang, over the lip instead of on it, and her hands came onto a wall by themselves.
195, 75.5 and 56.5 put her hang knuckles within half a centimetre of his, her wall knuckles 1-2 cm further off than
his and her left knee 2 cm closer than his (`work/parkour-revamp-20261109/sheets/remora_09_v25_reach.jpg`). Every
change to an arm or shoulder joint moves these: find them again each time.

It is a review setting. An installed character needs the same three numbers set on its own pawn by the game (the
installer does not do it yet); the same goes for the glider offset.

## What Remora taught (and the road now does by default)

- **Unit scale.** An FBX at Blender's metre scale imported at 1.7 cm; a scale left on the armature node was reset by
  retargeted clips and she shrank to 1 cm in motion. Unit scale 0.01 with the 100x applied fixes both.
- **One mesh for the landmark rig.** The landmark route refuses several meshes; the join keeps morphs by name.
- **Rest morphs.** Unreal rests every morph at 0, so a glTF rest pose (her softened lids) must be in the basis.
- **Normal maps.** glTF is OpenGL (+Y); Unreal reads DirectX. Unflipped, every bump lit from the wrong side.
- **Red hairline glow.** With Substrate and virtual shadow maps, screen-space skin scatter smeared the hair's shadow
  edge into a red line at the temples. Transmission, boundary bleed, radius and strength were each tested and were
  not the cause. Masking scatter under the hair fixes it and keeps the hair's shadow. Runtime Python cannot add a
  separate hair component here, so splitting the hair off was not an option.
- **Gaunt face.** The lid pose plus narrowed cheeks under hard overhead light read as gaunt in game though fine in
  Framewright. Judge faces in the game's own light; that is why the closeups are taken in game.
- **Chin step.** Rig weights, not the mesh: fixed by the rigid head and chin-measured neck blend.
- **Closeup camera.** The character's tick rewrites boom length and FOV every frame; closeups pause the actor tick.
  Body and pose views turn the character, not the camera: orbiting put the back view's camera inside a wall.
- **Envelope weights.** Heat weights failed on the layered character and on a welded copy, and the rig fell back to
  envelope capsules: mid upper arm split evenly four ways (22% on the forearm), trousers stretched into sheets between
  the legs, the tunic flung out in the attack and jump. Heat on a voxel stand-in works once the stand-in is only its
  outer surface: the remesh also seals hollow pockets between outfit and body, and their walls, seeing no bone, left
  the heat equations without a solution for every bone (0% coverage). Decimating the stand-in had the same effect.
- **The buttock rides the leg.** The stand-in heat gives the back of the hip to the thigh, so from behind a run
  balloons each buttock into a faceted lump as the knee lifts. `bind.hip_release` moves most of it to the pelvis
  with a long blend down the thigh. Judge it from behind: that is the view the player has.
- **Layers part.** Outfit layers a few millimetres apart get slightly different weights and the lower one comes
  through the upper one in motion. `bind.layer_follow` makes a covered vertex copy its cover, keeping up to eight
  influences. A test that skips the road's own influence cap looks cleaner than the game: pose-test with the
  road's full post-processing.
- **A template joint is not her joint.** Elbow, wrist and shoulder placed by Manny's proportions were centimetres
  off her mesh, and each showed as a different fault in game (an "extra bone" in the forearm, a shoulder "bending
  wrong"). A weight fix made earlier for the shoulder (`shoulder_release`) was treating the symptom. Measure the
  joints on the mesh first (`arm_joints`), then look at weights.
- **One surface, two owners.** Where a generated mesh fuses bare skin and outfit, smooth weights drag the outfit's
  edge with the limb. `bind.armhole_hold` tells them apart by colour and gives the outfit back to the torso. Judge
  it on the ledge hang, from behind and from the front.
- **Hair plastic.** Roughness and specular alone only traded a broad sheen for a dull mass; the hair's normal map is
  flat and its roughness map one value. Hair shading along a baked flow map is what changed how it reads.
- **A misspelt gain does nothing.** The game's Remora (and Character02) configs scale `mouth-parting`; MakeHuman's
  unit is `mouth-parling`, so the jaw was opened 1.5x with the lips parted at the full table weight, baring both rows
  of teeth. The face pass now flags any name the mesh lacks.
- **Relative paths.** `[System.IO.Path]::GetFullPath` resolves against the process directory, not PowerShell's
  location; a relative `-OutputDirectory` landed in a nested copy of the work folder. The road resolves paths against
  the PowerShell location.

## Healthy-skin repaint (the companion road)

When the skin itself needs repainting, it goes through the registered reference route before this road
([REFERENCE_PATCH.md](REFERENCE_PATCH.md)): capture guides on the chosen face, have the image model repaint the guide
views (Remora's prompt: `work/remora-airship-20261106/face88/skin-request/prompt.txt`), then `reference-patch` with
`relief_m: 0` (no carved shading, which is what read gaunt) and `retain_normal: 1`.

Keep the patch's lower bound **above where the head mesh ends**. The guide pictures stop at that jagged edge, and a
bound reaching below it painted the zigzag onto the neck (Remora v1). `face89/skin_recipe.py` started at 1.29 m;
1.314 m with a 12 mm feather fixed it. Read the edge from the guide hit maps: the lowest hit row per column, converted
with the view's centre and width.

## Not covered

- A production body rig: the rebind is heat weights on a stand-in, good enough to judge in motion, not a reviewed
  skin. Loose garments (a tunic hem over the thighs) still follow the legs; the rig road is
  [CHARACTER_ANIMATION.md](CHARACTER_ANIMATION.md) and the rig stage in [PIPELINE.md](PIPELINE.md).
- Hands: the fit brings Remora's hands from 9 and 10 of 24 joints inside to 18 and 15 (right thumb now inside); her
  right pinky still sits about 1 cm out. A first unbounded fit put every joint inside by folding them all into the
  palm: inside-ness alone is not a hand, so the fit is bounded and must reach the fingertips.
- Loose garments: with heat weights Remora's tunic hem reads acceptably in the walk, jog, attack and jump; there is
  no hem rule. Revisit only if a review flags it.
- Other games: only The Aether Wars is wired (`unreal.game`).
- Production readiness: deformation evidence, a cooked build and the ledger's gates, as everywhere else.
