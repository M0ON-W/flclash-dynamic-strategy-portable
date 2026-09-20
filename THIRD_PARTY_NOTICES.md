# 第三方声明

本仓库不包含 FlClash 本体或任何订阅数据。可移植包需要以下第三方二进制，它们不进入版本库，
由 `scripts/Fetch-Binaries.ps1` 按 `manifest.json` 中的哈希取回后放入 `bin/`。

## Mihomo

- 项目：MetaCubeX/mihomo
- 版本：1.19.30，Windows amd64，带 gVisor
- 源码：https://github.com/MetaCubeX/mihomo
- 发行页：https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.30
- 下载资产：`mihomo-windows-amd64-v1.19.30.zip` 中的 `mihomo-windows-amd64.exe`
- 许可证：GNU General Public License v3.0 or later
- 许可证副本：`licenses/mihomo-GPL-3.0.txt`
- 发行包 SHA-256：`22C09FD67673895EF7CD6B1820563918275C3D316F2462B306208675118DB3C0`
- 解压后可执行文件 SHA-256：`F55B3028D9160BEB9044F21B05DD7405B46524614A19642D6291492F5F985761`

## WinSW

- 项目：winsw/winsw
- 版本：2.12.0，x64
- 源码：https://github.com/winsw/winsw
- 发行页：https://github.com/winsw/winsw/releases/tag/v2.12.0
- 许可证：MIT
- 许可证副本：`licenses/WinSW-MIT.txt`
- 可执行文件 SHA-256：`05B82D46AD331CC16BDC00DE5C6332C1EF818DF8CEEFCD49C726553209B3A0DA`

WinSW 二进制在本项目中重命名为 `FlClashMihomoService.exe`，以配合同名 XML 服务配置；
哈希与上游发行文件一致，因此也可以直接从本机已安装的 FlClash 服务目录复制。

