# v1.0.0

## 中文

首次公開版本，提供可跨 Windows 電腦部署的 FlClash 三組動態策略系統。

- 自動維護 `净选`、`稳净`、`极速`。
- 自動建立並更新 Google/Gemini 地區可用出口池。
- 每 20 分鐘執行節點檢測，策略組每 10 分鐘健康檢查。
- 獨立 Mihomo TUN Windows 服務與 DNS 防洩漏配置。
- `稳净`使用 7 天滾動歷史，至少 3 天、216 個樣本後成熟。
- 包含安裝前檢查、備份、安全熱重載、驗收和回復腳本。
- 不包含任何訂閱、代理憑據、真實節點名單或原電腦歷史資料。

## English

Initial public release of the portable FlClash three-group dynamic-routing system for Windows.

- Automatically maintains `净选`, `稳净`, and `极速`.
- Automatically discovers and updates a region-compatible Google/Gemini egress pool.
- Runs node scans every 20 minutes and group health checks every 10 minutes.
- Includes an independent Mihomo TUN Windows service and DNS leak controls.
- Builds a seven-day rolling history; `稳净` matures after at least 216 samples over three days.
- Includes preflight validation, backup, safe hot reload, verification, and restoration tools.
- Contains no subscriptions, proxy credentials, real node lists, or measurements from the source computer.

The release ZIP contains bundled Mihomo and WinSW binaries with upstream source links, exact hashes, and license copies in `THIRD_PARTY_NOTICES.md`.
