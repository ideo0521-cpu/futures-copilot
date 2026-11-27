# -*- coding: utf-8 -*-
"""期貨副駕｜雲端看盤網頁（GitHub Actions 每 5 分鐘執行，輸出 docs/index.html → GitHub Pages）
兩套互相獨立的系統：
  1. 趨勢：4 條長週期規則 ≥3 條同向 → 進場；固定 3N 停損；同向少於 3 條 → 出場
  2. 期限結構（只用在能源／金屬／農產品）：主力月比次月貴（逆價差）→ 多；比次月便宜（正價差）→ 空
每個數字都標來源、時間、是成交價還是收盤／結算價。"""
import os, json, time, math, html, re, urllib.request
import numpy as np, pandas as pd

STATE = "state.json"          # 會被提交回 GitHub：訊號紀錄、期限結構每日紀錄
CACHE = "cache.json"          # 只留在執行機器上：新聞、CFTC、EIA、法人、期限結構報價的暫存
TZ = "Asia/Taipei"
通知頻道 = os.environ.get("NTFY_TOPIC", "")
SPEC_DATE = "2026-11-28"      # 合約規格逐一對照交易所官網的日期

C = {
 "GC": ("黃金","GC=F",.10,10.0,("MGC",.10,1.0),"金屬","gold price"),
 "SI": ("白銀","SI=F",.005,25.0,("SIL",.005,5.0),"金屬","silver price"),
 "HG": ("銅","HG=F",.0005,12.5,("MHG",.0005,1.25),"金屬","copper price"),
 "ES": ("S&P500","ES=F",.25,12.5,("MES",.25,1.25),"指數","S&P 500 futures stocks"),
 "NQ": ("那斯達克","NQ=F",.25,5.0,("MNQ",.25,.5),"指數","Nasdaq 100 futures stocks"),
 "YM": ("道瓊","YM=F",1.0,5.0,("MYM",1.0,.5),"指數","Dow futures stocks"),
 "RTY":("羅素2000","RTY=F",.10,5.0,("M2K",.10,.5),"指數","Russell 2000"),
 "6E": ("歐元","6E=F",.00005,6.25,("M6E",.0001,1.25),"外匯","euro dollar"),
 "6J": ("日圓","6J=F",.0000005,6.25,("MJY",.000001,1.25),"外匯","Japanese yen"),
 "6B": ("英鎊","6B=F",.0001,6.25,("M6B",.0001,.625),"外匯","pound sterling"),
 "6A": ("澳幣","6A=F",.00005,5.0,("M6A",.0001,1.0),"外匯","australian dollar"),
 "CL": ("原油","CL=F",.01,10.0,("MCL",.01,1.0),"能源","crude oil"),
 "NG": ("天然氣","NG=F",.001,10.0,("MNG",.001,1.0),"能源","natural gas"),
 "ZC": ("玉米","ZC=F",.25,12.5,("MZC",.5,2.5),"農產品","corn futures"),
 "ZS": ("黃豆","ZS=F",.25,12.5,("MZS",.5,2.5),"農產品","soybean futures"),
 "ZW": ("小麥","ZW=F",.25,12.5,("MZW",.5,2.5),"農產品","wheat futures"),
 "ZN": ("10年美債","ZN=F",.015625,15.625,None,"公債","10-year Treasury yield"),
 "ZB": ("30年美債","ZB=F",.03125,31.25,None,"公債","30-year Treasury yield"),
 "PL": ("白金","PL=F",.1,5.0,None,"金屬","platinum price"),
 "PA": ("鈀金","PA=F",.5,50.0,None,"金屬","palladium price"),
 "DX": ("美元指數","DX-Y.NYB",.005,5.0,None,"外匯","US dollar index"),
 "ZT": ("2年美債","ZT=F",.00390625,7.8125,None,"公債","2-year Treasury yield"),
 "ZF": ("5年美債","ZF=F",.0078125,7.8125,None,"公債","5-year Treasury yield"),
 "6C": ("加幣","6C=F",.00005,5.0,("MCD",.0001,1.0),"外匯","Canadian dollar"),
 "6S": ("瑞郎","6S=F",.00005,6.25,("MSF",.0001,1.25),"外匯","Swiss franc"),
 "6M": ("墨西哥披索","6M=F",.00001,5.0,None,"外匯","Mexican peso"),
 "6N": ("紐幣","6N=F",.00005,5.0,None,"外匯","New Zealand dollar"),
 "HO": ("熱燃油","HO=F",.0001,4.2,None,"能源","heating oil diesel"),
 "HE": ("瘦肉豬","HE=F",.025,10.0,None,"農產品","lean hog futures"),
 "LE": ("活牛","LE=F",.025,10.0,None,"農產品","live cattle futures"),
 "ZL": ("黃豆油","ZL=F",.01,6.0,("MZL",.02,1.2),"農產品","soybean oil"),
 "ZM": ("黃豆粉","ZM=F",.1,10.0,("MZM",.2,2.0),"農產品","soybean meal"),
 "CT": ("棉花","CT=F",.01,5.0,None,"農產品","cotton futures"),
 "SB": ("糖","SB=F",.01,11.2,None,"農產品","sugar futures"),
 "KC": ("咖啡","KC=F",.05,18.75,None,"農產品","coffee futures"),
 "CC": ("可可","CC=F",1.0,10.0,None,"農產品","cocoa futures"),
 "NKD": ("日經225","NKD=F",5.0,25.0,None,"指數","Nikkei 225"),
 "BTC": ("比特幣","BTC=F",5.0,25.0,("MBT",5.0,.5),"加密","bitcoin price"),
 "TX": ("台指","TXF",1.0,None,None,"台指","Taiwan stock market TAIEX"),
}

