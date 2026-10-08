# Retained experiments

These helpers remain available for replaying earlier experiments. They are not
the default acquisition, topology or texture route. Start with
[`docs/STATUS.md`](../../docs/STATUS.md) and
[`docs/WORKFLOW_PLAYBOOK.md`](../../docs/WORKFLOW_PLAYBOOK.md) for current work.
Moving a script does not turn a rejected candidate into an approved one.

The former top-level commands now live here:

- `audit_semantic_retopology_regions.ps1`
- `blend_ai_texture_region.py`
- `build_retopology_review_bundle.py`
- `canonicalize_feature_fairing_report.py`
- `canonicalize_paired_qem_report.py`
- `run_instant_meshes_reduction.ps1`
- `run_manifold_audit.ps1`
- `run_quadriflow_precondition_repair.ps1`
- `run_quadriflow_reduction.ps1`
- `run_regional_autoremesher_reduction.ps1`
- `run_semantic_instant_meshes_reduction.ps1`
- `run_smooth_review.ps1`
- `split_three_view_sheet.py`

Three Ennix one-offs moved here on 2026-10-08. They are historical, not part
of the character pipeline (`scripts/rebuild_character.py`, see
[`docs/CHARACTER_REBUILD.md`](../../docs/CHARACTER_REBUILD.md)), and are kept so
the early Ennix receipts stay explainable:

- `build_ennix_review.py`: the first head-only Ennix build, before the full
  character runner.
- `package_ennix_review.py`: zipped a 2026-10-07 Ennix delivery for review.
- `refine_ennix_landmarks.py`: measured Ennix's open hands and centreline for
  his rig landmarks once; the rebuild takes measured landmarks as a frozen
  input (`rig-landmarks.json`).

Run them using `scripts/experiments/<name>` from the repository root. Historical
handoff commands retain their original paths; use this directory when replaying
one. Interpreter discovery and other shared helpers still live in `scripts/`.
PowerShell parsing includes this directory in verification.

Blender and Unreal stage modules remain in `scripts/blender/` and `scripts/ue5/`:
some import siblings, and moving them independently would break those imports.
Modules such as `heal_mesh.py` and `screenshot_gallery.py` are retained utilities,
not a recommendation to use them for the next asset gate. Preserve old attempt
directories, and choose a new derivative when running an experiment.
