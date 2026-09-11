[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetQuads = 9000,
    [int] $VoxelResolution = 420,
    [int] $SmoothIterations = 5,
    [double] $SmoothLambda = 0.28,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
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
$repoRoot = Split-Path -Parent $PSScriptRoot
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    if (@(Get-ChildItem -LiteralPath $outputPath -Force).Count -gt 0) {
        throw "Refusing to overwrite non-empty reduction directory: $outputPath"
    }
}
else {
    New-Item -ItemType Directory -Path $outputPath | Out-Null
}
$candidate = Join-Path $outputPath 'voxel-quadriflow-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_voxel_quadriflow.py'

Write-Host 'REDUCTION_STAGE_BEGIN backend=VoxelQuadriFlow -- first make a coherent surface, then ask it to count.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' '--python' $driver '--' `
        $inputPath $candidate $report '--triangle-budget' $TriangleBudget '--target-quads' $TargetQuads `
        '--voxel-resolution' $VoxelResolution '--smooth-iterations' $SmoothIterations `
        '--smooth-lambda' $SmoothLambda 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log)
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    if (Test-Path -LiteralPath $report -PathType Leaf) {
        # The driver's own report parses to a PSCustomObject (5.1's ConvertFrom-Json
        # cannot emit a hashtable); Add-Member -Force sets or replaces each field.
        $failure = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
        $failure | Add-Member -NotePropertyName status -NotePropertyValue 'failed' -Force
        $failure | Add-Member -NotePropertyName retry_policy -NotePropertyValue 'manual_after_diagnosis_only' -Force
        $failure | Add-Member -NotePropertyName failure -NotePropertyValue ([ordered]@{
            exit_code = $exitCode
            output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
        }) -Force
        $failure | Add-Member -NotePropertyName log -NotePropertyValue $log -Force
        $failure | Add-Member -NotePropertyName completed_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
        Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 8)
    }
    else {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.reduction-candidate.v1'
            status = 'failed'
            retry_policy = 'manual_after_diagnosis_only'
            source = [ordered]@{
                path = $inputPath
                sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'Blender voxel remesh then QuadriFlow'
            settings = [ordered]@{
                triangle_budget = $TriangleBudget
                target_quads = $TargetQuads
                voxel_resolution = $VoxelResolution
                smooth_iterations = $SmoothIterations
                smooth_lambda = $SmoothLambda
                decimation_fallback = $false
            }
            failure = [ordered]@{
                exit_code = $exitCode
                output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
            }
            log = $log
            completed_utc = [DateTime]::UtcNow.ToString('o')
        }
        Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 6)
    }
    throw "Voxel/QuadriFlow reduction failed with exit code $exitCode. Evidence: $report. No retry was attempted."
}
foreach ($required in @($candidate, $report)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Voxel/QuadriFlow reduction exited 0 without writing $required"
    }
}
Write-Host "RAC_VOXEL_QUADRIFLOW_CANDIDATE_OK report=$report -- mechanics passed; appearance remains on trial."
