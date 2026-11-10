"""Download candles from Angel (free) into data/<interval>/<SYMBOL>.csv.

  python fetch.py day          # ~8 years daily candles for UNIVERSE
  python fetch.py 5min 90      # last 90 days of 5-minute candles
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import angel

# Liquid NIFTY 100 names. ponytail: hardcoded list, refresh yearly when index rebalances.
UNIVERSE = """RELIANCE HDFCBANK ICICIBANK INFY TCS BHARTIARTL ITC SBIN LT HINDUNILVR AXISBANK KOTAKBANK
BAJFINANCE MARUTI SUNPHARMA HCLTECH M&M TITAN ULTRACEMCO NTPC ONGC TATASTEEL POWERGRID ADANIENT
ADANIPORTS ASIANPAINT WIPRO COALINDIA JSWSTEEL BAJAJFINSV NESTLEIND TECHM GRASIM HINDALCO INDUSINDBK
CIPLA DRREDDY EICHERMOT HEROMOTOCO BPCL BRITANNIA TATACONSUM APOLLOHOSP DIVISLAB SBILIFE HDFCLIFE
SHRIRAMFIN BEL TRENT ETERNAL TATAPOWER IOC GAIL VEDL DLF BANKBARODA PNB CANBK RECLTD PFC IRFC
HAL ZYDUSLIFE AMBUJACEM DABUR GODREJCP PIDILITIND SIEMENS HAVELLS CHOLAFIN JIOFIN BAJAJ-AUTO TVSMOTOR
INDHOTEL LODHA NHPC IDEA YESBANK SUZLON IRCTC ASHOKLEY BHEL SAIL NMDC FEDERALBNK IDFCFIRSTB""".split()

INTERVALS = {"day": ("ONE_DAY", 1900), "5min": ("FIVE_MINUTE", 95)}  # max days per request


def tokens():
    master = json.loads((Path(__file__).parent / "data/scripmaster.json").read_text())
    return {x["symbol"][:-3]: x["token"] for x in master if x["exch_seg"] == "NSE" and x["symbol"].endswith("-EQ")}


def fetch(api, token, interval, days):
    name, chunk = INTERVALS[interval]
    end, rows = datetime.now(), []
    while days > 0:
        n = min(days, chunk)
        start = end - timedelta(days=n)
        r = {}
        for wait in (5, 15, 30, 60, 90):
            try:  # SDK raises on Angel's plain-text "exceeding access rate" reply
                r = api.getCandleData(dict(exchange="NSE", symboltoken=token, interval=name,
                                           fromdate=start.strftime("%Y-%m-%d 09:15"), todate=end.strftime("%Y-%m-%d 15:30")))
            except Exception:
                r = {}
            if r and r.get("status") and r.get("success") is not False:
                break
            time.sleep(wait)  # rate limited (Angel also caps per minute): back off
        else:
            raise RuntimeError("gave up after retries")  # never save a file with a hole in it
        rows = (r.get("data") or []) + rows
        end, days = start - timedelta(days=1), days - n
        time.sleep(1)  # ponytail: Angel historical limit is strict, 1 req/s is safe
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).drop_duplicates("time")
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values("time")


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "day"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 2900
    out = Path(__file__).parent / "data" / interval
    out.mkdir(parents=True, exist_ok=True)
    api, tok = angel.login(), tokens()
    for sym in UNIVERSE:
        if (out / f"{sym}.csv").exists():
            continue  # resume
        if sym not in tok:
            print("skip (no token):", sym)
            continue
        try:
            df = fetch(api, tok[sym], interval, days)
        except RuntimeError as e:
            print("FAILED", sym, e)  # rerun the script later to fill it in
            continue
        df.to_csv(out / f"{sym}.csv", index=False)
        print(sym, len(df), df["time"].iloc[0].date() if len(df) else "-")
