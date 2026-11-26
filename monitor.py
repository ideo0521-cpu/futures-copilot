# -*- coding: utf-8 -*-
"""期貨副駕｜雲端盯盤（GitHub Actions 每 5 分鐘執行）
- 規則、資料源與 Colab 版完全相同（程式核心直接取自 Colab 第 1 格）
- 有新機會／該平倉 → 推到手機 ntfy
- 每次執行都更新 docs/index.html → GitHub Pages 網頁，手機直接看"""
import os, json, time, math, html, urllib.request
import numpy as np, pandas as pd
CAPITAL = float(os.environ.get("CAPITAL") or 1000000)
RISK = float(os.environ.get("RISK_PCT") or 1)
TOTAL = float(os.environ.get("TOTAL_RISK_PCT") or 5)
通知頻道 = os.environ.get("NTFY_TOPIC", "")
STATE = "state.json"
TZ = "Asia/Taipei"
BOARD = []

# 規格：tick、每tick美元、微型(代號,tick,每tick美元)
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
 "ZC": ("玉米","ZC=F",.25,12.5,("XC",.125,1.25),"農產品","corn futures"),
 "ZS": ("黃豆","ZS=F",.25,12.5,("XK",.125,1.25),"農產品","soybean futures"),
 "ZW": ("小麥","ZW=F",.25,12.5,("XW",.125,1.25),"農產品","wheat futures"),
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
 "ZL": ("黃豆油","ZL=F",.01,6.0,None,"農產品","soybean oil"),
 "ZM": ("黃豆粉","ZM=F",.1,10.0,None,"農產品","soybean meal"),
 "CT": ("棉花","CT=F",.01,5.0,None,"農產品","cotton futures"),
 "SB": ("糖","SB=F",.01,11.2,None,"農產品","sugar futures"),
 "KC": ("咖啡","KC=F",.05,18.75,None,"農產品","coffee futures"),
 "CC": ("可可","CC=F",1.0,10.0,None,"農產品","cocoa futures"),
 "NKD": ("日經225","NKD=F",5.0,25.0,None,"指數","Nikkei 225"),
 "BTC": ("比特幣","BTC=F",5.0,25.0,("MBT",5.0,.5),"加密","bitcoin price"),
 "TX": ("台指","TXF",1.0,None,None,"台指","Taiwan stock market TAIEX"),
}
# 可下單合約（由大到小）：(代號, 說明, 跳動點, 每跳動金額, 幣別, 原始保證金)
# 期交所規格來源：期交所商品規格頁；保證金來源：ibff.com.tw 期交所保證金表（2026-11-23 取得，以期交所公告為準）
ALT = {
 "GC": [("GC","CME 黃金",.1,10,"USD",None),("MGC","CME 微型黃金",.1,1,"USD",None),("GDF","期交所 美元黃金 1盎司",.1,.1,"USD",560)],
 "ES": [("ES","CME 標普",.25,12.5,"USD",None),("SPF","期交所 美國標普500",.25,50,"TWD",103000),("MES","CME 微型標普",.25,1.25,"USD",None)],
 "NQ": [("NQ","CME 那斯達克",.25,5,"USD",None),("MNQ","CME 微型那斯達克",.25,.5,"USD",None),("UNF","期交所 美國那斯達克100",1,50,"TWD",98000)],
 "YM": [("YM","CME 道瓊",1,5,"USD",None),("UDF","期交所 美國道瓊",1,20,"TWD",64000),("MYM","CME 微型道瓊",1,.5,"USD",None)],
 "6E": [("6E","CME 歐元",.00005,6.25,"USD",None),("XEF","期交所 歐元兌美元",.0001,2,"USD",690),("M6E","CME 微型歐元",.0001,1.25,"USD",None)],
 "6B": [("6B","CME 英鎊",.0001,6.25,"USD",None),("XBF","期交所 英鎊兌美元",.0001,2,"USD",750),("M6B","CME 微型英鎊",.0001,.625,"USD",None)],
 "6A": [("6A","CME 澳幣",.00005,5,"USD",None),("XAF","期交所 澳幣兌美元",.0001,2.5,"USD",590),("M6A","CME 微型澳幣",.0001,1,"USD",None)],
 "TX": [("TX","期交所 大台",1,200,"TWD",701000),("MTX","期交所 小台",1,50,"TWD",175250),("TMF","期交所 微型台指",1,10,"TWD",35050)],
}
for _k, _v in C.items():
    if _k not in ALT:
        ALT[_k] = [(_k, "CME", _v[2], _v[3], "USD", None)] + ([(_v[4][0], "CME 微型", _v[4][1], _v[4][2], "USD", None)] if _v[4] else [])
