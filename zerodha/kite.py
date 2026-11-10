"""Zerodha Kite Connect helper.

  python kite.py login                      # once per day (token expires ~6 AM)
  python kite.py status                     # profile, funds, holdings, positions, orders
  python kite.py order BUY INFY 1           # DRY RUN: prints the order only
  python kite.py order BUY INFY 1 --live    # actually places a CNC market order on NSE
"""
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import socket

import urllib3.util.connection
from kiteconnect import KiteConnect

# Force IPv4: only the IPv4 address is whitelisted; api.kite.trade also resolves over IPv6.
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

HERE = Path(__file__).parent
TOKEN_FILE = HERE / ".access_token"


def env():
    # ponytail: tiny .env parser, swap for python-dotenv if you need quoting/multiline
    lines = (HERE / ".env").read_text().splitlines()
    return dict(l.split("=", 1) for l in lines if "=" in l and not l.startswith("#"))


def kite():
    cfg = env()
    k = KiteConnect(api_key=cfg["KITE_API_KEY"].strip())
    if TOKEN_FILE.exists():
        k.set_access_token(TOKEN_FILE.read_text().strip())
    return k, cfg


def login():
    k, cfg = kite()
    print("Opening login page. After login, copy the FULL URL you land on and paste it here.")
    webbrowser.open(k.login_url())
    url = input("Redirect URL: ").strip()
    request_token = parse_qs(urlparse(url).query)["request_token"][0]
    session = k.generate_session(request_token, api_secret=cfg["KITE_API_SECRET"].strip())
    TOKEN_FILE.write_text(session["access_token"])
    TOKEN_FILE.chmod(0o600)
    print("Logged in as", session["user_name"])


def status():
    k, _ = kite()
    show = lambda name, data: print(f"\n== {name} ==\n" + json.dumps(data, indent=2, default=str))
    show("profile", k.profile())
    show("funds (equity)", k.margins("equity"))
    show("holdings", k.holdings())
    show("positions", k.positions())
    show("orders today", k.orders())


def order(side, symbol, qty, live):
    k, _ = kite()
    params = dict(
        variety=k.VARIETY_REGULAR,
        exchange=k.EXCHANGE_NSE,
        tradingsymbol=symbol.upper(),
        transaction_type=side.upper(),  # BUY / SELL
        quantity=int(qty),
        product=k.PRODUCT_CNC,  # delivery; use PRODUCT_MIS for intraday
        order_type=k.ORDER_TYPE_MARKET,
        market_protection=-1,  # exchanges reject unprotected API market orders; -1 = auto
    )
    if not live:
        print("DRY RUN (add --live to send):", params)
        return
    print("Order placed, id:", k.place_order(**params))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["login"]:
        login()
    elif a[:1] == ["status"]:
        status()
    elif a[:1] == ["order"] and len(a) >= 4:
        order(a[1], a[2], a[3], "--live" in a)
    else:
        print(__doc__)
