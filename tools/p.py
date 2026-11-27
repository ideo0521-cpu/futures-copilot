import yfinance as yf
for s in ["CLZ24.NYM","CLF25.NYM","CLM25.NYM","CLZ25.NYM","CLF26.NYM","CLH26.NYM","NGZ24.NYM","ZCZ24.CBT","GCZ24.CMX"]:
    d = yf.Ticker(s).history(period="max", interval="1d")
    print(s, len(d), d.index[0].date() if len(d) else None, d.index[-1].date() if len(d) else None)
