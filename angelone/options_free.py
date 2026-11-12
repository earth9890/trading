"""FREE paper options trader (PAPER only, NEVER places orders). User's ask 2026-11-11: no NIFTY/SENSEX restriction -
the brain may buy calls/puts on ANY F&O stock (NFO) or NIFTY/BANKNIFTY/SENSEX/BANKEX, any listed strike/expiry,
every market day, positions carried overnight. Fake Rs 30k, real live prices, full costs (options_bt.cost + slippage).

  python options_free.py          # launchd 09:20 weekdays
  python options_free.py status   # cash, open positions, NET so far

Brain (headless opus + WebSearch) runs at SLOTS with a market packet (index moves, top F&O movers, open positions) and
replies {"actions":[BUY/SELL...]}. Between slots this loop marks positions every 2 min and exits on the brain's
stop/target, or at 15:15 on the contract's expiry day. Buy-only (option selling needs margin the Rs 30k doesn't have).
State: state_options_free.json   Journal: journal_options_free.csv
"""
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, time as T
from pathlib import Path

import angel
import options_bt as ob
import trader  # only log / alert / market_day
from options_recorder import market

HERE = Path(__file__).parent
STATE, JOURNAL = HERE / "state_options_free.json", HERE / "journal_options_free.csv"
CAPITAL = 30_000
SLOTS = ["09:40", "11:00", "12:30", "14:00", "15:00"]
SLIP_ABS, SLIP_PCT = 0.10, 0.01   # per side; stock-option spreads are ~1-2 ticks (0.05), wider when illiquid
EXCH_RATE = {"NFO": 0.0003503, "BFO": 0.000325}
IDX = {"NIFTY": ("NSE", "99926000"), "BANKNIFTY": ("NSE", "99926009"),
       "SENSEX": ("BSE", "99919000"), "BANKEX": ("BSE", "99919012")}


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"cash": CAPITAL, "pos": {}, "slots": {}}


def save(s):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(STATE)


def contracts(m):
    """Tradable options: NFO stock options + the 4 indices. Returns (options, {stock: NSE token})."""
    opts = [x for x in m if (x.get("instrumenttype") == "OPTSTK" and x["exch_seg"] == "NFO")
            or (x.get("instrumenttype") == "OPTIDX" and x["name"] in IDX and x["exch_seg"] in EXCH_RATE)]
    names = {x["name"] for x in opts}
    eq = {x["name"]: x["token"] for x in m if x["exch_seg"] == "NSE" and x["symbol"] == x["name"] + "-EQ" and x["name"] in names}
    return opts, eq


def exp_date(x):
    return datetime.strptime(x["expiry"], "%d%b%Y").date()


def tdays_left(expiry):
    """Market days after today up to and including expiry ('24NOV2026')."""
    e = datetime.strptime(expiry, "%d%b%Y").date()
    if (e - date.today()).days > 20:   # far away: exact count not needed (and holiday calendar may not reach it)
        return 99
    return sum(trader.market_day(date.fromordinal(d)) for d in range(date.today().toordinal() + 1, e.toordinal() + 1))


STOCK_EXIT_DAYS = 3   # stock options are physically settled; Angel margin on long ITM ramps up from expiry-4 (docs/fo_stocks_research.md)


def quotes(api, exch, toks):
    out = {}
    for i in range(0, len(toks), 50):
        out.update({r["symbolToken"]: r for r in market(api, exch, toks[i:i + 50])})
        time.sleep(1)
    return out


def chg(r):
    c = float(r.get("close") or 0)
    return (float(r["ltp"]) / c - 1) * 100 if c else 0.0


def mark(api, s):
    """Live LTP of each open option {symbol: ltp}."""
    out = {}
    for ex in EXCH_RATE:
        mine = {p["token"]: sym for sym, p in s["pos"].items() if p["exch"] == ex}
        for tok, r in quotes(api, ex, list(mine)).items():
            out[mine[tok]] = float(r["ltp"])
    return out


def equity(s, px):
    return s["cash"] + sum(px.get(k, p["buy"]) * p["qty"] for k, p in s["pos"].items())


