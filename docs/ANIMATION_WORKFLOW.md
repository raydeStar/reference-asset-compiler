# Open-source animation workflow

*Type: reference*

The production route is licensed motion source → approved poses → calibrated
retargeting → contact/performance cleanup → transition testing → exported review
→ gameplay acceptance. The tools prepare candidates and evidence. A script does
not decide whether a performance has weight, character or good timing.

Read [CHARACTER_ANIMATION.md](CHARACTER_ANIMATION.md) first. Existing mesh,
weights, UVs, textures, hierarchy and bind transforms remain the authority.
This animation workflow does not change the image-conditioned acquisition rule
or relabel historical character/model provenance. Unreal remains the chosen
delivery target; new authoring components use open licenses.

## Shipped interface

For explicit character profiles, the complete recipe-to-review command, clean
installation checks and optional independent Unreal plugin, see
[ANIMATION_REUSE.md](ANIMATION_REUSE.md). Character02's historical adapters below
remain available; they are not the only entry point.

`rac animation` is installed with the Python wheel. Its commands are `init`, `preflight`,
`derive`, `measure`, `compare`, `compare-models`, `review`, `summary` and `package`. The workstation
adapter is `scripts/anim/animation_pipeline.py` in this checkout; it provides
`snapshot`, `inspect`, `bake-library`, `export`, `surface-audit`, `engine-audit`, `engine-runtime`.
It calls the existing hash-pinned retargeter instead of copying the legacy studio.
Every run uses a new output directory; failures and logs are retained.

| Operation | Contract |
|---|---|
| Select clips | Explicit existing names; preserve source metadata and transforms. |
| Rotate a bone | Local XYZ offsets, each bounded to ±30°; existing non-root bone. |
| Retime | Duration factor 0.5–2, fixed sample rate; update marker times and nominal speed. Refuse event-bound, transition and root-track clips. |
| Solve contact | Explicit three-bone chain, support interval, world contact target, local contact offset, actor velocity and blend duration. Preserve segment lengths and effector orientation. Refuse unreachable targets. |
| Bake library | Existing calibrated native-rig retargeter, pinned source libraries, profiles and timing contract. A fresh bake is a new candidate, not the historical polished packet. |
| Export | Bake native actions; export GLB/FBX; reopen each and compare all named-bone poses at every source frame. |
| Compare models | Compare embedded GLB mesh/UV/weights/skin/material/image data independently of animation, including sparse morph data. Unknown compression/extensions require an explicit adapter. |
| Measure | Loop position/orientation gaps, peak joint speed, declared contact drift/speed/penetration, direct join position/velocity gaps, offline 30/60/120 Hz sampling. |
| Review | Named clip set, source hash, evidence hashes, reviewer, pending/accepted/rejected, cleanup minutes. |

The contact operation is a bounded limb solver, not a full-body optimizer or an
automatic foot-lock detector. Adjust the pelvis/pose first if the target is out
of reach. If a conventional `ik_<effector>` bone exists, declare it in
`sync_effectors`; the tool refuses to leave that target behind. Review twist,
coat, knee/elbow direction and hand/weapon relationships afterward. A pole
direction can be explicit. Multiple simultaneous contacts can conflict; they
need coordinated pose review, not an unbounded series of local fixes.

Example recipe operations (these are shapes, not recommended Character02 angles):

```json
[
  {"op": "retime", "clip": "MM_Idle", "duration_factor": 1.1},
  {"op": "rotation_offset", "clip": "MM_Idle", "bone": "head", "degrees_xyz": [0, 0, 2]},
  {"op": "solve_contact", "clip": "MM_Idle", "chain": ["thigh_l", "calf_l", "foot_l"], "interval_s": [0.2, 0.8], "target_cm": [0, 0, 0], "offset_cm": [0, 0, 0], "actor_velocity_cm_s": [0, 0, 0], "blend_s": 0.08, "sync_effectors": ["ik_foot_l"]}
]
```

Use a measured heel/ball/palm offset and target, not the example origin.
A sync marker is an instant; it is not evidence of an entire support interval.
In-place gait drift needs the controller's actor travel. Skeletal ankle height
alone is not the boot sole. The measurement report labels these limitations and
leaves unmeasured surface penetration/intersections explicit.

For Character02, `surface-audit` bridges the existing pinned skinning checkers.
It evaluates actual weighted boot vertices, hand/thumb-to-torso/coat triangles,
thumb/finger contacts and boot/boot intersections. It uses the native bind data
and all source weights. Its receipt identifies **offline packet poses**, even
though the older checker text describes its original UE-pose-dump use case.
Choose the plane explicitly; zero below is a declared source-space plane, not
the height of a measured game floor. Sampling does not prove continuous clearance.

