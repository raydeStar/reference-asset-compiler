<# Read-only ownership check shared by the direct AI launchers. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateRange(1, 1048576)][int] $MinimumFreeVramMiB,
    [string] $ComfyUrl = 'http://127.0.0.1:8188',
    [switch] $Json
)
$ErrorActionPreference = 'Stop'
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $gpuLines = @(& nvidia-smi --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits 2>&1 | ForEach-Object { $_.ToString() })
    $gpuExit = $LASTEXITCODE
    $computeApps = @(& nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>&1 | ForEach-Object { $_.ToString() })
    $ownersExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousPreference }
if ($gpuExit -ne 0 -or $ownersExit -ne 0 -or $gpuLines.Count -ne 1) {
    throw 'Unable to read one unambiguous GPU state and its owners; inference was not launched'
}
$parts = $gpuLines[0].Split(',')
if ($parts.Count -ne 2) { throw 'Malformed GPU state; inference was not launched' }
$freeMiB = [int]$parts[0].Trim()
$utilization = [int]$parts[1].Trim()
$comfyProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -match '(?i)ComfyUI[\\/]main\.py'
})
$queueRunning = 0
$queuePending = 0
if ($comfyProcesses.Count -gt 0) {
    try {
        $queue = Invoke-RestMethod -Uri ($ComfyUrl.TrimEnd('/') + '/queue') -TimeoutSec 4
        if ($null -eq $queue.queue_running -or $null -eq $queue.queue_pending) {
            throw 'ComfyUI queue response lacks running or pending entries'
        }
        $queueRunning = @($queue.queue_running).Count
        $queuePending = @($queue.queue_pending).Count
    } catch {
        throw "ComfyUI owns a live process but its queue could not be verified; inference was not launched: $($_.Exception.Message)"
    }
    if ($queueRunning -gt 0 -or $queuePending -gt 0) {
        throw "ComfyUI queue is busy (running=$queueRunning pending=$queuePending); inference was not launched"
    }
}
if ($freeMiB -lt $MinimumFreeVramMiB) {
    throw "GPU has $freeMiB MiB free; $MinimumFreeVramMiB MiB is required. No process was killed and inference was not launched. Owners: $($computeApps -join '; ')"
}
$result = [pscustomobject]@{
    free_mib = $freeMiB
    utilization = $utilization
    compute_owners = $computeApps
    comfy_process_count = $comfyProcesses.Count
    queue_running = $queueRunning
    queue_pending = $queuePending
}
if ($Json) { $result | ConvertTo-Json -Depth 4 } else { $result }
