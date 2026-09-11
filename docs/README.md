# Documentation index

*Type: reference*

Every document under `docs/` carries a one-line `*Type: ...*` header under its
title. Reference documents describe how things work today and are corrected in
place. Logs are dated and appended, never rewritten. Experiments and
escalations are retained verbatim so nobody repeats them. Start with
[STATUS.md](STATUS.md) if you are resuming work.

## Reference

- [STATUS.md](STATUS.md) — current asset matrix, artifact paths, next gate per asset, what awaits the user.
- [GETTING_STARTED.md](GETTING_STARTED.md) — what a machine needs; fresh clone to a walkable UE5 gallery.
- [AGENT_TASKS.md](AGENT_TASKS.md) — scoped open work with acceptance criteria, split by GPU need.
- [PIPELINE.md](PIPELINE.md) — the ledger stage table, human gates, receipt schemas, and promotion rules.
- [WORKFLOW_PLAYBOOK.md](WORKFLOW_PLAYBOOK.md) — stage-by-stage commands from approved image to UE proof.
- [COMPILER.md](COMPILER.md) — what the compile, gate, production and UE import scripts do and why.
- [PROPS.md](PROPS.md) — the static-prop route and how it differs from characters.
- [AI_STAGES_SETUP.md](AI_STAGES_SETUP.md) — the studio tree the two AI stages need, measured sizes, geometry modes.
- [UE5_VALIDATION.md](UE5_VALIDATION.md) — the UE import, skeleton and runtime validation contract.
- [SCENE_TOOLS.md](SCENE_TOOLS.md) — atmosphere recipes, protected UE derivatives, portable review pages.
- [CHARACTER_HEAD_AND_NECK.md](CHARACTER_HEAD_AND_NECK.md) — source-locked head fit and repeatable neck transition.
- [CHARACTER_SHOWCASE.md](CHARACTER_SHOWCASE.md) — how the README captures and GIF are reproduced with provenance.
- [ADAPTERS.md](ADAPTERS.md) — adapter registry policy: capabilities, not quality rankings.
- [SKELETON-COMPATIBILITY.md](SKELETON-COMPATIBILITY.md) — measured compatibility of compiled skeletons with Epic's Manny.
- [CLEANUP.md](CLEANUP.md) — retention and cleanup rules for large generated trees.
- [LEGACY_MIGRATION.md](LEGACY_MIGRATION.md) — what may be copied from the `${RAC_LEGACY_ROOT}` studio, and what may not.
- [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md) — the end-to-end readiness measurement of 2026-08-31 and what it does not prove.
- [FROM-IMAGE.md](FROM-IMAGE.md) — the one-image-to-compiled-prop route and its recorded corrections.
- [CLAUDE_RESUME_TEXTURES.md](CLAUDE_RESUME_TEXTURES.md) — the exact agent instruction for the texture stage.

## Logs (dated, append-only)

- [HANDOFF.md](HANDOFF.md) — the operational log: every attempt, acceptance, rejection and path since 2026-08-30.
- [DECISIONS.md](DECISIONS.md) — accepted decisions, rejected approaches and retained lessons.
- [AYRIC_REPAIR_2026-09-06.md](AYRIC_REPAIR_2026-09-06.md) — the rig repair and bounded face work of 2026-09-06.
- [SUNSET_WORKSHOP.md](SUNSET_WORKSHOP.md) — the workshop scene study, prop jobs and demo status.
- [SUNSET_NIGHT.md](SUNSET_NIGHT.md) — the night lighting variant v026 and its evidence.
- [SUNSET_DEMO_COMPLETION.md](SUNSET_DEMO_COMPLETION.md) — the demo completion contract and its dated closure.
- [SHOWCASE_HISTORY.md](SHOWCASE_HISTORY.md) — status paragraphs and showcase notes moved out of the README.

## Experiments and escalations (retained verbatim)

- [EXPERIMENT-hy3d21-female.md](EXPERIMENT-hy3d21-female.md) — Hunyuan3D-Paint 2.1 on the female; rejected on quality.
- [EXPERIMENT-retopo-ninja.md](EXPERIMENT-retopo-ninja.md) — every ninja reduction fails head review; retopology rejected.
- [DEFECTS-CLOSEUP-REVIEW.md](DEFECTS-CLOSEUP-REVIEW.md) — three close-up defects, their causes and the false starts.
- [ESCALATE-textures.md](ESCALATE-textures.md) — the texture stage escalation shared by the four 2026-08 characters.
- [ESCALATE-sunset-face.md](ESCALATE-sunset-face.md) — why paint repair could not fix the Ayric face.
- [ESCALATE-sunset-lighting.md](ESCALATE-sunset-lighting.md) — the stopped IntrinsicAnything lighting route.

## Drafts

- [BLOG_DRAFT.md](BLOG_DRAFT.md) — a write-up of the cat's route; images reference `docs/images/`.

## Releases

- [releases/v0.1.1.md](releases/v0.1.1.md) — reliability maintenance release notes, 2026-09-11. Root `CHANGELOG.md` lists every tag.
- [releases/v0.1.2.md](releases/v0.1.2.md) — stronger evidence, safer reruns and the first compile example.
- [MAINTENANCE_REVIEW_2026-09-11.md](MAINTENANCE_REVIEW_2026-09-11.md) — the accepted review mapped to implementation and verification.

## Evidence and media

- `evidence/*.json` — compact, hash-bound checkpoints per asset; treat as data, do not edit by hand.
- `images/` — the README media, with `provenance.json` beside each showcase set.
