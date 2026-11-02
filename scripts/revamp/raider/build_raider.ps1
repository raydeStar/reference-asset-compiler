<#
.SYNOPSIS
  Rebuild the rigged, speaking Raider from the accepted parts, in one run folder.

.DESCRIPTION
  The recorded chain from the assembled body, the painted hand acquisition and the baked face to the final rigged
  FBX, its gate and deformation reports, review renders and the speech demo. Every stage writes under
  <Work>\build\<Run>\ and nothing outside it is overwritten, so accepted authorities stay as they are.

  Inputs (git-ignored, machine-local, made by the earlier stages in docs/RAIDER_REVAMP.md):
    <Work>\parts-v2\raider-parts-v2.blend            parts (modeling gate v2)
    <Work>\assembled\raider-v3.glb                    painted body with the painted head placed
    work\raider-hand-r\textures\paint-attempt001\raider-hand-r.glb   painted hand-only acquisition
    work\raider-hand-r\references\primary.png        and its crop; <Work>\hand-src\*.lineage.json
    <Work>\evidence\seg-proto\parts-v2.npy            the reference part map
    <Work>\prod\ue5_manny-hero.json                   resolved UE5 Manny profile, hero tier
    <Work>\face\bake-v15\face-baked.blend             the wrapped, baked speaking face (wrap_face.py, bake_face.py,
                                                      fix_neck_paint.py)
    <Work>\body-paint\attempt002-pbr\raider-body*     calibrated body paint (metallic, roughness, paint mesh) and
    <Work>\body-paint\attempt002-masks\painted-face-parts.*   its per-face part labels
    work\raider-head\textures\paint-attempt002-rough60\raider-head*   calibrated head paint
  Blender needs MPFB 2 with MakeHuman's CC0 system assets for the skin and face stages. ffmpeg muxes the video.

  Stages, in order: hands, production, materials, landmarks, fingers, rig, skin, face, shoulders, mouth, look,
  check, renders, speech. -From starts at a stage when the earlier ones are already in the run folder.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\revamp\raider\build_raider.ps1 -Run v2
