# Current status

*Type: reference*

Last updated: 2026-09-11. This file holds the current state only and is
rewritten in place. History is in [HANDOFF.md](HANDOFF.md) (append-only,
dated); failures and retained lessons are in [DECISIONS.md](DECISIONS.md);
scoped open work is in [AGENT_TASKS.md](AGENT_TASKS.md). The stage names below
are the ledger stages listed in [PIPELINE.md](PIPELINE.md#ledger-stages).

Every `work/`, `out/` and `output/` path here is on the development workstation
and ignored by Git. Nothing in this repository is production-ready; the
checked-in cohort snapshot (`docs/evidence/v1-cohort-audit-current.json`)
truthfully reports 0 of 7 assets ready.

## Ledger cohort (`configs/v1-cohort.json`)

| Asset | Kind | Passed through | Next unresolved gate | Waiting on |
|---|---|---|---|---|
| `orange-adventurer-cat-ai-v2` | mascot | `ue5_import` (rig, deformation and headless UE import recorded; idle retargeted in the gallery) | `ue5_motion_review` | **Mark, in the engine.** Then `cook`. |
| `office-chair-ai-v2` | static_prop | Modeling, retopology and texture passed by Ayric; UE import passed (`docs/evidence/office-chair-ai-v2-ue-import-v1.json`) | `ue5_runtime_review` | **Mark, live editor and frame.** `cook` stays blocked until then. |
| `field-scout-female-ai-v4` | humanoid | `semantic_cleanup` | `production_retopology` | A guide- or landmark-aware quad route; every challenger so far is rejected (`docs/evidence/field-scout-female-v4-retopology-trials-v1.json`). Texture is a separate open rejection. |
| `field-scout-male-ai-v2` | humanoid | `generate_candidates` (Hunyuan multiview source hash-bound) | `modeling_approval` | **Mark**, on the fresh 70k derivative. The legacy runtime FBX has no receipt chain and stays regression evidence. |
| `ninja-man-ai-v3` | humanoid | `generate_candidates` | `modeling_approval` (rejected: mask, vest, wraps, boots, hands and feet lost) | A new image-conditioned acquisition. Do not rebuild the details in Blender. |
| `weathered-longsword` | static_prop | intake and route | `modeling_approval` | A formal pass through the static gates; the earlier candidate was "generally acceptable" but never ratified. |
| `sunburst-guitar-ai-v2` | static_prop | intake and route | `generate_candidates` | GPU. The earlier geometry and paint were rejected as rudimentary. |

The checked-in cohort snapshot predates the cat's membership (it still names
`fox-mascot-ai-v3`, retired by Ayric on 2026-09-01) and the chair's texture and
import receipts. Refresh it on the workstation with
`rac cohort-audit configs\v1-cohort.json --workspace-root work` before quoting
per-stage numbers. Exit 0 means every member is production-ready, 1 means the
cohort is intact but incomplete, 2 means usage error or `RAC_ERROR`.

Cat artifacts: recipe `recipes/orange-adventurer-cat-ai-v2-production.json`,
package `out/orange-adventurer-cat-ai-v2-production/`, ledger
`work/orange-adventurer-cat-ai-v2/state.json`, evidence
`docs/evidence/orange-adventurer-cat-ai-v2-*.json`. It carries Ayric's
texture waiver for texel density (about 20 texels/cm²) and confetti UV islands.

Chair artifacts: `work/office-chair-ai-v2` (1.019 m, 18,000 triangles, 4096
BaseColor parent at 427.8 texels/cm²), placed in `/Game/Compiled/L_RacGallery`.

## Sunset workshop and Ayric (scene demo, outside the cohort ledger)

Launcher: `scripts/play_workshop_demo.ps1 -Lighting <Night|Day|Ayric|AyricLegacy>`
on the workstation with its saved packages. Night (v026) is the default.

