"""PAPER options duel (dry run, NEVER places orders): expiry-day 15-min ORB on NIFTY (Tue) / SENSEX (Thu), BOT vs BRAIN.

  python options_paper.py        # launchd 09:17 weekdays; exits at once if today is not an expiry day

Real live prices (Angel ltpData) for the index and the ATM option, fake Rs 10k each, 1 lot, full costs (options_bt.cost).
Rules = options_bt.orb: range 09:15-09:30, first 5-min close outside -> buy ATM call/put; exit when index crosses the
other side of the range, option -30%, or 15:15. No re-entry (dropped 2026-11-10, docs/options_ideas.csv).
  BOT   takes every signal                                   -> journal_options_paper.csv
  BRAIN (headless Claude, 09:31 data packet) picks TRADE / CALLS_ONLY / PUTS_ONLY / SKIP; same rules on its
        allowed side, from the bars after its decision       -> journal_options_brain.csv
"""
import csv
import json
import re
import subprocess
import threading
import time
from datetime import date, datetime, timedelta, time as T
from pathlib import Path

import angel
import options_bt as ob
import trader  # paper mode: only log/alert/market_day are used

HERE = Path(__file__).parent
JOURNALS = {"BOT": HERE / "journal_options_paper.csv", "BRAIN": HERE / "journal_options_brain.csv",
            "FLOW": HERE / "journal_options_flow.csv", "FLY": HERE / "journal_options_fly.csv"}
CAPITAL = 30_000   # fake money per player (user, 2026-11-10)
INDEX = {"NIFTY": dict(exch="NSE", tok="99926000", sym="Nifty 50", oexch="NFO"),
         "SENSEX": dict(exch="BSE", tok="99919000", sym="SENSEX", oexch="BFO")}
VIX = dict(exch="NSE", tok="99926017")
ALLOW = {"TRADE": (1, -1), "CALLS_ONLY": (1,), "PUTS_ONLY": (-1,), "SKIP": ()}
API_LOCK = threading.Lock()   # BOT + BRAIN share one session and one rate limit; keep calls serial


def todays_expiry_index():
    """NIFTY or SENSEX if today is its weekly expiry (from the scrip master), else None."""
    m = json.loads((HERE / "data/scripmaster.json").read_text())
    today = date.today()
    for name in ("NIFTY", "SENSEX"):
        exps = {datetime.strptime(x["expiry"], "%d%b%Y").date() for x in m
                if x.get("name") == name and x.get("instrumenttype") == "OPTIDX"}
        if today in exps:
            return name, today.strftime("%d%b%Y").upper(), m
    return None, None, m


def ltp(api, exch, sym, tok):
    for w in (1, 3, 10):
        try:
            with API_LOCK:
                r = api.ltpData(exch, sym, tok)
                time.sleep(0.4)
            if r.get("status"):
                return float(r["data"]["ltp"])
        except Exception:
            pass
        time.sleep(w)
    return None


def candles(api, exch, tok, interval="FIVE_MINUTE", start=None):
    start = start or f"{date.today()} 09:15"
    for w in (3, 10, 30, 60):   # rate-limit replies are non-JSON -> SDK raises (crashed 2026-11-09 09:31)
        try:
            with API_LOCK:
                r = api.getCandleData(dict(exchange=exch, symboltoken=tok, interval=interval,
                                           fromdate=start, todate=f"{date.today()} 15:30"))
                time.sleep(1)
            if r.get("data"):
                return r["data"]
        except Exception:
            pass
        time.sleep(w)
    return []


def bars(api, idx):
    return candles(api, INDEX[idx]["exch"], INDEX[idx]["tok"])


def book(who, row):
    j = JOURNALS[who]
    new = not j.exists()
    with j.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def equity(who):
    j = JOURNALS[who]
    if not j.exists():
        return CAPITAL
    return CAPITAL + sum(float(r["net"]) for r in csv.DictReader(j.open()))


