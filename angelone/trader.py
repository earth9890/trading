"""Swing trading bot for Angel One. PAPER mode by default; --live sends real orders.

  python trader.py scan    [--live]   # after ~15:20: decide exits + tomorrow's buys (all executed by `enter`)
  python trader.py enter   [--live]   # 09:20+: queued sells, then buys + GTT stop-loss for each fill
  python trader.py check   [--live]   # any time: reconcile with broker, ensure EVERY position has a stop
  python trader.py status  [--live]
  brain (discretionary, same rails):
  python trader.py buy SYM RUPEES STOP_PRICE why...   # stop required, <=15% away, risk <=8% equity, max 5/day
  python trader.py sell SYM why...
  python trader.py setstop SYM PRICE                  # ratchet up only, never above 80% of highest close
  python trader.py veto SYM why...                    # drop a queued buy
  python trader.py adjust SYM RATIO                   # split/bonus before ex-date: qty x RATIO, prices / RATIO

Invariants (the reason this file exists):
  1. No position without a stop. Stop can't be placed -> exit (market hours) or alert.
  2. Bot capital is tracked in state (BOT_CAPITAL), isolated from the user's own cash/holdings.
  3. Never trade a symbol the user holds manually; size stops/sells from bot qty, never broker qty.
  4. Kill switch: equity < peak x (1 - MAX_DD) -> no new buys, stops stay. Daily loss > DAILY_LOSS -> no buys today.
  5. Orders are LIMIT (algo MARKET banned since Apr 2026), tagged, never blindly re-sent, always cancelled if unfilled.
"""
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import angel
import backtest
import fetch

HERE = Path(__file__).parent
LIVE = "--live" in sys.argv
STATE_FILE = HERE / ("state_live.json" if LIVE else "state_paper.json")
JOURNAL = HERE / ("journal_live.csv" if LIVE else "journal_paper.csv")
LOG = HERE / "trader.log"
BRAIN_MARK = HERE / ".brain_preopen_done"

# ---- strategy + risk config (change here, nowhere else) ----
BOT_CAPITAL = 10000    # bot only ever uses this much (+ its own P&L), whatever else is in the account
RISK = 0.02            # donchian: 2% of equity risked per trade
MAX_POS = 5              # user 2026-11-11; funds gate: spendable cash + MIN_POSITION Rs 1500
MAX_POS_PCT = 0.60     # one position <= 60% of equity
MIN_POSITION = 1500    # Rs; below this the Rs 23.6 DP charge eats the edge
MAX_DD = 0.20          # kill switch at -20% from peak equity
DAILY_LOSS = 0.03      # no new buys after -3% day
STRATEGY = "brain"     # "brain" or "donchian". Monthly rotation removed 2026-11-11 (user's order).
# brain: no rule buys; brain buys dips in top-10 momentum + watchlist.txt, -5% stop, auto take-profit at +5% NET
# (watcher -> `trader.py tp`). Backtest of quick-profit rules lost money (docs/strategy_results.md) - user chose it anyway.
USER_STOP = 0.05       # ./t buy: auto stop 5% below entry
TAKE_PROFIT = 0.05     # brain mode: sell when NET pnl >= 5% of cost
ENTRY_N, EXIT_N, STOP_ATR, VOL_MIN = 55, 20, 2.0, 1.5   # donchian: 55/20, 2xATR stop
MAX_GAP = 0.03         # donchian only: skip buy if open >3% above signal close
LIMIT_SLIP = 0.005     # buy limit = LTP +0.5%, sell limit = LTP -0.5%
STOP_BUFFER = 0.02     # stop-loss limit 2% below trigger so gaps still fill
MAX_STOP_PCT = 0.15    # brain: stop no further than 15% below LTP
MAX_TRADE_RISK = 0.08  # brain: (entry - stop) x qty <= 8% of equity
BRAIN_MAX_TRADES = 5   # brain buys+sells per day (user 2026-11-11)
SETSTOP_FLOOR = 0.80   # brain: stop never above 80% of the position's highest close
# NSE weekday holidays (docs/edge_cases.md). ponytail: refresh from NSE circular every December.
HOLIDAYS = {"2026-11-10", "2026-11-24", "2026-12-25"}
PROTECTED = {"JPL"}     # user order 2026-11-04: bot must NEVER buy/sell/GTT these (checked at the broker call itself)
CALENDAR_UNTIL = date(2026, 12, 31)   # fail closed after this
# GTT status strings per SDK docs (UNVERIFIED live: live_test dumps raw gttDetails to confirm)
GTT_ACTIVE = {"NEW", "ACTIVE"}
GTT_TRIGGERED = {"SENTTOEXCHANGE", "TRIGGERED", "EXECUTED", "COMPLETED"}
GTT_DEAD = {"CANCELLED", "EXPIRED", "DELETED", "REJECTED"}


def log(*a):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {'LIVE' if LIVE else 'PAPER'} " + " ".join(map(str, a))
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def alert(msg):
    log("ALERT", msg)
    # list args, no shell; message passed as argv so quotes/symbols can't inject
    subprocess.run(["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Trader"',
                    "-e", "end run", msg[:180]], capture_output=True)


# ---- state (atomic write, so a crash mid-write can't corrupt it) ----
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return dict(positions={}, queue_buy=[], queue_sell=[], peak=None, day=None, day_start=None,
                cash=BOT_CAPITAL, rebalanced="", brain_trades={})


def save_state(s):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, default=str))
    tmp.replace(STATE_FILE)


def journal(**row):
    new = not JOURNAL.exists()
    pd.DataFrame([row]).to_csv(JOURNAL, mode="a", header=new, index=False)


# ---- broker wrapper ----
class Fatal(Exception):
    pass


