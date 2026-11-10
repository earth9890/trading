"""Expiry-day hedged option SELLING backtest (Rs 30k account, 1 lot, defined max loss). PAPER research only.

  python options_sell_bt.py [IV_MULT ...]      # e.g. 0.9 1.0 1.1  (model sensitivity)

Prices are modelled (Black-Scholes, VIX x calibrated multiplier) -> selling results depend on the model's IV vs the
real move. Treat as a screen; the recorder's real option prices (data/flow/) are the check.
Strategies (all exit 15:15, or stop when open loss >= STOP x credit):
  iron_fly   09:30 sell ATM call+put, buy wings +-W
  condor     09:30 sell +-1% OTM call/put, buy +-2%
  orb_spread on ORB15 breakout: sell the opposite-side ATM credit spread (break up -> sell put spread)
"""
import sys
from datetime import time as T

import pandas as pd

import options_bt as ob
from options_ideas_bt import all_days

CAPITAL = 30_000
STOP = 1.0          # exit if open loss >= 1x credit received


def run_legs(day, i0, legs):
    """legs: [(K, call, +1 buy / -1 sell)]. Returns trade dict with net P&L (1 lot) or None."""
    g, sp = day.g, ob.SPEC[day.idx]
    q = sp["lot"]
    px = lambda i, S: [day.price(i, S, K, c) for K, c, _ in legs]
    p0 = px(i0, g.open[i0])
    # fills: pay slippage on every leg
    fill0 = [p * (1 + ob.SLIP_PCT * s) + ob.SLIP_ABS * s for p, (_, _, s) in zip(p0, legs)]
    credit = -sum(f * s for f, (_, _, s) in zip(fill0, legs))          # >0 for a credit structure
    if credit <= 0:
        return None
    value = lambda ps: -sum(p * s for p, (_, _, s) in zip(ps, legs))   # cost to buy back (credit structures)
    exit_i, exit_px = None, None
    for i in range(i0, len(g)):
        for S in (g.high[i], g.low[i]):
            if value(px(i, S)) - credit >= STOP * credit:
                exit_i, exit_px = i, px(i, S)
                break
        if exit_i is not None or g.time[i].time() >= T(15, 15):
            exit_i, exit_px = exit_i or i, exit_px or px(i, g.close[i])
            break
    if exit_px is None:
        exit_i, exit_px = len(g) - 1, px(len(g) - 1, g.close.iloc[-1])
    fill1 = [max(p * (1 - ob.SLIP_PCT * s) - ob.SLIP_ABS * s, 0.05) for p, (_, _, s) in zip(exit_px, legs)]
    gross = (credit - value(fill1)) * q
    buy_val = sum(f for f, (_, _, s) in zip(fill0, legs) if s > 0) * q + sum(f for f, (_, _, s) in zip(fill1, legs) if s < 0) * q
    sell_val = sum(f for f, (_, _, s) in zip(fill0, legs) if s < 0) * q + sum(f for f, (_, _, s) in zip(fill1, legs) if s > 0) * q
    n_orders = 2 * len(legs)
    cost = ob.cost(buy_val, sell_val, sp["exch"]) + (n_orders - 2) * 20 * 1.18   # cost() charges 2 orders
    width = max(abs(a[0] - b[0]) for a in legs for b in legs)
    return dict(d=day.d, idx=day.idx, credit=round(credit * q), gross=gross, net=gross - cost,
                stopped=exit_i is not None and g.time[exit_i].time() < T(15, 15), max_loss=width * q)


def iron_fly(day, w=None):
    sp = ob.SPEC[day.idx]
    w = w or sp["step"] * 4
    i = 3
    K = round(day.g.open[i] / sp["step"]) * sp["step"]
    t = run_legs(day, i, [(K, True, -1), (K, False, -1), (K + w, True, 1), (K - w, False, 1)])
    return [t] if t else []


def condor(day):
    sp = ob.SPEC[day.idx]
    i = 3
    S = day.g.open[i]
    r = lambda x: round(x / sp["step"]) * sp["step"]
    t = run_legs(day, i, [(r(S * 1.01), True, -1), (r(S * 0.99), False, -1), (r(S * 1.02), True, 1), (r(S * 0.98), False, 1)])
    return [t] if t else []


def orb_spread(day):
    sp, g = ob.SPEC[day.idx], day.g
    hi, lo = g.high[:3].max(), g.low[:3].min()
    for i in range(3, len(g) - 1):
        if g.time[i].time() >= T(13, 0):
            return []
        side = 1 if g.close[i] > hi else -1 if g.close[i] < lo else 0
        if side:
            K = round(g.open[i + 1] / sp["step"]) * sp["step"]
            w = sp["step"] * 4
            legs = [(K, False, -1), (K - w, False, 1)] if side > 0 else [(K, True, -1), (K + w, True, 1)]
            t = run_legs(day, i + 1, legs)
            return [t] if t else []
    return []


def main():
    mults = [float(x) for x in sys.argv[1:]] or [1.0]
    days = sorted(all_days(), key=lambda x: x[0].d)
    half = len(days) // 2
    rows = []
    for m in mults:
        ob.IV_MULT = m
        for name, fn in (("iron_fly", iron_fly), ("condor", condor), ("orb_spread", orb_spread)):
            res = []
            for day, f in days:
                day.vix = day.vix / day.__dict__.get("_m", 1.0) * m   # rescale IV for sensitivity
                day._m = m
                res.append(sum(t["net"] for t in fn(day)))
            s = pd.Series(res)
            eq = CAPITAL + s.cumsum()
            rows.append(dict(iv_mult=m, strategy=name, days=len(s), win=f"{(s > 0).mean():.0%}", total=round(s.sum()),
                             first_half=round(s[:half].sum()), second_half=round(s[half:].sum()), last25=round(s[-25:].sum()),
                             worst=round(s.min()), best=round(s.max()), maxDD=f"{(eq / eq.cummax() - 1).min():.0%}",
                             broke="YES" if eq.min() <= 0 else "no"))
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"\n{len(days)} expiry days, Rs {CAPITAL:,}, 1 lot, NET after costs+slippage\n")
    print(df.to_string(index=False))
    df.to_csv(ob.D.parent.parent / "docs/options_sell.csv", index=False)


if __name__ == "__main__":
    main()
