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
