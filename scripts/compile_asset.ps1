<#
.SYNOPSIS
  Compile one recipe into a gated, UE5-ready asset package.

.DESCRIPTION
  normalize -> gate -> package -> import manifest. Every stage reads from disk
  and writes to disk; no stage passes state in memory. A stage does not begin
  until the previous one exits 0.

  The gate runs against the EXPORTED file, not the pre-export scene, because
  the FBX round trip is exactly where scale and skinning quietly change.

.EXAMPLE
  .\scripts\compile_asset.ps1 -Recipe recipes\fox-mascot.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Recipe,
    [string] $Blender,
    [string] $CompilerPython,
    [switch] $SkipRender
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
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

# Tool paths come from scripts/rac_env.py rather than a default that is only
# right on one machine. Set RAC_BLENDER to override. The interpreter is the
# repository's own (.venv, then py -3.12/-3.11, then python), never bare
# `python`, which on a fresh machine is the Microsoft Store stub.
$compilerPython = & (Join-Path $PSScriptRoot 'resolve_python.ps1') -Python $CompilerPython
if (-not $Blender) {
    $Blender = (& $compilerPython (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0 -or -not $Blender) {
        throw 'Blender could not be resolved; set RAC_BLENDER or pass -Blender <path>.'
    }
}

if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) {
    throw "Blender not found at '$Blender'. Pass -Blender <path>."
}

$recipePath = Resolve-Path -LiteralPath $Recipe
$recipeData = Get-Content -LiteralPath $recipePath -Raw | ConvertFrom-Json
$assetId = $recipeData.asset_id
$profileId = $recipeData.skeleton_profile
if ($assetId -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') {
    throw 'Recipe asset_id must be a lowercase slug; paths do not belong on the guest list.'
}

