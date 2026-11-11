"""Offline checks for money-critical paths. No API calls, never touches real state.
Run: .venv/bin/python test_trader.py"""
import tempfile
from datetime import date
from pathlib import Path

import backtest
import trader

_tmp = Path(tempfile.mkdtemp())  # never touch real state/journal/log files
trader.STATE_FILE, trader.JOURNAL, trader.LOG = _tmp / "state.json", _tmp / "journal.csv", _tmp / "trader.log"
trader.alert = lambda m: trader.log("ALERT", m)  # no desktop popups
trader.time.sleep = lambda *_: None              # no real waiting


class Fake(trader.Broker):
    """Scriptable broker: no network."""
    def __init__(self):
        self.inst = {"INFY": {"tick_size": "10.000000", "symbol": "INFY-EQ", "token": "1"},
                     "IDEA": {"tick_size": "1.000000", "symbol": "IDEA-EQ", "token": "2"},
                     "TEST": {"tick_size": "5.000000", "symbol": "TEST-EQ", "token": "3"}}
        self.px, self.cash, self.held, self.gtt, self.orders_log = 100.0, 5000.0, {}, {}, []
        self.fill, self.cancel_ok, self.sell_raises = True, True, False

    def ltp(self, sym): return self.px
    def funds(self): return self.cash
    def holdings(self): return dict(self.held)
    def cancel_open_orders(self, sym, side="SELL"): self.orders_log.append(("CANCEL_OPEN", sym))
    def find_gtt(self, sym, qty): return None

    def limit_order(self, side, sym, qty, price, wait=90):
        if side == "SELL" and self.sell_raises:
            raise ConnectionError("net down")
        self.orders_log.append((side, sym, qty))
        if not self.fill:
            return 0, price
        self.held[sym] = self.held.get(sym, 0) + (qty if side == "BUY" else -qty)
        return qty, self.px

    def place_stop(self, sym, qty, trigger):
        rid = f"g{len(self.gtt) + 1}"
        self.gtt[rid] = "active"
        return rid

    def stop_state(self, rid): return self.gtt.get(rid, "dead") if rid else "dead"

    def cancel_stop(self, sym, rid):
        if rid and self.cancel_ok:
            self.gtt[rid] = "dead"
        return self.cancel_ok or not rid


def new_state():
    return dict(positions={}, queue_buy=[], queue_sell=[], peak=None, day=None, day_start=None,
                cash=5000.0, rebalanced="", brain_trades={})


def fails(fn, *a):
    try:
        fn(*a)
    except trader.Fatal:
        return True
    return False


# ---- ticks, calendar, costs ----
b = Fake()
assert b.tick("INFY") == 0.10 and b.tick("IDEA") == 0.01          # scrip master tick is paise
assert b.round_tick("INFY", 1135.17, up=True) == 1135.2
assert b.round_tick("INFY", 1135.17, up=False) == 1135.1
assert b.round_tick("INFY", 1135.2, up=True) == 1135.2
assert not trader.market_day(date(2026, 11, 8)) and not trader.market_day(date(2026, 11, 10))
assert trader.market_day(date(2026, 11, 4))
assert fails(trader.market_day, date(2027, 1, 4))                  # calendar fails closed
assert 40 < backtest.costs(2500, 2500) < 42                        # STT 5 + stamp 0.4 + exch + DP 23.6 + brok 2x5+GST
assert 8 < backtest.costs(2500, 0) < 10                           # no DP on a buy; min brokerage Rs 5+GST

trader.market_open = lambda: True

# ---- brain rails ----
b, s = Fake(), new_state()
assert fails(trader.cmd_buy, b, s, "TEST", 2500, 86)              # not a strategy candidate -> refused
s["candidates"] = ["TEST"]
for bad_stop in (80, 100, 101):                                    # >15% away, at LTP, above LTP
    assert fails(trader.cmd_buy, b, s, "TEST", 2500, bad_stop), bad_stop
trader.cmd_buy(b, s, "TEST", 9999, 86)   # 60% cap -> 30 sh; risk 14 x 30 = 420 > 8% (400) -> 28
assert b.orders_log[-1] == ("BUY", "TEST", 28), b.orders_log
p = s["positions"]["TEST"]
assert p["stop"] == 86 and b.stop_state(p["stop_id"]) == "active"
assert s["cash"] < 5000 - 28 * 100                                 # bot cash tracks buy + costs
assert fails(trader.cmd_setstop, b, s, "TEST", 80)                 # lower: refused
assert fails(trader.cmd_setstop, b, s, "TEST", 95)                 # above 80% of highest close (hi=100): refused
p["hi"] = 125
old = p["stop_id"]
trader.cmd_setstop(b, s, "TEST", 99)
assert p["stop"] == 99 and b.stop_state(old) == "dead" and b.stop_state(p["stop_id"]) == "active"
trader.cmd_sell(b, s, "TEST", "x")
s["candidates"] = ["TEST"]
s["brain_trades"] = {date.today().isoformat(): trader.BRAIN_MAX_TRADES}
assert "TEST" not in s["positions"] and fails(trader.cmd_buy, b, s, "TEST", 2500, 90)   # daily brain limit

