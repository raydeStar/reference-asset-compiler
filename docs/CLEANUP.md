# Retention and cleanup

Image-to-3D work can consume hundreds of gigabytes quickly. Cleanup is a stage,
not an emergency ritual performed after the disk fills.

Retain:

- immutable source references and hashes;
- selected authority meshes;
- approved production topology and textures;
- final rig/export packages;
- approval ledger and validation evidence;
- adapter version, settings, seed, logs, and final hashes;
- one compact rejection record when it teaches a reusable lesson.

Remove after explicit rejection:

- reproducible intermediate meshes and redundant renders;
- duplicate texture candidates;
- temporary FBX/OBJ round-trip files;
- abandoned virtual environments and model caches not shared by active jobs;
- UE Derived Data, Intermediate, and Saved output when no process owns it.

Never remove files referenced by `state.json`, an approved authority, user
source assets, active process working directories, or shared model caches
without verifying ownership. Measure free space before and after material
cleanup and record what was removed.
