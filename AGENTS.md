# Agent instructions

Read `CLAUDE.md` and `docs/HANDOFF.md` before changing the pipeline or legacy
assets. The repository contracts are authoritative; legacy generated outputs
are evidence, not source code to copy wholesale.

## Non-negotiable reconstruction boundary

The approved reference image must directly condition an AI geometry or mapping
stage. Never inspect the image and manually sculpt, trace, kitbash, or
procedurally rebuild an approximation in Blender. A visually plausible Blender
reconstruction is still a failed route when the image did not condition the AI
geometry. Blender starts only after AI acquisition, for cleanup, retopology,
UV/bake work, rigging, deformation, export, and evidence.

If AI acquisition fails, retain the rejection and repair or replace that AI
stage. Do not route around it with hand-authored geometry.

Keep work reversible and evidence-gated. Preserve dirty worktrees and open
creative applications. Do not use linked worktrees. Do not launch GPU inference
until GPU ownership and free VRAM are known. Do not auto-retry crashes.

For each asset, advance exactly one visible gate at a time: modeling, topology,
texture, rig/deformation, UE import, then cooked runtime. Store accepted and
rejected evidence with hashes and concise reasons. Never label an asset
production-ready from a render or import alone.
