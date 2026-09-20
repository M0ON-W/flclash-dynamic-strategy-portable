# 项目状态

> 本文件是项目状态的动态入口：每次部署、配置改动、发版或线上状态明显变化后都要更新。
> 更新规则见文末；只写核实过的事实，并附上取数命令与时间。

- 最后更新：2026-09-20（本机核对时间 15:30）
- 当前版本：v1.0.1（`manifest.json`）
- 仓库：`D:\Codex\flclash修改`，origin `https://github.com/M0ON-W/flclash-dynamic-strategy-portable`

## 仓库状态

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| 分支与同步 | `main` 本地领先 origin 6 个提交（整理与修复，尚未推送） | `git rev-list --left-right --count origin/main...main` |
| 工作区 | 干净 | `git status --short` 无输出 |
| 单元测试 | 22 个用例全部通过 | `python -m pytest tests -q` |
| 校验值 | `SHA256SUMS.txt` 62 条全部匹配 | 逐条重算 SHA-256，0 处不符 |
| 脚本编码 | `scripts/*.ps1` 均为 UTF-8 with BOM，PowerShell 5.1 与 7 均可解析 | 两个引擎下 `parseErrors=0` |
| 版本库体积 | 打包 25.05 MiB，其中 `bin/mihomo.exe`（50 MB）与 `bin/FlClashMihomoService.exe`（18 MB）占绝大部分 | `git count-objects -vH`、`git verify-pack` |

## 本机运行状态（2026-09-20 15:30 核对）

| 组件 | 状态 | 证据 |
| --- | --- | --- |
| FlClash 核心 | 运行中，控制器 `127.0.0.1:9090` 在线 | `Get-Process FlClash`、`latest_status.json.controller_online=true` |
| 独立 Mihomo | 进程与服务均运行，`FlClashMihomoService` 自动启动 | `Get-Process mihomo`、`Get-Service FlClashMihomoService` |
| 策略排程 | `FlClash-Strategy-20min` 最近一次 15:28 成功（结果 0） | `Get-ScheduledTaskInfo` |
| 提权排程 | `FlClash-Elevated-AtLogon` 正在运行 | `Get-ScheduledTask` |
| 观察器排程 | `FlClash-Google-Observer-20min` 最近一次 15:15 成功（结果 0） | `Get-ScheduledTaskInfo` |
| 当前节点规模 | 候选 56 个，在线 25 个（门槛 12），严格洁净 1 个 | `managed\latest_status.json` |
| 策略组人数 | 净选 1、稳净 1、极速 19 | `managed\latest_status.json.groups` |
| 稳净成熟度 | 样本 100%、成熟节点 48，仍标记 `provisional=true` | `managed\latest_status.json.stable_progress` |
| 本次应用 | 已延后：存在活跃 Google/OpenAI 连接，运行态未热加载 | `latest_status.json.apply.reason` |

## 观察器状态（只读，不改真实流量）

| 指标 | 值（2026-09-20 15:29） |
| --- | --- |
| 协议 | `google-observer-v1` |
| 有效轮次 | 549 |
| 最大中断 | 124724 秒（约 34.6 小时） |
| 独立出口数 | 42 |
| 公共池 / 严格池 | 0 / 0 |
| `observation_complete` | false |
| `atomic_switch_ready` | false |
| `real_traffic_unchanged` | true |

证据：`managed\google-observer\report.json`。观察器只产出候选报告，是否切换真实 Google 流量必须人工授权。

## 已知问题与待核实

- 观察器存在约 34.6 小时的最大中断，完整性门槛未达成；`public_pool_count` 与 `strict_pool_count` 仍为 0，尚无可切换的严格出口。需核实中断原因（任务未触发、机器休眠，或监听端口不可用）。
- `稳净` 仍为暂定状态（`provisional=true`），默认 MATCH 仍走 `极速`；成熟条件见 `docs/技術架構.md`。
- 本机 `managed\` 下存在旧文件 `strategy_manager.py.bak-openai-websocket` 与 `netflix-probe.yaml`，未清理；确认无用后再删除。
- Netflix 专用组依赖 `NETFLIX_PIN_PATTERNS` 匹配的固定线路，订阅变更后需要复核候选是否仍存在。

## 下一步

- 把整理后的仓库推送到 origin，并决定是否对 `bin/` 大文件做历史瘦身。
- 观察器中断原因核实后，再评估是否重新累积观察窗口。
- 视需要为 Netflix 固定出口与仓库整理打一个发布标签，并在 `docs/releases/` 补发布说明。

## 更新规则

1. 任何部署（`python src\strategy_manager.py --install`）、策略改动、订阅更换、发版或线上状态明显变化后，更新「最后更新」时间和相关表格行。
2. 只写当场核实过的事实，并在「证据」列写清取数命令或文件路径；不确定的内容放进「已知问题与待核实」。
3. 不在本文件写订阅地址、节点凭据、出口 IP、账号信息；观察器出口一律用其 HMAC 标识描述。
4. 改动本文件后运行 `python -m pytest tests -q` 与 `scripts\Update-Checksums.ps1`，保持测试与校验值同步。

