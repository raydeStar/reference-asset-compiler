<#
.SYNOPSIS
  Rig a prepared humanoid mesh for a browser studio, and hand back the evidence.

.DESCRIPTION
  The consumer-facing form of the humanoid rig stage, run as `rac run-stage rig`.
  It composes routes that already exist rather than inventing one:

    1. run_rig_candidate.ps1 on the portable landmark route against the
       ue5_manny_browser profile: derive landmarks, build the UE5 Manny
       skeleton, bind with heat weights, gate the rig, run the five-pose
       deformation suite. Any gate failure stops here.
    2. export_browser_payload.py on the rigged .blend: a self-contained, +Y up,
       metric GLB carrying the skin.
    3. The evidence: the deformation renders and landmark overlays copied into
       evidence\ with a views.json in the same shape review-views writes, each
       file bound to its SHA-256.

  The receipt is a candidate, never an approval: production_grade is false,
  landmarks stay derived_pending_overlay_review, and a person has to look at
  the pose suite before anything calls this rig good.

.PARAMETER OutputDirectory
  A new attempt directory. It is refused if it exists and is not empty, for the
  same reason every attempt here is kept rather than replaced.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $InputMesh,
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $Blender = $env:RAC_BLENDER,
    [string] $CompilerPython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Fail([string] $Reason) {
    # The compiler's run-stage reads the reason after "FAILED:" and gives it to
    # whoever asked, instead of "the stage exited with code 1".
    Write-Output "[RIG STAGE] FAILED: $Reason"
    exit 1
}

