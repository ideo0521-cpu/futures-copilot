import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, requests, json, time
src = open("tools/verify_core.py").read(); exec(src[:src.index("# ── A ──")])
from scipy import stats
CODE = {"CL":"067651","NG":"023651","HO":"022651","GC":"088691","SI":"084691","HG":"085692","PL":"076651","PA":"075651",
 "ZC":"002602","ZS":"005602","ZW":"001602","ZL":"007601","ZM":"026603","CT":"033661","SB":"080732","KC":"083731","CC":"073732",
 "HE":"054642","LE":"057642","ES":"13874A","NQ":"209742","YM":"124603","RTY":"239742","6E":"099741","6J":"097741","6B":"096742",
 "6A":"232741","6C":"090741","6S":"092741","6M":"095741","6N":"112741","DX":"098662","ZN":"043602","ZB":"020601","ZT":"042601","ZF":"044601","NKD":"240741"}
SECT = {k: s for s, ks in {"能源": "CL NG HO", "金屬": "GC SI HG PL PA", "農產": "ZC ZS ZW ZL ZM CT SB KC CC HE LE",
        "外匯": "6E 6J 6B 6A 6C 6S 6M 6N DX", "公債": "ZN ZB ZT ZF", "股指": "ES NQ YM RTY NKD"}.items() for k in ks.split()}
def cot(code):
    r = requests.get("https://publicreporting.cftc.gov/resource/6dca-aqww.json", timeout=60, params={
        "$select": "report_date_as_yyyy_mm_dd,market_and_exchange_names,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all",
        "$where": f"cftc_contract_market_code='{code}'", "$order": "report_date_as_yyyy_mm_dd", "$limit": 5000})
    d = pd.DataFrame(r.json())
    d["date"] = pd.to_datetime(d.report_date_as_yyyy_mm_dd)
    for k in ["noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all"]: d[k] = d[k].astype(float)
    d["net"] = (d.noncomm_positions_long_all - d.noncomm_positions_short_all) / d.open_interest_all
    return d.set_index("date")[["net", "market_and_exchange_names"]]
rows, trades = [], []
for k, cc in CODE.items():
    try:
        f, tick, pv = INST[k]; p = load(f); d = cot(cc)
    except Exception as e:
        print(k, "失敗", e); continue
    d = d[~d.index.duplicated()]
    idx = d.net.rolling(156, min_periods=104).apply(lambda x: (x[-1] - x.min()) / (x.max() - x.min() + 1e-12) * 100, raw=True)
    chg = d.net.diff(13)
    # 報告週二資料、週五公布 → 用下週一收盤進場（週二 + 6 天後的第一個交易日）
    avail = d.index + pd.Timedelta(days=6)
    c = p.values; N = pd.Series(nseries(c), index=p.index)
    pi = p.index.searchsorted(avail)
    ok = pi + 20 < len(p)
    e = pd.DataFrame({"idx": idx.values, "chg": chg.values, "pi": pi}, index=d.index)[ok].dropna()
    e["r4"] = [(c[i + 20] - c[i]) / N.iloc[i] if N.iloc[i] > 0 else np.nan for i in e.pi]          # 未來 4 週報酬（N 單位）
    e = e[np.isfinite(e.r4) & (e.pi > 260)]                          # 排除 N 還沒算穩的最前面一年
    e["code"] = k; e["sect"] = SECT[k]; rows.append(e)
    t, _ = simulate(c, c, c, c, p.index, tick, pv, 3, False)
    if len(t):
        s = pd.Series(chg.values, index=avail).sort_index()
        t["chg"] = [s[:d0 - pd.Timedelta(days=1)].iloc[-1] if len(s[:d0 - pd.Timedelta(days=1)]) else np.nan for d0 in t.d0]
        t["ix"] = [pd.Series(idx.values, index=avail)[:d0 - pd.Timedelta(days=1)].iloc[-1] if len(s[:d0 - pd.Timedelta(days=1)]) else np.nan for d0 in t.d0]
        t["code"] = k; t["sect"] = SECT[k]; trades.append(t.dropna(subset=["chg"]))
    print(k, d.market_and_exchange_names.iloc[-1][:40], d.index[0].date(), "~", d.index[-1].date(), flush=True)
E = pd.concat(rows); T = pd.concat(trades)
def test(name, sig, df):
    out = []
    for lab, a, b in [("1990–2009", "1990", "2010"), ("2010–2024/03", "2010", "2025")]:
        x = df[(df.index >= a) & (df.index < b)]; s = sig(x); v = (s * x.r4)[s != 0]
        tt = stats.ttest_1samp(v, 0) if len(v) > 30 else None
        out.append(f"{lab}: {len(v)} 次 平均 {v.mean():+.3f}N 勝率 {(v>0).mean():.0%} p={tt.pvalue:.3f}" if tt else f"{lab}: 樣本不足")
    print(f"  {name}｜" + "｜".join(out))
print("\n=== ③ 投機部位（COT）預測未來 4 週，全部商品 ===")
test("順勢：13 週投機淨部位增加→多、減少→空", lambda x: np.sign(x.chg), E)
test("反向：COT 指數 >90 → 空、<10 → 多", lambda x: np.where(x.idx > 90, -1, np.where(x.idx < 10, 1, 0)), E)
print("\n  各類別（反向極端，全期間）")
for s_ in dict.fromkeys(SECT.values()):
    x = E[E.sect == s_]; s = np.where(x.idx > 90, -1, np.where(x.idx < 10, 1, 0)); v = (s * x.r4)[s != 0]
    print(f"   {s_}: {len(v)} 次 平均 {v.mean():+.3f}N 勝率 {(v>0).mean():.0%}")
x = E[E.code == "CL"]
for nm, sig in [("順勢", lambda x: np.sign(x.chg)), ("反向極端", lambda x: np.where(x.idx > 90, -1, np.where(x.idx < 10, 1, 0)))]:
    s = sig(x); v = (s * x.r4)[s != 0]; print(f"   原油 CL {nm}: {len(v)} 次 平均 {v.mean():+.3f}N 勝率 {(v>0).mean():.0%}")
print("\n=== ④ 我們的趨勢交易，依進場時投機部位分組（每筆 R，已扣成本） ===")
for lab, a, b in [("1990–2009", "1990", "2010"), ("2010–2024/03", "2010", "2025")]:
    x = T[(T.d0 >= a) & (T.d0 < b)]
    ag = x[np.sign(x.chg) == x.side].R; dg = x[np.sign(x.chg) != x.side].R
    crowd = x[((x.side == 1) & (x.ix > 90)) | ((x.side == -1) & (x.ix < 10))].R
    print(f"  {lab}: 部位同向 {len(ag)} 筆 {ag.mean():+.3f}R｜反向 {len(dg)} 筆 {dg.mean():+.3f}R｜p={stats.ttest_ind(ag, dg, equal_var=False).pvalue:.3f}｜進場時已極端擁擠 {len(crowd)} 筆 {crowd.mean():+.3f}R")
x = T[T.code == "CL"]; ag = x[np.sign(x.chg) == x.side].R; dg = x[np.sign(x.chg) != x.side].R
print(f"  原油 CL：部位同向 {len(ag)} 筆 {ag.mean():+.3f}R｜反向 {len(dg)} 筆 {dg.mean():+.3f}R")
