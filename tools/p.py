import requests, re, datetime as dt, json
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"}
print("台北", (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%m/%d %H:%M:%S"))
import yfinance as yf
for s in ["ES=F", "NQ=F", "YM=F", "CL=F", "GC=F"]:
    d = yf.Ticker(s).history(period="1d", interval="1m")
    dd = yf.Ticker(s).history(period="5d", interval="1d")
    print("Yahoo", s, "分鐘", (d.index[-1].strftime("%m/%d %H:%M %Z"), round(float(d.Close.iloc[-1]), 2)) if len(d) else None, "日K", round(float(dd.Close.iloc[-1]), 2))
for nm, u in [("鉅亨 indexftr", "https://www.cnyes.com/futures/indexftr.aspx"), ("鉅亨 indexftr2", "https://www.cnyes.com/futures/indexftr"),
              ("富途 美股期貨", "https://www.futunn.com/futures-us/equity-index"), ("富途 能源", "https://www.futunn.com/futures-us/energy")]:
    try:
        r = requests.get(u, headers=H, timeout=25); t = r.text
        print(f"== {nm} HTTP {r.status_code} {len(t)}字 擋={('Just a moment' in t) or ('captcha' in t.lower())}")
        for kw in ["S&P", "標普", "道瓊", "原油", "納斯達克", "E-Mini"]:
            for m in list(re.finditer(re.escape(kw), t))[:2]:
                print("  ", kw, "→", re.sub(r"<[^>]+>|\s+", " ", t[m.start():m.start()+200])[:150])
        tm = re.findall(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", re.sub(r"<script.*?</script>", "", t, flags=re.S))
        print("   時間樣本", sorted(set(tm))[-5:])
    except Exception as e: print("==", nm, "失敗", e)
