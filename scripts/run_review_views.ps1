<#
.SYNOPSIS
  Fixed-view evidence for one mesh, with a manifest a consumer can bind to.

.DESCRIPTION
  A derivative is judged by looking at it, and a good front view cannot conceal
  a broken side. This renders the four fixed views in both passes -- the
  textured read, and flat clay under a normals matcap where faceting and
  flipped faces have nowhere to hide behind albedo detail -- and then writes a
  manifest naming every file with its hash beside the hash of the mesh they are
  of. Evidence nobody can bind to a source is not evidence.

  Nothing is judged here. It renders, lists, and stops.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [ValidateRange(256, 2048)][int] $Resolution = 768,
    [string] $Blender = $env:RAC_BLENDER,
    [string] $CompilerPython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string] $Text
    )
    # Windows PowerShell 5.1's Set-Content writes a byte-order mark for utf8,
    # and every Python reader of these receipts then sees "﻿{" and
    # rejects the JSON. Receipts are UTF-8 without a BOM, always.
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding $false))
}

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    # Evidence is retained, never replaced: a later render into the same place
    # would quietly make an older judgement refer to pictures nobody can see.
    throw "Refusing to overwrite review evidence: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$driver = Join-Path $repoRoot 'scripts\blender\render_turnaround.py'
$log = Join-Path $outputPath 'render.log'
$manifest = Join-Path $outputPath 'views.json'

Write-Host 'RAC_REVIEW_VIEWS_BEGIN -- a good front view cannot conceal a broken side.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the merge below would turn the first such line into a terminating
# error and kill the wrapper mid-run, with no evidence. Relax only around the
# call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' '--python' $driver '--' `
        $inputPath $outputPath $Resolution 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    throw "Fixed-view rendering failed with exit code $exitCode. Evidence: $log. No retry was attempted."
}

$expected = @(
    @{ view = 'front'; pass = 'beauty' }, @{ view = 'three-quarter'; pass = 'beauty' },
    @{ view = 'side'; pass = 'beauty' }, @{ view = 'back'; pass = 'beauty' },
    @{ view = 'front'; pass = 'matcap' }, @{ view = 'three-quarter'; pass = 'matcap' },
    @{ view = 'side'; pass = 'matcap' }, @{ view = 'back'; pass = 'matcap' }
)
$views = @()
foreach ($entry in $expected) {
    $name = "$($entry.pass)-$($entry.view).png"
    $file = Join-Path $outputPath $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Rendering exited 0 without writing $name. Evidence: $log"
    }
    $views += [ordered]@{
        view = $entry.view
        pass = $entry.pass
        file = $name
        sha256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$report = [ordered]@{
    schema = 'reference-asset-compiler.review-views.v1'
    source = $inputPath
    # Every picture is bound to the exact bytes it is a picture of. Evidence
    # that cannot be tied to a source is a screenshot, not evidence.
    source_sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    resolution = $Resolution
    passes = @('beauty', 'matcap')
    views = $views
    judged = $false
    note = 'Fixed views only. Nothing here is a verdict; a person reads them.'
}
Write-Utf8NoBom -Path $manifest -Text ($report | ConvertTo-Json -Depth 6)
Write-Host "RAC_REVIEW_VIEWS_OK manifest=$manifest views=$($views.Count)"
