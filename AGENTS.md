# Agent instructions

`CLAUDE.md` is the rulebook for every agent: workstation routing, the resume
protocol, and the non-negotiable rules, including the binding reconstruction
boundary (the approved image must condition an AI geometry or mapping stage;
Blender starts only after AI acquisition). Read it first; this file adds only
the operational notes it does not carry.

## Where to start

1. `docs/STATUS.md`: the current asset matrix, exact artifact paths, and the
   next unresolved gate per asset.
2. `docs/AGENT_TASKS.md`: scoped open work with acceptance criteria, split into
   tasks that need no GPU and tasks that do.
3. `docs/PIPELINE.md` and `docs/WORKFLOW_PLAYBOOK.md` as the task needs them.
4. `docs/DECISIONS.md`: what failed and why. Do not repeat it.
5. `docs/HANDOFF.md` only for history. It is chronological; the newest entry is
   last. `docs/GETTING_STARTED.md` says what a machine needs.

## Operating notes

- Legacy generated outputs under `${RAC_LEGACY_ROOT}` are evidence, not source
  code to copy wholesale. Preserve dirty worktrees and open creative
  applications. Do not use linked worktrees.
- Do not launch GPU inference until GPU ownership and free VRAM are known
  (`nvidia-smi`; thresholds are in MiB in the launchers). Do not auto-retry
  crashes; record them.
- Advance exactly one visible gate per asset at a time, in the order of the
  stage table in `docs/PIPELINE.md`. Store accepted and rejected evidence with
  hashes and concise reasons. Never label an asset production-ready from a
  render or import alone.
- Record outcomes as a dated entry appended to `docs/HANDOFF.md` and update
  `docs/STATUS.md` in place; add a lesson to `docs/DECISIONS.md` when something
  surprising happened.

## Without a GPU

Everything except the two AI stages runs on CPU: the ledger and audit, prop and
pre-rigged character compiles, retopology and UV transport, the free landmark
rig, deformation tests, fixed-view renders, UE import verification, the gallery
build and retarget, and every test. If the GPU is owned by another workload,
say so in your report and skip only `run_hy3d_geometry.ps1` and
`run_hy3d21_texture.ps1`.
