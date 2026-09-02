[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $QemSource,
    [Parameter(Mandatory = $true)][string] $AiAuthority,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [ValidateRange(0.0, 180.0)][double] $FaceAngleDegrees = 45.0,
    [ValidateRange(0.0, 180.0)][double] $ShapeAngleDegrees = 45.0,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
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
& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
    '--python' $driver '--' $qem $authority $blend $glb $report `
    '--face-angle-degrees' $FaceAngleDegrees `
    '--shape-angle-degrees' $ShapeAngleDegrees 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Paired Feature-QEM attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_PAIRED_FEATURE_QEM_OK report=$report"