$assetWork = Join-Path $repoRoot "work\$assetId"
$workDir = Join-Path $assetWork ('compile-attempts\' + [guid]::NewGuid().ToString('N'))
$outDir = Join-Path $repoRoot "out\$assetId"
$evidenceDir = Join-Path $workDir 'evidence'
# A published authority is never overwritten. Refuse before any Blender work
# rather than after twenty minutes of it; an empty leftover directory is fine.
if (Test-Path -LiteralPath $outDir) {
    throw "Published authority already exists: $outDir. This compiler never overwrites it; compile under a new asset id, or remove it deliberately yourself first."
}
New-Item -ItemType Directory -Force -Path $workDir, $evidenceDir | Out-Null

function Invoke-Blender {
    param([string] $Script, [string[]] $ScriptArgs, [string] $Label, [string[]] $ExpectedOutputs = @())

    Write-Host "[$assetId] $Label" -ForegroundColor Cyan
    $scriptPath = Join-Path $repoRoot "scripts\blender\$Script"
    $logDir = Join-Path $workDir 'logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stderrLog = Join-Path $logDir "$Script.stderr.log"

    # Delete what this call is about to rewrite, so a crashed stage cannot be
    # read as the previous run's success. Only per-run outputs under work\,
    # never retained evidence.
    foreach ($expected in $ExpectedOutputs) {
        if (Test-Path -LiteralPath $expected -PathType Leaf) { Remove-Item -LiteralPath $expected -Force }
    }

    # Redirect stderr to a file rather than merging with 2>&1. In Windows
    # PowerShell 5.1 a merged native stderr line becomes an ErrorRecord, and
    # under ErrorActionPreference=Stop a harmless DeprecationWarning then
    # terminates the run. Exit code is the signal; the log is the evidence.
    # ErrorActionPreference=Stop would promote that NativeCommandError into a
    # terminating one, so relax it for the duration of the call only.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # --python-exit-code 1: without it Blender exits 0 when the stage raised.
        $output = & $Blender -b --factory-startup --python-exit-code 1 --python $scriptPath -- @ScriptArgs 2>$stderrLog
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    $output | Where-Object { $_ -match '^\[(GATE|NORMALIZE|RENDER|DEFORM)' -or $_ -match '^  - ' } |
        ForEach-Object { Write-Host "  $_" }

    if ($code -ne 0) {
        Write-Host "  --- stderr ($stderrLog) ---" -ForegroundColor Yellow
        Get-Content -LiteralPath $stderrLog -ErrorAction SilentlyContinue |
            Select-Object -Last 30 | ForEach-Object { Write-Host "  $_" }
        throw "$Label failed with exit code $code"
    }
    foreach ($expected in $ExpectedOutputs) {
        if (-not (Test-Path -LiteralPath $expected -PathType Leaf)) {
            throw "$Label exited 0 without writing $expected"
        }
    }
}

# --- Stage A: resolve the skeleton profile, folding in this asset's waiver ----
$profileSrc = Join-Path $repoRoot "profiles\skeletons\$profileId.json"
if (-not (Test-Path -LiteralPath $profileSrc)) {
    throw "Unknown skeleton profile '$profileId' (expected $profileSrc)"
}
$profile = Get-Content -LiteralPath $profileSrc -Raw | ConvertFrom-Json
if ($recipeData.budget_waiver) {
    $profile.tri_budget_waiver = $recipeData.budget_waiver
}
if ($recipeData.texture_waiver) {
    $profile.texture_waiver = $recipeData.texture_waiver
}
$resolvedProfile = Join-Path $workDir 'resolved-profile.json'
# Windows PowerShell 5.1 -Encoding utf8 emits a BOM, which json.loads rejects.
[System.IO.File]::WriteAllText($resolvedProfile, ($profile | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding $false))

# --- Stage B0: stage textures under their shipped names ----------------------
# This happens before the export, not after, so the FBX can carry a relative
# reference to the exact files that ship beside it.
# work\<asset>\staged is this run's scratch copy of what gets published; the
# retained evidence lives in work\<asset>\evidence and out\. Recreating it is fine.
$stageDir = Join-Path $workDir 'staged'
$stageTextures = Join-Path $stageDir 'textures'
New-Item -ItemType Directory -Force -Path $stageTextures | Out-Null

# An asset may texture more than one material -- a body atlas plus a separate
# face projection, for instance. Accept the multi-material form, and fold the
# older single-material form into it so existing recipes keep working.
$materialTextures = [ordered]@{}
if ($recipeData.material_textures) {
    foreach ($m in $recipeData.material_textures.PSObject.Properties) {
        $materialTextures[$m.Name] = $m.Value
    }
} elseif ($recipeData.normalize.textured_material -and $recipeData.textures) {
    $materialTextures[$recipeData.normalize.textured_material] = $recipeData.textures
}

$slugFor = {
    param($text)
    ($text -replace '^M_', '') -replace '[^A-Za-z0-9]', ''
}

$textureMap = [ordered]@{}
$textureFiles = [ordered]@{}
foreach ($mat in $materialTextures.Keys) {
    $matMap = [ordered]@{}
    $matFiles = [ordered]@{}
    foreach ($slot in $materialTextures[$mat].PSObject.Properties) {
        if (-not (Test-Path -LiteralPath $slot.Value)) {
            throw "Texture '$($slot.Name)' for material '$mat' missing at $($slot.Value)"
        }
        $destName = "T_{0}_{1}.png" -f (& $slugFor $mat), $slot.Name
        $dest = Join-Path $stageTextures $destName
        Copy-Item -LiteralPath $slot.Value -Destination $dest -Force
        $matMap[$slot.Name] = $dest
        $matFiles[$slot.Name] = $destName
    }
    $textureMap[$mat] = $matMap
    $textureFiles[$mat] = $matFiles
}
$textureMapPath = Join-Path $workDir 'texture-map.json'
[System.IO.File]::WriteAllText($textureMapPath, ($textureMap | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))

# --- Stage B: normalize scale, origin, and naming ----------------------------
$normalizedFbx = Join-Path $stageDir "$assetId.fbx"
$normalizeReport = Join-Path $workDir 'normalize-report.json'
Invoke-Blender -Script 'normalize_ue5.py' -Label 'normalize' -ExpectedOutputs @($normalizedFbx, $normalizeReport) -ScriptArgs @(
    $recipePath.Path, $normalizedFbx, $normalizeReport, $textureMapPath
)

# --- Stage C: gate the exported file -----------------------------------------
$gateReport = Join-Path $workDir 'gate-rig-report.json'
Invoke-Blender -Script 'gate_rig.py' -Label "gate rig ($profileId)" -ExpectedOutputs @($gateReport) -ScriptArgs @(
    $normalizedFbx, $resolvedProfile, $gateReport
)

# --- Stage C2: texture quality -----------------------------------------------
# Skeleton gates say the character will animate. This one says whether it will
# look like anything. Both numbers land in the shipped manifest.
$uvRegions = Join-Path $workDir 'uv-regions.npz'
Invoke-Blender -Script 'export_uv_regions.py' -Label 'export uv regions' -ExpectedOutputs @($uvRegions) -ScriptArgs @(
    $normalizedFbx, $uvRegions
)

# --- Stage C1b: strip facial decals from clothed geometry --------------------
# Runs after the UV region map exists and before anything reads the atlas.
# The texture file is rewritten in place; the FBX references it by relative
# path and carries no pixels, so no re-export is needed.
$cleanReports = [ordered]@{}
if ($recipeData.clean_clothing_atlas) {
    foreach ($mat in $recipeData.clean_clothing_atlas.PSObject.Properties) {
        $target = $textureMap[$mat.Name]['BaseColor']
        if (-not $target) { continue }
        $opts = $mat.Value
        $cleanReport = Join-Path $workDir ("clean-{0}.json" -f ($mat.Name -replace '[^A-Za-z0-9]', ''))
        Write-Host "[$assetId] clean clothing atlas ($($mat.Name))" -ForegroundColor Cyan
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $cleanOut = & $compilerPython (Join-Path $repoRoot 'scripts\clean_clothing_atlas.py') `
                $target $uvRegions $target `
                --material $mat.Name `
                --regions $opts.regions `
                --tri-threshold $opts.tri_threshold `
                --grow $opts.grow `
                --report $cleanReport 2>&1
            $cleanCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previous
        }
        $cleanOut | Where-Object { $_ -match '^\[CLEAN\]' } | ForEach-Object { Write-Host "  $_" }
        if ($cleanCode -ne 0) { throw "clothing atlas clean failed for $($mat.Name)" }
        $cleanReports[$mat.Name] = (Get-Content -LiteralPath $cleanReport -Raw | ConvertFrom-Json)
    }
}