_TXC = {}
def txf(period, interval):
    """台指期（近月）：日K 用 FinMind 期交所日行情（一般盤），即時價用期交所 MIS（含夜盤，約 1 分鐘內）。"""
    import requests
    if interval == "1d":
        if _TXC.get("t", 0) < time.time() - 3600:          # 日K 一小時更新一次就夠
            st_ = (pd.Timestamp.now() - pd.DateOffset(years=3, days=10)).strftime("%Y-%m-%d")
            j = requests.get("https://api.finmindtrade.com/api/v4/data", timeout=30,
                             params={"dataset": "TaiwanFuturesDaily", "data_id": "TX", "start_date": st_}).json()
            d = pd.DataFrame(j["data"])
            d = d[(d.trading_session == "position") & ~d.contract_date.str.contains("/") & (d.volume > 0) & (d.close > 0)]
            d = d.sort_values("volume").groupby("date").tail(1).sort_values("date")      # 每天取成交量最大的月份＝近月
            d = d.rename(columns={"open": "Open", "max": "High", "min": "Low", "close": "Close"})
            d.index = pd.to_datetime(d.date); _TXC.update(t=time.time(), d=d[["Open", "High", "Low", "Close"]].astype(float))
        d = _TXC["d"]
        return d[d.index >= pd.Timestamp.now() - pd.DateOffset(months=1)] if period == "1mo" else d
    if interval == "1m":
        best = None
        for mt in ("0", "1"):                                # 0 一般盤、1 夜盤，取時間最新的那個
            j = requests.post("https://mis.taifex.com.tw/futures/api/getQuoteList", timeout=15,
                              headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
                              json={"MarketType": mt, "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "",
                                    "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}).json()
            q = [x for x in j["RtData"]["QuoteList"] if x["SymbolID"][-2:] in ("-F", "-M") and x["CLastPrice"] and x["CTime"]]
            if q:
                ts = pd.Timestamp(q[0]["CDate"] + q[0]["CTime"].zfill(6))
                now_ = pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None)
                if ts > now_ + pd.Timedelta(minutes=10): ts -= pd.Timedelta(days=1)                       # 日期標的是交易日
                if mt == "1" and ts.hour < 15 and ts + pd.Timedelta(days=1) <= now_ + pd.Timedelta(minutes=10): ts += pd.Timedelta(days=1)   # 夜盤過午夜
                if best is None or ts > best[0]: best = (ts, float(q[0]["CLastPrice"]))
        if best: return pd.DataFrame({"Open": [best[1]], "High": [best[1]], "Low": [best[1]], "Close": [best[1]]}, index=[best[0]])
    return None

# 芝商所期貨的免費報價都延遲 10 分鐘；用「即時、且幾乎同步的代理」把延遲期間的漲跌補上：
# 現價 ≈ 延遲期貨價 ×（代理現價 ÷ 代理在延遲時點的價格）。代理：Yahoo 即時外匯與比特幣（實測補正後誤差約 0.01–0.06%）
PROXY = {"6E": ("y", "EURUSD=X", 1), "6J": ("y", "JPY=X", -1), "6B": ("y", "GBPUSD=X", 1), "6A": ("y", "AUDUSD=X", 1),
         "6C": ("y", "CAD=X", -1), "6S": ("y", "CHF=X", -1), "6N": ("y", "NZDUSD=X", 1), "6M": ("y", "MXN=X", -1),
         "BTC": ("y", "BTC-USD", 1)}
# 註：期交所夜盤的美股期貨／黃金（SPF、UNF、UDF、GDF）報價時有時無、偶爾偏離，實測補正誤差反而比延遲價大，所以不採用
_MIS = {"t": 0, "q": {}, "h": {}}
def mis_quotes():
    """期交所 MIS：美股期貨（類別3）與黃金（類別7）近月的即時買賣報價中間價（造市商持續報價，比成交價即時），記下歷史供對齊延遲時點。"""
    import requests
    if time.time() - _MIS["t"] < 50: return _MIS["q"]
    now_ = pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None); hm = now_.strftime("%H:%M")
    mt = "0" if "08:45" <= hm < "13:45" else ("1" if hm >= "15:00" or hm < "05:00" else None)   # 只看正在交易的時段
    q = {}
    for kind in (("3", "7") if mt else ()):
        try:
            L = requests.post("https://mis.taifex.com.tw/futures/api/getQuoteList", timeout=15,
                              headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
                              json={"MarketType": mt, "SymbolType": "F", "KindID": kind, "CID": "", "ExpireMonth": "",
                                    "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}).json()["RtData"]["QuoteList"]
        except Exception: continue
        seen = set()
        for x in L:
            cid = x["SymbolID"][:3]
            if x["SymbolID"][-2:] not in ("-F", "-M") or cid in seen: continue                                                 # 每個商品只看第一列（近月），沒報價就整個跳過，不拿遠月充數
            seen.add(cid)
            try: b, a = float(x["CBestBidPrice"] or 0), float(x["CBestAskPrice"] or 0)
            except ValueError: continue
            if b > 0 and a >= b and (a - b) / ((a + b) / 2) < 0.003: q[cid] = (now_, (a + b) / 2)   # 價差太大的報價不用
    for cid, v in q.items():
        h = _MIS["h"].setdefault(cid, []); h.append(v); del h[:-40]
    _MIS.update(t=time.time(), q=q)
    return q

def rt_adjust(code, last, t_):
    if code not in PROXY: return last, t_
    src, sym, sg = PROXY[code]
    try:
        if src == "y":
            p = fetch(sym, "1d", "1m")
            if p is None or len(p) < 2 or p.index[-1] - t_ > pd.Timedelta(minutes=30): return last, t_
            then, now_p, t_new = float(p["Close"].asof(t_)), float(p["Close"].iloc[-1]), p.index[-1]
        else:
            q = mis_quotes()
            if sym not in q: return last, t_
            h = [v for v in _MIS["h"].get(sym, []) if v[0] <= t_]
            if not h or t_ - h[-1][0] > pd.Timedelta(minutes=6): return last, t_      # 剛開始跑還沒有延遲時點的紀錄，就先用延遲價
            then, (t_new, now_p) = h[-1][1], q[sym]
        if not (then > 0 and now_p > 0) or t_new <= t_: return last, t_
        f = (now_p / then) ** sg
        if abs(f - 1) > 0.02: return last, t_                                         # 10 分鐘內補正超過 2% 視為報價異常，不補
        return last * f, t_new
    except Exception:
        return last, t_

def fetch(sym, period, interval):
    if sym == "TXF":
        try: return txf(period, interval)
        except Exception: return None
    import yfinance as yf, logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)   # 休市時抓不到分鐘線的訊息不顯示
    for _ in range(3):
        try:
            d = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=False)
            if d is not None and not d.empty:
                d = d[["Open","High","Low","Close"]].dropna()
                if d.index.tz is not None: d.index = d.index.tz_convert("Asia/Taipei").tz_localize(None)
                return d
        except Exception: pass
        time.sleep(1.5)
    return None

def flip_levels(p):
    """明天收盤若穿越此價，該規則方向就翻轉"""
    c = p.values
    s199 = c[-199:].sum()
    return {
        "TSMOM 252日": c[-252],                 # 明天的252日前收盤
        "TSMOM 126日": c[-126],
        "價格 vs 200日均線": s199 / 199,        # 解 x = (s199+x)/200
        "2日 vs 200日均線": (s199 - 100 * c[-1]) / 99,  # 解 (c+x)/2 = (s199+x)/200
    }

def rnd(x, t): return round(round(x / t) * t, 10)
def fmt(x, t):
    ds = f"{t:.10f}".rstrip("0").split(".")[1] if t < 1 else ""
    return f"{x:,.{min(len(ds), 7)}f}"

def bar_done(code, idx):
    """哪些日K已經收盤。台指期：日盤 13:45 收（台北時間）。美國期貨：Yahoo 以交易日標日期，當天 17:00 美東（冬令 22:00 UTC）才收，
    台北凌晨 0–6 點那根還在交易中，不能當成已收盤。"""
    d = pd.DatetimeIndex(idx).normalize()
    if code == "TX":
        now = pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None)
        return (d + pd.Timedelta(hours=13, minutes=50)) <= now
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return (d + pd.Timedelta(hours=22, minutes=5)) <= now


# ───────────────────────── 合約清單（規格已對照交易所官網）─────────────────────────
# (代號, 名稱, 交易所, 跳動點, 每跳動金額, 幣別, 期交所即時報價代號)
TFX = {   # 期交所：規格頁 taifex.com.tw/cht/2/…；即時報價 mis.taifex.com.tw
 "ES": [("SPF", "期交所 美國標普500", .25, 50, "TWD", "SPF")],
 "NQ": [("UNF", "期交所 美國那斯達克100", 1, 50, "TWD", "UNF")],
 "YM": [("UDF", "期交所 美國道瓊", 1, 20, "TWD", "UDF")],
 "GC": [("GDF", "期交所 美元黃金", .1, .1, "USD", "GDF")],
 "6E": [("XEF", "期交所 歐元兌美元", .0001, 2, "USD", "XEF")],
 "6B": [("XBF", "期交所 英鎊兌美元", .0001, 2, "USD", "XBF")],
 "6A": [("XAF", "期交所 澳幣兌美元", .0001, 2.5, "USD", "XAF")],
}
def contracts(code):
    if code == "TX":
        return [("TX", "期交所 大台", 1, 200, "TWD", "TXF"), ("MTX", "期交所 小台", 1, 50, "TWD", "MXF"), ("TMF", "期交所 微台", 1, 10, "TWD", "TMF")]
    n, _, t, v, mic = C[code][:5]
    L = [(code, "CME 標準", t, v, "USD", None)]
    if mic: L.append((mic[0], "CME 微型", mic[1], mic[2], "USD", None))
    return L + TFX.get(code, [])

