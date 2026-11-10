"""Does 09:30 option open-interest flow predict the rest of the day? Uses data/oi/{IDX}_{EXP}.csv (real Angel OI,
5-min, live contracts only -> ~3-4 weeks). PAPER research only.   python options_flow_bt.py
Signal (order-flow convention): new PUT writing > new CALL writing near ATM = support = bullish.
  flow = (dPE - dCE) / (CE+PE OI at prev close), d = OI change prev close -> 09:30, ATM +-5 strikes.
"""
from datetime import time as T

import pandas as pd

import options_bt as ob

FILES = {"NIFTY": "NIFTY_17NOV2026", "SENSEX": "SENSEX_12NOV2026"}


def days(idx):
    oi = pd.read_csv(ob.D.parent / f"oi/{FILES[idx]}.csv")
    oi["time"] = pd.to_datetime(oi.time)
    oi["d"] = oi.time.dt.date
    g_all = ob.load(idx)
    tdays = sorted(g_all.d.unique())
    exps = sorted(ob.expiries(idx, tdays))
    vix = ob.load("VIX").set_index("time").close
    step = ob.SPEC[idx]["step"]
    out, prev = [], None
    for d, o in oi.groupby("d"):
        g = g_all[g_all.d == d].reset_index(drop=True)
        if prev is None or len(g) < 65:
            prev = o; continue
        S = g.close[2]                                   # 09:25 bar close = 09:30
        K = round(S / step) * step
        near = lambda x: x[(x.strike - K).abs() <= 5 * step]
        last = near(prev[prev.time == prev.time.max()]).groupby("typ").oi.sum()
        now = near(o[o.time.dt.time == T(9, 25)]).groupby("typ").oi.sum()
        prev = o
        if len(last) < 2 or len(now) < 2:
            continue
        flow = ((now.PE - last.PE) - (now.CE - last.CE)) / (last.CE + last.PE)
        rest = g.close.iloc[-1] / S - 1
        exp = next(e for e in exps if e >= d)
        day = ob.Day(idx, d, g_all[g_all.d == d], vix, exp, tdays)
        bot = sum(t["net"] for t in ob.orb(day))
        side = (1,) if flow > 0 else (-1,)
        flt = sum(t["net"] for t in ob.orb(day, allow=side))
        out.append(dict(d=d, idx=idx, pcr=round(now.PE / now.CE, 2), flow=round(flow * 100, 2),
                        rest_pct=round(rest * 100, 2), hit=(flow > 0) == (rest > 0), bot=round(bot), flow_bot=round(flt)))
    return out


if __name__ == "__main__":
    df = pd.DataFrame(days("NIFTY") + days("SENSEX"))
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    print(f"\n{len(df)} days: flow sign predicted rest-of-day direction {df.hit.mean():.0%} "
          f"(corr flow vs move {df.flow.corr(df.rest_pct):+.2f}; PCR vs move {df.pcr.corr(df.rest_pct):+.2f})")
    print(f"ORB all sides NET {df.bot.sum():+,}   ORB only in flow direction NET {df.flow_bot.sum():+,}")
    df.to_csv(ob.D.parent.parent / "docs/options_flow.csv", index=False)
