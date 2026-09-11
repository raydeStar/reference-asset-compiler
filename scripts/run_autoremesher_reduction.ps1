[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [int] $TriangleBudget = 20000,
    [int] $TargetQuads = 9000,
    [double] $Adaptivity = 0.5,
    [int] $IslandDetail = 10,
    [switch] $WeldShells,
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
$candidate = Join-Path $outputPath 'autoremesher-candidate.glb'
$report = Join-Path $outputPath 'reduction-report.json'
$log = Join-Path $outputPath 'reduction.log'
$driver = Join-Path $repoRoot 'scripts\blender\reduce_autoremesher.py'

Write-Host 'REDUCTION_STAGE_BEGIN backend=AutoRemesher -- the dense mesh enters a strictly supervised diet.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $runOutput = @(& $blenderPath '--background' '--python-exit-code' '1' '--python' $driver '--' `
        $inputPath $candidate $report '--triangle-budget' $TriangleBudget '--target-quads' $TargetQuads `
        '--adaptivity' $Adaptivity '--island-detail' $IslandDetail `
        $(if ($WeldShells) { '--weld-shells' }) `
        2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log)
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
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
        Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 6)
    }
    throw "AutoRemesher reduction failed with exit code $exitCode. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_REDUCTION_CANDIDATE_OK report=$report -- topology passed; appearance remains on trial."