RETRY_TEXT = ("exceeding access rate", "timed out", "timeout", "connection", "temporarily", "try after", "try later",
              "502", "503", "504")
RETRY_CODES = ("AB1004", "AB1019", "AB2001")  # AB2001 "Internal Error" seen live 2026-11-05          # "something went wrong / try later" [docs/angel_api.md]
TOKEN_CODES = ("AG8001", "AG8002", "AG8003")
DONE = ("complete", "rejected", "cancelled")


class Broker:
    def __init__(self):
        self.api = self._login()
        self.ip_ok = not LIVE or self._ip_check()
        master = json.loads((HERE / "data/scripmaster.json").read_text())
        self.inst = {x["symbol"][:-3]: x for x in master if x["exch_seg"] == "NSE" and x["symbol"].endswith("-EQ")}

    @staticmethod
    def _login(force=False):
        try:
            return angel.login(force)
        except SystemExit as e:  # angel.login exits on failure; never let that skip alerts/cleanup
            raise Fatal(f"login failed: {e}")

    @staticmethod
    def _ip_check():
        """Angel only accepts orders from the registered static IPv4. Jio home IPs change -> catch it early."""
        import requests
        want = angel.env().get("ANGEL_STATIC_IP", "")
        try:
            have = requests.get("https://api.ipify.org", timeout=8).text.strip()  # IPv4 forced in angel.py
        except Exception as e:
            log("ip check failed:", e)
            return True  # can't tell: let the order try (broker rejects if wrong)
        if have != want:
            alert(f"PUBLIC IP CHANGED: {have} != registered {want}. Orders will be rejected - update IP in Angel/Kite consoles + .env")
            return False
        return True

    def call(self, fn, *a, tries=6):
        """Read-only/idempotent calls only. Backoff + jitter on transient errors; relogin on token errors."""
        for i in range(tries):
            wait = min(30, 1.5 * 2 ** i) + random.random()
            try:
                r = getattr(self.api, fn)(*a)
            except Exception as e:
                msg = str(e).lower()
                if ("token" in msg or "unauthor" in msg) and i < 2:
                    time.sleep(1.5)
                    self.api = self._login(force=True)
                    continue
                if not any(t in msg for t in RETRY_TEXT) or i == tries - 1:
                    raise
                time.sleep(wait)
                continue
            if isinstance(r, dict) and (r.get("status") is False or r.get("success") is False):
                code, msg = r.get("errorcode") or r.get("errorCode"), str(r.get("message"))  # API uses both spellings
                if code in TOKEN_CODES and i < 2:
                    time.sleep(1.5)
                    self.api = self._login(force=True)
                    continue
                if (code in RETRY_CODES or any(t in msg.lower() for t in RETRY_TEXT)) and i < tries - 1:
                    time.sleep(wait)
                    continue
                raise Fatal(f"{fn}: {code} {msg}")
            time.sleep(1.05)  # holdings/orderbook/search are 1 req/s
            return r
        raise Fatal(f"{fn}: gave up after {tries} tries")

    def tick(self, sym):
        return float(self.inst[sym]["tick_size"]) / 100  # scrip master tick is in paise

    def round_tick(self, sym, px, up):
        t = self.tick(sym)
        return round((math.ceil if up else math.floor)(px / t - 1e-9) * t, 2)

    def ltp(self, sym):
        i = self.inst[sym]
        return float(self.call("ltpData", "NSE", i["symbol"], i["token"])["data"]["ltp"])

    def funds(self):
        """Cash the broker lets us spend now ('net' can include collateral)."""
        return float(self.call("rmsLimit")["data"]["availablecash"])

    def holdings(self):
        """sym -> qty held. Angel's holdings already include today's DELIVERY buys/sells (live test 2026-11-04:
        4 -> 5 right after a 1-share buy, back to 4 after the sell), so positions must NOT be added again."""
        out = {}
        for h in self.call("holding").get("data") or []:
            if h["tradingsymbol"].endswith("-EQ"):
                # quantity is the total; t1quantity is a SUBSET of it (seen live 2026-11-05: quantity 17, t1quantity 17)
                out[h["tradingsymbol"][:-3]] = int(h["quantity"])
        return {k: v for k, v in out.items() if v > 0}

    def orders(self):
        return self.call("orderBook").get("data") or []

    def find_order(self, tag, oid=None):
        """Match by orderid (from response) or by our ordertag (recovery after network error)."""
        for o in self.orders():
            if (oid and o.get("orderid") == oid) or o.get("ordertag") == tag:
                return o
        return None

    @staticmethod
    def status(o):
        return (o.get("orderstatus") or o.get("status") or "").lower()

    def cancel_open_orders(self, sym, side="SELL"):
        """Cancel open orders on sym (e.g. a GTT-triggered stop limit that never filled)."""
        ts = self.inst[sym]["symbol"]
        for o in self.orders():
            if o.get("tradingsymbol") == ts and o.get("transactiontype") == side and self.status(o) not in DONE:
                try:
                    self.api.cancelOrder(o["orderid"], o.get("variety") or "NORMAL")
                    log("cancelled stale", side, sym, o["orderid"])
                except Exception as e:
                    log("cancel stale failed:", e)

    def limit_order(self, side, sym, qty, price, wait=90):
        """LIMIT DELIVERY order -> wait for fill -> always cancel leftover. Returns (filled_qty, avg_price).
        Raises Fatal if the final state can't be confirmed (caller then checks holdings)."""
        if sym in PROTECTED:
            raise Fatal(f"{sym} is PROTECTED (user's own stock) - bot never orders it")
        if not self.ip_ok:
            raise Fatal("public IP != registered static IP - order would be rejected")
        i, tag = self.inst[sym], f"bot{uuid.uuid4().hex[:10]}"
        params = dict(variety="NORMAL", tradingsymbol=i["symbol"], symboltoken=i["token"], transactiontype=side,
                      exchange="NSE", ordertype="LIMIT", producttype="DELIVERY", duration="DAY",
                      price=str(price), quantity=str(qty), ordertag=tag)
        log("ORDER", side, sym, qty, "@", price, tag)
        try:
            r = self.api.placeOrderFullResponse(dict(params))
        except Exception as e:  # network died mid-request: did it reach the exchange? look it up, never re-send blind
            log("place error, checking by tag:", e)
            time.sleep(3)
            r = None
        oid = ((r or {}).get("data") or {}).get("orderid")
        o = self.find_order(tag, oid)
        if not o:
            raise Fatal(f"order not found: {r and r.get('message')} {r and r.get('errorcode')}")
        oid, st, end = o["orderid"], "", time.time() + wait
        try:
            while time.time() < end:
                try:
                    o = self.find_order(tag, oid) or o
                except Exception as e:
                    log("poll error:", e)
                st = self.status(o)
                if st in DONE:
                    break
                time.sleep(3)
        finally:
            if st not in DONE:
                try:
                    self.api.cancelOrder(oid, "NORMAL")
                except Exception as e:
                    log("cancel failed (re-reading):", e)
        for _ in range(10):  # cancel is async: wait for a terminal state before trusting filledshares
            if st in DONE:
                break
            time.sleep(3)
            o = self.find_order(tag, oid) or o
            st = self.status(o)
        if st not in DONE:
            raise Fatal(f"{sym} order {oid} stuck in '{st}' after cancel")
        if st == "rejected":
            log("REJECTED", sym, o.get("text"))
        return int(float(o.get("filledshares") or 0)), float(o.get("averageprice") or price)

    def find_gtt(self, sym, qty):
        """Active GTT SELL on sym for qty, if one exists (dedupe after an ambiguous create)."""
        try:
            rules = self.call("gttLists", ["NEW", "ACTIVE"], 1, 50).get("data") or []
        except Exception as e:
            log("gttLists failed:", e)
            return None
        for r in rules:
            if r.get("tradingsymbol") == self.inst[sym]["symbol"] and str(r.get("transactiontype")).upper() == "SELL" \
                    and int(float(r.get("qty") or 0)) == qty and str(r.get("status", "NEW")).upper() in GTT_ACTIVE:
                return str(r.get("id"))
        return None

    def place_stop(self, sym, qty, trigger):
        """GTT stop-loss sell (lives across days). Retries; adopts an existing identical rule instead of duplicating."""
        if sym in PROTECTED:
            raise Fatal(f"{sym} is PROTECTED (user's own stock) - bot never places GTT on it")
        if not getattr(self, "ip_ok", True):
            raise Fatal("public IP != registered static IP - GTT would be rejected")
        i = self.inst[sym]
        trig = self.round_tick(sym, trigger, up=False)
        price = self.round_tick(sym, trigger * (1 - STOP_BUFFER), up=False)
        params = dict(tradingsymbol=i["symbol"], symboltoken=i["token"], exchange="NSE", producttype="DELIVERY",
                      transactiontype="SELL", price=str(price), qty=str(qty), disclosedqty=str(qty),
                      triggerprice=str(trig), timeperiod=365)
        for attempt in range(3):
            try:
                rid = self.api.gttCreateRule(dict(params))  # SDK raises (TypeError) on a failed response
                log("STOP placed", sym, qty, "trigger", trig, "limit", price, "gtt", rid)
                return str(rid)
            except Exception as e:
                log(f"gtt create failed ({attempt + 1}/3):", e)
                time.sleep(2 * (attempt + 1))
                existing = self.find_gtt(sym, qty)
                if existing:
                    log("adopted existing gtt", existing)
                    return existing
        raise Fatal(f"{sym}: GTT stop could not be placed")

    def stop_state(self, rid):
        """'active' | 'triggered' | 'dead' | 'unknown' (API error / unrecognised status: don't act on it)."""
        if not rid:
            return "dead"
        try:
            d = self.call("gttDetails", rid).get("data") or {}
        except Exception as e:
            log("gttDetails failed:", e)
            return "unknown"
        st = str(d.get("status", "")).upper()
        if st in GTT_ACTIVE:
            return "active"
        if st in GTT_TRIGGERED:
            return "triggered"
        if st in GTT_DEAD:
            return "dead"
        log("unrecognised GTT status", repr(st), "- treating as unknown")
        return "unknown"

    def cancel_stop(self, sym, rid):
        """True if cancelled (or nothing to cancel). SDK returns {'status': False} instead of raising."""
        if not rid:
            return True
        i = self.inst[sym]
        try:
            r = self.api.gttCancelRule(dict(id=rid, symboltoken=i["token"], exchange="NSE"))
        except Exception as e:
            log("gtt cancel error:", e)
            return False
        if isinstance(r, dict) and (r.get("status") is False or r.get("success") is False):
            log("gtt cancel refused:", r.get("errorcode") or r.get("errorCode"), r.get("message"))
            return False
        return True

    def day_bar(self, sym):
        """Today's (open, low) or None."""
        df = fetch.fetch(self.api, self.inst[sym]["token"], "day", 5)
        if len(df) and df["time"].iloc[-1].date() == date.today():
            return float(df["open"].iloc[-1]), float(df["low"].iloc[-1])
        return None


