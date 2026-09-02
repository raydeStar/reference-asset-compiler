---
name: reference-asset-compiler
description: Run or extend an evidence-gated reference-image-to-game-ready-3D workflow in a Reference Asset Compiler repository. Use for asset intake, AI candidate routing, modeling or texture approvals, rig validation, UE5 runtime proof, retention, and repeatable batch production. Do not use for freeform Blender modeling outside this repository contract.
---

# Reference Asset Compiler

Treat the approved source image as immutable artistic authority. AI systems
produce isolated candidates; they never promote themselves.

Before acting:

1. Read the asset's `intake.json`, `routing.json`, and `state.json`.
2. Inspect active Blender, ComfyUI, Unreal, GPU, and disk state before launching
   local inference or cleanup.
3. Read the relevant profile in `profiles/` and only the stage guidance needed
   from `docs/PIPELINE.md`.

Preserve these invariants:

- do not texture or rig before fixed-view modeling approval;
- do not overwrite source references, authority meshes, or prior candidates;
- treat silhouette metrics as regression evidence, not artistic approval;
- keep geometry, texture, articulation, and runtime selection independent;
- require an explicit skeleton profile for nonstandard articulated assets;
- do not claim production readiness without deformation and cooked-runtime
  evidence;
- do not auto-retry crashed inference or kill user processes for VRAM;
- delete only explicitly rejected, reproducible artifacts not referenced by the
  ledger.

Use `rac promote` only after the corresponding human or technical review was
actually performed, and attach the exact evidence files reviewed. Run
`rac audit` before reporting stage status or readiness.

For detailed evidence expectations, read
[references/gates.md](references/gates.md). For adapter boundaries, read
`docs/ADAPTERS.md` in the repository root.
