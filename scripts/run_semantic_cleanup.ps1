[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Job,
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [string] $OutputDirectory,
    [string] $Blender = $env:RAC_BLENDER
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$compilerPython = $(& py -3.12 -c 'import sys; print(sys.executable)')
$jobPath = (Resolve-Path -LiteralPath $Job).Path
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
}
if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) {
    throw "Blender is unavailable: $Blender"
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $preflightLines = @(& $compilerPython -m reference_asset_compiler.cli `
        cleanup-preflight $jobPath $inputPath 2>&1)
    $preflightExit = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
if ($preflightExit -ne 0) {
    throw "Semantic cleanup preflight failed: $($preflightLines -join [Environment]::NewLine)"
}
$preflight = ($preflightLines -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $preflight.launch_ready -or $preflight.cleanup_launched) {
    throw 'Semantic cleanup preflight returned an unsafe state'
}

$cleanupRoot = [System.IO.Path]::GetFullPath((Join-Path $jobPath 'cleanup'))
$attemptDirectory = if ($OutputDirectory) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $cleanupRoot 'semantic-v1-attempt001'
}
$cleanupPrefix = $cleanupRoot.TrimEnd('\') + '\'
if (-not $attemptDirectory.StartsWith(
        $cleanupPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Semantic cleanup output must remain under the workspace cleanup directory'
}
if (Test-Path -LiteralPath $attemptDirectory) {
    throw "Cleanup attempt directory already exists; refusing retry or overwrite: $attemptDirectory"
}
[System.IO.Directory]::CreateDirectory($attemptDirectory) | Out-Null
$outputMesh = Join-Path $attemptDirectory 'cleaned.blend'
$topologyReport = Join-Path $attemptDirectory 'topology.json'
$receipt = Join-Path $attemptDirectory 'semantic-cleanup-receipt.json'
$attemptPath = Join-Path $attemptDirectory 'attempt.json'
$attempt = [ordered]@{
    schema = 'reference-asset-compiler.semantic-cleanup-attempt.v1'
    asset_id = $preflight.asset_id
    input_mesh = $inputPath
    input_mesh_sha256 = $preflight.input_mesh_sha256
    blender = $Blender
    started_at = [DateTimeOffset]::Now.ToString('o')
    status = 'running'
    retry = $false
}
$attempt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $attemptPath -Encoding utf8

try {
    & $Blender --background --factory-startup --python-exit-code 1 `
        --python (Join-Path $PSScriptRoot 'blender\semantic_cleanup.py') -- `
        $inputPath $outputMesh $topologyReport
    if ($LASTEXITCODE -ne 0) {
        throw "Blender semantic cleanup exited $LASTEXITCODE; the attempt is retained and will not be retried"
    }
    foreach ($path in @($outputMesh, $topologyReport)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Semantic cleanup output is missing: $path"
        }
    }

    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $repoRoot 'src'
        & $compilerPython -m reference_asset_compiler.cli cleanup-receipt `
            $jobPath $inputPath $outputMesh $topologyReport --output $receipt
        if ($LASTEXITCODE -ne 0) { throw 'Semantic cleanup receipt validation failed' }
        & $compilerPython -m reference_asset_compiler.cli promote $jobPath semantic_cleanup `
            --evidence $inputPath --evidence $outputMesh --evidence $topologyReport `
            --evidence $receipt `
            --note 'Conservative topology sanitation preserved the approved surface; no semantic parts were invented or removed.' `
            --approved-by 'semantic_cleanup.py'
        if ($LASTEXITCODE -ne 0) { throw 'Semantic cleanup ledger promotion failed' }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
    $attempt.status = 'succeeded'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.output_mesh_sha256 = (Get-FileHash -LiteralPath $outputMesh -Algorithm SHA256).Hash.ToLowerInvariant()
    $attempt.receipt = $receipt
    $attempt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $attemptPath -Encoding utf8
}
catch {
    $attempt.status = 'failed'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.failure = $_.Exception.Message
    $attempt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $attemptPath -Encoding utf8
    throw
}

Write-Host "RAC_SEMANTIC_CLEANUP_RECORDED asset=$($preflight.asset_id) receipt=$receipt -- dust removed; identity untouched."