#>
[CmdletBinding()]
param(
    [string] $Run = (Get-Date -Format 'yyyyMMdd-HHmm'),
    [string] $Work = 'work\raider-revamp',
    [string] $HandWork = 'work\raider-hand-r',
    [string] $FaceBake = 'face\bake-v15',
    [string] $BodyPaint = 'body-paint\attempt002-pbr',
    [string] $BodyParts = 'body-paint\attempt002-masks',
    [string] $HeadPaint = 'work\raider-head\textures\paint-attempt002-rough60',
    [ValidateSet('hands', 'production', 'materials', 'landmarks', 'fingers', 'rig', 'skin', 'face', 'shoulders', 'mouth',
                 'look', 'check', 'renders', 'speech')][string] $From = 'hands',
    [string] $Blender = $env:RAC_BLENDER,
    [string] $FFmpeg
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $repo
$here = Join-Path $repo 'scripts\revamp\raider'
$W = (Resolve-Path $Work).Path
$H = (Resolve-Path $HandWork).Path
$out = Join-Path $W "build\$Run"
New-Item -ItemType Directory -Force -Path (Join-Path $out 'logs') | Out-Null
$python = & (Join-Path $repo 'scripts\resolve_python.ps1')
if (-not $Blender) { $Blender = (& $python (Join-Path $repo 'scripts\rac_env.py') --blender) | Select-Object -Last 1 }
if (-not $Blender -or -not (Test-Path -LiteralPath $Blender)) { throw 'Blender not found; set RAC_BLENDER or pass -Blender.' }

$stages = 'hands', 'production', 'materials', 'landmarks', 'fingers', 'rig', 'skin', 'face', 'shoulders', 'mouth', 'look',
          'check', 'renders', 'speech'
$start = [array]::IndexOf($stages, $From)
function Want([string] $name) { return [array]::IndexOf($stages, $name) -ge $start }
function Step([string] $name, [scriptblock] $body) {
    if (-not (Want $name)) { return }
    $log = Join-Path $out "logs\$name.log"
    Write-Host "[raider] $name" -ForegroundColor Cyan
    $t = [Diagnostics.Stopwatch]::StartNew()
    $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
        $text = (& $body *>&1 | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        $code = $LASTEXITCODE
        [System.IO.File]::WriteAllText($log, $text, (New-Object System.Text.UTF8Encoding $false))
    }
    finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { Get-Content $log -Tail 30; throw "stage '$name' failed (exit $code); log: $log" }
    Write-Host ("[raider] {0} done in {1:n0} s" -f $name, $t.Elapsed.TotalSeconds)
}
# Blender with the user's add-ons (MPFB) or without them; a Python error fails the stage
function B([string[]] $a) { & $Blender '--background' '--python-exit-code' '1' @a }
function BF([string[]] $a) { & $Blender '--background' '--factory-startup' '--python-exit-code' '1' @a }

$assembled = Join-Path $out 'raider-assembled.glb'
$prodRaw = Join-Path $out 'raider_hero_production-raw.glb'
$prod = Join-Path $out 'raider_hero_production.glb'
$profileFile = Join-Path $W 'prod\ue5_manny-hero.json'
$fingers = Join-Path $out 'landmarks-fingers.json'
$rigDir = Join-Path $out 'rig'; $skinDir = Join-Path $out 'skin'; $faceDir = Join-Path $out 'face'
$shoulderDir = Join-Path $out 'shoulders'; $mouthDir = Join-Path $out 'mouth'; $final = Join-Path $out 'final'
New-Item -ItemType Directory -Force -Path $skinDir, $faceDir, $shoulderDir, $mouthDir, $final | Out-Null
$lineage = Get-ChildItem (Join-Path $W 'hand-src') -Filter '*.lineage.json' | Select-Object -First 1

Step 'hands' { B @((Join-Path $W 'parts-v2\raider-parts-v2.blend'), '--python', "$here\place_hands.py", '--',
    (Join-Path $W 'assembled\raider-v3.glb'), (Join-Path $H 'textures\paint-attempt001\raider-hand-r.glb'),
    (Join-Path $H 'references\primary.png'), $lineage.FullName, (Join-Path $W 'evidence\seg-proto\parts-v2.npy'), $assembled) }
Step 'production' { BF @('--python', "$here\prep_production.py", '--', $assembled, $prodRaw, '1.82') }
# materials: the body's and head's real metalness (the packed map had metallic = roughness), the plates toned to the
# reference's worn iron, the arm and chest skin to the reference's tone, and the jacket's slit below the collar closed
Step 'materials' {
    $bp = Join-Path $W $BodyPaint; $hp = (Resolve-Path $HeadPaint).Path; $parts = Join-Path $W $BodyParts
    $pbr = Join-Path $out 'raider_hero_production-pbr.glb'; $toned = Join-Path $out 'raider_hero_production-toned.glb'
    BF @('--python', "$here\fix_pbr_maps.py", '--', $prodRaw, $pbr,
        "raider-body_roughness=$bp\raider-body", "raider-head_roughness=$hp\raider-head")
    if ($LASTEXITCODE -ne 0) { return }
    BF @('--python', "$here\tone_metal.py", '--', $pbr, $toned, "$bp\raider-body.obj",
        "$parts\painted-face-parts.npy", "$parts\painted-face-parts.json")
    if ($LASTEXITCODE -ne 0) { return }
    $skinned = Join-Path $out 'raider_hero_production-skin.glb'
    BF @('--python', "$here\tone_skin.py", '--', $toned, $skinned, "$bp\raider-body.obj",
        "$parts\painted-face-parts.npy", "$parts\painted-face-parts.json")
    if ($LASTEXITCODE -ne 0) { return }
    BF @('--python', "$here\fill_holes.py", '--', $skinned, $prod)
}
# run_rig_candidate.ps1 refuses a non-empty folder (it protects accepted rigs): a rerun moves the run's earlier
# rig folder aside, timestamped, and never deletes it
function Fresh([string] $dir) {
    if ((Test-Path -LiteralPath $dir) -and (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1)) {
        Move-Item -LiteralPath $dir -Destination ("{0}.prev-{1}" -f $dir, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
}
# landmarks: a first landmark-backbone run derives the humanoid landmarks from the production mesh
Step 'landmarks' { Fresh (Join-Path $out 'rig-landmarks'); & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'scripts\run_rig_candidate.ps1') `
    -InputMesh $prod -Profile ue5_manny -ProfileFile $profileFile -Backbone landmark `
    -OutputDirectory (Join-Path $out 'rig-landmarks') -Blender $Blender }
Step 'fingers' { BF @('--python', (Join-Path $repo 'scripts\blender\measure_finger_landmarks.py'), '--', $prod,
    (Join-Path $out 'rig-landmarks\landmarks\humanoid-landmarks.json'), $fingers) }
Step 'rig' { Fresh $rigDir; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'scripts\run_rig_candidate.ps1') `
    -InputMesh $prod -Profile ue5_manny -ProfileFile $profileFile -Backbone landmark -Landmarks $fingers `
    -OutputDirectory $rigDir -Blender $Blender }
Step 'skin' { B @((Join-Path $rigDir 'raider_hero_rigged.blend'), '--python', (Join-Path $repo 'scripts\blender\skin_from_makehuman.py'), '--',
    (Join-Path $skinDir 'raider_hero_rigged.fbx'), (Join-Path $skinDir 'raider_hero_rigged.blend'), (Join-Path $skinDir 'mhskin-report.json')) }
Step 'face' { B @((Join-Path $skinDir 'raider_hero_rigged.blend'), '--python', "$here\attach_face.py", '--',
    (Join-Path $W "$FaceBake\face-baked.blend"), $assembled, "$prod.json",
    (Join-Path $faceDir 'raider_hero_rigged.fbx'), (Join-Path $faceDir 'raider_hero_rigged.blend')) }
Step 'shoulders' { B @((Join-Path $faceDir 'raider_hero_rigged.blend'), '--python', "$here\fix_shoulders.py", '--',
    (Join-Path $shoulderDir 'raider_hero_rigged.blend'), (Join-Path $shoulderDir 'raider_hero_rigged.fbx')) }
Step 'mouth' { B @((Join-Path $shoulderDir 'raider_hero_rigged.blend'), '--python', "$here\fix_mouth.py", '--',
    (Join-Path $mouthDir 'raider_hero_rigged.blend'), (Join-Path $mouthDir 'raider_hero_rigged.fbx')) }
# look: the face to the reference's look (grey-hazel eyes from MakeHuman's CC0 eye textures, skin tone, matte)
Step 'look' {
    $eyes = Get-ChildItem "$env:APPDATA\Blender Foundation\Blender" -Recurse -Filter 'brownlight_eye.png' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $eyes) { throw 'MPFB eye textures not found (MakeHuman system assets)' }
    B @((Join-Path $mouthDir 'raider_hero_rigged.blend'), '--python', "$here\look_face.py", '--', $eyes.DirectoryName,
        (Join-Path $final 'raider_hero_rigged.blend'), (Join-Path $final 'raider_hero_rigged.fbx'))
}
$finalBlend = Join-Path $final 'raider_hero_rigged.blend'; $finalFbx = Join-Path $final 'raider_hero_rigged.fbx'
Step 'check' {
    BF @('--python', (Join-Path $repo 'scripts\blender\gate_rig.py'), '--', $finalFbx, $profileFile, (Join-Path $final 'gate-rig.json'))
    if ($LASTEXITCODE -ne 0) { return }
    BF @('--python', (Join-Path $repo 'scripts\blender\deform_test.py'), '--', $finalFbx, (Join-Path $final 'deform'),
        (Join-Path $final 'deform-report.json'), '900', 'ue5_manny')
}
Step 'renders' {
    B @($finalBlend, '--python', "$here\final_renders.py", '--', (Join-Path $final 'renders'))
    if ($LASTEXITCODE -ne 0) { return }
    B @($finalBlend, '--python', "$here\pose_sheet.py", '--', (Join-Path $final 'poses'))
    if ($LASTEXITCODE -ne 0) { return }
    B @($finalBlend, '--python', "$here\face_rig_sheet.py", '--', (Join-Path $final 'face-rig'))
}
Step 'speech' {
    $speech = Join-Path $out 'speech'
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$here\speak_line.ps1" -OutputDirectory $speech
    if ($LASTEXITCODE -ne 0) { return }
    & $python "$here\align_visemes.py" $speech
    if ($LASTEXITCODE -ne 0) { return }
    # the demo settings Mark reviewed: bigger mouth shapes capped below where the corners tear, no blinks, close shot
    $env:RAC_SPEAK_GAIN = '1.4'; $env:RAC_SPEAK_MAX = '0.7'; $env:RAC_SPEAK_BLINK = '0'; $env:RAC_SPEAK_DIST = '1.0'
    B @($finalBlend, '--python', "$here\speak_demo.py", '--', (Join-Path $speech 'visemes-aligned.json'), (Join-Path $speech 'frames'), '24')
    if ($LASTEXITCODE -ne 0) { return }
    if (-not $FFmpeg) { $FFmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source }
    if (-not $FFmpeg) { $FFmpeg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
    if (-not $FFmpeg) { Write-Host 'ffmpeg not found: frames rendered, video not muxed'; return }
    & $FFmpeg -y -loglevel error -framerate 24 -start_number 1 -i (Join-Path $speech 'frames\f_%04d.png') -i (Join-Path $speech 'line.wav') `
        -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -shortest (Join-Path $speech 'raider-speaking.mp4')
}
Write-Host "RAIDER_BUILD_OK $out"
