# Open-library animation for a game character — 2026-10-14

*Type: how-to*

The UE template's 19 Manny clips, copied one to one onto a character with different proportions and a
knee-length coat, read as stiff (tucked "T-rex" arms, claw hands, hunch); the script-keyed traversal and
combat clips read as robotic. A baked shoulder/arm offset pass (2026-10-12, `CHARACTER_POSTURE_REPAIR.md`)
changed the motion by a few degrees and was retired at the user's request.

This stage replaces the locomotion with open-source clips retargeted onto the character's own game rig.
**Only open-source animation is used** (the user's rule): free-but-proprietary libraries such as Mixamo or
Epic's Game Animation Sample are out.

## Sources

| Library | License | Used for |
|---|---|---|
| Quaternius Universal Animation Library 1, Standard (`AL_Standard.fbx`, Unreal version) | CC0 | idle, walk, jog, sprint, jump start/loop/land |
| Quaternius Universal Animation Library 2, Standard (`UAL2_Standard.glb`) | CC0 | reserved: sword combo, block, dash, throw, climb-up, slide, roll |
| 100STYLE (Mason et al., Zenodo 8127870, BVH) | CC BY 4.0 | planned: real mocap locomotion for motion matching |

The archives are not redistributed; download them into `work/anim-sources/<name>/` (each in its own
folder, extracted, nothing executed). SHA-256 of the two UAL archives is in `work/anim-sources/SHA256SUMS.txt`.

## Pipeline

```powershell
$B = 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'   # Blender 5.2.2 LTS
& $B -b --factory-startup <character>_UE5_coat.blend --python-exit-code 1 -P scripts/anim/bake_library_clips.py -- `
   --profile profiles/animation/ual-to-ue-template.json `
   --library "ual1=<...>/Unreal Engine/AL_Standard.fbx" --library "ual2=<...>/UAL2_Standard.glb" --out <fresh dir>
& $B -b --factory-startup <character>_UE5_coat.blend --python-exit-code 1 -P scripts/anim/preview_baked_clips.py -- `
   --clips <dir>/clips.json --names MF_Unarmed_Jog_Fwd,MM_Jump --views q34,side --out <dir>/preview
```

- `scripts/anim/clip_retarget.py` — the retarget. World-rotation transfer relative to a matched T-pose
  (UAL's `A_TPose` action), with a yaw aligning the two rigs' shoulder lines, so bone-axis conventions never
  matter; pelvis travel scaled by hip height; UE IK bones pinned to the hands/feet; `planted_speed()`
  measures each loop's ground speed from ball-of-foot contact at 120 Hz (walk 91, jog 597, sprint 927 cm/s
  for character-02).
- `CoatFollow` (same module) — for a rig with `coat_<group>_NN_<side>` chains: per frame, the smallest
  outward hinge at each chain root that keeps the joints below it clear of the leg capsules
  (min(0.85 x rest clearance, 4 cm)); lower joints bend back 35%/30% so the panel drapes over a knee instead
  of levering out like a board; eased in 4 frames before contact, out over 8. `--no-coat-follow` disables.
- `RelaxedHands` and `Stance` (same module), per clip in the profile (`hands`, `stance`): the library's
  locomotion holds loose fists and its idle is a wide, staggered fighting stance (feet 0.50 m apart, one
  foot 0.46 m back), which the user read as clenched hands and odd posture. RelaxedHands builds a rest curl
  from the rig's own geometry (curl 18–32 deg at the knuckles rising index to pinky, spread closed to 30%,
  thumb tucked) and carries it with the animated hand; Stance runs two-bone leg IK to 0.26 m and at most
  0.14 m stagger with the knees turned forward, keeping each foot's animated rotation. Aim leg bones by the
  real vector to the child joint: this rig's bone axes do not point at their children.
- `profiles/animation/ual-to-ue-template.json` — bone map and clip map onto UE template asset names. The
  8-way walk/jog samples all take the forward cycle: right for a character that turns to face its movement
  (`bOrientRotationToMovement`), wrong for a strafing one.
- `scripts/anim/preview_baked_clips.py` — renders the exact baked tracks (fixed cameras, EEVEE, MP4).

The game side (The Aether Wars `Tools/LibraryAnims.py`, installer step `library`) keys `clips.json` straight
into `<prefix>_<clip>` on the character's skeleton (no IK retargeter in between), reads every key back
(character-02: worst 0.00003 cm / 0.0014 deg), and rebuilds the locomotion blend space at real speeds: walk
91 cm/s (rate 1), jog at the player's 500 cm/s (rate 0.837), a new sprint row at 840 cm/s (rate 0.907).

## Character-02 result

Packet `work/character-02/anim-ual-20261014/bake-v5/` (coat-follow with drape, relaxed hands, hip-width
idle), installed as the game's `Saved/LibraryAnims/Character02/ual-v3`. CPU review stills:
`bake-v5/stills-big/` (`preview_baked_clips.py --engine CYCLES` renders without the GPU). Blender previews in `bake-v3/preview/`; earlier comparison
videos (template vs UAL) in `work/character-02/anim-review-20261013/preview/`. The user liked the motion.
In-engine editor captures: game `Saved/PosedCloseups/ual-*-20261014*`.

Retained failures: hiding the imported library rig from the viewport stops Blender evaluating its pose
(every frame identical); a pelvis-frame facing alignment skewed the whole pose (bone axes differ between
rigs); median-of-frames foot speed at 30 Hz misread the sprint (82 cm/s); coat-follow judged on the hinge
joint itself could never clear (every chain hit the 70 deg cap); a rigid chain swing made jump panels stick
out horizontally.

Limits: the clips are hand-keyed game animation, not mocap; no starts/stops/pivots yet (100STYLE + UE Pose
Search is the next step); combat, dash and traversal still use the earlier clips; coat sway physics is off
(the baked coat-follow clears the legs; in-engine AnimDynamics could add secondary motion on top). User play
acceptance and cooked-runtime validation are open. Nothing is production-ready.

## Combat (2026-10-14)

`profiles/animation/ual-combat-to-ue-template.json` with `--contract <game combat-contract.json>` (The Aether
Wars `Tools/CombatContract.py`): Sword_Regular_A + A_Rec, B + B_Rec, C, and UAL 1 Sword_Attack_RM become the
combo's three cuts and the charged attack. `Sequence` joins a swing to its recovery (pelvis carried across the
join), `retime()` keeps the game's clip length with the peak sword-hand speed on its hit-trace time, and the
lunge goes onto UE's root bone (this rig's Blender armature object is that bone, so the whole pose is moved
back and a `root` track is keyed). The combo jumps to the next section mid-recovery, so the cuts stay
unmirrored (a mirrored second cut starts in the opposite stance): the pelvis gaps at the jumps are 0.2 and
2.1 cm. `coat_max_deg` 22 keeps coat-follow from levering the panels out flat in the wide lunges. Packet
`anim-ual-20261014/combat-v2/`; filmstrip `combat-v2/combat-filmstrip.jpg` (CPU Cycles).

Retained failures: mirroring the second cut (stance pop at the combo jump); root motion measured from frame 0
(the second cut starts displaced, 88 cm pelvis gap); using bone 0 as the root on a rig with no root bone
(pelvis frozen across the segment join, torso torn from legs) and shifting only top-level world matrices
(children left behind, spine 50–230 cm from its pelvis); uncapped coat-follow in lunges (panels flat as a table).

## 100STYLE motion capture and motion matching (2026-10-14)

`clip_retarget.BvhLibrary` reads a folder of BVH takes (100STYLE, CC BY 4.0: credit Mason et al. 2022). Time comes
from each take's own `Frame Time` (Blender keys one BVH frame per scene frame; reading the scene rate slowed the
mocap 2.5x), the reference is the BVH rest T-pose with a standing hip height measured from the take, and `Retarget`
scales by leg length. `facing_root_motion()` (`root_motion: facing` in a profile) puts each frame's ground position
and heading on UE's root bone, both Gaussian-smoothed so stride sway stays on the pelvis; motion matching reads it.
Profile `profiles/animation/100style-to-ue-template.json`; packet `work/character-02/anim-100style-20261014/mm-v1/`
(Neutral FW/FR/ID/TR1, 10.9k frames at 30 fps). The game side is The Aether Wars `Tools/MotionMatching.py`.

Measured limit: 100STYLE is captured in a small room. Neutral runs average 1.1 m/s (p95 ~1.75), and the fastest of
all 100 styles ("Rushed") reaches ~3 m/s at p95, against the game's 5 m/s jog and 8.4 m/s sprint. Motion matching
therefore covers idle, walking, starts, stops and turns, crossfading into the speed-matched library cycles above
~2 m/s; the hunched Neutral jog was dropped from the database after it surfaced at slow analog speeds.

**Play-test outcome (2026-10-14):** in game the motion-matched idle surfaced gestures from the ID/TR1 takes (hands
raised at random) and Mark reported the walk gliding, so motion matching is switched off for character-02; the
library cycles are back. Most of the glide turned out to be the game's blend space playing the walk at jog speed
(stale runtime data after Python edits; fixed in The Aether Wars `Tools/LibraryAnims.py`). Retry motion matching only
with a curated idle and walk takes that cover the stick's speed range. Retained failure: root motion carried the UE IK
side roots (`ik_foot_root`, `ik_hand_root`) metres away ("feet go flying"); `_rest_side_roots` keeps them at rest.

## Drawn-blades idle (2026-10-14)

`MM_Idle_Swords` in `ual-to-ue-template.json`: UAL 1 `Sword_Idle`, hands gripping (no relaxed-hands layer). Packet
`work/character-02/anim-ual-20261014/swordidle-v1/` (51 keys, 1.67 s; preview `sheet.jpg`; `work/` is not committed).
The game switches the Idle state to it while the blades are drawn (The Aether Wars `Tools/BladeIdle.py`).

## Starts and stops (2026-10-14)

The open libraries have no jog starts or stops (100STYLE tops out at walking pace), so `scripts/anim/transition_clips.py`
composes them from the profile's own accepted jog and idle, on the game's movement curves (profile `transition` clips:
`MM_Stop_L`, `MM_Stop_R`, `MM_Start`). The jog plays on a time warp (phase advance = distance / planted speed); the pose
cross-fades jog <-> idle; the feet follow an explicit step plan by two-bone leg IK. A stop is two steps: the foot planted at
release holds, the other steps through to its idle spot (0.22 s), then the planted foot closes up (lift 7 cm); the clip ends
on the idle's frame 0. A start steps off with the left foot onto the jog's touchdown (0.28 s); the right holds its idle spot
until the jog lifts it. `summary.json` records each clip's speed profile and per-frame ball-of-foot positions with the travel
added back (`slip`: planted median 0 cm/s on both stops). Packet `work/character-02/anim-ual-20261014/startstop-v4/`
(preview `preview/strip.jpg`). Game side: The Aether Wars `Tools/LocomotionFeel.py` and `UAetherLocomotionFeelComponent`.

Retained failures: v1/v2 planted one foot through the whole ~95 cm stop (out of leg reach: the foot dragged and sank 8 cm
into the floor) with a 3 cm "closing" lift that read as a slide; turning a planted foot about its ankle to the idle's toe-out
swung the ball 10 cm sideways (planted feet now keep their rotation until they lift); a start ending on jog frame 0 had no
touchdown inside the clip (both feet airborne at the join), so the start's phase is now chosen from its first touchdown.

## Pivots (2026-10-14)

`build_pivot` composes a 180-degree running reversal on the game's curves (reverse friction 16 = 2 x GroundFriction, accel
1400, yaw 720 deg/s), in the actor's frame while the actor turns: the inside foot keeps its ball fixed in the world and yaws
with the body, the outside foot arcs from behind onto the new direction's touchdown (0.22 s), the planted foot pushes off
0.04 s later; the clip then runs on until the jog reaches `end_phase_s`. Per-frame feet are reported back in world space
(`slip`: planted median 0.7-0.9 cm/s). Packet `work/character-02/anim-ual-20261014/pivot-v2/`.

## Dodges (2026-10-15)

`MM_Dodge_Fwd`: UAL 2 `Sword_Dash_RM` with `in_place` (travel extracted, not keyed: the game moves the capsule) and an
explicit `timing` retime (`length` + `[target s, source s]` anchors: 0.3 -> 0.1, 1.0 -> 0.34, end 1.57 -> 0.62 s).
`MM_Dodge_Back`: `transition_clips.build_backhop`, keyed offsets on the drawn-blades idle (pelvis crouch/rise/land, feet
lifted and reaching, spine pitched forward ~24 deg, arms thrown forward), legs by IK; `chest_ahead_of_pelvis_cm` in the
summary checks the lean sign. Single-segment clips with `root_motion: true` now go through the root-motion path (before,
their travel stayed in the pose). Candidates rejected: Roll_RM (a dive roll, kept for landing rolls), Hit_Knockback_RM (falls
flat), Shield_Dash_RM (shoulder charge). Packet `work/character-02/anim-ual-20261014/dodge-v2/`.

Retained failure (2026-10-15): `with_runin` (a plain-jog run-in before a stop/pivot touchdown, profile `runin_s`) made the
game's mid-stride entries worse (see The Aether Wars Docs/CharacterPipeline.md); kept as an option, unused.