# CME 原始保證金（美元）：NinjaTrader 保證金表 2026-08-31（券商與交易所會隨波動調整，下單前以你的券商為準）
MG_CME = {"GC":24630,"MGC":2473,"SI":36848,"SIL":7370,"HG":13200,"MHG":1320,"ES":28632,"MES":2863,"NQ":46473,"MNQ":4647,
          "YM":16989,"MYM":1699,"RTY":12257,"M2K":1226,"6E":2640,"M6E":231,"6J":3080,"MJY":264,"6B":2200,"M6B":187,"6A":2090,"M6A":193,
          "CL":8823,"MCL":885,"NG":3096,"MNG":312,"ZC":1210,"XC":242,"ZS":2310,"XK":484,"ZW":2145,"XW":429,"ZN":2063,"ZB":4070,
          "PL":9147,"PA":15715,"ZT":1320,"ZF":1375,"6C":1100,"MCD":88,"6S":4950,"MSF":396,"6M":1210,"6N":1540,"HO":13606,"HE":1870,"LE":3630,
          "ZL":2310,"ZM":1705,"NKD":25195,"BTC":94181,"MBT":1884}   # ICE 合約（DX、CT、SB、KC、CC）查無公開保證金
ALT = {k: [(pc, d, t, v, ccy, mg if mg else MG_CME.get(pc)) for pc, d, t, v, ccy, mg in lst] for k, lst in ALT.items()}
FXR = {"USD": 1.0, "TWD": 1 / 32.0}   # 執行時會用最新匯率覆蓋