def packet(api, s, eq, opts):
    px = mark(api, s)
    lines = [f"NOW {datetime.now():%F %H:%M} IST ({date.today():%A}). Fake cash Rs {s['cash']:.0f}, "
             f"equity Rs {equity(s, px):.0f} (started Rs {CAPITAL}).", "", "INDICES (spot, % vs prev close):"]
    spot = {}
    for name, (ex, tok) in IDX.items():
        r = quotes(api, ex, [tok]).get(tok)
        if r:
            spot[name] = float(r["ltp"])
            lines.append(f"  {name} {r['ltp']} ({chg(r):+.2f}%)")
    st = [(n, r) for n, r in ((n, quotes_cache.get(t)) for n, t in eq.items()) if r]
    st.sort(key=lambda x: chg(x[1]))
    fmt = lambda n, r: f"  {n} {r['ltp']} ({chg(r):+.2f}%) vol {r.get('tradeVolume')}"
    lines += ["", f"TOP F&O GAINERS (of {len(st)} stocks):"] + [fmt(n, r) for n, r in st[::-1][:15]]
    lines += ["", "TOP F&O LOSERS:"] + [fmt(n, r) for n, r in st[:15]]
    spot.update({n: float(r["ltp"]) for n, r in st[:6] + st[-6:]})
    lines += ["", "1-LOT COST of the ATM option (live premium x lot; risk = cost x |stop|, so pick 'risk' >= 1-lot risk or a"
              " cheaper OTM strike):"] + lot_costs(api, opts, spot)
    lines += ["", "OPEN POSITIONS:"] + ([
        f"  {k} qty {p['qty']} buy {p['buy']} now {px.get(k, '?')} stop {p['stop']} target {p['target']} "
        f"expiry {p['expiry']} why: {p['why']}" for k, p in s["pos"].items()] or ["  none"])
    nearest = sorted({x["expiry"] for x in opts if x["name"] in ("NIFTY", "SENSEX", "IRFC") and exp_date(x) >= date.today()},
                     key=lambda e: datetime.strptime(e, "%d%b%Y"))[:4]
    lines += ["", f"Upcoming expiries (format for the reply): {', '.join(nearest)}"]
    return "\n".join(lines)


quotes_cache = {}


def lot_costs(api, opts, spot):
    """ATM CE+PE premium, lot and 1-lot cost for each name in spot (indices + top movers)."""
    legs = [o for n, S in spot.items() for typ in ("CE", "PE") if (o := pick(opts, dict(name=n, type=typ, strike=S)))]
    q = {}
    for ex in EXCH_RATE:
        q.update(quotes(api, ex, [o["token"] for o in legs if o["exch_seg"] == ex]))
    out = []
    for o in legs:
        r = q.get(o["token"])
        if r and float(r["ltp"]) > 0:
            c = float(r["ltp"]) * int(o["lotsize"])
            out.append(f"  {o['symbol']} premium {r['ltp']} x lot {o['lotsize']} = Rs {c:,.0f} (risk at -40%: Rs {0.4 * c:,.0f})")
    return out


