[CmdletBinding()]
param(
    # One mesh: -Mesh, -Reference and -OutputObj. Many in one painter process,
    # its models loaded once: -Jobs, a JSON list of {mesh, reference,
    # output_obj, bake_size} (studio runner only). Each job gets its own receipt.
    [string] $Mesh,
    [string] $Reference,
    [string] $OutputObj,
    [string] $Jobs,
    [ValidateRange(6, 12)][int] $Views = 6,
    [ValidateSet(512, 768)][int] $Resolution = 512,
    # 'legacy' is the hash-pinned studio-tree copy of run_hy3d21_pbr.py, which
    # writes a 2048 JPEG atlas. 'studio' is this repository's
    # run_hy3d21_studio.py, hash-pinned likewise, which keeps the 4096 atlas
    # the pipeline already computes and writes every map as PNG.
    [ValidateSet('legacy', 'studio')][string] $RunnerKind = 'legacy',
    [ValidateSet(2048, 4096, 8192)][int] $Atlas = 2048,
    # Studio only: shrink every view to this many pixels before it is baked,
    # about one pixel a texel, so a texel's sample is an average rather than a
    # random pore of a far finer view. 0 keeps upstream's sizes.
    [ValidateRange(0, 4096)][int] $BakeSize = 0,
    # Studio only: fill the texels no view saw with OpenCV only within this
    # many texels of the mesh, the rest of the sheet from the nearest paint.
    # 0 fills the whole sheet as upstream does. A section uses a few percent
    # of its sheet, and the whole-sheet fill was 140 s of its 210 s at 8192.
    [ValidateRange(0, 256)][int] $InpaintReach = 0,
    [switch] $SmoothConditioningNormals,
    # The studio runner moves one-shot helpers off the GPU before sampling, runs
    # the UNet feed-forward and the VAE decode one image at a time, and moves
    # the diffusion weights off the GPU before upscaling and baking. Measured
    # on 2026-10-30 at 12 views x 768: 35.5 GiB reserved (spilling into shared
    # memory) -> 9.6 GiB under a hard 10 GiB cap, and about 25% faster. Not byte-identical (0.04% of atlas
    # pixels move by more than 16/255, at UV island edges); the user judged the
    # four-view renders identical and made it the default. This switch restores
    # the resident behaviour, e.g. to reproduce an attempt painted before it.
    [switch] $KeepStagesResident,
    # Studio only: write the OBJ and its PNG maps, not the GLB (the same maps
    # packed by Blender's exporter). The gate then asks for the maps.
    [switch] $MapsOnly,
    [switch] $NoUpscale,
    [string] $DiagnosticsDir,
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { throw 'Set RAC_LEGACY_ROOT to the studio tree that holds the Hunyuan3D-Paint runner, upstream checkout and models.' }),
    # 0 selects the measured floor: 21504 resident, 10752 released (a 12 GB
    # card; 12 views x 768 peaked at 9.6 GiB under a hard 10 GiB cap, and an
    # 8192 sheet at 9.1 GiB once the bake stopped holding every view's sheet).
    [int] $MinimumFreeVramMiB = 0,
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
$expectedStudioRunnerHash = '3EB301767870270BDEA38B2419CF3E53EADB2C0E7630F902D25A4B582ABD6C32'
$python = Join-Path $LegacyRoot '.venv-hy3d21\Scripts\python.exe'
$runner = Join-Path $LegacyRoot 'scripts\run_hy3d21_pbr.py'
if ($RunnerKind -eq 'studio') {
    $runner = Join-Path (Split-Path -Parent $PSScriptRoot) 'workflows\texture\hunyuan3d21\run_hy3d21_studio.py'
    $expectedRunnerHash = $expectedStudioRunnerHash
    $normalHelper = Join-Path (Split-Path -Parent $runner) 'seam_normals.py'
    if ((Get-FileHash -LiteralPath $normalHelper -Algorithm SHA256).Hash -ne 'D6F166BB122DC8F6E0EC47B42644A53C2600FE7AFD3E3F049DFA9AC3BB6AAFDD') {
        throw 'Studio normal helper changed; verify it and update its pinned hash before painting.'
    }
    $fillHelper = Join-Path (Split-Path -Parent $runner) 'sheet_fill.py'
    if ((Get-FileHash -LiteralPath $fillHelper -Algorithm SHA256).Hash -ne '0D95040DCD66D2102070FBB79C5E31051918D0B81AF8D4580FBAE530196E3B54') {
        throw 'Studio sheet-fill helper changed; verify it and update its pinned hash before painting.'
    }
} elseif ($Atlas -ne 2048) {
    throw "The legacy runner writes a 2048 atlas only; ask for -RunnerKind studio to keep $Atlas"
}
if ($SmoothConditioningNormals -and $RunnerKind -ne 'studio') {
    throw 'SmoothConditioningNormals requires RunnerKind studio.'
}
if ($InpaintReach -gt 0 -and $RunnerKind -ne 'studio') {
    throw 'InpaintReach requires RunnerKind studio.'
}
if ($NoUpscale -and $RunnerKind -ne 'studio') {
    throw 'NoUpscale requires RunnerKind studio.'
}
if ($MapsOnly -and $RunnerKind -ne 'studio') {
    throw 'MapsOnly requires RunnerKind studio.'
}
if ($Jobs) {
    if ($RunnerKind -ne 'studio') {
        throw 'Jobs requires RunnerKind studio.'
    }
    if ($Mesh -or $Reference -or $OutputObj) {
        throw 'Give -Mesh, -Reference and -OutputObj, or -Jobs, not both.'
    }
} elseif (-not ($Mesh -and $Reference -and $OutputObj)) {
    throw 'Give -Mesh, -Reference and -OutputObj, or -Jobs.'
}
# The legacy runner keeps every stage resident and its own 21 GiB check.
$releaseStages = $RunnerKind -eq 'studio' -and -not $KeepStagesResident
if ($MinimumFreeVramMiB -le 0) {
    $MinimumFreeVramMiB = if ($releaseStages) { 10752 } else { 21504 }
}
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

