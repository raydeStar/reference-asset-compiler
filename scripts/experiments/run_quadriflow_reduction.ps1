[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetQuads = 9000,
    [double] $MaximumP99M = 0.005,
    [double] $MaximumMaxM = 0.020,
    [string] $CompilerPython,
    [string] $Blender = $env:RAC_BLENDER
)
# Retained experiment: lives under scripts/experiments; shared helpers stay in scripts/.
$scriptsRoot = Split-Path -Parent $PSScriptRoot

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
$repoRoot = Split-Path -Parent $scriptsRoot
$compilerPython = & (Join-Path $scriptsRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $scriptsRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
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
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $runOutput = @(& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
        $inputPath $candidate $review $report '--triangle-budget' $TriangleBudget `
        '--target-quads' $TargetQuads '--maximum-p99-m' $MaximumP99M `
        '--maximum-max-m' $MaximumMaxM 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log)
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
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
        Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 8)
    }
    throw "Direct QuadriFlow attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_QUADRIFLOW_CANDIDATE_OK report=$report -- mechanics passed; the fixed views retain veto power."
