"""One-share LIVE smoke test of the bot's real order paths (trader.Broker). ~Rs 12 + ~Rs 24 charges.

  python live_test.py          # trading day 09:20-15:00; writes docs/live_test_result.json (all_ok unlocks --live)

Every step ASSERTS its result (a step that returns the wrong thing fails, not just one that raises).
Whatever fails, it still cancels the GTT and sells the share, so nothing is left unprotected.
Raw API payloads (holdings, orderbook, GTT) are saved so status strings / field names can be verified.
"""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.argv.append("--live")  # trader.LIVE must be True so the real Broker + live paths are used
import trader  # noqa: E402

SYM, OUT = "IDEA", Path(__file__).parent / "docs/live_test_result.json"
res = dict(started=datetime.now().isoformat(), steps=[], raw={})


def step(name, fn, check=lambda v: True, why=""):
    try:
        v = fn()
        ok = bool(check(v))
        res["steps"].append(dict(step=name, ok=ok, result=str(v)[:800], **({} if ok else {"failed_check": why})))
        trader.log("TEST", "ok" if ok else "FAIL", name, str(v)[:200], "" if ok else why)
        return v
    except Exception as e:
        res["steps"].append(dict(step=name, ok=False, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-1500:]))
        trader.log("TEST FAIL", name, e)
        return None


if __name__ == "__main__":
    if OUT.exists() and json.loads(OUT.read_text()).get("finished"):
        sys.exit("live test already done (delete docs/live_test_result.json to rerun)")
    if not trader.market_open() or datetime.now().hour >= 15:
        sys.exit("run on a trading day between 09:20 and 15:00")
    b = trader.Broker()
    res["raw"]["holding"] = step("raw_holding", lambda: b.call("holding").get("data"))
    step("funds_availablecash", b.funds, lambda v: v >= 50, "need >= Rs 50 cash")
    before = step("holdings_before", b.holdings, lambda v: isinstance(v, dict))
    ltp = step("ltp", lambda: b.ltp(SYM), lambda v: 1 < v < 1000)
    filled = rid = None
    if ltp and before is not None:
        price = b.round_tick(SYM, ltp * 1.005, up=True)
        filled = step("buy_limit_1", lambda: b.limit_order("BUY", SYM, 1, price), lambda v: v[0] == 1, "buy not filled")
    if filled and filled[0] == 1:
        step("holdings_after_buy", b.holdings, lambda v: v.get(SYM, 0) == before.get(SYM, 0) + 1,
             "position/holding qty did not rise by 1 (T1/netqty semantics?)")
        res["raw"]["orderbook"] = step("orderbook_has_tag", lambda: [
            {k: o.get(k) for k in ("orderid", "uniqueorderid", "ordertag", "status", "orderstatus", "text",
                                   "filledshares", "averageprice", "transactiontype", "variety")}
            for o in b.orders() if o.get("tradingsymbol") == f"{SYM}-EQ"],
            lambda v: any(str(o.get("ordertag", "")).startswith("bot") for o in v), "ordertag not echoed in orderBook")
        rid = step("gtt_create", lambda: b.place_stop(SYM, 1, filled[1] * 0.80), lambda v: bool(v))  # far below
        if rid:
            res["raw"]["gtt_details"] = step("raw_gtt_details", lambda: b.call("gttDetails", rid).get("data"))
            step("gtt_state_active", lambda: b.stop_state(rid), lambda v: v == "active",
                 "status string not in GTT_ACTIVE - update trader.GTT_* sets from raw_gtt_details")
            res["raw"]["gtt_list"] = step("raw_gtt_list", lambda: b.call("gttLists", ["NEW", "ACTIVE"], 1, 10).get("data"))
            step("find_gtt_dedupe", lambda: b.find_gtt(SYM, 1), lambda v: v == rid, "find_gtt can't see the rule")
            step("gtt_cancel", lambda: b.cancel_stop(SYM, rid), lambda v: v is True)
            res["raw"]["gtt_after_cancel"] = step("raw_gtt_after_cancel", lambda: b.call("gttDetails", rid).get("data"))
            step("gtt_state_dead", lambda: b.stop_state(rid), lambda v: v == "dead", "cancelled rule not seen as dead")
        ltp2 = b.ltp(SYM)
        step("sell_limit_1", lambda: b.limit_order("SELL", SYM, 1, b.round_tick(SYM, ltp2 * 0.995, up=False)),
             lambda v: v[0] == 1, "sell not filled - 1 IDEA share left over (no stop), sell it manually")
        step("holdings_restored", b.holdings, lambda v: v.get(SYM, 0) == before.get(SYM, 0))
    res["finished"] = datetime.now().isoformat()
    res["all_ok"] = bool(filled and filled[0] == 1) and all(s["ok"] for s in res["steps"])
    OUT.write_text(json.dumps(res, indent=2, default=str))
    trader.alert(f"LIVE TEST {'PASSED' if res['all_ok'] else 'FAILED'} - see docs/live_test_result.json")
