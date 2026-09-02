[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
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
