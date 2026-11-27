#@title 🔍 回測驗證 v5（38 檔＋台指＋戰情雷達；按 ▶：從 GitHub＋Yahoo 下載資料，逐筆重算副駕用的所有數字，約 3–4 分鐘）
# A. 1990–2024/03：pysystemtrade 換月調整日收盤（github.com/pst-group/pysystemtrade；該資料 2024/03 後未更新）
#    只有收盤價 → 訊號當天收盤產生、「隔天收盤」成交；停損以收盤檢查、收盤成交
# B. 2013–今天：Yahoo 日K（開高低收）→ 訊號隔天「開盤」成交；停損用盤中高低價，跳空穿越以開盤價成交
#    Yahoo 連續合約未做換月調整，換月跳空會混入損益（B 只用來檢查 2024/03 之後新資料的方向是否一致）
# 成本：每口來回 2×0.5 tick + 2×US$2.5；R = 每口初始風險；帳戶模擬＝每筆進場風險為帳戶固定比例、所有訊號同時持有、逐日複利
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, json, os, io, urllib.request
INST = {"GC": ("GOLD", .1, 100), "SI": ("SILVER", .005, 5000), "HG": ("COPPER", .0005, 25000),
        "ES": ("SP500", .25, 50), "NQ": ("NASDAQ", .25, 20), "YM": ("DOW", 1, 5), "RTY": ("RUSSELL", .1, 50),
        "6E": ("EUR", .00005, 125000), "6J": ("JPY", .0000005, 12500000), "6B": ("GBP", .0001, 62500),
        "6A": ("AUD", .00005, 100000), "CL": ("CRUDE_W", .01, 1000), "NG": ("GAS_US", .001, 10000),
        "ZC": ("CORN", .25, 50), "ZS": ("SOYBEAN", .25, 50), "ZW": ("WHEAT", .25, 50),
        "ZN": ("US10", .015625, 1000), "ZB": ("US30", .03125, 1000),
        # v4 擴充（規則不變，只增加分散）
        "PL": ("PLAT", .1, 50), "PA": ("PALLAD", .5, 100), "DX": ("DX", .005, 1000), "ZT": ("US2", .00390625, 2000), "ZF": ("US5", .0078125, 1000),
        "6C": ("CAD", .00005, 100000), "6S": ("CHF", .00005, 125000), "6M": ("MXP", .00001, 500000), "6N": ("NZD", .00005, 100000),
        "HO": ("HEATOIL", .0001, 42000), "HE": ("LEANHOG", .025, 400), "LE": ("LIVECOW", .025, 400), "ZL": ("SOYOIL", .01, 600),
        "ZM": ("SOYMEAL", .1, 100), "CT": ("COTTON2", .01, 500), "SB": ("SUGAR11", .01, 1120), "KC": ("COFFEE", .05, 375),
        "CC": ("COCOA", 1, 10), "NKD": ("NIKKEI", 5, 5), "BTC": ("BITCOIN", 5, .1)}
LOCAL = "/home/claude/pst/data/futures/adjusted_prices_csv/"
URL = "https://raw.githubusercontent.com/pst-group/pysystemtrade/master/data/futures/adjusted_prices_csv/"
def load(f):
    src = LOCAL + f + ".csv" if os.path.exists(LOCAL + f + ".csv") else io.StringIO(urllib.request.urlopen(URL + f + ".csv", timeout=60).read().decode())
    s = pd.read_csv(src, parse_dates=["DATETIME"]).set_index("DATETIME")["price"]
    s = s.groupby(s.index.date).last(); s.index = pd.to_datetime(s.index)
    return s[(s.index.dayofweek < 5) & (s.index >= "1989-01-01")].dropna()

def sigarr(c, i, S):
    return np.array([np.sign(c[i] - c[i-252]), np.sign(c[i] - c[i-126]), np.sign(c[i] - S(i, 200) / 200),
                     np.sign((c[i] + c[i-1]) / 2 - S(i, 200) / 200)])

