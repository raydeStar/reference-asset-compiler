# Cooked demo audit

Opt-in runtime evidence for the Sunset Workshop demo. This module is inert
unless the packaged executable receives `-RACDemoAudit`. It never runs in an
editor world and never modifies saved content. Normal play is unchanged.

The audit waits for rendering, checks the possessed Manny and separate sword,
uses engine-native movement input to walk toward the east collision boundary,
jumps and verifies landing, then captures the actual game and fixed room/window
cameras. This is programmatic cooked gameplay, **not physical keyboard testing**.
The paired window cameras share a direction and are 220 cm apart.

Add `-RACDemoAuditSky` to include a ninth, upward-looking skylight capture.
This extends the audit from 73 to 82 game seconds; the default eight-view audit
and all gameplay checks remain unchanged. Stars deserve an actual runtime receipt.

For a custom workshop pawn, supply `-RACDemoExpectedMesh=/Game/path/Asset.Asset`.
The audit requires that exact native mesh path; without it the Manny check
remains. `-RACDemoAuditCharacter` adds two full-character camera views and ends
at 102 game seconds. The portrait fixture returns the pawn to its starting
position after the movement tests; this reposition is not movement evidence.

During the audit only, walking speed is temporarily 120 cm/s so the walking
capture precedes wall contact. It is restored after that segment. A separate
check measures changing component-space foot positions during the stride;
moving a rigid mesh along with its capsule no longer passes as animation.
This does not replace visual deformation or foot-contact review.

For the modular Ayric avatar, also supply
`-RACDemoExpectedHeadMesh=/Game/path/Head.Head`. This requires exactly one
matching static head, attached to the skeletal `head` bone with matching world
position, rotation and scale during idle, walking, jump and landing. It also
records built LOD0 vertex/triangle counts for body, head and sword, requires
three components within 15,000 vertices / 20,000 triangles apiece and at most
60,000 triangles in total. These checks remain opt-in; they do not constrain
other characters or silently grant appearance approval.

Run a Development package with these additional arguments:

```text
-RACDemoAudit -RACDemoAuditExit -RACDemoAuditDir="C:/absolute/new/evidence-directory"
```

The output directory must not exist; old evidence is never overwritten.
`audit.json` includes individual checks, attachment samples and screenshot paths.
The caller must additionally bind the package/map/source hashes and visually
inspect the PNGs. A `PASS` does not grant human approval or asset production
readiness. Without `-RACDemoAuditExit`, the process remains open after the audit.

Build with the installed engine's `RunUAT.bat BuildPlugin`, passing this
`RacDemoAudit.uplugin`, a fresh `-Package` destination and `-TargetPlatforms=Win64`.
Install the resulting plugin into a validation project's `Plugins/RacDemoAudit`
and enable it in that project's descriptor before building the game. Do not
replace a user's existing plugin or modify an open project's configuration.

The game needs an explicit code-based Game target (and a matching Editor
target/module for project tooling). A Blueprint-only BuildCookRun can report
success while merely staging the plugin descriptor: its stock UnrealGame binary
does not contain this new runtime module. The first Sunset v018 package exposed
exactly that failure on launch. Preserve that rejected package and rebuild a
fresh archive with the explicit project target; do not call the standalone
BuildPlugin result proof that the game has linked the module.