def packet(api, idx, b, hi, lo):
    """Same 09:30 data the brain saw in the 30-day backtest (scratchpad brain_days/*.txt format)."""
    start = f"{date.today() - timedelta(days=30)} 09:15"
    daily = candles(api, INDEX[idx]["exch"], INDEX[idx]["tok"], "ONE_DAY", start)
    vix = {c[0][:10]: c[4] for c in candles(api, VIX["exch"], VIX["tok"], "ONE_DAY", start)}
    today = str(date.today())
    out = [f"INDEX: {idx}   DATE: {today} ({date.today():%A}) - weekly EXPIRY day   TIME NOW: 09:30 IST", "",
           "Last 15 sessions (daily):  date  open  high  low  close  | India VIX close"]
    out += [f"  {c[0][:10]}  {c[1]}  {c[2]}  {c[3]}  {c[4]}  | {vix.get(c[0][:10], '?')}"
            for c in [c for c in daily if c[0][:10] < today][-15:]]
    out += ["", "Today so far (5-min bars):  time  open  high  low  close"]
    out += [f"  {c[0][11:19]}  {c[1]}  {c[2]}  {c[3]}  {c[4]}" for c in b[:3]]
    out += [f"India VIX now: {vix.get(today, '?')}", f"Opening range (09:15-09:30): high {hi}  low {lo}"]
    return "\n".join(out)


def flow_signal(idx, step):
    """Order flow at 09:30 from options_recorder.py snapshots: new PUT writing > new CALL writing near ATM = bullish.
    Returns (decision, summary). Forward experiment: 28-day check was 54% (coin flip), docs/options_flow.csv."""
    f = HERE / f"data/flow/{date.today()}_{idx}.csv"
    if not f.exists():
        return "SKIP", "no recorder data"
    rows = list(csv.DictReader(f.open()))
    first, last = rows[0]["time"], max(r["time"] for r in rows if r["time"][11:16] <= "09:30")
    S = float([r for r in rows if r["time"] == last][0]["spot"])
    K = round(S / step) * step
    tot = lambda t, typ: sum(float(r["oi"] or 0) for r in rows
                             if r["time"] == t and r["typ"] == typ and abs(int(r["strike"]) - K) <= 5 * step)
    ce0, pe0, ce1, pe1 = tot(first, "CE"), tot(first, "PE"), tot(last, "CE"), tot(last, "PE")
    if not (ce0 and pe0 and ce1 and pe1):
        return "SKIP", "incomplete recorder data"
    flow = ((pe1 - pe0) - (ce1 - ce0)) / (ce0 + pe0)
    summary = (f"PCR {pe1 / ce1:.2f}; since prev close (ATM+-5) CE OI {ce1 - ce0:+,.0f}, PE OI {pe1 - pe0:+,.0f}; "
               f"flow {flow:+.1%} ({'put writing > call writing = support' if flow > 0 else 'call writing > put writing = resistance'})")
    return ("CALLS_ONLY" if flow > 0 else "PUTS_ONLY"), summary


def parse_decision(text):
    d = json.loads(re.findall(r'\{[^{}]*"decision"[^{}]*\}', text)[-1])
    if d["decision"] not in ALLOW:
        raise ValueError(f"bad decision {d['decision']}")
    return d["decision"], d.get("why", "")


def brain_decision(pkt):
    """Headless Claude picks the side. Any failure -> SKIP (brain sits out, alerted)."""
    prompt = f"""You are the trading brain for a PAPER options experiment (no real money). Below is the market data at 09:30 IST today.

{pkt}

The bot's rule today (weekly expiry day): at the first 5-min close outside the 09:15-09:30 opening range (before 13:00) it buys 1 lot of the ATM CALL (break above) or ATM PUT (break below); exits when the index crosses the other side of the range, or the option falls 30%, or at 15:15; no re-entry. Costs ~Rs 120/round trip; option buyers lose to theta on flat days and win big on trend days.

Your job: decide for TODAY only: TRADE (allow both directions), CALLS_ONLY, PUTS_ONLY, or SKIP. Consider trend of the last sessions, VIX level/change, gap, opening-range width, and scheduled events. You MAY use WebSearch for today's scheduled events and overnight global cues. Be quick (under 4 minutes).

Reply with ONLY one JSON line: {{"decision": "TRADE|CALLS_ONLY|PUTS_ONLY|SKIP", "why": "<one sentence>"}}"""
    try:
        r = subprocess.run(["/Users/harish/.local/bin/claude", "-p", prompt, "--model", "opus",
                            "--permission-mode", "dontAsk", "--allowedTools", "WebSearch"],
                           capture_output=True, text=True, timeout=420, cwd=HERE, stdin=subprocess.DEVNULL)
        return parse_decision(r.stdout)
    except Exception as e:
        trader.alert(f"OPTIONS BRAIN failed ({str(e)[:100]}) - brain sits out today")
        return "SKIP", "brain error"


