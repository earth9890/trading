"""Index OPTIONS-BUYING backtest (NIFTY / SENSEX weekly), Rs 10k account, 1 lot, full costs. Research only - never trades.

  python options_bt.py            # needs data/idx/{NIFTY,SENSEX,VIX}.csv (5-min)

Angel keeps no candles for expired option contracts, so option prices are MODELLED: Black-Scholes on the 5-min index
with IV = India VIX x IV_MULT (calibrate IV_MULT with calibrate() against real option candles). Option highs/lows inside a
bar come from the index high/low. Fills: entry next bar open + slippage; stop checked before target; flat by EXIT time.
"""
import math
from datetime import date, time as T
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).parent / "data/idx"
CAPITAL, R = 10_000, 0.065
IV_MULT = 1.0                 # global scale for sensitivity runs (python options_bt.py 1.1)
# Calibrated 2026-11-05 on real option candles (NIFTY 03NOV expiry day, NIFTY 09NOV at 3 DTE, SENSEX 05NOV expiry):
# implied vol / VIX = ~0.8 on expiry-day morning, rising to ~1.05 by 15:00; ~1.2 on non-expiry days.
SLIP_ABS, SLIP_PCT = 0.5, 0.003   # per side: Rs 0.5 + 0.3% of premium (ATM weekly spreads ~0.05-0.5)
STT_SELL = 0.0015             # options STT on sell premium: 0.15% since 1 Apr 2026 (Budget 2026; docs/options_research.md)
SPEC = {"NIFTY": dict(lot=65, step=50, exch=0.0003503), "SENSEX": dict(lot=20, step=100, exch=0.000325),
        "BANKNIFTY": dict(lot=30, step=100, exch=0.0003503), "BANKEX": dict(lot=30, step=100, exch=0.000325)}


def cost(buy_val, sell_val, exch):
    brok = 40.0
    ex = (buy_val + sell_val) * exch
    sebi = (buy_val + sell_val) * 1e-6
    return brok + ex + sebi + 0.18 * (brok + ex + sebi) + STT_SELL * sell_val + 0.00003 * buy_val