# 回測實績：由下方「🔍 回測驗證」儲存格逐筆重算（pysystemtrade 換月調整資料，樣本外 2010-01～2024-03；台指為加權指數 2013～2026）
# 規則＝4條≥3同向進場、<3出場、固定停損3N、訊號隔天收盤成交（回測驗證 v2 的 A）；台指為開高低收版；n=交易數 win=勝率 aw/al=平均賺/賠(R) exp=每筆期望值(R) is_exp=樣本內期望值 worst=最差單(R) hold=平均持有天 up/dn=20日後同向比例
H = {"GC":{"n":132,"win":0.4,"aw":1.07,"al":-0.72,"exp":0,"is_exp":0.09,"worst":-2.61,"hold":21,"b_exp":0.01,"up":0.5,"dn":0.45},"SI":{"n":115,"win":0.26,"aw":1.79,"al":-0.79,"exp":-0.12,"is_exp":-0.21,"worst":-2.52,"hold":29,"b_exp":1.91,"up":0.45,"dn":0.5},"HG":{"n":136,"win":0.25,"aw":1.86,"al":-0.7,"exp":-0.06,"is_exp":0.95,"worst":-2.42,"hold":24,"b_exp":0.33,"up":0.49,"dn":0.45},"ES":{"n":90,"win":0.31,"aw":2.29,"al":-0.72,"exp":0.22,"is_exp":0.5,"worst":-1.65,"hold":38,"b_exp":0.37,"up":0.68,"dn":0.33},"NQ":{"n":88,"win":0.25,"aw":3.56,"al":-0.74,"exp":0.33,"is_exp":0.32,"worst":-2.21,"hold":38,"b_exp":0.09,"up":0.67,"dn":0.36},"YM":{"n":95,"win":0.27,"aw":2.63,"al":-0.76,"exp":0.17,"is_exp":0.09,"worst":-1.74,"hold":36,"b_exp":-0.27,"up":0.65,"dn":0.29},"RTY":{"n":87,"win":0.3,"aw":1.51,"al":-0.72,"exp":-0.06,"is_exp":None,"worst":-2.46,"hold":22,"b_exp":0.13,"up":0.58,"dn":0.38},"6E":{"n":97,"win":0.36,"aw":2.31,"al":-0.71,"exp":0.38,"is_exp":0.59,"worst":-1.95,"hold":34,"b_exp":0,"up":0.5,"dn":0.59},"6J":{"n":103,"win":0.25,"aw":4.21,"al":-0.86,"exp":0.42,"is_exp":0.16,"worst":-3.4,"hold":32,"b_exp":-0.33,"up":0.48,"dn":0.58},"6B":{"n":113,"win":0.32,"aw":2,"al":-0.7,"exp":0.16,"is_exp":0.19,"worst":-2.61,"hold":30,"b_exp":-0.36,"up":0.51,"dn":0.5},"6A":{"n":116,"win":0.4,"aw":1.28,"al":-0.67,"exp":0.1,"is_exp":0.33,"worst":-1.87,"hold":28,"b_exp":0.21,"up":0.49,"dn":0.52},"CL":{"n":112,"win":0.31,"aw":2.46,"al":-0.77,"exp":0.24,"is_exp":0.57,"worst":-1.77,"hold":30,"b_exp":-0.23,"up":0.54,"dn":0.43},"NG":{"n":95,"win":0.28,"aw":2.43,"al":-0.73,"exp":0.17,"is_exp":0.39,"worst":-1.98,"hold":32,"b_exp":-0.27,"up":0.43,"dn":0.6},"ZC":{"n":74,"win":0.27,"aw":2.78,"al":-0.84,"exp":0.14,"is_exp":-0.04,"worst":-2.87,"hold":46,"b_exp":-0.34,"up":0.54,"dn":0.55},"ZS":{"n":156,"win":0.33,"aw":1.65,"al":-0.75,"exp":0.03,"is_exp":0.04,"worst":-2.08,"hold":21,"b_exp":-0.26,"up":0.5,"dn":0.42},"ZW":{"n":78,"win":0.23,"aw":2.53,"al":-0.7,"exp":0.05,"is_exp":0.43,"worst":-2.25,"hold":42,"b_exp":-0.31,"up":0.48,"dn":0.58},"ZN":{"n":99,"win":0.37,"aw":2.57,"al":-0.7,"exp":0.52,"is_exp":0.57,"worst":-1.49,"hold":34,"b_exp":-0.35,"up":0.56,"dn":0.5},"ZB":{"n":99,"win":0.26,"aw":3.15,"al":-0.68,"exp":0.32,"is_exp":None,"worst":-1.68,"hold":32,"b_exp":-0.25,"up":0.54,"dn":0.52},"PL":{"n":139,"win":0.32,"aw":1.09,"al":-0.74,"exp":-0.16,"is_exp":0.19,"worst":-2.02,"hold":23,"b_exp":0.22,"up":0.42,"dn":0.47},"PA":{"n":107,"win":0.25,"aw":2.21,"al":-0.78,"exp":-0.03,"is_exp":1.5,"worst":-1.9,"hold":28,"b_exp":-0.27,"up":0.59,"dn":0.49},"DX":{"n":85,"win":0.4,"aw":2.72,"al":-0.78,"exp":0.62,"is_exp":0.51,"worst":-2.78,"hold":41,"b_exp":None,"up":0.57,"dn":0.51},"ZT":{"n":118,"win":0.27,"aw":5.19,"al":-0.73,"exp":0.87,"is_exp":0.8,"worst":-2.68,"hold":27,"b_exp":0.54,"up":0.52,"dn":0.57},"ZF":{"n":89,"win":0.3,"aw":4.37,"al":-0.65,"exp":0.87,"is_exp":0.82,"worst":-1.63,"hold":36,"b_exp":-0.15,"up":0.57,"dn":0.53},"6C":{"n":142,"win":0.3,"aw":1.18,"al":-0.77,"exp":-0.19,"is_exp":0.24,"worst":-2.17,"hold":23,"b_exp":-0.26,"up":0.46,"dn":0.5},"6S":{"n":132,"win":0.24,"aw":1.31,"al":-0.79,"exp":-0.28,"is_exp":0.31,"worst":-6.68,"hold":25,"b_exp":0.12,"up":0.46,"dn":0.47},"6M":{"n":115,"win":0.34,"aw":1.53,"al":-0.84,"exp":-0.04,"is_exp":0.14,"worst":-5.24,"hold":28,"b_exp":2.54,"up":0.58,"dn":0.45},"6N":{"n":124,"win":0.33,"aw":1.2,"al":-0.69,"exp":-0.06,"is_exp":0.12,"worst":-1.45,"hold":26,"b_exp":-0.35,"up":0.48,"dn":0.46},"HO":{"n":144,"win":0.26,"aw":2.56,"al":-0.73,"exp":0.13,"is_exp":0.34,"worst":-2.27,"hold":23,"b_exp":0.03,"up":0.53,"dn":0.45},"HE":{"n":114,"win":0.27,"aw":2.86,"al":-0.8,"exp":0.2,"is_exp":0.3,"worst":-2.03,"hold":29,"b_exp":-0.52,"up":0.56,"dn":0.47},"LE":{"n":131,"win":0.27,"aw":1.71,"al":-0.7,"exp":-0.04,"is_exp":0.06,"worst":-1.77,"hold":25,"b_exp":0.54,"up":0.56,"dn":0.43},"ZL":{"n":129,"win":0.29,"aw":1.97,"al":-0.77,"exp":0.04,"is_exp":0.18,"worst":-1.98,"hold":26,"b_exp":0.86,"up":0.46,"dn":0.52},"ZM":{"n":132,"win":0.24,"aw":1.84,"al":-0.75,"exp":-0.13,"is_exp":-0.03,"worst":-2.66,"hold":25,"b_exp":0.05,"up":0.47,"dn":0.45},"CT":{"n":91,"win":0.36,"aw":3.34,"al":-0.85,"exp":0.67,"is_exp":0.25,"worst":-1.91,"hold":36,"b_exp":0.75,"up":0.56,"dn":0.44},"SB":{"n":119,"win":0.34,"aw":1.84,"al":-0.76,"exp":0.13,"is_exp":0.41,"worst":-1.85,"hold":27,"b_exp":-0.08,"up":0.48,"dn":0.54},"KC":{"n":90,"win":0.36,"aw":2.53,"al":-0.84,"exp":0.36,"is_exp":-0.35,"worst":-2.07,"hold":38,"b_exp":-0.15,"up":0.52,"dn":0.62},"CC":{"n":157,"win":0.2,"aw":4.24,"al":-0.76,"exp":0.23,"is_exp":-0.09,"worst":-1.54,"hold":21,"b_exp":-0.17,"up":0.52,"dn":0.44},"NKD":{"n":103,"win":0.23,"aw":2.54,"al":-0.77,"exp":0,"is_exp":None,"worst":-2.96,"hold":27,"b_exp":0.28,"up":0.6,"dn":0.31},"BTC":{"n":46,"win":0.22,"aw":6.19,"al":-0.9,"exp":0.64,"is_exp":None,"worst":-3.25,"hold":27,"b_exp":0.71,"up":0.53,"dn":0.38},"TX":{"n":73,"win":0.23,"aw":6.13,"al":-0.6,"exp":0.97,"is_exp":0.1,"worst":-1.24,"hold":43,"b_exp":None,"up":0.63,"dn":0.37}}
# 帳戶層級與新資料檢查（回測驗證 v5 的結果；第二格重跑後會自動改用新結果）
ACCS = {"ACC":{"0.001":{"oos":{"CAGR":0.04,"maxDD":0.177},"ins":{"CAGR":0.053,"maxDD":0.169}},"0.0015":{"oos":{"CAGR":0.058,"maxDD":0.263},"ins":{"CAGR":0.077,"maxDD":0.249}},"0.0025":{"oos":{"CAGR":0.088,"maxDD":0.424},"ins":{"CAGR":0.123,"maxDD":0.396}},"0.005":{"oos":{"CAGR":0.129,"maxDD":0.732},"ins":{"CAGR":0.211,"maxDD":0.682}},"0.01":{"oos":{"CAGR":0.045,"maxDD":0.97},"ins":{"CAGR":0.245,"maxDD":0.945}}},"CAP":{"oos":{"CAGR":0.032,"maxDD":0.142},"ins":{"CAGR":0.048,"maxDD":0.105}},"B":{"2013–2024/03":{"sharpe":0.34,"exp":0.11,"acc":{"CAGR":0.03,"maxDD":0.295}},"2024/04–今天":{"sharpe":-0.13,"exp":-0.05,"acc":{"CAGR":-0.02,"maxDD":0.161}}},"RADAR":{"強力多空(2ATR停損/4ATR停利) 2013–2024/03":{"n":2502,"win":0.35,"exp":0.02},"強力多空(2ATR停損/4ATR停利) 2024/04–今天":{"n":605,"win":0.34,"exp":0},"壓縮突破(上軌掛單/20MA停損/2倍停利) 2013–2024/03":{"n":756,"win":0.38,"exp":0.06},"壓縮突破(上軌掛單/20MA停損/2倍停利) 2024/04–今天":{"n":171,"win":0.37,"exp":0.08}}}
STATS_SRC = "內建數字（與回測驗證 v5 於 2026-11-23 19:36 執行結果一致）"
try:
    _j = json.load(open("/content/copilot_stats.json", encoding="utf-8"))
    H, ACCS = _j["H"], _j; STATS_SRC = f"回測驗證儲存格 {_j['time']} 的執行結果"