def trade_loop(who, allow, api, idx, exp, m, hi, lo, seen):
    """One paper trader. allow = sides it may take (1 call, -1 put); seen = bars already looked at."""
    sp, info = ob.SPEC[idx], INDEX[idx]
    reentry, trades = False, 0   # no re-entry: 2y test 2026-11-10 -97k vs -275k with it, better in both halves
    while allow and datetime.now().time() < T(13, 0) and trades < 2:
        time.sleep(30)
        done = bars(api, idx)[:-1]                      # last bar still forming
        if len(done) <= seen:
            continue
        x, seen = done[-1], len(done)
        side = 1 if x[4] > hi else -1 if x[4] < lo else 0
        if not side or side not in allow:
            continue
        S = ltp(api, info["exch"], info["sym"], info["tok"])
        K = round(S / sp["step"]) * sp["step"]
        typ = "CE" if side > 0 else "PE"
        o = next((y for y in m if y.get("name") == idx and y.get("expiry") == exp and y.get("instrumenttype") == "OPTIDX"
                  and float(y["strike"]) / 100 == K and y["symbol"].endswith(typ)), None)
        p0 = o and ltp(api, info["oexch"], o["symbol"], o["token"])
        if not p0:
            trader.log(f"options {who}: no option price", idx, K, typ); break
        buy = p0 * (1 + ob.SLIP_PCT) + ob.SLIP_ABS
        if buy * sp["lot"] > equity(who) * 0.9:
            trader.log(f"options {who}: 1 lot {buy * sp['lot']:.0f} > 90% of equity - skip"); break
        stop_idx, t0, p, why = (lo if side > 0 else hi), datetime.now(), p0, "15:15"
        trader.log(f"options {who} PAPER BUY {o['symbol']} 1 lot ({sp['lot']}) @ {buy:.2f} idx {S} stop idx {stop_idx}")
        while datetime.now().time() < T(15, 15):
            time.sleep(15)
            S, q = ltp(api, info["exch"], info["sym"], info["tok"]), ltp(api, info["oexch"], o["symbol"], o["token"])
            if S is None or q is None:
                continue
            p = q
            if (side > 0 and S <= stop_idx) or (side < 0 and S >= stop_idx):
                why = "index stop"; break
            if p <= buy * 0.70:
                why = "-30% stop"; break
        p = ltp(api, info["oexch"], o["symbol"], o["token"]) or p
        sell = max(p * (1 - ob.SLIP_PCT) - ob.SLIP_ABS, 0.05)
        q = sp["lot"]
        gross = (sell - buy) * q
        net = gross - ob.cost(buy * q, sell * q, sp["exch"])
        book(who, dict(day=date.today(), idx=idx, option=o["symbol"], qty=q, t_in=t0.strftime("%H:%M"),
                       t_out=datetime.now().strftime("%H:%M"), buy=round(buy, 2), sell=round(sell, 2),
                       gross=round(gross, 2), net=round(net, 2), exit=why))
        trades += 1
        trader.alert(f"OPTIONS {who} {o['symbol']}: NET {net:+.0f} (gross {gross:+.0f}, {why}) equity {equity(who):.0f}")
        if net > 0 or not reentry:
            break
        reentry = False
        hi, lo = max(hi, x[2]), min(lo, x[3])