def nseries(c):
    """N = 20日 EWMA 的 |收盤變動|；換月跳空（>6倍60日標準差）不計入"""
    d = pd.Series(np.r_[0, np.diff(c)])
    sd = d.rolling(60, min_periods=20).std().shift(1)
    d = d.where(~(d.abs() > 6 * sd), 0.0)
    return d.abs().ewm(span=20, adjust=False).mean().values

def simulate(o, h, l, c, idx, tick, pv, k=3.0, intraday=True, comm=2.5):
    """訊號在第 i 天收盤產生 → 第 i+1 天成交（沒有偷用當天收盤價）。
    intraday=True（有開高低收）：隔天開盤價成交；停損用盤中高低價檢查，跳空穿越停損則以開盤價成交。
    intraday=False（只有收盤價）：隔天收盤價成交；停損以收盤價檢查、收盤成交。
    回傳逐筆交易（R 倍數）與每日損益（R 單位）。"""
    n = len(c); cs = np.cumsum(np.r_[0, c]); S = lambda i, w: cs[i+1] - cs[i+1-w]
    N = nseries(c); cost = 2 * comm + 2 * 0.5 * tick * pv
    daily = np.zeros(n); out = []; contrib = []
    pos = 0; pend = None
    def add(j, v):
        daily[j] += v; contrib.append((idx[j], len(out), v))
    def close_trade(j, fill, how):
        nonlocal pos
        out.append(dict(d0=idx[ei], d1=idx[j], side=pos, R=(pos * (fill - entry) * pv - cost) / risk, days=j - ei, how=how))
        pos = 0
    for j in range(253, n):
        F = o[j] if intraday else c[j]
        ref = c[j-1]
        if pend is not None:
            if pend[0] == "exit" and pos:
                add(j, (pos * (F - ref) * pv - cost) / risk)
                close_trade(j, F, "趨勢出場")
            if pend[1] and pos == 0 and pend[2] > 0:
                side = pend[1]; entry = F; ei = j; pos = side
                stop = entry - side * pend[2]; risk = pend[2] * pv + cost; ref = entry
            pend = None
        if pos:
            if intraday:
                hit = (pos == 1 and l[j] <= stop) or (pos == -1 and h[j] >= stop)
                if hit:
                    fill = stop if j == ei else (min(o[j], stop) if pos == 1 else max(o[j], stop))
                    add(j, (pos * (fill - ref) * pv - cost) / risk)
                    close_trade(j, fill, "停損")
                else:
                    add(j, pos * (c[j] - ref) * pv / risk)
            else:
                add(j, pos * (c[j] - ref) * pv / risk)
                if (pos == 1 and c[j] <= stop) or (pos == -1 and c[j] >= stop):
                    add(j, -cost / risk)
                    close_trade(j, c[j], "停損")
        sg = sigarr(c, j, S); nl, ns = int((sg > 0).sum()), int((sg < 0).sum())
        want = 1 if nl >= 3 else (-1 if ns >= 3 else 0)
        if pos and want != pos: pend = ("exit", want, k * N[j])
        elif pos == 0 and want: pend = ("enter", want, k * N[j])
    if pos:
        add(n - 1, -cost / risk); close_trade(n - 1, c[-1], "期末平倉")
    simulate.contrib = contrib
    return pd.DataFrame(out), pd.Series(daily, index=idx)

def tstats(t):
    if t.empty: return dict(n=0)
    w, l = t.R[t.R > 0], t.R[t.R <= 0]
    return dict(n=int(len(t)), win=round(float((t.R > 0).mean()), 2), aw=round(float(w.mean()), 2) if len(w) else 0.0,
                al=round(float(l.mean()), 2) if len(l) else 0.0, exp=round(float(t.R.mean()), 2), worst=round(float(t.R.min()), 2),
                hold=int(t.days.mean()), stop_share=round(float((t.how == "停損").mean()), 2))

