[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Mesh,
    [Parameter(Mandatory = $true)][string] $Reference,
    [Parameter(Mandatory = $true)][string] $OutputObj,
    [ValidateRange(6, 12)][int] $Views = 6,
    [ValidateSet(512, 768)][int] $Resolution = 512,
    [string] $DiagnosticsDir,
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { throw 'Set RAC_LEGACY_ROOT to the studio tree that holds the Hunyuan3D-Paint runner, upstream checkout and models.' }),
    [int] $MinimumFreeVramMiB = 21504
)

$ErrorActionPreference = 'Stop'
$expectedRunnerHash = 'B039065EA96E0E63EFFECBA4379F63B8228F830B036EF1392790E5BF6B8F8A8B'
$python = Join-Path $LegacyRoot '.venv-hy3d21\Scripts\python.exe'
$runner = Join-Path $LegacyRoot 'scripts\run_hy3d21_pbr.py'
$upstream = Join-Path $LegacyRoot 'upstream\Hunyuan3D-2.1'
$models = Join-Path $LegacyRoot 'models\hy3d21\Hunyuan3D-2.1'

foreach ($required in @($python, $runner, $upstream, $models)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Hunyuan3D-Paint component is missing: $required"
    }
}

$actualRunnerHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash
if ($actualRunnerHash -ne $expectedRunnerHash) {
    throw "Legacy Hunyuan runner changed: expected $expectedRunnerHash, found $actualRunnerHash"
}

$meshPath = (Resolve-Path -LiteralPath $Mesh).Path
$referencePath = (Resolve-Path -LiteralPath $Reference).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputObj)
if ([System.IO.Path]::GetExtension($outputPath).ToLowerInvariant() -ne '.obj') {
    throw 'Hunyuan3D-Paint output must use an .obj path'
}
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null

$gpu = & nvidia-smi --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits
if ($LASTEXITCODE -ne 0 -or -not $gpu) {
    throw 'Unable to read GPU state; inference was not launched'
}
$parts = $gpu.Split(',')
$freeMiB = [int]$parts[0].Trim()
$utilization = [int]$parts[1].Trim()
if ($freeMiB -lt $MinimumFreeVramMiB) {
    throw "GPU has $freeMiB MiB free; $MinimumFreeVramMiB MiB is required. No process was killed."
}

Write-Host "HY3D21_LAUNCH_READY free_mib=$freeMiB utilization=$utilization% runner_sha256=$actualRunnerHash"
$runnerArgs = @($runner, $meshPath, $referencePath, $outputPath, '--views', $Views, '--resolution', $Resolution)
if ($DiagnosticsDir) {
    $diagnosticsPath = [System.IO.Path]::GetFullPath($DiagnosticsDir)
    if (Test-Path -LiteralPath $diagnosticsPath) {
        throw "Diagnostics directory already exists; refusing to overwrite evidence: $diagnosticsPath"
    }
    $runnerArgs += @('--diagnostics-dir', $diagnosticsPath)
}
# The runner and its dependencies write ordinary progress and warnings to
# stderr. Under $ErrorActionPreference = 'Stop', any caller that redirects our
# output to a log (2>&1, *>) would turn the first such line into a terminating
# error and kill the paint before a receipt exists. Relax only around the call.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $python @runnerArgs
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
$report = [System.IO.Path]::ChangeExtension($outputPath, '.validation.json')
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw "Hunyuan3D-Paint exited $exitCode without a validation report; it will not be auto-retried"
}
$gate = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if (-not $gate.faces_equal -or [double]$gate.geometry_delta -gt 0.000001 -or [double]$gate.uv_delta -gt 0.000001) {
    throw "Hunyuan3D-Paint topology/UV gate failed: $report"
}
if (-not (Test-Path -LiteralPath ([System.IO.Path]::ChangeExtension($outputPath, '.glb')) -PathType Leaf)) {
    throw 'Hunyuan3D-Paint validation passed but the expected GLB is missing'
}

Write-Host "HY3D21_TEXTURE_VALIDATED exit_code=$exitCode report=$report -- the paint is admitted; the mirror retains veto power."
