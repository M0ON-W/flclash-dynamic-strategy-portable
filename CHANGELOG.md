# 变更记录

记录本项目的显著变更。格式参考 Keep a Changelog，版本号与 `manifest.json` 保持一致。

## [未发布]

### 新增

- Netflix 专用出口组 `__Netflix` 与 `__managed-netflix` 规则集：播放出现空档时按 7 天/24 小时在线率、探测延迟与 4 小时冷却重新钉选出口，通过两个控制器同时生效（提交 af5c509）。
- Google 旁路只读观察器纳入版本管理：`src/google_observer.py`、`scripts/Install-GoogleObserver.ps1`、`scripts/Uninstall-GoogleObserver.ps1`、`tests/test_google_observer.py`、`docs/google-observer.md`。
- `scripts/Update-Checksums.ps1` 重新生成 `SHA256SUMS.txt`。
- `.github/workflows/tests.yml` 在 windows-latest 上运行单元测试。
- `AGENTS.md` 记录真源、私有数据与线上改动的约定。

### 变更

- 工作区整理为正式仓库：`src/` 为唯一真源，私有与本机内容移入被忽略的 `_local/`，发布说明移入 `docs/releases/`，配置样例移入 `assets/`（提交 86d9d91）。
- `README.md` 重写为面向维护的说明；维护文档统一为简体中文，历史发布说明保持原文。
- 直接路由新增 `DIRECT_DOMAINS`（`maitokens.top`、`maitokens.com`），使用国内 DoH 解析并排除 fake-IP。

### 修复

- 观察器安装脚本改为从 `src/` 取源文件，修正目录整理后找不到文件的问题。
- 单元测试在 `src/` 布局下可通过 `tests/conftest.py` 正确导入模块（此前发布版仓库的测试无法直接运行）。

## [1.0.1] - 2026-08-27

对应提交 afc9189（未打标签，发布说明见 `docs/releases/RELEASE_NOTES_v1.0.1.md`）。

- 新增扫描质量闸门，拒绝低在线率或受管策略组归零的候选。
- 保存完整非空的最优可用策略快照，移除不同服务组之间的空组填充。
- Google 候选改为搜索、GStatic、账号页与 Gemini 多端点检测，要求连续通过并优先采用相同出口 IP 的主备节点。
- 全新安装使用非空引导组完成首次扫描，严格净节点会自动加入 Google 验证池。
- Google 或 OpenAI 连接活跃时暂缓热加载；手动安全套用仍可逐组验证并在失败时完整回滚。
- DNS 不再注入合成 ECS；FlClash DNS 覆盖保持关闭，受管脚本与两个核心使用一致的规则感知 DNS。
- 新增不含真实节点、订阅或出口数据的单元测试。

## [1.0.0] - 2026-08-23

对应标签 `v1.0.0`（提交 7f5e3c9），发布说明见 `docs/releases/RELEASE_NOTES_v1.0.0.md`。

- 首次公开版本，提供可跨 Windows 电脑部署的 FlClash 三组动态策略系统。
- 自动维护 `净选`、`稳净`、`极速`。
- 自动建立并更新 Google/Gemini 地区可用出口池。
- 每 20 分钟执行节点检测，策略组每 10 分钟健康检查。
- 独立 Mihomo TUN Windows 服务与 DNS 防泄漏配置。
- `稳净` 使用 7 天滚动历史，至少 3 天、216 个样本后成熟。
- 包含安装前检查、备份、安全热重载、验收和恢复脚本。
- 不包含任何订阅、代理凭据、真实节点名单或原电脑历史数据。
