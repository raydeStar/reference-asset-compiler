# Changelog

Release notes live under `docs/releases/`; GitHub releases carry the same text
and any attached wheel.

## Unreleased

Faster AI stages: geometry generation is about 3× faster with a near-surface
volume decoder (meshes match to 0.008% of the diagonal), and studio paint
fills its two texture maps in parallel (byte-identical, about 40 s saved).

The geometry launcher starts again when run directly under Windows
PowerShell 5.1.

## v0.2.0 — 2026-10-30

RAC on a 12 GB GPU: geometry needs 8 GB (byte-identical meshes), studio-route
texture painting peaks under 10 GB at best quality (was 35–44 GB, spilling into
RAM) and runs faster, every AI run records its peak VRAM, and review renders can
use the CPU. Notes: [docs/releases/v0.2.0.md](docs/releases/v0.2.0.md).

## v0.1.2 — 2026-09-11

Stronger lineage and promotion guards, retained compile/bake attempts, consistent
Windows launchers, a shorter resume path and a runnable CC0 crate example.
Notes: [docs/releases/v0.1.2.md](docs/releases/v0.1.2.md).
Completion checklist: [docs/MAINTENANCE_REVIEW_2026-09-11.md](docs/MAINTENANCE_REVIEW_2026-09-11.md).

## v0.1.1 — 2026-09-11

Reliability maintenance for the existing Codex-operated workflow: audits
require every expected stage, failed prop exports stay failed, the installed
CLI works outside the checkout, the doctor gained route profiles, and local
verification matches CI. Notes: [docs/releases/v0.1.1.md](docs/releases/v0.1.1.md);
release: <https://github.com/raydeStar/reference-asset-compiler/releases/tag/v0.1.1>.

## workshop-2026-09-06

The Workshop Update: textures, rigging and the real UE 5.8 showcase (Ayric
v051 in the night workshop, walk GIF, provenance JSON). Release:
<https://github.com/raydeStar/reference-asset-compiler/releases/tag/workshop-2026-09-06>;
the dated record is in `docs/HANDOFF.md` under 2026-09-06.
