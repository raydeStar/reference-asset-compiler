# Legacy studio migration plan

The compiler repository is intentionally separate from the experimental
studio. Do not copy the entire `${RAC_LEGACY_ROOT}` tree: it
contains generated bulk, machine-local paths, licensed integrations, Unreal
derived data, and a valuable dirty worktree.

## What belongs in this repository

- portable manifests and schemas;
- adapter interfaces and capability declarations;
- reusable Blender/UE orchestration scripts after path removal and tests;
- fixed-camera and deformation test definitions;
- compact accepted/rejected evidence manifests with source hashes;
- documentation for licensed dependencies without redistributing them;
- deterministic cleanup and retention policies.

## What remains external

- model weights and Hugging Face caches;
- licensed Auto-Rig Pro files;
- Unreal Engine and DerivedDataCache;
- original user artwork unless its license explicitly permits redistribution;
- large generated meshes, textures, renders, and baked intermediates;
- machine-specific virtual environments and absolute-path configuration.

## Migration sequence

1. Freeze the current legacy checkpoint and record hashes for selected scripts
   and artifacts.
2. Port one workflow slice at a time, beginning with intake, candidate
   manifesting, and fixed-view review.
3. Replace hard-coded paths with configuration and dry-run support.
4. Add a small synthetic or redistributable fixture for every ported command.
5. Verify in a new `work/` asset workspace created by `rac new`.
6. Only then mark the legacy script superseded. Never delete the source merely
   because a port exists.

The first recommended slice is the fixed-camera Blender review plus the UE
subject-render helper. The female texture repair should remain an asset-level
experiment until its method is proven repeatable.
