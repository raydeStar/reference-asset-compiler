[CmdletBinding()]
param([string] $Python, [string] $WheelDir)
$ErrorActionPreference = 'Stop'
$selectedPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $Python
$arguments = @((Join-Path $PSScriptRoot 'verify.py'))
if ($WheelDir) { $arguments += @('--wheel-dir', $WheelDir) }
# PowerShell 5.1 treats redirected native stderr as errors under Stop. Preserve
# progress output and decide using the process exit code, as any decent butler would.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $selectedPython @arguments 2>&1 | ForEach-Object { $_.ToString() }
    $verifyExit = $LASTEXITCODE
}
finally { $ErrorActionPreference = $previousPreference }
exit $verifyExit
