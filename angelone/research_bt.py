"""Research harness: own engine reusing backtest.py costs/load/indicators. Local CSVs only.
Signal at day-i close -> fill at i+1 open. Stops checked from entry day (gap fills at open)."""
import numpy as np, pandas as pd
import backtest as B

data = B.load()
bn = pd.read_csv("data/bench/NIFTYBEES.csv", parse_dates=["time"]).set_index("time")
bn.index = bn.index.tz_localize(None) if bn.index.tz is not None else bn.index
bn = B.indicators(bn)
data["NIFTYBEES"] = bn
D = bn.index
syms = list(data)
P = lambda col: pd.DataFrame({k: d[col] for k, d in data.items()}).reindex(D)
O, H, L, C, ATR, TO = (P(c).values for c in ("open", "high", "low", "close", "atr", "turnover"))
col = {s: j for j, s in enumerate(syms)}; BJ = col["NIFTYBEES"]
Cdf = P("close")
MOM6 = (Cdf / Cdf.shift(126) - 1).values
MOM12 = (Cdf.shift(21) / Cdf.shift(252) - 1).values
HH55, LL20, SMA200, VR, LL20_ = P("hh55").values, P("ll20").values, P("sma200").values, P("vol_ratio").values, P("ll20").values
REG = (bn.close > bn.sma200).values
RSI2 = bn.rsi2.values
MEND = np.r_[D[:-1].month != D[1:].month, False]
i0 = int(np.searchsorted(D, pd.Timestamp(B.START)))

def engine(plan, cap=5000, stop_pct=None, stop_atr=None, risk=0.02, maxpos=2):
    cash, pos, tr, eq = cap, {}, [], []
    pend = (set(), [])
    for i in range(i0, len(D)):
        sells, buys = pend
        for s in sells:                      # open fills
            if s in pos:
                p, px = pos.pop(s), O[i, col[s]]
                bv, sv = p[0] * p[1], p[0] * px
                c = B.costs(bv, sv); cash += sv - c; tr.append((D[i], sv - bv - c))
        e = cash + sum(p[0] * C[i - 1, col[s]] for s, p in pos.items())
        for s, w in buys:
            j = col[s]; o = O[i, j]
            if s in pos or not np.isfinite(o): continue
            a = ATR[i - 1, j]
            stop = o * (1 - stop_pct) if stop_pct and w is not None else (o - stop_atr * a if stop_atr else 0)
            if w is None:
                if not np.isfinite(stop) or o - stop <= 0: continue
                q = int(min(risk * e / (o - stop), cash * .98 / o))
            else:
                q = int(min(w * e, cash * .98) / o)
                if stop_pct: stop = o * (1 - stop_pct)
                elif stop_atr and np.isfinite(a): stop = o - stop_atr * a
            if q < 1 or not np.isfinite(stop): continue
            cash -= q * o; pos[s] = (q, o, stop)
        for s in list(pos):                  # intraday stops
            j = col[s]; q, en, st = pos[s]
            if L[i, j] <= st:
                px = min(O[i, j], st); bv, sv = q * en, q * px
                c = B.costs(bv, sv); cash += sv - c; tr.append((D[i], sv - bv - c)); del pos[s]
        eq.append(cash + sum(p[0] * C[i, col[s]] for s, p in pos.items()))
        pend = plan(i, set(pos), eq[-1], maxpos)
    return pd.Series(eq, index=D[i0:]), pd.DataFrame(tr, columns=["t", "pnl"])

def top(i, n, mom):
    m = np.where((TO[i] > 20e7) & (np.arange(len(syms)) != BJ), mom[i], np.nan)
    m = np.where(m > 0, m, np.nan)
    o = [j for j in np.argsort(-np.nan_to_num(m, nan=-9))[:n] if np.isfinite(m[j])]
    return [syms[j] for j in o]

def rot(n=1, mom=MOM6, fb="bees"):
    def plan(i, held, eq, mp):
        st = held - {"NIFTYBEES"}
        if not REG[i]:
            if fb == "bees": return st, ([] if "NIFTYBEES" in held else [("NIFTYBEES", 1.0)])
            return held, []
        if MEND[i] or "NIFTYBEES" in held:
            t = top(i, n, mom)
            if not t: t = ["NIFTYBEES"] if fb == "bees" else []
            return held - set(t), [(s, 1 / len(t)) for s in t if s not in held]
        return set(), []
    return plan

def don(regime=True, vol=True):
    S = (C > HH55) & (C > SMA200) & ((VR >= 1.5) if vol else True)
    def plan(i, held, eq, mp):
        sells = {s for s in held if C[i, col[s]] < LL20[i, col[s]]}
        if regime and not REG[i]: return sells, []
        ok = [j for j in range(len(syms)) if j != BJ and S[i, j] and TO[i, j] > 20e7 and syms[j] not in held]
        ok.sort(key=lambda j: -np.nan_to_num(MOM6[i, j], nan=-9))
        return sells, [(syms[j], None) for j in ok[: max(0, mp - len(held))]]
    return plan