FIXED = ["TX", "ES", "NQ", "CL", "GC", "SI", "HG"]                        # 固定顯示區
COMMOD = [k for k, v in C.items() if v[5] in ("能源", "金屬", "農產品")]      # 期限結構只做這 19 檔
SEASONAL = {"NG", "HO", "HE", "LE", "ZC", "ZS", "ZW"}                       # 遠近月價差有明顯季節性
# 期限結構的月份（只列流動性好的月份）與 Yahoo 交易所後綴
MONTHS = {"CL": "FGHJKMNQUVXZ", "NG": "FGHJKMNQUVXZ", "HO": "FGHJKMNQUVXZ", "GC": "GJMQVZ", "SI": "HKNUZ", "HG": "HKNUZ",
          "PL": "FJNV", "PA": "HMUZ", "ZC": "HKNUZ", "ZS": "FHKNQUX", "ZW": "HKNUZ", "ZL": "FHKNQUVZ", "ZM": "FHKNQUVZ",
          "HE": "GJKMNQVZ", "LE": "GJMQVZ", "CT": "HKNVZ", "SB": "HKNV", "KC": "HKNUZ", "CC": "HKNUZ"}
SFX = {"CL": "NYM", "NG": "NYM", "HO": "NYM", "PL": "NYM", "PA": "NYM", "GC": "CMX", "SI": "CMX", "HG": "CMX",
       "ZC": "CBT", "ZS": "CBT", "ZW": "CBT", "ZL": "CBT", "ZM": "CBT", "HE": "CME", "LE": "CME", "CT": "NYB", "SB": "NYB", "KC": "NYB", "CC": "NYB"}
MCODE = "FGHJKMNQUVXZ"
TV = {"ES": "CME_MINI:ES1!", "NQ": "CME_MINI:NQ1!", "YM": "CBOT_MINI:YM1!", "RTY": "CME_MINI:RTY1!", "GC": "COMEX:GC1!", "SI": "COMEX:SI1!",
      "HG": "COMEX:HG1!", "PL": "NYMEX:PL1!", "PA": "NYMEX:PA1!", "CL": "NYMEX:CL1!", "NG": "NYMEX:NG1!", "HO": "NYMEX:HO1!",
      "6E": "CME:6E1!", "6J": "CME:6J1!", "6B": "CME:6B1!", "6A": "CME:6A1!", "6C": "CME:6C1!", "6S": "CME:6S1!", "6M": "CME:6M1!",
      "6N": "CME:6N1!", "DX": "ICEUS:DX1!", "ZC": "CBOT:ZC1!", "ZS": "CBOT:ZS1!", "ZW": "CBOT:ZW1!", "ZL": "CBOT:ZL1!", "ZM": "CBOT:ZM1!",
      "ZN": "CBOT:ZN1!", "ZB": "CBOT:ZB1!", "ZT": "CBOT:ZT1!", "ZF": "CBOT:ZF1!", "HE": "CME:HE1!", "LE": "CME:LE1!", "CT": "ICEUS:CT1!",
      "SB": "ICEUS:SB1!", "KC": "ICEUS:KC1!", "CC": "ICEUS:CC1!", "NKD": "CME:NKD1!", "BTC": "CME:BTC1!", "TX": "TAIFEX:TXF1!"}
CNYES = {"ES": "ESCON", "NQ": "NQCON", "YM": "YMCON"}
COT = {"ES": "13874A", "NQ": "209742", "YM": "124603", "RTY": "239742", "NKD": "240741", "GC": "088691", "SI": "084691", "HG": "085692",
       "PL": "076651", "PA": "075651", "CL": "067651", "NG": "023651", "HO": "022651", "6E": "099741", "6J": "097741", "6B": "096742",
       "6A": "232741", "6C": "090741", "6S": "092741", "6M": "095741", "6N": "112741", "DX": "098662", "ZC": "002602", "ZS": "005602",
       "ZW": "001602", "ZL": "007601", "ZM": "026603", "ZN": "043602", "ZB": "020601", "ZT": "042601", "ZF": "044601", "HE": "054642",
       "LE": "057642", "CT": "033661", "SB": "080732", "KC": "083731", "CC": "073732", "BTC": "133741"}
NEWS_KW = {"TX": ["台指", "台股", "台湾", "台积电", "加权指数"], "ES": ["标普", "美股", "美联储", "道指"], "NQ": ["纳指", "纳斯达克", "科技股", "英伟达", "美股"],
           "CL": ["原油", "油价", "OPEC", "欧佩克", "WTI", "布伦特", "霍尔木兹", "EIA"], "GC": ["黄金", "金价", "现货金"],
           "SI": ["白银", "银价", "现货银"], "HG": ["铜"]}
STATS = json.load(open("stats.json", encoding="utf-8"))
# 回測（pysystemtrade 回溯調整價；樣本外 2010–2024/03；39 檔全做；收盤成交、3N 停損、已扣手續費與 1 跳滑價）
SYS_BT = [("趨勢", "4 條長週期規則 ≥3 條同向進場、3N 停損、同向 <3 條出場", "0.50", "1990–2024/03 回測有效；之後每天前向紀錄"),
          ("期限結構", "主力月比次月貴 → 多、便宜 → 空（只做 19 檔商品）", "0.42", "回測有效 1990–2024/03、2024 後尚未驗證"),
          ("兩套各一份", "兩套獨立下單、不合併投票；每日損益相關係數 0.23", "0.58", "同上")]
RISK_BT = [("0.25%", (8.8, 42.4, -9.7), (3.5, 20.8, -3.7), (12.1, 47.3, -10.4)), ("0.5%", (12.9, 73.2, -19.3), (6.2, 38.0, -7.4), (17.7, 79.4, -20.9)),
           ("1%", (4.5, 97.0, -38.6), (9.2, 63.5, -14.8), (5.5, 98.8, -41.8)), ("2%", (-55.1, 100.0, -77.3), (4.6, 91.0, -29.5), (-68.8, 100.0, -83.6))]

def now_tp(): return pd.Timestamp.now(tz=TZ).tz_localize(None)
def rq():
    import requests; return requests
UA = {"User-Agent": "Mozilla/5.0"}

# ───────────────────────── 期交所即時報價（近月，日盤＋夜盤取最新）─────────────────────────
def mis_all():
    out = {}
    for kind in ("1", "3", "6", "7"):
        for mt in ("0", "1"):
            try:
                L = rq().post("https://mis.taifex.com.tw/futures/api/getQuoteList", timeout=15, headers={**UA, "Content-Type": "application/json"},
                              json={"MarketType": mt, "SymbolType": "F", "KindID": kind, "CID": "", "ExpireMonth": "", "RowSize": "全部",
                                    "PageNo": "", "SortColumn": "", "AscDesc": "A"}).json()["RtData"]["QuoteList"]
            except Exception: continue
            seen = set()
            for x in L:
                cid = x["SymbolID"][:3]
                if x["SymbolID"][-2:] not in ("-F", "-M") or cid in seen: continue
                seen.add(cid)                                       # 每個商品第一列 = 近月
                o = out.setdefault(cid, {"sym": x["SymbolID"][:-2], "name": x.get("DispCName", "")})
                try: last = float(x["CLastPrice"] or 0)
                except ValueError: last = 0
                if last > 0 and x.get("CTime"):
                    ts = pd.Timestamp(x["CDate"] + x["CTime"].zfill(6))
                    if mt == "1" and ts.hour < 15: ts += pd.Timedelta(days=1)      # 夜盤過午夜：日期標的是交易日
                    if ts > now_tp() + pd.Timedelta(minutes=10): ts -= pd.Timedelta(days=1)
                    if "t" not in o or ts > o["t"]: o.update(last=last, t=ts)
                try:
                    sp = float(x.get("SettlementPrice") or 0)
                    if mt == "0" and sp > 0: o.update(settle=sp, sdate=x["CDate"])
                except ValueError: pass
    return out