def brain(pkt):
    prompt = f"""You are a discretionary options trader running a PAPER account (fake money, no real orders). You have a free hand:
buy CALLS or PUTS on ANY NSE F&O stock (e.g. IRFC, ADANIPOWER, TATAPOWER, BHEL...) or NIFTY / BANKNIFTY / SENSEX / BANKEX,
any listed strike and expiry. Buy-only (no option writing). The goal is profit after costs (~Rs 60-80 per round trip + slippage).

{pkt}

What 2.4 years of real NSE data says (docs/strategy_results.md "F&O stock options", docs/fo_stocks_research.md):
no mechanical stock-option buying rule beat RANDOM entries in both halves; random call buying lost ~Rs 1.3k/trade; breakout and
long-buildup calls were WORSE than random; puts on >4% losers lost badly. Only short-buildup puts (price -2%, OI +5%, vol 1.5x)
and the cheapest small calls on >4% gainers were positive, and both failed the random test. So every buy is a discretionary
bet that needs a real catalyst you can name; SKIP is the default. Hard rules: never buy a stock in today's F&O ban list
(WebSearch "NSE F&O ban list today"); stock options need >=10 trading days to expiry at entry (the bot exits them 3 trading
days before expiry, physical settlement); prefer liquid large caps and ATM/1 strike ITM (mid-cap OTM spreads eat the edge);
no new position 1-3 sessions before the stock's results unless that is the trade; skip the first 15 min after news spikes;
target must be >3x costs; max 3 open, 1 per sector.
Think like a pro: news/catalysts (use WebSearch), momentum, volume, where the move can run. Cheap OTM options can 10x but most
go to zero. Lots are big: 1 lot of a near-ATM index or stock option often costs Rs 8,000-30,000. Size by RISK: "risk" = Rupees
you accept losing if the stop hits (typically Rs 1,500-4,000 per idea); the bot buys floor(risk / (premium x lot x |stop|)) lots,
max 50% of the account premium per position. You may also SELL open
positions, or do nothing. Each BUY needs a stop and a target as fractions of premium (stop -0.4 = exit at -40%, target 2.0 =
exit at +200%). Be quick (under 5 minutes).

Reply with ONLY one JSON line:
{{"actions": [{{"do": "BUY", "name": "IRFC", "type": "CE", "strike": 82, "expiry": "25NOV2026", "risk": 3000, "stop": -0.4, "target": 2.0, "why": "..."}},
              {{"do": "SELL", "symbol": "<open position symbol>", "why": "..."}}], "view": "<one sentence>"}}"""
    r = subprocess.run(["/Users/harish/.local/bin/claude", "-p", prompt, "--model", "opus",
                        "--permission-mode", "dontAsk", "--allowedTools", "WebSearch"],
                       capture_output=True, text=True, timeout=480, cwd=HERE, stdin=subprocess.DEVNULL)
    return json.loads(re.search(r"\{\s*\"actions\".*\}", r.stdout, re.S).group())


def pick(opts, a):
    """Listed contract closest to the brain's request (exact expiry if listed, else nearest future; nearest strike)."""
    c = [x for x in opts if x["name"] == a["name"].upper() and x["symbol"].endswith(a["type"].upper())
         and exp_date(x) >= date.today()]
    if a["name"].upper() not in IDX:   # stock: skip months we'd have to dump within days
        c = [x for x in c if tdays_left(x["expiry"]) > STOCK_EXIT_DAYS + 2]
    if not c:
        return None
    want = a.get("expiry", "").upper()
    e = want if any(x["expiry"] == want for x in c) else min(c, key=exp_date)["expiry"]
    c = [x for x in c if x["expiry"] == e]
    return min(c, key=lambda x: abs(float(x["strike"]) / 100 - float(a["strike"])))


