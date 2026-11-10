"""HYBRID backtest: each expiry morning the brain (blind opus, no tools, data up to 09:30 only) picks the day's
strategy -> BUY (bot's ORB15 breakout, no re-entry) / SELL (iron fly) / SKIP. PAPER research only.

  python options_hybrid_bt.py [N_DAYS=all]

Scored against fixed rules (always buy, always sell) and the oracle (best of the three each day), on both halves.
Iron fly is shown at IV x1.0 and x0.9 (the model over-prices morning options, so x0.9 is the conservative one).
Brain answers cached in docs/options_hybrid_brain.json -> results docs/options_hybrid.csv
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import options_bt as ob
import options_sell_bt as sb
from options_duel_bt import daily, packet

HERE = Path(__file__).parent
CACHE = HERE / "docs/options_hybrid_brain.json"
OUT = HERE / "docs/options_hybrid.csv"
CAPITAL = 30_000
CHOICES = ("BUY", "SELL", "SKIP")

PROMPT = """You are the strategy picker for a PAPER index-options experiment (no real money). Below is ALL market data available at 09:30 IST on a weekly EXPIRY day.

{pkt}

Pick exactly ONE plan for today:
- BUY: buy 1 lot ATM call/put on the first 5-min close outside the 09:15-09:30 range (before 13:00); exit if the index crosses back through the other side of the range, the option falls 30%, or 15:15. Wins big (+Rs 5k..15k) only on strong TREND days; loses Rs 1-3k on choppy/range days. Most days lose.
- SELL: at 09:30 sell the ATM call + ATM put and buy wings 4 strikes away (iron fly, max loss capped, ~Rs 600 costs). Wins Rs 1-5k on CALM range-bound days as expiry premium decays; loses up to ~Rs 6k on big trend days.
- SKIP: no trade (choose when neither edge is clear).

The question is: will the rest of today be a big trend day, a calm range day, or unclear? Use trend of last sessions, VIX level/change, gap, opening-range width, first bars. You have no tools; use only the data above.

Reply with ONLY one JSON line: {{"plan": "BUY|SELL|SKIP", "why": "<one sentence>"}}"""


def parse(text):
    import re
    d = json.loads(re.findall(r'\{[^{}]*"plan"[^{}]*\}', text)[-1])
    if d["plan"] not in CHOICES:
        raise ValueError(d["plan"])
    return d["plan"], d.get("why", "")


def ask(pkt):
    err = ""
    for _ in range(2):
        try:
            r = subprocess.run(["/Users/harish/.local/bin/claude", "-p", PROMPT.format(pkt=pkt), "--model", "opus",
                                "--permission-mode", "dontAsk"], capture_output=True, text=True, timeout=300,
                               cwd="/tmp", stdin=subprocess.DEVNULL)
            return parse(r.stdout)
        except Exception as e:
            err = str(e)[:100]
    return "SKIP", f"brain error: {err}"


def main(n):
    vix5, vix_d = ob.load("VIX").set_index("time").close, daily("VIX")
    days = []
    for idx in ("NIFTY", "SENSEX"):
        g_all, dl = ob.load(idx), daily(idx)
        tdays = sorted(g_all.d.unique())
        for e in sorted(ob.expiries(idx, tdays)):
            g = g_all[g_all.d == e]
            if len(g) >= 65 and len(dl[dl.index < e]) >= 15:
                days.append((e, idx, g, dl, tdays))
    days = sorted(days, key=lambda x: (x[0], x[1]))[-n:] if n else sorted(days, key=lambda x: (x[0], x[1]))

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = {f"{e}_{idx}": packet(idx, e, g.reset_index(drop=True), dl, vix_d, round(vix5.asof(g.time.iloc[2]), 2))
            for e, idx, g, dl, _ in days if f"{e}_{idx}" not in cache}
    print(f"{len(days)} days, asking brain for {len(todo)}", flush=True)
    keys = list(todo)
    with ThreadPoolExecutor(4) as ex:
        for i, (k, res) in enumerate(zip(keys, ex.map(ask, [todo[k] for k in keys]))):
            cache[k] = res
            if i % 10 == 9:
                CACHE.write_text(json.dumps(cache, indent=1))
                print(f"  {i + 1}/{len(keys)}", flush=True)
    CACHE.write_text(json.dumps(cache, indent=1))

    rows = []
    for e, idx, g, dl, tdays in days:
        ob.IV_MULT = 1.0
        d10 = ob.Day(idx, e, g, vix5, e, tdays)
        ob.IV_MULT = 0.9
        d09 = ob.Day(idx, e, g, vix5, e, tdays)
        ob.IV_MULT = 1.0
        buy = sum(t["net"] for t in ob.orb(d10))
        fly10 = sum(t["net"] for t in sb.iron_fly(d10))
        fly09 = sum(t["net"] for t in sb.iron_fly(d09))
        plan, why = cache[f"{e}_{idx}"]
        pick = lambda fly: {"BUY": buy, "SELL": fly, "SKIP": 0}[plan]
        rng = (g.high.max() - g.low.min()) / g.open.iloc[0] * 100
        rows.append(dict(day=e, idx=idx, plan=plan, day_range=round(rng, 2), buy=round(buy), fly=round(fly10),
                         fly_cons=round(fly09), hybrid=round(pick(fly10)), hybrid_cons=round(pick(fly09)),
                         oracle=round(max(buy, fly10, 0)), why=why))
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    half = len(df) // 2
    print(f"\n{len(df)} expiry days {df.day.min()} .. {df.day.max()}, Rs {CAPITAL:,}, 1 lot, NET after costs\n")
    print("brain plans:", df.plan.value_counts().to_dict())
    print("avg day range % by plan:", df.groupby("plan").day_range.mean().round(2).to_dict())
    out = []
    for col, name in [("buy", "always BUY (bot)"), ("fly", "always SELL (fly, IVx1.0)"), ("fly_cons", "always SELL (fly, IVx0.9)"),
                      ("hybrid", "HYBRID brain picks (IVx1.0)"), ("hybrid_cons", "HYBRID brain picks (IVx0.9)"), ("oracle", "oracle (perfect hindsight)")]:
        s = df[col]
        eq = CAPITAL + s.cumsum()
        out.append(dict(strategy=name, total=round(s.sum()), first_half=round(s[:half].sum()), second_half=round(s[half:].sum()),
                        last25=round(s[-25:].sum()), win_days=f"{(s > 0).sum()}/{(s != 0).sum()}", worst=round(s.min()),
                        maxDD=f"{(eq / eq.cummax() - 1).min():.0%}", min_equity=round(eq.min()), broke="YES" if eq.min() <= 0 else "no"))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(out).to_string(index=False))
    # was the brain's pick better than the other options on the days it chose?
    for p in CHOICES:
        sub = df[df.plan == p]
        if len(sub):
            print(f"  on {p} days ({len(sub)}): buy {sub.buy.sum():+,}  fly {sub.fly.sum():+,}  fly_cons {sub.fly_cons.sum():+,}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