function New-PaintJob {
    param([string] $MeshIn, [string] $ReferenceIn, [string] $OutputIn, [int] $Bake)
    if (-not $MeshIn -or -not $ReferenceIn -or -not $OutputIn) {
        throw 'A paint job needs a mesh, a reference and an output .obj'
    }
    if ($Bake -lt 0 -or $Bake -gt 4096) {
        throw "A bake size runs from 0 to 4096: $Bake"
    }
    $outputPath = [System.IO.Path]::GetFullPath($OutputIn)
    if ([System.IO.Path]::GetExtension($outputPath).ToLowerInvariant() -ne '.obj') {
        throw 'Hunyuan3D-Paint output must use an .obj path'
    }
    foreach ($extension in @('.obj', '.glb', '.validation.json', '.execution.json', '.failure.json')) {
        $retained = [System.IO.Path]::ChangeExtension($outputPath, $extension)
        if (Test-Path -LiteralPath $retained) {
            throw "Paint attempt already has retained evidence; choose a new attempt: $retained"
        }
    }
    return [ordered]@{
        mesh = (Resolve-Path -LiteralPath $MeshIn).Path
        reference = (Resolve-Path -LiteralPath $ReferenceIn).Path
        output_obj = $outputPath
        bake_size = $Bake
    }
}

$paintJobs = New-Object System.Collections.ArrayList
$jobsPath = $null
$resolvedJobsPath = $null
if ($Jobs) {
    $jobsPath = (Resolve-Path -LiteralPath $Jobs).Path
    $entries = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($jobsPath))
    $outputs = @{}
    foreach ($entry in $entries) {
        $bake = 0
        if ($null -ne $entry.bake_size) { $bake = [int]$entry.bake_size }
        $job = New-PaintJob -MeshIn $entry.mesh -ReferenceIn $entry.reference -OutputIn $entry.output_obj -Bake $bake
        if ($outputs.ContainsKey($job.output_obj.ToLowerInvariant())) {
            throw "Two jobs write the same output: $($job.output_obj)"
        }
        $outputs[$job.output_obj.ToLowerInvariant()] = $true
        [void]$paintJobs.Add($job)
    }
    if ($paintJobs.Count -eq 0) {
        throw "The jobs file lists nothing to paint: $jobsPath"
    }
    # The runner is handed the jobs as resolved here, beside the caller's list.
    $resolvedJobsPath = Join-Path (Split-Path -Parent $jobsPath) (([System.IO.Path]::GetFileNameWithoutExtension($jobsPath)) + '.resolved.json')
    if (Test-Path -LiteralPath $resolvedJobsPath) {
        throw "Paint batch already has retained evidence; choose a new attempt: $resolvedJobsPath"
    }
} else {
    [void]$paintJobs.Add((New-PaintJob -MeshIn $Mesh -ReferenceIn $Reference -OutputIn $OutputObj -Bake $BakeSize))
}
foreach ($job in $paintJobs) {
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($job.output_obj)) | Out-Null
}

