# RAC Animation Contact

Optional MIT-licensed source plugin, tested with Unreal Engine 5.8. Unreal's SDK
and runtime remain separately licensed. Copy this folder into a destination
project's `Plugins/`, enable `RACAnimation`, and build that project's editor.
Keep the project closed while rebuilding. Do not replace a running project's
existing contact node by copying over its classes.

This plugin derives from the verified Character02 sole-contact implementation.
Its class names and modules are independent of TheAetherWars. Left/right chains,
action slot, plant curves, correction limits, release time, lock speed, measured
skin samples and optional grounded-combat montage are properties. Each chain
requires thigh, calf, foot and an independent IK-target bone; the owner must be
an `ACharacter`. It is not a quadruped, arbitrary control-rig or vehicle solver.

## Configure from measured geometry

1. Use RAC's `scripts/blender/extract_sole_samples.py` on the accepted native rig,
   with explicit foot/ball bone names if the Manny defaults do not apply. This
   selects low weighted vertices; it does not invent shoe dimensions or modify
   weights. Review the sampling band/cells for unusual feet or footwear.
2. Prepare a JSON contact profile with schema `rac.unreal-contact-profile.v1`,
   `anim_blueprint`, `native_character_sha256`, a `probe` path/SHA-256 binding,
   `chains` (four names for each of `l` and `r`), `plant_curves` (`l`/`r`),
   `clearance_cm`, `max_correction_cm`, `combat_max_correction_cm` and
   `release_time_s`. `grounded_combat_montage` and `action_slot` are optional.
   The isolated-host smoke test produces a complete working example profile.
3. In Unreal Python, import RAC's `scripts/ue5/configure_rac_contact.py` and call
   `install(profile_path, fresh_receipt_directory)`. It validates the sample
   binding, backs up the saved AnimBP, inserts/configures one final component-space
   node, compiles and saves. Repeated installation updates the same node; a fresh
   receipt directory is required. Existing unknown/multiple graph layouts fail.
4. Reload in a new editor process and verify the saved node and curves. Test the
   actual animated/skinned character and destination controller/collision.

The installer does not author support intervals, retarget clips or change the
movement controller. Without positive plant curves the horizontal lock stays
released. Author these curves from declared contact intervals, preserving heel
roll and swing. Active actions normally release contact; only the explicitly
selected montage opts into bounded upward combat correction. An upstream floor
rig's recovery blending remains the destination's responsibility.

## Cost, limits and preservation

Terrain traces run on the game thread; worker animation evaluation reads cached
planes. Queries cover distributed sole points, both directions of travel and
inner/outer footprint guards: at most 192 per character. The 15 cm query envelope,
45 cm upward / 180 cm downward rays and visibility collision channel currently
target human-scale characters in centimetres. Crowd cost, extreme scales, network
prediction and cooked/platform behavior need destination-specific measurement.

The shipped game continues using its existing Aether node. Creating/testing this
plugin does not migrate that saved AnimBP or alter the accepted game fixes.
Plugin compilation and configuration/reload checks are separate from runtime
animation acceptance; Character02's earlier gameplay receipts concern the
installed Aether implementation, not an in-game trial of this renamed plugin.

Run `scripts/check_unreal_animation_plugin.py` from the repository for a clean
minimal-host build. The `scripts/ue5/check_rac_contact_plugin.py` fixture imports
only into that disposable host and checks repeated installation and saved reload.
