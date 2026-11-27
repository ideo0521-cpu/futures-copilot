import requests, re, datetime as dt
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"}
print("UTC", dt.datetime.utcnow(), "台北", dt.datetime.utcnow() + dt.timedelta(hours=8))
urls = {
 "StockQ 商品": "https://www.stockq.org/market/commodity.php",
 "StockQ 期指": "https://www.stockq.org/market/futures.php",
 "鉅亨 國際期指頁": "https://www.cnyes.com/futures/index.htm",
 "鉅亨 API 黃金": "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/GF:GC%23%23:FUTURES",
 "Investing 期貨頁": "https://www.investing.com/indices/us-spx-500-futures",
 "Investing 中文": "https://hk.investing.com/commodities/gold",
 "AASTOCKS": "http://www.aastocks.com/tc/stocks/market/index/hk-index-con.aspx",
}
for k, u in urls.items():
    try:
        r = requests.get(u, headers=H, timeout=20)
        t = r.text
        times = re.findall(r"(?:20\d\d[/-]\d{1,2}[/-]\d{1,2}\s*)?\b[0-2]?\d:[0-5]\d(?::[0-5]\d)?\b", t)
        print(f"== {k} | HTTP {r.status_code} | {len(t)} 字 | 擋機器人跡象: {'cloudflare' in t.lower() or 'captcha' in t.lower() or 'Just a moment' in t}")
        print("   時間樣本:", sorted(set(times))[-6:])
        for kw in ["黃金", "S&P", "標普", "原油", "Gold", "延遲", "delay", "Delayed"]:
            i = t.find(kw)
            if i >= 0: print("  ", kw, "→", re.sub(r"<[^>]+>|\s+", " ", t[i:i+220])[:160]); break
    except Exception as e:
        print(f"== {k} | 失敗 {type(e).__name__} {e}")
