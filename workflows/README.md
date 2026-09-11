# Workflow bundle

This directory closes the gap between the compiler and the actual generation
tools used during the reference-studio experiments. The compiler under
`scripts/` starts after an authority mesh/FBX and textures exist. These files
show how candidates were generated or painted before that point.

Read [the workflow playbook](../docs/WORKFLOW_PLAYBOOK.md) before running any
GPU stage. `scripts/workflow_doctor.ps1 -Profile ledger` checks the compiler
without launching inference or creative applications. Broader profiles inspect
their own dependencies; the `all` profile may run short Blender add-on probes.

[`catalog.json`](catalog.json) is the canonical routing and runner-hash registry.
Its `workstation_contract` identifies the defaults and challengers; each workflow
entry gives its deployment path and promotion boundary. Command recipes live in
[`docs/WORKFLOW_PLAYBOOK.md`](../docs/WORKFLOW_PLAYBOOK.md). There is no second
hand-maintained routing table here to disagree with the registry.

## Included provenance copies

The files are exact copies of tested or historically important entrypoints.
Their source hashes are recorded in `catalog.json`. Upstream projects, model
weights, licensed add-ons, and generated assets are intentionally not bundled.

- `geometry/comfyui/hy3d_final_cut.json` — the user's original 64-node graph.
- `geometry/hunyuan3d/run_hy3d_multiview.py` — the source-locked Hunyuan3D-2mv
  geometry runner that `scripts/run_hy3d_geometry.ps1` hash-pins and runs in
  place (no studio copy).
- `geometry/hunyuan3d/run_hy3d_single_view.py` — the single-image Hunyuan3D-2
  runner for requests with `"mode": "single_view"`; run in place likewise.
- `geometry/pixal3d/run_pixal3d.py` — alpha-locked Pixal3D candidate wrapper.
- `texture/hunyuan3d21/run_hy3d21_pbr.py` — topology/UV-locked Hunyuan3D-Paint
  2.1 runner. This one is copied byte-for-byte to the studio and verified there.
- `texture/hunyuan3d21/patch_hy3d21_windows.py` — Windows rasterizer build patch.
- `texture/hunyuan3d21/run_hy3d21_hires.py` — a retained variant that loads the
  mesh without vertex merging and saves the 4096 atlas without downsampling.
  Provenance for the female texture experiment; not the launcher default.
- `texture/trellis2/` — topology/UV-locked TRELLIS.2 challenger.
- `texture/intrinsicanything/` — README and pinned requirements for the
  IntrinsicAnything albedo challenger, stopped on 2026-09-05 after three bounded
  failures (see its README and `docs/ESCALATE-sunset-lighting.md`).
- `rigging/anigen/run_anigen_candidate.py` — immutable rig challenger wrapper.

Do not edit the provenance copies to make a local run pass. Add a versioned
wrapper or patch beside them and record the new hash and decision.
