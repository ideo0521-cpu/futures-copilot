import yfinance as yf, pandas as pd, datetime as dt
print("yfinance", yf.__version__, "UTC now", dt.datetime.utcnow())
for s in ["ES=F","6E=F","GC=F","ZC=F","EURUSD=X","BTC-USD"]:
    t = yf.Ticker(s)
    for per, iv in [("1d","1m"),("5d","1m"),("5d","1d")]:
        try:
            d = t.history(period=per, interval=iv)
            print(s, per, iv, len(d), d.index[-1] if len(d) else None, float(d.Close.iloc[-1]) if len(d) else None)
        except Exception as e: print(s, per, iv, "ERR", e)
