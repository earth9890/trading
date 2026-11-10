"""Test improvement ideas for the expiry-day ORB on ALL expiry days (2 years, NIFTY + SENSEX), split in two halves
so a filter only counts if it helps in BOTH. PAPER research only.   python options_ideas_bt.py
"""
from datetime import time as T

import pandas as pd

import options_bt as ob
from options_duel_bt import daily


def all_days():
    vix5, vix_d = ob.load("VIX").set_index("time").close, daily("VIX").close
    out = []
    for idx in ("NIFTY", "SENSEX"):
        g_all, dl = ob.load(idx), daily(idx)
        tdays = sorted(g_all.d.unique())
        for e in sorted(ob.expiries(idx, tdays)):
            g = g_all[g_all.d == e]
            past = dl[dl.index < e]
            if len(g) < 65 or len(past) < 21:
                continue
            day = ob.Day(idx, e, g, vix5, e, tdays)
            gg = day.g
            hi, lo = gg.high[:3].max(), gg.low[:3].min()
            vp = vix_d[vix_d.index < e]
            f = dict(gap=gg.open[0] / past.close.iloc[-1] - 1, orw=(hi - lo) / gg.open[0],
                     trend5=past.close.iloc[-1] / past.close.iloc[-6] - 1,
                     above20=past.close.iloc[-1] > past.close.tail(20).mean(), vix=vp.iloc[-1],
                     vix_chg=vp.iloc[-1] - vp.iloc[-6])
            out.append((day, f))
    return out


IDEAS = {
    "baseline (live rules)": lambda f: dict(reentry=True),
    "no re-entry": lambda f: dict(),
    "with-trend only (20d avg)": lambda f: dict(reentry=True, allow=(1,) if f["above20"] else (-1,)),
    "against-trend only": lambda f: dict(reentry=True, allow=(-1,) if f["above20"] else (1,)),
    "skip VIX > 16": lambda f: dict(reentry=True, allow=() if f["vix"] > 16 else (1, -1)),
    "skip VIX < 13": lambda f: dict(reentry=True, allow=() if f["vix"] < 13 else (1, -1)),
    "skip VIX rising (5d +1)": lambda f: dict(reentry=True, allow=() if f["vix_chg"] > 1 else (1, -1)),
    "skip wide OR (>0.6%)": lambda f: dict(reentry=True, allow=() if f["orw"] > 0.006 else (1, -1)),
    "skip narrow OR (<0.3%)": lambda f: dict(reentry=True, allow=() if f["orw"] < 0.003 else (1, -1)),
    "skip big gap (>0.5%)": lambda f: dict(reentry=True, allow=() if abs(f["gap"]) > 0.005 else (1, -1)),
    "entries before 11:00 only": lambda f: dict(reentry=True, last_entry=T(11, 0)),
    "option stop -20%": lambda f: dict(reentry=True, stop_pct=0.20),
    "option stop -50%": lambda f: dict(reentry=True, stop_pct=0.50),
    "target +100%": lambda f: dict(reentry=True, tgt_pct=1.0),
    "no index stop (only -30%)": lambda f: dict(reentry=True, idx_stop=False),
    "30-min range (6 bars)": lambda f: dict(reentry=True, n=6),
}


def main():
    days = all_days()
    half = len(days) // 2
    days_sorted = sorted(days, key=lambda x: x[0].d)
    rows = []
    for name, rule in IDEAS.items():
        nets = []
        for day, f in days_sorted:
            nets.append(sum(t["net"] for t in ob.orb(day, **rule(f))))
        s = pd.Series(nets)
        rows.append(dict(idea=name, days=len(s), traded=int((s != 0).sum()), win_days=f"{(s > 0).sum() / max((s != 0).sum(), 1):.0%}",
                         total=round(s.sum()), first_half=round(s[:half].sum()), second_half=round(s[half:].sum()),
                         last25=round(s[-25:].sum()), worst_day=round(s.min()), best_day=round(s.max())))
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"{len(days)} expiry days {days_sorted[0][0].d} .. {days_sorted[-1][0].d}, 1 lot, NET after costs+slippage\n")
    print(df.to_string(index=False))
    df.to_csv(ob.D.parent.parent / "docs/options_ideas.csv", index=False)


if __name__ == "__main__":
    main()
