[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Source,
    [Parameter(Mandatory = $true)][string] $Segmented,
    [Parameter(Mandatory = $true)][string] $Profile,
    [Parameter(Mandatory = $true)][string] $Audit,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [int] $MaximumVertices = 15000,
    [int] $MaximumTriangles = 20000,
    [double] $Adaptivity = 0.75,
    [string] $Blender = $env:RAC_BLENDER
)

$ErrorActionPreference = 'Stop'
if (-not $Blender) {
    $Blender = (& py -3.12 (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
}
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$segmentedPath = (Resolve-Path -LiteralPath $Segmented).Path
$profilePath = (Resolve-Path -LiteralPath $Profile).Path
$auditPath = (Resolve-Path -LiteralPath $Audit).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite regional retopology evidence: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$blend = Join-Path $outputPath 'regional-autoremesher-candidate.blend'
$glb = Join-Path $outputPath 'regional-autoremesher-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $PSScriptRoot 'blender\reduce_regional_autoremesher.py'

Write-Host 'REGIONAL_AUTOREMESHER_BEGIN -- detail receives a budget, not a eulogy.'
& $Blender --background --python-exit-code 1 --python $driver -- `
    $sourcePath $segmentedPath $profilePath $auditPath $blend $glb $report `
    --maximum-vertices $MaximumVertices --maximum-triangles $MaximumTriangles `
    --adaptivity $Adaptivity 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Regional AutoRemesher failed or was rejected. Evidence: $report. No automatic retry was attempted."
}
Write-Host "RAC_REGIONAL_AUTOREMESHER_CANDIDATE_OK report=$report -- now inspect the face, hands, gear, and tail."
