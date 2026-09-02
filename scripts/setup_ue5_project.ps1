<#
.SYNOPSIS
  Scaffold the disposable UE 5.8 validation project the compiler imports into.

.DESCRIPTION
  work\ue5-validate is ignored by Git on purpose: it fills with imported assets,
  derived data and cooked output. A fresh clone therefore has no project. This
  creates one that matches the development workstation:

    * RacValidate.uproject with the Python and Editor Scripting plugins;
    * Config files that start on the gallery map, use the Third Person game
      mode, cook the gallery, and use Enhanced Input;
    * the Third Person BLUEPRINT template's character, game mode and player
      controller, the shared Mannequin content and the Input pack, copied from
      your own Unreal Engine install (never redistributed here).

  It refuses to touch an existing project unless -Force is given, and it never
  deletes anything.

.EXAMPLE
  .\scripts\setup_ue5_project.ps1
  .\scripts\setup_ue5_project.ps1 -Destination D:\scratch\RacValidate
#>
[CmdletBinding()]
param(
    [string] $Destination,
    [string] $UnrealEditor = $env:RAC_UNREAL_EDITOR,
    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) { $Destination = Join-Path $repoRoot 'work\ue5-validate' }
if (-not $UnrealEditor) {
    $UnrealEditor = (& python (Join-Path $PSScriptRoot 'rac_env.py') --unreal-editor) | Select-Object -Last 1
}
if (-not (Test-Path -LiteralPath $UnrealEditor -PathType Leaf)) {
    throw "UnrealEditor.exe not found at '$UnrealEditor'. Set RAC_UNREAL_EDITOR."
}
# <engine>\Engine\Binaries\Win64\UnrealEditor.exe -> <engine>
$engineRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $UnrealEditor)))
$templates = Join-Path $engineRoot 'Templates'
# Engine association from the install's own Build.version, so a 5.7 or 5.9
# install writes a project it opens without a conversion prompt.
$engineVersion = '5.8'
$buildVersion = Join-Path $engineRoot 'Engine\Build\Build.version'
if (Test-Path -LiteralPath $buildVersion) {
    $bv = Get-Content -LiteralPath $buildVersion -Raw | ConvertFrom-Json
    $engineVersion = "$($bv.MajorVersion).$($bv.MinorVersion)"
}
if ($engineVersion -ne '5.8') {
    Write-Warning "Verified against UE 5.8; found $engineVersion. The project is written for $engineVersion, but the editor Python API and template layout may differ."
}
$sources = [ordered]@{
    'Content\Characters' = Join-Path $templates 'TemplateResources\High\Characters\Content'
    'Content\Input'      = Join-Path $templates 'TemplateResources\High\Input\Content'
    'Content\ThirdPerson\Blueprints' = Join-Path $templates 'TP_ThirdPersonBP\Content\ThirdPerson\Blueprints'
}
foreach ($src in $sources.Values) {
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Template content missing from this engine install: $src (UE 5.8 Third Person template expected)"
    }
}

$uproject = Join-Path $Destination 'RacValidate.uproject'
if ((Test-Path -LiteralPath $uproject) -and -not $Force) {
    Write-Host "RAC_UE5_PROJECT_EXISTS $uproject -- pass -Force to refresh config and template content."
    exit 0
}
New-Item -ItemType Directory -Force -Path $Destination, (Join-Path $Destination 'Config'), (Join-Path $Destination 'Content\Compiled') | Out-Null

$projectJson = @'
{
  "FileVersion": 3,
  "EngineAssociation": "__ENGINE_VERSION__",
  "Category": "Validation",
  "Description": "Clean destination for reference-asset-compiler import validation. Disposable; never an authority.",
  "Plugins": [
    { "Name": "PythonScriptPlugin", "Enabled": true },
    { "Name": "EditorScriptingUtilities", "Enabled": true }
  ]
}
'@
$engineIni = @'
[/Script/EngineSettings.GameMapsSettings]
GlobalDefaultGameMode=/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode.BP_ThirdPersonGameMode_C
GameDefaultMap=/Game/Compiled/L_RacGallery
EditorStartupMap=/Game/Compiled/L_RacGallery

[/Script/Engine.RendererSettings]
r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange=True
'@
$gameIni = @'
[/Script/UnrealEd.ProjectPackagingSettings]
+MapsToCook=(FilePath="/Game/Compiled/L_RacGallery")
+DirectoriesToAlwaysCook=(Path="/Game/Compiled")
'@
$inputIni = @'
[/Script/Engine.InputSettings]
DefaultPlayerInputClass=/Script/EnhancedInput.EnhancedPlayerInput
DefaultInputComponentClass=/Script/EnhancedInput.EnhancedInputComponent
DefaultViewportMouseCaptureMode=CapturePermanently_IncludingInitialMouseDown
DefaultViewportMouseLockMode=LockOnCapture
-ConsoleKeys=Tilde
+ConsoleKeys=Tilde
'@
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($uproject, $projectJson.Replace('__ENGINE_VERSION__', $engineVersion), $utf8)
[System.IO.File]::WriteAllText((Join-Path $Destination 'Config\DefaultEngine.ini'), $engineIni, $utf8)
[System.IO.File]::WriteAllText((Join-Path $Destination 'Config\DefaultGame.ini'), $gameIni, $utf8)
[System.IO.File]::WriteAllText((Join-Path $Destination 'Config\DefaultInput.ini'), $inputIni, $utf8)

foreach ($entry in $sources.GetEnumerator()) {
    $target = Join-Path $Destination $entry.Key
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $entry.Value '*') -Destination $target -Recurse -Force
    $count = (Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object).Count
    Write-Host ("  {0,-34} {1,5} files <- {2}" -f $entry.Key, $count, $entry.Value)
}
Write-Host "RAC_UE5_PROJECT_OK $uproject -- the stage is built; the actors arrive with import_and_verify.py."
