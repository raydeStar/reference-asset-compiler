# Character02 posture and hand clearance — 2026-10-12

The user accepted the sleeve improvement and requested hand/coat clearance and
less hunched shoulders, allowing a rebuild if needed. Inspection showed the
existing acquired game mesh already has a T-pose. This pass preserves it and
tailors the animation to the coat instead of replacing the face or garment.

Selected native bake: `work/character-02/posture-20261012/bake-v6-clearance/`.
Recipe: `recipes/character-02-posture-20261012.json`. The held correction lowers
the shoulders 3 cm, moves them out 2.5 cm, straightens the torso 3 degrees, and
adjusts upper-arm/forearm placement. Recorded local matrices are applied to the
original motion. Only isolated contacts need additional arm separation, with
smooth entry/exit: at most 10 degrees in rightward jog and 8 in attack 01.
Hand IK markers follow the corrected hands. Bind transforms, all mesh data,
weights, textures and facial expressions are unchanged.

## Rebuild

The original raw UE animation dump is retained in The Aether Wars at
`Saved/CharacterPosture/baseline-20261012/`. `Tools/CharacterPostureDump.py` creates
such a dump read-only. Do not substitute a dump of the already-corrected clips:
the recipe pins the original manifest and mesh reference hashes. The UE skeleton
asset contains older reference joints, so the mesh component's actual bind pose
is the authority. That reference matches the native rig within 0.000021 matrix
units; the initial Skeleton-reference comparison was rejected.

```powershell
& $Blender --background --factory-startup --python-exit-code 1 --python scripts/blender/tailor_character_locomotion.py -- --source work/character-02/seams-20261012/release-v2/Character02_UE5_coat.blend --dump "$UnrealProject/Saved/CharacterPosture/baseline-20261012" --trial work/character-02/posture-20261012/pose-trials-v3/trials.json --recipe recipes/character-02-posture-20261012.json --candidate elbow --out work/character-02/posture-20261012/fresh-replay
```

Use Blender 5.2.2 LTS. The native bake uses CPU geometry/math; trial renders used
Cycles OPTIX, 768 square, 16 samples, seed 23. `inspect_character_posture.py`
records the T-pose and original posed geometry. `trial_character_posture.py`
retains the held-pose experiments. The selected bake saves its executed script,
per-clip tracks, source/output hashes, collision samples and blend results.

The final gate passes all 1,113 recorded frames across 19 clips (idle, all eight
walk and eight jog directions, first attack, jump), and 960 blends spanning
idle/movement, adjacent directions and walk/jog. It checks palm/finger triangles
against coat skirt and torso through the collar. Upper sleeves and the wrist/cuff
overlap are excluded. Finite sampled checks do not prove all runtime blends or
all combat/traversal actions collision-free.

The game packet is `Saved/CharacterPosture/selected-v2-20261012/`.
`Tools/CharacterPosture.py` checks the exact imported FBX hash, requires the
clearance pass, backs up existing animation assets, writes absolute local tracks,
and reads every changed key back. Reapplying cannot accumulate corrections.
The headless installer's `posture` step runs after retarget/traversal. Changed
meshes require rebaking; other characters are unaffected. Original assets remain
in `Saved/CharacterPosture/backup-before-install-20261012/`.

## Retained failures and limits

- Initial shoulder lowering alone left the right hand in the coat.
- A wider stance or forward arms was less suitable than the selected held pose.
- `bake-v1` rejected using stale Skeleton reference transforms as bind data.
- `bake-v3` caught one contact in 384 idle/locomotion blends. A 5 mm shoulder
  spacing adjustment cleared that case; `bake-v4` passed 960 blends.
- Expanding the collision region up through the collar (`bake-v5-full-torso`)
  found four rightward-jog frames and five first-attack frames. The selected v6
  applies bounded, smoothly entered arm separation and clears those frames.

Unreal 5.8.3 installation and editor captures are recorded in the game project's
`Saved/CharacterPosture/installation.json`, `Saved/CharacterTextureRepair/` logs
and `Saved/PosedCloseups/posture-*`. Front, side, back and elevated three-quarter
views were inspected. This is editor-render evidence; user gameplay acceptance
and cooked-runtime validation are separate. Collar tears, cuff lining and hair
quality are not repaired by this animation pass. Nothing is production-ready.