function Get-Sha256([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$inputPath = (Resolve-Path -LiteralPath $InputMesh).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if ((Test-Path -LiteralPath $outputPath) -and @(Get-ChildItem -LiteralPath $outputPath -Force).Count -gt 0) {
    Fail "The attempt directory already holds an attempt: $outputPath"
}
# Blender's Python on Windows cannot write past MAX_PATH, and the deepest
# file this route writes sits well below the attempt directory. Refuse up front
# with the reason, rather than let a landmark write fail inside Blender.
$deepest = Join-Path $outputPath 'candidate\landmarks\overlay-three-quarter.png'
if ($deepest.Length -ge 250) {
    Fail "The attempt directory is too deeply nested for Blender on Windows ($($deepest.Length) characters to its deepest file; the limit is 260). Use a shorter output location."
}
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
if (-not $Blender) { Fail 'Blender could not be resolved; set RAC_BLENDER or pass -Blender.' }
$blenderPath = (Resolve-Path -LiteralPath $Blender).Path
$profileFile = Join-Path $repoRoot 'profiles\skeletons\ue5_manny_browser.json'
$candidateDir = Join-Path $outputPath 'candidate'
$evidenceDir = Join-Path $outputPath 'evidence'
$payloadPath = Join-Path $outputPath 'rigged.glb'
$payloadReport = Join-Path $outputPath 'browser-payload.json'
$reportPath = Join-Path $outputPath 'rig-stage-report.json'

# --- 1. Rig and gate --------------------------------------------------------
$candidateArgs = @{
    InputMesh = $inputPath; OutputDirectory = $candidateDir; Profile = 'ue5_manny'
    ProfileFile = $profileFile; Backbone = 'landmark'; Blender = $blenderPath
}
if ($CompilerPython) { $candidateArgs.CompilerPython = $CompilerPython }
try { & (Join-Path $PSScriptRoot 'run_rig_candidate.ps1') @candidateArgs | ForEach-Object { Write-Output $_ } }
catch { Fail ("The humanoid could not be rigged: " + $_.Exception.Message) }

$stem = [System.IO.Path]::GetFileNameWithoutExtension($inputPath) -replace '_production$', ''
$riggedBlend = Join-Path $candidateDir "${stem}_rigged.blend"
foreach ($required in @($riggedBlend, (Join-Path $candidateDir 'gate-rig.json'), (Join-Path $candidateDir 'deform-report.json'), (Join-Path $candidateDir 'rig-candidate.json'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { Fail "The rig route finished without writing $required" }
}
$gate = Get-Content -LiteralPath (Join-Path $candidateDir 'gate-rig.json') -Raw | ConvertFrom-Json
$deform = Get-Content -LiteralPath (Join-Path $candidateDir 'deform-report.json') -Raw | ConvertFrom-Json
$candidate = Get-Content -LiteralPath (Join-Path $candidateDir 'rig-candidate.json') -Raw | ConvertFrom-Json
$landmarkFile = Join-Path $candidateDir 'landmarks\humanoid-landmarks.json'
$landmarkNotes = @()
$landmarkReview = 'derived_pending_overlay_review'
if (Test-Path -LiteralPath $landmarkFile -PathType Leaf) {
    $landmarkData = Get-Content -LiteralPath $landmarkFile -Raw | ConvertFrom-Json
    $landmarkNotes = @($landmarkData.notes)
    if ($landmarkData.review_status) { $landmarkReview = [string]$landmarkData.review_status }
}
if (-not [bool]$gate.ok) { Fail ("The rig gate refused the candidate: " + (@($gate.failures) -join '; ')) }
if (-not [bool]$deform.ok) { Fail ("The deformation suite refused the candidate: " + (@($deform.failures) -join '; ')) }
if (-not [bool]$candidate.geometry_unchanged) { Fail 'Binding changed the mesh geometry; a rig must not move the vertices it binds.' }
# Bones the binder gave no vertices to. Usually fingers on a mitten-like hand;
# reported, never hidden, because a clip that curls them will show nothing.
$unweighted = @($candidate.bind.vertices_per_bone.PSObject.Properties | Where-Object { [int]$_.Value -eq 0 } | ForEach-Object { $_.Name })

# --- 2. Browser payload -----------------------------------------------------
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $exportOutput = & $blenderPath '--background' '--factory-startup' '--python-exit-code' '1' '--python' (Join-Path $repoRoot 'scripts\blender\export_browser_payload.py') '--' $riggedBlend $payloadPath $payloadReport 2>&1
    $exportCode = $LASTEXITCODE
} finally { $ErrorActionPreference = $previous }
if ($exportCode -ne 0 -or -not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) {
    $exportOutput | Select-Object -Last 10 | ForEach-Object { Write-Output "  $_" }
    Fail "The rigged model could not be exported for the browser (Blender exit $exportCode)."
}
$payload = Get-Content -LiteralPath $payloadReport -Raw | ConvertFrom-Json
if ([int]$payload.exported.armatures -ne 1) { Fail "The exported model carries $($payload.exported.armatures) armatures; exactly one was expected." }

# --- 3. Evidence ------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
$views = New-Object System.Collections.Generic.List[object]
foreach ($image in @(Get-ChildItem -LiteralPath (Join-Path $candidateDir 'deform') -Filter 'deform-*.png' | Sort-Object Name)) {
    # deform-<pose>-<front|side>.png
    if ($image.BaseName -notmatch '^deform-(?<pose>.+)-(?<view>front|side)$') { continue }
    Copy-Item -LiteralPath $image.FullName -Destination (Join-Path $evidenceDir $image.Name)
    $views.Add([ordered]@{ view = $Matches.view; pass = $Matches.pose; file = $image.Name; sha256 = Get-Sha256 (Join-Path $evidenceDir $image.Name) })
}
foreach ($overlay in @(Get-ChildItem -LiteralPath (Join-Path $candidateDir 'landmarks') -Filter 'overlay-*.png' -ErrorAction SilentlyContinue | Sort-Object Name)) {
    $name = "landmarks-$($overlay.Name)"
    Copy-Item -LiteralPath $overlay.FullName -Destination (Join-Path $evidenceDir $name)
    $views.Add([ordered]@{ view = ($overlay.BaseName -replace '^overlay-', ''); pass = 'landmarks'; file = $name; sha256 = Get-Sha256 (Join-Path $evidenceDir $name) })
}
if (@($views | Where-Object { $_.pass -ne 'landmarks' }).Count -eq 0) { Fail 'The deformation suite wrote no pose renders to review.' }
$sourceSha = Get-Sha256 $inputPath
$viewsManifest = [ordered]@{
    schema = 'reference-asset-compiler.rig-evidence.v1'
    source_sha256 = $sourceSha
    payload_sha256 = Get-Sha256 $payloadPath
    views = $views
}
[System.IO.File]::WriteAllText((Join-Path $evidenceDir 'views.json'), ($viewsManifest | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $false))

$poses = @($deform.poses.PSObject.Properties | ForEach-Object {
    [ordered]@{ name = $_.Name; vertices_moved = $_.Value.vertices_moved; max_displacement_m = $_.Value.max_displacement_m; side_bias = $_.Value.side_bias; bbox_volume_ratio = $_.Value.bbox_volume_ratio }
})
$receipt = [ordered]@{
    schema = 'reference-asset-compiler.rig-candidate.v1'
    source = $inputPath
    source_sha256 = $sourceSha
    payload = $payloadPath
    payload_sha256 = Get-Sha256 $payloadPath
    payload_bytes = (Get-Item -LiteralPath $payloadPath).Length
    skeleton_profile = 'ue5_manny_browser'
    route = 'landmark'
    bones = [int]$payload.exported.bones
    triangles = [int]$payload.exported.triangles
    maximum_influences = [int]$candidate.bind.maximum_influences
    weight_coverage = [double]$candidate.bind.coverage
    geometry_unchanged = [bool]$candidate.geometry_unchanged
    gate = [ordered]@{ passed = [bool]$gate.ok; warnings = @($gate.warnings) }
    deformation = [ordered]@{ passed = [bool]$deform.ok; warnings = @($deform.warnings); poses = $poses }
    unweighted_bones = $unweighted
    landmarks = [ordered]@{ status = $landmarkReview; notes = $landmarkNotes }
    evidence_directory = $evidenceDir
    evidence_manifest = Join-Path $evidenceDir 'views.json'
    production_grade = $false
    requires_deformation_review = $true
    next = 'A person reviews the pose suite and landmark overlays before this rig is accepted anywhere.'
}
[System.IO.File]::WriteAllText($reportPath, ($receipt | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $false))
Write-Output "RAC_RIG_STAGE_OK bones=$($receipt.bones) triangles=$($receipt.triangles) poses=$($poses.Count) output=$payloadPath"
