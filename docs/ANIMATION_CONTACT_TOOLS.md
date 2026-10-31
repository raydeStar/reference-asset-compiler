# Animation contact tools

Generic tools for idle/handoff relaxation, measured sole contact in Unreal and
runtime contact measurement. Character values live in profiles; tool names say
what the tool does. The Character02 profiles reproduce its 2026-10-22/23 repairs
exactly (same output hashes as the retired one-off scripts).

## Relax an idle and its handoffs (CPU)

```powershell
python scripts/anim/relax_idle_handoffs.py --packet <clips.json> --skeleton <skeleton.json> `
  --profile profiles/animation/repair/<name>-idle.json --out <fresh dir>
```

The profile (`rac.idle-handoff-relaxation.v1`) names the idle clip, damps its
pelvis drift, aims the upper and lower arms (x/y of a unit downward direction,
mirrored per side), relaxes the thumbs, and lists the clips that enter or leave
the idle with their arm offsets and blend side (`start`, `end` or absent). Clips
named in the profile must exist in the packet. Root tracks, timing and events are
preserved and checked. `profiles/animation/repair/character02-idle.json` reproduces
the accepted Character02 candidate (packet `e28f6e9a…`).

For a full idle/walk polish on the native rig in Blender, use
`scripts/blender/polish_locomotion.py` with a `profiles/animation/polish/` profile
([ENNIX_ANIMATION_POLISH.md](ENNIX_ANIMATION_POLISH.md) is the worked case).

## Measured sole contact in Unreal

`integrations/unreal/RACAnimation` provides `FAnimNode_RACSoleContact`, configured
from a `rac.unreal-contact-profile.v1` profile by `scripts/ue5/configure_rac_contact.py`.
Every runtime constant is profile data: leg chains, pelvis bone, action slot,
plant curves and lock weights, lock speed, plant envelope, pelvis reserve,
clearance and correction limits, release time, combat montage and limit, and a
`terrain` block (collision channel, ray reach, ground slope, query spacing,
prediction). Defaults reproduce the original human-scale solver. See the plugin
README for the field list and limits. `scripts/check_unreal_animation_plugin.py`
builds it in a fresh minimal host.

## Measure runtime contact (CPU)

An owned engine probe (in the game repository: it drives the game's own pawn
and actions) writes a proof JSON. `analyze_runtime_contact.py` measures it:

```powershell
python scripts/anim/analyze_runtime_contact.py walk     <proof> <out> --criteria profiles/animation/runtime-contact/<name>.json
python scripts/anim/analyze_runtime_contact.py turns    <proof> <out> --criteria ... [--before <proof>]
python scripts/anim/analyze_runtime_contact.py recovery <proof> <out> --criteria ...
python scripts/anim/analyze_runtime_contact.py combat   <proof> <out> --criteria ... [--before <proof>]
python scripts/anim/analyze_runtime_contact.py compare-recovery <before> <after> <out>
```

Criteria (`rac.runtime-contact-criteria.v1`) declare `walk_speed_cm_s`; steady,
support and exit speed bands default to fractions of it, and the windows
(`steady_window_s`, `recovery_window_s`, `settled_after_s`) are optional. Unknown
fields fail. Library code: `reference_asset_compiler.animation_runtime_contact`.

### Proof contract

- Top level: `error` (null when complete), `frames`; `plan` (`[name, [[seconds,
  input, yaw], …]]`) for walk/turn runs; `cases` (`[name, swings, resume_walking]`)
  and `sole_measurement` for attack runs; optional `review_profile`.
- Each frame: `case`, `time`, `delta_s`, `step`, `input`, `speed_cm_s`, `falling`,
  `heading`, `pawn` and component-space `bones` as `[x, y, z, qx, qy, qz, qw]`
  (centimetres, UE-local), `soles.{l,r}` with `gap_cm`, `point`, `vertex`,
  `traced_samples`, `valid_ground_samples`; optional `plant_curves.{l,r}`.
- Attack runs add `combo_active`, `combo_playing`, `any_montage`, `attacking`,
  `section` and `montage_position`; turn comparisons read `cycle_start` and
  `transition_time`.
- Paired comparisons need identical fixed-step frames (same case and time keys).

Leg chains (`thigh_`, `calf_`, `foot_`, `ball_`, `ik_foot_l/r`) are the only bones a
contact fix may move in a paired comparison; everything else must stay put.

## Author run cycles and turn-in-place clips (CPU)

```powershell
python scripts/anim/author_locomotion_clips.py --packet <clips.json> --skeleton <skeleton.json> `
  --profile profiles/animation/authoring/<name>.json --out <fresh dir>
```

Writes a new packet: every existing clip unchanged plus the profile's new clips,
`measurements.json` and `authoring-derivation.json` (input, profile and code hashes).
Library code: `reference_asset_compiler.animation_authoring`.

- **Cycles** (`cycles`): a phase-synchronised blend of two looped in-place cycles,
  aligned on their left touchdowns (`contacts_s`). The lower body takes the weight
  whose unplanted stance already moves nearest `speed_cm_s`, and the upper body
  takes `upper_weight`. Support is detected from the ball of the foot (low and
  moving backward). Each support is then planted at the declared speed with
  `solve_contact`: the ball is the effector and the foot holds its mid-stance
  orientation, so ankle and ball both stay put. Heel/toe roll returns in the ramp
  frames. The clip carries `speed_cm_s`, `contacts_s` and loop `support_intervals`.
- **Turns** (`turns`): idle-to-idle turns on the spot. The root track carries the
  yaw (exact, no translation; `root_motion: true`). Planted feet stay fixed in
  the world. Each step moves the midfoot to the foot's standing spot under the
  turn, bowing away from the planted foot. The step order (`first_step: auto`)
  and, for a foot that steps twice, the intermediate landing share are chosen for
  footprint clearance. The hips stay over the support, and the pelvis lowers
  only as far as leg reach needs. Head and chest lead the turn, and the clip
  starts and ends on the stand clip's first frame. Positive `degrees` turn toward
  the character's left, whatever the rig's axes. `support_intervals` lists each
  foot's planted intervals in clip seconds.
- **Measurements:** slide of the foot and the ball during declared support (world
  speed, including the declared travel for in-place cycles); the loop seam (pose
  difference and seam acceleration relative to the cycle's own); root yaw error
  and translation; start/end distance from the stand pose; closest approach of
  the two footprints (ankle-to-ball segments); and knee bend.

`profiles/animation/authoring/character02-run-turns.json` makes a 500 cm/s run
from the UAL jog and sprint, plus four turns (L/R 90 in 1.0 s, L/R 180 in 1.3 s).
100STYLE has no forward run faster than about 220 cm/s: its runs circle a small
capture floor. So it cannot supply a ~500 cm/s run without warping the stride
by more than 2x.
