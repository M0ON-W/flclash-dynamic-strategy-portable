<#
.SYNOPSIS
    重新生成 SHA256SUMS.txt。

.DESCRIPTION
    按 git 跟踪的文件生成可移植包的文件清单校验值，排除 .github/ 与
    SHA256SUMS.txt 自身。发布新版本前运行一次，并同步更新 manifest.json 的
    版本号与 docs/releases/ 下的发布说明。
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$output = Join-Path $repoRoot 'SHA256SUMS.txt'

$previousEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
    $raw = & git -C $repoRoot -c core.quotepath=false ls-files -z
    if ($LASTEXITCODE -ne 0) { throw 'git ls-files failed' }
} finally {
    [Console]::OutputEncoding = $previousEncoding
}

$lines = foreach ($file in (($raw -split "`0") | Where-Object { $_ } | Sort-Object)) {
    $relative = $file -replace '\\', '/'
    if ($relative -eq 'SHA256SUMS.txt' -or $relative.StartsWith('.github/')) { continue }
    $full = Join-Path $repoRoot ($relative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $full)) { throw "missing tracked file: $relative" }
    $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLower()
    "$hash  $relative"
}

[IO.File]::WriteAllLines($output, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "wrote $output ($($lines.Count) entries)"

