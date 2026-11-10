"""Market-hours watcher: polls every 60s, no LLM, never trades. Wakes the brain (EVENT run) on anomalies.

  python watcher.py            # launchd starts it 09:16 on trading days; exits at 15:30

Watches the LIVE positions if live is unlocked, else the PAPER ones. Triggers (debounced):
  - position down >= DROP from today's open, or up >= SPIKE      -> brain EVENT
  - price within NEAR_STOP of its stop                           -> brain EVENT
  - NIFTYBEES down >= MARKET_DROP from today's open              -> brain EVENT
  - stop not active (live, checked every 5 min)                  -> `trader.py check` (re-protects) + brain EVENT
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
LIVE_OK = (HERE / "docs/live_test_result.json").exists() and \
    json.loads((HERE / "docs/live_test_result.json").read_text()).get("all_ok") is True
if LIVE_OK:
    sys.argv.append("--live")
import trader  # noqa: E402  (after --live so trader.LIVE matches)

POLL, GTT_EVERY = 60, 5                 # seconds; GTT check every 5th poll
DROP, SPIKE, NEAR_STOP, MARKET_DROP = 0.05, 0.08, 0.02, 0.02
COOLDOWN, MAX_EVENTS = 45 * 60, 4       # per trigger key; brain EVENT runs per day
fired, events = {}, 0


def wake_brain(reason):
    """Start a brain EVENT run in the background (debounced, capped per day)."""
    global events
    if events >= MAX_EVENTS:
        return trader.log("watcher: event cap reached, not waking brain:", reason)
    events += 1
    trader.alert(f"watcher -> brain: {reason}")
    (HERE / ".brain_event").write_text(f"{datetime.now():%F %T} {reason}\n")
    subprocess.Popen([str(HERE / "brain.sh"), "EVENT", "opus"], cwd=HERE,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def trigger(key, reason):
    if time.time() - fired.get(key, 0) > COOLDOWN:
        fired[key] = time.time()
        wake_brain(reason)


def poll_once(b, s, opens, n):
    for sym in list(s["positions"]) + ["NIFTYBEES"]:
        if sym not in opens:
            bar = b.day_bar(sym)
            if bar:
                opens[sym] = bar[0]
    nb = b.ltp("NIFTYBEES")
    if "NIFTYBEES" in opens and nb <= opens["NIFTYBEES"] * (1 - MARKET_DROP):
        trigger("market", f"NIFTYBEES {nb / opens['NIFTYBEES'] - 1:.1%} today - market selloff")
    for sym, p in s["positions"].items():
        ltp = nb if sym == "NIFTYBEES" else b.ltp(sym)
        o = opens.get(sym)
        if o and ltp <= o * (1 - DROP):
            trigger(f"drop:{sym}", f"{sym} {ltp / o - 1:.1%} from open ({ltp})")
        if o and ltp >= o * (1 + SPIKE):
            trigger(f"spike:{sym}", f"{sym} +{ltp / o - 1:.1%} from open ({ltp}) - news?")
        if ltp <= p["stop"] * (1 + NEAR_STOP):
            trigger(f"near:{sym}", f"{sym} {ltp} within {NEAR_STOP:.0%} of stop {p['stop']:.2f}")
        if trader.LIVE and n % GTT_EVERY == 0 and b.stop_state(p["stop_id"]) not in ("active", "unknown"):
            trader.log(f"watcher: {sym} stop not active -> running check")
            subprocess.run([sys.executable, "trader.py", "check", "--live"], cwd=HERE, timeout=600)
            trigger(f"stop:{sym}", f"{sym} stop was not active - check ran, verify")


def main():
    if not trader.market_day():
        return
    b = trader.Broker() if trader.LIVE else trader.PaperBroker(trader.load_state())
    opens, n = {}, 0
    trader.log(f"watcher started ({'LIVE' if trader.LIVE else 'PAPER'} positions)")
    while trader.market_open():
        n += 1
        try:
            poll_once(b, trader.load_state(), opens, n)  # re-read state: bot/brain may have changed positions
        except Exception as e:  # watcher must never die mid-session
            trader.log("watcher error:", type(e).__name__, e)
        time.sleep(POLL)
    trader.log("watcher stopped (market closed)")


if __name__ == "__main__":
    main()