def account(daily_R, f):
    """固定比例風險帳戶：每筆進場時風險 = 帳戶 f（例 0.02）。所有商品同時持倉，逐日複利。"""
    r = (f * daily_R).clip(lower=-0.99)
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    dd = float((1 - eq / eq.cummax()).max())
    return dict(CAGR=round(float(eq.iloc[-1] ** (1 / yrs) - 1), 3), maxDD=round(dd, 3),
                Sharpe=round(float(r.mean() / r.std() * np.sqrt(252)), 2), worst_day=round(float(r.min()), 3), years=round(yrs, 1))

def portfolio(trades, contribs, M, rank):
    """同時最多持有 M 筆；同一天有多個新訊號時依 rank（樣本內期望值）優先。回傳每日損益（R 單位，未乘風險比例）與被採用的交易。"""
    rows = []
    for code, t in trades.items():
        for tid, r in t.iterrows():
            rows.append((r.d0, rank.get(code, 99), code, tid, r.d1))
    rows.sort(key=lambda x: (x[0], x[1]))
    acc, open_ = set(), []
    for d0, _, code, tid, d1 in rows:
        open_ = [x for x in open_ if x[1] > d0]          # 出場日在今天之後的才算仍持有
        if len(open_) < M:
            acc.add((code, tid)); open_.append((code, d1))
    parts = []
    for code, cl in contribs.items():
        x = pd.DataFrame(cl, columns=["d", "tid", "v"])
        x = x[[(code, t) in acc for t in x.tid]]
        parts.append(x.groupby("d").v.sum())
    P = pd.concat(parts, axis=1).fillna(0).sum(axis=1).sort_index()
    return P, acc

SHP = lambda x: round(float(x.mean() / x.std() * np.sqrt(252)), 2)
# ── A ──
TR, CT, DA = {}, {}, {}
for code, (f, tick, pv) in INST.items():
    p = load(f); c = p.values
    t, d = simulate(c, c, c, c, p.index, tick, pv, 3, False); TR[code] = t; CT[code] = list(simulate.contrib); DA[code] = d
P = pd.DataFrame(DA).fillna(0).sum(axis=1); P = P[P.index >= "1990-01-01"]
AT = pd.concat([t.assign(code=k) for k, t in TR.items()])
OA, IA = AT[AT.d0 >= "2010-01-01"], AT[(AT.d0 < "2010-01-01") & (AT.d0 >= "1990-01-01")]
print(f"A. 1990–2024/03（隔天收盤成交）{len(INST)} 檔合計")
print("   Sharpe 樣本內", SHP(P[:"2009"]), "樣本外", SHP(P["2010":]))
print("   樣本內", tstats(IA)); print("   樣本外", tstats(OA))
ACC = {}
for f_ in (0.001, 0.0015, 0.0025, 0.005, 0.01):
    a, b = account(P["2010":], f_), account(P[:"2009"], f_); ACC[str(f_)] = dict(oos=a, ins=b)
    print(f"   帳戶：每筆風險 {f_:.2%} → 樣本外 年化 {a['CAGR']:.1%} 最大回撤 {a['maxDD']:.0%}｜樣本內 年化 {b['CAGR']:.1%} 最大回撤 {b['maxDD']:.0%}")
