<#
.SYNOPSIS
  Cook and package one workshop level into a fresh, retained archive.

.DESCRIPTION
  Wraps RunUAT BuildCookRun for the validation project. Refuses to overwrite
  an existing archive, never retries, and writes the full UAT log beside the
  archive so a failed cook keeps its evidence. Requires a completed player
  build receipt for the level (the JSON written by swap_workshop_player.py or
  a scene build script) so a level nobody has built cannot be cooked by
  accident.

.EXAMPLE
  .\scripts\cook_workshop_level.ps1 -Map /Game/SunsetWorkshop/L_WorkshopNight_v028 `
      -Archive output/sunset-workshop-ayric-v028 `
      -Receipt work/sunset-workshop/evidence/ayric-player-v028.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Map,
    [Parameter(Mandatory = $true)][string] $Archive,
    [Parameter(Mandatory = $true)][string] $Receipt,
    [string] $Project = 'work/ue5-validate/RacValidate.uproject',
    [ValidateSet('Development', 'Shipping')][string] $Configuration = 'Development'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$receiptPath = Join-Path $repoRoot $Receipt
if (-not (Test-Path -LiteralPath $receiptPath)) { throw "No build receipt at $receiptPath; build the level before cooking it." }
# Not `$receipt`: PowerShell variables are case-insensitive, and assigning a
# parsed object to the [string] parameter would coerce it to text.
$build = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if (-not $build.ok) { throw "The build receipt reports ok=false; nothing to cook." }
if ($build.level -and $build.level -ne $Map) { throw "Receipt is for $($build.level), not $Map." }

$archivePath = Join-Path $repoRoot $Archive
if (Test-Path -LiteralPath $archivePath) { throw "Retained archive exists: $archivePath. Choose a fresh version." }
$projectPath = Join-Path $repoRoot $Project
if (-not (Test-Path -LiteralPath $projectPath)) { throw "Project not found: $projectPath" }

$unrealCmd = (& python (Join-Path $PSScriptRoot 'rac_env.py') --unreal-cmd) | Select-Object -Last 1
$uat = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $unrealCmd)))) 'Build\BatchFiles\RunUAT.bat'
if (-not (Test-Path -LiteralPath $uat)) { throw "RunUAT.bat not found next to $unrealCmd" }

$staging = Join-Path $repoRoot ('work/sunset-workshop/staged-' + (Split-Path -Leaf $Archive))
$log = "$archivePath.cook.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archivePath) | Out-Null
Write-Host "WORKSHOP_COOK_BEGIN map=$Map archive=$archivePath"
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $uat BuildCookRun "-project=$projectPath" -noP4 -platform=Win64 "-clientconfig=$Configuration" `
        -build -cook "-map=$Map" -stage -pak -archive "-stagingdirectory=$staging" `
        "-archivedirectory=$archivePath" -unattended -utf8output *> $log
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previous
}
if ($code -ne 0) { throw "Cook failed with exit code $code. No automatic retry. Log: $log" }
$exe = Get-ChildItem -LiteralPath $archivePath -Recurse -Filter '*.exe' | Where-Object { $_.Directory.Name -eq 'Windows' } | Select-Object -First 1
$bytes = (Get-ChildItem -LiteralPath $archivePath -Recurse -File | Measure-Object -Property Length -Sum).Sum
$summary = [ordered]@{
    schema = 'reference-asset-compiler.workshop-cook.v1'
    map = $Map
    archive = $archivePath
    receipt = $receiptPath
    configuration = $Configuration
    executable = $(if ($exe) { $exe.FullName } else { $null })
    bytes = $bytes
    log = $log
    completed_utc = [DateTime]::UtcNow.ToString('o')
}
[System.IO.File]::WriteAllText("$archivePath.cook.json", ($summary | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding $false))
Write-Host "WORKSHOP_COOK_OK $archivePath ($([math]::Round($bytes / 1MB)) MB) -- the level is boxed; the walk is yours."
