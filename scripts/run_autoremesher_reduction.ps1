[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetQuads = 9000,
    [double] $Adaptivity = 0.5,
    [int] $IslandDetail = 10,
    [switch] $WeldShells,
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
$candidate = Join-Path $outputPath 'autoremesher-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_autoremesher.py'

Write-Host 'REDUCTION_STAGE_BEGIN backend=AutoRemesher -- the dense mesh enters a strictly supervised diet.'
$runOutput = @(& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
    $inputPath $candidate $report '--triangle-budget' $TriangleBudget '--target-quads' $TargetQuads `
    '--adaptivity' $Adaptivity '--island-detail' $IslandDetail `
    $(if ($WeldShells) { '--weld-shells' }) `
    2>&1 | Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.reduction-candidate.v1'
            status = 'failed'
            retry_policy = 'manual_after_diagnosis_only'
            source = [ordered]@{
                path = $inputPath
                sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'AutoRemesher'
            settings = [ordered]@{ triangle_budget = $TriangleBudget; target_quads = $TargetQuads }
            failure = [ordered]@{
                exit_code = $exitCode
                output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
            }
            log = $log
            completed_utc = [DateTime]::UtcNow.ToString('o')
        }
        $failure | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $report -Encoding utf8
    }
    throw "AutoRemesher reduction failed with exit code $exitCode. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_REDUCTION_CANDIDATE_OK report=$report -- topology passed; appearance remains on trial."
