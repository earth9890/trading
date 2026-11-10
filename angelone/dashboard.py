#!/usr/bin/env python3
"""READ-ONLY local dashboard. stdlib only, 127.0.0.1:8000. Never imports angel/trader, never touches .env/.session.json/app.log."""
import csv, json, re, plistlib, glob, os, html
from datetime import date, datetime
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

D = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(D, *a)
BAD = re.compile(r"bearer|authorization|x-privatekey|totp|password", re.I)

def text(path, tail=None):
    try:
        with open(path, errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if not BAD.search(l)]
    except OSError:
        return ""
    return "\n".join(lines[-tail:] if tail else lines)

def jload(name):
    try:
        return json.load(open(P(name)))
    except Exception:
        return None

def rows(name):
    try:
        with open(P(name), newline="", errors="replace") as f:
            return [r for r in csv.DictReader(f) if not BAD.search(" ".join(map(str, r.values())))]
    except OSError:
        return None

def consts():
    t = text(P("trader.py"))
    def num(k, d):
        m = re.search(rf"^{k}\s*=\s*([\d.]+)", t, re.M)
        return float(m[1]) if m else d
    m = re.search(r"^HOLIDAYS\s*=\s*\{([^}]*)\}", t, re.M)
    hol = re.findall(r"\d{4}-\d\d-\d\d", m[1]) if m else []
    return num("MAX_DD", .2), num("DAILY_LOSS", .05), hol

EQ = re.compile(r"^(\S+ \S+) (LIVE|PAPER) equity ([\d.]+)", re.M)
LTP = re.compile(r"^(\S+ \S+) (LIVE|PAPER)\s+(\S+) x\d+ entry [\d.]+ ltp ([\d.]+)")
def ltps(log):
    out = {"LIVE": {}, "PAPER": {}}
    for l in log.splitlines():
        m = LTP.match(l)
        if m:
            out[m[2]][m[3]] = float(m[4])
    return out

def account(name, lp):
    s = jload(f"state_{name}.json")
    if not s:
        return None
    pos = []
    for sym, p in (s.get("positions") or {}).items():
        last = lp.get(sym, p["entry"])
        pos.append(dict(sym=sym, qty=p["qty"], entry=p["entry"], stop=p.get("stop"), last=last,
                        stop_dist=(last - p["stop"]) / last * 100 if p.get("stop") else None,
                        pnl_gross=(last - p["entry"]) * p["qty"], t0=p.get("t0"), why=p.get("why")))
    eq = s.get("cash", 0) + sum(x["qty"] * x["last"] for x in pos)
    ds, pk = s.get("day_start") or eq, s.get("peak") or eq
    mdd, dl, _ = consts()
    jr = rows(f"journal_{name}.csv") or []
    realised = sum(float(r["pnl"]) for r in jr if r.get("pnl"))
    return dict(equity=eq, cash=s.get("cash"), day_start=ds, day_pnl=eq - ds, peak=pk,
                drawdown_pct=(1 - eq / pk) * 100 if pk else 0,
                buys_allowed=eq >= pk * (1 - mdd) and eq >= ds * (1 - dl),
                positions=pos, realised_net=realised, n_closed=len(jr), state_day=s.get("day"),
                queue_buy=s.get("queue_buy"), queue_sell=s.get("queue_sell"),
                candidates=s.get("candidates"), brain_trades=s.get("brain_trades"),
                rebalanced=s.get("rebalanced"), journal=jr)

OPT_CAPITAL = 30000.0   # options practice money per player (options_paper.CAPITAL)

def opts(fn):
    r = rows(fn) or []
    eq, curve = OPT_CAPITAL, []
    for x in r:
        eq += float(x.get("net") or 0)
        curve.append(dict(day=x["day"], eq=round(eq, 2)))
    wins = sum(float(x.get("net") or 0) > 0 for x in r)
    return dict(trades=r, curve=curve, equity=eq, total_net=eq - OPT_CAPITAL, n=len(r),
                win_rate=wins / len(r) * 100 if r else None)

