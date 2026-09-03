# FlClash 三組動態策略可移植包

[中文](#中文簡介) · [English](#english-introduction) · [English README](README_EN.md)

## 中文簡介

一套適用於 Windows FlClash 的可移植動態策略系統：自動建立 `净选`、`稳净`、`极速`三個中文策略組，為 Google/Gemini 維持經地區可用性檢測的專用出口池，並透過獨立 Mihomo TUN、DNS 防洩漏及 20 分鐘靜默排程持續更新。安裝完成後不依賴 Codex。

## English Introduction

A portable dynamic-routing system for FlClash on Windows. It automatically maintains three Chinese policy groups—`净选` (clean), `稳净` (stable and clean), and `极速` (fast)—plus a region-checked Google/Gemini egress pool. An independent Mihomo TUN service, DNS leak controls, rolling history, safe rollback, and a silent 20-minute scheduler keep the system working without Codex after installation.

## 能復現的功能

- 三個中文可見策略組：`净选`、`稳净`、`极速`。
- 隱藏的專用動態組 `__谷歌AI` 與 `__OpenAI`；每輪自動排除返回「所在地區不支援」頁面的節點，並在 OpenAI 連接活躍時延後策略熱加載保護連線。
- 採用 MetaCubeX MRS 原生規則提供器實現精細分流：OpenAI 專用、Google/Gemini 潔淨分流、非 CN AI 淨選、微軟/蘋果中國區直連、國際服務極速、國內媒體與網址 (微信/Bilibili/淘寶等) 直連。
- 國內 DNS 智慧分流：國內網域使用經代理發送的 AliDNS DoH 搭配合成 ECS，兼顧 CDN 加速與隱私偽裝。
- 每 20 分鐘並行檢測節點可用性、服務相容性、延遲、短程吞吐與出口風險；策略組自身每 10 分鐘健康檢查。
- Google/Gemini 候選池從目標電腦自己的訂閱自動建立，不依賴本機預存節點；候選節點每輪依序下載 1 MiB 測速，避免多條線路同時測速互相爭搶帶寬。
- `稳净`累積 7 天滾動歷史，至少 3 天、216 個樣本後才可成為成熟樣本；成熟前自動標記為暫定。
- DNS 使用 fake-IP、DoH、規則跟隨、IPv6 關閉、TUN DNS 劫持，且不使用系統 DNS 作為上游解析來源。
- 哔哩哔哩主站、API 与视频 CDN 固定直连并排除 fake-IP；安装验收同时检查代理入口和 TUN 下的访问。
- 獨立 Mihomo 以 LocalSystem Windows 服務自動啟動；FlClash 自身的 TUN 保持關閉，避免雙 TUN。
- FlClash 關閉時，獨立服務仍可維持 TUN，並可供背景管理器繼續檢測。
- 策略腳本綁定 FlClash 配置；重新匯入或更新訂閱後，排程會重新建立策略組。

## 不能被軟體保證的事項

節點的出口信譽、服務風控結果、延遲與帶寬會隨供應商、時間和網路環境改變。因此，本項目能完整復現的是「檢測、累積、排序和自動切換機制」，不能讓另一台電腦得到完全相同的節點排名，也不能對任何節點作永久、絕對潔淨的保證。`净选`表示當前檢測條件下最嚴格通過的節點。

## 前置條件

- Windows 10/11 x64。
- 已安裝 FlClash，已匯入並選中一份含有內聯 `proxies` 節點的配置。
- FlClash 安裝時保持運行，核心控制端口為本機 `127.0.0.1:9090`。
- Python 3.10 或更高版本，且安裝中允許取得 PyYAML 6.0.3。
- 以系統管理員身分執行安裝腳本。
- 已驗證版本：FlClash `0.8.96+2026081701`、Mihomo `1.19.30`、WinSW `2.12.0`。

若 FlClash 資料庫結構不相容、配置只有 `proxy-providers` 而沒有內聯節點，安裝前檢查會拒絕繼續。

## 安裝

1. 解壓 ZIP，不要直接在壓縮檔內執行。
2. 啟動 FlClash，選中要使用的訂閱配置；保持 FlClash 自身「虛擬網卡/TUN」關閉。
3. 以系統管理員身分開啟 PowerShell，進入解壓目錄。
4. 執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\Install.ps1 -ReplaceExistingOverrides
```

`-ReplaceExistingOverrides`表示同意清除 FlClash 現有的腳本覆寫、規則覆寫和策略組覆寫。本機配置會先備份到：

```text
%APPDATA%\com.follow\clash\managed\backups\portable-時間戳
```

安裝期間不會關閉 FlClash。首次全量檢測可能需要數分鐘。

## 驗收

安裝器會自動驗收，也可隨時手動執行：

```powershell
.\scripts\Verify.ps1
```

驗收項目包括策略組、規則落點、Google 專用路由、7890 代理入口、獨立服務、TUN、虛擬網卡和靜默排程。

## 日常使用

- FlClash 使用規則模式。
- FlClash 自身「虛擬網卡/TUN」保持關閉。
- 不要手動停止 `FlClashMihomoService`。
- 正常更新或重新匯入訂閱即可；背景排程會自行恢復動態策略組。
- 無需再次執行安裝腳本，也不需要 Codex 參與。

## 回復安裝前狀態

回復會停止獨立 TUN，因此網路可能短暫中斷。先手動退出 FlClash，再以系統管理員 PowerShell 執行：

```powershell
.\scripts\Restore-Previous.ps1 -ConfirmRestore
```

回復腳本不會替你關閉 FlClash；若偵測到 FlClash 仍在運行，它會拒絕操作。

更多內容見 [docs/安裝與遷移.md](docs/安裝與遷移.md)、[docs/技術架構.md](docs/技術架構.md) 和 [docs/項目總結.md](docs/項目總結.md)。

## Egern 手機版

`egern/` 提供不依賴 Windows 或本機服務的 Egern 三組策略移植、加密分流 DNS、安全版與经审查的去广告增强版。安装、回滚、第三方许可和真机验收边界见 [egern/README.md](egern/README.md)。
