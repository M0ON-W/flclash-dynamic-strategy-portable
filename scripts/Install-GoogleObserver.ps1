[CmdletBinding()]
param([switch]$StartNow)

$ErrorActionPreference = 'Stop'
$taskName = 'FlClash-Google-Observer-20min'
$appHome = Join-Path $env:APPDATA 'com.follow\clash'
$observerHome = Join-Path $appHome 'managed\google-observer'
$pythonw = 'C:\Users\WangYue\AppData\Local\Programs\Python\Python312\pythonw.exe'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceObserver = Join-Path $repoRoot 'src\google_observer.py'
$sourceManager = Join-Path $repoRoot 'src\strategy_manager.py'
foreach ($path in @($pythonw, $sourceObserver, $sourceManager)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required file: $path" }
}
New-Item -ItemType Directory -Path $observerHome -Force | Out-Null
Copy-Item -LiteralPath $sourceObserver -Destination (Join-Path $observerHome 'google_observer.py') -Force
Copy-Item -LiteralPath $sourceManager -Destination (Join-Path $observerHome 'strategy_manager.py') -Force
$currentUser = $env:USERDOMAIN + '\' + $env:USERNAME
& icacls.exe $observerHome /inheritance:r /grant:r ($currentUser + ':(OI)(CI)F') 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict observer directory ACL.' }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + (Join-Path $observerHome 'google_observer.py') + '" --scheduled') -WorkingDirectory $observerHome
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(20) -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration (New-TimeSpan -Days 3650)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($repeat, $logon) -Principal $principal -Settings $settings -Description 'Read-only staged Google egress observer. Does not reload either proxy core.' -Force | Out-Null
if ($StartNow) { Start-ScheduledTask -TaskName $taskName }
Write-Host "Installed $taskName"
