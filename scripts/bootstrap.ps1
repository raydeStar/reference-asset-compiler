[CmdletBinding()]
param(
    [string] $PythonLauncher = 'py',
    [string] $PythonVersion = '3.12'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repoRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    & $PythonLauncher "-$PythonVersion" -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed with exit code $LASTEXITCODE"
    }
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed with exit code $LASTEXITCODE"
}
& $python -m pip install -e "${repoRoot}[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Editable install failed with exit code $LASTEXITCODE"
}

Write-Host "RAC_BOOTSTRAP_OK $python -- the workshop is swept and the compiler has found its monocle."