def tfx_ref(M, cid):
    """期交所合約的參考價：最新成交價；沒有成交就用結算價。回傳 (價, 標籤)"""
    o = M.get(cid) or {}
    if o.get("last") and (not o.get("settle") or now_tp() - o["t"] < pd.Timedelta(hours=20)):
        return o["last"], f"期交所 {o['sym']} 成交價 {o['t']:%m/%d %H:%M}"
    if o.get("settle"):
        return o["settle"], f"期交所 {o['sym']} 結算價 {o['sdate'][4:6]}/{o['sdate'][6:]}"
    return None, "期交所目前沒有報價"

# ───────────────────────── 第二、第三報價來源 ─────────────────────────
def tv_quotes():
    """TradingView 連續合約第 1、2 個月份（Yahoo 換月時間和 TradingView 不同，兩個都抓才能比到同一個合約）"""
    try:
        tick = list(TV.values()) + [v.replace("1!", "2!") for v in TV.values()]
        r = rq().post("https://scanner.tradingview.com/futures/scan", headers=UA, timeout=20,
                      json={"symbols": {"tickers": tick}, "columns": ["close", "time", "update_mode"]}).json()
        inv = {v: (k, 1) for k, v in TV.items()}; inv.update({v.replace("1!", "2!"): (k, 2) for k, v in TV.items()})
        out = {}
        for x in r.get("data", []):
            if x["s"] in inv and x["d"][0] is not None:
                k, n = inv[x["s"]]
                out.setdefault(k, {})[n] = (float(x["d"][0]), pd.Timestamp(int(x["d"][1]), unit="s", tz="UTC").tz_convert(TZ).tz_localize(None) if x["d"][1] else None)
        return out
    except Exception as e:
        print("TradingView 失敗", e); return {}

def cnyes_quotes():
    try:
        t = rq().get("https://www.cnyes.com/futures/indexftr.aspx", headers=UA, timeout=20); t.encoding = "utf-8"
        out = {}
        for code, key in CNYES.items():
            m = re.search(r"<td>([\d:]+)</td>\s*<td><a href=\"/futures/flashchart/" + key + r"\.html\"[^>]*>[^<]*</a></td>\s*<td>[^<]*</td>\s*<td class=\"[^\"]*\">([\d.,]+)</td>", t.text)
            if m: out[code] = (float(m.group(2).replace(",", "")), m.group(1))
        return out
    except Exception as e:
        print("鉅亨失敗", e); return {}

# ───────────────────────── 背景資訊（不參與訊號）─────────────────────────
def load_cache():
    try: return json.load(open(CACHE, encoding="utf-8"))
    except Exception: return {}

def jin10(cache):
    J = cache.setdefault("news", {})
    pages = 1 if len(J) > 50 else 8
    mx = None
    for _ in range(pages):
        try:
            p = {"channel": "-8200", "vip": "1"}
            if mx: p["max_time"] = mx
            d = rq().get("https://flash-api.jin10.com/get_flash_list", params=p, timeout=20,
                         headers={**UA, "x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0", "Origin": "https://www.jin10.com", "Referer": "https://www.jin10.com/"}).json()["data"]
        except Exception as e:
            print("金十失敗", e); break
        if not d: break
        for x in d:
            c = (x.get("data") or {}).get("content") or (x.get("data") or {}).get("title") or ""
            c = re.sub(r"<[^>]+>", "", c).strip()
            if c: J[x["id"]] = (x["time"], c[:200])
        mx = d[-1]["time"]
    for k in sorted(J)[:-800]: del J[k]

def news_for(cache, code):
    hits = [(k, t, c) for k, (t, c) in cache.get("news", {}).items() if any(w in c for w in NEWS_KW[code])]
    return sorted(hits, key=lambda x: x[1], reverse=True)[:5]

def cot(cache):
    if time.time() - cache.get("cot_t", 0) < 6 * 3600: return
    try:
        st_ = (now_tp() - pd.DateOffset(years=3, days=14)).strftime("%Y-%m-%d")
        codes = ",".join(f"'{c}'" for c in COT.values())
        j = rq().get("https://publicreporting.cftc.gov/resource/6dca-aqww.json", timeout=60, params={
            "$select": "cftc_contract_market_code,market_and_exchange_names,report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all",
            "$where": f"cftc_contract_market_code in ({codes}) AND report_date_as_yyyy_mm_dd >= '{st_}'", "$limit": "20000"}).json()
        d = pd.DataFrame(j)
        out = {}
        for code, cc in COT.items():
            x = d[d.cftc_contract_market_code == cc].sort_values("report_date_as_yyyy_mm_dd")
            if len(x) < 20: continue
            net = x.noncomm_positions_long_all.astype(float) - x.noncomm_positions_short_all.astype(float)
            out[code] = dict(date=x.report_date_as_yyyy_mm_dd.iloc[-1][:10], net=float(net.iloc[-1]), chg=float(net.iloc[-1] - net.iloc[-2]),
                             pct=float((net <= net.iloc[-1]).mean() * 100), n=int(len(net)), oi=float(x.open_interest_all.iloc[-1]),
                             mkt=x.market_and_exchange_names.iloc[-1])
        cache.update(cot=out, cot_t=time.time())
    except Exception as e:
        print("CFTC 失敗", e)

def eia(cache):
    if time.time() - cache.get("eia_t", 0) < 3 * 3600: return
    try:
        import csv, io
        rows = list(csv.reader(io.StringIO(rq().get("https://ir.eia.gov/wpsr/table1.csv", headers=UA, timeout=30).text)))
        hd = rows[0]
        r = next(x for x in rows if x[0].startswith("Commercial (Excluding SPR)"))
        cache.update(eia=dict(week=hd[1], prev=hd[2], v=float(r[1].replace(",", "")), chg=float(r[3].replace(",", ""))), eia_t=time.time())
    except Exception as e:
        print("EIA 失敗", e)

def inst(cache):
    if time.time() - cache.get("inst_t", 0) < 3600: return
    try:
        j = rq().get("https://api.finmindtrade.com/api/v4/data", timeout=30, params={"dataset": "TaiwanFuturesInstitutionalInvestors", "data_id": "TX",
                     "start_date": (now_tp() - pd.Timedelta(days=14)).strftime("%Y-%m-%d")}).json()["data"]
        d = pd.DataFrame(j); d["net"] = d.long_open_interest_balance_volume - d.short_open_interest_balance_volume
        days = sorted(d.date.unique())
        out = {"date": days[-1], "rows": []}
        for who in ("外資", "投信", "自營商"):
            x = d[d.institutional_investors == who].set_index("date").net
            out["rows"].append((who, int(x.get(days[-1], 0)), int(x.get(days[-1], 0) - x.get(days[-2], 0)) if len(days) > 1 else None))
        cache.update(inst=out, inst_t=time.time())
    except Exception as e:
        print("法人失敗", e)