def schedule():
    lines = text(P("logs", "launchd.log")).splitlines()
    runs = {}
    for i, l in enumerate(lines):
        m = re.match(r"=== (\S+ \S+) (.*)", l)
        if m:
            runs.setdefault(m[2].strip(), []).append((m[1], i))
    out = []
    for f in sorted(glob.glob(os.path.expanduser("~/Library/LaunchAgents/com.harish.*.plist"))):
        try:
            pl = plistlib.load(open(f, "rb"))
        except Exception:
            continue
        sci = pl.get("StartCalendarInterval", [])
        sci = [sci] if isinstance(sci, dict) else sci
        times = sorted({f"{c.get('Hour', '*')}:{int(c.get('Minute', 0)):02d}" if "Hour" in c else "-" for c in sci})
        days = sorted({c["Weekday"] for c in sci if "Weekday" in c})
        args = [os.path.basename(a) for a in pl.get("ProgramArguments", [])]
        out.append(dict(label=pl["Label"], at=", ".join(times) or ("RunAtLoad" if pl.get("RunAtLoad") else "-"),
                        days="Mon-Fri" if days == [1, 2, 3, 4, 5] else ",".join(map(str, days)) or "daily",
                        cmd=" ".join(args), key=None))
    today = date.today().isoformat()
    tr = []
    for k, v in runs.items():
        for ts, i in v:
            if ts.startswith(today):
                nxt = lines[i + 1:i + 40]
                tb = []
                for l in nxt:
                    if l.startswith("==="):
                        break
                    tb.append(l)
                tb_txt = "\n".join(tb)
                tr.append(dict(ts=ts, job=k, error="Traceback" in tb_txt, tb=tb_txt[-1500:] if "Traceback" in tb_txt else ""))
    for j in out:
        a = j["cmd"].split()
        if a and a[0] == "run.sh":
            v = runs.get(" ".join(a[1:]))
            j["last_run"] = v[-1][0] if v else None
        elif a and a[0] == "brain.sh":
            fs = sorted(glob.glob(P("logs", "brain", f"*-{a[1]}.log")))
            j["last_run"] = os.path.basename(fs[-1])[:10] if fs else None
        else:
            j["last_run"] = None
    return dict(jobs=out, today_runs=sorted(tr, key=lambda x: x["ts"], reverse=True))

def brain_logs():
    fs = sorted(glob.glob(P("logs", "brain", "*.log")), reverse=True)[:12]
    return [dict(name=os.path.basename(f), body=text(f)[-6000:]) for f in fs]

def status():
    mdd, dl, hol = consts()
    lt = jload("docs/live_test_result.json") or {}
    today = date.today()
    return dict(now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), live_test_ok=lt.get("all_ok"),
                holiday_today=today.isoformat() in hol, weekend=today.weekday() >= 5,
                max_dd=mdd, daily_loss=dl, holidays=hol)

def overview():
    log = text(P("trader.log"))
    lp = ltps(log)
    live, paper = account("live", lp["LIVE"]), account("paper", lp["PAPER"])
    kill = bool(live) and not live["buys_allowed"]
    curves = {"LIVE": [], "PAPER": []}
    for m in EQ.finditer(log):
        curves[m[2]].append((m[1], float(m[3])))
    return dict(status=status(), kill=kill, live=live, paper=paper, curves=curves,
                opt_bot=opts("journal_options_paper.csv"), opt_brain=opts("journal_options_brain.csv"),
                opt_flow=opts("journal_options_flow.csv"), opt_fly=opts("journal_options_fly.csv"))

def journal():
    allr = []
    for n in ("live", "paper"):
        for r in rows(f"journal_{n}.csv") or []:
            allr.append(dict(r, acct=n.upper()))
    return sorted(allr, key=lambda r: r.get("t1", ""), reverse=True)

def activity():
    ls = text(P("trader.log"), 600).splitlines()[::-1]
    return dict(lines=ls)

def research():
    return {k: text(P("docs", f"{k}.md")) for k in ("strategy_results", "github_research", "options_research", "intraday_research")} | {"brain_journal": text(P("brain_journal.md"))}

def duel():
    r = rows("docs/options_duel.csv")
    return dict(backtest=r, cols=list(r[0].keys()) if r else [])

IDX_RE, DAY_RE = re.compile(r"^(NIFTY|SENSEX)$"), re.compile(r"^\d{4}-\d\d-\d\d$")
_cache = {}
def cached_rows(f):   # whole-file csv cache keyed on mtime; the OI files are ~75k rows
    mt = os.path.getmtime(f)
    if _cache.get(f, (None,))[0] != mt:
        with open(f, newline="", errors="replace") as fh:
            _cache[f] = (mt, list(csv.DictReader(fh)))
    return _cache[f][1]

def fl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

