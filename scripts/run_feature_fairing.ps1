[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $AiAuthority,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [int] $Iterations = 6,
    [double] $LambdaFactor = 0.25,
    [double] $MuFactor = -0.255,
    [double] $FeatureLow = 0.27,
    [double] $FeatureHigh = 0.40,
    [double] $MaximumDisplacementM = 0.004,
    [int] $MinimumComponentVertices = 100,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$authorityPath = (Resolve-Path -LiteralPath $AiAuthority).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite feature-fairing attempt: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$driver = Join-Path $PSScriptRoot 'blender\fair_feature_qem.py'
$blend = Join-Path $outputPath 'feature-faired-candidate.blend'
$glb = Join-Path $outputPath 'feature-faired-candidate.glb'
$report = Join-Path $outputPath 'fairing-report.json'
$log = Join-Path $outputPath 'fairing.log'

Write-Host 'FEATURE_FAIRING_BEGIN -- smooth the acreage; keep the cat.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
        '--python' $driver '--' $inputPath $authorityPath $blend $glb $report `
        '--iterations' $Iterations '--lambda-factor' $LambdaFactor `
        '--mu-factor' $MuFactor '--feature-low' $FeatureLow `
        '--feature-high' $FeatureHigh `
        '--maximum-displacement-m' $MaximumDisplacementM `
        '--minimum-component-vertices' $MinimumComponentVertices 2>&1 |
        ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Feature-fairing attempt failed or was rejected. Evidence: $report."
}
Write-Host "RAC_FEATURE_FAIRING_OK report=$report -- smoother is useful only if it still looks like the cat."
