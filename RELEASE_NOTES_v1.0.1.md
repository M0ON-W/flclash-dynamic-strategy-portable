# v1.0.1

## 中文

- 新增掃描品質閘門，拒絕低在線率或受管策略組歸零的候選。
- 保存完整非空的最後可用策略快照，移除不同服務組之間的空組填充。
- Google 候選改為搜尋、GStatic、帳號頁與 Gemini 多端點檢測，要求連續通過並優先採用相同出口 IP 的主備節點。
- 全新安裝使用非空引導組完成首次掃描，嚴格淨節點會自動加入 Google 驗證池。
- Google 或 OpenAI 連接活躍時暫緩熱加載；手動安全套用仍可逐組驗證並在失敗時完整回復。
- DNS 不再注入合成 ECS；FlClash DNS 覆蓋保持關閉，受管腳本與兩個核心使用一致的規則感知 DNS。
- 新增不含真實節點、訂閱或出口資料的單元測試。

## English

- Adds a scan-quality gate that rejects low-availability or zero-member candidates.
- Saves a complete non-empty last-known-good snapshot and removes cross-service empty-group filling.
- Validates Google candidates against Search, GStatic, Google Accounts, and Gemini, requires consecutive passes, and prefers same-exit-IP primary and standby nodes.
- Uses non-empty bootstrap groups for the first scan and automatically adds strict-clean nodes to the Google validation pool.
- Defers hot reloads while Google or OpenAI connections are active; manual safe apply still verifies each group and performs a complete rollback on failure.
- Removes synthetic ECS injection and keeps FlClash DNS override disabled so both cores use the same rule-aware managed DNS.
- Adds unit tests containing no real node, subscription, or exit data.