except Exception:
    pass
RULES = [
 ("TSMOM 252日", "收盤 > 252日前收盤 → 多，反之空", "Moskowitz, Ooi & Pedersen (2012) Time Series Momentum, JFE；Hurst, Ooi & Pedersen (AQR 2017) A Century of Evidence on Trend-Following", "0.90 / 0.74"),
 ("TSMOM 126日", "收盤 > 126日前收盤 → 多，反之空", "同上（6個月回看期）", "0.46 / 0.71"),
 ("價格 vs 200日均線", "收盤 > SMA200 → 多，反之空", "Brock, Lakonishok & LeBaron (1992) Journal of Finance；Murphy《金融市場技術分析》第9章", "0.57 / 0.66"),
 ("2日 vs 200日均線", "SMA2 > SMA200 → 多，反之空", "Brock, Lakonishok & LeBaron (1992) 的 (1,200)/(2,200) 變形", "0.60 / 0.65"),
]
FAILED = "v2/v3 的『翻轉價當停損』（回測虧損單平均是停損的2.5倍、最差57倍，已改為固定3N停損）、舊版多週期評分(樣本外Sharpe 0.03)、TSMOM 21日、海龜20日突破、EMA 5/8/13、MACD訊號線、RSI(2)、布林通道、ADX/DMI(-0.30)、拋物線SAR(-0.01)、NR7(-0.76)、一目均衡表(0.03)、61種K線型態(88組中61組樣本外虧損)"

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
    dec = max(0, -int(math.floor(math.log10(t)))) if t < 1 else 0
    return f"{x:,.{min(dec,7)}f}"

