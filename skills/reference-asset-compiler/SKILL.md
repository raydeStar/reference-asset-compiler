---
name: reference-asset-compiler
description: Run or extend an evidence-gated reference-image-to-game-ready-3D workflow in a Reference Asset Compiler repository. Use for asset intake, AI candidate routing, modeling or texture approvals, rig validation, UE5 runtime proof, retention, and repeatable batch production. Do not use for freeform Blender modeling outside this repository contract.
---

# Reference Asset Compiler

Treat the approved source image as immutable artistic authority. AI systems
produce isolated candidates; they never promote themselves.

Before acting:

1. Read `CLAUDE.md`, then `docs/STATUS.md` for the current gate per asset.
2. Read the asset's `intake.json`, `routing.json`, and `state.json`.
3. Run `scripts\workflow_doctor.ps1 -Profile ledger|geometry|texture|ue|all`
   (read-only) and inspect active Blender, ComfyUI, Unreal, GPU, and disk state
   before launching local inference or cleanup.
4. Read the relevant profile in `profiles/` and only the stage guidance needed
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

## The `rac` ledger CLI

`rac` (or `python -m reference_asset_compiler.cli` with `PYTHONPATH=src`)
has these subcommands today:

| Subcommand | Purpose |
|---|---|
| `new <asset_id> <reference> --kind <kind>` | Create an immutable-reference workspace under `work/` (`--articulation`, `--skeleton-profile`, `--rig-backbone`, `--adapter`, budgets) |
| `plan <intake.json>` | Generate a routing decision from an intake manifest (`examples/*.json` are samples) |
| `promote <job> <stage> --evidence ... --note ... --approved-by ...` | Record a reviewed stage with immutable evidence (`--status passed|rejected|blocked|in_progress`) |
| `audit <job>` | Verify source and evidence hashes plus stage order |
| `cohort-audit <manifest>` | Require every asset in a release cohort to be production-ready (`--workspace-root`) |
| `geometry-preflight <request> --legacy-root <studio>` | Validate a one-attempt Hunyuan geometry request before launch (`--repo-root` outside a source checkout) |
| `cleanup-preflight <job> <input_mesh>` | Verify an approved modeling mesh before cleanup |
| `cleanup-receipt <job> <input_mesh> <output_mesh> <topology_report>` | Freeze a conservative-cleanup receipt bound to its input and output |
| `retopology-receipt <job> <input_mesh> <output_mesh> <report> --view ... --approved-by ... --note ...` | Freeze a reviewed production-retopology receipt |

Exit codes: `audit` and `cohort-audit` return 0 when the ledger is complete,
1 when the audit or cohort fails, 2 for usage errors or `RAC_ERROR`.

Use `rac promote` only after the corresponding human or technical review was
actually performed, and attach the exact evidence files reviewed. Run
`rac audit` before reporting stage status or readiness. The stage names, human
gates, required receipt schemas and recording scripts are the table in
[docs/PIPELINE.md](../../docs/PIPELINE.md#ledger-stages).

For detailed evidence expectations, read
[references/gates.md](references/gates.md). For adapter boundaries, read
[docs/ADAPTERS.md](../../docs/ADAPTERS.md).