# ───────────────────────── 期限結構（主力月 vs 次月）─────────────────────────
def curve(cache):
    """每小時一次：抓每個商品接下來 6 個上市月份的日K，成交量最大＝主力月，下一個上市月份＝次月"""
    if time.time() - cache.get("curve_t", 0) < 3600 and cache.get("curve"): return
    import yfinance as yf, logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    t0 = now_tp(); syms = {}
    for code in COMMOD:
        L = []
        for i in range(0, 30):
            y, m = divmod(t0.month - 1 + i, 12); y += t0.year
            if MCODE[m] in MONTHS[code]: L.append((f"{code}{MCODE[m]}{y % 100:02d}.{SFX[code]}", y * 12 + m))
            if len(L) >= 6: break
        syms[code] = L
    allsym = [s for L in syms.values() for s, _ in L]
    try:
        D = yf.download(allsym, period="20d", interval="1d", auto_adjust=False, progress=False, group_by="ticker", threads=True)
    except Exception as e:
        print("期限結構下載失敗", e); return
    out = {}
    for code, L in syms.items():
        got = []
        for s, mi in L:
            try:
                x = D[s][["Close", "Volume"]].dropna()
                if len(x): got.append((s, mi, x))
            except Exception: pass
        if len(got) < 2: continue
        vol = [float(x.Volume.tail(3).mean()) for _, _, x in got]
        i = int(np.argmax(vol))
        if i + 1 >= len(got): i -= 1
        (s1, m1, a), (s2, m2, b) = got[i], got[i + 1]
        j = pd.concat([a.Close, b.Close], axis=1, keys=["a", "b"]).dropna()
        if not len(j): continue
        ann = (j.a - j.b) / j.a.abs() * 12 / (m2 - m1)            # >0：主力月比次月貴（逆價差）
        out[code] = dict(main=s1.split(".")[0], nxt=s2.split(".")[0], pa=float(j.a.iloc[-1]), pb=float(j.b.iloc[-1]), date=str(j.index[-1].date()),
                         ann=float(ann.iloc[-1]), sm=float(ann.tail(5).mean()), n5=int(min(5, len(ann))), months=m2 - m1,
                         hist=[(str(k.date()), round(float(v), 4)) for k, v in ann.tail(5).items()])
    cache.update(curve=out, curve_t=time.time())

# ───────────────────────── 趨勢分析 ─────────────────────────
def in_session(code, t):
    """是否在交易時段（只判斷近 24 小時交易的商品；農產品、軟商品、畜產時段分段，不判斷回傳 None）"""
    if code == "TX":
        hm = t.strftime("%H:%M"); wd = t.weekday()
        day = wd < 5 and "08:45" <= hm < "13:45"
        night = ("15:00" <= hm and wd < 5) or (hm < "05:00" and 1 <= wd <= 5)
        return day or night
    if C[code][5] not in ("指數", "外匯", "能源", "金屬", "公債", "加密"): return None
    et = t.tz_localize(TZ).tz_convert("America/New_York"); wd = et.weekday(); h = et.hour + et.minute / 60
    if wd == 5 or (wd == 6 and h < 18) or (wd == 4 and h >= 17): return False
    return not (17 <= h < 18)

def analyze(code, tvq, cnq):
    name, ysym, tick, tv_, micro, grp, q = C[code]
    D = fetch(ysym, "3y", "1d")
    if D is None or len(D) < 300: return dict(code=code, name=name, err="抓不到日線資料")
    live = fetch(ysym, "1d", "1m")
    t = now_tp()
    fresh = live is not None and len(live) and t - live.index[-1] <= pd.Timedelta(minutes=40)
    if code == "TX": fresh = live is not None and len(live) and live.index[-1] > D.index[-1] + pd.Timedelta(hours=13, minutes=45)
    if code == "TX":
        src = "期交所 MIS 臺指期近月"
        if fresh: last, t_, kind = float(live["Close"].iloc[-1]), live.index[-1], "成交價"
        else: last, t_, kind, src = float(D["Close"].iloc[-1]), pd.Timestamp(D.index[-1].date()), "日盤收盤價", "FinMind 期交所日行情 臺指期近月"
    elif fresh:
        last, t_ = rt_adjust(code, float(live["Close"].iloc[-1]), live.index[-1])
        src = f"Yahoo {ysym}"; kind = "成交價（延遲約 10 分）" if code not in PROXY else "成交價＋即時匯率補正"
    else:
        last, t_, src, kind = float(D["Close"].iloc[-1]), pd.Timestamp(D.index[-1].date()), f"Yahoo {ysym}", "日K收盤／結算價"
    Dc = D[bar_done(code, D.index)]
    p = Dc["Close"]; c = p.values
    sma200 = c[-200:].mean(); sma2 = c[-2:].mean()
    rules = [("TSMOM 252日", c[-1], c[-253], "收盤 vs 252 日前收盤"), ("TSMOM 126日", c[-1], c[-127], "收盤 vs 126 日前收盤"),
             ("價格 vs 200日均線", c[-1], sma200, "收盤 vs 200 日均線"), ("2日 vs 200日均線", sma2, sma200, "2 日均線 vs 200 日均線")]
    sig = {k: float(np.sign(a - b)) for k, a, b, _ in rules}
    nl = sum(1 for v in sig.values() if v > 0); ns = sum(1 for v in sig.values() if v < 0)
    side = 1 if nl >= 3 else (-1 if ns >= 3 else 0)
    lv = flip_levels(p)
    dpx = p.diff(); sdx = dpx.rolling(60, min_periods=20).std().shift(1)
    dpx = dpx.where(~(dpx.abs() > 6 * sdx), 0.0)
    N = float(dpx.abs().ewm(span=20, adjust=False).mean().iloc[-1])
    xref = None
    if side:
        agree = sorted([lv[k] for k, v in sig.items() if v == side], reverse=(side == 1))
        n = max(nl, ns)
        agree = [x for x in agree if (x < last if side == 1 else x > last)]
        if len(agree) >= n - 2: xref = agree[n - 3]
    # 報價健康度：和 TradingView（第二來源）比價；交易時段內報價超過 40 分沒更新＝過期
    h = dict(state="ok", note="")
    tq2 = tvq.get(code) or {}
    tq = tq2.get(1)
    if tq and 2 in tq2 and abs(last / tq[0] - 1) > 0.005 and abs(last / tq2[2][0] - 1) <= 0.005:
        tq = tq2[2]; h["m2"] = True                                     # Yahoo 已換到下一個月份：改跟 TradingView 第 2 個月份比
    opn = in_session(code, t)
    if tq:
        diff = (last - tq[0]) / tq[0] * 100
        h.update(tv=tq[0], diff=diff, tv2=(tq2.get(2) or (None,))[0])
        if abs(diff) > 0.5:
            h.update(state="diff", note=f"與 TradingView 差 {diff:+.2f}%（TradingView 近月 {fmt(tq2[1][0], tick)}" + (f"、次月 {fmt(tq2[2][0], tick)}" if 2 in tq2 else "") + "）")
    else:
        h.update(state="nosrc", note="沒有第二來源")
    if h["state"] != "diff":
        if opn is None or opn: 
            if opn and (t_ is None or t - t_ > pd.Timedelta(minutes=40) or not fresh):
                h.update(state="stale", note=f"交易時段內報價停在 {tstr(t_)}")
        else:
            if h["state"] == "ok": h["state"] = "closed"
    if code in cnq:
        h["cn"] = cnq[code]
        d3 = (last - cnq[code][0]) / cnq[code][0] * 100
        h["cnd"] = d3
        if abs(d3) > 0.5 and h["state"] in ("ok", "closed"): h.update(state="diff", note=f"與鉅亨差 {d3:+.2f}%")
    return dict(code=code, name=name, grp=grp, last=last, t=t_, src=src, kind=kind, tick=tick, close=c[-1], cdate=Dc.index[-1],
                rules=rules, sig=sig, nl=nl, ns=ns, side=side, nag=max(nl, ns) if side else 0, lv=lv, N=N, dist=3 * N, xref=xref, h=h)

