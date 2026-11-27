import requests, json, datetime as dt, time
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}
print("台北", dt.datetime.utcnow() + dt.timedelta(hours=8))
def show(k, f):
    try: print("==", k, "|", f())
    except Exception as e: print("==", k, "| 失敗", type(e).__name__, str(e)[:200])
def j10_flash():
    r = requests.get("https://flash-api.jin10.com/get_flash_list", params={"channel": "-8200", "vip": "1"},
                     headers={**H, "x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0", "Origin": "https://www.jin10.com", "Referer": "https://www.jin10.com/"}, timeout=20)
    d = r.json().get("data", [])
    return f"HTTP {r.status_code} 筆數 {len(d)} | " + " / ".join(f"{x.get('time')} {str(x.get('data',{}).get('content',''))[:40]}" for x in d[:4])
show("金十 快訊", j10_flash)
def j10_oil():
    r = requests.get("https://flash-api.jin10.com/get_flash_list", params={"channel": "-8200", "vip": "1", "classify": "[13]"},
                     headers={**H, "x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0", "Origin": "https://www.jin10.com", "Referer": "https://www.jin10.com/"}, timeout=20)
    d = r.json().get("data", []); oil = [x for x in d if "原油" in str(x.get("data", {}).get("content", ""))]
    return f"HTTP {r.status_code} 含『原油』{len(oil)} 筆 | " + " / ".join(f"{x.get('time')} {str(x['data']['content'])[:50]}" for x in oil[:3])
show("金十 原油相關", j10_oil)
def j10_cal():
    today = (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d")
    r = requests.get("https://e0430d16720e4211b5e072c26205c890.z3c.jin10.com/get/data", params={"date": today},
                     headers={**H, "x-app-id": "sKKYe29sFuJaeOCJ", "x-version": "2.0", "Origin": "https://rili.jin10.com", "Referer": "https://rili.jin10.com/"}, timeout=20)
    d = r.json().get("data", [])
    return f"HTTP {r.status_code} 筆數 {len(d)} | " + " / ".join(f"{x.get('pub_time','')} {x.get('country','')}{x.get('name','')}" for x in d[:4])
show("金十 財經日曆", j10_cal)
def cot():
    r = requests.get("https://publicreporting.cftc.gov/resource/72hh-3qpy.json",
                     params={"$where": "cftc_contract_market_code='067651'", "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 2}, timeout=30)
    d = r.json(); x = d[0]
    return f"HTTP {r.status_code} 最新 {x['report_date_as_yyyy_mm_dd'][:10]} 管理基金 多 {x.get('m_money_positions_long_all')} 空 {x.get('m_money_positions_short_all')} | 生產商 多 {x.get('prod_merc_positions_long')} 空 {x.get('prod_merc_positions_short')}"
show("CFTC COT 原油（官方）", cot)
def curve():
    import yfinance as yf
    out = []
    for s in ["CL=F", "CLF27.NYM", "CLG27.NYM", "CLH27.NYM", "CLZ27.NYM"]:
        d = yf.Ticker(s).history(period="5d", interval="1d")
        out.append(f"{s} {d.Close.iloc[-1]:.2f}@{d.index[-1].date()}" if len(d) else f"{s} 無")
    return " | ".join(out)
show("原油期限結構（Yahoo 各月份）", curve)
def eia():
    r = requests.get("https://ir.eia.gov/wpsr/table1.csv", headers=H, timeout=20)
    return f"HTTP {r.status_code} | {r.text[:200]!r}"
show("EIA 週報 CSV", eia)
