import warnings; warnings.filterwarnings("ignore")
import io, re, json, time, requests, numpy as np, pandas as pd, yfinance as yf
import monitor as M
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}
now = pd.Timestamp.now(tz="Asia/Taipei"); print("試算時間（台北）", now.strftime("%Y-%m-%d %H:%M"))
CAP, BUD = 1_000_000, 5_000
fx = float(yf.Ticker("TWD=X").history(period="5d").Close.iloc[-1]); M.FXR["TWD"] = 1 / fx; print("美元兌台幣", round(fx, 3))
# ── 1. 保證金：NinjaTrader（CME/ICE 原始保證金）＋ 期交所官方 ──
def nt_margins():
    out = {}
    for q in ["", "?text=micro"]:
        r = requests.get("https://ninjatrader.com/pricing/margins/" + q, headers=H, timeout=30)
        for t in pd.read_html(io.StringIO(r.text)):
            cols = [str(c) for c in t.columns]
            if "Symbol" in cols and "Initial" in cols:
                for _, x in t.iterrows():
                    try: out[str(x["Symbol"]).strip()] = float(str(x["Initial"]).replace("$", "").replace(",", ""))
                    except: pass
    return out
try: NT = nt_margins(); print("NinjaTrader 保證金筆數", len(NT), {k: NT.get(k) for k in ["MCL", "CL", "MGC", "M6E", "MES"]})
except Exception as e: NT = {}; print("NinjaTrader 失敗", e)
def taifex_margins():
    out = {}
    for u in ["https://www.taifex.com.tw/cht/5/indexMarging", "https://www.taifex.com.tw/cht/5/commodityMarging", "https://www.taifex.com.tw/cht/5/currencyMarging", "https://www.taifex.com.tw/cht/5/stockMarging"]:
        try:
            r = requests.get(u, headers=H, timeout=30); r.encoding = "utf-8"
            for t in pd.read_html(io.StringIO(r.text)):
                s = t.astype(str).to_string()
                for nm, code in [("臺股期貨", "TX"), ("小型臺指", "MTX"), ("微型臺指", "TMF"), ("黃金期貨", "GDF"), ("歐元兌美元", "XEF"), ("英鎊兌美元", "XBF"), ("澳幣兌美元", "XAF"), ("美國標普500", "SPF"), ("美國那斯達克100", "UNF"), ("美國道瓊", "UDF")]:
                    for _, row in t.iterrows():
                        v = [str(a) for a in row.values]
                        if any(nm in a for a in v):
                            nums = [float(a.replace(",", "")) for a in v if re.fullmatch(r"[\d,]+(\.\d+)?", a.replace(" ", ""))]
                            if nums and code not in out: out[code] = (nums, u.split("/")[-1])
        except Exception as e: print("期交所頁面失敗", u, e)
    return out
TF = taifex_margins(); print("期交所官方保證金（數字欄＝結算/維持/原始）", TF)
# ── 2. 目前期限結構（商品類）：Yahoo 各月份合約，取最近兩個有成交的月份 ──
SUF = {"CL": "NYM", "NG": "NYM", "HO": "NYM", "PL": "NYM", "PA": "NYM", "GC": "CMX", "SI": "CMX", "HG": "CMX",
       "ZC": "CBT", "ZS": "CBT", "ZW": "CBT", "ZL": "CBT", "ZM": "CBT", "CT": "NYB", "SB": "NYB", "KC": "NYB", "CC": "NYB", "HE": "CME", "LE": "CME"}
MC = "FGHJKMNQUVXZ"
def curve(code):
    pts = []
    y, m = now.year, now.month
    for i in range(0, 16):
        mm = (m - 1 + i) % 12; yy = y + (m - 1 + i) // 12
        s = f"{code}{MC[mm]}{str(yy)[2:]}.{SUF[code]}"
        try:
            d = yf.Ticker(s).history(period="10d", interval="1d")
            if len(d) and (now.tz_localize(None) - d.index[-1].tz_localize(None)).days <= 6 and d.Volume.iloc[-3:].sum() > 0:
                pts.append((yy * 12 + mm, s, float(d.Close.iloc[-1]), int(d.Volume.iloc[-1])))
        except Exception: pass
        if len(pts) >= 2: break
    if len(pts) < 2: return None
    (m1, s1, p1, _), (m2, s2, p2, _) = pts[0], pts[1]
    ann = (p1 - p2) / p1 * 12 / (m2 - m1)
    return dict(near=s1, p1=p1, far=s2, p2=p2, ann=ann, side=int(np.sign(ann)))
