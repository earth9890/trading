"""Intraday (MIS) backtest on 1y of 5-min candles, NIFTY-100 universe, realistic Angel costs.

  python intraday_bt.py          # needs data/5min/*.csv (python fetch.py 5min 365)

Fills are conservative: entry next bar open + slippage, stop checked before target inside a bar,
gaps through the stop fill at the bar open, everything flat by 15:15.
"""
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).parent / "data/5min"
CAPITAL, SLIP, MAXT = 10_000, 0.0005, 2       # Rs; 0.05% per side (LIMIT at touch on liquid names); trades/day
EXIT_T = pd.Timestamp("15:15").time()


def cost(notional):
    """Angel intraday round trip on one side's notional (buy + sell, same size)."""
    brok = 2 * min(20, 0.001 * notional)                   # Rs 20 or 0.1% per order, lower
    exch = 2 * 0.0000297 * notional
    return brok + exch + 0.00025 * notional + 0.00003 * notional + 0.18 * (brok + exch) + 2 * 1e-6 * notional


def load():
    out = {}
    for f in sorted(D.glob("*.csv")):
        df = pd.read_csv(f, parse_dates=["time"])
        df["time"] = df["time"].dt.tz_localize(None) if df["time"].dt.tz is not None else df["time"]
        df = df[(df.time.dt.time >= pd.Timestamp("09:15").time()) & (df.time.dt.time <= pd.Timestamp("15:25").time())]
        if (df.close * df.volume).groupby(df.time.dt.date).sum().median() > 50e7:   # >Rs 50cr/day: liquid only
            out[f.stem] = df
    return out


def walk(bars, side, entry, stop, target):
    """bars after entry. Returns exit price (stop first, then target, else 15:15 close)."""
    for t, o, h, l, c in bars:
        if side > 0:
            if l <= stop:
                return min(o, stop) * (1 - SLIP)
            if target and h >= target:
                return target
        else:
            if h >= stop:
                return max(o, stop) * (1 + SLIP)
            if target and l <= target:
                return target
        if t >= EXIT_T:
            return c * (1 - SLIP * side)
    return c * (1 - SLIP * side)


def days(df):
    for d, g in df.groupby(df.time.dt.date):
        if len(g) >= 70:
            yield d, list(zip(g.time.dt.time, g.open, g.high, g.low, g.close)), g


def orb(data, rr=None, n=3, max_rng=0.015):
    """Opening range (first n bars) breakout, both sides, stop = other side of range, target rr*R or EOD."""
    tr = []
    for sym, df in data.items():
        for d, b, _ in days(df):
            hi, lo = max(x[2] for x in b[:n]), min(x[3] for x in b[:n])
            if (hi - lo) / lo > max_rng:
                continue
            for i in range(n, len(b) - 1):
                t, o, h, l, c = b[i]
                if t >= pd.Timestamp("14:00").time():
                    break
                side = 1 if c > hi else -1 if c < lo else 0
                if side:
                    e = b[i + 1][1] * (1 + SLIP * side)
                    stop = lo if side > 0 else hi
                    tgt = e + side * rr * abs(e - stop) if rr else None
                    x = walk(b[i + 1:], side, e, stop, tgt)
                    tr.append((d, b[i + 1][0], sym, side * (x / e - 1)))
                    break
    return tr


def gap_fade(data, gap=0.01, stop=0.01):
    """Gap > 1% vs yesterday close: fade it from 09:20, target yesterday close, stop 1%, EOD exit."""
    tr = []
    for sym, df in data.items():
        prev = None
        for d, b, _ in days(df):
            if prev:
                g = b[0][1] / prev - 1
                if abs(g) > gap:
                    side = -1 if g > 0 else 1
                    e = b[1][1] * (1 + SLIP * side)
                    x = walk(b[1:], side, e, e * (1 - side * stop), prev)
                    tr.append((d, b[1][0], sym, side * (x / e - 1)))
            prev = b[-1][4]
    return tr


def first_hour_rs(data, top=2, stop=0.01):
    """10:15: long the strongest (from open) stocks when market (avg) is up, short weakest when down. Stop 1%, EOD."""
    snap = {}
    for sym, df in data.items():
        for d, b, _ in days(df):
            k = next((i for i, x in enumerate(b) if x[0] >= pd.Timestamp("10:15").time()), None)
            if k:
                snap.setdefault(d, []).append((b[k - 1][4] / b[0][1] - 1, sym, b[k:]))
    tr = []
    for d, rows in snap.items():
        mkt = np.mean([r[0] for r in rows])
        rows.sort(key=lambda r: -r[0])
        pick, side = (rows[:top], 1) if mkt > 0 else (rows[-top:], -1)
        for _, sym, b in pick:
            e = b[0][1] * (1 + SLIP * side)
            x = walk(b, side, e, e * (1 - side * stop), None)
            tr.append((d, b[0][0], sym, side * (x / e - 1)))
    return tr


def last_half_hour(data):
    """Gao et al. intraday momentum: first-30-min return (incl. overnight) sign -> trade 14:55-15:15 in that direction."""
    tr = []
    for sym, df in data.items():
        prev = None
        for d, b, _ in days(df):
            k = next((i for i, x in enumerate(b) if x[0] >= pd.Timestamp("14:55").time()), None)
            if prev and k:
                side = 1 if b[5][4] > prev else -1
                e = b[k][1] * (1 + SLIP * side)
                x = walk(b[k:], side, e, e * (1 - side * 0.01), None)
                tr.append((d, b[k][0], sym, side * (x / e - 1)))
            prev = b[-1][4]
    return tr


def portfolio(trades, lev):
    """Per day take the first MAXT trades by entry time, capital*lev split across them."""
    if not trades:
        return dict(trades=0)
    t = pd.DataFrame(trades, columns=["day", "t", "sym", "ret"]).sort_values(["day", "t"])
    t = t.groupby("day").head(MAXT)
    per = CAPITAL * lev / MAXT
    t["pnl"] = per * t.ret - t.apply(lambda r: cost(per), axis=1)
    daily = t.groupby("day").pnl.sum()
    eq = CAPITAL + daily.cumsum()
    return dict(trades=len(t), win=f"{(t.pnl > 0).mean():.0%}", gross_bps=round(t.ret.mean() * 1e4, 1),
                cost_bps=round(cost(per) / per * 1e4, 1), net_pnl=round(daily.sum()),
                ret=f"{daily.sum() / CAPITAL:.0%}", maxdd=f"{(eq / eq.cummax() - 1).min():.0%}",
                worst_day=round(daily.min()), days=f"{(daily > 0).mean():.0%} green")


if __name__ == "__main__":
    data = load()
    span = min(df.time.min() for df in data.values()).date(), max(df.time.max() for df in data.values()).date()
    print(f"{len(data)} liquid stocks, {span[0]} .. {span[1]}, capital Rs {CAPITAL:,}, {MAXT} trades/day max\n")
    tests = {"ORB15 EOD": lambda: orb(data), "ORB15 2R": lambda: orb(data, rr=2), "ORB15 1R": lambda: orb(data, rr=1),
             "ORB30 EOD": lambda: orb(data, n=6, max_rng=0.02), "gap fade 1%": lambda: gap_fade(data),
             "first-hour RS": lambda: first_hour_rs(data), "last half-hour mom": lambda: last_half_hour(data)}
    rows = []
    for name, fn in tests.items():
        tr = fn()
        for lev in (1, 5):
            rows.append(dict(strategy=name, lev=f"{lev}x", **portfolio(tr, lev)))
    print(pd.DataFrame(rows).to_string(index=False))