# ---- manual holdings are never mixed ----
b, s = Fake(), new_state()
b.held = {"IDEA": 4}
trader.LIVE = True
assert trader.open_position(b, s, "IDEA", 10, 100.0, stop_pct=0.15) is False and not b.orders_log
trader.LIVE = False


# ---- buy dies mid-way ----
class Boom(Fake):
    def limit_order(self, *a, **k): raise ConnectionError("net down")


b, s = Boom(), new_state()
try:
    trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
    raise AssertionError("error swallowed with no fill")
except ConnectionError:
    pass
assert not s["positions"]
seq = iter([{}, {"TEST": 10}])                                     # error, but broker shows 10 bought -> adopt + protect
b.holdings = lambda: next(seq)
assert trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
assert s["positions"]["TEST"]["qty"] == 10 and b.stop_state(s["positions"]["TEST"]["stop_id"]) == "active"

# ---- sell paths ----
b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
b.cancel_ok = False                                                # GTT won't cancel -> must NOT sell (double sell)
trader.close_position(b, s, "TEST", "t")
assert ("SELL", "TEST", 10) not in b.orders_log and s["positions"]["TEST"]["qty"] == 10
b.cancel_ok, b.sell_raises = True, True                            # sell blows up after GTT cancel -> re-protected + queued
trader.close_position(b, s, "TEST", "t")
assert b.stop_state(s["positions"]["TEST"]["stop_id"]) == "active" and "TEST" in s["queue_sell"]
b.sell_raises, b.fill = False, False                               # limit not filled -> re-protected + queued
trader.close_position(b, s, "TEST", "t")
assert b.stop_state(s["positions"]["TEST"]["stop_id"]) == "active" and "TEST" in s["queue_sell"]
b.fill = True
trader.close_position(b, s, "TEST", "t")
assert "TEST" not in s["positions"] and "TEST" not in s["queue_sell"]
assert 5000 - 60 < s["cash"] < 5000                                # round trip at same price costs ~Rs 25-50

# ---- reconcile ----
b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
rid = s["positions"]["TEST"]["stop_id"]
b.gtt[rid], b.held = "triggered", {}                               # stop filled at broker
trader.reconcile(b, s)
assert "TEST" not in s["positions"]

b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
rid = s["positions"]["TEST"]["stop_id"]
b.gtt[rid], b.px = "triggered", 80.0                              # triggered, limit unfilled, price gapped below
trader.reconcile(b, s)
assert ("CANCEL_OPEN", "TEST") in b.orders_log and "TEST" not in s["positions"]

b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
b.gtt[s["positions"]["TEST"]["stop_id"]] = "unknown"               # can't read GTT -> touch nothing
n = len(b.orders_log)
trader.reconcile(b, s)
assert len(b.orders_log) == n and len(b.gtt) == 1

b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
b.gtt[s["positions"]["TEST"]["stop_id"]] = "dead"                  # stop vanished, price fine -> re-place
trader.reconcile(b, s)
assert b.stop_state(s["positions"]["TEST"]["stop_id"]) == "active" and len(b.gtt) == 2

b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
b.held["TEST"] = 14                                                # user bought 4 more manually
trader.reconcile(b, s)
assert s["positions"]["TEST"]["qty"] == 10                         # bot never claims the user's shares

b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
trader.market_open = lambda: False                                 # outside market hours reconcile never sells
b.gtt[s["positions"]["TEST"]["stop_id"]], b.px = "dead", 80.0
trader.reconcile(b, s)
assert ("SELL", "TEST", 10) not in b.orders_log and "TEST" in s["queue_sell"]

# ---- split/bonus adjust ----
trader.market_open = lambda: True
b, s = Fake(), new_state()
trader.open_position(b, s, "TEST", 10, 100.0, stop_pct=0.15)
old = s["positions"]["TEST"]["stop_id"]
trader.cmd_adjust(b, s, "TEST", 2)
p = s["positions"]["TEST"]
assert p["qty"] == 20 and abs(p["stop"] - 42.5) < 1e-9 and b.stop_state(old) == "dead" and b.stop_state(p["stop_id"]) == "active"
assert fails(trader.cmd_adjust, b, s, "TEST", 2)                   # never twice in a day

# ---- user's protected stocks: real Broker refuses before any API call ----
b = Fake()
for fn in (lambda: trader.Broker.limit_order(b, "SELL", "JPL", 12, 1400.0),
           lambda: trader.Broker.place_stop(b, "JPL", 12, 1200.0)):
    try:
        fn(); raise AssertionError("JPL order not blocked")
    except trader.Fatal:
        pass
print("all checks passed")


# brain mode: net_pnl matches the live status line (BHEL 2026-11-11: ltp 430.40 -> NET +45), take-profit level
_p = dict(qty=11, qty0=11, entry=422.65, buy_cost=5.54)
assert round(trader.net_pnl(_p, 430.40)[0]) == 45, trader.net_pnl(_p, 430.40)
assert trader.net_pnl(_p, 422.65 * 1.06)[0] >= trader.TAKE_PROFIT * trader.net_pnl(_p, 0)[1]   # +5% net needs ~+5.9% price (charges)
assert trader.net_pnl(_p, 422.65 * 1.05)[0] < trader.TAKE_PROFIT * trader.net_pnl(_p, 0)[1]
print("brain-mode checks passed")
