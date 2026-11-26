# 期貨副駕｜雲端盯盤

每 5 分鐘由 GitHub Actions 執行 `monitor.py`：
- 39 檔期貨（含台指期夜盤）長週期趨勢規則：4 條規則 ≥3 條同向進場、固定 3N 停損、同向 <3 出場
- 有「新機會／該平倉」→ 推播到 ntfy（變數 `NTFY_TOPIC`）
- 每次更新 `docs/index.html` → GitHub Pages 手機網頁

可調整的變數（Settings → Secrets and variables → Actions → Variables）：
`CAPITAL`（台幣資金，預設 1000000）、`RISK_PCT`（每筆風險 %，預設 1）、`TOTAL_RISK_PCT`（總風險上限 %，預設 5）；手機通知頻道放在 Secrets 的 `NTFY_TOPIC`（不公開）