class PaperBroker(Broker):
    """Real prices from Angel, simulated fills. GTT emulated in paper_stops() with today's candle low."""

    def __init__(self, state):
        super().__init__()
        self.s = state

    def funds(self):
        return self.s["cash"]

    def holdings(self):
        return {k: p["qty"] for k, p in self.s["positions"].items()}

    def limit_order(self, side, sym, qty, price, wait=90):
        ltp = self.ltp(sym)
        if (side == "BUY" and ltp > price) or (side == "SELL" and ltp < price):
            log("PAPER no fill", side, sym, "ltp", ltp, "limit", price)
            return 0, price
        log("PAPER fill", side, sym, qty, "@", ltp)
        return qty, ltp

    def place_stop(self, sym, qty, trigger):
        rid = f"paper-{uuid.uuid4().hex[:6]}"
        log("PAPER stop", sym, qty, "trigger", round(trigger, 2), rid)
        return rid

    def stop_state(self, rid):
        return "active" if rid else "dead"

    def cancel_stop(self, sym, rid):
        return True

    def cancel_open_orders(self, sym, side="SELL"):
        pass

    def find_gtt(self, sym, qty):
        return None


# ---- market calendar ----
def market_day(d=None):
    d = d or date.today()
    if d > CALENDAR_UNTIL:
        raise Fatal("holiday calendar expired: update HOLIDAYS from NSE circular")
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def market_open():
    n = datetime.now()
    return market_day() and (9, 15) <= (n.hour, n.minute) < (15, 30)


