import requests, json, datetime as dt, time
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36", "Accept": "application/json, text/plain, */*"}
print("台北", dt.datetime.utcnow() + dt.timedelta(hours=8))
def show(k, f):
    try: print("==", k, "|", f())
    except Exception as e: print("==", k, "| 失敗", type(e).__name__, str(e)[:150])
# 1. CME 官網（黃金 437、ES 133）
for pid, nm in [(437, "黃金"), (133, "S&P ES")]:
    def f(pid=pid):
        r = requests.get(f"https://www.cmegroup.com/CmeWS/mvc/quotes/v2/{pid}?isProtected&_t={int(time.time()*1000)}", headers={**H, "Referer": "https://www.cmegroup.com/"}, timeout=20)
        if r.status_code != 200: return f"HTTP {r.status_code}"
        q = r.json()["quotes"][0]; return f"{q.get('expirationMonth')} 最新 {q.get('last')} 時間 {q.get('updated')} | 整體更新 {r.json().get('tradeDate')}"
    show(f"CME 官網 {nm}", f)
# 2. TradingView 掃描器（公開 JSON）
def tv():
    body = {"symbols": {"tickers": ["COMEX:GC1!", "CME_MINI:ES1!", "CME:6E1!", "CBOT:ZC1!", "NYMEX:CL1!"]}, "columns": ["close", "update_mode", "time"]}
    r = requests.post("https://scanner.tradingview.com/futures/scan", json=body, headers=H, timeout=20)
    if r.status_code != 200: return f"HTTP {r.status_code} {r.text[:100]}"
    return "; ".join(f"{d['s']} {d['d']}" for d in r.json()["data"])
show("TradingView", tv)
# 3. 期交所 MIS：你實際下單的 GDF、XEF 等
def mis():
    out = []
    for kind in ("6", "7"):
        L = requests.post("https://mis.taifex.com.tw/futures/api/getQuoteList", headers={**H, "Content-Type": "application/json"}, timeout=15,
            json={"MarketType": "1", "SymbolType": "F", "KindID": kind, "CID": "", "ExpireMonth": "", "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}).json()["RtData"]["QuoteList"]
        for x in L[:12]:
            if x["SymbolID"][-2:] in ("-F", "-M"): out.append(f"{x['DispCName']} 成交{x['CLastPrice']}@{x['CTime']} 買{x['CBestBidPrice']}/賣{x['CBestAskPrice']}")
    return " | ".join(out[:8])
show("期交所 MIS 夜盤（外匯/黃金）", mis)
