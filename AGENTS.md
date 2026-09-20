# 仓库约定

本仓库管理一套运行在 Windows 上的 FlClash + 独立 Mihomo 动态策略系统。以下约定用于长期维护，改动前先读一遍。

## 真源与产物

- `src/strategy_manager.py`、`src/google_observer.py` 是唯一真源。
- `%APPDATA%\com.follow\clash\managed\` 下的同名文件是部署产物，不要直接改；改完源码后用
  `python src\strategy_manager.py --install` 重新部署。
- 修改后至少运行 `python -m pytest tests -q`，保持全部用例通过。

## 私有数据边界

- `_local/` 已被 .gitignore 忽略，里面是本机私有内容（运行备份、私有 profile、历史发布包、二进制暂存、临时脚本）。
- 禁止把订阅地址、节点凭证、`state.json`、`config.yaml`、观察器运行数据提交进仓库。
- 提交前确认 `git status --short` 不出现 `_local/`，也不要使用会强行加入忽略文件的参数。

## 状态文件

- `PROJECT_STATUS.md` 是项目状态的动态入口。部署、策略或配置改动、发版、线上状态明显变化后必须更新。
- 每条状态写清证据（取数命令或文件路径）与核对时间；不确定的内容放进「已知问题与待核实」。
- 不得在其中写入订阅地址、节点凭据、出口 IP 或账号信息。

## 改动线上环境

- 重启 FlClash、Mihomo 服务或切换真实流量属于会中断网络的改动，先说明再执行。
- 读取实时状态时区分三件事：持久化配置、FlClash 运行时（`127.0.0.1:9090`）、独立 Mihomo 运行时（`127.0.0.1:19090`）。`pending_runtime_apply` 只表示待应用。
- 报告状态时用实际证据（控制器返回、日志、文件哈希），不要用「任务已启动」代替「已生效」。

## 文档与语言

- 文档使用简体中文，路径、命令、配置名保持英文原文。
- 提交信息使用英文祈使句（`feat:`、`fix:`、`chore:`、`docs:`）。

## 脚本编码

- `.ps1` 文件必须保存为 UTF-8 with BOM。Windows PowerShell 5.1 会把无 BOM 的 UTF-8 当成 ANSI 读取，含中文的脚本会直接报语法错误。
- Python 文件保持 UTF-8（无需 BOM）。