def fly_loop(api, idx, exp, m):
    """FLY: hedged SELLER. 09:31 sell ATM call+put, buy wings +-4 strikes (max loss capped). Exit 15:15 or when open
    loss >= credit. Model backtest +36k..+143k/2y (options_sell_bt.py) but the model over-prices morning options, so
    only real prices count - this is the real-price test."""
    sp, info = ob.SPEC[idx], INDEX[idx]
    S = ltp(api, info["exch"], info["sym"], info["tok"])
    K, w, q = round(S / sp["step"]) * sp["step"], 4 * sp["step"], sp["lot"]
    find = lambda k, typ: next((y for y in m if y.get("name") == idx and y.get("expiry") == exp and y.get("instrumenttype") == "OPTIDX"
                                and float(y["strike"]) / 100 == k and y["symbol"].endswith(typ)), None)
    legs = [(find(K, "CE"), -1), (find(K, "PE"), -1), (find(K + w, "CE"), 1), (find(K - w, "PE"), 1)]
    if not all(o for o, _ in legs):
        return trader.log("options FLY: missing contract")
    px = lambda: [ltp(api, info["oexch"], o["symbol"], o["token"]) for o, _ in legs]
    p0 = px()
    if None in p0:
        return trader.log("options FLY: no prices")
    fill0 = [p * (1 + ob.SLIP_PCT * s) + ob.SLIP_ABS * s for p, (_, s) in zip(p0, legs)]
    credit = -sum(f * s for f, (_, s) in zip(fill0, legs))
    if credit <= 0 or (w - credit) * q > equity("FLY") * 0.9:
        return trader.log(f"options FLY: skip (credit {credit:.1f}, max loss {(w - credit) * q:.0f})")
    t0, why, p = datetime.now(), "15:15", p0
    trader.log(f"options FLY PAPER SELL {idx} {K} fly +-{w} credit {credit:.2f} x {q} (max loss {(w - credit) * q:.0f})")
    while datetime.now().time() < T(15, 15):
        time.sleep(30)
        now = px()
        if None in now:
            continue
        p = now
        if -sum(x * s for x, (_, s) in zip(p, legs)) - credit >= credit:
            why = "stop (loss = credit)"; break
    p = [a or b for a, b in zip(px(), p)]
    fill1 = [max(x * (1 - ob.SLIP_PCT * s) - ob.SLIP_ABS * s, 0.05) for x, (_, s) in zip(p, legs)]
    debit = -sum(f * s for f, (_, s) in zip(fill1, legs))
    gross = (credit - debit) * q
    buy_val = sum(f for f, (_, s) in zip(fill0, legs) if s > 0) * q + sum(f for f, (_, s) in zip(fill1, legs) if s < 0) * q
    sell_val = sum(f for f, (_, s) in zip(fill0, legs) if s < 0) * q + sum(f for f, (_, s) in zip(fill1, legs) if s > 0) * q
    net = gross - ob.cost(buy_val, sell_val, sp["exch"]) - 6 * 20 * 1.18      # 8 orders; cost() counts 2
    book("FLY", dict(day=date.today(), idx=idx, option=f"{idx} {K} iron fly +-{w}", qty=q, t_in=t0.strftime("%H:%M"),
                     t_out=datetime.now().strftime("%H:%M"), buy=round(credit, 2), sell=round(debit, 2),
                     gross=round(gross, 2), net=round(net, 2), exit=why))
    trader.alert(f"OPTIONS FLY {idx} {K}: NET {net:+.0f} (credit {credit:.1f} -> {debit:.1f}, {why}) equity {equity('FLY'):.0f}")


def main():
    if not trader.market_day():
        return
    idx, exp, m = todays_expiry_index()
    if not idx:
        return trader.log("options paper: not an expiry day")
    api = angel.login()
    while datetime.now().time() < T(9, 31):
        time.sleep(20)
    while len(b := bars(api, idx)) < 3:
        time.sleep(30)
    hi, lo = max(x[2] for x in b[:3]), min(x[3] for x in b[:3])
    seen = 3 if datetime.now().time() < T(9, 36) else len(b) - 1   # late start: don't act on stale bars
    trader.log(f"options paper {idx} {exp}: range {lo}-{hi}, equity BOT {equity('BOT'):.0f} BRAIN {equity('BRAIN'):.0f}")
    bot = threading.Thread(target=trade_loop, args=("BOT", (1, -1), api, idx, exp, m, hi, lo, seen))
    bot.start()
    fdec, fwhy = flow_signal(idx, ob.SPEC[idx]["step"])
    trader.log(f"options FLOW decision {fdec}: {fwhy}")
    flow = threading.Thread(target=trade_loop, args=("FLOW", ALLOW[fdec], api, idx, exp, m, hi, lo, seen))
    flow.start()
    fly = threading.Thread(target=fly_loop, args=(api, idx, exp, m))
    fly.start()
    dec, why = brain_decision(packet(api, idx, b, hi, lo) + f"\nOption order flow at 09:30: {fwhy}")
    trader.log(f"options BRAIN decision {dec}: {why}")
    trader.alert(f"OPTIONS BRAIN {idx}: {dec} - {why}"[:180])
    # brain trades only bars after its decision: it can't take a breakout that happened while it was thinking
    trade_loop("BRAIN", ALLOW[dec], api, idx, exp, m, hi, lo, len(bars(api, idx)) - 1)
    bot.join()
    flow.join()
    fly.join()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["selftest"]:
        assert parse_decision('blah\n{"decision": "PUTS_ONLY", "why": "x"}') == ("PUTS_ONLY", "x")
        try:
            parse_decision('{"decision": "BUY"}'); raise SystemExit("bad decision accepted")
        except ValueError:
            pass
        assert ALLOW["SKIP"] == () and ALLOW["TRADE"] == (1, -1)
        print("selftest ok"); sys.exit()
    try:
        main()
    except Exception as e:   # never die silently (2026-11-09 crash went unnoticed)
        trader.alert(f"OPTIONS PAPER CRASHED: {str(e)[:150]}")
        raise
