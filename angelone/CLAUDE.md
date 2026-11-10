# angelone-trading

Personal swing-trading bot for Angel One SmartAPI (₹10k capital since 2026-11-05). Zerodha Kite setup lives separately in `~/zerodha-trading`.

## Safety rules (non-negotiable)
- **Paper by default.** Never pass `--live` or place/modify/cancel real orders or GTT rules unless the user explicitly asks in this session.
- **No position without a stop.** If a stop can't be placed, exit the position (trader.py enforces this; don't weaken it).
- Never print or paste `.env` contents (API key, PIN, TOTP secret). `logs/` may contain auth headers — don't share it.
- Never run two API-heavy scripts at once: one shared rate limit (candles 3/s 180/min; holdings/orderbook/search 1/s).
- Algo orders must be LIMIT (Angel bans algo MARKET orders since 1 Apr 2026). Only from the registered static IPv4 (`angel.py` forces IPv4).
- Don't promise returns. Backtests have survivorship bias and exclude 20% STCG tax.

## Files
| File | Purpose |
|---|---|
| `angel.py` | login (PIN+TOTP, auto), `status`, `price SYM`, `candles SYM N`, `order` (dry-run unless `--live`) |
| `trader.py` | the bot: `scan` / `enter` / `check` / `status` `[--live]`. Config constants at top. |
| `backtest.py` | daily-bar engine + `costs()` (Angel delivery: STT 0.1%×2, stamp, exch, DP ₹23.6/sell) |
| `research_bt.py` | rotation / donchian / dip research harness (local CSVs only) |
| `fetch.py` | download candles → `data/day/*.csv` (resumable, backoff). `UNIVERSE` list here. |
| `test_trader.py` | offline asserts for tick rounding, calendar, costs. Run after editing trader.py. |
| `docs/angel_api.md` | SmartAPI reference: limits, params, error codes, GTT, gotchas |
| `docs/edge_cases.md` | settlement, circuits, ASM/GSM, holidays, gaps, rejections, risk rules |
| `docs/strategy_results.md` | backtest results of all strategies tested |
| `state_paper.json` / `state_live.json` | bot state (atomic writes). `journal_*.csv` trade log, `trader.log` run log |
| `dashboard.py` / `dashboard.html` | read-only local dashboard at http://127.0.0.1:8001 (launchd com.harish.dashboard); never imports angel/trader |

## Daily schedule (launchd, weekdays; ~/Library/LaunchAgents/com.harish.*)
| Time | Job | What |
|---|---|---|
| 09:05 | brain PREOPEN (opus) | news check, veto queued buys |
| 09:21 / 15:21 | trader live enter / scan | rules, LIVE (locked until live_test passes) |
| 09:16-15:30 | watcher.py (no LLM) | polls every 60s; wakes brain EVENT on -5% / +8% move, near stop, NIFTY -2%, stop missing (max 4/day) |
| 09:24 / 16:15 | trader paper enter / scan | pure-rules baseline to judge the brain against |
| 09:12-15:31 | options_recorder.py (read-only) | 5-min option chain snapshots NIFTY+SENSEX nearest expiry (ATM+-10: ltp, OI, volume, buy/sell qty) -> data/flow/{date}_{IDX}.csv |
| 09:17 | options_paper.py (PAPER only) | expiry days: 5 players, Rs 30k fake each: BOT (every ORB15 signal), BRAIN (opus 09:31 picks side, sees order flow), FLOW (side from 09:30 OI change), FLY (hedged iron-fly seller), HYBRID (opus picks BUY breakout / SELL fly / SKIP; same prompt as options_hybrid_bt.py). journal_options_{paper,brain,flow,fly,hybrid}.csv. No re-entry. |
| 09:27 Nov 4 | live_test.py | 1-share IDEA live smoke test (one-off) |
| 09:40 | brain VERIFY (sonnet) | live-test outcome, fills, every position has stop |
| 12:35 | brain MIDDAY (sonnet) | news, ratchet stops |
| 15:05 | brain PRECLOSE (opus) | exits / discretionary decision |
| 15:52 | brain POSTCLOSE (opus) | research tomorrow's queue, journal |
Brain = headless `claude -p` via `brain.sh SLOT model`, instructions in `brain_prompt.md`, memory in `brain_journal.md`, logs in `logs/brain/`.
Brain trades only via `trader.py buy|sell|setstop|veto|adjust --live` (stop ≤15% away, risk ≤8% equity, max 2 brain trades/day, setstop ≤80% of highest close, kill switch). Live `enter` waits for `.brain_preopen_done` (till 09:35) so vetoes land first.
Disable everything: `for f in ~/Library/LaunchAgents/com.harish.{trader,brain}.*; do launchctl unload $f; done`

## Strategy (default `STRATEGY="rotation"`)
Month-end: hold top-2 liquid NIFTY-100 stocks by 12-1 momentum (>0), 50% each, 15% hard stop (GTT).
NIFTYBEES < 200DMA → park in NIFTYBEES. Stopped out → cash until month-end.
Backtest 2019-26: ~32%/yr full universe, median 26% on random half-universes, DD -28..-47%. Real expectation lower (survivorship, tax).
Benchmark to beat: NIFTYBEES buy & hold 11.6%/yr, DD -36%. Rejected: RSI2, 20d breakout, dip-buy, intraday, F&O.

## Yearly / periodic maintenance
- December: update `HOLIDAYS` + `CALENDAR_UNTIL` in trader.py from NSE circular (bot fails closed after the date).
- Refresh `data/scripmaster.json` monthly (tokens/ticks) and `fetch.UNIVERSE` when NIFTY 100 rebalances.
- Unverified until live_test passes (it asserts each + saves raw payloads in docs/live_test_result.json): GTT status strings (`GTT_*` sets), GTT on same-day buys, `ordertag` in orderBook, holdings `quantity` vs `t1quantity`.
- Bot capital is isolated: `state_live.json` `cash` (starts 5000) is the bot's money; user's own cash/holdings never count. Bot never buys a symbol the user holds.
- Splits/bonus: Angel candles are adjusted, but live GTT prices aren't → `trader.py adjust SYM RATIO --live` before ex-date (brain PREOPEN checks).
- One Angel session/day shared via `.session.json` (0600) - never add code that logs in per call. SDK bug: hardcoded X-ClientPublicIP, patched in `angel._fix_ip`. SDK bug 2: GTT create/modify/cancel routes have bogus `/gtt-service` prefix ("no Route matched"), also patched there. Angel holdings already include same-day buys/sells - never add position netqty.
- Brain runs with `--permission-mode dontAsk` + allowlist in brain.sh (no raw shell, no .env, no editing brain.sh/run.sh/brain_prompt.md/LaunchAgents). Brain buys only from `state.candidates` (top-10 momentum) or NIFTYBEES.
- `ANGEL_STATIC_IP` in .env must match the IP registered at Angel; bot refuses orders/GTT if public IP differs.
- Known gaps: stop limit is 2% below trigger (a bigger gap leaves it unfilled → reconcile sells next run); brain has shell access, so code rails are defense-in-depth, not a sandbox.
