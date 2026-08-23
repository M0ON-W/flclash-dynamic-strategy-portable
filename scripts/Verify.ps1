[CmdletBinding()]
param(
    [switch]$SkipTunCheck
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$runtimeVerifier = Join-Path $PSScriptRoot 'verify_runtime.py'
$taskName = 'FlClash-Strategy-20min'
$serviceName = 'FlClashMihomoService'
$failed = $false

function Resolve-Python {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolved = & $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return ($resolved | Select-Object -Last 1).Trim()
        }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw '未找到 Python。'
}

try {
    $pythonExe = Resolve-Python
    $runtimeArguments = @($runtimeVerifier)
    if ($SkipTunCheck) {
        $runtimeArguments += '--skip-tun-check'
    }
    & $pythonExe @runtimeArguments
    if ($LASTEXITCODE -ne 0) {
        $failed = $true
    }
} catch {
    Write-Error $_.Exception.Message
    $failed = $true
}

$service = Get-CimInstance Win32_Service -Filter "Name='$serviceName'" -ErrorAction SilentlyContinue
$serviceResult = [pscustomobject]@{
    Name = $serviceName
    Installed = $null -ne $service
    State = if ($service) { $service.State } else { $null }
    StartMode = if ($service) { $service.StartMode } else { $null }
}
$serviceResult | Format-List
if (-not $service -or $service.State -ne 'Running' -or $service.StartMode -ne 'Auto') {
    $failed = $true
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$taskInfo = if ($task) { Get-ScheduledTaskInfo -TaskName $taskName } else { $null }
$taskResult = [pscustomobject]@{
    Name = $taskName
    Installed = $null -ne $task
    State = if ($task) { $task.State } else { $null }
    LastTaskResult = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
    NextRunTime = if ($taskInfo) { $taskInfo.NextRunTime } else { $null }
    SilentExecutable = if ($task) { [IO.Path]::GetFileName($task.Actions[0].Execute) } else { $null }
}
$taskResult | Format-List
if (-not $task -or $task.State -notin @('Ready', 'Running') -or $taskResult.SilentExecutable -ne 'pythonw.exe') {
    $failed = $true
}

if (-not $SkipTunCheck) {
    $adapter = Get-NetAdapter -Name 'MihomoSvc' -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Adapter = 'MihomoSvc'
        Present = $null -ne $adapter
        Status = if ($adapter) { $adapter.Status } else { $null }
    } | Format-List
    if (-not $adapter -or $adapter.Status -ne 'Up') {
        $failed = $true
    }
}

if ($failed) {
    Write-Error '验收未全部通过。'
    exit 1
}

Write-Host '验收通过。'
exit 0
