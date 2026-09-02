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
    throw "Refusing to overwrite texture UV attempt: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$driver = Join-Path $repoRoot 'scripts\blender\prepare_texture_uv_transport.py'
$blend = Join-Path $outputPath 'uv-authority.blend'
$obj = Join-Path $outputPath 'texture-transport.obj'
$report = Join-Path $outputPath 'uv-transport-report.json'
$log = Join-Path $outputPath 'uv-prep.log'

Write-Host 'RAC_TEXTURE_UV_PREP_BEGIN -- coordinates stay put; only the map may unfold.'
& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $blend $obj $report 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Texture UV preparation failed. Evidence: $log"
}
Write-Host "RAC_TEXTURE_UV_PREP_OK report=$report"
