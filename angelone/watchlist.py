"""Watchlist (read-only, never trades): symbols in watchlist.txt -> price, returns, trend, vs the bot's momentum list.
  python watchlist.py        # prints table + writes docs/watchlist.json (dashboard shows it). launchd 16:30 weekdays.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import angel

HERE = Path(__file__).parent


def row(api, sym, tok, cands):
    now = datetime.now()
    for w in (1, 3, 10, 30):
        try:
            c = api.getCandleData(dict(exchange="NSE", symboltoken=tok, interval="ONE_DAY",
                                       fromdate=(now - timedelta(days=400)).strftime("%Y-%m-%d 09:15"),
                                       todate=now.strftime("%Y-%m-%d %H:%M")))["data"]
            break
        except Exception:
            time.sleep(w)
    else:
        return dict(sym=sym, error="no candles")
    cl = [r[4] for r in c]
    p = cl[-1]
    ret = lambda n: round((p / cl[-1 - n] - 1) * 100, 1) if len(cl) > n else None
    sma200 = sum(cl[-200:]) / 200 if len(cl) >= 200 else None
    hi52 = max(r[2] for r in c[-250:])
    return dict(sym=sym, ltp=p, day=ret(1), week=ret(5), month=ret(21), year=ret(250),
                mom12_1=round((cl[-22] / cl[-253] - 1) * 100, 1) if len(cl) > 252 else None,
                trend="UP" if sma200 and p > sma200 else "DOWN" if sma200 else "?",
                from_52w_high=round((p / hi52 - 1) * 100, 1), in_bot_top10=sym in cands)


def main():
    syms = [l.strip().upper() for l in (HERE / "watchlist.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    m = json.loads((HERE / "data/scripmaster.json").read_text())
    tok = {x["symbol"][:-3]: x["token"] for x in m if x.get("exch_seg") == "NSE" and x["symbol"].endswith("-EQ")}
    cands = set(json.loads((HERE / "state_live.json").read_text()).get("candidates") or [])
    api = angel.login()
    out = []
    for s in syms:
        out.append(row(api, s, tok[s], cands) if s in tok else dict(sym=s, error="not on NSE"))
        time.sleep(0.5)   # candle limit 3/s
    (HERE / "docs/watchlist.json").write_text(json.dumps(dict(at=datetime.now().isoformat(timespec="minutes"), rows=out), indent=1))
    print(f"{'SYM':12}{'LTP':>9}{'day%':>7}{'week%':>7}{'month%':>8}{'year%':>7}{'mom12-1':>8}  trend  vs52wHi  botTop10")
    for r in out:
        if "error" in r:
            print(f"{r['sym']:12} {r['error']}"); continue
        print(f"{r['sym']:12}{r['ltp']:>9}{r['day']:>7}{r['week']:>7}{r['month']:>8}{str(r['year']):>7}{str(r['mom12_1']):>8}  "
              f"{r['trend']:5}{r['from_52w_high']:>8}%  {'YES' if r['in_bot_top10'] else '-'}")


if __name__ == "__main__":
    main()
