[CmdletBinding()]
param(
    [string]$Recipe = 'recipes/assemblies/sunset-ayric-neck-transition.json',
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Blender = $env:RAC_BLENDER,
    [string]$CompilerPython,
    [switch]$SkipReview
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
# Blender comes from scripts/rac_env.py (RAC_BLENDER first, then the usual
# install locations), not from the Steam path of the machine this was written on.
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$recipePath = if ([IO.Path]::IsPathRooted($Recipe)) { [IO.Path]::GetFullPath($Recipe) } else { [IO.Path]::GetFullPath((Join-Path $repoRoot $Recipe)) }
$outputPath = if ([IO.Path]::IsPathRooted($Output)) { [IO.Path]::GetFullPath($Output) } else { [IO.Path]::GetFullPath((Join-Path $repoRoot $Output)) }
if (Test-Path -LiteralPath $outputPath) { throw 'Keep previous seam evidence; choose a new output directory.' }
if (!(Test-Path -LiteralPath $Blender -PathType Leaf)) { throw 'Blender is missing; pass -Blender with its executable path.' }
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $Blender -b --factory-startup --python-exit-code 1 --python (Join-Path $PSScriptRoot 'blender/transfer_neck_vertex_color.py') -- $recipePath $outputPath
    $transferExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousPreference }
if ($transferExit -ne 0) { throw 'Neck transfer failed; no automatic retry, and no promotion.' }
$receipt = Get-Content -Raw -LiteralPath (Join-Path $outputPath 'neck-transfer.json') | ConvertFrom-Json
if (!$receipt.ok -or $receipt.before_fingerprint -ne $receipt.after_fingerprint) { throw 'Seam transfer changed a protected mesh attribute.' }
if (!$SkipReview) {
    $ErrorActionPreference = 'Continue'
    try {
        & $Blender -b --factory-startup --python-exit-code 1 --python (Join-Path $PSScriptRoot 'blender/render_workshop_face_repair.py') -- (Join-Path $outputPath 'assembly-fit.blend') (Join-Path $outputPath 'fit-review') --albedo-only
        $reviewExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($reviewExit -ne 0) { throw 'Seam close-up review failed; retain the candidate without advancing.' }
}
Write-Host "RAC_NECK_CANDIDATE_READY $outputPath -- the face is locked, but the guest still has the final word."
Write-Host 'CPU-only transport. Native material, motion, cooked runtime and human approval remain separate gates.'
