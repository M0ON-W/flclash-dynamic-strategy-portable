# FlClash 动态策略系统

在 Windows 上为 FlClash 自动维护 `净选`、`稳净`、`极速` 三个中文策略组，并额外维护隐藏的 Google/Gemini、OpenAI、Netflix 专用出口池；配合独立 Mihomo TUN 服务、防泄漏 DNS 与 20 分钟静默排程，安装完成后不依赖 Codex 运行。

本目录就是该项目的 Git 仓库（origin: `https://github.com/M0ON-W/flclash-dynamic-strategy-portable`），既包含可移植安装包的内容，也包含本机实时运行的管理器、观察器与运维文档。

## 目录结构

| 路径 | 作用 |
| --- | --- |
| `src/strategy_manager.py` | 主程序。唯一真源，本机运行的版本由它部署而来 |
| `src/google_observer.py` | Google 旁路只读观察器，导入 `strategy_manager` 复用常量与控制器调用 |
| `tests/` | 单元测试，`conftest.py` 负责把 `src/` 加入导入路径 |
| `scripts/` | 安装、验收、回滚、运行时校验，以及 Google 观察器的安装/卸载脚本 |
| `docs/` | 架构、安装迁移、项目总结、观察器说明、历史发布说明 |
| `egern/` | 手机端 Egern 三组策略移植、模块与校验脚本 |
| `assets/` | 早期产出的配置样例（Shadowrocket 三组扩展、覆写脚本预览） |
| `bin/`, `licenses/` | 可移植包自带的 mihomo 与 WinSW 二进制及其许可证 |
| `_local/` | 私有区，已被 .gitignore 忽略：运行备份、私有 profile、历史发布包、二进制暂存、临时脚本 |

`_local/` 的存在是为了让「公开内容」和「本机私有内容」在同一条路径下互不干扰。发布或推送前确认 `git status --short` 中不出现 `_local/`。

## 本机运行的系统

| 组件 | 位置 |
| --- | --- |
| 部署的管理器 | `%APPDATA%\com.follow\clash\managed\strategy_manager.py` |
| 观察器 | `%APPDATA%\com.follow\clash\managed\google-observer\google_observer.py` |
| 状态与日志 | `managed\state.json`、`managed\latest_status.json`、`managed\manager.log` |
| 定时任务 | `FlClash-Strategy-20min`（每 20 分钟执行 `--scheduled`）、`FlClash-Google-Observer-20min` |
| 控制器 | FlClash `127.0.0.1:9090`（代理 7890）、独立 Mihomo `127.0.0.1:19090`（代理 17890） |

工作约定：FlClash 自身 TUN 保持关闭，TUN 由独立 Mihomo 服务提供，避免双 TUN；`pending_runtime_apply` 之类的状态字段只代表待应用，不能当作已生效。

## 常用命令

部署（或更新）本机运行的管理器，脚本会先把自身复制到 `managed\` 再重建脚本绑定：

```powershell
python src\strategy_manager.py --install
```

其余入口参数：

```text
--scheduled            排程一次静默运行（由定时任务调用）
--force-scan           强制重新全量检测
--safe-apply           在安全窗口内应用策略
--scan-existing        只扫描现有节点
--reclassify-existing  按新规则重新分类
--service-tun-on       打开独立 Mihomo TUN
--service-tun-off      关闭独立 Mihomo TUN
```

Google 观察器（需管理员 PowerShell，只读、不切换真实流量）：

```powershell
.\scripts\Install-GoogleObserver.ps1 -StartNow
.\scripts\Uninstall-GoogleObserver.ps1            # 保留观察数据
.\scripts\Uninstall-GoogleObserver.ps1 -RemoveObservationData
```

## 开发与测试

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
```

修改代码时先把 `src/strategy_manager.py` 改好并跑通测试，再执行 `--install` 部署到本机；不要直接编辑 `managed\` 下的副本，那是产物。

## 策略组与专用出口

- `净选`：当前检测条件下最严格通过的一组出口。
- `稳净`：累积 7 天滚动历史，至少 3 天且 216 个样本后才算成熟样本，成熟前标记为暂定。
- `极速`：按延迟与短程吞吐排序的快速出口。
- `__谷歌AI`、`__OpenAI`：隐藏专用池，逐轮排除返回地区不支持页面的节点。
- `__Netflix`：只保留匹配固定美国节点模式的成员，播放出现空档时按 7 天/24 小时在线率、探测延迟和 4 小时冷却重新钉选出口。

分流依赖 `__managed-*` 系列 MRS 规则集（来源 MetaCubeX meta-rules-dat），DNS 使用 fake-IP + DoH + 规则跟随，且不使用系统 DNS 上游；Bilibili 与 `maitokens.top` / `maitokens.com` 走直连并使用国内 DoH 解析。

## 可移植包与发布

`manifest.json` 记录包版本、已验证的 FlClash/Mihomo/WinSW/Python/PyYAML 版本与二进制 SHA-256，`SHA256SUMS.txt` 给出文件清单校验值。在目标机器上以管理员身份安装与验收：

```powershell
.\scripts\Install.ps1 -ReplaceExistingOverrides
.\scripts\Verify.ps1
.\scripts\Restore-Previous.ps1 -ConfirmRestore   # 回滚（会短暂断网）
```

历史发布说明见 `docs/releases/`，变更记录见 `CHANGELOG.md`。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/技術架構.md](docs/技術架構.md) | 组结构、DNS、规则、双控制器与代码布局 |
| [docs/安裝與遷移.md](docs/安裝與遷移.md) | 在新机器上安装、迁移与验收步骤 |
| [docs/項目總結.md](docs/項目總結.md) | 项目背景与实现历程 |
| [docs/google-observer.md](docs/google-observer.md) | 观察器边界与部署方式 |
| [egern/README.md](egern/README.md) | 手机端 Egern 移植说明 |
| [README_EN.md](README_EN.md) | English introduction |

## 不保证的事项

节点出口信誉、服务风控结果、延迟与带宽会随供应商、时间和网络环境变化。本项目能复现的是「检测、累积、排序和自动切换机制」，不能让另一台机器得到完全相同的节点排名，也不能对任何节点做永久、绝对的洁净保证。

## 第三方

`licenses/` 收录 mihomo（GPL-3.0）与 WinSW（MIT）许可证；`egern/modules/` 下各模块按自身 LICENSE 分发，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