$gpuState = & (Join-Path $PSScriptRoot 'assert_gpu_available.ps1') -MinimumFreeVramMiB $MinimumFreeVramMiB -ComfyUrl $ComfyUrl
$freeMiB = $gpuState.free_mib
$utilization = $gpuState.utilization
$computeApps = $gpuState.compute_owners
$comfyProcessCount = $gpuState.comfy_process_count
$queueRunning = $gpuState.queue_running
$queuePending = $gpuState.queue_pending

Write-Host "HY3D21_LAUNCH_READY free_mib=$freeMiB utilization=$utilization% runner_sha256=$actualRunnerHash jobs=$($paintJobs.Count)"
$startedUtc = [DateTime]::UtcNow.ToString('o')
$runnerArgs = @($runner)
if ($Jobs) {
    Write-Utf8NoBom -Path $resolvedJobsPath -Text (ConvertTo-Json -InputObject @($paintJobs) -Depth 4)
    $runnerArgs += @('--jobs', $resolvedJobsPath)
} else {
    $runnerArgs += @($paintJobs[0].mesh, $paintJobs[0].reference, $paintJobs[0].output_obj)
}
$runnerArgs += @('--views', $Views, '--resolution', $Resolution)
if ($RunnerKind -eq 'studio') {
    $runnerArgs += @('--atlas', $Atlas, '--legacy-root', $LegacyRoot)
    if ($SmoothConditioningNormals) { $runnerArgs += '--smooth-conditioning-normals' }
    if ($releaseStages) { $runnerArgs += '--release-stages' }
    if (-not $Jobs -and $BakeSize -gt 0) { $runnerArgs += @('--bake-size', $BakeSize) }
    if ($InpaintReach -gt 0) { $runnerArgs += @('--inpaint-reach', $InpaintReach) }
    if ($MapsOnly) { $runnerArgs += '--maps-only' }
    if ($NoUpscale) { $runnerArgs += '--no-upscale' }
    # The runner rechecks the same floor after CUDA initialises.
    $runnerArgs += @('--min-free-gib', ([double]$MinimumFreeVramMiB / 1024).ToString([Globalization.CultureInfo]::InvariantCulture))
}
if ($DiagnosticsDir) {
    $diagnosticsPath = [System.IO.Path]::GetFullPath($DiagnosticsDir)
    if (Test-Path -LiteralPath $diagnosticsPath) {
        throw "Diagnostics directory already exists; refusing to overwrite evidence: $diagnosticsPath"
    }
    $runnerArgs += @('--diagnostics-dir', $diagnosticsPath)
}
# Each receipt exists BEFORE the runner starts, with status 'running'. A wrapper
# killed between here and the first painted view still leaves evidence that an
# attempt was made, and the operator driver then refuses to relaunch into the
# same attempt directory instead of silently retrying crashed inference.
$receipts = New-Object System.Collections.ArrayList
for ($number = 0; $number -lt $paintJobs.Count; $number++) {
    $job = $paintJobs[$number]
    $batch = $null
    if ($Jobs) {
        $batch = [ordered]@{ jobs_file = $jobsPath; jobs = $paintJobs.Count; number = $number + 1 }
    }
    $execution = [ordered]@{
        schema = 'reference-asset-compiler.paint-execution.v1'
        status = 'running'
        started_utc = $startedUtc
        completed_utc = $null
        runner = $runner
        runner_sha256 = $actualRunnerHash.ToLowerInvariant()
        input_mesh = $job.mesh
        input_mesh_sha256 = (Get-FileHash -LiteralPath $job.mesh).Hash.ToLowerInvariant()
        reference = $job.reference
        reference_sha256 = (Get-FileHash -LiteralPath $job.reference).Hash.ToLowerInvariant()
        output_obj = $job.output_obj
        views = $Views
        resolution = $Resolution
        runner_kind = $RunnerKind
        atlas = $Atlas
        bake_size = $job.bake_size
        inpaint_reach = $InpaintReach
        no_upscale = [bool]$NoUpscale
        batch = $batch
        conditioning_normals = $(if ($SmoothConditioningNormals) { 'seam_independent_vertex' } else { 'face' })
        release_stages = $releaseStages
        required_free_vram_mib = $MinimumFreeVramMiB
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
    $executionPath = [System.IO.Path]::ChangeExtension($job.output_obj, '.execution.json')
    Write-Utf8NoBom -Path $executionPath -Text ($execution | ConvertTo-Json -Depth 5)
    [void]$receipts.Add($execution)
}

function Test-PaintGate {
    # The painter's own gate for one job: the reason it is refused, or $null.
    param($Job)
    $report = [System.IO.Path]::ChangeExtension($Job.output_obj, '.validation.json')
    $failure = [System.IO.Path]::ChangeExtension($Job.output_obj, '.failure.json')
    if (Test-Path -LiteralPath $failure -PathType Leaf) {
        $recorded = Get-Content -LiteralPath $failure -Raw | ConvertFrom-Json
        return "Hunyuan3D-Paint failed on this job: $($recorded.error)"
    }
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        return 'Hunyuan3D-Paint left no validation report for this job; it will not be auto-retried'
    }
    $gate = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $gate.faces_equal -or [double]$gate.geometry_delta -gt 0.000001 -or [double]$gate.uv_delta -gt 0.000001) {
        return "Hunyuan3D-Paint topology/UV gate failed: $report"
    }
    if ($MapsOnly) {
        $stem = [System.IO.Path]::ChangeExtension($Job.output_obj, $null).TrimEnd('.')
        foreach ($suffix in @('.png', '_metallic.png', '_roughness.png')) {
            if (-not (Test-Path -LiteralPath ($stem + $suffix) -PathType Leaf)) {
                return "Hunyuan3D-Paint validation passed but the map $($stem + $suffix) is missing"
            }
        }
    } elseif (-not (Test-Path -LiteralPath ([System.IO.Path]::ChangeExtension($Job.output_obj, '.glb')) -PathType Leaf)) {
        return 'Hunyuan3D-Paint validation passed but the expected GLB is missing'
    }
    return $null
}

