[CmdletBinding()]
param(
    [string] $LegacyRoot = $(if ($env:RAC_LEGACY_ROOT) { $env:RAC_LEGACY_ROOT } else { '' }),
    [string] $ComfyRoot = $(if ($env:RAC_COMFY_ROOT) { $env:RAC_COMFY_ROOT } else { '' }),
    [string] $Blender = $env:RAC_BLENDER,
    [string] $UnrealCmd = $env:RAC_UNREAL_CMD,
    [switch] $Json
)

# Ask the resolver for anything the caller did not pin, the same way the other
# drivers do. Reading the environment variable alone means an unset variable
# becomes an empty path and the report dies on its first Test-Path, which is a
# worse answer than 'not found' from a doctor whose whole job is to say what is
# installed.
if (-not $Blender) {
    $Blender = (& python (Join-Path $PSScriptRoot 'rac_env.py') --blender) | Select-Object -Last 1
}
if (-not $UnrealCmd) {
    $UnrealCmd = (& python (Join-Path $PSScriptRoot 'rac_env.py') --unreal-cmd) | Select-Object -Last 1
}

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$checks = [System.Collections.Generic.List[object]]::new()

function Add-WorkflowCheck {
    param(
        [Parameter(Mandatory = $true)][string] $Id,
        [Parameter(Mandatory = $true)][bool] $Available,
        [Parameter(Mandatory = $true)][string] $RequiredFor,
        [Parameter(Mandatory = $true)][string] $Detail
    )

    $checks.Add([pscustomobject]@{
        id = $Id
        available = $Available
        required_for = $RequiredFor
        detail = $Detail
    })
}

# Join-Path throws on an empty root, and an unset root is the single most
# likely state on a machine that is not the one this was built on. A doctor
# that dies when something is missing cannot report what is missing, so join
# against a visible placeholder and let the Test-Path below record it absent.
function Join-Root {
    param([string] $Root, [string] $Leaf, [string] $Variable)
    # Path-legal on Windows: angle brackets are not, and Test-Path throws on
    # them rather than returning false.
    if ([string]::IsNullOrWhiteSpace($Root)) { return ('({0} not set)' -f $Variable) }
    return (Join-Path $Root $Leaf)
}

$graph = Join-Path $repoRoot 'workflows\geometry\comfyui\hy3d_final_cut.json'
Add-WorkflowCheck -Id 'workflow.hy3d_final_cut' -Available (Test-Path -LiteralPath $graph -PathType Leaf) -RequiredFor 'historical ComfyUI geometry graph' -Detail $graph

$customNodes = Join-Root $ComfyRoot 'custom_nodes' 'RAC_COMFY_ROOT'
$hy3dWrapper = Join-Path $customNodes 'ComfyUI-Hunyuan3DWrapper'
$reactorCandidates = @(
    (Join-Path $customNodes 'comfyui-reactor-node'),
    (Join-Path $customNodes 'ComfyUI-ReActor')
)
$reactor = $reactorCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Container } | Select-Object -First 1
Add-WorkflowCheck -Id 'comfy.node.Hunyuan3DWrapper' -Available (Test-Path -LiteralPath $hy3dWrapper -PathType Container) -RequiredFor 'loading Hy3D nodes in the historical graph' -Detail $hy3dWrapper
Add-WorkflowCheck -Id 'comfy.node.ReActor' -Available ([bool]$reactor) -RequiredFor 'optional legacy face-swap branch only' -Detail $(if ($reactor) { $reactor } else { $reactorCandidates -join ' or ' })

$geometryPython = Join-Root $LegacyRoot '.venv-hy3d\Scripts\python.exe' 'RAC_LEGACY_ROOT'
$geometryRunner = Join-Root $LegacyRoot 'scripts\run_hy3d_multiview.py' 'RAC_LEGACY_ROOT'
$geometryUpstream = Join-Root $LegacyRoot 'upstream\Hunyuan3D-2' 'RAC_LEGACY_ROOT'
Add-WorkflowCheck -Id 'hy3d2mv.python' -Available (Test-Path -LiteralPath $geometryPython -PathType Leaf) -RequiredFor 'guarded image-conditioned multiview geometry candidate' -Detail $geometryPython
if (Test-Path -LiteralPath $geometryRunner -PathType Leaf) {
    $geometryRunnerHash = (Get-FileHash -LiteralPath $geometryRunner -Algorithm SHA256).Hash
    $geometryRunnerExact = $geometryRunnerHash -eq '36C7B72DF2CDAD4CE55CD309F4FB6CA9343521FF078399836F8FA57C6A9320C2'
} else {
    $geometryRunnerHash = 'missing'
    $geometryRunnerExact = $false
}
Add-WorkflowCheck -Id 'hy3d2mv.runner_exact' -Available $geometryRunnerExact -RequiredFor 'guarded image-conditioned multiview geometry candidate' -Detail "$geometryRunner sha256=$geometryRunnerHash"
Add-WorkflowCheck -Id 'hy3d2mv.upstream' -Available (Test-Path -LiteralPath $geometryUpstream -PathType Container) -RequiredFor 'guarded image-conditioned multiview geometry candidate' -Detail $geometryUpstream