def bar_done(code, idx):
    """哪些日K已經收盤。台指期：日盤 13:45 收（台北時間）。美國期貨：Yahoo 以交易日標日期，當天 17:00 美東（冬令 22:00 UTC）才收，
    台北凌晨 0–6 點那根還在交易中，不能當成已收盤。"""
    d = pd.DatetimeIndex(idx).normalize()
    if code == "TX":
        now = pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None)
        return (d + pd.Timedelta(hours=13, minutes=50)) <= now
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return (d + pd.Timedelta(hours=22, minutes=5)) <= now

def analyze(code, cap_usd, risk_pct):
    name, ysym, tick, tv, micro, grp, q = C[code]
    tick = ALT[code][-1][2] if code == "TX" else tick
    D = fetch(ysym, "3y", "1d")
    if D is None or len(D) < 300: return dict(code=code, name=name, err="抓不到日線資料")
    live = fetch(ysym, "1d", "1m")
    last = float(live["Close"].iloc[-1]) if live is not None and len(live) else float(D["Close"].iloc[-1])
    t_ = live.index[-1] if live is not None and len(live) else D.index[-1]
    if live is not None and len(live): last, t_ = rt_adjust(code, last, t_)   # 用即時的代理報價把 10 分鐘延遲補到現在
    ts = t_.strftime("%m/%d %H:%M")
    Dc = D[bar_done(code, D.index)]                                       # 只用已收盤日K
    p = Dc["Close"]   # 用盤面原始收盤（和你看圖一致）
    c = p.values
    sig = {"TSMOM 252日": np.sign(c[-1] - c[-253]), "TSMOM 126日": np.sign(c[-1] - c[-127]),
           "價格 vs 200日均線": np.sign(c[-1] - c[-200:].mean()), "2日 vs 200日均線": np.sign(c[-2:].mean() - c[-200:].mean())}
    cons = float(np.mean(list(sig.values())))
    side = 1 if cons >= 0.5 else (-1 if cons <= -0.5 else 0)
    lv = flip_levels(p)
    h = H[code]
    r = dict(nag=int(sum(1 for v in sig.values() if v == side)), code=code, name=name, grp=grp, last=last, ts=ts, close=c[-1], close_date=Dc.index[-1].strftime("%m/%d"),
             sig=sig, cons=cons, side=side, lv=lv, h=h, tick=tick, edge=True)   # 系統優勢來自全部商品一起做，不挑個別商品（個別商品樣本少、雜訊大）
    if side == 0: return r
    agree = sorted([lv[k] for k, v in sig.items() if v == side], reverse=(side == 1))
    agree = [x for x in agree if (x < last if side == 1 else x > last)]
    n = int(sum(1 for v in sig.values() if v == side))
    xref = agree[n - 3] if len(agree) >= n - 2 and n >= 3 else None      # 趨勢出場參考：收盤穿越會讓同向條數 <3
    dpx = p.diff(); sdx = dpx.rolling(60, min_periods=20).std().shift(1)
    dpx = dpx.where(~(dpx.abs() > 6 * sdx), 0.0)                          # 換月跳空不計入波動
    N = float(dpx.abs().ewm(span=20, adjust=False).mean().iloc[-1])      # N ≈ 20日平均收盤變動（海龜 N）
    stop = rnd(last - side * 3 * N, tick)                                 # 固定停損 3N（回測驗證儲存格的設定）
    dist = abs(last - stop)
    budget = cap_usd * risk_pct / 100
    cands = []
    for pc, desc, t, v, ccy, mg in ALT[code]:
        vu = v * FXR[ccy]                                  # 每跳動換成美元
        per = dist / t * vu + 2 * 2.5 + vu                 # 停損點數 + 來回手續費 + 1 tick 滑價（美元）
        if ccy == "TWD": per += 2 * 2e-5 * last * (v / t) * FXR["TWD"]   # 期交所期交稅 十萬分之二（來回）
        k = int(budget // per)
        mg_u = mg * FXR[ccy] if mg else None
        if mg_u: k = min(k, int(cap_usd // mg_u))          # 保證金也要付得起
        cands.append(dict(prod=pc, desc=desc, per=per, k=max(0, k), mg=mg, ccy=ccy))
    ok_c = [x for x in cands if x["k"] >= 1]
    pick = ok_c[0] if ok_c else min(cands, key=lambda x: x["per"])
    k = pick["k"] if ok_c else 0
    r.update(stop=stop, N=N, xref=(rnd(xref, tick) if xref is not None else None), dist=dist, prod=pick["prod"], pdesc=pick["desc"], lots=k, per=pick["per"], maxloss=k * pick["per"],
             mg=pick["mg"], mgccy=pick["ccy"], expm=k * pick["per"] * h["exp"], worstm=k * pick["per"] * h["worst"], dist_pct=dist / last * 100,
             alts=" / ".join(x["prod"] for x in cands))
    return r


def push(text, st):
    print(text)                                            # 這格下方也會顯示
    if not 通知頻道.strip(): return True
    title, _, body = text.partition("\n")
    body = body.encode()[:3900].decode(errors="ignore")    # ntfy 單則上限 4096 bytes
    req = urllib.request.Request("https://ntfy.sh", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"topic": 通知頻道.strip(), "title": title, "message": body, "priority": 4}).encode())
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status == 200
    except Exception as e:
        print("手機通知失敗：", e); return False

def money(twd): return f"{twd:,.0f} 元"

def main():
    st = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    st.setdefault("pos", {}); st.setdefault("ledger", [])
    now = pd.Timestamp.now(tz=TZ)
    t = fetch("TWD=X", "5d", "1d"); fx = float(t["Close"].iloc[-1]) if t is not None else 32.0
    FXR["TWD"] = 1 / fx; cap_usd = CAPITAL / fx
    first = not st.get("started")
    new, closed = [], []
    for code in C:
        try: r = analyze(code, cap_usd, RISK)
        except Exception as e: print(code, "分析失敗", e); continue
        if r.get("err"): continue
        BOARD.append(r)
        name, tick = C[code][0], C[code][2]
        p = st["pos"].get(code)
        if p:
            d = fetch(C[code][1], "1mo", "15m"); lo = hi = r["last"]         # 現價＋進場「之後」每 15 分鐘K的最高最低價
            if d is not None and len(d):
                ix = d.index.tz_convert(TZ) if d.index.tz is not None else d.index.tz_localize(TZ)   # 抓資料時已換成台北時間
                d = d[ix > pd.Timestamp(p.get("t0") or p["d0"] + " 00:00+08:00")]
                if len(d): lo, hi = min(lo, float(d["Low"].min())), max(hi, float(d["High"].max()))
            hit = (p["side"] == 1 and lo <= p["stop"]) or (p["side"] == -1 and hi >= p["stop"])
            if hit or r["side"] != p["side"]:
                px = p["stop"] if hit else r["last"]
                R = -1.0 if hit else (p["side"] * (px - p["entry"]) / abs(p["entry"] - p["stop"]) if p["entry"] != p["stop"] else 0.0)
                pnl = round(R * p.get("risk", 0))
                if p.get("risk"):      # 只有真的下單的才通知
                    why = "碰到停損，認賠" if hit else "趨勢結束"
                    closed.append(f"・{name}：{why}，在 {fmt(px, tick)} 平倉，這筆{'賺' if pnl >= 0 else '虧'} {money(abs(pnl))}")
                    st["ledger"].append(dict(code=code, d1=str(now.date()), pnl=pnl))
                del st["pos"][code]; p = None
                if hit: st.setdefault("cool", {})[code] = str(now.date())   # 回測規則：停損後隔天才可再進場
        if not p and r["side"] and r.get("stop") is not None and st.get("cool", {}).get(code) != str(now.date()):
            used = sum(v.get("risk", 0) for v in st["pos"].values())
            used_mg = sum(v.get("margin", 0) for v in st["pos"].values() if v.get("risk"))
            mg = (r.get("mg") or 0) * r["lots"] * FXR[r.get("mgccy") or "USD"] * fx          # 這筆要押的保證金（台幣）
            ok = r["lots"] > 0 and used + r["maxloss"] * fx <= CAPITAL * TOTAL / 100 and used_mg + mg <= CAPITAL * 0.5   # 保證金最多用一半資金
            st["pos"][code] = dict(side=r["side"], entry=r["last"], stop=r["stop"], d0=str(now.date()), t0=str(now), prod=r["prod"], lots=r["lots"],
                                   risk=round(r["maxloss"] * fx) if ok else 0, margin=round(mg) if ok else 0)
            if ok:
                up = r["side"] == -1
                new.append(f"・{name}：{'做空' if up else '做多'} {r['prod']} {r['lots']} 口，現在價格 {fmt(r['last'], tick)}\n"
                           f"　{'漲' if up else '跌'}到 {fmt(r['stop'], tick)} 就認賠，最多虧 {money(r['maxloss'] * fx)}")
    led = pd.DataFrame(st["ledger"])
    month = int(led[led.d1.str[:7] == now.strftime("%Y-%m")].pnl.sum()) if len(led) else 0
    hold = {k: v for k, v in st["pos"].items() if v.get("risk")}
    risk_now = sum(v["risk"] for v in hold.values())
    head = f"📈 期貨提醒 {now:%m/%d %H:%M}"
    foot = f"目前手上 {len(hold)} 筆，全部停損最多虧 {money(risk_now)}（資金的 {risk_now / CAPITAL:.1%}）｜這個月損益 {month:+,} 元"
    if first:
        st["started"] = str(now)
        push(head + "\n✅ 開始幫你盯盤（每 5 分鐘看一次）\n\n"
             + (f"現在可以做的 {len(new)} 筆：\n" + "\n".join(new) if new else "現在沒有你資金做得起的機會。")
             + f"\n\n其他商品資金不夠一口，不用理。\n之後只有「新機會」或「該平倉」才會通知你。\n{foot}", st)
    elif new or closed:
        msg = [head]
        if closed: msg += ["🔔 該平倉了（先處理）"] + closed
        if new: msg += ["🆕 新機會"] + new
        push("\n".join(msg + ["", foot]), st)
    if now.hour == 8 and st.get("last_summary") != str(now.date()):
        st["last_summary"] = str(now.date())
        lines = [f"・{C[k][0]}：{'空' if v['side'] == -1 else '多'} {v['prod']} {v['lots']} 口，停損 {fmt(v['stop'], C[k][2])}" for k, v in hold.items()]
        push(head + "\n☀️ 早安，目前持倉：\n" + ("\n".join(lines) if lines else "沒有持倉") + f"\n\n{foot}", st)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_board(st, now, fx)
    print(f"（{now:%H:%M} 檢查完成：新機會 {len(new)}、平倉 {len(closed)}）")


def write_board(st, now, fx):
    E = html.escape
    hold = {k: v for k, v in st["pos"].items() if v.get("risk")}
    last = {r["code"]: r for r in BOARD}
    def pnl(k, v):
        r = last.get(k)
        if not r or v["entry"] == v["stop"]: return None
        return v["side"] * (r["last"] - v["entry"]) / abs(v["entry"] - v["stop"]) * v["risk"]
    rows_h = []
    for k, v in hold.items():
        r = last.get(k, {}); t = C[k][2]; px = r.get("last")
        gap = abs(px - v["stop"]) / px * 100 if px else None
        u = pnl(k, v)
        rows_h.append(f"<tr><td>{E(C[k][0])}</td><td class={'s' if v['side']<0 else 'l'}>{'空' if v['side']<0 else '多'} {E(v['prod'])}×{v['lots']}</td>"
                      f"<td class=n>{fmt(v['entry'], t)}</td><td class=n>{fmt(px, t) if px else '—'}</td><td class=n>{fmt(v['stop'], t)}</td>"
                      f"<td class=n>{'' if gap is None else f'{gap:.1f}%'}</td><td class='n {'g' if (u or 0)>=0 else 'r'}'>{'' if u is None else f'{u:+,.0f}'}</td></tr>")
    rows_a = []
    for r in sorted(BOARD, key=lambda r: (-(abs(r["side"])), C[r["code"]][5])):
        t = r["tick"]; sd = r["side"]
        tag = "多" if sd > 0 else ("空" if sd < 0 else "觀望")
        can = (f"{E(r['prod'])}×{r['lots']}" if r.get("lots") else "資金不足") if sd else ""
        rows_a.append(f"<tr><td>{E(r['name'])} <small>{E(r['code'])}</small></td><td class={'l' if sd>0 else ('s' if sd<0 else 'z')}>{tag}{f" {r['nag']}/4" if sd else ''}</td>"
                      f"<td class=n>{fmt(r['last'], t)}</td><td class=n>{fmt(r['stop'], t) if r.get('stop') is not None else ''}</td><td>{can}</td><td class=n><small>{E(r['ts'])}</small></td></tr>")
    led = st["ledger"][-15:][::-1]
    rows_l = "".join(f"<tr><td>{E(x['d1'])}</td><td>{E(C.get(x['code'], (x['code'],))[0])}</td><td class='n {'g' if x['pnl']>=0 else 'r'}'>{x['pnl']:+,}</td></tr>" for x in led)
    month = sum(x["pnl"] for x in st["ledger"] if x["d1"][:7] == now.strftime("%Y-%m"))
    risk_now = sum(v["risk"] for v in hold.values())
    doc = f"""<!DOCTYPE html><html lang=zh-Hant><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=120><title>期貨副駕</title><style>
:root{{color-scheme:light dark;--bg:light-dark(#fff,#0f1115);--ink:light-dark(#111,#e8e8e8);--mut:light-dark(#666,#9aa);--ln:light-dark(#e5e5e5,#262a33);--l:#0a8f4a;--s:#d0342c}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}}
main{{max-width:900px;margin:auto;padding:16px}}h1{{font-size:22px;margin:0}}h2{{font-size:17px;margin:22px 0 6px}}
.kp{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}}.kp div{{border:1px solid var(--ln);border-radius:10px;padding:10px}}
.kp b{{display:block;font-size:20px}}.kp span,small,.m{{color:var(--mut);font-size:12px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;white-space:nowrap}}td,th{{padding:7px 6px;border-bottom:1px solid var(--ln);text-align:left}}
th{{font-size:12px;color:var(--mut);font-weight:500}}.n{{text-align:right;font-variant-numeric:tabular-nums}}.l,.g{{color:var(--l)}}.s,.r{{color:var(--s)}}.z{{color:var(--mut)}}
</style></head><body><main>
<h1>期貨副駕</h1><div class=m>更新 {now:%m/%d %H:%M}（台北）｜每 5 分鐘自動更新｜美國期貨報價晚約 10 分鐘，外匯／比特幣已補正，台指期約 1 分鐘</div>
<div class=kp><div><span>手上</span><b>{len(hold)} 筆</b></div><div><span>全部停損最多虧</span><b>{risk_now:,.0f}</b><span>資金的 {risk_now/CAPITAL:.1%}</span></div><div><span>本月損益</span><b class={'g' if month>=0 else 'r'}>{month:+,}</b></div></div>
<h2>目前持倉</h2><div class=scroll><table><tr><th>商品</th><th>部位</th><th class=n>進場</th><th class=n>現價</th><th class=n>停損</th><th class=n>距停損</th><th class=n>未實現(元)</th></tr>{''.join(rows_h) or '<tr><td colspan=7 class=z>沒有持倉</td></tr>'}</table></div>
<h2>全部 {len(BOARD)} 檔訊號</h2><div class=scroll><table><tr><th>商品</th><th>方向/同意</th><th class=n>現價</th><th class=n>停損</th><th>你做得起</th><th class=n>報價時間</th></tr>{''.join(rows_a)}</table></div>
<h2>最近平倉</h2><div class=scroll><table><tr><th>日期</th><th>商品</th><th class=n>損益(元)</th></tr>{rows_l or '<tr><td colspan=3 class=z>還沒有</td></tr>'}</table></div>
<p class=m>規則：4 條長週期趨勢規則有 3 條以上同方向就進場，固定 3N 停損，同方向少於 3 條就出場。每筆風險 {RISK:g}%、總風險上限 {TOTAL:g}%、資金 {CAPITAL:,.0f} 元。</p>
</main></body></html>"""
    os.makedirs("docs", exist_ok=True)
    open("docs/index.html", "w", encoding="utf-8").write(doc)

if __name__ == "__main__":
    main()
