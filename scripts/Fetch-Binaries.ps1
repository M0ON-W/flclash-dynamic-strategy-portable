<#
.SYNOPSIS
    取回可移植包所需的二进制，并按 manifest.json 校验 SHA-256。

.DESCRIPTION
    bin/mihomo.exe 与 bin/FlClashMihomoService.exe 不再保存在版本库里。
    mihomo.exe 默认从 MetaCubeX 官方发行包下载后解压；FlClashMihomoService.exe
    默认从本机已安装的 FlClash 服务目录复制。两个文件都必须与 manifest.json
    中的 binary_sha256 一致，任何不匹配都会报错退出。

.EXAMPLE
    .\scripts\Fetch-Binaries.ps1

.EXAMPLE
    .\scripts\Fetch-Binaries.ps1 -MihomoZip D:\downloads\mihomo-windows-amd64-v1.19.30.zip
#>
[CmdletBinding()]
param(
    [string]$MihomoZip,
    [string]$ServiceExePath = (Join-Path $env:ProgramData 'FlClashMihomoService\FlClashMihomoService.exe'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$binDir = Join-Path $repoRoot 'bin'
$manifestPath = Join-Path $repoRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "找不到 manifest.json：$manifestPath" }

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$targets = @(
    @{ Name = 'mihomo.exe';                  Hash = $manifest.binary_sha256.'bin/mihomo.exe'.ToLower() },
    @{ Name = 'FlClashMihomoService.exe';    Hash = $manifest.binary_sha256.'bin/FlClashMihomoService.exe'.ToLower() }
)

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

function Test-Ready([string]$Path, [string]$Hash) {
    (Test-Path -LiteralPath $Path) -and ((Get-Sha256 $Path) -eq $Hash)
}

New-Item -ItemType Directory -Path $binDir -Force | Out-Null

# --- mihomo.exe ---
$mihomoTarget = Join-Path $binDir 'mihomo.exe'
$mihomoHash = $targets[0].Hash
if ((Test-Ready $mihomoTarget $mihomoHash) -and -not $Force) {
    Write-Host 'mihomo.exe：已存在且哈希一致，跳过。'
} else {
    $zipPath = $MihomoZip
    if (-not $zipPath) {
        $zipPath = Join-Path $env:TEMP ('mihomo-windows-amd64-v{0}.zip' -f $manifest.mihomo_release.version)
        if (-not (Test-Path -LiteralPath $zipPath)) {
            Write-Host ('下载 mihomo {0} ...' -f $manifest.mihomo_release.version)
            Invoke-WebRequest -Uri $manifest.mihomo_release.url -OutFile $zipPath -UseBasicParsing
        }
    }
    if (-not (Test-Path -LiteralPath $zipPath)) { throw "找不到 mihomo 发行包：$zipPath" }

    $extractDir = Join-Path $env:TEMP ('mihomo-extract-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    try {
        $assetPath = Join-Path $extractDir $manifest.mihomo_release.asset
        if (-not (Test-Path -LiteralPath $assetPath)) {
            throw "发行包中缺少 $($manifest.mihomo_release.asset)：$zipPath"
        }
        $actual = Get-Sha256 $assetPath
        if ($actual -ne $mihomoHash) {
            throw "mihomo.exe 哈希不匹配：期望 $mihomoHash，实际 $actual"
        }
        Copy-Item -LiteralPath $assetPath -Destination $mihomoTarget -Force
        Write-Host 'mihomo.exe：已写入 bin\mihomo.exe 并校验通过。'
    } finally {
        if (Test-Path -LiteralPath $extractDir) { Remove-Item -LiteralPath $extractDir -Recurse -Force }
    }
}

# --- FlClashMihomoService.exe ---
$serviceTarget = Join-Path $binDir 'FlClashMihomoService.exe'
$serviceHash = $targets[1].Hash
if ((Test-Ready $serviceTarget $serviceHash) -and -not $Force) {
    Write-Host 'FlClashMihomoService.exe：已存在且哈希一致，跳过。'
} else {
    if (-not (Test-Path -LiteralPath $ServiceExePath)) {
        throw ("找不到 FlClashMihomoService.exe（默认位置：{0}）。请先安装 FlClash 服务，" -f $ServiceExePath) +
              '或用 -ServiceExePath 指定文件，例如从历史发布包的 bin/ 目录提取。'
    }
    $actual = Get-Sha256 $ServiceExePath
    if ($actual -ne $serviceHash) {
        throw "FlClashMihomoService.exe 哈希不匹配：期望 $serviceHash，实际 $actual（来源：$ServiceExePath）"
    }
    Copy-Item -LiteralPath $ServiceExePath -Destination $serviceTarget -Force
    Write-Host 'FlClashMihomoService.exe：已写入 bin\FlClashMihomoService.exe 并校验通过。'
}

# --- 最终复核 ---
$summary = foreach ($target in $targets) {
    $path = Join-Path $binDir $target.Name
    if (-not (Test-Ready $path $target.Hash)) { throw "最终校验失败：$($target.Name)" }
    '{0}  {1}' -f $target.Hash, $target.Name
}
Write-Host '两个二进制均已就绪：'
$summary | ForEach-Object { Write-Host ('  ' + $_) }

