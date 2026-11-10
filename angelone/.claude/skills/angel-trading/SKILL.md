---
name: angel-trading
description: Run, check, backtest or modify the Angel One swing-trading bot in ~/angelone-trading (paper or live). Use when the user asks to trade, scan for signals, check positions/stops/funds, run the daily bot, backtest a strategy, or change trading rules for their Angel One / Zerodha account.
---

# Angel trading bot

Read `CLAUDE.md` in this repo first; its safety rules override everything here.

## Routine actions
```bash
cd ~/angelone-trading
.venv/bin/python trader.py status            # paper state, equity, positions, stops
.venv/bin/python trader.py scan              # 15:20 IST or after close
.venv/bin/python trader.py enter             # 09:20-10:00 IST
.venv/bin/python trader.py check             # reconcile + stops + kill switch
.venv/bin/python angel.py status             # real broker funds + holdings (read-only)
```
Add `--live` ONLY when the user explicitly asks for real orders in the current session. Before the first live run, confirm: static IP still matches (`curl -4 api.ipify.org` vs registered), funds, and that they accept the risk.

## When the user asks...
- "should I buy X / what to trade today": run `scan` (paper), report signals + regime + stops. Never recommend trading without a stop or outside the strategy.
- "backtest Y": add to `research_bt.py` or `backtest.STRATEGIES`, report IS (2019-22) vs OOS (2023-26), compare to NIFTYBEES B&H, use `backtest.costs()`. Flag survivorship bias.
- "change risk/stop": edit constants at top of `trader.py`, then run `test_trader.py`.
- API error: check `docs/angel_api.md` (codes, limits) and `docs/edge_cases.md`. Rate limit text: `Access denied because of exceeding access rate` → backoff, don't hammer.

## Long runs
`fetch.py` and `scan` take minutes (rate limits): run in background, notify on finish.
