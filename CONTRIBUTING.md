# Contributing

Keep changes small, evidence-backed, and profile-specific. A new adapter must
describe its capability without claiming quality. A new articulated profile
must include an explicit skeleton map, deformation suite, export contract, and
runtime acceptance evidence.

Run before submitting:

```powershell
.\scripts\verify.ps1
```

Generated assets, model weights, licensed add-ons, Unreal content, and local
paths do not belong in commits. Tests should exercise contracts and observable
state, not exact prose.

## Where to start

- `docs/AGENT_TASKS.md` lists scoped open work with acceptance criteria and
  says which tasks need a GPU. Most do not.
- `AGENTS.md` and `CLAUDE.md` hold the rules every change is measured against.
- Something did not run on your machine? Open an issue with the *It did not run
  on my machine* form. It asks for the read-only `scripts\workflow_doctor.ps1`
  report, which is usually enough to diagnose without a follow-up question.
  Results, questions and ideas go to
  [Discussions](https://github.com/raydeStar/reference-asset-compiler/discussions).
- CI runs pytest, ruff over `src`, `tests` and `scripts`, and a parse check of
  every Blender and Unreal stage. `scripts\verify.ps1` is the same contract
  locally; new scripts must pass ruff before they are pushed.
