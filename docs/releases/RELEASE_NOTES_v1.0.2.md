# v1.0.2

## 中文

- 仓库整理为可长期维护的结构：`src/` 为唯一真源，`tests/` 在 `src/` 布局下可直接运行，私有与本机内容移入被忽略的 `_local/`。
- 新增 Netflix 专用出口组 `__Netflix`：固定线路筛选，播放空档时按 7 天/24 小时在线率、探测延迟与 4 小时冷却重钉出口，通过两个控制器同时生效。
- `maitokens.top` 与 `maitokens.com` 改为直连并使用国内 DoH 解析；Google 严格池排除指定节点。
- 新增只读 Google 观察器子系统的文档、安装脚本与用例（不在本版本切换真实流量）。
- 修复 PowerShell 脚本编码：全部改为 UTF-8 with BOM，Windows PowerShell 5.1 下可正常解析执行。
- 从仓库与历史中移除 `bin/mihomo.exe` 与 `bin/FlClashMihomoService.exe`（合计约 68 MB），改用 `scripts/Fetch-Binaries.ps1` 按哈希取回。
- 新增 `PROJECT_STATUS.md` 作为项目状态的动态入口，`CHANGELOG.md` 记录版本变更。

## English

- Restructured the repository for long-term maintenance: `src/` is the single source of truth, the test suite runs directly against that layout, and private machine data moved into the gitignored `_local/`.
- Added the hidden `__Netflix` group: pinned upstream lines, gap-triggered repin gated by 7-day/24-hour online rates, probe latency and a four-hour cooldown, applied on both controllers.
- `maitokens.top` and `maitokens.com` now resolve directly through domestic DoH; the Google strict pool excludes a designated node.
- Added the read-only Google observer subsystem documentation, installer and tests (no real-traffic switch in this release).
- Fixed PowerShell encoding: every script is UTF-8 with BOM and parses under Windows PowerShell 5.1.
- Removed `bin/mihomo.exe` and `bin/FlClashMihomoService.exe` from the working tree and history (~68 MB) in favour of `scripts/Fetch-Binaries.ps1`, which verifies SHA-256 against `manifest.json`.
- Added `PROJECT_STATUS.md` as the living status entry point and `CHANGELOG.md` for release history.
