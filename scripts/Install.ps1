[CmdletBinding()]
param(
    [switch]$ReplaceExistingOverrides,
    [switch]$SkipIndependentTun,
    [switch]$SkipFlClashAutoStart
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

$taskName = 'FlClash-Strategy-20min'
$flClashTaskName = 'FlClash-Elevated-AtLogon'
$serviceName = 'FlClashMihomoService'
$packageRoot = Split-Path -Parent $PSScriptRoot
$managerSource = Join-Path $packageRoot 'src\strategy_manager.py'
$preflight = Join-Path $PSScriptRoot 'preflight.py'
$verifyScript = Join-Path $PSScriptRoot 'Verify.ps1'
$requirements = Join-Path $packageRoot 'requirements.txt'
$serviceBinarySource = Join-Path $packageRoot 'bin\FlClashMihomoService.exe'
$mihomoSource = Join-Path $packageRoot 'bin\mihomo.exe'
$appHome = Join-Path $env:APPDATA 'com.follow\clash'
$managed = Join-Path $appHome 'managed'
$installedManager = Join-Path $managed 'strategy_manager.py'
$serviceRuntime = Join-Path $managed 'mihomo-service'
$serviceDestination = 'C:\ProgramData\FlClashMihomoService'
$serviceBinary = Join-Path $serviceDestination 'FlClashMihomoService.exe'
$serviceXml = Join-Path $serviceDestination 'FlClashMihomoService.xml'
$installRecord = Join-Path $managed 'portable-install.json'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '请以管理员身份运行此脚本。'
    }
}

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
        $resolved = & $python.Source -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return ($resolved | Select-Object -Last 1).Trim()
        }
    }
    throw '未找到 Python 3.10 或更高版本。'
}

function Resolve-FlClash {
    $running = Get-CimInstance Win32_Process -Filter "Name='FlClash.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
    $runningPath = if ($running) { $running.ExecutablePath } else { $null }
    $candidates = @(
        $runningPath,
        (Join-Path $env:ProgramFiles 'FlClash\FlClash.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\FlClash\FlClash.exe')
    ) | Where-Object { $_ }
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} 'FlClash\FlClash.exe'
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw '找不到 FlClash.exe。请先安装并启动 FlClash。'
}

function Assert-PortFree([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listener) {
        throw "端口 $Port 已被其他程序占用。"
    }
}

Assert-Administrator
if (-not $ReplaceExistingOverrides) {
    throw '安装会替换 FlClash 现有覆写规则。确认已理解后，请增加参数 -ReplaceExistingOverrides。'
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw '此包只包含 Windows x64 版 Mihomo。'
}

foreach ($required in @($managerSource, $preflight, $verifyScript, $requirements, $serviceBinarySource, $mihomoSource)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "交付包缺少文件：$required"
    }
}

$pythonExe = Resolve-Python
$pythonVersion = & $pythonExe -c 'import sys; print(".".join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3,10) else 1)'
if ($LASTEXITCODE -ne 0) {
    throw "Python 版本过低：$pythonVersion"
}
$pythonwExe = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonwExe)) {
    throw '当前 Python 安装缺少 pythonw.exe，无法创建静默后台任务。'
}

& $pythonExe -c 'import yaml' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install --user --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) {
        throw 'PyYAML 安装失败。'
    }
}

$flClashExe = Resolve-FlClash
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $existingService) {
    Assert-PortFree 17890
    Assert-PortFree 19090
}

& $pythonExe $preflight
if ($LASTEXITCODE -ne 0) {
    throw '安装前检查未通过；上方 JSON 列出了原因。'
}

New-Item -ItemType Directory -Path $managed -Force | Out-Null
if (-not (Test-Path -LiteralPath $installRecord)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = Join-Path $managed "backups\portable-$stamp"
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach ($name in @('database.sqlite', 'shared_preferences.json', 'config.yaml')) {
        $source = Join-Path $appHome $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $backup $name) -Force
        }
    }
    $profiles = Join-Path $appHome 'profiles'
    if (Test-Path -LiteralPath $profiles) {
        Copy-Item -LiteralPath $profiles -Destination (Join-Path $backup 'profiles') -Recurse -Force
    }
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $runItem = Get-ItemProperty -Path $runKey -ErrorAction SilentlyContinue
    $runValue = if ($runItem) { $runItem.PSObject.Properties['FlClash'] } else { $null }
    [pscustomobject]@{
        RegistryPath = $runKey
        Name = 'FlClash'
        Value = if ($runValue) { $runValue.Value } else { $null }
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'FlClash-HKCU-Run.json') -Encoding UTF8
} else {
    $previous = Get-Content -LiteralPath $installRecord -Raw | ConvertFrom-Json
    $backup = [string]$previous.BackupPath
}

[pscustomobject]@{
    InstalledAt = (Get-Date).ToString('o')
    PackageVersion = '1.0.0'
    BackupPath = $backup
    Python = $pythonExe
    FlClash = $flClashExe
    Status = 'Installing'
} | ConvertTo-Json | Set-Content -LiteralPath $installRecord -Encoding UTF8

