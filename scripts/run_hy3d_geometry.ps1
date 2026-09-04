[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Request,
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { throw 'Set RAC_LEGACY_ROOT to the studio tree that holds the Hunyuan3D checkout, environment, and pinned runner.' }),
    [string] $RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string] $CompilerPython = $(& py -3.12 -c 'import sys; print(sys.executable)'),
    [int] $MinimumFreeVramMiB = 0,
    [string] $ComfyUrl = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
# Two hash-pinned runners: multiview (three guidance views) and single view
# (the reference image alone). The request's mode selects one after preflight.
$expectedRunnerHashes = @{
    multiview   = 'EBE3900B671A1A32416CFB650AA57967150ACEB8AE2994FC252DA9C61356C207'
    single_view = '119B41DD0DF2AB4E1C9F75A6159F3F8A2C7D47DFC7A20309AC7FBF0519A2AF6C'
}
$runnerNames = @{ multiview = 'run_hy3d_multiview.py'; single_view = 'run_hy3d_single_view.py' }
$generationSchemas = @{ multiview = 'reference-studio.hunyuan3d-multiview.v2'; single_view = 'reference-studio.hunyuan3d-single-view.v1' }
$compilerPython = $CompilerPython
$hyPython = Join-Path $LegacyRoot '.venv-hy3d\Scripts\python.exe'
$runner = Join-Path $LegacyRoot 'scripts\run_hy3d_multiview.py'
$expectedRunnerHash = $expectedRunnerHashes.multiview
$upstream = Join-Path $LegacyRoot 'upstream\Hunyuan3D-2'

foreach ($required in @($hyPython, $upstream)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Hunyuan3D multiview component is missing: $required"
    }
}


