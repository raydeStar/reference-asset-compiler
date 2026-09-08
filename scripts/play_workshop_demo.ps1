[CmdletBinding()]
param([ValidateSet('Night','Day','Ayric','AyricLegacy')][string]$Lighting='Night')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$variant = if ($Lighting -eq 'Ayric') {
    @{
        Build='output/sunset-workshop-ayric-v051/Windows'
        Map='/Game/SunsetWorkshop/L_WorkshopNight_v051'
        Receipt='work/sunset-workshop/evidence/cooked-ayric-v051/audit.json'
        Summary='Ayric v051 review: repaired locomotion, separate detailed AI head, bounded neck colour/normal transition. Final neck appearance awaits your approval.'
    }
} elseif ($Lighting -eq 'AyricLegacy') {
    @{
        Build='output/sunset-workshop-ayric-v036/Windows'
        Map='/Game/SunsetWorkshop/L_WorkshopNight_v036'
        Receipt='work/sunset-workshop/evidence/cooked-ayric-v036/audit.json'
        Summary='Ayric v036: repaired anatomical pivots, hand retargeting and in-place locomotion. Existing face retained; face repair remains under review.'
    }
} elseif ($Lighting -eq 'Night') {
    @{
        Build='output/sunset-workshop-night-v026/Windows'
        Map='/Game/SunsetWorkshop/L_WorkshopNight_v026'
        Receipt='work/sunset-workshop/evidence/night-review-v026.json'
        Summary='Night v026: moonlight, warm work areas, starry sky and low desert dust.'
    }
} else {
    @{
        Build='output/sunset-workshop-demo-v018-r2/Windows'
        Map='/Game/SunsetWorkshop/L_WorkshopDemo_v018'
        Receipt='work/sunset-workshop/evidence/final-demo-v018.json'
        Summary='Preserved daytime v018: warm workshop and real-depth desert exterior.'
    }
}
$buildRoot = Join-Path $repoRoot $variant.Build
$executable = Join-Path $buildRoot 'RacValidate.exe'
if (!(Test-Path -LiteralPath $executable)) {
    throw 'Cooked workshop build is missing. See docs/SUNSET_WORKSHOP.md.'
}
if (!(Test-Path -LiteralPath (Join-Path $repoRoot $variant.Receipt))) {
    throw 'This variant has not completed its packaged visual review. The butler refuses to bluff.'
}
if ($Lighting -in @('Ayric','AyricLegacy')) {
    $audit = Get-Content -Raw -LiteralPath (Join-Path $repoRoot $variant.Receipt) | ConvertFrom-Json
    if (!$audit.ok -or !$audit.cooked_runtime -or $audit.map -ne ($variant.Map.Split('/')[-1])) {
        throw 'The Ayric package lacks a passing matching runtime audit. Knees first, ceremony later.'
    }
}
$log = Join-Path $repoRoot ('work/sunset-workshop/evidence/demo-play-' + $Lighting.ToLowerInvariant() + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.log')
# Intentionally visible: the guest asked to wander, not admire a process ID.
$game = Start-Process -FilePath $executable -ArgumentList @(
    $variant.Map, '-windowed', '-ResX=1600', '-ResY=900',
    '-nosplash', ('"-abslog=' + $log + '"')
) -WorkingDirectory $buildRoot -WindowStyle Normal -PassThru
$who = if ($Lighting -in @('Ayric','AyricLegacy')) { 'Ayric' } else { 'Manny' }
Write-Host "WORKSHOP_DEMO_OPEN pid=$($game.Id) -- $who has the keys. WASD, mouse, Space; Alt+F4 exits."
Write-Host "$($variant.Summary) Log: $log"
