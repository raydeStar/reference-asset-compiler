# Ennix idle and walk polish

Use `profiles/animation/polish/ennix.json` with the existing native character,
CC0 Quaternius motion and MIT RAC tools. Existing Manny-derived game clips are
comparison evidence only. Character acquisition provenance remains unchanged.
The local case and rejected attempts are in `work/ennix-idle-walk-20261023/`.

## Author and export

Instantiate the existing Ennix workflow with explicit CHARACTER, PACKET, UAL1
and UAL1_LICENSE inputs as described in [ANIMATION_REUSE.md](ANIMATION_REUSE.md).
Use `animation_pipeline.py bake-library` to rebuild the source packet if needed.
The one-degree demo operation in that workflow is not the polish operation.

Run Blender on `scripts/blender/polish_locomotion.py` with explicit `--source`,
`--packet`, `--profile profiles/animation/polish/ennix.json` and a fresh `--out`.
The profile defines a quiet idle, a scarf-clearing left arm, 23 cm stance width,
8 degree toe-out, 105 cm/s walking, 4 cm swing clearance and a requested cadence
of 1.8 steps/s. Sampling at 30 Hz makes the loop 1.1 seconds, about 1.82 steps/s.
These settings fit Ennix; they are not universal humanoid defaults. Native rest
frames, weights and mesh data remain unchanged.

Export `MM_Idle` and `MF_Unarmed_Walk_Fwd` with `animation_packet.py`.
Run `check_relaxed_idle.py` on the exported GLB and
`check_hand_body_clearance.py --mesh Ennix_Outfit_And_Hands` on the packet.
The latter checks sampled hand/non-arm body triangles, not cloth, sleeves,
unsampled frames or containment. Review four views over two loops. Keep editable
Blender, FBX and GLB deliveries; exact model-payload comparison remains required.

## Bind the destination before keying it

An Unreal Skeleton asset's reference pose can differ from its SkeletalMesh
reference pose. Ennix has this difference, plus different bone-axis conventions
from the native Blender rig. A successful import does not establish equivalence.

`scripts/ue5/export_animation_binding.py` takes a JSON path through
`RAC_ANIMATION_BINDING_CONFIG`. Supply `mesh`, `reference_clip` and a fresh
`output` directory. The clip must use the mesh's skeleton. The helper evaluates
with `optional_skeletal_mesh`, then reads **GetRefBonePose** for the actual mesh
bind frames, and exports the installed mesh read-only. It quits the editor only
when `RAC_OWNED_EDITOR_PROCESS=1` explicitly identifies an owned process.

For the same model with corresponding bones and weights,
`scripts/anim/transport_bind_frames.py` accepts `--packet`, `--skeleton`,
`--source-bind`, `--target-bind` and fresh `--output`. It carries skin deformation
as `animated * inverse(source_bind) * target_bind`, then reconstructs local keys.
This transports frame conventions; it does not retarget another body's
proportions. Model coordinates, bone correspondence and weights require checks.

When keying a new Unreal AnimSequence, set its **retarget source asset to the
actual destination mesh**. Otherwise Unreal can apply another reference-pose
conversion. Key required foot IK helpers from the transported component-space
foot transforms using their declared parent frames. Verify evaluated local keys
with retargeting enabled, then close and reload the assets and verify again.

`scripts/blender/extract_engine_sole_samples.py` accepts `--mesh-export`,
`--engine-bind` and fresh `--output`. These samples use installed geometry,
complete imported weights and actual engine bone frames. Do not supply native
Blender samples directly to a differently framed engine rig.

## Game review

Use versioned Ennix clips, blend space and AnimBlueprint. The walk row matches
105 cm/s; L/R markers and support curves come from the authored loop. Run and
combat clips remain outside this polish scope. Sole correction is configured
per character. Ennix's 6 cm trial saturated on a dungeon ridge; the subsequent
12 cm correction uses 0.4 cm clearance. Character02's settings are unchanged.

When editing Unreal BlendSpace samples from Python, copy the reflected array to
a Python list, update and assign each edited struct back into that list, then
set the complete property. Do the same for axis structs. Rebuild cached blend
triangles, save, and inspect every clip reference and speed row in a fresh editor.
Mutating a struct yielded by reflected-array iteration can silently leave the
saved asset unchanged. Confirm support curves during actual walking as well.