def dip(N=10, mode="rsi"):
    since = {}
    def plan(i, held, eq, mp):
        if "NIFTYBEES" in held:
            since.setdefault("t", i)
            if i - since["t"] >= N: since.clear(); return {"NIFTYBEES"}, []
            return set(), []
        since.clear()
        sig = RSI2[i] < 10 if mode == "rsi" else C[i, BJ] < LL20[i, BJ]
        return set(), ([("NIFTYBEES", 1.0)] if sig else [])
    return plan

def stats(eq, tr, a, b):
    e = eq[a:b]
    if len(e) < 30: return None
    y = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / y) - 1; dd = (e / e.cummax() - 1).min()
    t = tr[(tr.t >= e.index[0]) & (tr.t <= e.index[-1])] if len(tr) else tr
    w, l = (t[t.pnl > 0], t[t.pnl <= 0]) if len(t) else (t, t)
    pf = w.pnl.sum() / -l.pnl.sum() if len(l) and l.pnl.sum() else float("nan")
    return cagr, dd, len(t), pf, (len(w) / len(t) if len(t) else float("nan"))

def row(name, eq, tr):
    out = [name]
    for a, b in ((None, None), ("2019", "2022"), ("2023", None)):
        s = stats(eq, tr, a, b)
        out += ["%.1f%%" % (s[0] * 100), "%.0f%%" % (s[1] * 100)] + ([s[2], "%.2f" % s[3], "%.0f%%" % (s[4] * 100)] if a is None else [])
    s = stats(eq, tr, None, None); out.append("%.2f" % (s[0] / abs(s[1])))
    return out

if __name__ == "__main__":
    R = []
    add = lambda n, e, t: R.append(row(n, e, t))
    bh = pd.Series(5000 * C[i0:, BJ] / O[i0, BJ], index=D[i0:]); E0 = pd.DataFrame(columns=["t", "pnl"])
    add("NIFTYBEES B&H", bh, E0)
    res = {}
    for nm, kw in [("rot n=1 6m bees-fb stop15%", dict(plan=rot(1), stop_pct=.15)),
                   ("rot n=2 6m bees-fb stop15%", dict(plan=rot(2), stop_pct=.15)),
                   ("rot n=1 12-1 bees-fb stop15%", dict(plan=rot(1, MOM12), stop_pct=.15)),
                   ("rot n=2 12-1 bees-fb stop15%", dict(plan=rot(2, MOM12), stop_pct=.15)),
                   ("rot n=2 6m cash-fb stop15%", dict(plan=rot(2, fb="cash"), stop_pct=.15)),
                   ("rot n=2 6m bees-fb stop2.5ATR", dict(plan=rot(2), stop_atr=2.5)),
                   ("rot n=3 6m bees-fb stop15%", dict(plan=rot(3), stop_pct=.15)),
                   ("don55/20 no filter 2%/2pos", dict(plan=don(False), stop_atr=2.0)),
                   ("don55/20 +regime 2%/2pos", dict(plan=don(True), stop_atr=2.0)),
                   ("don55/20 +regime novol 2%/2pos", dict(plan=don(True, False), stop_atr=2.0)),
                   ("don+regime 1%/2pos", dict(plan=don(True), stop_atr=2.0, risk=.01)),
                   ("don+regime 1%/1pos", dict(plan=don(True), stop_atr=2.0, risk=.01, maxpos=1)),
                   ("don+regime 2%/1pos", dict(plan=don(True), stop_atr=2.0, maxpos=1)),
                   ("dip rsi2<10 hold5", dict(plan=dip(5), stop_pct=.08)),
                   ("dip rsi2<10 hold10", dict(plan=dip(10), stop_pct=.08)),
                   ("dip 20d-low hold10", dict(plan=dip(10, "low"), stop_pct=.08)),
                   ("dip 20d-low hold20", dict(plan=dip(20, "low"), stop_pct=.08))]:
        e, t = engine(**kw); res[nm] = (e, t); add(nm, e, t)
    # core-satellite: 70% static B&H + 30% sat (capital 1500), no rebalance
    for sat in ("rot n=2 6m bees-fb stop15%", "don55/20 +regime 2%/2pos", "rot n=1 6m bees-fb stop15%"):
        kw = {"rot n=2 6m bees-fb stop15%": dict(plan=rot(2), stop_pct=.15), "rot n=1 6m bees-fb stop15%": dict(plan=rot(1), stop_pct=.15),
              "don55/20 +regime 2%/2pos": dict(plan=don(True), stop_atr=2.0)}[sat]
        e, t = engine(cap=1500, **kw); add("70%BH + 30% " + sat, 3500 * bh / 5000 + e, t)
    hdr = ["strategy", "CAGR", "maxDD", "trades", "PF", "win%", "IS CAGR", "IS DD", "OOS CAGR", "OOS DD", "CAGR/|DD|"]
    print("| " + " | ".join(hdr) + " |\n|" + "---|" * len(hdr))
    for r in R: print("| " + " | ".join(map(str, r)) + " |")
