[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Report,
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
$reportPath = [System.IO.Path]::GetFullPath($Report)
if (Test-Path -LiteralPath $reportPath) {
    throw "Refusing to overwrite strict manifold audit: $reportPath"
}
$driver = Join-Path $repoRoot 'scripts\blender\audit_manifold.py'

Write-Host 'MANIFOLD_AUDIT_BEGIN -- topology gets cross-examined without moving a vertex.'
& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $reportPath
if ($LASTEXITCODE -ne 0) {
    throw "Strict manifold audit found a failed precondition. Evidence: $reportPath"
}
