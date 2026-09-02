[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$python = if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $venvPython
} else {
    (Get-Command py -ErrorAction Stop).Source
}
$usingLauncher = [System.IO.Path]::GetFileName($python) -ieq 'py.exe'
$previousPythonPath = $env:PYTHONPATH

function Invoke-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $ArgumentList
    )

    if ($usingLauncher) {
        & $python '-3.12' @ArgumentList
    } else {
        & $python @ArgumentList
    }
}

try {
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    Invoke-RepoPython -ArgumentList @(
        '-m', 'compileall', '-q', (Join-Path $repoRoot 'src')
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Python compilation failed with exit code $LASTEXITCODE"
    }
    # The Blender stage scripts import bpy and cannot be executed outside
    # Blender, but a syntax error in one costs a full headless round trip to
    # discover. Byte-compiling them here is cheap and catches that.
    Invoke-RepoPython -ArgumentList @(
        '-m', 'compileall', '-q', (Join-Path $repoRoot 'scripts\blender')
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Blender stage scripts failed to compile with exit code $LASTEXITCODE"
    }
    Invoke-RepoPython -ArgumentList @(
        '-m', 'unittest', 'discover', '-s', (Join-Path $repoRoot 'tests'), '-v'
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Contract tests failed with exit code $LASTEXITCODE"
    }
    Invoke-RepoPython -ArgumentList @(
        '-m',
        'reference_asset_compiler.cli',
        'plan',
        (Join-Path $repoRoot 'examples\humanoid.json'),
        '--output',
        (Join-Path $repoRoot 'output\verify-routing.json')
    )
    if ($LASTEXITCODE -ne 0) {
        throw "CLI smoke test failed with exit code $LASTEXITCODE"
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host 'RAC_VERIFY_OK -- every gatekeeper is awake, and none accepted a flattering render as identification.'
