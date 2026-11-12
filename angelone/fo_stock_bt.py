"""F&O STOCK option-BUYING backtest on NSE daily bhavcopies (research only, never trades).

  .venv/bin/python -I fo_stock_bt.py build   # data/fo_bhav/*.zip -> data/fo_compact.csv.gz (OPTSTK near 2 expiries +-20% strikes, FUTSTK)
  .venv/bin/python -I fo_stock_bt.py run     # -> docs/fo_stocks_bt.csv

Timing (no lookahead): signal uses day-t CLOSE data only; entry = day t+1 OPEN of the chosen contract (+slippage). The contract
(expiry/strike/liquidity) is picked from day-t data. Entry day's own high/low can trigger stop/target (stop assumed first if both).
Gap through stop/target fills at the open. Underlying volume/OI = sum over all FUTSTK expiries (no roll artefacts).
Universe is point-in-time (a stock is tradable only on days it has option rows), so no survivorship from list changes.
"""
import sys, zipfile, glob, io, os
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from options_bt import cost  # noqa: E402
EXCH = 0.0003503
CAP, MAXPOS, MAXLOT_COST = 30_000, 5, 6_000
MIN_VOL_LOTS, MIN_OI_LOTS = 20, 200       # liquidity on signal day: TtlTradgVol is already in lots (RELIANCE ATM 36k vs OI 10.6k lots); OI is in shares so /lot
MIN_TDAYS = 10                            # research rule: >=10 trading days to expiry at entry, else next month
EXIT_BEFORE = 3                           # research rule: exit by E-3 (physical settlement margin ramp)
N_SEEDS = 40                              # random-control seeds
COMPACT = HERE / "data/fo_compact.csv.gz"


def build():
    cols = ["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "HghPric", "LwPric", "ClsPric",
            "UndrlygPric", "OpnIntrst", "TtlTradgVol", "NewBrdLotQty"]
    out = []
    for f in sorted(glob.glob(str(HERE / "data/fo_bhav/*.zip"))):
        with zipfile.ZipFile(f) as z:
            df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), usecols=cols)
        df = df[df.FinInstrmTp.isin(["STO", "STF"])]
        o = df[df.FinInstrmTp == "STO"].copy()
        o["exp_rank"] = o.groupby("TckrSymb").XpryDt.rank(method="dense")
        o = o[(o.exp_rank <= 2) & ((o.StrkPric / o.UndrlygPric - 1).abs() <= 0.20)].drop(columns="exp_rank")
        out += [o, df[df.FinInstrmTp == "STF"]]
    pd.concat(out).to_csv(COMPACT, index=False)
    print("compact rows", sum(map(len, out)))


def load():
    df = pd.read_csv(COMPACT, parse_dates=["TradDt", "XpryDt"])
    df.columns = ["d", "tp", "sym", "exp", "k", "ot", "o", "h", "l", "c", "und", "oi", "vol", "lot"]
    dates = np.sort(df.d.unique())
    di = {d: i for i, d in enumerate(dates)}
    df["di"] = df.d.map(di)
    f = df[df.tp == "STF"]
    u = df.groupby(["sym", "di"]).und.median().unstack(0)          # spot close, days x sym
    fv, fo = (f.groupby(["sym", "di"])[x].sum().unstack(0) for x in ("vol", "oi"))
    opt = df[df.tp == "STO"]
    return dates, di, u, fv, fo, opt


