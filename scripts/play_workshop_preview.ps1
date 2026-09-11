[CmdletBinding()]
param(
    [string] $Level = '/Game/SunsetWorkshop/L_WorkshopPreview_v004',
    [string] $CompilerPython
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$project = Join-Path $repoRoot 'work/ue5-validate/RacValidate.uproject'
if ($Level -notmatch '^/Game/SunsetWorkshop/[A-Za-z0-9_]+$') {
    throw 'Choose a saved SunsetWorkshop level, not an arbitrary command line.'
}
$map = Join-Path $repoRoot ('work/ue5-validate/Content/' + $Level.Substring(6) + '.umap')
if (!(Test-Path -LiteralPath $project) -or !(Test-Path -LiteralPath $map)) {
    throw 'The local workshop project/map has not been built. See docs/SUNSET_WORKSHOP.md.'
}
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
$editor = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --unreal-editor) | Select-Object -Last 1
if ($LASTEXITCODE -ne 0 -or -not $editor) { throw 'Could not resolve Unreal Editor; set RAC_UNREAL_EDITOR.' }
$log = Join-Path $repoRoot ('work/sunset-workshop/evidence/interactive-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.log')
# An intentionally visible game window: the guest has asked to take a stroll.
$game = Start-Process -FilePath $editor.Trim() -ArgumentList @(
    ('"' + $project + '"'), $Level, '-game', '-windowed', '-ResX=1600', '-ResY=900',
    '-nop4', '-nosplash', ('"-abslog=' + $log + '"')
) -WorkingDirectory $repoRoot -WindowStyle Normal -PassThru
Write-Host "WORKSHOP_OPEN pid=$($game.Id) -- your boots await. WASD, mouse, Space; Alt+F4 closes."
Write-Host "Uncooked local preview, not a packaged release. Log: $log"
