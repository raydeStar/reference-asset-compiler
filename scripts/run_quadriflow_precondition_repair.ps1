[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [double] $MaximumP99M = 0.00005,
    [double] $MaximumMaxM = 0.00020,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
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
& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $candidate $report '--maximum-p99-m' $MaximumP99M `
    '--maximum-max-m' $MaximumMaxM 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "QuadriFlow precondition repair failed. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_QUADRIFLOW_PRECONDITION_REPAIR_OK report=$report"