class Mkt:
    def __init__(self):
        self.dates, self.di, self.u, self.fv, self.fo, opt = load()
        self.opt = opt
        self.byday = {i: g for i, g in opt.groupby("di")}
        # contract series: (sym,exp,k,ot) -> arrays keyed by di
        self.ser = {}
        for key, g in opt.groupby(["sym", "exp", "k", "ot"]):
            g = g.sort_values("di")
            self.ser[key] = (g.di.values, g[["o", "h", "l", "c"]].values, g.vol.values, g.oi.values, g.lot.iloc[-1])
        self.expday = {}  # expiry date -> index in trading calendar (or None if beyond data)

    def exp_idx(self, exp):
        return int(np.searchsorted(self.dates, np.datetime64(exp)))  # == len(dates) if beyond data

    def pick(self, sym, t, ot, k_otm=None, max_prem_pct=None):
        """Choose contract from day-t data. ot 'CE'/'PE'. k_otm strikes OTM from ATM, or cheapest-OTM under max_prem_pct of spot."""
        g = self.byday.get(t)
        if g is None: return None
        g = g[(g.sym == sym) & (g.ot == ot)]
        if g.empty: return None
        S = self.u.at[t, sym] if sym in self.u.columns else None
        if S is None or S != S: return None
        exps = sorted(g.exp.unique())
        today = pd.Timestamp(self.dates[t])
        ok = [e for e in exps if self.exp_idx(e) - t >= MIN_TDAYS]
        if not ok: return None
        g = g[g.exp == ok[0]].sort_values("k")
        ks = g.k.values
        atm = int(np.abs(ks - S).argmin())
        step = 1 if ot == "CE" else -1
        if max_prem_pct is None:
            j = atm + step * k_otm
            if not 0 <= j < len(g): return None
            r = g.iloc[j]
        else:
            r = None
            for j in range(atm + step, len(g) if step > 0 else -1, step):
                if g.iloc[j].c < max_prem_pct * S:
                    r = g.iloc[j]; break
            if r is None or r.c <= 0: return None
        if r.vol < MIN_VOL_LOTS or r.oi / r.lot < MIN_OI_LOTS or r.c <= 0: return None
        return (sym, r.exp, r.k, ot)

    def sim(self, key, t, stop, tgt, tstop, slip, cap=MAXLOT_COST):
        """Returns (entry_di, exit_di, net) for 1 lot, or None. stop/tgt are fractions or None; tstop = max days held (None = to expiry-3)."""
        di_, ohlc, vol, oi, lot = self.ser[key]
        e = np.searchsorted(di_, t + 1)
        if e >= len(di_) or di_[e] != t + 1 or vol[e] <= 0: return None   # must trade on entry day
        sl = lambda p: max(0.05, slip * p)
        ent = ohlc[e, 0] + sl(ohlc[e, 0])
        if ent * lot > cap or ent <= 0: return None
        exp_i = self.exp_idx(key[1])
        last = exp_i - EXIT_BEFORE                                                  # force-exit day (trading days before expiry)
        sp, tp = (ent * (1 - stop) if stop else None), (ent * (1 + tgt) if tgt else None)
        x = None
        for n in range(e, len(di_)):
            d = di_[n]
            if d > last and n > e: n -= 1; break
            o, h, l, c = ohlc[n]
            if vol[n] <= 0 and n > e: continue
            if sp is not None and (o <= sp if n > e else False): x = (d, o); break
            if sp is not None and l <= sp: x = (d, sp); break
            if tp is not None and (o >= tp if n > e else False): x = (d, o); break
            if tp is not None and h >= tp: x = (d, tp); break
            if d >= last or (tstop and d - di_[e] >= tstop): x = (d, c); break
        if x is None: x = (di_[n], ohlc[n, 3])                            # data ended
        xp = max(x[1] - sl(x[1]), 0.0)
        bv, sv = ent * lot, xp * lot
        return di_[e], x[0], sv - bv - cost(bv, sv, EXCH)