# ---- core ----
def equity(b, s):
    """Bot cash (tracked in state) + bot positions. User's own cash/holdings never count."""
    return s["cash"] + sum(p["qty"] * b.ltp(k) for k, p in s["positions"].items())


def spendable(b, s):
    return min(s["cash"], b.funds()) * 0.97


def risk_gate(b, s):
    """Returns (ok_to_buy, equity). Updates peak + day start."""
    eq = equity(b, s)
    today = date.today().isoformat()
    if s.get("day") != today:
        s["day"], s["day_start"] = today, eq
    s["peak"] = max(s.get("peak") or eq, eq)
    if eq < s["peak"] * (1 - MAX_DD):
        alert(f"KILL SWITCH: equity {eq:.0f} < {1 - MAX_DD:.0%} of peak {s['peak']:.0f}. No new buys.")
        return False, eq
    if eq < s["day_start"] * (1 - DAILY_LOSS):
        log(f"daily loss limit hit ({eq:.0f} vs {s['day_start']:.0f}), no buys today")
        return False, eq
    return True, eq


def book_exit(s, sym, qty, px, reason):
    """Record a (partial) exit of bot shares: cash, journal, qty."""
    p = s["positions"][sym]
    sell_cost = backtest.costs(0, qty * px)
    s["cash"] += qty * px - sell_cost
    buy_cost = p.get("buy_cost", 0) * qty / p.get("qty0", p["qty"])
    net = round((px - p["entry"]) * qty - sell_cost - buy_cost, 2)
    journal(sym=sym, t0=p["t0"], t1=datetime.now(), entry=p["entry"], exit=round(px, 2), qty=qty, pnl=net, reason=reason)
    alert(f"CLOSED {sym} {qty} @ {px:.2f} ({reason}): NET pnl {net:+.2f} after charges "
          f"(gross {(px - p['entry']) * qty:+.2f}, charges {sell_cost + buy_cost:.2f})")
    p["qty"] -= qty
    if p["qty"] <= 0:
        del s["positions"][sym]


def protect(b, s, sym):
    """Ensure sym has a stop for the bot qty. Outside market hours never sells."""
    p = s["positions"][sym]
    try:
        p["stop_id"] = b.place_stop(sym, p["qty"], p["stop"])
    except Fatal as e:
        if market_open():
            alert(f"{sym}: cannot place stop ({e}) -> selling")
            close_position(b, s, sym, "no-stop-possible", reprotect=False)
        else:
            alert(f"{sym}: UNPROTECTED, stop failed ({e}); next market run retries or sells")
    save_state(s)


def close_position(b, s, sym, reason, reprotect=True):
    """Sell bot qty. Market closed -> queue for next open (stop stays). Unfilled rest -> re-protect + re-queue."""
    p = s["positions"][sym]
    if not market_open():
        if sym not in s["queue_sell"]:
            s["queue_sell"].append(sym)
        return log(f"market closed: queued SELL {sym} ({reason})")
    b.cancel_open_orders(sym, "SELL")  # e.g. a triggered GTT's limit order sitting unfilled
    if not b.cancel_stop(sym, p["stop_id"]) and b.stop_state(p["stop_id"]) == "active":
        alert(f"{sym}: GTT {p['stop_id']} would not cancel - not selling (avoids double sell)")
        return
    p["stop_id"] = None
    save_state(s)  # crash from here on -> reconcile sees no stop and re-protects
    before = b.holdings().get(sym, 0) if LIVE else p["qty"]
    qty = min(p["qty"], before)
    filled, px = 0, 0.0
    if qty > 0:
        try:
            filled, px = b.limit_order("SELL", sym, qty, b.round_tick(sym, b.ltp(sym) * (1 - LIMIT_SLIP), up=False))
        except Exception as e:
            filled, px = (max(0, before - b.holdings().get(sym, 0)) if LIVE else 0), b.ltp(sym)
            alert(f"{sym} sell error ({e}); filled {filled}")
            if "AB4036" in str(e):   # exchange cautionary list (ASM/GSM): Angel rejects API orders, app still works
                s.setdefault("api_blocked", {})[sym] = date.today().isoformat()
                alert(f"SELL {sym} IN THE ANGEL APP: exchange cautionary list blocks API orders today")
    if filled:
        book_exit(s, sym, filled, px, reason)
    if sym in s["positions"]:
        if sym not in s["queue_sell"]:
            s["queue_sell"].append(sym)  # retry next enter run
        alert(f"{sym}: sold {filled}, {s['positions'][sym]['qty']} left -> re-protected, queued to retry")
        if reprotect:
            protect(b, s, sym)
    elif sym in s["queue_sell"]:
        s["queue_sell"].remove(sym)
    save_state(s)