RANK = {k: i for i, k in enumerate(IA.groupby("code").R.mean().sort_values(ascending=False).index)}
PC, _ = portfolio(TR, CT, 20, RANK); PC = PC[PC.index >= "1990-01-01"]
CAP = dict(oos=account(PC["2010":], 0.001), ins=account(PC[:"2009"], 0.001))
print(f"   帳戶：每筆 0.1%、總風險上限 2%（同時最多 20 筆）→ 樣本外 年化 {CAP['oos']['CAGR']:.1%} 最大回撤 {CAP['oos']['maxDD']:.0%}｜樣本內 年化 {CAP['ins']['CAGR']:.1%} 最大回撤 {CAP['ins']['maxDD']:.0%}")
H2 = {}
for code, (f, tick, pv) in INST.items():
    t = TR[code]; o, i_ = t[t.d0 >= "2010-01-01"], t[(t.d0 < "2010-01-01") & (t.d0 >= "1990-01-01")]
    s = tstats(o); s["is_exp"] = round(float(i_.R.mean()), 2) if len(i_) else None
    p = load(f); f20 = p.shift(-20) - p
    sg = np.sign(p - p.shift(252)) + np.sign(p - p.shift(126)) + np.sign(p - p.rolling(200).mean()) + np.sign(p.rolling(2).mean() - p.rolling(200).mean())
    m = (p.index >= "2010-01-01") & f20.notna()
    s["up"] = round(float((f20[m & (sg >= 2)] > 0).mean()), 2); s["dn"] = round(float((f20[m & (sg <= -2)] < 0).mean()), 2)
    H2[code] = s
# ── B ──
BRES = {}
try:
    import yfinance as yf
    def yload(sym):
        d = yf.Ticker(sym).history(period="max", interval="1d", auto_adjust=False)[["Open", "High", "Low", "Close"]].dropna()
        d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
        d = d.groupby(d.index.normalize()).last(); return d[d.index >= "2012-01-01"]
    YT, YD, MISS = [], {}, []
    for code, (f, tick, pv) in INST.items():
        try: d = yload(code + "=F")
        except Exception: d = None
        if d is None or len(d) < 400: MISS.append(code); continue
        t, dl = simulate(d.Open.values, d.High.values, d.Low.values, d.Close.values, d.index, tick, pv, 3, True)
        YT.append(t.assign(code=code)); YD[code] = dl
    YT = pd.concat(YT)
    for code, g in YT[YT.d0 >= "2024-04-01"].groupby("code"): H2[code]["b_exp"] = round(float(g.R.mean()), 2); H2[code]["b_n"] = int(len(g))
    YP = pd.DataFrame(YD).fillna(0).sum(axis=1); YP = YP[YP.index >= "2013-01-01"]
    print(f"\nB. Yahoo 開高低收（隔天開盤成交、盤中停損）{len(YD)} 檔合計（缺資料：{MISS}）")
    for lab, a, b in [("2013–2024/03", "2013-01-01", "2024-03-31"), ("2024/04–今天（pysystemtrade 沒有的新資料）", "2024-04-01", "2100-01-01")]:
        tt = YT[(YT.d0 >= a) & (YT.d0 <= b)]; pp = YP[a:b]
        BRES[lab.split("（")[0]] = dict(sharpe=SHP(pp), exp=tstats(tt).get("exp"), acc=account(pp, 0.001))
        print(f"   {lab}: Sharpe {SHP(pp)}  {tstats(tt)}  帳戶0.1% {account(pp, 0.001)}")
    tw = yload("^TWII"); tw = tw[tw.index >= "1997-07-01"] if len(tw) else tw
    twf = yf.Ticker("^TWII").history(period="max", interval="1d", auto_adjust=False)[["Open", "High", "Low", "Close"]].dropna()
    twf.index = twf.index.tz_localize(None) if twf.index.tz is not None else twf.index
    twf = twf.groupby(twf.index.normalize()).last(); twf = twf[twf.index >= "1997-07-01"]
    # 台指成本：手續費約 NT$50/邊 ＋ 期交稅 十萬分之二×契約價值（以近年點位約 2 萬點估）→ 約 US$4/邊
    t, dl = simulate(twf.Open.values, twf.High.values, twf.Low.values, twf.Close.values, twf.index, 1.0, 200 / 32, 3, True, comm=(50 + 2e-5 * 20000 * 200) / 32)
    o, i_ = t[t.d0 >= "2013-01-01"], t[t.d0 < "2013-01-01"]
    s = tstats(o); s["is_exp"] = round(float(i_.R.mean()), 2)
    c = twf.Close; f20 = c.shift(-20) - c
    sg = np.sign(c - c.shift(252)) + np.sign(c - c.shift(126)) + np.sign(c - c.rolling(200).mean()) + np.sign(c.rolling(2).mean() - c.rolling(200).mean())
    m = (c.index >= "2013-01-01") & f20.notna()
    s["up"] = round(float((f20[m & (sg >= 2)] > 0).mean()), 2); s["dn"] = round(float((f20[m & (sg <= -2)] < 0).mean()), 2)
    H2["TX"] = s
    print("   台指（加權指數 1997–今天，隔天開盤成交、盤中停損）樣本外2013–：", s)
