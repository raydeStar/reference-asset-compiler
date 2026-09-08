# Nightfall at the workshop

Verified local night variant, 2026-09-05. Daytime v018 remains intact.

```powershell
./scripts/play_workshop_demo.ps1 -Lighting Night
./scripts/play_workshop_demo.ps1 -Lighting Day
```

Night is the default. WASD moves, mouse looks, Space jumps, Alt+F4 exits.
The launcher refuses missing packages/review receipts and does not close existing
games. Normal play never receives the audit flag.

## Lighting and atmosphere

Warm bench/seating pools, broad cool window fill, quieter exterior lighting,
post-processing and a star sky. All 169 original static-mesh actors retain their
meshes, materials, collision profiles and transforms. Manny, his separate sword
and game mode remain unchanged. One non-colliding Engine sky sphere is added.

The user rejected the first tall rounded dust cloud. Final local fog has zero
radial density, height density 0.5, UI falloff 1200 (shader falloff 12), and centers
at Z=-280 cm above a desert floor at Z=-400 cm. Its warm emissive term is
(0.0001, 0.000075, 0.000045). Global fog density is 0.012, height falloff 1.2.
This is deliberately very faint ground-weighted haze, not a particle sandstorm.

The stock star texture candidate was rejected for stretched specks. Final stars
are deterministic direction-space shader points on the existing Engine sky
sphere, with horizon fade and exposure compensation, added to SkyAtmosphere
luminance. No new bitmap, AI geometry, model downloads or custom-character work.

## Actual verification

- Map: `/Game/SunsetWorkshop/L_WorkshopNight_v026`.
- Map SHA-256: `9c6275ad0234c279939c2f8f942691a19e7bbed6410ab224c508356be2988e5c`.
- Package: `output/sunset-workshop-night-v026/Windows`.
- Size: 1,132,895,624 bytes across 48 files, excluding generated Saved files.
- Clean Win64 Development build/cook/archive: zero cook errors/warnings.
- Twelve packaged programmatic gameplay checks pass; all nine actual 1600x900
  frames inspected, including paired window views and the upward skylight.
- Fresh repository verification: 183 tests plus routing checks pass.

Physical keyboard testing is not claimed. These are agent visual judgments,
not invented human approval or individual-asset production certification.

## Evidence and reproduction

Under `work/sunset-workshop/evidence/`: `night-review-v026.html` shows cooked
imagery and before/after; `night-review-v026.json` hashes the package and evidence.
`cooked-night-v026-audit/audit.json` lists gameplay checks;
`night-v026-invariants.json` compares objects; `night-v026-dust.json` records fog;
`night-dust-user-correction.json` binds the user's request and screenshot hash.

Retained drivers under `work/sunset-workshop/`: `night_v026.py`,
`review_night_v026.py`, `verify_night_v026.py`, `cook_night.ps1 -Version v026`,
and `finalize_night_v026.py`. Existing maps, archives and receipts are never
overwritten; choose fresh versions for further iterations.

Runtime review uses `-RACDemoAudit -RACDemoAuditSky -RACDemoAuditExit` and a fresh
absolute `-RACDemoAuditDir`. Sky adds a ninth view and extends the run to 82 game
seconds. The module is inert without the audit flag. Canonical source:
`integrations/ue5/RacDemoAudit`.

Rejected candidates, daytime package, open day game and parked Ayric work were
preserved. No git commit/push or cleanup was part of this pass.