def signals(m):
    """-> {name: [(t, sym, ot, k_otm|None, max_prem|None, score)]}"""
    u, fv, fo = m.u, m.fv, m.fo
    ret = u.pct_change(fill_method=None)
    hi20 = u.shift(1).rolling(20).max(); lo20 = u.shift(1).rolling(20).min()
    vr = fv / fv.shift(1).rolling(20).mean()
    oich = fo.pct_change(fill_method=None)
    sma50 = u.rolling(50).mean(); r20 = u.pct_change(20, fill_method=None)
    rng = np.random.default_rng(7)
    S = {}
    def add(name, mask, ot, k=None, mp=None, score=None):
        sc = score if score is not None else ret.abs()
        out = []
        for t in range(55, len(m.dates) - 1):
            row = mask.iloc[t]
            for sym in row.index[row.fillna(False).values]:
                out.append((t, sym, ot, k, mp, float(sc.iat[t, u.columns.get_loc(sym)])))
        S[name] = out
    up_b, dn_b = (u >= hi20) & (vr > 2), (u <= lo20) & (vr > 2)
    for k in (0, 1, 2):
        add(f"breakout20_call_otm{k}", up_b, "CE", k, None, vr)
        add(f"breakout20_put_otm{k}", dn_b, "PE", k, None, vr)
    add("lottery_call_gain4", ret > 0.04, "CE", None, 0.015, ret)
    add("lottery_put_loss4", ret < -0.04, "PE", None, 0.015, -ret)
    trend = (u > sma50) & (r20.shift(1) > 0)
    for k in (0, 1):
        add(f"meanrev_call_dn5_otm{k}", (ret < -0.05) & trend, "CE", k, None, -ret)
    add("longbuildup_call_otm1", (ret > 0.02) & (oich > 0.05) & (vr > 1.5), "CE", 1, None, oich)
    add("shortbuildup_put_otm1", (ret < -0.02) & (oich > 0.05) & (vr > 1.5), "PE", 1, None, oich)
    return S


def random_signals(m, seed, ot):
    """Random control: ~5% of tradable stock-days, otm1 (same pick/exit rules as real strategies)."""
    rng = np.random.default_rng(seed)
    mask = pd.DataFrame(rng.random(m.u.shape) < 0.05, index=m.u.index, columns=m.u.columns) & m.u.notna()
    return [(t, sym, ot, 1, None, 1.0) for t in range(55, len(m.dates) - 1) for sym in mask.columns[mask.iloc[t].values]]


def portfolio(trades):
    """trades: [(entry_di, exit_di, net, cost_out)] already score-ordered per day. Max MAXPOS concurrent, cash CAP."""
    open_, taken, eq, peak, dd = [], [], 0.0, 0.0, 0.0
    for en, ex, net, outlay in sorted(trades, key=lambda x: x[0]):
        open_ = [p for p in open_ if p[0] > en]
        if len(open_) >= MAXPOS or sum(p[1] for p in open_) + outlay > CAP: continue
        open_.append((ex, outlay)); taken.append((ex, net))
    for ex, net in sorted(taken):
        eq += net; peak = max(peak, eq); dd = min(dd, eq - peak)
    return len(taken), sum(n for _, n in taken), dd


def evaluate(m, picks, mid, name, stop, tgt, ts, slip, cap):
    res = []
    for t, key in picks:
        r = m.sim(key, t, stop, tgt, ts, slip, cap)
        if r: res.append((r[0], r[1], r[2], m.ser[key][4] * m.ser[key][1][np.searchsorted(m.ser[key][0], r[0]), 0]))
    if not res: return None
    p = np.array([r[2] for r in res]); w, l = p[p > 0], p[p <= 0]
    half = np.array([r[0] <= mid for r in res])
    pn, pnet, pdd = portfolio(res)
    return dict(strategy=name, stop=stop, target=tgt, tstop=ts or "expiry-3", slip=slip, lot_cap=cap, trades=len(p),
                win_pct=round(100 * len(w) / len(p), 1), avg_win=round(w.mean()) if len(w) else 0,
                avg_loss=round(l.mean()) if len(l) else 0, net=round(p.sum()), best=round(p.max()),
                worst=round(p.min()), net_h1=round(p[half].sum()), n_h1=int(half.sum()),
                net_h2=round(p[~half].sum()), n_h2=int((~half).sum()),
                port_trades=pn, port_net=round(pnet), port_maxdd=round(pdd))


def make_picks(m, sigs):
    out = []
    for t, sym, ot, k, mp, sc in sorted(sigs, key=lambda x: (x[0], -x[5])):
        key = m.pick(sym, t, ot, k, mp)
        if key: out.append((t, key))
    return out


