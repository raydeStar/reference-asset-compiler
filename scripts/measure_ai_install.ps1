[CmdletBinding()]
param(
    [string] $StudioRoot = $env:RAC_LEGACY_ROOT,
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($StudioRoot)) {
    throw 'Set RAC_LEGACY_ROOT or pass -StudioRoot.'
}
$studio = [System.IO.Path]::GetFullPath($StudioRoot)
$hfHome = if ($env:HF_HOME) {
    [System.IO.Path]::GetFullPath($env:HF_HOME)
}
else {
    Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\huggingface'
}

function Measure-Tree {
    param([string] $Name, [string] $Path, [string] $Purpose)
    $exists = Test-Path -LiteralPath $Path -PathType Container
    $bytes = [int64]0
    $files = 0
    if ($exists) {
        $items = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction Stop)
        $files = $items.Count
        $sum = ($items | Measure-Object -Property Length -Sum).Sum
        if ($null -ne $sum) { $bytes = [int64]$sum }
    }
    [pscustomobject]@{
        name = $Name
        purpose = $Purpose
        path = $Path
        exists = $exists
        files = $files
        bytes = $bytes
        gib = [math]::Round($bytes / 1GB, 3)
    }
}

function Find-HuggingFaceSubfolder {
    param([string] $RepositoryDirectory, [string] $Subfolder)
    $snapshots = Join-Path $RepositoryDirectory 'snapshots'
    if (-not (Test-Path -LiteralPath $snapshots -PathType Container)) { return $null }
    $match = Get-ChildItem -LiteralPath $snapshots -Directory -Force |
        ForEach-Object { Join-Path $_.FullName $Subfolder } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
        Select-Object -First 1
    return $match
}

$singleView = Find-HuggingFaceSubfolder `
    (Join-Path $hfHome 'hub\models--tencent--Hunyuan3D-2') 'hunyuan3d-dit-v2-0'
$multiview = Find-HuggingFaceSubfolder `
    (Join-Path $hfHome 'hub\models--tencent--Hunyuan3D-2mv') 'hunyuan3d-dit-v2-mv'
$missingSingle = Join-Path $hfHome `
    'hub\models--tencent--Hunyuan3D-2\snapshots\(not-installed)\hunyuan3d-dit-v2-0'
$missingMultiview = Join-Path $hfHome `
    'hub\models--tencent--Hunyuan3D-2mv\snapshots\(not-installed)\hunyuan3d-dit-v2-mv'

$rows = @(
    Measure-Tree 'geometry_checkout' (Join-Path $studio 'upstream\Hunyuan3D-2') 'geometry source'
    Measure-Tree 'paint_checkout' (Join-Path $studio 'upstream\Hunyuan3D-2.1') 'paint source'
    Measure-Tree 'geometry_environment' (Join-Path $studio '.venv-hy3d') 'geometry Python/CUDA environment'
    Measure-Tree 'paint_environment' (Join-Path $studio '.venv-hy3d21') 'paint Python/CUDA environment'
    Measure-Tree 'paint_weights' (Join-Path $studio 'models\hy3d21\Hunyuan3D-2.1') 'Hunyuan3D-Paint 2.1 PBR'
    Measure-Tree 'dino_weights' (Join-Path $studio 'models\hy3d21\dinov2-giant') 'DINOv2 giant image encoder'
    Measure-Tree 'single_view_geometry_cache' `
        $(if ($singleView) { $singleView } else { $missingSingle }) 'single-view geometry weights'
    Measure-Tree 'multiview_geometry_cache' `
        $(if ($multiview) { $multiview } else { $missingMultiview }) 'optional multiview geometry weights'
)
$installed = @($rows | Where-Object exists)
$totalBytes = [int64](($installed | Measure-Object -Property bytes -Sum).Sum)
$pinnedGeometry = @(
    [ordered]@{
        mode = 'single_view'
        revision = '9cd649ba6913f7a852e3286bad86bfa9a2d83dcf'
        files = @('config.yaml', 'model.fp16.safetensors')
        bytes = [int64]4928153166
        gib = [math]::Round(4928153166 / 1GB, 3)
    },
    [ordered]@{
        mode = 'multiview'
        revision = '3a761b539b29fe4ff64714813aa9560fd66f5de0'
        files = @('config.yaml', 'model.fp16.safetensors')
        bytes = [int64]4928153170
        gib = [math]::Round(4928153170 / 1GB, 3)
    }
)
$payload = [ordered]@{
    schema = 'reference-asset-compiler.ai-install-size.v1'
    measured_at = [DateTimeOffset]::Now.ToString('o')
    studio_root = $studio
    huggingface_home = $hfHome
    counting_method = 'logical file lengths; alternate weight formats are counted when both exist'
    components = $rows
    pinned_geometry_payloads = $pinnedGeometry
    total = [ordered]@{
        bytes = $totalBytes
        gib = [math]::Round($totalBytes / 1GB, 3)
    }
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 6
    return
}

$rows | Format-Table name, exists, files, gib, purpose -AutoSize
Write-Host ("RAC_AI_INSTALL_SIZE total_bytes={0} total_gib={1}" -f `
        $payload.total.bytes, $payload.total.gib)
Write-Host 'Pinned fresh geometry payload: 4,928,153,166 bytes single-view; 4,928,153,170 bytes multiview.'
Write-Host 'The ruler counts what is installed, including duplicate .bin/.safetensors files.'
