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
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)
# Retained experiment: lives under scripts/experiments; shared helpers stay in scripts/.
$scriptsRoot = Split-Path -Parent $PSScriptRoot

$ErrorActionPreference = 'Stop'
$compilerPython = & (Join-Path $scriptsRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $scriptsRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
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
$driver = Join-Path $scriptsRoot 'blender\reduce_regional_autoremesher.py'

Write-Host 'REGIONAL_AUTOREMESHER_BEGIN -- detail receives a budget, not a eulogy.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $Blender --background --python-exit-code 1 --python $driver -- `
        $sourcePath $segmentedPath $profilePath $auditPath $blend $glb $report `
        --maximum-vertices $MaximumVertices --maximum-triangles $MaximumTriangles `
        --adaptivity $Adaptivity 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Regional AutoRemesher failed or was rejected. Evidence: $report. No automatic retry was attempted."
}
Write-Host "RAC_REGIONAL_AUTOREMESHER_CANDIDATE_OK report=$report -- now inspect the face, hands, gear, and tail."