def reconcile(b, s):
    """Broker is the truth. Every bot position must be covered by one active stop for the bot qty."""
    held = b.holdings()
    for sym in list(s["positions"]):
        p = s["positions"][sym]
        have, st = held.get(sym, 0), b.stop_state(p["stop_id"])
        if have > p["qty"]:
            alert(f"{sym}: broker {have} > bot {p['qty']} (manual shares mixed in) - bot manages only its {p['qty']}")
        if have < p["qty"]:  # shares left the account: stop fill or manual sell
            gone = p["qty"] - have
            if st == "active":  # sold outside the bot / qty changed: kill the rule, re-sized below if needed
                b.cancel_stop(sym, p["stop_id"])
                st = "dead"
            book_exit(s, sym, gone, p["stop"] * (1 - STOP_BUFFER / 2), "stop/external")
            alert(f"{sym}: {gone} shares left the account (stop?) - booked")
            if sym not in s["positions"]:
                continue
        if st == "unknown":
            log(f"{sym}: stop state unknown - not touching it this run")
            continue
        if st == "active":
            continue
        if b.ltp(sym) <= p["stop"] * 1.005:  # stop triggered/missing and price already through it
            alert(f"{sym} at/below stop {p['stop']:.2f}, not protected -> exit")
            close_position(b, s, sym, "stop-gap")
            continue
        if st == "triggered":
            b.cancel_open_orders(sym, "SELL")  # its exchange order is still open: avoid a double sell
        existing = b.find_gtt(sym, p["qty"])
        if existing:
            p["stop_id"] = existing
            continue
        log("stop missing for", sym, "- re-placing")
        protect(b, s, sym)
    if LIVE:
        for sym, q in held.items():
            if sym not in s["positions"]:
                log(f"note: {sym} x{q} held but not managed by bot (manual holding) - ignored")
    save_state(s)


def paper_stops(b, s):
    """Paper only: emulate GTT with today's candle (low <= stop -> fill at min(open, stop))."""
    for sym in list(s["positions"]):
        p = s["positions"][sym]
        bar = b.day_bar(sym)
        if bar and bar[1] <= p["stop"]:
            px = min(bar[0], p["stop"])
            book_exit(s, sym, p["qty"], px, "stop")
            alert(f"PAPER stop hit {sym} @ {px:.2f}")


def signals(b, syms, strict=()):
    """Refresh daily candles + indicators. Fatal if a `strict` (held) symbol fails or >5% of the rest fail."""
    out, failed = {}, []
    for sym in syms:
        try:
            df = fetch.fetch(b.api, b.inst[sym]["token"], "day", 420)
        except Exception as e:
            log("candles failed", sym, e)
            failed.append(sym)
            continue
        df = df.set_index("time")
        df.index = df.index.tz_localize(None)
        d = backtest.indicators(df)
        d["hhN"] = d.high.rolling(ENTRY_N).max().shift()
        d["llN"] = d.low.rolling(EXIT_N).min().shift()
        out[sym] = d
    if set(failed) & set(strict) or len(failed) > 0.05 * max(1, len(syms)):
        raise Fatal(f"candle download failed for {failed} - not deciding on partial data")
    return out


def rank(b, s, data):
    """Liquid stocks by 12-1 momentum (>0), best first; user's manual holdings excluded."""
    held = set(s["positions"])
    moms, manual = {}, (set(b.holdings()) - held) if LIVE else set()
    for sym, d in data.items():
        if sym != "NIFTYBEES" and sym not in manual and len(d) > 253 and d.turnover.iloc[-1] > 20e7:
            m = d.close.iloc[-22] / d.close.iloc[-253] - 1   # 12-1 momentum: skip latest month
            if m > 0:
                moms[sym] = m
    ranked = sorted(moms, key=moms.get, reverse=True)
    log("momentum top:", {k: f"{moms[k]:.0%}" for k in ranked[:5]})
    return ranked


