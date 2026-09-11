# Contributing

Keep changes small, evidence-backed, and profile-specific. A new adapter must
describe its capability without claiming quality. A new articulated profile
must include an explicit skeleton map, deformation suite, export contract, and
runtime acceptance evidence.

Run before submitting:

```powershell
.\scripts\verify.ps1
```

The wrapper selects `.venv`, then Python 3.12/3.11, then PATH. Pass `-Python`
to select explicitly, or run `python scripts/verify.py` with your active
interpreter. `-WheelDir dist` keeps the verified wheel for inspection.

Generated assets, model weights, licensed add-ons, Unreal content, and local
paths do not belong in commits. Tests should exercise contracts and observable
state, not exact prose.

## Where to start

- `docs/AGENT_TASKS.md` lists scoped open work with acceptance criteria and
  says which tasks need a GPU. Most do not. `docs/STATUS.md` is the current
  state; `docs/README.md` indexes every document by type.
- `AGENTS.md` and `CLAUDE.md` hold the rules every change is measured against.
- Pull requests use `.github/PULL_REQUEST_TEMPLATE.md`; paste the
  `RAC_VERIFY_OK` line. Security reports follow `SECURITY.md`.
- Something did not run on your machine? Open an issue with the *It did not run
  on my machine* form. It asks for the read-only `scripts\workflow_doctor.ps1`
  report, which is usually enough to diagnose without a follow-up question.
  Results, questions and ideas go to
  [Discussions](https://github.com/raydeStar/reference-asset-compiler/discussions).
- Local verification and CI both call `scripts/verify.py`: pytest, Ruff over
  `src`, `tests` and `scripts`, stage parsing, wheel build, then an installed CLI
  smoke test outside the checkout in an isolated environment with its declared
  dependencies. CI runs this sequence on Python 3.11 and 3.12. No Blender,
  Unreal, model download, or GPU inference is needed for these checks.
- Use `workflow_doctor.ps1 -Profile ledger` for compiler setup, or select
  `geometry`, `texture`, `ue`, or `all`. Text and JSON have identical readiness
  and exit semantics; optional tools never block an unrelated route.