# --- Stage C1c: bake AO and pack ORM ----------------------------------------
# Retopology is unavailable for these meshes (see docs/ESCALATE-textures.md),
# so there is no low-poly target for a normal bake. AO is real geometry data
# these assets never had, and it completes the PBR set.
$pbrReports = [ordered]@{}
if ($recipeData.bake_pbr) {
    foreach ($mat in $recipeData.bake_pbr.PSObject.Properties) {
        $opts = $mat.Value
        $baseColor = $textureMap[$mat.Name]['BaseColor']
        $existingOrm = $textureMap[$mat.Name]['ORM']
        $ormName = "T_{0}_ORM.png" -f (& $slugFor $mat.Name)
        $ormPath = Join-Path $stageTextures $ormName
        $pbrReport = Join-Path $workDir ("pbr-{0}.json" -f ($mat.Name -replace '[^A-Za-z0-9]', ''))

        $pbrArgs = @($normalizedFbx, $mat.Name, $ormPath, $pbrReport)
        if ($baseColor)   { $pbrArgs += @('--basecolor', $baseColor) }
        if ($existingOrm) { $pbrArgs += @('--existing-orm', $existingOrm) }
        if ($opts.resolution) { $pbrArgs += @('--resolution', $opts.resolution) }
        if ($opts.samples)    { $pbrArgs += @('--samples', $opts.samples) }

        Invoke-Blender -Script 'bake_pbr.py' -Label "bake PBR ($($mat.Name))" -ExpectedOutputs @($pbrReport, $ormPath) -ScriptArgs $pbrArgs
        $pbrReports[$mat.Name] = (Get-Content -LiteralPath $pbrReport -Raw | ConvertFrom-Json)

        # The freshly baked ORM replaces whatever the recipe declared.
        $textureMap[$mat.Name]['ORM'] = $ormPath
        if (-not $textureFiles[$mat.Name]) { $textureFiles[$mat.Name] = [ordered]@{} }
        $textureFiles[$mat.Name]['ORM'] = $ormName
    }
}

