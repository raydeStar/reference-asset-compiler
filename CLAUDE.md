# Claude Code entrypoint

This repository is the canonical, portable home of the Reference Asset
Compiler. Start with [docs/HANDOFF.md](docs/HANDOFF.md), then read
[docs/WORKFLOW_PLAYBOOK.md](docs/WORKFLOW_PLAYBOOK.md),
[docs/PIPELINE.md](docs/PIPELINE.md), and
[docs/DECISIONS.md](docs/DECISIONS.md).

## Actual workstation routing

Do not infer tool roles from an aspirational architecture:

- ComfyUI is used for image-to-3D **geometry generation** here. The preserved
  original graph is `workflows/geometry/comfyui/hy3d_final_cut.json`.
- Existing-mesh PBR **texturing** uses the isolated Hunyuan3D-Paint 2.1 runner
  in `workflows/texture/hunyuan3d21/`.
- TRELLIS.2 is an isolated texture challenger, not the default.
- Blender performs topology/UV preservation, review, rigging, deformation,
  and export.
- The compiler normalizes, gates, packages, imports, and verifies existing
  authorities. It does not generate geometry, repaint textures, or author a
  fresh humanoid rig.

Run `scripts\workflow_doctor.ps1` before asking the user what is installed.
It reports the local routes without launching inference. If the task is texture
repair, do not reinstall ComfyUI nodes or propose a ControlNet workflow; follow
Stage 4 of the playbook and the exact instruction in
`docs/CLAUDE_RESUME_TEXTURES.md`.

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
   `docs/HANDOFF.md`.
4. Choose one unresolved acceptance gate. Do not blur modeling, texturing, and
   rigging into one pass.
5. Preserve source hashes, commands, settings, versions, fixed-view evidence,
   and rejection reasons.
6. Never claim production readiness without deformation evidence and a cooked
   UE5 runtime result.

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

The handoff documents contain operational decisions and evidence, not private
model reasoning. They are intended to let any capable coding agent resume the
work without repeating the same failed experiments.
