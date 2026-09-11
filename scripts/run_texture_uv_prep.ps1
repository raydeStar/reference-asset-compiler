[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER,
    [switch] $AllowTriangulatedGlb
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
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
$uvArguments = @($inputPath, $blend, $obj, $report)
if ($AllowTriangulatedGlb) { $uvArguments += '--allow-triangulated-glb' }
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' '--python' $driver '--' `
        @uvArguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Texture UV preparation failed with exit code $exitCode. Evidence: $log. No retry was attempted."
}
foreach ($required in @($blend, $obj, $report)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Texture UV preparation exited 0 without writing $required. Evidence: $log"
    }
}
Write-Host "RAC_TEXTURE_UV_PREP_OK report=$report"