# ── 3. 逐檔試算 ──
rows, book = [], []
for code in M.C:
    r = M.analyze(code, CAP / fx, 0.5)                # 0.5% = 5,000 元
    if r.get("err"): rows.append(dict(商品=f"{M.C[code][0]} {code}", 判定="暫時排除：" + r["err"])); continue
    last, N = r["last"], r["N"]; dist = 3 * N
    cv = curve(code) if code in SUF else None
    alts = sorted(M.ALT[code], key=lambda a: (a[1].startswith("期交所"), -0))     # CME 優先
    best = None
    for pc, desc, t, v, ccy, mg0 in alts:
        vu = v * M.FXR[ccy]
        per = (dist / t * vu + 2 * 2.5 + vu) * fx
        if ccy == "TWD": per += 2 * 2e-5 * last * (v / t)
        mg = NT.get(pc) if not desc.startswith("期交所") else None
        if desc.startswith("期交所") and pc in TF: mg = TF[pc][0][-1] / (fx if ccy == "USD" and TF[pc][0][-1] > 5000 else 1) if ccy == "TWD" else TF[pc][0][-1]
        mg_twd = mg * fx if (mg is not None and ccy == "USD") else mg
        lots = int(BUD // per)
        cand = dict(prod=pc, desc=desc, per=round(per), mg=None if mg_twd is None else round(mg_twd), lots=lots)
        if lots >= 1 and best is None: best = cand
    smallest = min(({"prod": a[0], "per": round(((dist / a[2] * a[3] * M.FXR[a[4]]) + 5 + a[3] * M.FXR[a[4]]) * fx)} for a in alts), key=lambda x: x["per"])
    pick = best or smallest
    ts = r["side"]; cs = cv["side"] if cv else None
    if best is None: verdict = f"資金不足（最小 {smallest['prod']} 一口風險 {smallest['per']:,}）"
    elif best["mg"] is None: verdict = "暫時排除：查不到保證金"
    else: verdict = "可交易"
    rows.append(dict(商品=f"{M.C[code][0]} {code}", 趨勢=("多" if ts > 0 else "空" if ts < 0 else "觀望"),
                     期限結構=("—（不適用）" if code not in SUF else ("查無曲線" if cv is None else ("多（逆價差 %+.1f%%/年）" % (cv["ann"] * 100) if cs > 0 else "空（正價差 %+.1f%%/年）" % (cv["ann"] * 100)))),
                     合約=pick["prod"], 一口保證金=pick.get("mg"), 一口3N停損風險=pick["per"], 每系統可做口數=pick.get("lots", 0), 判定=verdict))
    if best and best["mg"] is not None:
        for sysn, sd in [("趨勢", ts), ("期限", cs if code in SUF else 0)]:
            if sd: book.append(dict(code=code, sys=sysn, side=sd, lots=best["lots"], risk=best["lots"] * best["per"], mg=best["lots"] * best["mg"]))
T = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print("\n" + T.to_string(index=False))
B = pd.DataFrame(book)
if len(B):
    print("\n=== 依今天訊號，兩系統全部進場時 ===")
    print(B.to_string(index=False))
    g = B.groupby("code").apply(lambda x: pd.Series(dict(gross_mg=x.mg.sum(), net_lots=(x.side * x.lots).sum(), lots=x.lots.iloc[0], mg1=x.mg.iloc[0] / x.lots.iloc[0])))
    net_mg = float((g.net_lots.abs() * g.mg1).sum())
    print(f"總停損風險 {B.risk.sum():,.0f} 元（上限 5% = 50,000）｜保證金：分開計 {B.mg.sum():,.0f} 元、同商品合併淨部位後 {net_mg:,.0f} 元（上限 50% = 500,000）")
