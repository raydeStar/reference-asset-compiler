[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetQuads = 9000,
    [double] $MaximumP99M = 0.005,
    [double] $MaximumMaxM = 0.020,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
}
$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite QuadriFlow attempt directory: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$candidate = Join-Path $outputPath 'quadriflow-candidate.blend'
$review = Join-Path $outputPath 'quadriflow-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_quadriflow.py'

Write-Host 'REDUCTION_STAGE_BEGIN backend=DirectQuadriFlow -- one clean surface, no voxelization, no decimation fallback.'
$runOutput = @(& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $candidate $review $report '--triangle-budget' $TriangleBudget `
    '--target-quads' $TargetQuads '--maximum-p99-m' $MaximumP99M `
    '--maximum-max-m' $MaximumMaxM 2>&1 | Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.production-retopology-candidate.v1'
            status = 'failed'
            retry_policy = 'manual_after_diagnosis_only'
            source = [ordered]@{
                path = $inputPath
                sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'Blender QuadriFlow direct'
            settings = [ordered]@{
                triangle_budget = $TriangleBudget
                target_quads = $TargetQuads
                maximum_p99_m = $MaximumP99M
                maximum_max_m = $MaximumMaxM
            }
            failure = [ordered]@{
                exit_code = $exitCode
                output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
            }
        }
        $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $report -Encoding utf8
    }
    throw "Direct QuadriFlow attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_QUADRIFLOW_CANDIDATE_OK report=$report -- mechanics passed; the fixed views retain veto power."