$textureReports = [ordered]@{}
foreach ($mat in $textureMap.Keys) {
    $baseColor = $textureMap[$mat]['BaseColor']
    if (-not $baseColor) { continue }
    $texReport = Join-Path $workDir ("gate-texture-{0}.json" -f ($mat -replace '[^A-Za-z0-9]', ''))
    Write-Host "[$assetId] gate texture ($mat)" -ForegroundColor Cyan
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $texOut = & $compilerPython (Join-Path $repoRoot 'scripts\gate_texture.py') `
            $uvRegions $baseColor $resolvedProfile $texReport --material-name $mat 2>&1
        $texCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $texOut | Where-Object { $_ -match '^\[GATE TEX\]' -or $_ -match '^  - ' } |
        ForEach-Object { Write-Host "  $_" }
    if ($texCode -ne 0) {
        throw "texture gate failed for $mat with exit code $texCode"
    }
    $textureReports[$mat] = (Get-Content -LiteralPath $texReport -Raw | ConvertFrom-Json)
}

# --- Stage D: fixed-view evidence --------------------------------------------
if (-not $SkipRender) {
    Invoke-Blender -Script 'render_turnaround.py' -Label 'render turnaround' -ScriptArgs @(
        $normalizedFbx, $evidenceDir
    )
}

# --- Stage D2: deformation suite ---------------------------------------------
# A bind-pose render proves nothing. This is the gate that catches a mirrored
# rig or a joint that drives no geometry.
$deformPath = Join-Path $workDir 'deform-report.json'
if (-not $SkipRender) {
    Invoke-Blender -Script 'deform_test.py' -Label 'deformation suite' -ExpectedOutputs @($deformPath) -ScriptArgs @(
        $normalizedFbx, (Join-Path $evidenceDir 'deform'), $deformPath
    )
}

# --- Stage E: package --------------------------------------------------------
# Publish only after every gate has passed, and publish the staged directory
# whole so the FBX keeps its relative texture references. The payload is built
# in a hidden sibling and renamed into place only if out\<asset> is still
# absent, the way compile_prop.py does it: the published authority is never a
# scratch pad, and never deleted.
$publishDir = Join-Path (Split-Path -Parent $outDir) ('.{0}-{1}' -f $assetId, [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $publishDir | Out-Null
Copy-Item -Path (Join-Path $stageDir '*') -Destination $publishDir -Recurse -Force
$textureManifest = $textureFiles

# --- Stage F: UE5 import manifest --------------------------------------------
# Texture import settings are a per-file property in UE. Getting sRGB or the
# compression setting wrong on a Normal or ORM map produces lighting that looks
# subtly wrong in a way nobody can name for three weeks.
$importSettings = @{
    BaseColor = @{ sRGB = $true;  compression = 'TC_Default';   flip_green = $false }
    Normal    = @{ sRGB = $false; compression = 'TC_Normalmap'; flip_green = $true }
    ORM       = @{ sRGB = $false; compression = 'TC_Masks';     flip_green = $false }
}

$gate = Get-Content -LiteralPath $gateReport -Raw | ConvertFrom-Json
$deform = if (Test-Path -LiteralPath $deformPath) {
    $d = Get-Content -LiteralPath $deformPath -Raw | ConvertFrom-Json
    [ordered]@{ ok = $d.ok; failures = @($d.failures); warnings = @($d.warnings); poses = $d.poses }
} else { 'not run (-SkipRender)' }
$normalize = Get-Content -LiteralPath $normalizeReport -Raw | ConvertFrom-Json

$textures = [ordered]@{}
foreach ($mat in $textureManifest.Keys) {
    $perMaterial = [ordered]@{}
    foreach ($slot in $textureManifest[$mat].Keys) {
        $perMaterial[$slot] = @{
            file     = "textures/$($textureManifest[$mat][$slot])"
            settings = $importSettings[$slot]
        }
    }
    $textures[$mat] = $perMaterial
}

$manifest = [ordered]@{
    asset_id              = $assetId
    kind                  = $recipeData.kind
    skeleton_profile      = $profileId
    retarget_note         = $profile.retarget_note
    fbx                   = "$assetId.fbx"
    fbx_sha256            = (Get-FileHash -LiteralPath (Join-Path $publishDir "$assetId.fbx") -Algorithm SHA256).Hash.ToLowerInvariant()
    source_authority      = $recipeData.source.authority_fbx
    source_authority_sha256 = (Get-FileHash -LiteralPath $recipeData.source.authority_fbx -Algorithm SHA256).Hash.ToLowerInvariant()
    blender_version       = $normalize.blender_version
    ue5_import = [ordered]@{
        import_uniform_scale = 1.0
        import_as_skeletal   = $true
        skeleton             = 'None -- create new on first import, then reuse'
        root_bone_name       = $normalize.ue5_root_bone_will_be
        convert_scene        = $true
        force_front_x_axis   = $false
        normal_import_method = 'ImportNormals'
        max_influences       = $profile.max_influences
    }
    measurements = [ordered]@{
        height_m_before  = $normalize.before.height_m
        height_m_after   = $normalize.after.height_m
        height_cm_in_ue5 = [math]::Round($normalize.after.height_m * 100, 1)
        uniform_scale_applied = $normalize.uniform_scale_applied
        translation_applied   = $normalize.translation_applied
        bone_count_blender    = $gate.bone_count
        bone_count_expected_ue5 = $gate.bone_count + $(if ($normalize.ue5_root_bone_will_be) { 1 } else { 0 })
        total_tris            = $gate.total_tris
        max_influences        = ($gate.meshes | ForEach-Object { $_.max_influences } | Measure-Object -Maximum).Maximum
        unweighted_verts      = ($gate.meshes | ForEach-Object { $_.unweighted_verts } | Measure-Object -Sum).Sum
    }
    # LODs are generated by UE5's own mesh reduction, never by Blender's
    # Decimate modifier. Decimate produces long skinny triangles, which are the
    # direct cause of the faceted shading this pipeline exists to eliminate.
    # UE's reducer is edge-collapse with boundary and skinning constraints.
    lods = @(
        [ordered]@{ lod = 0; percent_triangles = 1.0;  screen_size = 1.0;  source = 'imported' }
        [ordered]@{ lod = 1; percent_triangles = 0.5;  screen_size = 0.4;  source = 'ue5_reduction' }
        [ordered]@{ lod = 2; percent_triangles = 0.25; screen_size = 0.15; source = 'ue5_reduction' }
    )
    materials = @($gate.meshes | ForEach-Object { $_.materials } | Select-Object -Unique)
    textures  = $textures
    gate = [ordered]@{
        profile  = $profileId
        ok       = $gate.ok
        failures = @($gate.failures)
        warnings = @($gate.warnings)
    }
    deformation = $deform
    texture_quality = $textureReports
    clothing_atlas_clean = $cleanReports
    pbr_bake = $pbrReports
}

Write-Utf8NoBom -Path (Join-Path $publishDir "$assetId.ue5import.json") -Text ($manifest | ConvertTo-Json -Depth 10)
Copy-Item -LiteralPath $resolvedProfile -Destination (Join-Path $publishDir 'resolved-profile.json')

# Rename into place. If an authority appeared while this ran, keep it and
# leave the fresh payload beside it for the person to compare.
if (Test-Path -LiteralPath $outDir) {
    throw "Published authority appeared during the compile: $outDir. It was not touched; the fresh payload is retained at $publishDir."
}
[System.IO.Directory]::Move($publishDir, $outDir)
$manifestPath = Join-Path $outDir "$assetId.ue5import.json"

Write-Host ""
Write-Host "[$assetId] RAC_COMPILE_OK" -ForegroundColor Green
Write-Host "  fbx      : $(Join-Path $outDir "$assetId.fbx")"
Write-Host "  manifest : $manifestPath"
Write-Host "  height   : $($normalize.after.height_m) m ($([math]::Round($normalize.after.height_m * 100, 1)) cm in UE5)"
Write-Host "  skeleton : $profileId, $($gate.bone_count) bones in FBX"
Write-Host "  tris     : $($gate.total_tris)"
