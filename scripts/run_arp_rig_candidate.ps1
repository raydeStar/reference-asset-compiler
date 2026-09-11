[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputMesh,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory,
    [Parameter(Mandatory = $true)] [string] $HandLandmarks,
    [string] $MarkerProfile,
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
if (-not $MarkerProfile) {
    $MarkerProfile = Join-Path $repoRoot 'profiles\rigging\arp-humanoid-a-pose.json'
}
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}

$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$profilePath = (Resolve-Path -LiteralPath $MarkerProfile).Path
$handPath = (Resolve-Path -LiteralPath $HandLandmarks).Path
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputPath) {
    $existing = @(Get-ChildItem -LiteralPath $outputPath -Force)
    if ($existing.Count -gt 0) {
        throw "Refusing to overwrite non-empty rig candidate directory: $outputPath"
    }
}
else {
    New-Item -ItemType Directory -Path $outputPath | Out-Null
}

$candidate = Join-Path $outputPath 'arp-rig-candidate.blend'
$report = Join-Path $outputPath 'rig-candidate.json'
$log = Join-Path $outputPath 'rig-candidate.log'
$driver = Join-Path $repoRoot 'scripts\blender\rig_humanoid_arp.py'

Write-Host 'RIG_STAGE_BEGIN name=arp-existing-mesh-candidate -- the bones have received a written invitation.'
# Blender writes ordinary warnings to stderr. Under $ErrorActionPreference =
# 'Stop', the 2>&1 merge below would turn the first such line into a
# terminating error and kill the wrapper mid-run, with no receipt. Relax only
# around the call; the exit code decides.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $runOutput = @(& $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' `
        '--python' $driver '--' $inputPath $candidate $report $profilePath $handPath 2>&1 | `
        ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log)
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($exitCode -ne 0) {
    $failure = [ordered]@{
        schema = 'reference-asset-compiler.arp-rig-candidate.v1'
        status = 'failed'
        retry_policy = 'manual_after_diagnosis_only'
        input = [ordered]@{
            path = $inputPath
            sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        profile = [ordered]@{
            path = $profilePath
            sha256 = (Get-FileHash -LiteralPath $profilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        hand_landmarks = [ordered]@{
            path = $handPath
            sha256 = (Get-FileHash -LiteralPath $handPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        failure = [ordered]@{
            exit_code = $exitCode
            stage = 'arp_existing_mesh_candidate'
            output_tail = @($runOutput | Select-Object -Last 40 | ForEach-Object { $_.ToString() })
        }
        log = $log
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    Write-Utf8NoBom -Path $report -Text ($failure | ConvertTo-Json -Depth 6)
    throw "Auto-Rig Pro candidate failed with exit code $exitCode. Evidence was retained at $report. No retry was attempted."
}
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or
    -not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'Auto-Rig Pro returned success without the required candidate and report.'
}
Write-Host "RAC_ARP_RIG_CANDIDATE_OK report=$report -- the rig may now face deformation review."