except Exception as e:
    print("Yahoo 資料抓取失敗：", e)
print("\n各商品（A：2010–2024/03 隔天收盤成交；台指為 B）；b_exp = 該商品在 Yahoo 2024/04 後的每筆期望值")
print(pd.DataFrame(H2).T.reindex(columns=["n", "win", "aw", "al", "exp", "is_exp", "worst", "hold", "b_exp", "b_n", "up", "dn"]).to_string())
# ── D. 你原本的戰情雷達：把「強力多頭/空頭」與「壓縮突破」照原規則逐筆回測（Yahoo 開高低收量）──
def radar_signals(d):
    c, h, l, v = d.Close, d.High, d.Low, d.Volume.fillna(0)
    pdm, mdm = h.diff(), l.diff(); pdm[pdm < 0] = 0; mdm[mdm > 0] = 0
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1); atr = tr.rolling(14).mean()
    pdi = 100 * pdm.ewm(alpha=1/14).mean() / atr; mdi = 100 * mdm.abs().ewm(alpha=1/14).mean() / atr
    adx = ((pdi - mdi).abs() / (pdi + mdi).abs() * 100).rolling(14).mean()
    ma20, ma50 = c.rolling(20).mean(), c.rolling(50).mean()
    wk = c.resample("W-FRI").last(); prev19 = wk.rolling(19).sum().shift(1)
    lab = c.index.to_period("W-FRI").end_time.normalize()
    wkma = (prev19.reindex(lab).values + c.values) / 20                     # 本週用當天價格當週收盤（和原版即時算法一致）
    tp = (h + l + c) / 3; vwap = (tp * v).rolling(20).sum() / v.rolling(20).sum(); vwap = vwap.fillna(c)
    ts = np.where((c > ma20) & (ma20 > ma50), 1, np.where((c < ma20) & (ma20 < ma50), -1, 0)).astype(float)
    sc = ts.copy()
    sc += np.where((c.values > wkma) & (sc > 0), 1, 0) - np.where((c.values <= wkma) & (sc < 0), 1, 0)
    sc = np.where(adx.values > 25, np.where(sc > 0, sc + 1, sc - 1), sc)
    sc += np.where(c > vwap, .5, -.5)
    std20 = c.rolling(20).std(); ub, lb = ma20 + 2 * std20, ma20 - 2 * std20; ema20 = c.ewm(span=20).mean()
    sq = ((ub < ema20 + 1.5 * atr) & (lb > ema20 - 1.5 * atr)).values
    return sc, sq, atr.values, ub.values, ma20.values

