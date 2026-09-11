[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $QemSource,
    [Parameter(Mandatory = $true)][string] $AiAuthority,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [ValidateRange(0.0, 180.0)][double] $FaceAngleDegrees = 45.0,
    [ValidateRange(0.0, 180.0)][double] $ShapeAngleDegrees = 45.0,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$qem = (Resolve-Path -LiteralPath $QemSource).Path
$authority = (Resolve-Path -LiteralPath $AiAuthority).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) {
    throw "Refusing to overwrite paired-QEM attempt: $output"
}
[System.IO.Directory]::CreateDirectory($output) | Out-Null
$driver = Join-Path $PSScriptRoot 'blender\pair_feature_qem_triangles.py'
$blend = Join-Path $output 'paired-feature-qem-candidate.blend'
$glb = Join-Path $output 'paired-feature-qem-candidate.glb'
$report = Join-Path $output 'pairing-report.json'
$log = Join-Path $output 'pairing.log'

Write-Host 'PAIRED_FEATURE_QEM_BEGIN -- the vertices stay put; the topology must earn its loops.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
        '--python' $driver '--' $qem $authority $blend $glb $report `
        '--face-angle-degrees' $FaceAngleDegrees `
        '--shape-angle-degrees' $ShapeAngleDegrees 2>&1 |
        ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Paired Feature-QEM attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_PAIRED_FEATURE_QEM_OK report=$report"