$requestPath = (Resolve-Path -LiteralPath $Request).Path
$repoPath = (Resolve-Path -LiteralPath $RepoRoot).Path
$legacyPath = (Resolve-Path -LiteralPath $LegacyRoot).Path
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoPath 'src'
    $preflightLines = @(& $compilerPython -m reference_asset_compiler.cli geometry-preflight `
        $requestPath --legacy-root $legacyPath --repo-root $repoPath 2>&1)
    $preflightExit = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
if ($preflightExit -ne 0) {
    throw "Geometry request preflight failed; inference was not launched: $($preflightLines -join [Environment]::NewLine)"
}
$preflight = ($preflightLines -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $preflight.launch_ready -or $preflight.inference_launched) {
    throw 'Geometry preflight returned an unsafe launch state; inference was not launched'
}
$mode = if ($preflight.mode) { [string]$preflight.mode } else { 'multiview' }
if (-not $runnerNames.ContainsKey($mode)) { throw "Unsupported geometry request mode: $mode" }
$runner = Join-Path $LegacyRoot ('scripts\' + $runnerNames[$mode])
$expectedRunnerHash = $expectedRunnerHashes[$mode]
$requiredFreeVramMiB = if ($MinimumFreeVramMiB -gt 0) {
    $MinimumFreeVramMiB
} elseif ($mode -eq 'single_view') {
    12288
} else {
    18432
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Required Hunyuan3D runner is missing: $runner (copy it from workflows\geometry\hunyuan3d)"
}
$actualRunnerHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash
if ($actualRunnerHash -ne $expectedRunnerHash) {
    throw "Hunyuan runner changed: expected $expectedRunnerHash, found $actualRunnerHash"
}

$gpuLines = @(& nvidia-smi --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits 2>&1)
if ($LASTEXITCODE -ne 0 -or $gpuLines.Count -ne 1) {
    throw 'Unable to read one unambiguous GPU state; inference was not launched'
}
$gpuParts = $gpuLines[0].Split(',')
$freeMiB = [int]$gpuParts[0].Trim()
$utilization = [int]$gpuParts[1].Trim()
$computeApps = @(& nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>&1)

$comfyProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -match '(?i)ComfyUI[\\/]main\.py'
})
$queueRunning = 0
$queuePending = 0
if ($comfyProcesses.Count -gt 0) {
    try {
        $queue = Invoke-RestMethod -Uri ($ComfyUrl.TrimEnd('/') + '/queue') -TimeoutSec 4
        $queueRunning = @($queue.queue_running).Count
        $queuePending = @($queue.queue_pending).Count
    }
    catch {
        throw "ComfyUI owns a live process but its queue could not be verified; inference was not launched: $($_.Exception.Message)"
    }
    if ($queueRunning -gt 0 -or $queuePending -gt 0) {
        throw "ComfyUI queue is busy (running=$queueRunning pending=$queuePending); inference was not launched"
    }
}
if ($freeMiB -lt $requiredFreeVramMiB) {
    throw "GPU has $freeMiB MiB free; $requiredFreeVramMiB MiB is required for $mode. ComfyUI queue was checked (running=$queueRunning pending=$queuePending). No process was killed and inference was not launched. Owners: $($computeApps -join '; ')"
}

$outputDirectory = [System.IO.Path]::GetFullPath([string]$preflight.output_directory)
if (Test-Path -LiteralPath $outputDirectory) {
    throw "Attempt directory already exists; this launcher never retries or overwrites: $outputDirectory"
}
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$candidate = Join-Path $outputDirectory 'candidate.glb'
$generationReport = Join-Path $outputDirectory 'generation.json'
$preparedDirectory = Join-Path $outputDirectory 'prepared'
$attemptReport = Join-Path $outputDirectory 'attempt.json'
$candidateReceipt = Join-Path $outputDirectory 'candidate-receipt.json'

$attempt = [ordered]@{
    schema = 'reference-asset-compiler.hy3d-attempt.v1'
    asset_id = $preflight.asset_id
    status = 'running'
    started_at = [DateTimeOffset]::Now.ToString('o')
    request = $preflight.request
    request_sha256 = $preflight.request_sha256
    runner = $runner
    runner_sha256 = $actualRunnerHash.ToLowerInvariant()
    free_vram_mib = $freeMiB
    gpu_utilization_percent = $utilization
    gpu_compute_owners = $computeApps
    comfy_process_count = $comfyProcesses.Count
    comfy_queue_running = $queueRunning
    comfy_queue_pending = $queuePending
    retry = $false
}
$attempt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $attemptReport -Encoding utf8

$inputByView = @{}
foreach ($input in $preflight.inputs) { $inputByView[[string]$input.view] = $input }
$parameters = $preflight.parameters
Write-Host "HY3D_GEOMETRY_LAUNCH_READY asset=$($preflight.asset_id) free_mib=$freeMiB utilization=$utilization% runner_sha256=$actualRunnerHash"

try {
    $viewArguments = if ($mode -eq 'single_view') {
        @('--image', [string]$inputByView.primary.path)
    } else {
        @('--front', [string]$inputByView.front.path, '--left', [string]$inputByView.left.path, '--back', [string]$inputByView.back.path)
    }
    & $hyPython $runner @viewArguments `
        --output $candidate `
        --report $generationReport `
        --prepared-dir $preparedDirectory `
        --steps ([int]$parameters.steps) `
        --octree-resolution ([int]$parameters.octree_resolution) `
        --chunks ([int]$parameters.chunks) `
        --seed ([int]$parameters.seed)
    $runnerExit = $LASTEXITCODE
    if ($runnerExit -ne 0) {
        throw "Hunyuan3D multiview exited $runnerExit; the attempt is retained and will not be auto-retried"
    }
    foreach ($requiredOutput in @($candidate, $generationReport)) {
        if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
            throw "Hunyuan3D reported success but output is missing: $requiredOutput"
        }
    }
    $generation = Get-Content -LiteralPath $generationReport -Raw | ConvertFrom-Json
    if ($generation.schema -ne $generationSchemas[$mode]) {
        throw 'Hunyuan3D generation report has an unsupported schema'
    }

    $receipt = [ordered]@{
        schema = 'reference-asset-compiler.geometry-candidate.v1'
        asset_id = $preflight.asset_id
        adapter = 'hunyuan3d_2_1'
        ok = $true
        candidate = $candidate
        candidate_sha256 = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        image_sha256 = $preflight.source_authority.sha256
        source_image = $preflight.source_authority.path
        source_image_sha256 = $preflight.source_authority.sha256
        mode = $mode
        # Multiview receipts bind the derived guidance views and their report;
        # a single-view receipt is bound by the source image hash alone.
        image_inputs = $(if ($mode -eq 'multiview') { @($preflight.inputs) } else { $null })
        image_derivation_report = $(if ($mode -eq 'multiview') { $preflight.derivation_report.path } else { $null })
        image_derivation_report_sha256 = $(if ($mode -eq 'multiview') { $preflight.derivation_report.sha256 } else { $null })
        generation_report = $generationReport
        generation_report_sha256 = (Get-FileHash -LiteralPath $generationReport -Algorithm SHA256).Hash.ToLowerInvariant()
        request = $preflight.request
        request_sha256 = $preflight.request_sha256
        runner = $runner
        runner_sha256 = $actualRunnerHash.ToLowerInvariant()
        parameters = $parameters
        status = 'candidate -- not approved, not an asset'
    }
    $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $candidateReceipt -Encoding utf8
    $attempt.status = 'succeeded'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.candidate_sha256 = $receipt.candidate_sha256
    $attempt.candidate_receipt = $candidateReceipt
    $attempt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $attemptReport -Encoding utf8
}
catch {
    $attempt.status = 'failed'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.failure = $_.Exception.Message
    $attempt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $attemptReport -Encoding utf8
    throw
}

Write-Host "HY3D_GEOMETRY_CANDIDATE_OK receipt=$candidateReceipt -- the machine has spoken; the modeling gate has not."
