<#
.SYNOPSIS
  Compile every recipe in recipes\ and print a pass/fail matrix.

.DESCRIPTION
  This is the single command the pipeline promises. It attaches to no MCP
  server and needs no interactive application. A failing asset does not stop
  the others; the summary at the end is the report.

.EXAMPLE
  .\scripts\compile_all.ps1
#>
[CmdletBinding()]
param(
    [string] $Blender,
    [switch] $SkipRender
)

# Tool paths come from scripts/rac_env.py rather than a default that is only
# right on one machine. Set RAC_BLENDER to override.
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
}

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$recipes = Get-ChildItem -LiteralPath (Join-Path $repoRoot 'recipes') -Filter *.json | Sort-Object Name

$results = @()
foreach ($recipe in $recipes) {
    $status = 'PASS'
    $detail = ''
    try {
        & (Join-Path $PSScriptRoot 'compile_asset.ps1') `
            -Recipe $recipe.FullName -Blender $Blender -SkipRender:$SkipRender
    } catch {
        $status = 'FAIL'
        $detail = $_.Exception.Message
    }
    $results += [pscustomobject]@{
        Asset  = [System.IO.Path]::GetFileNameWithoutExtension($recipe.Name)
        Status = $status
        Detail = $detail
    }
}

Write-Host ''
Write-Host '================ COMPILE MATRIX ================' -ForegroundColor Cyan
foreach ($r in $results) {
    $colour = if ($r.Status -eq 'PASS') { 'Green' } else { 'Red' }
    Write-Host ("  {0,-20} {1}  {2}" -f $r.Asset, $r.Status, $r.Detail) -ForegroundColor $colour
}

$failed = @($results | Where-Object { $_.Status -eq 'FAIL' }).Count
if ($failed -gt 0) {
    Write-Host "RAC_COMPILE_ALL_FAILED $failed of $($results.Count)" -ForegroundColor Red
    exit 1
}
Write-Host "RAC_COMPILE_ALL_OK $($results.Count) assets" -ForegroundColor Green
