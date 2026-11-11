"""Angel One SmartAPI helper. Login is automatic (PIN + TOTP), no browser.

  python angel.py status                       # funds + holdings
  python angel.py price INFY                   # live LTP
  python angel.py candles INFY 5               # last 5 days, 5-minute candles
  python angel.py order BUY INFY 1             # DRY RUN: prints the order only
  python angel.py order BUY INFY 1 --live      # actually places a DELIVERY limit order (0.5% through LTP)
"""
import utils.session
import utils.clients
import utils.http_session
import utils.transport
import json
import logging
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pyotp
import urllib3.util.connection
from SmartApi import SmartConnect

logging.disable(logging.ERROR)  # SDK logs every request; its ERROR lines print headers incl. API key -> silenced (our code logs the message/errorcode)

# Force IPv4: Angel accepts only an IPv4 static IP.
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

HERE = Path(__file__).parent


def env():
    # ponytail: tiny .env parser, swap for python-dotenv if you need quoting/multiline
    lines = (HERE / ".env").read_text().splitlines()
    return {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in lines if "=" in l and not l.startswith("#"))}


def _fix_ip(api, cfg):
    """SDK 1.5.5 bug: a `finally:` hardcodes X-ClientPublicIP=106.193.147.98 for everyone. Send our registered IP."""
    api.clientPublicIp = cfg.get("ANGEL_STATIC_IP") or api.clientPublicIp
    # SDK 1.5.5 bug #2: GTT create/modify/cancel routes carry a "/gtt-service" prefix -> "no Route matched".
    # Documented path (verified live 2026-11-04) has no prefix, same as gtt details/list.
    for k in ("api.gtt.create", "api.gtt.modify", "api.gtt.cancel"):
        api._routes[k] = api._routes[k].replace("/gtt-service", "")
    return api


SESSION = HERE / ".session.json"   # shared by every process; Angel invalidates sessions when one ID logs in too often


def login(force=False):
    """One Angel session per day shared via .session.json (0600). force=True after a token error."""
    import fcntl
    cfg = env()
    if not cfg.get("ANGEL_PIN"):
        sys.exit("Add ANGEL_PIN to .env first")
    with open(HERE / ".session.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)  # concurrent processes: only one logs in, the rest reuse its tokens
        if not force and SESSION.exists():
            c = json.loads(SESSION.read_text())
            if c.get("day") == datetime.now().strftime("%Y-%m-%d"):  # tokens die at midnight
                return _fix_ip(SmartConnect(api_key=cfg["ANGEL_API_KEY"], access_token=c["jwt"], refresh_token=c["refresh"],
                                            feed_token=c["feed"], userId=cfg["ANGEL_CLIENT_ID"], timeout=15), cfg)
        api = _fix_ip(SmartConnect(api_key=cfg["ANGEL_API_KEY"], timeout=15), cfg)  # SDK default timeout = none
        r = api.generateSession(cfg["ANGEL_CLIENT_ID"], cfg["ANGEL_PIN"], pyotp.TOTP(cfg["ANGEL_TOTP_SECRET"]).now())
        if not r.get("status"):
            sys.exit(f"Login failed: {r.get('message')} ({r.get('errorcode')})")
        tmp = SESSION.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(dict(day=datetime.now().strftime("%Y-%m-%d"), jwt=api.access_token,
                                       refresh=api.refresh_token, feed=api.feed_token)))
        tmp.replace(SESSION)
        return api


def token(api, symbol):
    """NSE equity symbol -> (tradingsymbol, symboltoken)."""
    want = f"{symbol.upper()}-EQ"
    for s in api.searchScrip("NSE", symbol.upper())["data"]:
        if s["tradingsymbol"] == want:
            return s["tradingsymbol"], s["symboltoken"]
    sys.exit(f"{want} not found on NSE")


def show(name, data):
    print(f"\n== {name} ==\n" + json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "status":
        api = login()
        show("funds", api.rmsLimit()["data"])
        show("holdings", api.holding()["data"])
    elif cmd == "price" and len(a) == 2:
        api = login()
        ts, tok = token(api, a[1])
        print(ts, "LTP:", api.ltpData("NSE", ts, tok)["data"]["ltp"])
    elif cmd == "candles" and len(a) >= 2:
        api = login()
        ts, tok = token(api, a[1])
        days = int(a[2]) if len(a) > 2 else 5
        now = datetime.now()
        rows = api.getCandleData(dict(
            exchange="NSE", symboltoken=tok, interval="FIVE_MINUTE",
            fromdate=(now - timedelta(days=days)).strftime("%Y-%m-%d 09:15"),
            todate=now.strftime("%Y-%m-%d %H:%M"),
        ))["data"] or []
        print("time, open, high, low, close, volume")
        for r in rows[-10:]:
            print(*r, sep=", ")
        print(f"({len(rows)} candles total, last 10 shown)")
    elif cmd == "order" and len(a) >= 4:
        side, sym, qty = a[1].upper(), a[2], int(a[3])
        api = login()
        ts, tok = token(api, sym)
        params = dict(
            variety="NORMAL", tradingsymbol=ts, symboltoken=tok, transactiontype=side,
            exchange="NSE", ordertype="LIMIT", producttype="DELIVERY",  # INTRADAY for same-day
            duration="DAY", quantity=str(qty),
        )
        # Angel bans MARKET orders for API/algo since 1 Apr 2026 -> marketable LIMIT 0.5% through LTP
        ltp = api.ltpData("NSE", ts, tok)["data"]["ltp"]
        params["price"] = str(round(ltp * (1.005 if side == "BUY" else 0.995), 1))
        if "--live" not in a:
            print("DRY RUN (add --live to send):", params)
        else:
            print("Order placed, id:", api.placeOrder(params))
    else:
        print(__doc__)