def chain(q):
    idx = q.get("idx", ["NIFTY"])[0]
    idx = idx if IDX_RE.match(idx) else "NIFTY"
    def expiry(f):
        try:
            return datetime.strptime(os.path.basename(f)[len(idx) + 1:-4], "%d%b%Y")
        except ValueError:
            return datetime.min
    oi_day = {}   # day -> nearest-expiry OI file holding that day
    for f in sorted(glob.glob(P("data", "oi", f"{idx}_*.csv")), key=expiry, reverse=True):
        for d in {r["time"][:10] for r in cached_rows(f)}:
            oi_day[d] = f
    flow_day = {os.path.basename(f)[:10]: f for f in glob.glob(P("data", "flow", f"*_{idx}.csv"))
                if DAY_RE.match(os.path.basename(f)[:10])}
    days = sorted(set(oi_day) | set(flow_day), reverse=True)
    if not days:
        return dict(idx=idx, days=[], day=None)
    day = q.get("day", [days[0]])[0]
    day = day if DAY_RE.match(day) and day in days else days[0]
    fr = [r for r in cached_rows(flow_day[day]) if r["time"][:10] == day] if day in flow_day else []
    src = [r for r in cached_rows(oi_day[day]) if r["time"][:10] == day] if day in oi_day else fr
    src = sorted(src, key=lambda r: r["time"])
    first, last, cur, pcr_s = {}, {}, {}, []
    for i, r in enumerate(src):
        k, v = (int(fl(r["strike"])), r["typ"]), fl(r["oi"])
        first.setdefault(k, v)
        last[k] = cur[k] = v
        if i + 1 == len(src) or src[i + 1]["time"] != r["time"]:
            ce = sum(x for (s, t), x in cur.items() if t == "CE")
            pcr_s.append(dict(t=r["time"][11:16], pcr=round(sum(x for (s, t), x in cur.items() if t == "PE") / ce, 3) if ce else None))
    fl_last, flow_s = {}, []
    for i, r in enumerate(sorted(fr, key=lambda r: r["time"])):
        fl_last[(int(fl(r["strike"])), r["typ"])] = r
    for t in sorted({r["time"] for r in fr}):
        snap = [r for r in fr if r["time"] == t]
        flow_s.append(dict(t=t[11:16], spot=fl(snap[0]["spot"]), buy=sum(fl(r["totbuy"]) for r in snap), sell=sum(fl(r["totsell"]) for r in snap)))
    spot = flow_s[-1]["spot"] if flow_s else None
    if not spot:
        for l in open(P("data", "idx", f"{idx}.csv"), errors="replace"):
            if l.startswith(day):
                spot = fl(l.split(",")[4])
    strikes = sorted({s for s, _ in last})
    pain = {S: sum(v * max(0, S - K) if t == "CE" else v * max(0, K - S) for (K, t), v in last.items()) for S in strikes}
    mp = min(pain, key=pain.get) if pain else None
    near = sorted(sorted(strikes, key=lambda s: abs(s - (spot or mp or 0)))[:31])
    def g(k, t, c):
        r = fl_last.get((k, t))
        return fl(r[c]) if r else None
    rows_ = [dict(k=k, ce=last.get((k, "CE"), 0), pe=last.get((k, "PE"), 0), ce0=first.get((k, "CE"), 0), pe0=first.get((k, "PE"), 0),
                  ce_buy=g(k, "CE", "totbuy"), ce_sell=g(k, "CE", "totsell"), pe_buy=g(k, "PE", "totbuy"), pe_sell=g(k, "PE", "totsell"),
                  ce_ltp=g(k, "CE", "ltp"), pe_ltp=g(k, "PE", "ltp")) for k in near]
    tce, tpe = sum(v for (s, t), v in last.items() if t == "CE"), sum(v for (s, t), v in last.items() if t == "PE")
    tce0, tpe0 = sum(v for (s, t), v in first.items() if t == "CE"), sum(v for (s, t), v in first.items() if t == "PE")
    return dict(idx=idx, day=day, days=days, expiry=os.path.basename(oi_day[day])[len(idx) + 1:-4] if day in oi_day else None,
                spot=spot, strikes=rows_, max_pain=mp, pcr=round(tpe / tce, 3) if tce else None, pcr_series=pcr_s,
                tot_ce=tce, tot_pe=tpe, chg_ce=tce - tce0, chg_pe=tpe - tpe0, flow_series=flow_s, has_flow=bool(fr),
                first_t=src[0]["time"][11:16] if src else None, last_t=src[-1]["time"][11:16] if src else None)

def strategies():
    return dict(duel=rows("docs/options_duel.csv") or [], ideas=rows("docs/options_ideas.csv") or [],
                sell=rows("docs/options_sell.csv") or [], flow=rows("docs/options_flow.csv") or [], results=text(P("docs", "strategy_results.md")))

API = dict(strategies=strategies, overview=overview, journal=journal, activity=activity, schedule=schedule,
           brain=lambda: dict(logs=brain_logs(), journal=text(P("brain_journal.md"))),
           research=research, duel=duel, chain=chain)

class H(BaseHTTPRequestHandler):
    def send(self, code, body, ct):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)
    do_HEAD = lambda self: self.do_GET()
    def do_GET(self):
        if self.headers.get("Host") not in ("127.0.0.1:8001", "localhost:8001"):   # block DNS rebinding
            return self.send(403, "forbidden", "text/plain")
        u = urlsplit(self.path)
        path, q = u.path, parse_qs(u.query)
        if path in ("/", "/index.html"):
            return self.send(200, open(P("dashboard.html")).read(), "text/html; charset=utf-8")
        if path.startswith("/api/") and path[5:] in API:
            try:
                fn = API[path[5:]]
                return self.send(200, json.dumps(fn(q) if fn is chain else fn(), default=str), "application/json")
            except Exception as e:
                return self.send(500, json.dumps(dict(error=str(e))), "application/json")
        self.send(404, "not found", "text/plain")
    do_POST = do_PUT = do_DELETE = lambda self: self.send(405, "read-only", "text/plain")
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8001), H).serve_forever()