```powershell
python scripts/anim/animation_pipeline.py surface-audit "$run/inspect/recipe.json" --blender $blender --output "$run/surfaces" --floor-z-cm 0 --sample-hz 30
```

## Recipe and license boundary

Schema `reference-asset-compiler.animation-recipe.v1` binds packet, native
character, optional installed configuration, inspected skeleton, mapping files,
provider artifacts and license evidence by SHA-256. It states pose intent,
UE-local coordinates (cm, Z up, xyzw), benchmark cases and bounded operations.
Derived packets preserve gameplay events, root-motion flags, aliases and source
provenance; operations that cannot preserve a timing contract refuse to run.
Receipts record numerical tool versions and code hashes; Blender receipts record
its version, script hash, native fingerprints and exported hashes.

Providers are interchangeable **packet producers**: `licensed-library`, `capture`
or `generator`. No generator is installed or executed by this interface. Before
admitting its packet, inventory code, motion/data, weights, body models and
dependencies as applicable. Generator inventory requires separate code, weights
and training-data evidence plus the explicit completeness declaration. Only the
declared license allowlist is accepted. Hash and allowlist checks verify recorded
evidence; they cannot establish that an operator's license declaration or complete
dependency inventory is truthful. Read the actual terms before recording them.

The default Character02 snapshot uses existing CC0 Quaternius libraries and MIT
retarget scripts. Blender, NumPy and SciPy remain the authoring core; optional
review-video encoding uses a local FFmpeg executable. No Auto-Rig Pro, restricted
SMPL family model, Kimodo weights, AnimoFlow application, video generator or
hosted AI service is introduced. A future local LLM controller should call these
same bounded commands. Neither MCP nor an LLM is required to compute the motion.

## Character02 reproduction on this workstation

Use a fresh `$run` on every attempt. The selected packet comes from the installed
Character02 configuration, never from a guessed latest directory.

```powershell
$project = 'C:\Users\Ayric\Documents\Unreal Projects\TheAetherWars'
$blender = 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
$unreal = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$unrealCmd = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$run = 'work/animation-my-fresh-attempt'
python scripts/anim/animation_pipeline.py snapshot --project $project --output "$run/snapshot"
rac animation preflight "$run/snapshot/recipe.json"
python scripts/anim/animation_pipeline.py inspect "$run/snapshot/recipe.json" --blender $blender --output "$run/inspect"
rac animation measure "$run/inspect/recipe.json" --output "$run/baseline.json"
```

Copy the inspected recipe to a new candidate recipe and edit its `operations`.
Keep benchmark conditions identical for comparison. Author contact intervals,
surface offsets and actor travel for the intended test before solving contacts.
Do not rewrite an already-used recipe; receipts bind its exact contents.

```powershell
rac animation derive "$run/candidate-recipe.json" --output "$run/candidate"
rac animation measure "$run/candidate-recipe.json" --candidate "$run/candidate/clips.json" --output "$run/candidate-measurements.json"
rac animation compare "$run/baseline.json" "$run/candidate-measurements.json" --output "$run/comparison.json"
python scripts/anim/animation_pipeline.py export "$run/candidate-recipe.json" --packet "$run/candidate/clips.json" --blender $blender --output "$run/export" --clips MM_Idle,MF_Unarmed_Jog_Fwd,MM_Pivot_L --render-views
```

Export the baseline through the same adapter/settings, then run `rac animation
compare-models baseline.glb candidate.glb --output fresh-model-comparison.json`.
This checks exported payload preservation in addition to the native fingerprint.
Run the existing exported relaxed-standing-idle pose gate when that is the
declared stance; neither duration edits nor valid motion channels waive it.

For four-view 24 FPS videos with two repeats, add `--motion-fps 24 --ffmpeg
'absolute/path/to/ffmpeg.exe'` to the export command. The CPU-rendered videos are
low-resolution review aids, with separate higher-resolution stills. Repeating a
one-shot action does not certify its end-to-start seam. Video files come from the
reimported GLB, not an unexported control rig. The native `.blend` keeps editable
actions. Synthetic packet roots become armature-object animation without changing
the native bone hierarchy; verify destination root extraction before installation.

An independent fresh-source bake can be invoked with `bake-library`, the inspected
recipe, `--blender`, `--output`, and optional `--clips`. This replays the current
calibration profiles. It does not reproduce subsequent historical cleanup unless
that cleanup is explicitly represented in additional operations.

