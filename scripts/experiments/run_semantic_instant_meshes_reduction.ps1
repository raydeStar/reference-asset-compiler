[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Profile,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [Parameter(Mandatory = $true)][string] $RemiRoot,
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
$compilerPython = & (Join-Path $scriptsRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $scriptsRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}
$source = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = (Resolve-Path -LiteralPath $Profile).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$remiPath = (Resolve-Path -LiteralPath $RemiRoot).Path
$native = @(Get-ChildItem -LiteralPath (Join-Path $remiPath 'remi\instant_meshes\_native') `
        -Filter '_remi_instant_meshes.cp313-win_amd64.pyd' -File)
if ($native.Count -ne 1) {
    throw "Expected exactly one Windows Remi native module under: $remiPath"
}
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) {
    throw "Refusing to overwrite semantic retopology attempt: $output"
}
[System.IO.Directory]::CreateDirectory($output) | Out-Null
$blend = Join-Path $output 'semantic-instant-meshes-candidate.blend'
$glb = Join-Path $output 'semantic-instant-meshes-candidate.glb'
$report = Join-Path $output 'reduction-report.json'
$log = Join-Path $output 'reduction.log'
$driver = Join-Path $scriptsRoot 'blender\reduce_semantic_instant_meshes.py'

Write-Host 'SEMANTIC_INSTANT_MESHES_BEGIN -- four regions, one evidence gate.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
        '--python' $driver '--' $source $profilePath $blend $glb $report $remiPath `
        $native[0].FullName 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log)
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    if (-not (Test-Path -LiteralPath $report)) {
        $failure = [ordered]@{
            schema = 'reference-asset-compiler.semantic-production-retopology-candidate.v1'
            status = 'failed'
            retry_policy = 'manual_after_diagnosis_only'
            purpose = 'Downstream region-aware retopology of approved AI geometry; not image reconstruction.'
            source = [ordered]@{
                path = $source
                sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            profile = [ordered]@{
                path = $profilePath
                sha256 = (Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            backend = 'Remi Instant Meshes field solver'
            native_module = [ordered]@{
                path = $native[0].FullName
                sha256 = (Get-FileHash -LiteralPath $native[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            failure = [ordered]@{
                exit_code = $exitCode
                output_tail = @($runOutput | Select-Object -Last 50 | ForEach-Object { $_.ToString() })
            }
            production_grade = $false
        }
        Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 7)
    }
    throw "Semantic Instant Meshes attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_SEMANTIC_INSTANT_MESHES_OK report=$report"