$paintPython = Join-Root $LegacyRoot '.venv-hy3d21\Scripts\python.exe' 'RAC_LEGACY_ROOT'
$paintRunner = Join-Root $LegacyRoot 'scripts\run_hy3d21_pbr.py' 'RAC_LEGACY_ROOT'
$paintUpstream = Join-Root $LegacyRoot 'upstream\Hunyuan3D-2.1' 'RAC_LEGACY_ROOT'
$paintModel = Join-Root $LegacyRoot 'models\hy3d21\Hunyuan3D-2.1' 'RAC_LEGACY_ROOT'
Add-WorkflowCheck -Id 'hy3d21.python' -Available (Test-Path -LiteralPath $paintPython -PathType Leaf) -RequiredFor 'default existing-mesh PBR texture candidate' -Detail $paintPython
if (Test-Path -LiteralPath $paintRunner -PathType Leaf) {
    $runnerHash = (Get-FileHash -LiteralPath $paintRunner -Algorithm SHA256).Hash
    # Keep this authority synchronized with run_hy3d21_texture.ps1.  The
    # current runner adds immutable UV/geometry validation and diagnostics;
    # treating its verified hash as missing blocks the very guarded path the
    # doctor is meant to admit.
    $runnerExact = $runnerHash -eq 'B039065EA96E0E63EFFECBA4379F63B8228F830B036EF1392790E5BF6B8F8A8B'
} else {
    $runnerHash = 'missing'
    $runnerExact = $false
}
Add-WorkflowCheck -Id 'hy3d21.runner_exact' -Available $runnerExact -RequiredFor 'default existing-mesh PBR texture candidate' -Detail "$paintRunner sha256=$runnerHash"
Add-WorkflowCheck -Id 'hy3d21.upstream' -Available (Test-Path -LiteralPath $paintUpstream -PathType Container) -RequiredFor 'default existing-mesh PBR texture candidate' -Detail $paintUpstream
Add-WorkflowCheck -Id 'hy3d21.model' -Available (Test-Path -LiteralPath $paintModel -PathType Container) -RequiredFor 'default existing-mesh PBR texture candidate' -Detail $paintModel

Add-WorkflowCheck -Id 'blender' -Available (Test-Path -LiteralPath $Blender -PathType Leaf) -RequiredFor 'review, topology, rig gates, and export' -Detail $Blender

