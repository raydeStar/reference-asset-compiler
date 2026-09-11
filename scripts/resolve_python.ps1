param([string] $Python)
$ErrorActionPreference = 'Stop'
if ($Python) {
    $resolved = Get-Command $Python -ErrorAction Stop
    return $resolved.Source
}
$repoPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $repoPython -PathType Leaf) { return $repoPython }
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($version in @('-3.12', '-3.11')) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $candidate = & py $version -c 'import sys; print(sys.executable)' 2>$null }
        finally { $ErrorActionPreference = $previousPreference }
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
}
return (Get-Command python -ErrorAction Stop).Source
