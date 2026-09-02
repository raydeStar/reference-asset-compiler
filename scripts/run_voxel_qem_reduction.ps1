[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetTriangles = 18000,
    [int] $VoxelResolution = 420,
    [int] $SmoothIterations = 5,
    [double] $SmoothLambda = 0.28,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
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
$candidateExtension = if ([System.IO.Path]::GetExtension($inputPath) -ieq '.fbx') { '.fbx' } else { '.glb' }
$candidate = Join-Path $outputPath ("voxel-qem-candidate$candidateExtension")
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_voxel_qem.py'

Write-Host 'REDUCTION_STAGE_BEGIN backend=VoxelQEM -- coherent surface first, explicit reduction second.'
$runOutput = @(& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $candidate $report '--triangle-budget' $TriangleBudget '--target-triangles' $TargetTriangles `
    '--voxel-resolution' $VoxelResolution '--smooth-iterations' $SmoothIterations `
    '--smooth-lambda' $SmoothLambda 2>&1 | Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    if (Test-Path -LiteralPath $report -PathType Leaf) {
        $failure = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json -AsHashtable
    }
    else {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.production-retopology-candidate.v1'
            source = [ordered]@{
                path = $inputPath
                sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'Blender voxel remesh then collapse QEM'
        }
    }
    $failure.status = 'failed'
    $failure.retry_policy = 'manual_after_diagnosis_only'
    $failure.failure = [ordered]@{
        exit_code = $exitCode
        output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
    }
    $failure.log = $log
    $failure.completed_utc = [DateTime]::UtcNow.ToString('o')
    $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $report -Encoding utf8
    throw "Voxel/QEM reduction failed with exit code $exitCode. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_VOXEL_QEM_CANDIDATE_OK report=$report -- mechanics passed; appearance remains on trial."