# ───────────────────────── 每口資訊 ─────────────────────────
def cur(v, ccy):
    s = "US$" if ccy == "USD" else "NT$"
    return ("−" if v < 0 else "") + s + f"{abs(v):,.0f}"

def lot_rows(code, side, dist, ref_cme, ref_lab, M, st_key, sysname):
    """每個合約一列：進場參考、停損（換成該合約自己的報價）、停損虧損/口、歷史統計換算成金額"""
    s = (STATS[st_key].get(code) or {}).get("oos") if st_key in STATS else None
    rows = []
    for pc, desc, tk, tv_, ccy, cid in contracts(code):
        if cid: ref, lab = tfx_ref(M, cid)
        else: ref, lab = ref_cme, ref_lab
        if not ref: rows.append(dict(pc=pc, desc=desc, ref=None, lab=lab)); continue
        stop = rnd(ref - side * dist, tk)
        loss = abs(ref - stop) / tk * tv_
        rows.append(dict(pc=pc, desc=desc, ref=ref, lab=lab, stop=stop, tk=tk, ccy=ccy, loss=loss,
                         avg=s["avg"] * loss if s else None, mx=s["max_win"] * loss if s else None, worst=s["worst"] * loss if s else None,
                         win=s["win"] if s else None))
    return rows, s

# ───────────────────────── 主程式 ─────────────────────────
def main():
    st = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    cache = load_cache()
    t = now_tp()
    fxd = fetch("TWD=X", "5d", "1d"); fx = (float(fxd["Close"].iloc[-1]), fxd.index[-1]) if fxd is not None else (None, None)
    M = mis_all(); tvq = tv_quotes(); cnq = cnyes_quotes()
    for f in (jin10, cot, eia, inst, curve):
        try: f(cache)
        except Exception as e: print(f.__name__, "失敗", e)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    R = []
    for code in C:
        try: r = analyze(code, tvq, cnq)
        except Exception as e: print(code, "分析失敗", e); continue
        if r.get("err"): print(code, r["err"]); continue
        cv = cache.get("curve", {}).get(code) if code in COMMOD else None
        r["cv"] = cv
        r["cside"] = (1 if cv["sm"] > 0 else -1) if cv and cv["sm"] != 0 else 0
        R.append(r)
    # 期限結構每日前向紀錄（2024/03 之後沒有回測資料，從現在起每天記下來）
    rec = st.setdefault("carry_rec", {})
    for r in R:
        cv = r["cv"]
        if cv:
            rec.setdefault(r["code"], {})[cv["date"]] = dict(main=cv["main"], nxt=cv["nxt"], pa=cv["pa"], pb=cv["pb"], ann=round(cv["ann"], 4), sm=round(cv["sm"], 4), side=r["cside"])
            for k in sorted(rec[r["code"]])[:-400]: del rec[r["code"]][k]
    # 訊號變化紀錄
    sig = st.setdefault("sig", {}); log = st.setdefault("log", [])
    if "pos" in st and not st.get("seeded"):                 # 舊版的持倉紀錄＝當時的趨勢訊號，轉成訊號紀錄
        for k, v in st["pos"].items():
            log.append(dict(t=str(v.get("t0", v["d0"]))[:16], code=k, sys="趨勢", frm=None, to=v["side"], px=v["entry"]))
        st["seeded"] = True
    news_msg = []
    for r in R:
        for sysk, val, px in (("趨勢", r["side"], r["last"]), ("期限結構", r["cside"], (r["cv"] or {}).get("pa"))):
            if sysk == "期限結構" and r["code"] not in COMMOD: continue
            key = f"{r['code']}|{sysk}"
            if key not in sig:
                sig[key] = val; continue
            if sig[key] != val:
                log.append(dict(t=t.strftime("%Y-%m-%d %H:%M"), code=r["code"], sys=sysk, frm=sig[key], to=val, px=px))
                news_msg.append(f"{r['name']} {sysk}：{lab(sig[key])} → {lab(val)}（{fmt(px, r['tick']) if px else ''}）")
                sig[key] = val
    del log[:-300]
    st.pop("pos", None); st.pop("ledger", None); st.pop("cool", None); st.pop("started", None); st.pop("last_summary", None)
    if news_msg and 通知頻道.strip(): push("📈 訊號變化 " + t.strftime("%m/%d %H:%M") + "\n" + "\n".join(news_msg))
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_board(R, st, cache, M, fx, t)
    print(f"（{t:%H:%M} 完成：{len(R)} 檔，訊號變化 {len(news_msg)}）")

def lab(v): return "多" if v and v > 0 else ("空" if v and v < 0 else "觀望")

def push(text):
    title, _, body = text.partition("\n")
    req = urllib.request.Request("https://ntfy.sh", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"topic": 通知頻道.strip(), "title": title, "message": body[:3900]}).encode())
    try: urllib.request.urlopen(req, timeout=20)
    except Exception as e: print("通知失敗", e)

# ───────────────────────── 網頁 ─────────────────────────
E = html.escape
def tstr(t): return f"{t:%m/%d}" if t.hour == 0 and t.minute == 0 else f"{t:%m/%d %H:%M}"
def sgn(v, d=0): return ("+" if v > 0 else ("−" if v < 0 else "")) + f"{abs(v):,.{d}f}"
def side_html(v, extra=""):
    return f"<b class={'l' if v > 0 else ('s' if v < 0 else 'z')}>{lab(v)}{extra}</b>"

HEALTH = {"ok": ("正常", "g"), "closed": ("休市", "z"), "diff": ("價差異常", "r"), "stale": ("報價過期", "r"), "nosrc": ("無第二來源", "z")}

def lot_table(rows, s, period_note):
    if not rows: return ""
    body = []
    for x in rows:
        if x.get("ref") is None:
            body.append(f"<div class=lot><div class=lh><b>{E(x['pc'])}</b> <small>{E(x['desc'])}</small></div><div class=z>{E(x['lab'])}</div></div>"); continue
        tk, ccy = x["tk"], x["ccy"]
        winx = "—" if x["win"] is None else f"{x['win']:.0%}"
        num = lambda v: "—" if v is None else f"<span class={'g' if v >= 0 else 'r'}>{('+' if v >= 0 else '')}{cur(v, ccy)}</span>"
        body.append(f"<div class=lot><div class=lh><b>{E(x['pc'])}</b> <small>{E(x['desc'])}</small></div>"
                    f"<div class=lg><span>進場參考<b>{fmt(x['ref'], tk)}</b></span><span>停損<b>{fmt(x['stop'], tk)}</b></span><span>停損虧損/口<b class=r>−{cur(x['loss'], ccy)}</b></span></div>"
                    f"<div class=ls>歷史 平均 {num(x['avg'])}・最大 {num(x['mx'])}・最差 {num(x['worst'])}・勝率 {winx}</div>"
                    f"<div class=src>{E(x['lab'])}</div></div>")
    note = (f"<p class=m>歷史＝{E(period_note)} {s['n']} 筆：平均每筆 {s['avg']:+.2f}R、最大 {s['max_win']:+.1f}R、最差 {s['worst']:+.1f}R、勝率 {s['win']:.0%}；"
            f"金額＝R × 該合約現在的每口停損虧損。停損虧損不含手續費與滑價；跳空可能超過停損（最差一筆就是實際發生過的）。</p>") if s else "<p class=m>此商品沒有歷史回測資料。</p>"
    return "".join(body) + note