Write-Host '正在安装动态策略并执行首次检测；FlClash 不会被关闭。'
& $pythonExe $managerSource --install
if ($LASTEXITCODE -ne 0) {
    throw '动态策略首次安装失败；可使用 Restore-Previous.ps1 恢复。'
}

$serviceConfig = Join-Path $serviceRuntime 'config.yaml'
if (-not (Test-Path -LiteralPath $serviceConfig)) {
    throw '独立 Mihomo 配置没有生成。'
}

if (-not $existingService) {
    New-Item -ItemType Directory -Path $serviceDestination -Force | Out-Null
    Copy-Item -LiteralPath $serviceBinarySource -Destination $serviceBinary -Force
    Copy-Item -LiteralPath $mihomoSource -Destination (Join-Path $serviceDestination 'mihomo.exe') -Force
    $escapedRuntime = [Security.SecurityElement]::Escape($serviceRuntime)
    $xml = @"
<service>
  <id>$serviceName</id>
  <name>FlClash Mihomo Independent Service</name>
  <description>Independent LocalSystem Mihomo core for the managed FlClash strategy.</description>
  <executable>%BASE%\mihomo.exe</executable>
  <arguments>-d &quot;$escapedRuntime&quot; -f &quot;$escapedRuntime\config.yaml&quot;</arguments>
  <workingdirectory>$escapedRuntime</workingdirectory>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <stoptimeout>15 sec</stoptimeout>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
  <resetfailure>1 hour</resetfailure>
  <log mode="roll" />
</service>
"@
    [IO.File]::WriteAllText($serviceXml, $xml, [Text.UTF8Encoding]::new($false))
    & $serviceBinary install --no-elevate
    if ($LASTEXITCODE -ne 0) {
        throw '独立 Mihomo Windows 服务安装失败。'
    }
} else {
    $expectedServiceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $serviceBinarySource).Hash
    $installedServiceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $serviceBinary).Hash
    if ($expectedServiceHash -ne $installedServiceHash) {
        throw '已存在同名服务，但 WinSW 版本与此包不同。请先恢复或卸载旧项目。'
    }
}

$service = Get-Service -Name $serviceName
if ($service.Status -ne 'Running') {
    Start-Service -Name $serviceName
}
$deadline = (Get-Date).AddSeconds(15)
do {
    Start-Sleep -Milliseconds 500
    $serviceReady = Test-NetConnection -ComputerName 127.0.0.1 -Port 19090 -InformationLevel Quiet -WarningAction SilentlyContinue
} until ($serviceReady -or (Get-Date) -ge $deadline)
if (-not $serviceReady) {
    throw '独立 Mihomo 服务已安装，但控制端口 19090 未就绪。'
}

if (-not $SkipIndependentTun) {
    & $pythonExe $installedManager --service-tun-on
    if ($LASTEXITCODE -ne 0) {
        throw '独立 TUN 启用失败，管理器已尝试回滚到原状态。'
    }
}

$userId = "$env:USERDOMAIN\$env:USERNAME"
$managerAction = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$installedManager`" --scheduled" -WorkingDirectory $managed
$repeatTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration (New-TimeSpan -Days 3650)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$managerPrincipal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName $taskName -Action $managerAction -Trigger @($repeatTrigger, $logonTrigger) -Principal $managerPrincipal -Settings $taskSettings -Description 'Update FlClash dynamic strategy groups every 20 minutes without a console window.' -Force | Out-Null

if (-not $SkipFlClashAutoStart) {
    $flClashAction = New-ScheduledTaskAction -Execute $flClashExe
    $flClashTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
    $flClashPrincipal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $flClashTaskName -Action $flClashAction -Trigger $flClashTrigger -Principal $flClashPrincipal -Settings $taskSettings -Description 'Start FlClash elevated at user logon.' -Force | Out-Null
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $runItem = Get-ItemProperty -Path $runKey -ErrorAction SilentlyContinue
    $runProperty = if ($runItem) { $runItem.PSObject.Properties['FlClash'] } else { $null }
    if ($runProperty) {
        Remove-ItemProperty -Path $runKey -Name 'FlClash'
    }
}

[pscustomobject]@{
    InstalledAt = (Get-Date).ToString('o')
    PackageVersion = '1.0.0'
    BackupPath = $backup
    Python = $pythonExe
    FlClash = $flClashExe
    ServiceTunEnabled = -not $SkipIndependentTun
    Status = 'Complete'
} | ConvertTo-Json | Set-Content -LiteralPath $installRecord -Encoding UTF8

& $verifyScript -SkipTunCheck:$SkipIndependentTun
if ($LASTEXITCODE -ne 0) {
    throw '安装完成，但验收未全部通过；请查看上方结果。'
}

Write-Host '安装与验收完成。日常使用无需运行 Codex。'