def radar_bt(d, tick, pv, kind):
    o, h, l, c = d.Open.values, d.High.values, d.Low.values, d.Close.values; idx = d.index
    sc, sq, atr, ub, ma20 = radar_signals(d); cost = 2 * 2.5 + 2 * 0.5 * tick * pv
    out = []; pos = 0; i = 210
    while i < len(c) - 1:
        if pos == 0:
            j = i + 1
            if kind == "strong" and not sq[i] and (sc[i] >= 3 or sc[i] <= -3) and atr[i] > 0:
                side = 1 if sc[i] >= 3 else -1; entry = o[j]; sl = entry - side * 2 * atr[i]; tp_ = entry + side * 4 * atr[i]
            elif kind == "squeeze" and sq[i] and h[j] >= ub[i] and ub[i] > ma20[i]:
                side = 1; entry = max(o[j], ub[i]); sl = ma20[i]; tp_ = entry + 2 * (entry - sl)
            else:
                i += 1; continue
            risk = abs(entry - sl) * pv + cost; pos = side
            k = j if kind == "strong" else j + 1                         # 盤中突破進場那天無法判斷高低點先後，從隔天起檢查出場
            while k < len(c):
                hit_sl = (l[k] <= sl) if side == 1 else (h[k] >= sl)
                hit_tp = (h[k] >= tp_) if side == 1 else (l[k] <= tp_)
                if hit_sl:                                                   # 同一天兩個都碰到：保守算停損
                    fill = min(o[k], sl) if side == 1 else max(o[k], sl)
                    out.append(dict(d0=idx[j], R=(side * (fill - entry) * pv - cost) / risk)); break
                if hit_tp:
                    fill = (max(o[k], tp_) if side == 1 else min(o[k], tp_)) if k > j else tp_
                    out.append(dict(d0=idx[j], R=(side * (fill - entry) * pv - cost) / risk)); break
                k += 1
            pos = 0; i = k + 1
        else:
            i += 1
    return pd.DataFrame(out)

RADAR = {}
try:
    import yfinance as yf
    RT = {"strong": [], "squeeze": []}
    for code, (f, tick, pv) in INST.items():
        try:
            d = yf.Ticker(code + "=F").history(period="max", interval="1d", auto_adjust=False)[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
            d = d.groupby(d.index.normalize()).last(); d = d[d.index >= "2012-01-01"]
        except Exception: continue
        if len(d) < 400: continue
        for kind in RT: RT[kind].append(radar_bt(d, tick, pv, kind).assign(code=code))
    print("\nD. 你原本戰情雷達的訊號（隔天開盤進場、盤中碰停損/停利出場；同日兩者都碰到算停損）")
    for kind, nm in [("strong", "強力多空(2ATR停損/4ATR停利)"), ("squeeze", "壓縮突破(上軌掛單/20MA停損/2倍停利)")]:
        T = pd.concat(RT[kind]) if RT[kind] else pd.DataFrame(columns=["d0", "R"])
        for lab, a, b in [("2013–2024/03", "2013-01-01", "2024-03-31"), ("2024/04–今天", "2024-04-01", "2100-01-01")]:
            tt = T[(T.d0 >= a) & (T.d0 <= b)]
            if len(tt):
                RADAR[f"{nm} {lab}"] = dict(n=int(len(tt)), win=round(float((tt.R > 0).mean()), 2), exp=round(float(tt.R.mean()), 2))
                print(f"   {nm} {lab}: {len(tt)} 筆  勝率 {(tt.R > 0).mean():.0%}  每筆平均 {tt.R.mean():+.2f}R")
except Exception as e:
    print("雷達回測失敗：", e)

# ── 與第一格副駕剛才用的數字比對 ──
HC = globals().get("H")
if HC:
    diff = [k for k in H2 if k in HC and any(abs((HC[k].get(x) or 0) - (H2[k].get(x) or 0)) > 0.011 for x in ("win", "exp", "is_exp", "worst"))]
    print("\n與第一格副駕剛才使用的數字比對：", "✅ 完全一致" if not diff else f"❌ 不一致：{diff}（以本次重算為準，已寫入共用檔）")
# ── 寫入共用績效檔：第一格（副駕）執行時會優先讀這個檔，兩格用同一份數字 ──
OUT = dict(time=pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M"), H=H2, ACC=ACC, CAP=CAP, B=BRES, RADAR=RADAR)
os.makedirs("/content", exist_ok=True) if os.path.isdir("/content") else None
json.dump(OUT, open("/content/copilot_stats.json" if os.path.isdir("/content") else "copilot_stats.json", "w"), ensure_ascii=False)
print("\n已寫入 /content/copilot_stats.json（", OUT["time"], "）→ 回到第一格按 ▶，副駕就會改用這次重算的數字")
print("STATS_JSON " + json.dumps(OUT, ensure_ascii=False))
