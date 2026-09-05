<#
.SYNOPSIS
  Rig an approved mesh with the best route this machine has, then gate it.

.DESCRIPTION
  One command for the rig stage, either-or:

    * Auto-Rig Pro, when it is installed and operational in Blender and the
      profile is a humanoid. Higher-quality binding (pseudo-voxel), needs the
      user's licence and a reviewed hand-landmark file.
    * The portable landmark route otherwise: derive joints from the mesh (and
      Manny's proportions for humanoids, or the reviewed joint-ring guides for
      mascots), build the skeleton, bind with heat weights, export FBX. Free.

  Both routes end at the same gates: gate_rig.py against the skeleton profile
  and deform_test.py's five poses. The route taken and why is written to
  rig-route.json beside the outputs, so a receipt never hides which one ran.

.PARAMETER ProfileFile
  A resolved profile JSON (for example one carrying a tri_budget_waiver, as
  compile_asset.ps1 writes) to use instead of profiles\skeletons\<Profile>.json.

.PARAMETER Backbone
  auto (default) picks Auto-Rig Pro when available for humanoids; arp forces it
  (fails if unavailable); landmark forces the portable route.

.EXAMPLE
  .\scripts\run_rig_candidate.ps1 -InputMesh .\work\hero\prod-v1\hero_production.fbx `
      -Profile ue5_manny -OutputDirectory .\work\hero\rig\attempt001

.EXAMPLE
  .\scripts\run_rig_candidate.ps1 -InputMesh .\work\cat\prod-v1\cat_production.fbx `
      -Profile mascot_biped_tail -RingProfile .\work\cat\retopo\joint-guides\fitted-profile.json `
      -BindingReport .\work\cat\prod-v1\texture-payload-binding.json -OutputDirectory .\work\cat\rig\attempt001
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [Parameter(Mandatory = $true)][ValidateSet('ue5_manny', 'ue4_mannequin', 'mascot_biped_tail')][string] $Profile,
    [ValidateSet('auto', 'arp', 'landmark')][string] $Backbone = 'auto',
    [string] $ProfileFile,
    [string] $HandLandmarks,
    [string] $RingProfile,
    [string] $BindingReport,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
}
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = $(if ($ProfileFile) { (Resolve-Path -LiteralPath $ProfileFile).Path } else { Join-Path $repoRoot "profiles\skeletons\$Profile.json" })
if (-not (Test-Path -LiteralPath $profilePath)) { throw "Unknown skeleton profile: $profilePath" }
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if ((Test-Path -LiteralPath $outputPath) -and @(Get-ChildItem -LiteralPath $outputPath -Force).Count -gt 0) {
    throw "Refusing to overwrite non-empty rig candidate directory: $outputPath"
}
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$assetStem = [System.IO.Path]::GetFileNameWithoutExtension($inputPath) -replace '_production$', ''
$humanoid = $Profile -in @('ue5_manny', 'ue4_mannequin')

function Invoke-Blender {
    param([string[]] $Arguments, [string] $Label)
    Write-Host "[rig] $Label" -ForegroundColor Cyan
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    $output | Where-Object { $_ -match '^\[(LANDMARKS|LANDMARK RIG|GATE RIG|DEFORM)\]' -or $_ -match '^  - ' } | ForEach-Object { Write-Host "  $_" }
    if ($code -ne 0) {
        $output | Select-Object -Last 15 | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        throw "$Label failed with exit code $code"
    }
}

# --- Route decision -----------------------------------------------------------
$arpAvailable = $false
$arpDetail = 'not probed'
if ($humanoid -and $Backbone -ne 'landmark') {
    $probe = Join-Path $repoRoot 'scripts\blender\preflight_arp.py'
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $probeOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' '--python' $probe 2>&1)
        $probeCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    $line = $probeOutput | Where-Object { $_ -like 'RAC_ARP_PREFLIGHT_JSON=*' } | Select-Object -Last 1
    if ($line) {
        $report = ($line -replace '^RAC_ARP_PREFLIGHT_JSON=', '') | ConvertFrom-Json
        $arpAvailable = ($probeCode -eq 0) -and [bool]$report.ok
        $arpDetail = "Auto-Rig Pro probe ok=$($report.ok) exit=$probeCode"
    } else {
        $arpDetail = "Auto-Rig Pro probe produced no report (exit $probeCode)"
    }
}
$route = 'landmark'
$reason = 'portable landmark route'
if ($Backbone -eq 'landmark') {
    $reason = 'landmark route requested explicitly (-Backbone landmark); Auto-Rig Pro was not probed'
} elseif ($humanoid -and $Backbone -eq 'arp') {
    if (-not $arpAvailable) { throw "Backbone 'arp' requested but Auto-Rig Pro is not operational: $arpDetail" }
    $route = 'arp'; $reason = 'Auto-Rig Pro requested explicitly and operational'
} elseif ($humanoid -and $Backbone -eq 'auto' -and $arpAvailable) {
    if ($HandLandmarks) { $route = 'arp'; $reason = 'Auto-Rig Pro operational and reviewed hand landmarks supplied' }
    else { $reason = 'Auto-Rig Pro operational but no -HandLandmarks file; the ARP route requires reviewed hand landmarks, so the landmark route ran' }
} elseif (-not $humanoid) {
    $reason = 'mascot profiles always use the landmark route (Auto-Rig Pro is humanoid-only)'
} elseif (-not $arpAvailable) {
    $reason = "Auto-Rig Pro not operational ($arpDetail); landmark route ran"
}
Write-Host "[rig] route=$route -- $reason"

$riggedFbx = Join-Path $outputPath "${assetStem}_rigged.fbx"
$gateReport = Join-Path $outputPath 'gate-rig.json'
$deformDir = Join-Path $outputPath 'deform'
$deformReport = Join-Path $outputPath 'deform-report.json'
$landmarks = $null

if ($route -eq 'arp') {
    $arpDir = Join-Path $outputPath 'arp'
    & (Join-Path $PSScriptRoot 'run_arp_rig_candidate.ps1') -InputMesh $inputPath -OutputDirectory $arpDir -HandLandmarks $HandLandmarks -Blender $blenderPath
    if ($LASTEXITCODE -ne 0) { throw 'Auto-Rig Pro candidate failed' }
    $candidate = Join-Path $arpDir 'arp-rig-candidate.blend'
    Write-Host "[rig] Auto-Rig Pro candidate at $candidate; export its FBX with the ARP game exporter, then gate with gate_rig.py and deform_test.py."
    $riggedFbx = $candidate
} else {
    $landmarkDir = Join-Path $outputPath 'landmarks'
    if ($humanoid) {
        Invoke-Blender -Label 'derive humanoid landmarks' -Arguments @('--python', (Join-Path $repoRoot 'scripts\blender\derive_humanoid_landmarks.py'), '--', $inputPath, $landmarkDir, '--profile', $profilePath)
        $landmarks = Join-Path $landmarkDir 'humanoid-landmarks.json'
    } else {
        if (-not $RingProfile -or -not $BindingReport) { throw 'Mascot landmarks need -RingProfile (fitted joint rings) and -BindingReport (texture payload binding).' }
        Invoke-Blender -Label 'derive mascot landmarks' -Arguments @('--python', (Join-Path $repoRoot 'scripts\blender\derive_mascot_landmarks.py'), '--', $inputPath, (Resolve-Path $RingProfile).Path, (Resolve-Path $BindingReport).Path, $landmarkDir)
        $landmarks = Join-Path $landmarkDir 'mascot-landmarks.json'
    }
    Invoke-Blender -Label 'build skeleton and bind' -Arguments @('--python', (Join-Path $repoRoot 'scripts\blender\rig_from_landmarks.py'), '--', $inputPath, $landmarks, $profilePath, $riggedFbx, (Join-Path $outputPath 'rig-candidate.json'))
    Invoke-Blender -Label "gate rig ($Profile)" -Arguments @('--python', (Join-Path $repoRoot 'scripts\blender\gate_rig.py'), '--', $riggedFbx, $profilePath, $gateReport)
    Invoke-Blender -Label 'deformation suite' -Arguments @('--python', (Join-Path $repoRoot 'scripts\blender\deform_test.py'), '--', $riggedFbx, $deformDir, $deformReport)
}

$receipt = [ordered]@{
    schema = 'reference-asset-compiler.rig-route.v1'
    input_mesh = $inputPath
    input_sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    skeleton_profile = $Profile
    backbone_requested = $Backbone
    route = $route
    reason = $reason
    auto_rig_pro = [ordered]@{ available = $arpAvailable; detail = $arpDetail }
    landmarks = $landmarks
    rigged_fbx = $riggedFbx
    gate_report = $(if (Test-Path -LiteralPath $gateReport) { $gateReport } else { $null })
    deform_report = $(if (Test-Path -LiteralPath $deformReport) { $deformReport } else { $null })
    next = 'record_rig_and_skin.py and record_deformation.py bind these files into the ledger once the overlay and pose renders have been reviewed.'
}
[System.IO.File]::WriteAllText((Join-Path $outputPath 'rig-route.json'), ($receipt | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))
Write-Host "RAC_RIG_ROUTE_OK route=$route output=$outputPath -- the bones arrived by whichever road was open."