def watchlist():
    f = HERE / "watchlist.txt"
    return {l.strip().upper() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")} if f.exists() else set()


def net_pnl(p, ltp):
    """NET pnl if the position were sold at ltp (buy cost share + sell charges), and the cost basis."""
    gross = (ltp - p["entry"]) * p["qty"]
    return gross - p.get("buy_cost", 0) * p["qty"] / p.get("qty0", p["qty"]) - backtest.costs(0, ltp * p["qty"]), p["entry"] * p["qty"]


def cmd_scan(b, s):
    if not market_day():
        return log("market closed today, nothing to scan")
    reconcile(b, s) if LIVE else paper_stops(b, s)
    data = signals(b, ["NIFTYBEES"], strict=["NIFTYBEES"])
    if date.today() != data["NIFTYBEES"].index[-1].date():
        raise Fatal("no NIFTYBEES candle for today (holiday or data error) - scan aborted")
    nb = data["NIFTYBEES"].iloc[-1]
    held = sorted(set(s["positions"]) - {"NIFTYBEES"})
    syms = sorted((set(fetch.UNIVERSE) | set(held)) - {"NIFTYBEES"})
    data.update(signals(b, syms, strict=held))
    for sym, p in s["positions"].items():  # highest close: floor for brain setstop
        p["hi"] = max(p.get("hi", p["entry"]), float(data[sym].close.iloc[-1]))
    if STRATEGY == "brain":   # rules only refresh the brain's buy list; brain decides buys, watcher takes profit
        s["candidates"], s["queue_buy"] = rank(b, s, data)[:10], []
        return log("brain mode: candidates", s["candidates"], "+ watchlist", sorted(watchlist()))
    # donchian: exits close < 20-day low, then breakout entries
    for sym in held:
        r = data[sym].iloc[-1]
        if r.close < r.llN and sym not in s["queue_sell"]:
            s["queue_sell"].append(sym)
            log("queued SELL", sym, "exit-20d-low")
    if nb.close <= nb.sma200:
        s["queue_buy"] = []
        return log(f"regime OFF (NIFTYBEES {nb.close:.2f} <= 200DMA {nb.sma200:.2f}) - no new buys")
    ok, eq = risk_gate(b, s)
    slots = MAX_POS - len(s["positions"]) + len(s["queue_sell"])
    if not ok or slots <= 0:
        s["queue_buy"] = []
        return log("no buy slots" if ok else "risk gate closed")
    cands = []
    for sym, d in data.items():
        r = d.iloc[-1]
        if sym == "NIFTYBEES" or sym in s["positions"] or r.turnover < 20e7:
            continue
        if r.close > r.hhN and r.close > r.sma200 and r.vol_ratio >= VOL_MIN:
            cands.append(dict(sym=sym, close=float(r.close), atr=float(r.atr), mom=float(r.mom)))
    cands.sort(key=lambda c: -c["mom"])
    s["queue_buy"] = cands[:slots]
    log("signals:", [c["sym"] for c in cands], "-> queued:", [c["sym"] for c in s["queue_buy"]])


def wait_for_brain():
    """Live: give the 09:05 brain run (news vetoes) until 09:35 to finish before buying."""
    while LIVE and datetime.now().time() < datetime.strptime("09:35", "%H:%M").time():
        if BRAIN_MARK.exists() and BRAIN_MARK.read_text().strip() == date.today().isoformat():
            return
        time.sleep(20)


def cmd_enter(b, s):
    if not market_open():
        return log("market not open - enter runs 09:15-15:30 on trading days")
    reconcile(b, s) if LIVE else paper_stops(b, s)
    for sym in list(s["queue_sell"]):
        if sym in s["positions"]:
            close_position(b, s, sym, "queued-exit")
        elif sym in s["queue_sell"]:
            s["queue_sell"].remove(sym)
    ok, eq = risk_gate(b, s)
    for c in list(s["queue_buy"]):
        sym = c["sym"]
        if not ok or len(s["positions"]) >= MAX_POS or sym in s["positions"]:
            continue
        s["queue_buy"].remove(c)
        ltp = b.ltp(sym)
        if ltp > c["close"] * (1 + MAX_GAP):
            log(f"skip {sym}: gapped {ltp / c['close'] - 1:.1%} above signal")
            continue
        qty = int(min(RISK * eq / (STOP_ATR * c["atr"]), MAX_POS_PCT * eq / ltp, spendable(b, s) / ltp))   # donchian
        if qty < 1 or qty * ltp < MIN_POSITION:
            alert(f"skip {sym}: size {qty} x {ltp:.2f} below Rs {MIN_POSITION} (equity {eq:.0f}) - bot can't buy")
            continue
        open_position(b, s, sym, qty, ltp, atr=c.get("atr"), why=c.get("why", "rule"))
    save_state(s)


def open_position(b, s, sym, qty, ltp, stop_pct=None, atr=None, stop_px=None, why=""):
    """The ONLY way a position gets opened. Buy -> persist -> GTT stop; stop fails -> sell at once."""
    before = b.holdings().get(sym, 0)
    if LIVE and before:
        log(f"skip {sym}: user holds it manually - bot never mixes with manual holdings")
        return False
    try:
        filled, px = b.limit_order("BUY", sym, qty, b.round_tick(sym, ltp * (1 + LIMIT_SLIP), up=True))
    except Exception as e:  # unknown order state: trust the broker's holdings, never leave a fill unprotected
        alert(f"{sym} buy error ({e}) - checking holdings")
        time.sleep(5)
        filled, px = b.holdings().get(sym, 0) - before, ltp
        if filled <= 0:
            raise
    if not filled:
        return False
    if stop_px:
        stop = min(stop_px, px * 0.995)
    else:
        stop = px * (1 - stop_pct) if stop_pct else px - STOP_ATR * atr
    buy_cost = backtest.costs(filled * px, 0)
    s["cash"] -= filled * px + buy_cost
    s["positions"][sym] = dict(qty=filled, qty0=filled, entry=px, stop=stop, stop_id=None, hi=px,
                               buy_cost=round(buy_cost, 2), t0=datetime.now().isoformat(), why=why)
    save_state(s)  # persist BEFORE stop call: a crash here is caught by reconcile next run
    protect(b, s, sym)
    return True


# ---- brain commands: discretionary decisions, same hard rails as the rules ----
def brain_budget(s):
    today = date.today().isoformat()
    s["brain_trades"] = {today: s.get("brain_trades", {}).get(today, 0)}
    if s["brain_trades"][today] >= BRAIN_MAX_TRADES:
        raise Fatal(f"brain trade limit ({BRAIN_MAX_TRADES}/day) reached")
    s["brain_trades"][today] += 1


def cmd_buy(b, s, sym, rupees, stop_px, *why):
    sym, rupees, stop_px = sym.upper(), float(rupees), float(stop_px)
    if not market_open():
        raise Fatal("market closed")
    if sym not in b.inst:
        raise Fatal(f"{sym} not an NSE EQ symbol")
    if sym != "NIFTYBEES" and sym not in set(s.get("candidates", [])) | watchlist():
        raise Fatal(f"{sym} not in momentum candidates {s.get('candidates', [])} or watchlist.txt - brain can't add new names")
    ok, eq = risk_gate(b, s)
    if not ok:
        raise Fatal("risk gate closed (kill switch / daily loss)")
    if sym in s["positions"] or len(s["positions"]) >= MAX_POS:
        raise Fatal(f"already holding {sym} or max {MAX_POS} positions")
    ltp = b.ltp(sym)
    if not ltp * (1 - MAX_STOP_PCT) <= stop_px < ltp:
        raise Fatal(f"stop {stop_px} must be below LTP {ltp} and within {MAX_STOP_PCT:.0%}")
    qty = int(min(rupees, MAX_POS_PCT * eq, spendable(b, s)) / ltp)
    qty = min(qty, int(MAX_TRADE_RISK * eq / (ltp - stop_px)))
    if qty < 1 or qty * ltp < MIN_POSITION:
        raise Fatal(f"size {qty} x {ltp} below minimum Rs {MIN_POSITION} after risk caps")
    brain_budget(s)
    log(f"BRAIN BUY {sym} x{qty} ~{ltp} stop {stop_px} why: {' '.join(why)}")
    open_position(b, s, sym, qty, ltp, stop_px=stop_px, why="brain: " + " ".join(why))


def cmd_sell(b, s, sym, *why):
    sym = sym.upper()
    if sym not in s["positions"]:
        raise Fatal(f"{sym} not a bot position")
    brain_budget(s)
    close_position(b, s, sym, "brain: " + " ".join(why))


def cmd_mybuy(b, s, sym, rupees=None):
    """User's own order (typed by the user via ./t): any NSE stock, up to all spendable cash, auto stop -5%.
    Same risk rails as the brain (kill switch, 60% max position, 8% max risk, 5 positions) but no watchlist limit
    and no brain trade budget."""
    sym = sym.upper()
    if not market_open():
        raise Fatal("market closed")
    if sym not in b.inst:
        raise Fatal(f"{sym} not an NSE EQ symbol")
    ok, eq = risk_gate(b, s)
    if not ok:
        raise Fatal("risk gate closed (kill switch / daily loss)")
    if sym in s["positions"] or len(s["positions"]) >= MAX_POS:
        raise Fatal(f"already holding {sym} or max {MAX_POS} positions")
    ltp = b.ltp(sym)
    stop_px = b.round_tick(sym, ltp * (1 - USER_STOP), up=False)
    qty = int(min(float(rupees or 1e12), MAX_POS_PCT * eq, spendable(b, s)) / ltp)
    qty = min(qty, int(MAX_TRADE_RISK * eq / (ltp - stop_px)))
    if qty < 1 or qty * ltp < MIN_POSITION:
        raise Fatal(f"size {qty} x {ltp} below minimum Rs {MIN_POSITION} (spendable Rs {spendable(b, s):.0f})")
    log(f"USER BUY {sym} x{qty} ~{ltp} stop {stop_px}")
    open_position(b, s, sym, qty, ltp, stop_px=stop_px, why="user order")


def cmd_mysell(b, s, sym):
    """User's own sell (typed by the user via ./t): no brain trade budget."""
    sym = sym.upper()
    if sym not in s["positions"]:
        raise Fatal(f"{sym} not a bot position")
    close_position(b, s, sym, "user order")


def cmd_tp(b, s, sym):
    """Take profit (watcher calls this, no brain budget): sell if NET pnl >= TAKE_PROFIT of cost right now."""
    sym = sym.upper()
    p = s["positions"].get(sym)
    if not p:
        raise Fatal(f"{sym} not a bot position")
    if s.get("api_blocked", {}).get(sym) == date.today().isoformat():
        return log(f"tp {sym}: API orders blocked today (cautionary list) - user must sell in the app")
    net, basis = net_pnl(p, b.ltp(sym))
    if net < TAKE_PROFIT * basis:
        return log(f"tp {sym}: NET {net:+.0f} < {TAKE_PROFIT:.0%} of {basis:.0f} - hold")
    alert(f"TAKE PROFIT {sym}: NET {net:+.0f} ({net / basis:+.1%})")
    close_position(b, s, sym, f"take-profit NET {net:+.0f}")


def cmd_setstop(b, s, sym, price):
    """Ratchet only, and never tighter than SETSTOP_FLOOR x highest close (tight stops tested badly)."""
    sym, price = sym.upper(), float(price)
    p = s["positions"].get(sym) or {}
    if not p:
        raise Fatal(f"{sym} not a bot position")
    ltp = b.ltp(sym)
    cap = min(ltp * 0.995, p.get("hi", p["entry"]) * SETSTOP_FLOOR)
    if not p["stop"] < price <= cap:
        raise Fatal(f"new stop {price} must be > current {p['stop']:.2f} and <= {cap:.2f}")
    old_id = p["stop_id"]
    new_id = b.place_stop(sym, p["qty"], price)  # new first, then cancel old: never unprotected
    p["stop"], p["stop_id"] = price, new_id
    if not b.cancel_stop(sym, old_id):
        alert(f"{sym}: old GTT {old_id} not cancelled - two stops live, check app")
    log(f"STOP raised {sym} -> {price}")


def cmd_adjust(b, s, sym, ratio):
    """Split/bonus: ratio = new shares per old share (1:1 bonus -> 2, 1:5 split -> 5). Run BEFORE the ex-date open,
    else the GTT (old price) fires on the mechanical price drop. Re-sizes the stop: new first, then cancel old."""
    sym, r = sym.upper(), float(ratio)
    p = s["positions"].get(sym)
    if not p or not 1 < r <= 20:
        raise Fatal(f"{sym} not a bot position or bad ratio {ratio}")
    if p.get("adjusted") == date.today().isoformat():
        raise Fatal(f"{sym} already adjusted today")
    old_id, new_qty = p["stop_id"], int(round(p["qty"] * r))
    new_id = b.place_stop(sym, new_qty, p["stop"] / r)
    if not b.cancel_stop(sym, old_id):
        b.cancel_stop(sym, new_id)
        raise Fatal(f"{sym}: old GTT {old_id} would not cancel - adjustment aborted, old stop kept")
    p.update(qty=new_qty, qty0=int(round(p.get("qty0", p["qty"]) * r)), entry=p["entry"] / r, stop=p["stop"] / r,
             hi=p.get("hi", p["entry"]) / r, stop_id=new_id, adjusted=date.today().isoformat())
    log(f"ADJUSTED {sym} x{r}: qty {new_qty} entry {p['entry']:.2f} stop {p['stop']:.2f}")


def cmd_cancelgtt(b, s, sym, rid):
    """Cancel a stray GTT (e.g. left by live_test). Refuses if it protects a bot position."""
    sym = sym.upper()
    if any(p.get("stop_id") == str(rid) for p in s["positions"].values()):
        raise Fatal(f"GTT {rid} protects a bot position - use sell/setstop instead")
    log(f"cancelgtt {sym} {rid}:", b.cancel_stop(sym, str(rid)))


def cmd_veto(b, s, sym, *why):
    sym = sym.upper()
    s["queue_buy"] = [c for c in s["queue_buy"] if c["sym"] != sym]
    log(f"BRAIN VETO {sym}: {' '.join(why)}")


def cmd_status(b, s):
    ok, eq = risk_gate(b, s)
    if LIVE and not live_allowed():
        log("LIVE LOCKED: live_test.py has not passed (docs/live_test_result.json) - observe only")
    log(f"equity {eq:.0f} (bot cash {s['cash']:.0f}) peak {s['peak']:.0f} buys_allowed={ok} strategy={STRATEGY}")
    for sym, p in s["positions"].items():
        ltp = b.ltp(sym)
        gross = (ltp - p["entry"]) * p["qty"]
        net = net_pnl(p, ltp)[0]
        log(f"  {sym} x{p['qty']} entry {p['entry']:.2f} ltp {ltp:.2f} stop {p['stop']:.2f} hi {p.get('hi', 0):.2f} "
            f"NET pnl if sold now {net:+.0f} (gross {gross:+.0f}) stop_id {p['stop_id']} ({b.stop_state(p['stop_id'])})")
    if JOURNAL.exists():
        done = pd.read_csv(JOURNAL)
        log(f"realised NET pnl (after all charges): {done.pnl.sum():+.2f} over {len(done)} closed trades")
    log("queued buys:", [c["sym"] for c in s["queue_buy"]], "queued sells:", s["queue_sell"])


def wake_brain_on_error(cmd, err):
    """Live run failed -> start the brain now to diagnose, fix and rerun (never wait for a human or the next slot).
    brain.sh skips EVENT if a brain run is already active, so a failing rerun can't loop."""
    if not LIVE or cmd not in ("enter", "scan", "check"):
        return
    here = Path(__file__).parent
    (here / ".brain_event").write_text(f"{datetime.now():%F %T} RUN FAILED: `trader.py {cmd} --live` -> {err}\n")
    subprocess.Popen([str(here / "brain.sh"), "EVENT", "opus"], cwd=here, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    log("woke brain to fix failed run:", cmd)


def live_allowed():
    f = HERE / "docs/live_test_result.json"
    return f.exists() and json.loads(f.read_text()).get("all_ok") is True


def acquire_lock(lock):
    """Atomic lock (O_EXCL). Waits up to 10 min; stale (>30 min) locks are broken."""
    deadline = time.time() + 600
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL))
            return
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 1800:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                alert(f"{lock.name} held 10+ min - run skipped")
                sys.exit(4)
            time.sleep(5)


