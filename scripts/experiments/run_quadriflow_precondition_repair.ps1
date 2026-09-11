[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [double] $MaximumP99M = 0.00005,
    [double] $MaximumMaxM = 0.00020,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)
# Retained experiment: lives under scripts/experiments; shared helpers stay in scripts/.
$scriptsRoot = Split-Path -Parent $PSScriptRoot

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $scriptsRoot
$compilerPython = & (Join-Path $scriptsRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $scriptsRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite QuadriFlow precondition repair: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$candidate = Join-Path $outputPath 'quadriflow-ready.blend'
$report = Join-Path $outputPath 'precondition-repair.json'
$log = Join-Path $outputPath 'precondition-repair.log'
$driver = Join-Path $repoRoot 'scripts\blender\repair_quadriflow_preconditions.py'

Write-Host 'QUADRIFLOW_PRECONDITION_REPAIR_BEGIN -- collapsing only measured micro-edges.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
        $inputPath $candidate $report '--maximum-p99-m' $MaximumP99M `
        '--maximum-max-m' $MaximumMaxM 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "QuadriFlow precondition repair failed. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_QUADRIFLOW_PRECONDITION_REPAIR_OK report=$report"
