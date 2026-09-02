[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [Parameter(Mandatory = $true)] [string] $HandLandmarks,
    [string] $MarkerProfile,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $MarkerProfile) {
    $MarkerProfile = Join-Path $repoRoot 'profiles\rigging\arp-humanoid-a-pose.json'
}
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
}

$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = (Resolve-Path -LiteralPath $MarkerProfile).Path
$handPath = (Resolve-Path -LiteralPath $HandLandmarks).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    $existing = @(Get-ChildItem -LiteralPath $outputPath -Force)
    if ($existing.Count -gt 0) {
        throw "Refusing to overwrite non-empty rig candidate directory: $outputPath"
    }
}
else {
    New-Item -ItemType Directory -Path $outputPath | Out-Null
}

$candidate = Join-Path $outputPath 'arp-rig-candidate.blend'
$report = Join-Path $outputPath 'rig-candidate.json'
$log = Join-Path $outputPath 'rig-candidate.log'
$driver = Join-Path $repoRoot 'scripts\blender\rig_humanoid_arp.py'

Write-Host 'RIG_STAGE_BEGIN name=arp-existing-mesh-candidate -- the bones have received a written invitation.'
$runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
    '--python' $driver '--' $inputPath $candidate $report $profilePath $handPath 2>&1 | `
    Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    $failure = [ordered]@{
        schema = 'reference-asset-compiler.arp-rig-candidate.v1'
        status = 'failed'
        retry_policy = 'manual_after_diagnosis_only'
        input = [ordered]@{
            path = $inputPath
            sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        profile = [ordered]@{
            path = $profilePath
            sha256 = (Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        hand_landmarks = [ordered]@{
            path = $handPath
            sha256 = (Get-FileHash -LiteralPath $handPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        failure = [ordered]@{
            exit_code = $exitCode
            stage = 'arp_existing_mesh_candidate'
            output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
        }
        log = $log
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $failure | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $report -Encoding utf8
    throw "Auto-Rig Pro candidate failed with exit code $exitCode. Evidence was retained at $report. No retry was attempted."
}
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or
    -not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Auto-Rig Pro returned success without the required candidate and report.'
}
Write-Host "RAC_ARP_RIG_CANDIDATE_OK report=$report -- the rig may now face deformation review."
