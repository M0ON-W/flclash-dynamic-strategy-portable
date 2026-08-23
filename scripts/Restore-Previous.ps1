[CmdletBinding()]
param(
    [switch]$ConfirmRestore
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if (-not $ConfirmRestore) {
    throw '此操作会停止独立 TUN 并恢复安装前配置。确认后请增加参数 -ConfirmRestore。'
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请以管理员身份运行此脚本。'
}

$appHome = Join-Path $env:APPDATA 'com.follow\clash'
$managed = Join-Path $appHome 'managed'
$installRecord = Join-Path $managed 'portable-install.json'
if (-not (Test-Path -LiteralPath $installRecord)) {
    throw '找不到 portable-install.json，无法确定应恢复的备份。'
}
$record = Get-Content -LiteralPath $installRecord -Raw | ConvertFrom-Json
$backup = [IO.Path]::GetFullPath([string]$record.BackupPath)
$backupRoot = [IO.Path]::GetFullPath((Join-Path $managed 'backups'))
if (-not $backup.StartsWith($backupRoot, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $backup)) {
    throw '安装记录中的备份路径无效。'
}

$running = Get-Process FlClash, FlClashCore -ErrorAction SilentlyContinue
if ($running) {
    throw '请先手动退出 FlClash，再运行恢复脚本；脚本不会替你关闭它。'
}

foreach ($taskName in @('FlClash-Strategy-20min', 'FlClash-Elevated-AtLogon')) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}

$serviceName = 'FlClashMihomoService'
$serviceDestination = [IO.Path]::GetFullPath('C:\ProgramData\FlClashMihomoService')
$expectedServiceDestination = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'FlClashMihomoService'))
if (-not $serviceDestination.Equals($expectedServiceDestination, [StringComparison]::OrdinalIgnoreCase)) {
    throw '服务目录校验失败。'
}
$serviceBinary = Join-Path $serviceDestination 'FlClashMihomoService.exe'
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $serviceName -Force
        (Get-Service -Name $serviceName).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
    }
    if (Test-Path -LiteralPath $serviceBinary) {
        & $serviceBinary uninstall --no-elevate
        if ($LASTEXITCODE -ne 0) {
            throw '独立 Mihomo 服务卸载失败。'
        }
    } else {
        throw '服务存在但包装器文件缺失，未自动删除服务。'
    }
}
if (Test-Path -LiteralPath $serviceDestination) {
    Remove-Item -LiteralPath $serviceDestination -Recurse -Force
}

foreach ($name in @('database.sqlite', 'shared_preferences.json', 'config.yaml')) {
    $source = Join-Path $backup $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $appHome $name) -Force
    }
}

$runBackupPath = Join-Path $backup 'FlClash-HKCU-Run.json'
if (Test-Path -LiteralPath $runBackupPath) {
    $runBackup = Get-Content -LiteralPath $runBackupPath -Raw | ConvertFrom-Json
    if ($null -ne $runBackup.Value -and [string]$runBackup.Value) {
        New-Item -Path $runBackup.RegistryPath -Force | Out-Null
        Set-ItemProperty -Path $runBackup.RegistryPath -Name $runBackup.Name -Value ([string]$runBackup.Value)
    }
}

$scriptPath = Join-Path $appHome 'scripts\348822000000000101.js'
if (Test-Path -LiteralPath $scriptPath) {
    Remove-Item -LiteralPath $scriptPath -Force
}
$serviceRuntime = [IO.Path]::GetFullPath((Join-Path $managed 'mihomo-service'))
$managedRoot = [IO.Path]::GetFullPath($managed) + [IO.Path]::DirectorySeparatorChar
if (-not $serviceRuntime.StartsWith($managedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw '托管运行目录校验失败。'
}
if (Test-Path -LiteralPath $serviceRuntime) {
    Remove-Item -LiteralPath $serviceRuntime -Recurse -Force
}
foreach ($name in @('state.json', 'latest_status.json', 'manager.log', 'manager.log.1', 'manager.lock', 'last-known-good.yaml', 'strategy_manager.py', 'portable-install.json')) {
    $path = Join-Path $managed $name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

Write-Host "已恢复安装前配置：$backup"
Write-Host '现在可以重新启动 FlClash。'
