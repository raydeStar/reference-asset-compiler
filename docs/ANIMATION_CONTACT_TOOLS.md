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
