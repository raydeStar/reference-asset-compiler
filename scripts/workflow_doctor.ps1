[CmdletBinding()]
param(
    [string] $LegacyRoot = $env:RAC_LEGACY_ROOT,
    [string] $ComfyRoot = $env:RAC_COMFY_ROOT,
    [string] $Blender = $env:RAC_BLENDER,
    [string] $UnrealCmd = $env:RAC_UNREAL_CMD,
    [ValidateSet('ledger', 'geometry', 'texture', 'ue', 'all')][string] $Profile = 'all',
    [string] $Python,
    [switch] $Json,
    [switch] $SkipAddonProbes
)
$ErrorActionPreference = 'Stop'
$selectedPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $Python
$arguments = @((Join-Path $PSScriptRoot 'workflow_doctor.py'), '--profile', $Profile)
foreach ($pair in @(@('--legacy-root', $LegacyRoot), @('--comfy-root', $ComfyRoot),
                     @('--blender', $Blender), @('--unreal-cmd', $UnrealCmd))) {
    if ($pair[1]) { $arguments += $pair }
}
if ($Json) { $arguments += '--json' }
if ($SkipAddonProbes) { $arguments += '--skip-addon-probes' }
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $selectedPython @arguments 2>&1 | ForEach-Object { $_.ToString() }
    $doctorExit = $LASTEXITCODE
}
finally { $ErrorActionPreference = $previousPreference }
exit $doctorExit
