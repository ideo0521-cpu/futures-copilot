# 期貨副駕｜雲端看盤網頁

GitHub Actions 每 5 分鐘執行 `monitor.py`，輸出 `docs/index.html`（GitHub Pages）。

- 趨勢系統（39 檔，含台指期夜盤）：4 條長週期規則 ≥3 條同向進場、固定 3N 停損、同向 <3 出場
- 期限結構系統（19 檔能源／金屬／農產品）：主力月比次月貴 → 多、便宜 → 空；每日前向紀錄在 `state.json`
- 每個合約（CME 標準、CME 微型、期交所）列出進場參考、停損、每口停損虧損、歷史平均／最大／最差／勝率（`stats.json`）
- 報價：Yahoo 為主、TradingView 第二來源、鉅亨第三來源（ES/NQ/YM）；台指期與期交所商品用期交所 MIS
- 背景資訊（不參與訊號）：金十快訊、CFTC 持倉、EIA 原油庫存、三大法人
- 手機通知：Secrets 加 `NTFY_TOPIC` 才會在訊號變化時推播（目前關閉）
