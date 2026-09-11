[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
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
    throw "Refusing to overwrite smooth-review derivative: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$outputBlend = Join-Path $outputPath 'smooth-review.blend'
$outputGlb = Join-Path $outputPath 'smooth-review.glb'
$report = Join-Path $outputPath 'smooth-review.json'
$driver = Join-Path $repoRoot 'scripts\blender\prepare_smooth_review.py'

Write-Host 'SMOOTH_REVIEW_BEGIN -- changing normals metadata, never the geometry.'
& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $outputBlend $outputGlb $report
if ($LASTEXITCODE -ne 0) {
    throw "Smooth-review derivative failed. Evidence: $report"
}
Write-Host "RAC_SMOOTH_REVIEW_OK report=$report"
