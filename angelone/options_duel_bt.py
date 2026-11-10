"""Bot vs Brain options backtest over the last N expiry days (NIFTY + SENSEX). PAPER research only.

  python options_duel_bt.py [N=25]

BOT   = options_bt.orb with one re-entry (the live paper rules).
BRAIN = headless Claude (opus, NO tools -> can't look ahead) reads the same 09:30 packet the live brain gets and picks
        TRADE / CALLS_ONLY / PUTS_ONLY / SKIP; then the same rules on the allowed side.
Option prices are modelled (Black-Scholes on 5-min index, calibrated IV; expired contracts have no candles).
Brain answers are cached in docs/options_duel_brain.json. Output: docs/options_duel.csv
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import options_bt as ob
from options_paper import ALLOW, parse_decision

HERE = Path(__file__).parent
CACHE = HERE / "docs/options_duel_brain.json"
OUT = HERE / "docs/options_duel.csv"


def daily(name):
    df = pd.read_csv(ob.D / f"{name}.csv")
    df["d"] = pd.to_datetime(df.time.str[:10]).dt.date
    return df.groupby("d").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))


def packet(idx, d, g, dl, vix_d, vix_now):
    hi, lo = g.high[:3].max(), g.low[:3].min()
    out = [f"INDEX: {idx}   DATE: {d} ({d:%A}) - weekly EXPIRY day   TIME NOW: 09:30 IST", "",
           "Last 15 sessions (daily):  date  open  high  low  close  | India VIX close"]
    for dd, r in dl[dl.index < d].tail(15).iterrows():
        out.append(f"  {dd}  {r.open}  {r.high}  {r.low}  {r.close}  | {vix_d.close.get(dd, '?')}")
    out += ["", "Today so far (5-min bars):  time  open  high  low  close"]
    out += [f"  {r.time:%H:%M:%S}  {r.open}  {r.high}  {r.low}  {r.close}" for r in g.head(3).itertuples()]
    out += [f"India VIX now: {vix_now}", f"Opening range (09:15-09:30): high {hi}  low {lo}"]
    return "\n".join(out)


PROMPT = """You are the trading brain for a PAPER options experiment (no real money). Below is ALL market data available at 09:30 IST on that day.

{pkt}

The bot's rule today (weekly expiry day): at the first 5-min close outside the 09:15-09:30 opening range (before 13:00) it buys 1 lot of the ATM CALL (break above) or ATM PUT (break below); exits when the index crosses the other side of the range, or the option falls 30%, or at 15:15; one re-entry after a loss. Costs ~Rs 120/round trip; option buyers lose to theta on flat days and win big on trend days.

Your job: decide for THIS day only: TRADE (allow both directions), CALLS_ONLY, PUTS_ONLY, or SKIP. Consider trend of the last sessions, VIX level/change, gap, opening-range width. You have no tools; use only the data above.

Reply with ONLY one JSON line: {{"decision": "TRADE|CALLS_ONLY|PUTS_ONLY|SKIP", "why": "<one sentence>"}}"""


def ask_brain(pkt):
    for _ in range(2):
        try:
            r = subprocess.run(["/Users/harish/.local/bin/claude", "-p", PROMPT.format(pkt=pkt), "--model", "opus",
                                "--permission-mode", "dontAsk"], capture_output=True, text=True, timeout=300,
                               cwd="/tmp", stdin=subprocess.DEVNULL)
            return parse_decision(r.stdout)
        except Exception as e:
            err = str(e)[:100]
    return "SKIP", f"brain error: {err}"


def features(g, dl, vix_d, d, prev_close):
    hi, lo = g.high[:3].max(), g.low[:3].min()
    past = dl[dl.index < d]
    vx = vix_d.close
    vprev = vx[vx.index < d]
    return dict(gap=round((g.open[0] / prev_close - 1) * 100, 2), or_width=round((hi - lo) / g.open[0] * 100, 2),
                trend5=round((past.close.iloc[-1] / past.close.iloc[-6] - 1) * 100, 2),
                vix=round(vprev.iloc[-1], 2), vix_chg=round(vprev.iloc[-1] - vprev.iloc[-6], 2),
                day_move=round((g.close.iloc[-1] / g.open[0] - 1) * 100, 2),
                day_range=round((g.high.max() - g.low.min()) / g.open[0] * 100, 2))


def main(n):
    vix5 = ob.load("VIX").set_index("time").close
    vix_d = daily("VIX")
    days = []
    for idx in ("NIFTY", "SENSEX"):
        g_all, dl = ob.load(idx), daily(idx)
        tdays = sorted(g_all.d.unique())
        for e in sorted(ob.expiries(idx, tdays)):
            g = g_all[g_all.d == e]
            if len(g) >= 65:
                days.append((e, idx, g, dl, tdays))
    days = sorted(days, key=lambda x: (x[0], x[1]))[-n:]

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    jobs = {}
    for e, idx, g, dl, tdays in days:
        key = f"{e}_{idx}"
        if key not in cache:
            g = g.reset_index(drop=True)
            jobs[key] = packet(idx, e, g, dl, vix_d, round(vix5.asof(g.time[2]), 2))
    with ThreadPoolExecutor(4) as ex:
        for key, res in zip(jobs, ex.map(ask_brain, jobs.values())):
            cache[key] = res
            print("brain", key, res[0], flush=True)
    CACHE.write_text(json.dumps(cache, indent=1))

    rows = []
    for e, idx, g, dl, tdays in days:
        day = ob.Day(idx, e, g, vix5, e, tdays)
        dec, why = cache[f"{e}_{idx}"]
        bot = ob.orb(day, reentry=True)
        brain = ob.orb(day, reentry=True, allow=ALLOW[dec])
        prev = dl[dl.index < e].close.iloc[-1]
        f = lambda ts, k: round(sum(t[k] for t in ts))
        rows.append(dict(day=e, idx=idx, brain=dec, bot_trades=len(bot),
                         bot_sides="/".join("C" if t["call"] else "P" for t in bot),
                         bot_net=f(bot, "net"), brain_net=f(brain, "net"),
                         **features(day.g, dl, vix_d, e, prev), why=why))
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    pd.set_option("display.width", 250)
    print(df.drop(columns="why").to_string(index=False))
    for who in ("bot", "brain"):
        s = df[f"{who}_net"]
        eq = ob.CAPITAL + s.cumsum()
        print(f"{who.upper():6} total NET {s.sum():+,.0f}  days won {(s > 0).sum()}/{(s != 0).sum()} traded  "
              f"best {s.max():+,.0f} worst {s.min():+,.0f}  maxDD {(eq / eq.cummax() - 1).min():.0%}  min equity {eq.min():,.0f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 25)