| Item | Current candidate | State | Waiting on |
|---|---|---|---|
| Ayric character | v051: `/Game/SunsetWorkshop/L_WorkshopNight_v051`, package `output/sunset-workshop-ayric-v051/Windows` | All 18 cooked checks pass (movement, collision, jump, attachments, native budgets). Body 12,574 v / 16,039 t; head 12,740 / 19,988; sword 11,123 / 18,000; LOD0 total 36,437 / 54,027. | **Mark: approve or reject the v051 neck.** A collar edge is visible close up; do not call it welded. `AyricLegacy` keeps v036. |
| Ayric body texture | `work/sunset-ayric-v2/prod-calibrated-v001` via `recipes/sunset-ayric-v2-production.json` | Fails baked-light correlation (-0.24 against 0.12); shipped under a waiver marked PROVISIONAL in Ayric's name. `texture_approval` is pending in the ledger. | **Mark: confirm or revoke the waiver** after in-engine review. Face/surface correspondence concern remains open; no further blind painter retries. |
| Ayric head | `/Game/Compiled/SunsetAyricRigidHeadV1Production/sunset-ayric-rigid-head-v1-production` | Image-conditioned head; texture gate passed without waiver (agent-delegated, head-only); native UE import and static review passed. | Nothing separate; judged as part of v051. |
| Ayric body mesh | `/Game/SunsetWorkshop/RigRepairs/neck_transfer_v012/ayric_body`, source `work/sunset-ayric-v2/rig/neck-transfer-v008` | v036 anatomical rig and animations shared; neck transfer replays exactly (`docs/CHARACTER_HEAD_AND_NECK.md`). | Hand roll under the retargeted idle is a known open item. |
| Manny demo | Day v018 (`output/sunset-workshop-demo-v018-r2/Windows`), Night v026 (`output/sunset-workshop-night-v026/Windows`) | Both cooked; 13 editor and 12 packaged checks pass. No physical-keyboard test is claimed. | Complete as a local demo. |
| Plant | `out/sunset-plant-production`; native-v002 material fix in `/Game/SunsetWorkshop/Optimized/` | Texture passed (delegated); native-v001 import receipt passed but is visually rejected for a bumpy normal; native-v002 removes it but is not a ledger revision. | A warmed native review and an explicit material-derivative lineage. |
| Sofa | `work/sunset-sofa` `prod-region-v009` | Passes texture and four-view native review; `prod-delighted-v004` rejected. | Nothing open for the demo. |
| Sword (scene) | Attached to Ayric in v051 | Native import (1.35 m, 11,123 LOD0 vertices) and six-frame static review passed; attachment error zero in the cooked audit. | Nothing open for the demo; the cohort `weathered-longsword` ledger is separate. |
| IntrinsicAnything albedo challenger | `workflows/texture/intrinsicanything/` | Stopped after three bounded failures (`docs/ESCALATE-sunset-lighting.md`). | Not to be resumed without a different method. |

## Workstation-bound facts

- The GPU was owned by the user's other project on 2026-09-11; no inference
  was launched for the maintenance release. Check `nvidia-smi` before any AI
  stage. Thresholds are MiB: 21,504 for paint, 12,288 single-view, 18,432
  multiview geometry.
- AI stages need the studio tree named by `RAC_LEGACY_ROOT`
  (`docs/AI_STAGES_SETUP.md`). Run `scripts\workflow_doctor.ps1 -Profile
  geometry|texture` to see what is present without launching anything.
- The head fit and neck transfer used no GPU; they replay on CPU with
  `scripts/run_neck_transition.ps1`.
- Open interactive Blender, ComfyUI and Unreal sessions may own files under the
  studio tree. Preserve them.

## Decisions that need the user (Mark / Ayric)

1. v051 neck: approve or reject.
2. Ayric body texture waiver: confirm or revoke.
3. Cat `ue5_motion_review` in the gallery.
4. Chair `ue5_runtime_review` in the gallery.
5. Female retopology route and male modeling approval on the 70k derivative.

Until those land, no ledger promotion, no "production-ready" wording, and no
relabelling of a retained failure as a pass.

## Release state

`v0.1.2` completes the follow-up maintenance review; notes in
[releases/v0.1.2.md](releases/v0.1.2.md) and the
[completion checklist](MAINTENANCE_REVIEW_2026-09-11.md).
`v0.1.1` was the first reliability maintenance release, and
`workshop-2026-09-06` carries the workshop showcase. Root `CHANGELOG.md` links them.

The follow-up maintenance review strengthens receipt requirements. The asset
matrix above summarizes recorded history, not a fresh certification under those
requirements. Re-audit a workspace before resuming it; missing legacy bindings
must be resolved with evidence, not by relabeling the old record as passed.
