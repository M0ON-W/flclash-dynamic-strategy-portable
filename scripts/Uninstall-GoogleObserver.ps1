[CmdletBinding()]
param([switch]$RemoveObservationData)

$ErrorActionPreference = 'Stop'
$taskName = 'FlClash-Google-Observer-20min'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
if ($RemoveObservationData) {
    $observerHome = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'com.follow\clash\managed\google-observer'))
    $managedRoot = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'com.follow\clash\managed')) + [IO.Path]::DirectorySeparatorChar
    if (-not $observerHome.StartsWith($managedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Observer path boundary check failed.' }
    if (Test-Path -LiteralPath $observerHome) { Remove-Item -LiteralPath $observerHome -Recurse -Force }
}
Write-Host "Uninstalled $taskName"