def buy(api, s, opts, a):
    o = pick(opts, a)
    if not o:
        return trader.log(f"options FREE: no contract for {a}")
    if o["symbol"] in s["pos"]:
        return trader.log(f"options FREE: already hold {o['symbol']}")
    q = quotes(api, o["exch_seg"], [o["token"]]).get(o["token"])
    if not q or float(q["ltp"]) <= 0:
        return trader.log(f"options FREE: no price for {o['symbol']}")
    px = float(q["ltp"]) * (1 + SLIP_PCT) + SLIP_ABS
    lot = int(o["lotsize"])
    stop = abs(float(a.get("stop", -0.4))) or 0.4
    risk = float(a.get("risk", a.get("rupees", 3000)))
    # 10% slack: the brain sizes off the pre-slippage quote
    lots = min(int(risk * 1.1 // (px * lot * stop)), int(min(s["cash"], 0.5 * CAPITAL) // (px * lot)))
    if lots < 1:
        return trader.log(f"options FREE: 1 lot of {o['symbol']} = Rs {px * lot:.0f} (risk {px * lot * stop:.0f} at stop) "
                          f"> risk {risk:.0f} / 50% cap / cash - skip")
    qty = lots * lot
    s["cash"] -= px * qty
    s["pos"][o["symbol"]] = dict(token=o["token"], exch=o["exch_seg"], expiry=o["expiry"], qty=qty, buy=round(px, 2),
                                 t_in=f"{datetime.now():%F %H:%M}", stop=float(a.get("stop", -0.4)),
                                 target=float(a.get("target", 2.0)), why=str(a.get("why", ""))[:200])
    trader.log(f"options FREE PAPER BUY {o['symbol']} x{qty} @ {px:.2f} = Rs {px * qty:.0f}: {a.get('why', '')}")


def sell(s, sym, ltp, why):
    p = s["pos"].pop(sym)
    px = max(ltp * (1 - SLIP_PCT) - SLIP_ABS, 0.05)
    bv, sv = p["buy"] * p["qty"], px * p["qty"]
    c = ob.cost(bv, sv, EXCH_RATE[p["exch"]])
    net = sv - bv - c
    s["cash"] += sv - c
    row = dict(t_in=p["t_in"], t_out=f"{datetime.now():%F %H:%M}", option=sym, qty=p["qty"], buy=p["buy"],
               sell=round(px, 2), gross=round(sv - bv, 2), net=round(net, 2), exit=why, idea=p["why"])
    new = not JOURNAL.exists()
    with JOURNAL.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    trader.alert(f"OPTIONS FREE {sym}: NET {net:+.0f} (gross {sv - bv:+.0f}, {why}) cash {s['cash']:.0f}")


def check_exits(api, s):
    px, now = mark(api, s), datetime.now()
    for sym, p in list(s["pos"].items()):
        ltp = px.get(sym)
        if ltp is None:
            continue
        r = ltp / p["buy"] - 1
        if r <= p["stop"]:
            sell(s, sym, ltp, f"stop {r:+.0%}")
        elif r >= p["target"]:
            sell(s, sym, ltp, f"target {r:+.0%}")
        elif datetime.strptime(p["expiry"], "%d%b%Y").date() <= now.date() and now.time() >= T(15, 15):
            sell(s, sym, ltp, "expiry day 15:15")
        elif not any(sym.startswith(i) for i in IDX) and tdays_left(p["expiry"]) <= STOCK_EXIT_DAYS:
            sell(s, sym, ltp, f"stock option {STOCK_EXIT_DAYS} days before expiry (physical settlement)")
    return px


def run_slot(api, s, opts, eq):
    quotes_cache.clear()
    quotes_cache.update(quotes(api, "NSE", list(eq.values())))
    try:
        d = brain(packet(api, s, eq, opts))
    except Exception as e:
        return trader.alert(f"OPTIONS FREE brain failed ({str(e)[:100]}) - no new trades this slot")
    trader.log(f"options FREE brain view: {d.get('view', '')}")
    px = mark(api, s)
    for a in d.get("actions", []):
        try:
            if a.get("do") == "BUY":
                buy(api, s, opts, a)
            elif a.get("do") == "SELL" and a.get("symbol") in s["pos"]:
                sell(s, a["symbol"], px.get(a["symbol"], s["pos"][a["symbol"]]["buy"]), "brain: " + str(a.get("why", ""))[:80])
        except Exception as e:
            trader.log(f"options FREE action failed {a}: {str(e)[:120]}")
        save(s)


def status():
    s = load()
    net = sum(float(r["net"]) for r in csv.DictReader(JOURNAL.open())) if JOURNAL.exists() else 0
    print(f"cash Rs {s['cash']:.0f}  closed NET {net:+.0f}  open: {len(s['pos'])}")
    for k, p in s["pos"].items():
        print(f"  {k} x{p['qty']} @ {p['buy']}  stop {p['stop']:+.0%} target {p['target']:+.0%}  {p['why'][:80]}")


def main():
    if sys.argv[1:] == ["status"]:
        return status()
    if not trader.market_day():
        return
    m = json.loads((HERE / "data/scripmaster.json").read_text())
    opts, eq = contracts(m)
    api, s = angel.login(), load()
    today = str(date.today())
    s["slots"] = {today: s.get("slots", {}).get(today, [])}
    while datetime.now().time() < T(15, 25):
        due = [x for x in SLOTS if x <= f"{datetime.now():%H:%M}" and x not in s["slots"][today]]
        if due:
            s["slots"][today] += due        # missed slots collapse into one brain run
            run_slot(api, s, opts, eq)
        elif s["pos"]:
            check_exits(api, s)
        save(s)
        time.sleep(120)
    px = check_exits(api, s)
    save(s)
    trader.alert(f"OPTIONS FREE day end: cash {s['cash']:.0f}, equity {equity(s, px):.0f} (start {CAPITAL}), "
                 f"{len(s['pos'])} open")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        trader.alert(f"OPTIONS FREE CRASHED: {str(e)[:150]}")
        raise
