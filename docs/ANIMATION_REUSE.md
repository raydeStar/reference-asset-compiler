# Reusable animation authoring and contact integration

Use an existing accepted native rig and licensed motion. These commands create
new candidates and evidence; they do not acquire a character, replace bind data,
install game assets, or grant artistic approval. The initial coordinate contract
is UE-local centimetres, Z-up, xyzw rotations. Other conventions need an adapter.

## Three ways to use the workflow

1. **Installed CLI / Python:** `rac animation init`, `preflight`, `derive`,
   `measure`, `compare`, `compare-models`, `review`, `summary`, and `package`.
   Python callers can use `animation_profiles.create_recipe` and
   `animation_workflow` functions directly.
2. **Blender from a checkout:** run `scripts/anim/animation_pipeline.py run` for
   inspection, baseline measurement, bounded edits, candidate measurement,
   FBX/GLB export and reimport, exact model-payload comparison, and a review package.
   Individual `inspect`, `export` and `bake-library` commands remain available.
3. **Optional Unreal plugin:** `integrations/unreal/RACAnimation` provides the
   measured-sole contact node independently of TheAetherWars. Its runtime and
   editor modules build against UE 5.8. It requires an `ACharacter` owner,
   explicit leg/IK bone chains, measured skin samples and the destination's
   collision. See its README for installation and limitations.

The wheel contains the portable Python commands. Blender/Unreal scripts and the
Unreal plugin require the repository checkout and those applications. Source
assets are supplied separately; a Git clone does not contain private characters,
Quaternius archives, generated binaries or historical `work/` captures.

## Bind a profile to inputs

Examples are `profiles/animation/workflows/ennix.json` and `character02.json`.
They take explicit `NAME=PATH` inputs, with no environment-variable fallback.
Other profile paths resolve relative to the profile, even when its output lives
elsewhere. Unknown, duplicate or missing input names fail. Bound content is
hashed; the packet must identify the same native source. Copy a profile and
declare the new character, pose intent, clip names, operations, providers and
benchmark. Do not copy another character's contact targets or pose offsets as
an artistic prescription.

The supplied examples demonstrate a one-degree head-pose alternative on idle
and preserve walking. They deliberately make no quality/acceptance claim.
The Ennix example needs UAL1; Character02's full selected packet also declares
UAL2. `UAL1_LICENSE`/`UAL2_LICENSE` must be the supplied license evidence, not an
invented file. Retarget code and license paths already resolve inside RAC.

```powershell
rac animation init profiles/animation/workflows/ennix.json `
  --input "CHARACTER=$nativeBlend" --input "PACKET=$bakedPacket" `
  --input "UAL1=$ualFbx" --input "UAL1_LICENSE=$ualLicense" `
  --output work/my-ennix-recipe

python scripts/anim/animation_pipeline.py run work/my-ennix-recipe/recipe.json `
  --blender $blender --clips MM_Idle,MF_Unarmed_Walk_Fwd `
  --render-views --output work/my-ennix-review
```

Use a new output directory for every attempt. A failed attempt retains its log,
execution receipt and workflow receipt. It is never automatically retried.
`workflow.json` records technical completion; `model-comparison.json` requires
unchanged embedded geometry, UVs, weights, bind matrices, materials and images.
Both export formats are reimported and checked at every source frame. Quaternion
sign changes use the shortest orientation distance. Static bone attachments are
exported from a consistent bind pose so the selected first animation frame does
not alter their default transforms.

The review package contains the candidate exports, comparison receipts and
license evidence. It is not a complete source archive: the recipe retains hashes
and paths of externally supplied sources. Keep native source dependencies with
the native asset. Blender groom curves require the existing separate groom route;
GLB/FBX mesh checks do not certify Alembic groom export.

## Bake a new character's packet

The upstream retargeter is now present in this RAC checkout. No sibling
`rac-character` source checkout is required. Supply existing licensed libraries
and the character's already established game rig:

```powershell
& $blender --background --factory-startup $nativeBlend --python-exit-code 1 `
  --python scripts/anim/bake_library_clips.py -- `
  --profile profiles/animation/ual-to-ue-template.json `
  --library "ual1=$ualFbx" --clips MM_Idle,MF_Unarmed_Walk_Fwd `
  --out work/my-fresh-bake
```

The included UAL profile targets a Manny-compatible biped. Its stance settings
need review for each character's proportions and clothing. A new bake reproduces
the selected mapping and layers; it does not reconstruct later Character02
cleanup unless those operations and their exact input packet are also supplied.
The retained `repair_character02_*` and `install_character02_*` scripts document
that benchmark's repairs/migrations. They are not the generic entry point, and
hash-guarded one-time migrations must not be replayed against the current game.

`snapshot --project ... --config Tools/Characters/<name>.json` is available for
installed projects using the existing library-animation configuration contract.
Its older Character02 default remains for compatibility. Profiles plus `init`
are the route for characters that have not been installed in a game.

## Verification from a clean checkout

Clone the published revision into an ordinary independent directory. Do not copy
an old `work/`, editable installation, or local configuration into that checkout.
Create an isolated Python environment, install `.[dev,tools]`, and run:

```powershell
./scripts/verify.ps1 -Python $isolatedPython
```

This runs the full tests, lint, stage parsing, wheel build, and an installation
outside the checkout. The installed-wheel check executes a full mathematical
limb recipe through contact solving, measurement, comparison, pending review,
packaging and rejection of a tampered authority. That fixture checks portable
contracts; it is not substituted for a real second character.

Then run the two real character profiles with explicit licensed/source inputs.
The publication evidence records Character02 and Ennix separately, including
source hashes, exports and the exact checked revision. Tests do not approve the
animation's weight, appearance, responsiveness, terrain coverage or cooked game.

For the optional plugin's independent compile check:

```powershell
python scripts/check_unreal_animation_plugin.py --engine $unrealEngineDirectory `
  --output work/fresh-plugin-build
```

This creates its own small host project. It does not edit or rebuild an existing
game. `scripts/ue5/check_rac_contact_plugin.py` additionally exercises import,
configuration, repeat installation and a separate saved-graph reload in that
host using the explicitly supplied FBX and sole samples.
