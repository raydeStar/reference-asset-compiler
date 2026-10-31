[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Request,
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { throw 'Set RAC_LEGACY_ROOT to the studio tree that holds the Hunyuan3D checkout, environment, and pinned runner.' }),
    [string] $RepoRoot,
    [string] $CompilerPython,
    [int] $MinimumFreeVramMiB = 0,
    [string] $ComfyUrl = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
# Resolved here, not as a param default: Windows PowerShell 5.1 leaves
# $PSScriptRoot empty inside a [CmdletBinding()] script's param defaults.
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
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
# Two hash-pinned runners: multiview (three guidance views) and single view
# (the reference image alone). The request's mode selects one after preflight.
$expectedRunnerHashes = @{
    multiview   = '1CA6E74756F1DF02240A97E35DB3C68DD3F1DE2179908C0CD36588D0BAB599E6'
    single_view = 'D8AACD0D0963B2A694170725678913C6F45CD7C9904BCF9699E13990E59671CD'
}
$runnerNames = @{ multiview = 'run_hy3d_multiview.py'; single_view = 'run_hy3d_single_view.py' }
$generationSchemas = @{ multiview = 'reference-studio.hunyuan3d-multiview.v2'; single_view = 'reference-studio.hunyuan3d-single-view.v1' }
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
$hyPython = Join-Path $LegacyRoot '.venv-hy3d\Scripts\python.exe'
$runnerRoot = Join-Path $RepoRoot 'workflows\geometry\hunyuan3d'
$runner = Join-Path $runnerRoot 'run_hy3d_multiview.py'
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
# Native stderr merged with 2>&1 becomes an ErrorRecord in Windows PowerShell
# 5.1, and under Stop the first warning line would terminate this launcher.
# Relax only around each native call; exit codes decide, as they always did.
$previousPythonPath = $env:PYTHONPATH
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $env:PYTHONPATH = Join-Path $repoPath 'src'
    $preflightLines = @(& $compilerPython -m reference_asset_compiler.cli geometry-preflight `
        $requestPath --legacy-root $legacyPath --repo-root $repoPath 2>&1 | ForEach-Object { $_.ToString() })
    $preflightExit = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousPreference
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
# Execute the versioned runner directly. The studio supplies its environment
# and upstream install, not a second mutable copy of our spellbook.
$runner = Join-Path $runnerRoot $runnerNames[$mode]
$expectedRunnerHash = $expectedRunnerHashes[$mode]
$releaseStages = [bool]$preflight.parameters.release_stages
# Older preflight output has no volume_decoding; it meant the dense decoder.
$volumeDecoding = if ($preflight.parameters.volume_decoding) { [string]$preflight.parameters.volume_decoding } else { 'dense' }
# Floors are measured peaks plus headroom (docs/evidence/
# geometry-vram-calibration-20261030.json, octree 512, 20000 chunks): the
# allocator reserved at most 7.94 GiB resident and 5.18 GiB released in either
# mode, and released runs were bit-identical. About 2.5 GiB above the peak
# covers the CUDA context and other inputs.
$requiredFreeVramMiB = if ($MinimumFreeVramMiB -gt 0) {
    $MinimumFreeVramMiB
} elseif ($releaseStages) {
    8192
} else {
    10240
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Required versioned Hunyuan3D runner is missing: $runner"
}
$actualRunnerHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash
if ($actualRunnerHash -ne $expectedRunnerHash) {
    throw "Hunyuan runner changed: expected $expectedRunnerHash, found $actualRunnerHash"
}

$gpuState = & (Join-Path $PSScriptRoot 'assert_gpu_available.ps1') -MinimumFreeVramMiB $requiredFreeVramMiB -ComfyUrl $ComfyUrl
$freeMiB = $gpuState.free_mib
$utilization = $gpuState.utilization
$computeApps = $gpuState.compute_owners
$comfyProcessCount = $gpuState.comfy_process_count
$queueRunning = $gpuState.queue_running
$queuePending = $gpuState.queue_pending

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
    required_free_vram_mib = $requiredFreeVramMiB
    release_stages = $releaseStages
    volume_decoding = $volumeDecoding
    gpu_utilization_percent = $utilization
    gpu_compute_owners = $computeApps
    comfy_process_count = $comfyProcessCount
    comfy_queue_running = $queueRunning
    comfy_queue_pending = $queuePending
    retry = $false
}
Write-Utf8NoBom -Path $attemptReport -Text ($attempt | ConvertTo-Json -Depth 8)
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
    # The runner and its dependencies write ordinary progress to stderr. If a
    # caller redirects this launcher's output (2>&1, *>), Stop would turn the
    # first such line into a terminating error while the child kept running on
    # the GPU. Relax only around the call; the exit code is the verdict.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    # The runner rechecks the same floor after CUDA initialises.
    $viewArguments += @('--min-free-gib', ([double]$requiredFreeVramMiB / 1024).ToString([Globalization.CultureInfo]::InvariantCulture))
    if ($releaseStages) { $viewArguments += '--release-stages' }
    $viewArguments += @('--volume-decoding', $volumeDecoding)
    try {
        & $hyPython $runner @viewArguments `
            --output $candidate `
            --report $generationReport `
            --prepared-dir $preparedDirectory `
            --steps ([int]$parameters.steps) `
            --octree-resolution ([int]$parameters.octree_resolution) `
            --chunks ([int]$parameters.chunks) `
            --seed ([int]$parameters.seed)
        $runnerExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
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
    Write-Utf8NoBom -Path $candidateReceipt -Text ($receipt | ConvertTo-Json -Depth 10)
    $attempt.status = 'succeeded'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.candidate_sha256 = $receipt.candidate_sha256
    $attempt.candidate_receipt = $candidateReceipt
    Write-Utf8NoBom -Path $attemptReport -Text ($attempt | ConvertTo-Json -Depth 8)
}
catch {
    $attempt.status = 'failed'
    $attempt.completed_at = [DateTimeOffset]::Now.ToString('o')
    $attempt.failure = $_.Exception.Message
    Write-Utf8NoBom -Path $attemptReport -Text ($attempt | ConvertTo-Json -Depth 8)
    throw
}

Write-Host "HY3D_GEOMETRY_CANDIDATE_OK receipt=$candidateReceipt -- the machine has spoken; the modeling gate has not."
