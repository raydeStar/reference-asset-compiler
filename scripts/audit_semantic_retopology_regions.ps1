[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Profile,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = (Resolve-Path -LiteralPath $Profile).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite semantic region audit: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$driver = Join-Path $PSScriptRoot 'blender\audit_semantic_retopology_regions.py'
$blend = Join-Path $outputPath 'semantic-regions.blend'
$report = Join-Path $outputPath 'region-audit.json'
$log = Join-Path $outputPath 'region-audit.log'

Write-Host 'SEMANTIC_REGION_AUDIT_BEGIN -- downstream cuts, upstream authority intact.'
& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
    '--python' $driver '--' $inputPath $profilePath $blend $report 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Semantic region audit failed. Evidence: $log. No retry was attempted."
}
Write-Host "RAC_SEMANTIC_REGION_AUDIT_OK report=$report"
