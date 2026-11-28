<#
.SYNOPSIS
  The game review road: a polished character GLB to a playable review in the game, with in-game closeups.

.DESCRIPTION
  One command from a recipe (schema reference-asset-compiler.game-review-recipe.v1; see docs/GAME_REVIEW.md):

    01-single   game_review_single_mesh.py   join the meshes, bake rest morph weights (and any picked variant)
    02-rig      run_rig_candidate.ps1        landmark route, ue5_manny profile; a failed rig gate is recorded and
                                             the review goes on (review only, never production)
    02a-landmarks derive_humanoid_landmarks.py  the joints from the mesh; recipe arm_joints measured finds the elbow
                                             and wrist on the arm instead of placing them by template, and
                                             measured_shoulder the shoulder joint as well
    02a-hands   fit_hand_landmarks.py        finger joints fitted to the hands of the mesh before rigging
                                             (recipe hand_fit false keeps Manny's template hand)
    02b-bind    game_review_bind.py          heat weights on a watertight voxel stand-in, copied to the real mesh
                                             (recipe bind.method rig keeps the rig's own weights)
    03-manny    manny_axes.py                Manny's bone axes on the landmark rig, joints and mesh unmoved
    04-finish   game_review_finish.py        rigid head + chin-measured neck weights, under-hair scatter mask,
                                             neck-turn render
    05-export   export_game_review.py        centimetre FBX (scale applied into the bones) + textures by slot
    06-unreal   game_review_import.py        headless import, materials and looks, Manny animations retargeted
    07-closeups game_review_play.py          in-game face (per look) and four body views, labelled sheet

  Every attempt directory is new: an existing non-empty one is refused, so earlier evidence is never replaced.
  -Play opens the game afterwards with the character on the player pawn (-PlayLook <look> for a named look).
  -Motion samples every animation the player uses (montages split into clips; empty ones flagged): motion.jpg.
  -Baseline also shoots the game's own hero (no swap) through the same animations at the same frames, and
  motion-compare.jpg puts the two side by side, clip by clip (implies -Motion).
  -Poses adds a pose sheet (bind, idle, walk, jog, attack, jump; four sides each) for judging the body rig.
  -Face adds the face pass: the game's face component held in each expression and each lip-sync mouth shape
  (face.jpg), with the recipe's face.mouth_morph_gain; morph names the mesh lacks are flagged on the sheet.
  -ReuseFrom takes steps 01-04 from an earlier attempt when nothing they read has changed (a look-only change runs
  in minutes). The game and editor must be closed for 06 and 07; this script refuses rather than closing them.
  The saved player Blueprint, level and default character are never modified.

.EXAMPLE
  .\scripts\run_game_review.ps1 -Recipe .\work\remora\game-review.json -OutputDirectory .\work\remora\game\attempt01 -Play
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Recipe,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $ReuseFrom,
    [string] $Compare,
    [ValidateSet('finish', 'export', 'unreal', 'closeups')][string] $Through = 'closeups',
    [switch] $Play,
    [switch] $Poses,
    [switch] $Motion,
    [switch] $Face,
    [switch] $Baseline,
    [string] $PlayLook = 'default',
    [string] $Blender = $env:RAC_BLENDER,
    [string] $CompilerPython,
    [int] $CloseupTimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Relative paths are taken from PowerShell's location; .NET's GetFullPath would use the process directory instead
function Get-FullPath([string] $Path) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) { throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender.' }
}
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$out = Get-FullPath($OutputDirectory)
if ((Test-Path -LiteralPath $out) -and @(Get-ChildItem -LiteralPath $out -Force).Count -gt 0) {
    throw "Refusing to reuse non-empty attempt directory $out; name a new one."
}
New-Item -ItemType Directory -Force -Path $out, (Join-Path $out 'logs') | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding $false
$receipt = [ordered]@{ schema = 'reference-asset-compiler.game-review.v1'; review_only = $true; production_ready = $false
    started_utc = (Get-Date).ToUniversalTime().ToString('o'); steps = [ordered]@{} }
function Save-Receipt { [System.IO.File]::WriteAllText((Join-Path $out 'game-review.json'), ($receipt | ConvertTo-Json -Depth 8), $utf8) }
function Hash($path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Json($path) { Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json }

function Invoke-Logged {
    param([string] $Step, [string] $Exe, [string[]] $Arguments)
    $log = Join-Path $out "logs\$Step.log"
    Write-Host "[game-review] $Step" -ForegroundColor Cyan
    $started = Get-Date
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments *> $log
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
    $receipt.steps[$Step] = [ordered]@{ exit_code = $code; seconds = $seconds; log = $log }
    Save-Receipt
    if ($code -ne 0) {
        Get-Content -LiteralPath $log -Tail 20 | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        throw "$Step failed (exit $code); see $log"
    }
}

function Invoke-Blender([string] $Step, [string[]] $Arguments) {
    Invoke-Logged -Step $Step -Exe $blenderPath -Arguments (@('--background', '--factory-startup', '--python-exit-code', '1') + $Arguments)
}

# --- the job ---------------------------------------------------------------------------------------------------
$env:PYTHONPATH = Join-Path $repoRoot 'src'
$resolveArgs = @('-m', 'reference_asset_compiler.game_review', 'resolve', (Get-FullPath $Recipe), $out, '--repo-root', $repoRoot)
if ($ReuseFrom) { $resolveArgs += @('--reuse-from', (Get-FullPath($ReuseFrom))) }
Invoke-Logged -Step '00-job' -Exe $python -Arguments $resolveArgs
$jobPath = Join-Path $out 'job.json'
$job = Read-Json $jobPath
$paths = $job.paths
$receipt.job = $jobPath
$receipt.name = $job.name
$receipt.version = $job.version
$receipt.source = $job.source
$receipt.source_sha256 = $job.source_sha256
Save-Receipt

# --- Blender: one mesh, rig, Manny axes, finish ----------------------------------------------------------------
if ($ReuseFrom) {
    $earlier = Read-Json (Join-Path (Get-FullPath($ReuseFrom)) 'job.json')
    New-Item -ItemType Directory -Force -Path (Split-Path $paths.finish) | Out-Null
    Copy-Item -LiteralPath $earlier.paths.finish -Destination $paths.finish
    Copy-Item -LiteralPath ($earlier.paths.finish + '.json') -Destination ($paths.finish + '.json')
    $receipt.steps['01-04'] = [ordered]@{ reused_from = $earlier.paths.finish; sha256 = (Hash $paths.finish) }
    $earlierReceipt = Read-Json (Join-Path (Get-FullPath($ReuseFrom)) 'game-review.json')
    $receipt.rig_gate = $earlierReceipt.rig_gate
    if ($earlierReceipt.PSObject.Properties['bind']) { $receipt.bind = $earlierReceipt.bind }
} else {
    Invoke-Blender '01-single' @('--python', (Join-Path $repoRoot 'scripts\blender\game_review_single_mesh.py'), '--', $jobPath)

    $rigLandmarks = @()
    $armJoints = if ($job.PSObject.Properties['arm_joints']) { [string]$job.arm_joints } else { 'template' }
    if ($job.hand_fit -or $armJoints -ne 'template') {
        $landDir = $paths.landmarks
        Invoke-Blender '02a-landmarks' @('--python', (Join-Path $repoRoot 'scripts\blender\derive_humanoid_landmarks.py'), '--',
            $paths.single, $landDir, '--profile', (Join-Path $repoRoot 'profiles\skeletons\ue5_manny.json'), '--arm-joints', $armJoints)
        $landmarksFile = Join-Path $landDir 'humanoid-landmarks.json'
        $derived = Read-Json $landmarksFile
        if ($derived.PSObject.Properties['arm_joints']) { $receipt.arm_joints = $derived.arm_joints; Save-Receipt }
        if ($job.hand_fit) {
            $fittedLandmarks = Join-Path $landDir 'humanoid-landmarks-hands.json'
            Invoke-Blender '02a-hands' @('--python', (Join-Path $repoRoot 'scripts\blender\fit_hand_landmarks.py'), '--',
                $paths.single, $landmarksFile, $fittedLandmarks, (Join-Path $landDir 'hands'))
            $receipt.hand_fit = (Read-Json (Join-Path $landDir 'hand-fit.json')).hands
            Save-Receipt
            $landmarksFile = $fittedLandmarks
        }
        $rigLandmarks = @('-Landmarks', $landmarksFile)
    }
    $rigDir = $paths.rig
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $started = Get-Date
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run_rig_candidate.ps1') `
            -InputMesh $paths.single -OutputDirectory $rigDir -Profile ue5_manny -Backbone landmark -Blender $blenderPath `
            -CompilerPython $python @rigLandmarks *> (Join-Path $out 'logs\02-rig.log')
        $rigCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($paths.single)
    $rigged = Join-Path $rigDir "${stem}_rigged.blend"
    if (-not (Test-Path -LiteralPath $rigged)) { throw "the rig route wrote no $rigged; see logs\02-rig.log" }
    $gate = Join-Path $rigDir 'gate-rig.json'
    $gateFailures = @()
    if (Test-Path -LiteralPath $gate) { $gateFailures = @((Read-Json $gate).failures) }
    $receipt.steps['02-rig'] = [ordered]@{ exit_code = $rigCode; seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        rigged_blend = $rigged; log = (Join-Path $out 'logs\02-rig.log') }
    $receipt.rig_gate = [ordered]@{ passed = ($rigCode -eq 0); failures = $gateFailures
        note = 'A review in the game does not need the production rig gate; a failed gate is recorded, never waived.' }
    Save-Receipt
    if ($gateFailures.Count) { Write-Host "  rig gate failed (recorded, review continues): $($gateFailures -join '; ')" -ForegroundColor Yellow }

    if ($job.bind.method -eq 'voxel_heat') {
        Invoke-Logged -Step '02b-bind' -Exe $blenderPath -Arguments @('--background', '--python-exit-code', '1', $rigged,
            '--python', (Join-Path $repoRoot 'scripts\blender\game_review_bind.py'), '--', $jobPath, $paths.bound)
        $receipt.bind = Read-Json ($paths.bound + '.json')
        $rigged = $paths.bound
        Save-Receipt
    }
    if (-not (Test-Path -LiteralPath $job.manny_refpose)) {
        throw "Manny's reference pose is missing ($($job.manny_refpose)). Dump it with the editor closed: UnrealEditor-Cmd.exe <project> -run=pythonscript -script=`"scripts\ue5\dump_manny_reference.py $(Split-Path $job.manny_refpose)`""
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $paths.manny) | Out-Null
    Invoke-Logged -Step '03-manny' -Exe $blenderPath -Arguments @('--background', '--python-exit-code', '1', $rigged,
        '--python', (Join-Path $repoRoot 'scripts\blender\manny_axes.py'), '--', $job.manny_refpose, $paths.manny)
    $neckPng = Join-Path (Split-Path $paths.finish) 'neck-pose.png'
    Invoke-Logged -Step '04-finish' -Exe $blenderPath -Arguments @('--background', '--python-exit-code', '1', $paths.manny,
        '--python', (Join-Path $repoRoot 'scripts\blender\game_review_finish.py'), '--', $jobPath, $paths.finish, $neckPng)
}
$receipt.finish = Read-Json ($paths.finish + '.json')
$receipt.finish_blend = $paths.finish
$receipt.finish_sha256 = Hash $paths.finish
Save-Receipt
if ($Through -eq 'finish') { Write-Host "GAME_REVIEW_DONE through finish: $out"; return }

Invoke-Logged -Step '05-export' -Exe $blenderPath -Arguments @('--background', '--python-exit-code', '1', $paths.finish,
    '--python', (Join-Path $repoRoot 'scripts\blender\export_game_review.py'), '--', $jobPath)
$receipt.fbx = $paths.fbx
$receipt.fbx_sha256 = Hash $paths.fbx
Save-Receipt
if ($Through -eq 'export') { Write-Host "GAME_REVIEW_DONE through export: $out"; return }

# --- Unreal ----------------------------------------------------------------------------------------------------
$project = $job.unreal.project
$engine = $job.unreal.engine_dir
$running = @(Get-CimInstance Win32_Process -Filter "Name like 'UnrealEditor%'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$(Split-Path -Leaf $project)*" })
if ($running.Count) {
    throw "Unreal is running on this project (pid $(($running | ForEach-Object ProcessId) -join ', ')); close it, then rerun with -ReuseFrom $out"
}
$dest = [string]$job.unreal.dest
if ($dest -like '/Game/RAC/*') {      # the review's own folder: cleared on disk too (a failed import can leave it locked)
    $folder = Join-Path (Split-Path -Parent $project) ('Content\' + $dest.Substring(6).Replace('/', '\'))
    if (Test-Path -LiteralPath $folder) { [System.IO.Directory]::Delete($folder, $true) }
}
New-Item -ItemType Directory -Force -Path $paths.unreal | Out-Null
$env:RAC_GAME_REVIEW_JOB = $jobPath
Invoke-Logged -Step '06-unreal' -Exe (Join-Path $engine 'UnrealEditor-Cmd.exe') -Arguments @($project, '-run=pythonscript',
    "-script=$(Join-Path $repoRoot 'scripts\ue5\game_review_import.py')", '-unattended', '-nop4', '-nosplash', '-stdout',
    "-abslog=$(Join-Path $out 'logs\06-unreal-engine.log')")
$import = Read-Json (Join-Path $paths.unreal 'import.json')
if (-not $import.ok) { throw "the Unreal import failed: see $(Join-Path $paths.unreal 'import.json')" }
$receipt.unreal = [ordered]@{ mesh = $import.mesh; retargeted = $import.retargeted; cut = $import.cut_no_manny_source
    looks = @($job.looks.PSObject.Properties | ForEach-Object { $_.Name }) }
Save-Receipt
if ($Through -eq 'unreal') { Write-Host "GAME_REVIEW_DONE through unreal: $out"; return }

function Start-Game([string] $Mode, [string] $Log) {
    $env:RAC_GAME_REVIEW_MODE = $Mode
    $res = $job.unreal.resolution
    Start-Process -FilePath (Join-Path $engine 'UnrealEditor.exe') -PassThru -ArgumentList @("`"$project`"", $job.unreal.level,
        '-game', '-windowed', "-ResX=$($res[0])", "-ResY=$($res[1])", '-nosplash', '-nop4', "-abslog=`"$Log`"",
        "-ExecCmds=`"t.MaxFPS 60,py $(Join-Path $repoRoot 'scripts\ue5\game_review_play.py')`"")
}

$env:RAC_GAME_REVIEW_POSES = $(if ($Poses) { '1' } else { '0' })
$env:RAC_GAME_REVIEW_MOTION = $(if ($Motion) { '1' } else { '0' })
$env:RAC_GAME_REVIEW_FACE = $(if ($Face) { '1' } else { '0' })
if ($Baseline) { $Motion = $true; $env:RAC_GAME_REVIEW_MOTION = '1' }
$env:RAC_GAME_REVIEW_BASELINE = '0'
if ($Motion -and $CloseupTimeoutSeconds -lt 900) { $CloseupTimeoutSeconds = 900 }      # ~20 clips x 8 frames
$game = Start-Game 'closeups' (Join-Path $out 'logs\07-closeups-engine.log')
$done = Join-Path $paths.closeups 'done.json'
$errorFile = Join-Path $paths.unreal 'runtime-error.json'
$waited = 0
while (-not (Test-Path -LiteralPath $done) -and -not (Test-Path -LiteralPath $errorFile) -and -not $game.HasExited -and $waited -lt $CloseupTimeoutSeconds) {
    Start-Sleep -Seconds 2; $waited += 2
}
if (-not $game.WaitForExit(30000)) { Stop-Process -Id $game.Id }      # only the game this script started
if (Test-Path -LiteralPath $errorFile) { throw "the in-game script failed: see $errorFile" }
if (-not (Test-Path -LiteralPath $done)) { throw "no closeups within $CloseupTimeoutSeconds s; see logs\07-closeups-engine.log" }
if ($Baseline) {      # the game's own hero through the same clips, for the side-by-side
    $env:RAC_GAME_REVIEW_BASELINE = '1'
    $base = Start-Game 'closeups' (Join-Path $out 'logs\07-baseline-engine.log')
    $baseDone = Join-Path $paths.closeups 'baseline\done.json'
    $waited = 0
    while (-not (Test-Path -LiteralPath $baseDone) -and -not (Test-Path -LiteralPath $errorFile) -and -not $base.HasExited -and $waited -lt $CloseupTimeoutSeconds) {
        Start-Sleep -Seconds 2; $waited += 2
    }
    if (-not $base.WaitForExit(30000)) { Stop-Process -Id $base.Id }      # only the game this script started
    $env:RAC_GAME_REVIEW_BASELINE = '0'
    if (Test-Path -LiteralPath $errorFile) { throw "the baseline in-game script failed: see $errorFile" }
    if (-not (Test-Path -LiteralPath $baseDone)) { throw "no baseline within $CloseupTimeoutSeconds s; see logs\07-baseline-engine.log" }
}
$sheetArgs = @((Join-Path $PSScriptRoot 'game_review_sheet.py'), $out)
if ($Compare) { $sheetArgs += @('--compare', (Get-FullPath($Compare))) }
Invoke-Logged -Step '07-sheet' -Exe $python -Arguments $sheetArgs
$shots = Get-ChildItem -LiteralPath $paths.closeups -File | Where-Object { $_.Extension -in '.png', '.jpg' }
$receipt.closeups = [ordered]@{}
foreach ($shot in $shots) { $receipt.closeups[$shot.Name] = Hash $shot.FullName }
$receipt.finished_utc = (Get-Date).ToUniversalTime().ToString('o')
Save-Receipt

if ($Play) {
    $env:RAC_GAME_REVIEW_LOOK = $PlayLook
    $p = Start-Game 'play' (Join-Path $out 'logs\08-play-engine.log')
    $receipt.play_pid = $p.Id
    Save-Receipt
    Write-Host "[game-review] the game is open with $($job.name) $($job.version) (pid $($p.Id))"
}
Write-Host "GAME_REVIEW_DONE $out $(Join-Path $paths.closeups 'closeups.jpg')"