def card(r, M, cache):
    code, tk = r["code"], r["tick"]
    h = r["h"]; hs, hc = HEALTH[h["state"]]
    chk = []
    if "tv" in h and h["state"] != "diff": chk.append(("Yahoo 已換到次月，對照 " if h.get("m2") else "") + f"TradingView {'次月' if h.get('m2') else ''}{fmt(h['tv'], tk)}（差 {h['diff']:+.2f}%）")
    if "cn" in h: chk.append(f"鉅亨 {fmt(h['cn'][0], tk)}（{h['cn'][1]}，差 {h['cnd']:+.2f}%）")
    src = (f"<div class=src>{E(r['src'])}｜{E(r['kind'])}｜{tstr(r['t'])}<br><span class={hc}>● {hs}</span> "
           f"{E(h.get('note', ''))}{'｜' if h.get('note') and chk else ''}{E('｜'.join(chk))}</div>")
    cs = ""
    if code in COMMOD:
        cs = " ｜ 期限結構 " + (side_html(r["cside"]) if r["cv"] else "<b class=z>無資料</b>")
    agx = f" {r['nag']}/4" if r["side"] else ""
    out = [f"<section class=card id={code}><div class=top><b>{E(r['name'])}</b> <small>{code}</small><span class=px>{fmt(r['last'], tk)}</span></div>{src}",
           f"<div class=sg>趨勢 {side_html(r['side'], agx)}{cs}</div>"]
    tlab = f"{r['src']} {r['kind'].split('（')[0]} {tstr(r['t'])}"
    if r["side"]:
        rows, s = lot_rows(code, r["side"], r["dist"], r["last"], tlab, M, "trend", "趨勢")
        per = (STATS["trend"].get(code) or {}).get("oos") or {}
        pn = f"趨勢系統回測 {per.get('first', '')[:4]}–{per.get('last', '')[:4]} 樣本外" + ("（以加權指數代替台指期）" if code == "TX" else "")
        out.append(f"<h4>趨勢：{'做多' if r['side'] > 0 else '做空'}｜停損距離 3N = 3 × {fmt(r['N'], tk / 10)} = {fmt(r['dist'], tk)}</h4>" + lot_table(rows, s, pn))
    cv = r["cv"]
    if cv and r["cside"]:
        same = cv["date"] == str(r["cdate"].date()) and abs(cv["pa"] - r["close"]) <= 1e-9 * max(1, abs(cv["pa"]))
        ref, rl = (r["last"], tlab) if same and code != "TX" else (cv["pa"], f"Yahoo {cv['main']} 日K收盤 {cv['date'][5:].replace('-', '/')}")
        rows, s = lot_rows(code, r["cside"], r["dist"], ref, rl, M, "carry", "期限結構")
        per = (STATS["carry"].get(code) or {}).get("oos") or {}
        pn = f"期限結構回測 {per.get('first', '')[:4]}–{per.get('last', '')[:4]} 樣本外"
        out.append(f"<h4>期限結構：{'做多' if r['cside'] > 0 else '做空'}｜{cv['main']} {fmt(cv['pa'], tk)} {'＞' if cv['pa'] > cv['pb'] else '＜'} {cv['nxt']} {fmt(cv['pb'], tk)}"
                   f"（5 日平均年化 {cv['sm']:+.1%}）<br><small class=w>回測有效 1990–2024/03、2024 後尚未驗證{'；季節性商品，遠近月價差含季節因素' if code in SEASONAL else ''}；停損同樣 3N</small></h4>"
                   + lot_table(rows, s, pn))
    # 依據與翻轉價
    rl = []
    for (k, a, b, desc) in r["rules"]:
        v = r["sig"][k]
        rl.append(f"<tr><td>{E(k)}<br><small>{E(desc)}</small></td><td class=n>{fmt(a, tk)}<br><small>vs {fmt(b, tk)}</small></td><td>{side_html(v)}</td><td class=n>{fmt(r['lv'][k], tk)}</td></tr>")
    det = [f"<p class=m>訊號依據：{r['cdate']:%m/%d} 收盤 {fmt(r['close'], tk)}（只用已收盤的日K）。翻轉價＝下一根日K收盤穿越此價，該規則就轉向。</p>",
           f"<div class=scroll><table><tr><th>規則</th><th class=n>現在數值</th><th>方向</th><th class=n>翻轉價</th></tr>{''.join(rl)}</table></div>"]
    if r["side"] and r["xref"] is not None:
        det.append(f"<p class=m>趨勢出場參考：收盤{'跌破' if r['side'] > 0 else '漲破'} {fmt(rnd(r['xref'], tk), tk)} → 同向剩 2 條，趨勢系統出場。</p>")
    elif not r["side"]:
        det.append(f"<p class=m>目前多 {r['nl']} 條、空 {r['ns']} 條，要有 3 條同向才進場。</p>")
    det.append(f"<p class=m>N＝近 20 日平均收盤變動（換月跳空不計）＝{fmt(r['N'], tk / 10)}；3N＝{fmt(r['dist'], tk)}（{r['dist'] / r['last']:.1%}）。</p>")
    if cv:
        hist = "、".join(f"{d[5:].replace('-', '/')} {v:+.1%}" for d, v in cv["hist"])
        det.append(f"<p class=m>期限結構：主力月（近 3 日成交量最大）{cv['main']} {fmt(cv['pa'], tk)}、次月 {cv['nxt']} {fmt(cv['pb'], tk)}（Yahoo 日K收盤 {cv['date']}），"
                   f"相隔 {cv['months']} 個月，年化 {cv['ann']:+.1%}。近 {cv['n5']} 日：{hist}；平均 {cv['sm']:+.1%} → {lab(r['cside'])}。"
                   f"翻轉條件：5 日平均年化跨過 0（主力月與次月同價）。</p>")
    out.append(f"<details><summary>規則數字與翻轉價</summary>{''.join(det)}</details>")
    # 背景資訊
    bg = []
    if code in NEWS_KW:
        nw = news_for(cache, code)
        if nw:
            bg.append("<b>金十快訊</b><ul>" + "".join(f"<li><small>{E(tm[5:16])}</small> <a href='https://flash.jin10.com/detail/{E(k)}'>{E(c[:60])}{'…' if len(c) > 60 else ''}</a></li>" for k, tm, c in nw) + "</ul>")
        else: bg.append("<b>金十快訊</b>：近期沒有相關快訊")
    ct = cache.get("cot", {}).get(code)
    if ct:
        bg.append(f"<b>CFTC 持倉</b>（{E(ct['mkt'])}，{ct['date']}）：非商業淨部位 {sgn(ct['net'])} 口（週變化 {sgn(ct['chg'])}），在近 3 年 {ct['n']} 週中位於第 {ct['pct']:.0f} 百分位")
    if code == "CL" and cache.get("eia"):
        e = cache["eia"]; bg.append(f"<b>EIA 商業原油庫存</b>（{E(e['week'])} 當週）：{e['v']:,.1f} 百萬桶，較前週 {sgn(e['chg'], 1)}")
    if code == "TX" and cache.get("inst"):
        i = cache["inst"]
        bg.append(f"<b>三大法人台指期未平倉淨口數</b>（{E(i['date'])}，FinMind／期交所）：" + "、".join(f"{w} {sgn(n)}" + (f"（{sgn(c)}）" if c is not None else "") for w, n, c in i["rows"]))
    if bg: out.append("<details><summary>背景資訊（不參與訊號）</summary><div class=bg>" + "<br>".join(bg) + "</div></details>")
    return "".join(out) + "</section>"

