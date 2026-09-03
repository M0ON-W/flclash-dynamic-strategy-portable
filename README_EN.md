# FlClash Dynamic Strategy Portable Package

[中文說明](README.md)

This package reproduces the FlClash dynamic-routing project on a compatible Windows computer without copying subscriptions, proxy credentials, node names, or historical measurements from the original machine.

## Features

- Three visible Chinese policy groups: `净选` (clean), `稳净` (stable and clean), and `极速` (fast).
- Hidden AI egress groups (`__谷歌AI` and `__OpenAI`). Google candidates are filtered for regional redirects; when a dedicated pool is temporarily empty or stale, it falls back to `极速` so ordinary routing remains available.
- Granular rule-provider routing via MetaCubeX MRS: AI & Google through clean groups, Microsoft/Apple China & Chinese domestic services (WeChat, Bilibili, Taobao) DIRECT, and international traffic through Fast.
- Rule-aware DNS routing: external DoH uses the selected proxy, while domestic domains use AliDNS DoH through `极速`; no system DNS upstream is used.
- Parallel node availability, service compatibility, latency, short-throughput, and egress-risk checks every 20 minutes.
- Bounded-parallel 1 MiB throughput measurements for Google/Gemini candidates, with two consecutive validation passes and same-exit-IP standby preference.
- A scan-quality gate rejects low-availability or empty required groups. Failed candidate reloads restore runtime configuration, state, DNS preferences, and the override script together.
- A seven-day rolling history; `稳净` requires at least 216 samples over three days before becoming mature.
- Fake-IP DNS, DoH upstreams, rule-aware DNS routing, disabled IPv6, and TUN interception of TCP/UDP port 53.
- Bilibili web, API, image, and video CDN domains are pinned to DIRECT and excluded from fake-IP; verification checks both the proxy entry and independent TUN access.
- An independent LocalSystem Mihomo service with automatic startup, failure recovery, and its own `MihomoSvc` TUN adapter.
- Hidden `pythonw.exe` scheduled execution with no recurring terminal windows.
- Preflight validation, installation backup, runtime verification, safe configuration reload, and explicit restoration tooling.

## Requirements

- Windows 10 or 11, x64.
- FlClash with an active profile containing inline `proxies` entries.
- FlClash running locally with its controller available on `127.0.0.1:9090` during installation.
- Python 3.10 or newer.
- Administrator privileges for the installer.

Validated with FlClash `0.8.96+2026081701`, Mihomo `1.19.30`, WinSW `2.12.0`, and PyYAML `6.0.3`. The preflight script refuses to modify an incompatible FlClash database layout.

## Install

Keep FlClash running and leave FlClash's own TUN/virtual-adapter switch off. Open an elevated PowerShell window in the extracted package directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Install.ps1 -ReplaceExistingOverrides
```

The explicit switch acknowledges that existing FlClash script, rule, and policy-group overrides will be replaced. A local backup is created before modification.

## Verify

```powershell
.\scripts\Verify.ps1
```

## Restore

Restoration stops the independent TUN and can temporarily interrupt networking. Exit FlClash manually first, then run:

```powershell
.\scripts\Restore-Previous.ps1 -ConfirmRestore
```

## Scope of the result

The package reproduces the detection, history, ranking, routing, and failover system. It cannot make a provider node permanently clean, force advertised bandwidth, or reproduce identical rankings on a different computer or network. Every target machine builds its own measurements and Gemini candidate pool.