$arpProbe = Join-Path $repoRoot 'scripts\blender\preflight_arp.py'
$arpAvailable = $false
$arpDetail = 'Blender is unavailable, so Auto-Rig Pro was not probed'
if (Test-Path -LiteralPath $Blender -PathType Leaf) {
    $arpOutput = @(& $Blender '--background' '--factory-startup' '--python-exit-code' '1' '--python' $arpProbe 2>&1)
    $arpExitCode = $LASTEXITCODE
    $arpLine = $arpOutput | Where-Object { $_ -like 'RAC_ARP_PREFLIGHT_JSON=*' } | Select-Object -Last 1
    if ($arpLine) {
        $arpReport = ($arpLine -replace '^RAC_ARP_PREFLIGHT_JSON=', '') | ConvertFrom-Json
        $arpAvailable = $arpExitCode -eq 0 -and [bool]$arpReport.ok
        $operatorCount = @($arpReport.operators.psobject.Properties | Where-Object Value).Count
        $propertyCount = @($arpReport.scene_properties.psobject.Properties | Where-Object Value).Count
        $arpDetail = 'Blender {0}; module={1}; operators={2}/{3}; ue5_controls={4}/{5}' -f `
            $arpReport.blender_version, $arpReport.addon_module, $operatorCount, `
            @($arpReport.operators.psobject.Properties).Count, $propertyCount, `
            @($arpReport.scene_properties.psobject.Properties).Count
        if ($arpReport.failure) { $arpDetail += '; failure=' + $arpReport.failure }
    }
    else {
        $arpDetail = 'Auto-Rig Pro probe emitted no report; exit=' + $arpExitCode
    }
}
Add-WorkflowCheck -Id 'auto_rig_pro.operational' -Available $arpAvailable -RequiredFor 'preferred existing-mesh humanoid rig authoring' -Detail $arpDetail

$autoRemeshProbe = Join-Path $repoRoot 'scripts\blender\preflight_autoremesher.py'
$autoRemeshAvailable = $false
$autoRemeshDetail = 'Blender is unavailable, so AutoRemesher was not probed'
if (Test-Path -LiteralPath $Blender -PathType Leaf) {
    $autoRemeshOutput = @(& $Blender '--background' '--python-exit-code' '1' '--python' $autoRemeshProbe 2>&1)
    $autoRemeshExitCode = $LASTEXITCODE
    $autoRemeshLine = $autoRemeshOutput | Where-Object { $_ -like 'RAC_AUTOREMESHER_PREFLIGHT_JSON=*' } | Select-Object -Last 1
    if ($autoRemeshLine) {
        $autoRemeshReport = ($autoRemeshLine -replace '^RAC_AUTOREMESHER_PREFLIGHT_JSON=', '') | ConvertFrom-Json
        $autoRemeshAvailable = $autoRemeshExitCode -eq 0 -and [bool]$autoRemeshReport.ok
        $autoRemeshDetail = 'Blender {0}; enabled={1}; settings={2}; operator={3}' -f `
            $autoRemeshReport.blender_version, $autoRemeshReport.enabled, `
            $autoRemeshReport.scene_settings, $autoRemeshReport.operator
    }
    else { $autoRemeshDetail = 'AutoRemesher probe emitted no report; exit=' + $autoRemeshExitCode }
}
Add-WorkflowCheck -Id 'autoremesher.operational' -Available $autoRemeshAvailable -RequiredFor 'isolated raw-generation reduction challenger' -Detail $autoRemeshDetail

Add-WorkflowCheck -Id 'unreal.commandlet' -Available (Test-Path -LiteralPath $UnrealCmd -PathType Leaf) -RequiredFor 'UE import verification and cook' -Detail $UnrealCmd

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
Add-WorkflowCheck -Id 'wsl' -Available ([bool]$wsl) -RequiredFor 'Pixal3D and TRELLIS.2 challengers' -Detail $(if ($wsl) { $wsl.Source } else { 'wsl.exe not found' })

$gpu = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
Add-WorkflowCheck -Id 'nvidia-smi' -Available ([bool]$gpu) -RequiredFor 'read-only GPU ownership and VRAM preflight' -Detail $(if ($gpu) { $gpu.Source } else { 'nvidia-smi.exe not found' })

$result = [ordered]@{
    schema = 'reference-asset-compiler.workflow-doctor.v1'
    timestamp = [DateTimeOffset]::Now.ToString('o')
    inference_launched = $false
    checks = $checks
    routing = [ordered]@{
        geometry = 'guarded direct Hunyuan3D-2mv runner with immutable multiview request, VRAM and Comfy queue checks, and one-shot attempt directories'
        comfyui = 'preserved historical geometry graph; optional until its exact custom-node environment is restored'
        texture = 'Hunyuan3D-Paint 2.1 local runner'
        texture_challenger = 'TRELLIS.2 in WSL'
        rigging = $(if ($arpAvailable) { 'Auto-Rig Pro existing-mesh authoring and candidate driver are operational; explicit hand landmarks and downstream gates remain' } else { 'No operational preferred existing-mesh humanoid rig runtime' })
        rigging_challenger = 'AniGen generates a replacement mesh and rig together; it cannot advance an approved mesh through rig_and_skin'
        reduction_challenger = $(if ($autoRemeshAvailable) { 'AutoRemesher is operational; candidates require fixed-view and bake gates' } else { 'No operational AutoRemesher reduction challenger' })
        post_authority = 'compiler scripts and UE5 verification'
    }
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
    return
}

foreach ($check in $checks) {
    $mark = if ($check.available) { 'OK' } else { 'MISSING' }
    Write-Host ("[{0}] {1} -- {2}" -f $mark, $check.id, $check.detail)
}

$requiredMissing = @($checks | Where-Object {
    -not $_.available -and $_.id -in @(
        'workflow.hy3d_final_cut',
        'hy3d2mv.python',
        'hy3d2mv.runner_exact',
        'hy3d2mv.upstream',
        'hy3d21.python',
        'hy3d21.runner_exact',
        'hy3d21.upstream',
        'hy3d21.model',
        'blender',
        'unreal.commandlet'
    )
})
if ($requiredMissing.Count -gt 0) {
    throw "WORKFLOW_DOCTOR_INCOMPLETE required_missing=$($requiredMissing.Count) -- the butler found locked doors and declined to call them hallways."
}

Write-Host 'WORKFLOW_DOCTOR_OK -- generation routes are identified; no GPU work was launched.'
