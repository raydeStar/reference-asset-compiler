# Workflow bundle

This directory closes the gap between the compiler and the actual generation
tools used during the reference-studio experiments. The compiler under
`scripts/` starts after an authority mesh/FBX and textures exist. These files
show how candidates were generated or painted before that point.

Read [the workflow playbook](../docs/WORKFLOW_PLAYBOOK.md) before running any
GPU stage. Run `scripts\workflow_doctor.ps1` first; it is read-only and does
not launch ComfyUI, Blender, inference, or Unreal.

## Routing summary

| Need | Default on this workstation | Alternative | Never assume |
|---|---|---|---|
| Initial image-to-3D geometry | Original Hunyuan3D ComfyUI graph, stopped at `Hy3DExportMesh`; compare against Pixal3D | Pixal3D wrapper | That ComfyUI is the texture production path |
| Existing-mesh PBR texture | Hunyuan3D-Paint 2.1 source-locked runner | TRELLIS.2 isolated challenger | That either candidate is accepted without fixed-view review |
| Humanoid rig | User-supplied Auto-Rig Pro in a compatible Blender, followed by compiler gates | AniGen challenger | That the compiler authors a new rig |
| Mascot rig | Explicit custom Blender skeleton/profile | AniGen challenger | That Manny is suitable for a fox or arbitrary creature |
| UE5 packaging | `scripts\compile_asset.ps1`, then UE import/verify/cook | none | That an FBX import alone is production proof |

## Included provenance copies

The files are exact copies of tested or historically important entrypoints.
Their source hashes are recorded in `catalog.json`. Upstream projects, model
weights, licensed add-ons, and generated assets are intentionally not bundled.

- `geometry/comfyui/hy3d_final_cut.json` — the user's original 64-node graph.
- `geometry/pixal3d/run_pixal3d.py` — alpha-locked Pixal3D candidate wrapper.
- `texture/hunyuan3d21/` — topology/UV-locked Hunyuan3D-Paint 2.1 runner and
  Windows rasterizer patch.
- `texture/trellis2/` — topology/UV-locked TRELLIS.2 challenger.
- `rigging/anigen/run_anigen_candidate.py` — immutable rig challenger wrapper.

Do not edit the provenance copies to make a local run pass. Add a versioned
wrapper or patch beside them and record the new hash and decision.
