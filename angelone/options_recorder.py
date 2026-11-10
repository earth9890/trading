"""Order-flow recorder (read-only, never trades): every 5 min 09:14-15:30 on market days, snapshot the nearest-expiry
NIFTY + SENSEX option chain (ATM +-10 strikes, CE+PE) via getMarketData FULL -> data/flow/{date}_{IDX}.csv
  columns: time,spot,symbol,strike,typ,ltp,oi,volume,totbuy,totsell
Why: Angel deletes candles of expired contracts, so this is our only source of REAL expiry-day option prices + OI
for future backtests, and it feeds the FLOW paper player (options_paper.py).

  python options_recorder.py            # launchd 09:13 weekdays
  python options_recorder.py once       # one snapshot now (test)
"""
import csv
import json
import sys
import time
from datetime import date, datetime, time as T
from pathlib import Path

import angel
import trader

HERE = Path(__file__).parent
OUT = HERE / "data/flow"
IDX = {"NIFTY": dict(exch="NSE", tok="99926000", oexch="NFO", step=50),
       "SENSEX": dict(exch="BSE", tok="99919000", oexch="BFO", step=100)}
COLS = ["time", "spot", "symbol", "strike", "typ", "ltp", "oi", "volume", "totbuy", "totsell"]


def chain(m, name, today):
    """Nearest expiry >= today: {strike: {CE: row, PE: row}}."""
    opts = [x for x in m if x.get("name") == name and x.get("instrumenttype") == "OPTIDX"]
    exp = min(d for d in {datetime.strptime(x["expiry"], "%d%b%Y").date() for x in opts} if d >= today)
    out = {}
    for x in opts:
        if datetime.strptime(x["expiry"], "%d%b%Y").date() == exp:
            out.setdefault(int(float(x["strike"]) / 100), {})[x["symbol"][-2:]] = x
    return exp, out


def market(api, exch, tokens):
    for w in (1, 3, 10):
        try:
            r = api.getMarketData("FULL", {exch: tokens})
            if r.get("status"):
                return r["data"]["fetched"]
        except Exception:
            pass
        time.sleep(w)
    return []


def snapshot(api, m):
    now, today = datetime.now().strftime("%Y-%m-%dT%H:%M:00"), date.today()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, i in IDX.items():
        spot = market(api, i["exch"], [i["tok"]])
        if not spot:
            trader.log(f"recorder {name}: no spot"); continue
        S = float(spot[0]["ltp"])
        exp, ch = chain(m, name, today)
        K = round(S / i["step"]) * i["step"]
        legs = [ch[k][t] for k in range(K - 10 * i["step"], K + 11 * i["step"], i["step"]) for t in ("CE", "PE")
                if k in ch and t in ch[k]]
        info = {x["token"]: x for x in legs}
        rows = market(api, i["oexch"], list(info)[:50])
        f = OUT / f"{today}_{name}.csv"
        new = not f.exists()
        with f.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(COLS)
            for r in rows:
                x = info.get(r["symbolToken"])
                if x:
                    w.writerow([now, S, x["symbol"], int(float(x["strike"]) / 100), x["symbol"][-2:], r.get("ltp"),
                                r.get("opnInterest"), r.get("tradeVolume"), r.get("totBuyQuan"), r.get("totSellQuan")])
        time.sleep(1)


def main():
    m = json.loads((HERE / "data/scripmaster.json").read_text())
    api = angel.login()
    if sys.argv[1:] == ["once"]:
        return snapshot(api, m)
    if not trader.market_day():
        return
    while datetime.now().time() < T(9, 14):
        time.sleep(20)
    while datetime.now().time() < T(15, 31):   # 09:14 snapshot = previous close OI, then every 5 min
        try:
            snapshot(api, m)
        except Exception as e:   # one bad snapshot must not kill the day's recording
            trader.log(f"recorder snapshot failed: {str(e)[:150]}")
        time.sleep(300 - time.time() % 300 + 2)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        trader.alert(f"OPTIONS RECORDER CRASHED: {str(e)[:150]}")
        raise
