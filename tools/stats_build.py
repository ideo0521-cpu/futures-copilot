# 一次性：計算每個商品「趨勢系統」「期限結構系統」的歷史逐筆統計（R 為單位），寫入 stats.json
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, io, urllib.request, os, json
src = open("tools/verify_core.py").read(); exec(src[:src.index("# ── A ──")])
MURL = "https://raw.githubusercontent.com/pst-group/pysystemtrade/master/data/futures/multiple_prices_csv/"
os.makedirs("mp", exist_ok=True)
def load_mp(f):
    fn = f"mp/{f}.csv"
    if not os.path.exists(fn): open(fn, "wb").write(urllib.request.urlopen(MURL + f + ".csv", timeout=90).read())
    m = pd.read_csv(fn, parse_dates=["DATETIME"]).set_index("DATETIME")
    m = m.groupby(m.index.date).last(); m.index = pd.to_datetime(m.index)
    return m
def ym(x): x = str(int(x)); return int(x[:4]) * 12 + int(x[4:6])
def ann_carry(m):
    m = m.dropna(subset=["PRICE", "CARRY", "PRICE_CONTRACT", "CARRY_CONTRACT"])
    d = m.PRICE_CONTRACT.map(ym) - m.CARRY_CONTRACT.map(ym)       # >0：carry 合約較近
    d = d.replace(0, np.nan)
    return ((m.CARRY - m.PRICE) / m.PRICE.abs() * 12 / d).replace([np.inf, -np.inf], np.nan)   # >0 = 逆價差（近月貴）→ 偏多
SECT = {k: s for s, ks in {"能源": "CL NG HO", "金屬": "GC SI HG PL PA", "農產/軟商品/畜產": "ZC ZS ZW ZL ZM CT SB KC CC HE LE",
        "外匯": "6E 6J 6B 6A 6C 6S 6M 6N DX", "公債": "ZN ZB ZT ZF", "股價指數": "ES NQ YM RTY NKD", "加密": "BTC"}.items() for k in ks.split()}

def sim(c, idx, tick, pv, want, k=3.0, comm=2.5):
    """通用逐筆模擬（只有收盤價）：want[j] 是第 j 天收盤後想要的方向；隔天收盤成交；固定 k×N 停損（收盤檢查）；停損後若訊號仍在，隔天重新進場。"""
    n = len(c); N = nseries(c); cost = 2 * comm + 2 * 0.5 * tick * pv
    daily = np.zeros(n); posarr = np.zeros(n); trades = []; pos = 0; pend = None
    for j in range(253, n):
        F = c[j]; ref = c[j-1]
        if pend is not None:
            if pend[0] == "exit" and pos:
                daily[j] += (pos * (F - ref) * pv - cost) / risk; trades.append((idx[ei], idx[j], pos, (pos * (F - entry) * pv - cost) / risk)); pos = 0
            if pend[1] and pos == 0 and pend[2] > 0:
                pos = pend[1]; entry = F; ei = j; stop = entry - pos * pend[2]; risk = pend[2] * pv + cost; ref = entry
            pend = None
        if pos:
            daily[j] += pos * (c[j] - ref) * pv / risk
            if (pos == 1 and c[j] <= stop) or (pos == -1 and c[j] >= stop):
                daily[j] -= cost / risk; trades.append((idx[ei], idx[j], pos, (pos * (c[j] - entry) * pv - cost) / risk)); pos = 0
        posarr[j] = pos
        w = want[j]
        if pos and w != pos: pend = ("exit", w, k * N[j])
        elif pos == 0 and w: pend = ("enter", w, k * N[j])
    return pd.Series(daily, index=idx), pd.Series(posarr, index=idx), pd.DataFrame(trades, columns=["d0", "d1", "side", "R"])

def st(t, a=None, b=None):
    if a: t = t[(t.d0 >= a) & (t.d0 < b)]
    if len(t) < 5: return None
    w = t[t.R > 0].R; l = t[t.R <= 0].R
    return dict(n=int(len(t)), win=round(float((t.R > 0).mean()), 3), avg=round(float(t.R.mean()), 3), avg_win=round(float(w.mean()), 3) if len(w) else None,
                max_win=round(float(t.R.max()), 2), avg_loss=round(float(l.mean()), 3) if len(l) else None, worst=round(float(t.R.min()), 2),
                hold=int((pd.to_datetime(t.d1) - pd.to_datetime(t.d0)).dt.days.median()), first=str(t.d0.min())[:10], last=str(t.d0.max())[:10])
out = {"trend": {}, "carry": {}, "note": "pysystemtrade 回溯調整價（至 2024/03），收盤成交、固定 3N 停損、已扣手續費與 1 跳滑價；R＝每筆進場時的停損風險"}
for code, (f, tick, pv) in INST.items():
    try: p = load(f)
    except Exception as e: print(code, e); continue
    c = p.values
    t, _ = simulate(c, c, c, c, p.index, tick, pv, 3, False)
    out["trend"][code] = dict(all=st(t), oos=st(t, "2010", "2025"))
    if SECT.get(code) in ("能源", "金屬", "農產/軟商品/畜產"):
        m = load_mp(f); car = ann_carry(m).reindex(p.index).ffill(limit=5).rolling(5, min_periods=3).mean()
        _, _, tc = sim(c, p.index, tick, pv, np.nan_to_num(np.sign(car.values)))
        out["carry"][code] = dict(all=st(tc), oos=st(tc, "2010", "2025"))
    print(code, out["trend"][code]["all"], out["carry"].get(code, {}).get("all"), flush=True)
# 台指期：用 Yahoo 加權指數 2000 年起（pysystemtrade 沒有台指）
import yfinance as yf
tw = yf.Ticker("^TWII").history(start="2000-01-01", interval="1d").Close; tw.index = tw.index.tz_localize(None)
c = tw.values; t, _ = simulate(c, c, c, c, tw.index, 1, 200, 3, False, comm=(50 + 2e-5 * 20000 * 200) / 32)
out["trend"]["TX"] = dict(all=st(t), oos=st(t, "2010", "2027"), note="以加權指數代替台指期（2000 年起）")
print("TX", out["trend"]["TX"])
json.dump(out, open("stats.json", "w"), ensure_ascii=False, indent=1)