def write_board(R, st, cache, M, fx, t):
    by = {r["code"]: r for r in R}
    z1 = [by[k] for k in FIXED if k in by]
    act = [r for r in R if r["code"] not in FIXED and (r["side"] or r["cside"])]
    z2 = sorted(act, key=lambda r: (-r["nag"], -abs(r["cside"]), C[r["code"]][5]))
    z3 = [r for r in R if r["code"] not in FIXED and not (r["side"] or r["cside"])]
    cnt = {}
    for r in R: cnt[r["h"]["state"]] = cnt.get(r["h"]["state"], 0) + 1
    health = "｜".join(f"<span class={HEALTH[k][1]}>{HEALTH[k][0]} {cnt[k]}</span>" for k in ("ok", "closed", "diff", "stale", "nosrc") if cnt.get(k))
    bad = [r for r in R if r["h"]["state"] in ("diff", "stale")]
    badl = ("<div class='alert'>" + "<br>".join(f"{E(r['name'])} {r['code']}：{E(r['h']['note'])}" for r in bad) + "</div>") if bad else ""
    sys_t = "".join(f"<tr><td>{E(a)}</td><td>{E(b)}</td><td class=n>{c}</td><td><small>{E(d)}</small></td></tr>" for a, b, c, d in SYS_BT)
    risk_t = "".join(f"<tr><td>{a}</td>" + "".join(f"<td class=n>{x[0]:+.1f}% / <span class=r>{x[1]:.0f}%</span></td>" for x in (b, c, d)) + "</tr>" for a, b, c, d in RISK_BT)
    # 訊號變化紀錄
    lg = []
    for x in st.get("log", [])[::-1][:40]:
        r = by.get(x["code"])
        if not r: continue
        tk = r["tick"]
        now_px = r["last"] if x["sys"] == "趨勢" or not r["cv"] else r["cv"]["pa"]
        mv = "" if not x.get("px") else (now_px - x["px"]) / x["px"] * 100
        good = "" if mv == "" or not x["to"] else ("g" if mv * x["to"] >= 0 else "r")
        lg.append(f"<tr><td><small>{E(x['t'][5:16])}</small></td><td>{E(r['name'])}</td><td>{E(x['sys'])}</td><td>{'' if x['frm'] is None else lab(x['frm']) + ' → '}{side_html(x['to'])}</td>"
                  f"<td class=n>{fmt(x['px'], tk) if x.get('px') else '—'}</td><td class='n {good}'>{'' if mv == '' else f'{mv:+.2f}%'}</td></tr>")
    fxs = f"美元/台幣 {fx[0]:.3f}（Yahoo TWD=X {fx[1]:%m/%d}）" if fx[0] else ""
    doc = f"""<!DOCTYPE html><html lang=zh-Hant><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=300><title>期貨副駕</title><style>
:root{{color-scheme:light dark;--bg:light-dark(#fff,#0f1115);--ink:light-dark(#111,#e8e8e8);--mut:light-dark(#666,#9aa);--ln:light-dark(#e5e5e5,#262a33);--card:light-dark(#fafafa,#161a21);--l:#0a8f4a;--s:#d0342c;--w:#b7791f}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}}
main{{max-width:900px;margin:auto;padding:12px}}h1{{font-size:22px;margin:0}}h2{{font-size:17px;margin:22px 0 8px}}h4{{font-size:14px;margin:12px 0 4px}}
small,.m,.src{{color:var(--mut);font-size:12px}}.m{{margin:4px 0}}a{{color:inherit}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;white-space:nowrap}}td,th{{padding:6px 6px;border-bottom:1px solid var(--ln);text-align:left;vertical-align:top}}
th{{font-size:12px;color:var(--mut);font-weight:500}}.n{{text-align:right;font-variant-numeric:tabular-nums}}.l,.g{{color:var(--l)}}.s,.r{{color:var(--s)}}.z{{color:var(--mut)}}.w{{color:var(--w)}}
.card{{border:1px solid var(--ln);border-radius:12px;padding:12px;margin:10px 0;background:var(--card)}}.top{{display:flex;gap:6px;align-items:baseline}}.top b{{font-size:18px}}
.px{{margin-left:auto;font-size:18px;font-variant-numeric:tabular-nums}}.sg{{font-size:16px;margin:6px 0}}details{{margin-top:8px}}summary{{cursor:pointer;color:var(--mut);font-size:13px}}
.bg{{font-size:13px}}.bg ul{{margin:4px 0;padding-left:18px}}.alert{{border:1px solid var(--s);color:var(--s);border-radius:8px;padding:8px;margin:8px 0;font-size:13px}}
.mini td,.mini th{{font-size:12px;padding:4px;white-space:normal}}
.lot{{border-top:1px solid var(--ln);padding:8px 0}}.lg{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:4px 0}}.lg span{{font-size:11px;color:var(--mut)}}
.lg b{{display:block;font-size:15px;color:var(--ink);font-variant-numeric:tabular-nums}}.lg b.r{{color:var(--s)}}.ls{{font-size:12px}}
</style></head><body><main>
<h1>期貨副駕</h1><div class=m>更新 {t:%Y/%m/%d %H:%M}（台北）· 每 5 分鐘 · {E(fxs)}</div>
<div class=m>報價狀態：{health}</div>{badl}
<div class=scroll><table class=mini><tr><th>系統</th><th>規則</th><th class=n>樣本外 Sharpe</th><th>驗證</th></tr>{sys_t}</table></div>
<p class=m>Sharpe：pysystemtrade 回溯調整價，2010–2024/03 樣本外，39 檔（期限結構 19 檔）全做，已扣手續費與 1 跳滑價。</p>
<div class=scroll><table class=mini><tr><th>每筆風險</th><th class=n>趨勢 年化/最大回撤</th><th class=n>期限結構</th><th class=n>兩套各一份</th></tr>{risk_t}</table></div>
<p class=m>同一回測，每筆按資金的固定比例冒險、全部商品都做、沒有總風險上限（趨勢平均同時 34 筆、期限結構 18 筆）。只做少數商品時回撤會不同。</p>
<h2>主要商品</h2>{''.join(card(r, M, cache) for r in z1)}
<h2>其他有訊號的商品（{len(z2)}）</h2>{''.join(card(r, M, cache) for r in z2) or '<p class=m>沒有</p>'}
<details><summary>觀望中的商品（{len(z3)}）</summary>{''.join(card(r, M, cache) for r in z3)}</details>
<h2>訊號變化紀錄</h2><div class=scroll><table><tr><th>時間</th><th>商品</th><th>系統</th><th>變化</th><th class=n>當時價</th><th class=n>至今</th></tr>{''.join(lg) or '<tr><td colspan=6 class=z>還沒有變化</td></tr>'}</table></div>
<p class=m>「至今」綠色＝往新訊號方向走。期限結構的當時價／現價用主力月收盤。</p>
<h2>資料來源</h2><p class=m>美國期貨：Yahoo Finance（1 分K，延遲約 10 分；外匯與比特幣用 Yahoo 即時匯率補正），第二來源 TradingView（延遲 10 分），標普／那斯達克／道瓊另對照鉅亨網；
兩來源差超過 0.5% 或報價落後第二來源 30 分以上標紅。台指期與期交所商品：期交所 MIS（約 1 分）、日K 為 FinMind 期交所日行情。期限結構：Yahoo 各月份合約日K（每小時更新）。
背景資訊：金十數據快訊、CFTC 持倉報告（Legacy）、EIA 週報 Table 1、FinMind 三大法人。合約規格（跳動點、每跳金額）於 {SPEC_DATE} 逐一對照 CME 與期交所官網。</p>
</main></body></html>"""
    os.makedirs("docs", exist_ok=True)
    open("docs/index.html", "w", encoding="utf-8").write(doc)

if __name__ == "__main__":
    main()
