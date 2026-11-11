"""BANKNIFTY / BANKEX MONTHLY expiry-day backtest (+ NIFTY/SENSEX weekly for comparison). Rs 30k, 1 lot, NET. PAPER research.
  python options_bank_bt.py     # needs data/idx/{BANKNIFTY,BANKEX,NIFTY,SENSEX,VIX}.csv ; writes docs/options_bank.csv
Prices modelled (Black-Scholes, India VIX x IV_MULT) - bank indices trade at higher IV than VIX, hence 1.0/1.2/1.4."""
from datetime import date

import pandas as pd

import options_bt as ob
import options_sell_bt as sb

ob.CAPITAL = CAP = 30_000
STRATS = {"orb15_noreentry": lambda d: ob.orb(d, reentry=False), "iron_fly_w4_stop1x": sb.iron_fly}


def lot(idx, e):   # historical lot per expiry (NSE/BSE circulars, per coordinator)
    if idx == "BANKEX":
        return 15 if e < date(2025, 1, 1) else 30
    if idx == "BANKNIFTY":
        return 15 if e <= date(2025, 1, 29) else 30 if e < date(2025, 7, 31) else 35 if e < date(2026, 1, 27) else 30
    return ob.SPEC[idx]["lot"]


def days(idx, m):
    ob.IV_MULT = m
    g_all, vix = ob.load(idx), ob.load("VIX").set_index("time").close
    td = sorted(g_all.d.unique())
    for e in sorted(ob.expiries(idx, td)):
        g = g_all[g_all.d == e]
        if len(g) >= 65:
            ob.SPEC[idx]["lot"] = lot(idx, e)
            yield ob.Day(idx, e, g, vix, e, td)


def stats(s):
    eq = CAP + s.cumsum()
    return dict(days=len(s), total=round(s.sum()), win_days=int((s > 0).sum()), worst=round(s.min()), best=round(s.max()),
                maxdd_rs=round((eq - eq.cummax()).min()), maxdd_pct=f"{(eq / eq.cummax() - 1).min():.0%}")


rows = []
for idx in ("BANKNIFTY", "BANKEX", "NIFTY", "SENSEX"):
    for m in (1.0, 1.2, 1.4):
        for name, fn in STRATS.items():
            s = pd.Series({d.d: sum(t["net"] for t in fn(d)) for d in days(idx, m)})
            rows.append(dict(idx=idx, freq="monthly" if "BANK" in idx else "weekly", iv_mult=m, strategy=name, **stats(s)))
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(df.to_string(index=False))
df.to_csv(ob.D.parent.parent / "docs/options_bank.csv", index=False)