$exitCode = $null
try {
    # The runner and its dependencies write ordinary progress and warnings to
    # stderr. Under $ErrorActionPreference = 'Stop', any caller that redirects
    # our output to a log (2>&1, *>) would turn the first such line into a
    # terminating error and kill the paint before it finished. Relax only
    # around the call; the exit code and the receipts below are the verdict.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python @runnerArgs
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        Write-Warning "Painter exited abnormally ($exitCode). Retaining outputs and receipts; no retry. Geometry/UV validation below is separate from process health."
    }
}
catch {
    $completed = [DateTime]::UtcNow.ToString('o')
    for ($number = 0; $number -lt $paintJobs.Count; $number++) {
        $execution = $receipts[$number]
        $execution.status = 'failed'
        $execution.completed_utc = $completed
        $execution.failure = $_.Exception.Message
        Write-Utf8NoBom -Path ([System.IO.Path]::ChangeExtension($paintJobs[$number].output_obj, '.execution.json')) -Text ($execution | ConvertTo-Json -Depth 5)
    }
    throw
}

$completed = [DateTime]::UtcNow.ToString('o')
$refused = New-Object System.Collections.ArrayList
for ($number = 0; $number -lt $paintJobs.Count; $number++) {
    $job = $paintJobs[$number]
    $execution = $receipts[$number]
    $execution.completed_utc = $completed
    $execution.exit_code = $exitCode
    $execution.clean_process_exit = ($exitCode -eq 0)
    $execution.validation_present = (Test-Path -LiteralPath ([System.IO.Path]::ChangeExtension($job.output_obj, '.validation.json')) -PathType Leaf)
    $reason = Test-PaintGate -Job $job
    if ($Jobs) {
        # In a batch the job's own gate is its verdict; the process's exit code,
        # shared by every job and faulted at teardown, is kept beside it.
        $execution.status = $(if ($null -eq $reason) { 'completed' } else { 'failed' })
    } else {
        $execution.status = $(if ($exitCode -eq 0) { 'completed' } else { 'failed' })
    }
    if ($null -ne $reason) {
        $execution.status = 'failed'
        $execution.failure = $reason
        [void]$refused.Add("job $($number + 1) ($($job.output_obj)): $reason")
    }
    Write-Utf8NoBom -Path ([System.IO.Path]::ChangeExtension($job.output_obj, '.execution.json')) -Text ($execution | ConvertTo-Json -Depth 5)
}
if ($refused.Count -gt 0) {
    if (-not $Jobs) {
        throw ($refused[0] -replace '^job 1 \([^)]*\): ', '')
    }
    throw "$($refused.Count) of $($paintJobs.Count) paint jobs failed; the rest are kept: $($refused -join '; ')"
}

$reportPaths = ($paintJobs | ForEach-Object { [System.IO.Path]::ChangeExtension($_.output_obj, '.validation.json') }) -join ', '
Write-Host "HY3D21_TEXTURE_VALIDATED exit_code=$exitCode jobs=$($paintJobs.Count) report=$reportPaths -- the paint is admitted; the mirror retains veto power."
