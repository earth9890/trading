"""Download 5-min INDEX candles: python fetch_idx.py NAME EXCH TOKEN [FROM]  -> data/idx/NAME.csv (same format as NIFTY.csv)."""
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd

import angel

name, exch, tok = sys.argv[1:4]
start = datetime.strptime(sys.argv[4] if len(sys.argv) > 4 else "2024-10-29", "%Y-%m-%d").date()
api, rows, d = angel.login(), [], start
while d <= date.today():
    e = min(d + timedelta(days=29), date.today())
    for wait in (3, 10, 30, 60, None):
        try:
            r = api.getCandleData(dict(exchange=exch, symboltoken=tok, interval="FIVE_MINUTE",
                                       fromdate=f"{d} 09:15", todate=f"{e} 15:30"))
            if r and r.get("status") and r.get("success") is not False:
                break
        except Exception:
            pass
        if wait is None:
            raise SystemExit(f"gave up {d}..{e}")  # never save a file with a hole in it
        time.sleep(wait)
    rows += r.get("data") or []
    print(d, e, len(r.get("data") or []), flush=True)
    d = e + timedelta(days=1)
    time.sleep(1)
df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).drop_duplicates("time").sort_values("time")
df["time"] = df["time"].astype(str).str[:19] + "+05:30"
df.to_csv(f"data/idx/{name}.csv", index=False)
n = df.groupby(df.time.str[:10]).size()
print(name, len(df), "rows", len(n), "days; per-day min/median/max", n.min(), n.median(), n.max())