if __name__ == "__main__":
    cmds = dict(scan=cmd_scan, enter=cmd_enter, check=lambda b, s: reconcile(b, s) if LIVE else paper_stops(b, s),
                status=cmd_status, buy=cmd_buy, tp=cmd_tp, sell=cmd_sell, mybuy=cmd_mybuy, mysell=cmd_mysell, setstop=cmd_setstop, veto=cmd_veto,
                adjust=cmd_adjust, cancelgtt=cmd_cancelgtt)
    argv = [a for a in sys.argv[1:] if a != "--live"]
    if not argv or argv[0] not in cmds and argv[0] != "notify":
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "notify":  # brain -> user desktop notification (no broker, no lock)
        alert(" ".join(args))
        sys.exit(0)
    if LIVE and not live_allowed() and cmd not in ("status", "cancelgtt"):
        sys.exit("live trading locked until live_test.py passes (docs/live_test_result.json all_ok)")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(3))  # timeout/kill -> finally still saves + unlocks
    if cmd == "enter":
        wait_for_brain()  # BEFORE the lock: the brain's veto commands need it
    lock = HERE / f".trader{'_live' if LIVE else ''}.lock"
    acquire_lock(lock)
    state, rc = load_state(), 0
    if "started" in state:  # migrate old paper state
        state["rebalanced"] = "2026-10" if state.pop("started") else ""
    state.setdefault("rebalanced", "")
    state.setdefault("brain_trades", {})
    try:
        broker = Broker() if LIVE else PaperBroker(state)
        cmds[cmd](broker, state, *args)
        if cmd != "status":
            risk_gate(broker, state)
    except Fatal as e:
        alert(f"FATAL {cmd}: {e}")
        wake_brain_on_error(cmd, f"FATAL {e}")
        rc = 2
    except Exception as e:
        alert(f"CRASH {cmd}: {type(e).__name__}: {e}")
        wake_brain_on_error(cmd, f"CRASH {type(e).__name__}: {e}")
        raise
    finally:
        save_state(state)
        lock.unlink(missing_ok=True)
    sys.exit(rc)
