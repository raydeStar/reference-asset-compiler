[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $Profile,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [Parameter(Mandatory = $true)][string] $RemiRoot,
    [string] $Blender = $env:RAC_BLENDER
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) |
        Select-Object -Last 1
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
$driver = Join-Path $PSScriptRoot 'blender\reduce_semantic_instant_meshes.py'

Write-Host 'SEMANTIC_INSTANT_MESHES_BEGIN -- four regions, one evidence gate.'
$runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
    '--python' $driver '--' $source $profilePath $blend $glb $report $remiPath `
    $native[0].FullName 2>&1 | Tee-Object -FilePath $log)
$exitCode = $LASTEXITCODE
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
        $failure | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $report -Encoding utf8
    }
    throw "Semantic Instant Meshes attempt failed or was rejected. Evidence: $report. No retry was attempted."
}
Write-Host "RAC_SEMANTIC_INSTANT_MESHES_OK report=$report"
