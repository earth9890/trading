"""Daily-bar swing backtester with mandatory stops, realistic Indian delivery costs.

  python backtest.py                 # run every strategy on data/day/*.csv
  python backtest.py rsi2            # one strategy

Rules baked in (no look-ahead):
  - signal on day t close -> enter at day t+1 open
  - every trade has a stop from day 1; gap through stop fills at the open (worse)
  - stop and target hit same bar -> assume stop (pessimistic)
  - size = risk% of equity / (entry - stop), capped by free cash and max positions
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CAPITAL = 5000
RISK = 0.02          # 2% of equity per trade = Rs 100 at start
MAX_POS = 2
START = "2019-01-01"


def costs(buy_value, sell_value):
    # delivery: STT 0.1% both sides, stamp 0.015% buy, exch+SEBI ~0.0035% each side (+18% GST), DP Rs 23.6 per sell (Angel)
    exch = (buy_value + sell_value) * 0.000035 * 1.18
    dp = 23.6 if sell_value > 0 else 0  # Angel DP Rs 20 + GST, charged per sell only
    # Angel delivery brokerage: 0.1% per order, min Rs 5, max Rs 20, +18% GST (third-party sources 2026; verify vs contract note)
    brok = sum(min(20, max(5, 0.001 * v)) for v in (buy_value, sell_value) if v > 0) * 1.18
    return 0.001 * (buy_value + sell_value) + 0.00015 * buy_value + exch + dp + brok


def indicators(df):
    c, h, l = df["close"], df["high"], df["low"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["sma200"] = c.rolling(200).mean()
    df["sma50"] = c.rolling(50).mean()
    df["sma5"] = c.rolling(5).mean()
    d = c.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    df["rsi2"] = 100 - 100 / (1 + up.ewm(alpha=1 / 2).mean() / dn.ewm(alpha=1 / 2).mean())
    df["hh20"] = h.rolling(20).max().shift()   # prior 20-day high
    df["hh252"] = h.rolling(252).max()
    df["ll10"] = l.rolling(10).min()
    df["mom"] = c / c.shift(126) - 1           # 6-month momentum (ranking)
    df["near_high"] = c / df["hh252"]          # 1.0 = at 52-week high
    df["hh55"] = h.rolling(55).max().shift()
    df["ll20"] = l.rolling(20).min().shift()
    df["vol_ratio"] = df["volume"].rolling(3).mean() / df["volume"].rolling(50).mean()
    df["turnover"] = (c * df["volume"]).rolling(20).mean()
    return df


# Each strategy: entry(df) -> bool Series (signal at close), stop(row) -> price, exit rules.
STRATEGIES = {
    # 1) Connors RSI(2) pullback in uptrend + mandatory ATR stop + 7-day time stop
    "rsi2": dict(
        entry=lambda d: (d.close > d.sma200) & (d.rsi2 < 5),
        stop_atr=2.5, exit=lambda r: r.close > r.sma5, max_days=7, rank="rsi2",
    ),
    # 2) Donchian 55/20 breakout in uptrend with volume confirmation
    "donchian": dict(
        entry=lambda d: (d.close > d.hh55) & (d.close > d.sma200) & (d.vol_ratio >= 1.5),
        stop_atr=2.0, exit=lambda r: r.close < r.ll20, max_days=120, rank="mom",
    ),
    # 3) 52-week-high momentum (George & Hwang): hold strongest names near highs, exit below 50 DMA, 12% hard stop
    "mom52": dict(
        entry=lambda d: (d.near_high >= 0.97) & (d.close > d.sma200) & (d.mom > 0.15),
        stop_atr=2.5, exit=lambda r: r.close < r.sma50, max_days=250, rank="near_high",  # 12% stop -> position too small for Rs 5k
    ),
    # 4) 20-day breakout + chandelier trailing stop (3 ATR)
    "breakout": dict(
        entry=lambda d: (d.close > d.hh20) & (d.close > d.sma200) & (d.sma50 > d.sma200),
        stop_atr=2.0, trail_atr=3.0, exit=None, max_days=60, rank="mom",
    ),
}


def load():
    out = {}
    for f in sorted(Path(__file__).parent.glob("data/day/*.csv")):
        df = pd.read_csv(f, parse_dates=["time"]).set_index("time")
        df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
        if len(df) > 300:
            out[f.stem] = indicators(df)
    return out


def run(name, data, verbose=False):
    s = STRATEGIES[name]
    sig = {k: s["entry"](d).fillna(False) for k, d in data.items()}
    dates = sorted(set().union(*[d.index for d in data.values()]))
    dates = [t for t in dates if t >= pd.Timestamp(START)]
    cash, pos, trades, curve = CAPITAL, {}, [], []
    pending = []  # symbols to buy at next open

    for t in dates:
        # 1) entries at today's open from yesterday's signals
        for sym in pending:
            d = data[sym]
            if t not in d.index or sym in pos or len(pos) >= MAX_POS:
                continue
            i = d.index.get_loc(t)
            prev, bar = d.iloc[i - 1], d.iloc[i]
            entry = bar.open
            stop = entry * (1 - s["stop_pct"]) if s.get("stop_pct") else entry - s["stop_atr"] * prev.atr
            if not np.isfinite(stop) or stop <= 0 or entry - stop <= 0:
                continue
            equity = cash + sum(p["qty"] * data[k].close.asof(t) for k, p in pos.items())
            qty = int(min(RISK * equity / (entry - stop), cash * 0.98 / entry))
            if qty < 1 or qty * entry < 1000:  # ponytail: skip tiny trades, DP charge would eat them
                continue
            cash -= qty * entry
            pos[sym] = dict(qty=qty, entry=entry, stop=stop, risk=qty * (entry - stop), hi=entry, day=0, t0=t,
                            target=entry + s["target_atr"] * prev.atr if s.get("target_atr") else None)
        pending = []

        # 2) manage open positions on today's bar
        for sym in list(pos):
            d = data[sym]
            if t not in d.index:
                continue
            p, bar = pos[sym], d.loc[t]
            p["day"] += 1
            px = None
            if bar.low <= p["stop"]:
                px = min(bar.open, p["stop"])  # gap-down fills at open
            elif p["target"] and bar.high >= p["target"]:
                px = max(bar.open, p["target"])
            elif (s["exit"] and s["exit"](bar)) or p["day"] >= s["max_days"]:
                px = bar.close
            if px is None:
                if s.get("trail_atr"):  # chandelier trail, only ratchets up
                    p["hi"] = max(p["hi"], bar.close)
                    p["stop"] = max(p["stop"], p["hi"] - s["trail_atr"] * bar.atr)
                continue
            buy_v, sell_v = p["qty"] * p["entry"], p["qty"] * px
            pnl = sell_v - buy_v - costs(buy_v, sell_v)
            cash += sell_v - costs(buy_v, sell_v)
            trades.append(dict(sym=sym, t0=p["t0"], t1=t, entry=p["entry"], exit=px, qty=p["qty"],
                               pnl=pnl, r=pnl / p["risk"]))
            del pos[sym]

        # 3) today's signals -> tomorrow's buys, liquid names only, best ranked first
        cands = [k for k, d in data.items() if t in d.index and sig[k].get(t, False)
                 and d.at[t, "turnover"] > 20e7 and k not in pos]
        sign = 1 if s["rank"] == "rsi2" else -1  # rsi2: most oversold first; else highest first
        key = lambda k: sign * data[k].at[t, s["rank"]]
        pending = sorted(cands, key=key)[: MAX_POS - len(pos)]

        curve.append(cash + sum(p["qty"] * data[k].close.asof(t) for k, p in pos.items()))

    return report(name, pd.DataFrame(trades), pd.Series(curve, index=dates), verbose)


def report(name, tr, eq, verbose):
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    res = dict(strategy=name, trades=len(tr), final=round(eq.iloc[-1]), cagr=f"{(eq.iloc[-1] / CAPITAL) ** (1 / years) - 1:.1%}",
               max_dd=f"{dd:.1%}")
    if len(tr):
        w, l = tr[tr.pnl > 0], tr[tr.pnl <= 0]
        res.update(win=f"{len(w) / len(tr):.0%}", avg_win=round(w.pnl.mean()) if len(w) else 0,
                   avg_loss=round(l.pnl.mean()) if len(l) else 0,
                   pf=round(w.pnl.sum() / -l.pnl.sum(), 2) if len(l) and l.pnl.sum() else np.inf,
                   worst=round(tr.pnl.min()), avg_R=round(tr.r.mean(), 2))
        by_year = tr.groupby(tr.t1.dt.year).pnl.sum().round()
        res["by_year"] = dict(by_year)
    if verbose and len(tr):
        print(tr.tail(10).to_string())
    return res


if __name__ == "__main__":
    data = load()
    print(f"{len(data)} stocks loaded, capital Rs {CAPITAL}, risk {RISK:.0%}/trade, max {MAX_POS} positions\n")
    for n in (sys.argv[1:] or STRATEGIES):
        print(run(n, data, verbose=len(sys.argv) > 1))