def bs(S, K, t, iv, call):
    """Black-Scholes premium; t in years (>0)."""
    t = max(t, 1e-6)
    d1 = (math.log(S / K) + (R + iv * iv / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    return S * N(d1) - K * math.exp(-R * t) * N(d2) if call else K * math.exp(-R * t) * N(-d2) - S * N(-d1)


def load(name):
    df = pd.read_csv(D / f"{name}.csv")
    df["time"] = pd.to_datetime(df["time"].str[:19])
    # <= 15:15: index data ends with a synthetic 15:25 closing-price print (seen 2026-11-03: 23810 vs 23730 traded)
    df = df[(df.time.dt.time >= T(9, 15)) & (df.time.dt.time <= T(15, 15))]
    df["d"] = df.time.dt.date
    return df


def expiries(idx, days):
    """Weekly expiry per week (holiday -> previous trading day). NIFTY Thu -> Tue from 2025-09-01;
    SENSEX Fri -> Tue (2025-01-01) -> Thu (2025-09-01). Schedules from public NSE/BSE circulars."""
    if idx in ("BANKNIFTY", "BANKEX"):   # MONTHLY: last expiry-weekday of the month, holiday -> previous trading day
        def mwd(d):
            if idx == "BANKNIFTY":
                return 3 if d < date(2025, 9, 1) else 1
            return 0 if d < date(2025, 1, 1) else 1 if d < date(2025, 9, 1) else 3
        s, out = set(days), set()
        for ym in {(d.year, d.month) for d in days}:
            nxt = pd.Timestamp(ym[0], ym[1], 1) + pd.offsets.MonthEnd(0)   # last calendar day of month
            while nxt.weekday() != mwd(nxt.date()):
                nxt -= pd.Timedelta(days=1)
            t = nxt.date()
            if t > max(days):   # month not finished in the data: expiry not yet known
                continue
            while t not in s and t >= date(ym[0], ym[1], 1):
                t -= pd.Timedelta(days=1)
            if t in s:
                out.add(t)
        return out

    def wd(d):
        if idx == "NIFTY":
            return 3 if d < date(2025, 9, 1) else 1
        return 4 if d < date(2025, 1, 1) else 1 if d < date(2025, 9, 1) else 3
    s, out = set(days), set()
    for d in days:
        target = d + pd.Timedelta(days=(wd(d) - d.weekday()))
        while target not in s and target >= d - pd.Timedelta(days=d.weekday()):
            target -= pd.Timedelta(days=1)
        if target in s:
            out.add(target)
    return out


def t_years(d, tm, exp, tdays):
    """Trading-time to expiry close (15:30) in years: full days between + fraction of today."""
    left_today = max((15 * 60 + 30) - (tm.hour * 60 + tm.minute), 1) / 375
    between = sum(1 for x in tdays if d < x <= exp)
    return (between + left_today) / 252


class Day:
    def __init__(self, idx, d, g, vix, exp, tdays):
        self.idx, self.d, self.g, self.exp = idx, d, g.reset_index(drop=True), exp
        mins = (g.time.dt.hour * 60 + g.time.dt.minute).values
        mult = np.where(d == exp, np.interp(mins, [13 * 60, 15 * 60], [0.8, 1.05]), 1.2)
        self.vix = vix.reindex(g.time).ffill().bfill().values / 100 * mult * IV_MULT
        self.tdays = tdays

    def price(self, i, S, K, call):
        return bs(S, K, t_years(self.d, self.g.time[i].time(), self.exp, self.tdays), self.vix[i], call)


def trade(day, i_entry, call, stop_pct=None, tgt_pct=None, idx_stop=None, exit_t=T(15, 15), k=None):
    """Buy 1 ATM lot at bar i_entry open. Exit on option stop/target (from index hi/lo), index stop, or exit_t close."""
    g, sp = day.g, SPEC[day.idx]
    if i_entry >= len(g):
        return None
    S0 = g.open[i_entry]
    K = k or round(S0 / sp["step"]) * sp["step"]
    p0 = day.price(i_entry, S0, K, call)
    buy = p0 * (1 + SLIP_PCT) + SLIP_ABS
    if buy * sp["lot"] > CAPITAL * 0.9 or buy < 2:
        return None
    exitp = None
    for i in range(i_entry, len(g)):
        worst_S = g.low[i] if call else g.high[i]
        best_S = g.high[i] if call else g.low[i]
        worst, best = day.price(i, worst_S, K, call), day.price(i, best_S, K, call)
        if idx_stop is not None and ((call and g.low[i] <= idx_stop) or (not call and g.high[i] >= idx_stop)):
            exitp = day.price(i, idx_stop, K, call); break
        if stop_pct and worst <= buy * (1 - stop_pct):
            exitp = buy * (1 - stop_pct); break
        if tgt_pct and best >= buy * (1 + tgt_pct):
            exitp = buy * (1 + tgt_pct); break
        if g.time[i].time() >= exit_t:
            exitp = day.price(i, g.close[i], K, call); break
    if exitp is None:
        exitp = day.price(len(g) - 1, g.close.iloc[-1], K, call)
    sell = max(exitp * (1 - SLIP_PCT) - SLIP_ABS, 0.05)
    q = sp["lot"]
    gross = (sell - buy) * q
    return dict(d=day.d, idx=day.idx, call=call, buy=round(buy, 2), sell=round(sell, 2), gross=gross,
                net=gross - cost(buy * q, sell * q, sp["exch"]), expiry=day.d == day.exp)


# ---------------- strategies (return list of trades for one Day) ----------------
def orb(day, n=3, stop_pct=0.30, tgt_pct=None, idx_stop=True, reentry=False, last_entry=T(13, 0), allow=(1, -1)):
    """15-min opening range breakout: first 5-min close outside range -> buy ATM call/put next bar."""
    g = day.g
    hi, lo = g.high[:n].max(), g.low[:n].min()
    out, i = [], n
    while i < len(g) - 1 and g.time[i].time() < last_entry:
        side = 1 if g.close[i] > hi else -1 if g.close[i] < lo else 0
        if side in allow:   # allow=(1,) calls only, (-1,) puts only, () skip
            t = trade(day, i + 1, side > 0, stop_pct=stop_pct, tgt_pct=tgt_pct,
                      idx_stop=(lo if side > 0 else hi) if idx_stop else None)
            if t:
                out.append(t)
            if not reentry or not t or t["net"] > 0:
                break
            reentry = False   # at most one re-entry after a loss (like the thread's day 3)
            hi, lo = max(hi, g.high[i]), min(lo, g.low[i])
        i += 1
    return out


def gao(day):
    """First 30 min (incl. overnight gap, via day open vs prior close stored on Day) predicts last half hour."""
    g = day.g
    if day.prev_close is None:
        return []
    r1 = g.close[5] / day.prev_close - 1
    i = int(np.argmax(g.time.dt.time.values >= T(14, 50)))
    if not i or abs(r1) < 0.002:
        return []
    t = trade(day, i, r1 > 0, stop_pct=0.3, exit_t=T(15, 15))
    return [t] if t else []


def trend_1030(day, move=0.004):
    """10:30: index moved > 0.4% from open -> buy in that direction, stop -30% option, exit 15:15."""
    g = day.g
    i = int(np.argmax(g.time.dt.time.values >= T(10, 30)))
    if not i:
        return []
    r = g.close[i - 1] / g.open[0] - 1
    if abs(r) < move:
        return []
    t = trade(day, i, r > 0, stop_pct=0.3)
    return [t] if t else []


def expiry_straddle_1400(day):
    """Expiry-day 'gamma blast': buy ATM call + put at 14:00, each -40% stop, +100% target, exit 15:15."""
    g = day.g
    i = int(np.argmax(g.time.dt.time.values >= T(14, 0)))
    if not i:
        return []
    out = [trade(day, i, c, stop_pct=0.4, tgt_pct=1.0) for c in (True, False)]
    return [t for t in out if t]


def run(idx, strat, only_expiry, **kw):
    g_all, vix = load(idx), load("VIX").set_index("time").close
    tdays = sorted(g_all.d.unique())
    exps = sorted(expiries(idx, tdays))
    trades, prev = [], None
    for d, g in g_all.groupby("d"):
        exp = next((e for e in exps if e >= d), None)
        if exp and len(g) >= 65 and (not only_expiry or d == exp):
            day = Day(idx, d, g, vix, exp, tdays)
            day.prev_close = prev
            trades += strat(day, **kw)
        prev = g.close.iloc[-1]
    return pd.DataFrame(trades)


def report(name, t):
    if t.empty:
        return dict(strategy=name, trades=0)
    daily = t.groupby("d").net.sum()
    eq = CAPITAL + daily.cumsum()
    yrs = max((pd.Timestamp(t.d.max()) - pd.Timestamp(t.d.min())).days / 365, 0.1)
    return dict(strategy=name, trades=len(t), win=f"{(t.net > 0).mean():.0%}", avg_gross=round(t.gross.mean()),
                avg_cost=round((t.gross - t.net).mean()), avg_net=round(t.net.mean()), total_net=round(t.net.sum()),
                per_year=f"{t.net.sum() / CAPITAL / yrs:+.0%}", maxdd=f"{(eq / eq.cummax() - 1).min():.0%}",
                worst=round(t.net.min()), best=round(t.net.max()), broke="YES" if eq.min() <= 0 else "no")


if __name__ == "__main__":
    import sys
    IV_MULT = float(sys.argv[1]) if len(sys.argv) > 1 else IV_MULT
    tests = [
        ("NIFTY expiry ORB15 (idx stop + -30%)", "NIFTY", orb, True, {}),
        ("NIFTY expiry ORB15 +reentry (thread style)", "NIFTY", orb, True, dict(reentry=True)),
        ("NIFTY expiry ORB15 tgt +60%", "NIFTY", orb, True, dict(tgt_pct=0.6)),
        ("NIFTY ORB15 all days", "NIFTY", orb, False, {}),
        ("SENSEX expiry ORB15", "SENSEX", orb, True, {}),
        ("SENSEX expiry ORB15 +reentry", "SENSEX", orb, True, dict(reentry=True)),
        ("NIFTY trend 10:30 all days", "NIFTY", trend_1030, False, {}),
        ("NIFTY last-30min (Gao) all days", "NIFTY", gao, False, {}),
        ("NIFTY expiry 14:00 straddle buy", "NIFTY", expiry_straddle_1400, True, {}),
    ]
    rows = []
    for name, idx, fn, exp_only, kw in tests:
        rows.append(report(name, run(idx, fn, exp_only, **kw)))
        print(rows[-1], flush=True)
    print(f"\nIV_MULT={IV_MULT}  capital Rs {CAPITAL:,}  1 lot  costs+slippage included\n")
    print(pd.DataFrame(rows).to_string(index=False))
