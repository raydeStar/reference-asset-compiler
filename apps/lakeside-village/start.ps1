[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $assets = @('timber-cabin', 'round-cottage', 'pine-tree', 'wooden-dock', 'rowboat', 'mossy-rock', 'barrel-crates')
    foreach ($asset in $assets) {
        if (-not (Test-Path -LiteralPath "public/assets/$asset.glb")) {
            throw "Missing $asset.glb. Restore the retained demo assets described in README.md; the butler cannot display an imaginary file."
        }
    }
    if (-not (Test-Path -LiteralPath 'node_modules/vite')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Retry when the connection returns.' }
    }
    Write-Host 'Stillwater is opening at http://127.0.0.1:5178 — the lake has kept your seat.'
    & npm.cmd run dev
} finally {
    Pop-Location
}
