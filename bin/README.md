# bin/ 目录

这里存放可移植包需要的两个二进制，它们**不进入版本库**（已从 Git 历史中移除，见 CHANGELOG v1.0.2），
下载或复制后用 `manifest.json` 中 `binary_sha256` 的值校验：

| 文件 | 来源 | SHA-256（见 manifest.json） |
| --- | --- | --- |
| `mihomo.exe` | MetaCubeX mihomo `1.19.30` 官方发行包 `mihomo-windows-amd64-v1.19.30.zip`，解压其中的 `mihomo-windows-amd64.exe` | `F55B3028…85761` |
| `FlClashMihomoService.exe` | 本机已安装的 FlClash 服务目录（默认 `%ProgramData%\FlClashMihomoService\FlClashMihomoService.exe`） | `05B82D46…B3A0DA` |

取回方式：

```powershell
.\scripts\Fetch-Binaries.ps1
.\scripts\Fetch-Binaries.ps1 -MihomoZip D:\downloads\mihomo-windows-amd64-v1.19.30.zip   # 离线
.\scripts\Fetch-Binaries.ps1 -ServiceExePath 'D:\path\FlClashMihomoService.exe'          # 指定来源
```

脚本会逐个校验哈希，任何不匹配都会报错退出；许可证见 `licenses/`。

