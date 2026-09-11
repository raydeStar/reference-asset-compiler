# Maintenance review completion — 2026-09-11

*Type: reference*

This tracks the accepted Fable review against the completed implementation.
It changes the existing agent-operated workflow, not asset approval decisions.
No UI or AI inference is part of this maintenance pass.

## Confirmed bugs

| Review item | Resolution | Verification |
|---|---|---|
| A1: passed stages overwritten | Explicit replacement, prior-ledger snapshot, downstream validation | `test_promotion_guards.py` |
| A2: texture hash chain / failed gate | Source retopology lineage plus actual FBX, maps and gate hashes; `ok: true` required | `test_promotion_guards.py`, `test_production_maintenance.py` |
| A3: token mechanical evidence | Concrete unwrap payload and static manifest/payload contracts | `test_promotion_guards.py`, `test_runtime_evidence.py` |
| A4: half-created workspace after invalid routing | Plan validation before copying the source | `test_promotion_guards.py` |
| A5: missing modeling hashes compare equal | Both sides must be SHA-256 values | `test_promotion_guards.py` |
| A6: invalid mascot backbone default | Default names registered `blender_custom_rig` | `test_planner.py` |
| A7: external path handling | Shared separator normalization and Windows/POSIX absolute-path recognition | `test_evidence.py`; foreign drives still require accessible files |
| A8: first matching receipt wins | Reject distinct active receipts; follow explicit native supersession; coalesce repeated paths | `test_evidence.py`, `test_runtime_evidence.py` |
| A9: PowerShell BOM receipts | Write UTF-8 without BOM; accept historical UTF-8 BOM on reads | `test_evidence.py`, PowerShell tests |
| A10: character compile deletes authority | Fresh attempt directory and complete new publication; existing destinations refused | `test_scripts_powershell_runtime.py` |
| A11: Blender failure reads stale reports | Shared exception exit flag, fresh outputs, checked exit codes; retained production attempts | `test_production_maintenance.py`, native fixture |
| A12: cp1252 Blender decoding | Explicit UTF-8 with replacement | `test_scripts_rac_env_blender.py` |
| A13: 5.1 stderr / unsupported switches | Bounded preference restoration, plain ordered failure objects | PowerShell parse and runtime tests |
| A14: hard-coded discovery | Shared compiler interpreter and Blender discovery, including moved wrappers | PowerShell tests |
| A15: second geometry attempt dead end | Reject an attempt inconsistent with the passed generation record before dispatch | `test_scripts_crank_attempt_guard.py` |
| A16: stale texture package reuse | Check current UV-authority and source-map hashes before reuse | `test_scripts_crank_attempt_guard.py` |
| A17: texture launch ownership and interrupted attempts | Shared GPU/queue guard, unambiguous device state, pre-launch execution receipt, retained-output refusal | Synthetic GPU-guard runtime test; no live inference |
| A18: Restricted execution policy | Explicit process-scoped `-ExecutionPolicy Bypass`, without changing machine policy | `test_scripts_crank_attempt_guard.py` |
| A19: resume overwrites approved views / recipes | Reuse complete view sets; reject partial sets and conflicting recipes; portable repository paths | Existing operator tests and code review |

## Hardening and integration

- Promotions check existing evidence integrity and serialize state updates.
  Retained JSON publication is atomic and exclusive, including concurrent
  recorders; an idempotent call preserves the original bytes.
- Articulated retopology requires an explicit deformation-topology attestation.
  The CLI accepts delegated authorization; an integration test records and
  promotes the resulting real receipt with its scoped review.
- Audit exit codes are documented accurately: a single-workspace audit tests
  ledger integrity; its `production_ready` field separately reports completion.
  Cohort success requires every member to be complete.
- Geometry preflight supports custom workspace roots. Evidence lookup,
  reviewer identities, hashing, child environments and Blender command creation
  share common helpers. The Windows GPU guard also covers the Pixal3D challenger.
- Short Blender operations have bounded timeouts. Isolated wheel dependency
  installation has a 600-second allowance; normal CLI checks remain bounded.
- Texture packaging validates map dimensions before writing. Blender calls use
  factory startup; doctor version checks no longer import `datetime.UTC` early.
- Real cohort integration tests replace mocked audit outcomes. Package version
  comes from `__init__.py`; Dependabot also proposes Python dependency updates.
- The production builder now emits the stricter texture bindings itself. It
  consumes already-reviewed retopology for ledgered assets and records only the
  mechanical unwrap stage. Budget trials remain separate; selection copies the
  measured winner instead of baking it again.
- Production publication refuses existing authorities. A bounded Windows
  sharing-lock retry applies only to a completed directory rename, never to an
  inference or compiler process. Failed staging directories remain available.

## Documentation and repository structure

- `STATUS.md` is the resume entry point; `HANDOFF.md` retains chronological
  history. `CLAUDE.md` carries the rules and `AGENTS.md` points to them.
- The shorter README keeps verified media, setup and the real operator route.
  Historical showcase details live in `SHOWCASE_HISTORY.md`.
- `PIPELINE.md` lists stages, receipts and human gates. The catalog is the
  canonical workflow registry; the duplicate routing table was removed.
- The document index links previously orphaned references and labels document
  types. Compiler/prop/setup descriptions now distinguish workstation assets
  from runnable examples and explain MiB thresholds and preflight placeholders.
- Thirteen retained wrappers/helpers moved to `scripts/experiments/`, with an
  index and corrected paths. Blender/Unreal modules remain together for sibling
  imports. Recursive PowerShell parsing includes the moved wrappers.
- A deterministic CC0 crate provides a fresh-clone compile target. Its initial
  face-colored texture failed the baked-light gate; the retained failure led to
  a neutral fixture, not a weaker gate. It passes a CPU compile/bake/package and
  FBX reimport with 12 triangles and 0.6 m height.
- Security reporting, a PR template and changelog are present. GitHub private
  vulnerability reporting is enabled. The previously merged branches were
  cleaned up by Fable; the separate checkout owning local `main` is preserved.

Validation logs and the synthetic native receipt are retained locally under
`output/fable-completion/`. No actual reference assets, model runners, recipes,
profiles, waivers or `docs/evidence/` approvals were changed. Missing bindings
in historical ledgers remain failures until supported by new reviewed evidence.
