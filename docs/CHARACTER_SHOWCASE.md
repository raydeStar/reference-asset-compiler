# Reproducible native character showcase

The README media stages the v051 character inside the finished night workshop,
not an AI-generated advertisement or a black-background studio. Still images
are copied byte-for-byte from Unreal screenshots. The saved room and original
materials remain intact. A temporary 3-lumen, 120 cm rectangular portrait fill
is declared in the recipe and public provenance; it is not saved to the map.
The GIF contains 24 evaluated poses across the actual 1.5-second walking cycle;
FFmpeg only palette-encodes those frames. It does not generate or interpolate
motion. This is an animation showcase, not a real-time performance measurement.

## Prerequisites

Use the existing local `work/ue5-validate/RacValidate.uproject`, its v051 assets,
and successful `work/sunset-workshop/evidence/cooked-ayric-v051/audit.json`.
These generated artifacts are not included in a source-only clone. See
[the handoff](HANDOFF.md) for acquisition and artifact history. The recipe refuses
an unsuccessful audit or a different skeletal mesh. It requires UE 5.8, Python
with Pillow, and an installed FFmpeg executable. ComfyUI and AI inference are
not required for capture or packaging.

Check GPU ownership before starting the editor, and preserve any open creative
application. Run from the repository root in PowerShell:

```powershell
$env:RAC_ROOT = (Get-Location).Path
$env:RAC_RIG_REVIEW = 'readme-showcase-my-review-v001'
$env:RAC_SHOWCASE_CONFIG = 'configs/showcase/ayric-workshop-v051.json'
$editor = 'C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe'
$project = Join-Path $env:RAC_ROOT 'work/ue5-validate/RacValidate.uproject'
$capture = Join-Path $env:RAC_ROOT 'scripts/ue5/capture_character_showcase.py'
Start-Process $editor -ArgumentList @($project, "-ExecutePythonScript=$capture", '-unattended', '-nosplash') -WindowStyle Hidden -Wait
python scripts/package_character_showcase.py work/sunset-workshop/evidence/readme-showcase-my-review-v001 docs/images/my-showcase-v001 --ffmpeg 'C:/path/to/ffmpeg.exe'
```

Use fresh output names. The capture uses an unsaved staging fixture in the
actual workshop with original materials; it saves no source asset or map. Adjust cameras,
resolution and sample count in a copied JSON recipe, not the source character.
All workshop stills use a retargeted idle pose.
The walking view includes the feet and attached equipment.

## Evidence before publication

The packager checks unique records, image hashes, a complete ordered cycle,
actual animation positions, moving foot bones, and attachment errors of no more than 0.1 cm.
It rejects duplicated walk images and checks the encoded GIF frame count and
duration. `provenance.json` binds the public files to the capture receipt, recipe
and separate packaged-runtime audit. Automated checks do not replace visual
review: inspect face, collar, both profiles, hands, feet and the full loop.

The README candidate has 36,437 vertices / 54,027 triangles across body, rigid
head and sword at LOD0. The packaged audit passed 18 checks, independently of
this editor capture. It is not a facial-animation or cloth demonstration.
The small close-up collar edge remains disclosed, and final neck appearance
still requires human approval. Publication does not advance an asset ledger.

Earlier black-background `readme-showcase` attempts are retained: v001 was loosely framed; v002
exposed reentrant screenshot callbacks producing duplicate portrait records.
The packager rejected that receipt. The capture now guards callback reentry.
v003 exposed frozen rendered poses despite changing animation timestamps:
Unreal's `OverrideAnimationData` evaluates immediately, so the live animation
position must be set before that call. v004 corrects the order and records bone
positions; packaging also rejects frozen feet. These are fresh captures, not
retroactively repaired receipts.

The subsequent `workshop-glamour` series uses the real room. v001 had no fill
and obscured the face; v002's 700-lumen fill and v003's 18-lumen fill were too
bright for the saved exposure. v004 uses only 3 lumens. Source textures were
not adjusted to compensate for staging light. The current README points to
`docs/images/ayric-workshop-v051`; earlier studio media is retained separately.

See [the canonical head and neck method](CHARACTER_HEAD_AND_NECK.md) for the
actual texture/geometry repair. Lighting a screenshot is not a texture repair—
even the butler cannot polish away topology.
