import requests, json, re, pandas as pd, time
H={"User-Agent":"Mozilla/5.0"}
def P(t,x): print("=====",t); print(str(x)[:3000]); print(flush=True)
# 1 TradingView
try:
    syms=["CME_MINI:ES1!","CME_MINI:NQ1!","CBOT_MINI:YM1!","NYMEX:CL1!","COMEX:GC1!","COMEX:SI1!","COMEX:HG1!","CME:6E1!","NYMEX:NG1!","CBOT:ZC1!","ICEUS:DX1!","CME:BTC1!"]
    r=requests.post("https://scanner.tradingview.com/futures/scan",headers=H,json={"symbols":{"tickers":syms},"columns":["close","update_mode","description","currency","pricescale","change","time","volume"]},timeout=20).json()
    P("TV",r)
except Exception as e: P("TV err",e)
# 2 MIS kinds
for k in range(1,12):
    for mt in ("0","1"):
        try:
            L=requests.post("https://mis.taifex.com.tw/futures/api/getQuoteList",headers={**H,"Content-Type":"application/json"},json={"MarketType":mt,"SymbolType":"F","KindID":str(k),"CID":"","ExpireMonth":"","RowSize":"全部","PageNo":"","SortColumn":"","AscDesc":"A"},timeout=15).json()["RtData"]["QuoteList"]
            cids=sorted(set(x["SymbolID"][:3] for x in L))
            P(f"MIS kind {k} mt {mt} n={len(L)}",cids[:60])
            for x in L:
                if x["SymbolID"][:3] in ("SPF","UNF","UDF","GDF","XEF","XBF","XAF","TXF","MXF","TMF") and x["SymbolID"][-2:] in ("-F","-M"):
                    print({kk:x.get(kk) for kk in ("SymbolID","DispCName","CLastPrice","CBestBidPrice","CBestAskPrice","CRefPrice","CDate","CTime","CTotalVolume","SettlementPrice","CDiff")})
        except Exception as e: P(f"MIS {k} err",e)
# 3 cnyes
try:
    t=requests.get("https://www.cnyes.com/futures/indexftr.aspx",headers=H,timeout=20); t.encoding="utf-8"
    s=t.text; i=s.find("道瓊"); P("cnyes len %d"%len(s), s[max(0,i-1500):i+2500])
except Exception as e: P("cnyes err",e)
# 4 jin10
try:
    j=requests.get("https://flash-api.jin10.com/get_flash_list",params={"channel":"-8200","vip":"1"},headers={**H,"x-app-id":"bVBF4FyRTn5NJF5n","x-version":"1.0.0","Origin":"https://www.jin10.com","Referer":"https://www.jin10.com/"},timeout=20).json()
    P("jin10",json.dumps(j,ensure_ascii=False)[:2500])
except Exception as e: P("jin10 err",e)
# 5 CFTC
try:
    j=requests.get("https://publicreporting.cftc.gov/resource/6dca-aqww.json",params={"cftc_contract_market_code":"067651","$order":"report_date_as_yyyy_mm_dd DESC","$limit":"2"},timeout=30).json()
    P("cftc",json.dumps(j)[:2500])
    j=requests.get("https://publicreporting.cftc.gov/resource/6dca-aqww.json",params={"$select":"cftc_contract_market_code,market_and_exchange_names","$where":"report_date_as_yyyy_mm_dd > '2026-11-01'","$limit":"500"},timeout=30).json()
    P("cftc codes",[(x["cftc_contract_market_code"],x["market_and_exchange_names"]) for x in j])
except Exception as e: P("cftc err",e)
# 6 EIA
try:
    t=requests.get("https://ir.eia.gov/wpsr/table1.csv",headers=H,timeout=20).text; P("eia",t[:2500])
except Exception as e: P("eia err",e)
# 7 FinMind institutional
try:
    j=requests.get("https://api.finmindtrade.com/api/v4/data",params={"dataset":"TaiwanFuturesInstitutionalInvestors","data_id":"TX","start_date":"2026-11-20"},timeout=30).json()
    P("finmind inst",json.dumps(j,ensure_ascii=False)[:2500])
    j=requests.get("https://api.finmindtrade.com/api/v4/data",params={"dataset":"TaiwanFuturesDaily","data_id":"TX","start_date":"2026-11-26"},timeout=30).json()
    P("finmind daily",json.dumps(j["data"][:6],ensure_ascii=False))
except Exception as e: P("finmind err",e)
# 8 yahoo monthly
import yfinance as yf
for s in ["CLF27.NYM","CLG27.NYM","GCG27.CMX","GCJ27.CMX","SIH27.CMX","HGH27.CMX","ZCH27.CBT","NGF27.NYM","CTH27.NYB","HEG27.CME","GC=F","CL=F"]:
    try:
        d=yf.Ticker(s).history(period="5d",interval="1d",auto_adjust=False); P("yf "+s,d[["Close","Volume"]].tail(3))
    except Exception as e: P("yf err "+s,e)
try:
    i=yf.Ticker("CL=F").info; P("CL=F info",{k:i.get(k) for k in ("underlyingSymbol","expireDate","regularMarketTime","regularMarketPrice","previousClose","exchange")})
except Exception as e: P("info err",e)
