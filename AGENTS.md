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

## Where to start

- `docs/GETTING_STARTED.md`: what a machine needs and the clone-to-gallery path.
- `docs/HANDOFF.md`: the current asset matrix, exact artifact paths, and the
  next unresolved gate. Read the tail first; it is chronological.
- `docs/AGENT_TASKS.md`: scoped open work with acceptance criteria, split into
  tasks that need no GPU and tasks that do.
- `docs/DECISIONS.md`: what failed and why. Do not repeat it.

## Without a GPU

Everything except the two AI stages runs on CPU: the ledger and audit, prop and
pre-rigged character compiles, retopology and UV transport, the free landmark
rig, deformation tests, fixed-view renders, UE import verification, the gallery
build and retarget, and every test. If the GPU is owned by another workload,
say so in your report and skip only `run_hy3d_geometry.ps1` and
`run_hy3d21_texture.ps1`.

