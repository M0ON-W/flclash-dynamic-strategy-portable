# Google 旁路观察器

该观察器仅从当前正式状态读取候选及其监听端口，所有输出均写入
%APPDATA%\com.follow\clash\managed\google-observer。它不会调用控制器配置接口、
修改正式 state.json、FlClash 数据库、覆写脚本、DNS 或任何策略组。

首阶段只生成脱敏观察状态和报告。出口使用本机随机密钥生成 HMAC 标识，
报告不含节点名、出口 IP、订阅地址或账号内容。观察满 24 小时且达到完整性门槛后，
仍只产生候选报告，不会自动切换真实 Google 流量。

安装并立即启动：

```powershell
.\scripts\Install-GoogleObserver.ps1 -StartNow
```

卸载任务但保留观察数据：

```powershell
.\scripts\Uninstall-GoogleObserver.ps1
```
