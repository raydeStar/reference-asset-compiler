# Claude Code entrypoint

This repository is the canonical, portable home of the Reference Asset
Compiler. It is operated by coding agents, so these documents are the operator
interface. Resume in this order:

1. [docs/STATUS.md](docs/STATUS.md): the current asset matrix, exact artifact
   paths, and the next unresolved gate per asset (rewritten in place).
2. [docs/AGENT_TASKS.md](docs/AGENT_TASKS.md): scoped open work with
   acceptance criteria, split by whether a GPU is needed.
3. [docs/PIPELINE.md](docs/PIPELINE.md) for the stage table and gates, and
   [docs/WORKFLOW_PLAYBOOK.md](docs/WORKFLOW_PLAYBOOK.md) for exact commands,
   as the task needs them.
4. [docs/DECISIONS.md](docs/DECISIONS.md): what failed and why. Do not repeat it.
5. [docs/HANDOFF.md](docs/HANDOFF.md) only for history; it is the append-only
   dated log. [docs/README.md](docs/README.md) indexes every document.

New to the machine? [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) says
what it needs. `AGENTS.md` holds the Codex-specific operational notes.

## Actual workstation routing

Do not infer tool roles from an aspirational architecture. The routing registry
with runner hashes is `workflows/catalog.json`; `workflows/README.md` explains
the bundle. The summary:

- Image-to-3D **geometry generation** defaults to the hash-pinned direct
  Hunyuan3D Python runners, executed from this repository's
  `workflows/geometry/hunyuan3d/` by `scripts/run_hy3d_geometry.ps1`. A request
  without `mode` runs multiview; `"mode": "single_view"` is chosen explicitly
  when only the picture exists. The launcher inspects a live ComfyUI queue only
  to avoid GPU contention. The preserved original ComfyUI graph at
  `workflows/geometry/comfyui/hy3d_final_cut.json` is historical and optional.
- Existing-mesh PBR **texturing** enters through `scripts/run_hy3d21_texture.ps1`,
  which hash-verifies and runs the studio copy of the Hunyuan3D-Paint 2.1 runner
  at `${RAC_LEGACY_ROOT}/scripts/run_hy3d21_pbr.py`. The bundled
  `workflows/texture/hunyuan3d21/` files are provenance copies; do not execute
  them directly or edit their path logic mid-experiment.
- TRELLIS.2 and IntrinsicAnything are isolated texture challengers, not the
  default; IntrinsicAnything is stopped.
- Humanoid rigging is `scripts/run_rig_candidate.ps1`: Auto-Rig Pro when the
  user's Blender has it, otherwise the free landmark rig in this repository.
- Blender performs topology/UV preservation, review, rigging, deformation,
  and export.
- The compiler normalizes, gates, packages, imports, and verifies existing
  authorities. It does not generate geometry, repaint textures, or author a
  fresh humanoid rig.

Run `scripts\workflow_doctor.ps1` (optionally `-Profile ledger|geometry|texture|ue`)
before asking the user what is installed. It reports the local routes without
launching inference. If the task is texture repair, do not reinstall ComfyUI
nodes or propose a ControlNet workflow; follow Stage 4 of the playbook and the
exact instruction in `docs/CLAUDE_RESUME_TEXTURES.md`.

The earlier experimental studio is the tree `RAC_LEGACY_ROOT` points at (a
separate, machine-local checkout that is not part of this repository). Recipes
name it as `${RAC_LEGACY_ROOT}/...`, never by absolute path, and `python
scripts/rac_env.py --all` reports whether it is set. It contains large generated assets,
licensed-tool integrations, Unreal content, and a dirty worktree. Treat it as
read-only evidence until a migration step explicitly names the files to copy.
Do not clean it, reset it, close interactive Blender/ComfyUI/Unreal processes,
or overwrite an authority candidate.

## Resume protocol

1. Inspect `git status`, disk headroom, active GPU jobs, and open DCC/engine
   processes before doing expensive work.
2. Run `scripts\verify.ps1` in this repository.
3. Read the current asset matrix and exact artifact paths in
   `docs/STATUS.md`; consult `docs/HANDOFF.md` only when you need the history
   behind an entry.
4. Choose one unresolved acceptance gate. Do not blur modeling, texturing, and
   rigging into one pass.
5. Preserve source hashes, commands, settings, versions, fixed-view evidence,
   and rejection reasons.
6. Never claim production readiness without deformation evidence and a cooked
   UE5 runtime result. `rac audit` exits 0 for an intact ledger (check the
   separate `production_ready` field), 1 for failed integrity, and 2 for usage
   errors. `rac cohort-audit` exits 0 only when every asset is production-ready;
   an incomplete or failed cohort exits 1, and usage errors exit 2.

## Non-negotiable rules

- The approved source image is the artistic contract.
- Image reconstruction must begin with image-conditioned AI geometry or
  mapping. Never inspect a reference and manually or procedurally rebuild an
  approximation in Blender. Blender begins only after AI acquisition, for
  cleanup, retopology, UV/bake work, rigging, deformation, and verification.
- AI systems propose isolated candidates; visual gates select them.
- Modeling is approved before texturing, and texturing before rigging.
- A humanoid must target the declared UE skeleton contract, not a merely
  similar or randomly generated hierarchy.
- Facial texture landmarks must align with the modeled eye sockets, nose, and
  mouth. Reject stamped, doubled, or displaced features.
- Fixed front, three-quarter, side, and back views are required. A good front
  view cannot conceal a broken side.
- Preserve accepted authorities. Make repairs as versioned derivatives.
- Record failures. Do not silently retry a crashed inference.
- Human gates stay human; the list is the stage table in `docs/PIPELINE.md`.

The handoff documents contain operational decisions and evidence, not private
model reasoning. They are intended to let any capable coding agent resume the
work without repeating the same failed experiments.
