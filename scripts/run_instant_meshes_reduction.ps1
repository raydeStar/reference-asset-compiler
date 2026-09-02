[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [Parameter(Mandatory = $true)][string] $RemiRoot,
    [int] $TargetFaces = 9000,
    [int] $TriangleBudget = 20000,
    [double] $CreaseAngleDegrees = 35.0,
    [double] $MaximumP99M = 0.005,
    [double] $MaximumMaxM = 0.020,
    [double] $TimeoutSeconds = 300.0,
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
$remiPath = (Resolve-Path -LiteralPath $RemiRoot).Path
$native = @(Get-ChildItem -LiteralPath (Join-Path $remiPath 'remi\instant_meshes\_native') `
        -Filter '_remi_instant_meshes.cp313-win_amd64.pyd' -File)
if ($native.Count -ne 1) {
    throw "Expected exactly one verified Windows Remi native module under: $remiPath"
}
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    throw "Refusing to overwrite Instant Meshes attempt: $outputPath"
}
[System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
$candidate = Join-Path $outputPath 'instant-meshes-candidate.blend'
$review = Join-Path $outputPath 'instant-meshes-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_instant_meshes.py'

Write-Host 'INSTANT_MESHES_REDUCTION_BEGIN -- the field solver now answers to evidence.'
$runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
    '--python' $driver '--' $inputPath $candidate $review $report $remiPath $native[0].FullName `
    '--target-faces' $TargetFaces '--triangle-budget' $TriangleBudget `
    '--crease-angle-degrees' $CreaseAngleDegrees '--maximum-p99-m' $MaximumP99M `
    '--maximum-max-m' $MaximumMaxM '--timeout-seconds' $TimeoutSeconds 2>&1 |
    Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    if (-not (Test-Path -LiteralPath $report)) {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.production-retopology-candidate.v1'
            status = 'failed'
            retry_policy = 'manual_after_diagnosis_only'
            source = [ordered]@{
                path = $inputPath
                sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'Remi Instant Meshes field solver'
            native_module = [ordered]@{
                path = $native[0].FullName
                sha256 = (Get-FileHash -LiteralPath $native[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            failure = [ordered]@{
                exit_code = $exitCode
                output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
            }
            production_grade = $false
        }
        $failure | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $report -Encoding utf8
    }
    throw "Instant Meshes attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_INSTANT_MESHES_CANDIDATE_OK report=$report"