```powershell
python scripts/anim/animation_pipeline.py engine-audit "$run/inspect/recipe.json" --unreal $unrealCmd --output "$run/saved-assets"
python scripts/anim/animation_pipeline.py engine-runtime "$run/inspect/recipe.json" --unreal $unreal --output "$run/runtime-30" --fps 30
python scripts/anim/animation_pipeline.py engine-runtime "$run/inspect/recipe.json" --unreal $unreal --output "$run/runtime-60" --fps 60
python scripts/anim/animation_pipeline.py engine-runtime "$run/inspect/recipe.json" --unreal $unreal --output "$run/runtime-120" --fps 120
```

These commands inspect the **currently installed baseline**, not a candidate
that has not been installed. Audit reloads saved settings/markers and verifies
packet identity. Runtime creates and closes its own offscreen `-game` process;
it never attaches to the user's editor. It retains frame times and achieved FPS,
not merely the requested cap. The existing probe covers input-driven idle,
walk, jog, sprint-speed and stops; its sprint phase is not a Shift-key test.
This is editor game mode, not cooked runtime. Neither command saves game assets.
Keep output paths space-free for Unreal's `ExecCmds` launcher.

## Acceptance and known gaps

The numerical benchmark covers idle/armed idle, walk/jog/sprint, start, both
stops/pivots, jump/land, three attacks and two dodges. Existing transition metadata
supplies direct join samples. Full benchmark acceptance still needs:

- Annotated support phases on both feet, boot/ground surface measurements and
  skinned-body/clothing/weapon intersections in gameplay. Offline surface checks
  are available, with recorded exclusions; a low joint-drift score is insufficient.
- Starts/stops on both support feet, left/right turns and reversals, jump-to-land,
  interrupted attacks and weapon-grip checks in the actual controller.
- Freshly installed candidate persistence, root extraction, events and chosen
  clip after reload, plus cooked/runtime proof when promoting an asset.
- Human comparison of weight, readability, responsiveness and character, over
  two loops and four views. Preserve the existing stance/deformation checks.

Use `rac animation review --help` to record a real decision with `--clip` for each
reviewed clip, `--evidence`, `--note`, `--reviewer` and `--cleanup-minutes`.
Agents may create pending reviews, never impersonate the human reviewer.
`rac animation summary` excludes pending reviews from the acceptance denominator,
counts named clips and includes rejected-attempt cleanup time. Supply one current
decision per packet/clip; do not count multiple revisions as separate successes.

`rac animation package` copies explicitly selected exports/evidence and retained
license files into a new review folder. The recipe records external source paths;
this is not a self-contained copy of all source libraries. The manifest does not
promote an asset or assert that arbitrary supplied evidence proves acceptance.

No benchmark metric automatically names a winner. A skeleton may keep perfect
appointments while its performance remains an unattended coat rack.

## First implementation evidence — 2026-10-22

Retained artifacts: `work/animation-methodology-20261022/`. The original packet
and native character remained unchanged. `baseline.json` covers 17 cases;
`export-v4/receipt.json` verifies all 19 packet clips in GLB and FBX. Earlier
export-v2/v3 rejection receipts preserve action-selection bugs fixed before v4.
`library-replay/` exercises source-library retargeting for idle and walk.

`candidate/` is an explicitly unapproved 1.1× idle-duration alternative; other
clips are preserved. `comparison.json` is numerical evidence, not an improvement
claim. `candidate-export/` contains idle/jog/pivot exports, four views and review
videos. Installed-baseline probes passed at caps 30/60/120 with observed averages
29.6/58.0/77.7 FPS. Sustained 120 FPS, candidate gameplay and the remaining
acceptance checklist are **not established**. See the evidence index and STATUS
for final verification receipts.

The full-rate surface check found hand/coat intersections in both variants:
192 side/frame observations in the 575-frame baseline and 201 in the 582-frame
candidate. The longer idle adds samples, so raw counts are not a fair quality
ranking. Both also have a minimum boot height of -2.254 cm in Attack 03 against
the declared zero plane. Neither passes clearance; verify the visible contacts
and engine grounding before attempting a pose-specific fix. These receipts
are `baseline-surfaces-30/` and `candidate-surfaces-30/`.

`model-preservation.json` confirms identical exported model payloads. Both
baseline and candidate fail `check_relaxed_idle.py` for the declared relaxed
standing contract (elbow bend around 47°, plus pelvis drift). Rejections are
retained in `baseline-idle-pose.json` and `candidate-idle-pose.json`; measured
native height is 1.78518 m. Do not present this timing alternative as a corrected
relaxed idle. A different stance contract needs an explicit artistic intent,
not looser thresholds invented to obtain a pass.
