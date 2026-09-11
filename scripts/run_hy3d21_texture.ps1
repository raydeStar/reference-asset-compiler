[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Mesh,
    [Parameter(Mandatory = $true)][string] $Reference,
    [Parameter(Mandatory = $true)][string] $OutputObj,
    [ValidateRange(6, 12)][int] $Views = 6,
    [ValidateSet(512, 768)][int] $Resolution = 512,
    [string] $DiagnosticsDir,
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { throw 'Set RAC_LEGACY_ROOT to the studio tree that holds the Hunyuan3D-Paint runner, upstream checkout and models.' }),
    [int] $MinimumFreeVramMiB = 21504,
    [string] $ComfyUrl = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string] $Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string] $Text
    )
    # Windows PowerShell 5.1's Set-Content writes a byte-order mark for utf8,
    # and every Python reader of these receipts then sees "\ufeff{" and
    # rejects the JSON. Receipts are UTF-8 without a BOM, always.
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding $false))
}
$expectedRunnerHash = 'B039065EA96E0E63EFFECBA4379F63B8228F830B036EF1392790E5BF6B8F8A8B'
$python = Join-Path $LegacyRoot '.venv-hy3d21\Scripts\python.exe'
$runner = Join-Path $LegacyRoot 'scripts\run_hy3d21_pbr.py'
$upstream = Join-Path $LegacyRoot 'upstream\Hunyuan3D-2.1'
$models = Join-Path $LegacyRoot 'models\hy3d21\Hunyuan3D-2.1'

foreach ($required in @($python, $runner, $upstream, $models)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Hunyuan3D-Paint component is missing: $required"
    }
}

$actualRunnerHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash
if ($actualRunnerHash -ne $expectedRunnerHash) {
    throw "Legacy Hunyuan runner changed: expected $expectedRunnerHash, found $actualRunnerHash"
}

$meshPath = (Resolve-Path -LiteralPath $Mesh).Path
$referencePath = (Resolve-Path -LiteralPath $Reference).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputObj)
if ([System.IO.Path]::GetExtension($outputPath).ToLowerInvariant() -ne '.obj') {
    throw 'Hunyuan3D-Paint output must use an .obj path'
}
foreach ($extension in @('.obj', '.glb', '.validation.json', '.execution.json')) {
    $retained = [System.IO.Path]::ChangeExtension($outputPath, $extension)
    if (Test-Path -LiteralPath $retained) {
        throw "Paint attempt already has retained evidence; choose a new attempt: $retained"
    }
}
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null

$gpuState = & (Join-Path $PSScriptRoot 'assert_gpu_available.ps1') -MinimumFreeVramMiB $MinimumFreeVramMiB -ComfyUrl $ComfyUrl
$freeMiB = $gpuState.free_mib
$utilization = $gpuState.utilization
$computeApps = $gpuState.compute_owners
$comfyProcessCount = $gpuState.comfy_process_count
$queueRunning = $gpuState.queue_running
$queuePending = $gpuState.queue_pending

Write-Host "HY3D21_LAUNCH_READY free_mib=$freeMiB utilization=$utilization% runner_sha256=$actualRunnerHash"
$executionPath = [System.IO.Path]::ChangeExtension($outputPath, '.execution.json')
if (Test-Path -LiteralPath $executionPath) {
    throw "Execution receipt already exists; preserve it and choose a new attempt: $executionPath"
}
$startedUtc = [DateTime]::UtcNow.ToString('o')
$runnerArgs = @($runner, $meshPath, $referencePath, $outputPath, '--views', $Views, '--resolution', $Resolution)
if ($DiagnosticsDir) {
    $diagnosticsPath = [System.IO.Path]::GetFullPath($DiagnosticsDir)
    if (Test-Path -LiteralPath $diagnosticsPath) {
        throw "Diagnostics directory already exists; refusing to overwrite evidence: $diagnosticsPath"
    }
    $runnerArgs += @('--diagnostics-dir', $diagnosticsPath)
}
$report = [System.IO.Path]::ChangeExtension($outputPath, '.validation.json')
# The receipt exists BEFORE the runner starts, with status 'running'. A wrapper
# killed between here and the first painted view still leaves evidence that an
# attempt was made, and the operator driver then refuses to relaunch into the
# same attempt directory instead of silently retrying crashed inference.
$execution = [ordered]@{
    schema = 'reference-asset-compiler.paint-execution.v1'
    status = 'running'
    started_utc = $startedUtc
    completed_utc = $null
    runner = $runner
    runner_sha256 = $actualRunnerHash.ToLowerInvariant()
    input_mesh = $meshPath
    input_mesh_sha256 = (Get-FileHash -LiteralPath $meshPath).Hash.ToLowerInvariant()
    reference = $referencePath
    reference_sha256 = (Get-FileHash -LiteralPath $referencePath).Hash.ToLowerInvariant()
    output_obj = $outputPath
    views = $Views
    resolution = $Resolution
    initial_free_vram_mib = $freeMiB
    gpu_utilization_percent = $utilization
    gpu_compute_owners = $computeApps
    comfy_process_count = $comfyProcessCount
    comfy_queue_running = $queueRunning
    comfy_queue_pending = $queuePending
    exit_code = $null
    clean_process_exit = $false
    validation_present = $false
    retry_performed = $false
}
Write-Utf8NoBom -Path $executionPath -Text ($execution | ConvertTo-Json -Depth 5)

try {
    # The runner and its dependencies write ordinary progress and warnings to
    # stderr. Under $ErrorActionPreference = 'Stop', any caller that redirects
    # our output to a log (2>&1, *>) would turn the first such line into a
    # terminating error and kill the paint before it finished. Relax only
    # around the call; the exit code and the receipt below are the verdict.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python @runnerArgs
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    $execution.completed_utc = [DateTime]::UtcNow.ToString('o')
    $execution.exit_code = $exitCode
    $execution.clean_process_exit = ($exitCode -eq 0)
    $execution.validation_present = (Test-Path -LiteralPath $report -PathType Leaf)
    $execution.status = $(if ($exitCode -eq 0) { 'completed' } else { 'failed' })
    Write-Utf8NoBom -Path $executionPath -Text ($execution | ConvertTo-Json -Depth 5)
    if ($exitCode -ne 0) {
        Write-Warning "Painter exited abnormally ($exitCode). Retaining outputs and receipt; no retry. Geometry/UV validation below is separate from process health."
    }
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw "Hunyuan3D-Paint exited $exitCode without a validation report; it will not be auto-retried"
    }
    $gate = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $gate.faces_equal -or [double]$gate.geometry_delta -gt 0.000001 -or [double]$gate.uv_delta -gt 0.000001) {
        throw "Hunyuan3D-Paint topology/UV gate failed: $report"
    }
    if (-not (Test-Path -LiteralPath ([System.IO.Path]::ChangeExtension($outputPath, '.glb')) -PathType Leaf)) {
        throw 'Hunyuan3D-Paint validation passed but the expected GLB is missing'
    }
}
catch {
    $execution.status = 'failed'
    if (-not $execution.completed_utc) { $execution.completed_utc = [DateTime]::UtcNow.ToString('o') }
    $execution.failure = $_.Exception.Message
    Write-Utf8NoBom -Path $executionPath -Text ($execution | ConvertTo-Json -Depth 5)
    throw
}

Write-Host "HY3D21_TEXTURE_VALIDATED exit_code=$exitCode report=$report -- the paint is admitted; the mirror retains veto power."