`scripts/ue5/character02_walk_runtime.py` also accepts `RAC_WALK_REVIEW_PROFILE`,
a JSON path specifying `mesh`, `anim_class`, `groom`, optional `hair_material`
and `walk_speed_cm_s`. This changes only the owned runtime pawn; it never saves
or replaces the default player Blueprint. `RAC_BOOT_PROBE` must match the
installed mesh and bind frames. `RAC_WALK_OUTPUT` must be fresh.

The profile enables two stop timings and left/right/reversal exits to idle and
walking. `RAC_TURN_CASE` optionally selects comma-separated cases;
`RAC_WALK_CAPTURE_CASES` limits screenshots without reducing measurement cases.
Independent cases reset the pawn **and create a fresh animation instance** by
clearing and restoring its animation class; assert the instance changed.
Teleporting only the pawn retains the previous world-space foot plant and makes
the next case invalid. Within each case, actual turns and blends are uninterrupted.

Fixed 30/60 Hz dense-trace runs are correctness probes, not performance benchmarks
or cooked tests. Human review still decides naturalness and responsiveness.

## Idle/walk baseline for the turn pass

The retained case uses native packet `candidate-v6/clips.json`, final exports
`export-v6-pose/animated.{blend,fbx,glb}`, engine clips under
`/Game/Ennix/AnimationPolish/20261023/V6`, and the corrected saved blend space and
AnimBlueprint under `V8`. `candidate-runtime-v8.json` selects this graph only for
the owned test pawn. The original Ennix config and Character02 default player
are unchanged. `delivery-receipt.json` binds implementation, assets and evidence.

Both eight-case runtime panels have no negative **observed** sole gaps. Hit
coverage is 99.836% at 30 Hz and 99.847% at 60 Hz; missed queries are not passes.
Straight flat-support intervals remain locked, but sharp-turn ankle excursion
reaches 10.445/9.414 cm. That baseline limitation is corrected by the subsequent
turn pass below. The native pose/export checks and sampled
game hand/body clearance pass. Human visual acceptance remains pending.

The profile is character-specific. It assumes the documented UE-style humanoid
bone names and Quaternius source mapping; using another body requires its own
calibration, deformation review and runtime evidence. Refer to
`docs/evidence/ennix-polish-20261023.json` for the exact checked implementation.

## Sharp-turn runtime correction

`work/ennix-turn-contact-20261023/` retains the separate TurnV1 graph, contact
profile, exact launch commands, module hashes and paired runtime proofs. Source
clips and native exports are unchanged. The correction uses the MIT RACAnimation
plugin, leaving the installed Aether implementation and Character02 untouched.
The profile sets `maximum_plant_offset_cm: 35`, `maximum_pelvis_drop_cm: 6`,
`clearance_cm: 0.4`, `max_correction_cm: 12` and `release_time_s: 0.06`. These are
Ennix-specific settings, not universal defaults. Actual pelvis lowering is at
most 1.937/3.031 cm in the 30/60 Hz panels; the foot position stays reachable
without stretching either leg. Rotation remains free for pivots.

Build the optional plugin in a separate host with
`scripts/check_unreal_animation_plugin.py`, verify the engine BuildId, and install
its source/binaries as `Plugins/RACAnimation`. The descriptor is explicitly
disabled by default. Local review launches use `-EnablePlugins=RACAnimation`;
they do not alter the project's saved plugin setting or default player. A packaged
destination needs its own explicit enable/build/cooked checks.

Configure a new AnimBlueprint through `scripts/ue5/configure_rac_contact.py` using
the actual engine-frame probe. `sample_source_sha256` binds the installed-mesh
export; the older `native_character_sha256` field remains supported for native
probes. Replace/bypass the old contact node in the derivative graph, then verify
only the intended contact node reaches the output after a fresh reload. The
retained `install_candidate.py` is Ennix's exact graph adapter.

Eight actual-game cases at each rate show <0.001 cm planted-ankle XY excursion,
positive observed sole gaps, unchanged movement path/leg lengths and clear sampled
hands/body. Four fixed camera angles and paired turn-to-idle/walk/reversal movies
are in the turn case's `presentation/review.html`. All 212 original game files
remain unchanged. See `docs/evidence/ennix-turn-20261023.json`; human visual,
cooked and performance acceptance remain separate.
