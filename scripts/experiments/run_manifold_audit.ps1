[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Report,
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
