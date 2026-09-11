[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Profile,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)
# Retained experiment: lives under scripts/experiments; shared helpers stay in scripts/.
$scriptsRoot = Split-Path -Parent $PSScriptRoot

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$compilerPython = & (Join-Path $scriptsRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $scriptsRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = (Resolve-Path -LiteralPath $Profile).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite semantic region audit: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$driver = Join-Path $scriptsRoot 'blender\audit_semantic_retopology_regions.py'
$blend = Join-Path $outputPath 'semantic-regions.blend'
$report = Join-Path $outputPath 'region-audit.json'
$log = Join-Path $outputPath 'region-audit.log'

Write-Host 'SEMANTIC_REGION_AUDIT_BEGIN -- downstream cuts, upstream authority intact.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
        '--python' $driver '--' $inputPath $profilePath $blend $report 2>&1 |
        ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Semantic region audit failed. Evidence: $log. No retry was attempted."
}
Write-Host "RAC_SEMANTIC_REGION_AUDIT_OK report=$report"
