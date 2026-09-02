# Exact resume instruction: texture stage

Paste or point Claude Code to this file:

> Work in your clone of this repository. Read
> `CLAUDE.md`, `docs/WORKFLOW_PLAYBOOK.md`, `docs/ESCALATE-textures.md`, and
> `workflows/catalog.json` before acting. Run
> `scripts\workflow_doctor.ps1`; it is read-only. Do not use ComfyUI for this
> texture task, do not install ComfyUI nodes, and do not invent a ControlNet or
> IP-Adapter path. On this workstation ComfyUI is the historical geometry
> generator. Existing-mesh texturing uses the tested, topology-locked
> Hunyuan3D-Paint 2.1 runner through `scripts\run_hy3d21_texture.ps1`.
>
> Preserve the current branch, the untracked
> `scripts/blender/reunwrap_rebake.py`, the legacy studio, open applications,
> and GPU-owning processes. Do not launch inference until `nvidia-smi` shows at
> least 21 GiB free VRAM, and do not kill processes. Do not auto-retry a crash.
>
> The remaining defect is upstream texture construction, not UE import or
> rigging. Build one reversible experiment using coherent semantic UV islands
> on the final-scale mesh, a de-lit authority, Hunyuan3D-Paint for the body PBR,
> and a head-only UV-aware identity transfer constrained to head geometry.
> Never stamp a whole face sheet onto the body atlas. Reject doubled eyes or
> scarf lines, the U-shaped chin artifact, face pixels on trousers, baked
> shadows, seams, and bright specks.
>
> First prove the method on the female, because she is the canonical failure.
> Produce unlit base-color and lit PBR front/three-quarter/side face closeups,
> plus full-body front/three-quarter/side/back comparisons against the approved
> authority. Do not alter the compiler, rigs, UE packages, or accepted assets
> until the texture review passes. Record exact inputs, hashes, command,
> environment, topology/UV validation, outputs, and rejection reason. If the
> method fails three bounded iterations, stop and write an evidence-backed
> escalation rather than continuing heuristic pixel repairs.

This instruction deliberately separates the already-verified compiler/UE
mechanics from the unresolved artistic texture stage.