def run():
    m = Mkt()
    print("days", len(m.dates), m.dates[0], m.dates[-1], "contracts", len(m.ser), flush=True)
    S = signals(m)
    first, last = 55, len(m.dates) - 1
    mid = (first + last) // 2
    grid = [(s, g, n) for s in (0.3, 0.5) for g in (0.5, 1.0, 2.0) for n in (2, 5, 10, None)]
    cfgs = lambda base: ((0.01, 6000), (0.0, 6000), (0.02, 6000), (0.03, 6000), (0.01, 30000)) if base == (0.5, 1.0, 5) \
        else ((0.01, 6000), (0.01, 30000))
    rows = []
    for name, sigs in S.items():
        picks = make_picks(m, sigs)
        print(name, "signals", len(sigs), "picked", len(picks), flush=True)
        for g in grid:
            for slip, cap in cfgs(g):
                r = evaluate(m, picks, mid, name, *g, slip, cap)
                if r: rows.append(r)
    # random control: N_SEEDS seeds, per side; distribution of NET (total, h1, h2, per-trade) per config
    ctrl = {}
    for ot in ("CE", "PE"):
        for seed in range(N_SEEDS):
            picks = make_picks(m, random_signals(m, seed, ot))
            for g in grid:
                for slip, cap in cfgs(g):
                    r = evaluate(m, picks, mid, "", *g, slip, cap)
                    if r: ctrl.setdefault((ot, g, slip, cap), []).append(r)
        print("control", ot, "done", flush=True)
    q = lambda a, x: float(np.percentile(a, x))
    cd = {}
    for (ot, g, slip, cap), rs in ctrl.items():
        a = lambda k: np.array([r[k] for r in rs], float)
        pt = lambda h: np.array([r["net_" + h] / max(r["n_" + h], 1) for r in rs])
        cd[(ot, g, slip, cap)] = dict(p95=q(pt("h1"), 95), p95b=q(pt("h2"), 95))
        row = dict(strategy="CONTROL_random_" + ("call" if ot == "CE" else "put") + f"_otm1_x{N_SEEDS}seeds", stop=g[0], target=g[1],
                   tstop=g[2] or "expiry-3", slip=slip, lot_cap=cap, trades=round(a("trades").mean()),
                   win_pct=round(a("win_pct").mean(), 1), avg_win=round(a("avg_win").mean()), avg_loss=round(a("avg_loss").mean()),
                   net=round(a("net").mean()), net_p5=round(q(a("net"), 5)), net_p95=round(q(a("net"), 95)),
                   best=round(a("best").mean()), worst=round(a("worst").mean()), net_h1=round(a("net_h1").mean()), n_h1=round(a("n_h1").mean()),
                   net_h2=round(a("net_h2").mean()), n_h2=round(a("n_h2").mean()), port_trades=round(a("port_trades").mean()),
                   port_net=round(a("port_net").mean()), port_maxdd=round(a("port_maxdd").mean()))
        rows.append(row)
    # edge flag: positive AND per-trade net in BOTH halves beats the random control's 95th pct per-trade (same side/exit/slip/cap)
    for r in rows:
        r.setdefault("net_p5", ""); r.setdefault("net_p95", "")
        c = cd.get(("CE" if "call" in r["strategy"] else "PE", (r["stop"], r["target"], None if r["tstop"] == "expiry-3" else r["tstop"]),
                    r["slip"], r["lot_cap"]))
        r["edge"] = ""
        if c and not r["strategy"].startswith("CONTROL"):
            r["edge"] = int(r["trades"] >= 50 and r["n_h1"] >= 15 and r["n_h2"] >= 15 and r["net_h1"] > 0 and r["net_h2"] > 0 and
                            r["net_h1"] / r["n_h1"] > c["p95"] and r["net_h2"] / r["n_h2"] > c["p95b"])
    pd.DataFrame(rows).to_csv(HERE / "docs/fo_stocks_bt.csv", index=False)
    print("wrote", len(rows), "rows")


if __name__ == "__main__":
    {"build": build, "run": run}[sys.argv[1]]()
