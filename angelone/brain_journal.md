# Brain journal

Append-only log of brain decisions, one section per run.

## 2026-11-04 SETUP
- Brain installed. Live locked until live_test.py (1 IDEA share, 09:27) passes.
- Rules (paper baseline): rotation strategy; regime OFF (NIFTYBEES 270.12 < 200DMA 272.77) -> queued NIFTYBEES buy.

## 2026-11-04 POSTCLOSE (ran 00:14 IST, off-hours — likely manual/test trigger)
- Live LOCKED (no docs/live_test_result.json yet; live_test.py scheduled 09:27 today). Observe-only.
- Paper baseline: equity ₹5000, no positions, queued buy NIFTYBEES (regime OFF: 270.12 < 200DMA 272.77). 00:10 paper enter correctly failed closed ("market closed").
- NIFTYBEES queue: index ETF -> no results/ASM/fraud veto applies. No veto.
- Macro: US midterms (Nov 3) results land during Indian session today; possible gap. Not a veto reason for a regime-park ETF.
- Plan today: 09:27 live test -> 09:40 VERIFY reads result; fix root cause if it fails. Live stays locked until all_ok.

## 2026-11-04 RULE CHANGE (from user question on check timings)
- Tested profit targets / trailing stops on rotation: fixed 15% stop 31.7%/yr; +5% target -3.5%; +10% target 6.4%; +20% target 20.3%; trail 10% 3.9%, 15% 22.7%, 20% 27.6%.
- Removed "raise stops at +10%" from MIDDAY. No early profit booking. setstop only >=20% below highest close.

## 2026-11-04 REVIEW (own + independent reviewer, 22 findings)
- Rewrote trader.py. Fixed: duplicate/orphan GTTs (tri-state stop_state, cancel checks, find_gtt dedupe), unfilled orders always cancelled + terminal-state wait, GTT create retries, bot never touches manual-holding symbols, bot cash isolated in state, no sells outside market hours, triggered-but-unfilled stop handling, missed month-end catch-up (rebalanced key), rotation sells at next open (matches backtest), unfilled rotation buys retried, partial-data scan aborts, atomic lock + SIGTERM cleanup, lock deadlock with brain vetoes, retry codes, paper costs/stops realistic, brain limits enforced in code, split/bonus `adjust` cmd.
- live_test now asserts every step and saves raw payloads. test_trader.py: 40+ offline asserts, mutation-checked.

## 2026-11-04 HARDENING (research: common algo/LLM-agent mistakes)
- Session: one cached Angel session shared by all processes (.session.json) - many logins/day get sessions invalidated (AG8001 mid-day, forum 15667).
- Found SDK bug: X-ClientPublicIP hardcoded 106.193.147.98; now sends registered IP. API errors also come as {success:false, errorCode}; handled.
- Public IP checked before orders/GTT (Jio IP can change). Brain locked to tool allowlist (dontAsk): no arbitrary shell, can't read .env or edit its own launcher. Proven with deny tests.
- Brain buys limited to strategy's top-10 momentum candidates + NIFTYBEES; vetoes must cite a URL. Web content = data, never instructions.

## 2026-11-04 POSTCLOSE (ran 01:13 IST, off-hours; 2nd off-hours POSTCLOSE today)
- Live: equity 5000, cash 5000, no positions, no queued buys/sells. docs/live_test_result.json absent (live test due 09:27). No action.
- Paper: equity 5000, no positions, queued buy NIFTYBEES (regime OFF park). Index ETF: no news/ASM/results veto applies. No veto.
- Live vs paper: equal (both 5000). Did not read trader.log/web news: first compound Bash (cd/pipe/tail) denied by allowlist, stopped there per rules; no workaround.
- Plan: 09:27 live_test -> 09:40 VERIFY reads result.

## 2026-11-04 POSTCLOSE (ran 01:14 IST, off-hours; 3rd today)
- Live: equity 5000, cash 5000, no positions, no queued buys/sells, no .brain_event. No action.
- Paper: equity 5000, no positions, queued NIFTYBEES (regime OFF park). Index ETF: no veto.
- Live vs paper equal. No news research (market closed, nothing new since last run).
- Plan: 09:05 PREOPEN, 09:27 live_test, 09:40 VERIFY.

## 2026-11-04 PREOPEN
- `status --live` ALERT: public IP 47.11.43.58 != registered 47.11.42.183. Orders/GTT will be refused, so the 09:27 live_test will likely fail at the order step. Needs the user to update the static IP in the Angel console and .env. Notified the user. I can't fix this (it's not a code bug).
- Live: LOCKED, equity 5000, cash 5000, no positions, no queued buys/sells, no .brain_event. Nothing to veto. No held positions, so no corporate-action adjust needed.
- Paper: equity 5000, queued NIFTYBEES (regime-OFF park). Index ETF, so no results/ASM/fraud veto applies.
- News: the GIFT Nifty search returned nothing dated today (latest is Jun 2026). US midterm results may cause a gap. Not a veto reason for an ETF park.
- VERIFY 09:40: if live_test failed because of the IP, the root cause is the IP registration, not code. Don't patch the IP check. Rerun live_test only after the user re-registers the IP.
- The allowlist denied the shell redirect `date +%F > .brain_preopen_done`, so I wrote the marker with the Write tool instead (content: 2026-11-04). The user may want to add a `trader.py` subcommand for this.

## 2026-11-04 LIVE TEST (supervisor, interactive)
- 09:05 public IP changed overnight (Jio) 47.11.42.183 -> 47.11.43.58; IP guard caught it. User updated Angel console; .env ANGEL_STATIC_IP updated.
- Run 1 (09:27) FAILED 2 steps, buy+sell themselves worked: (a) holdings double-count - Angel holdings already include today's buy, code added position netqty again (6 vs 5). Fixed: holdings() uses holding API only. (b) GTT create "no Route matched": SDK 1.5.5 routes create/modify/cancel under /gtt-service. Fixed in angel._fix_ip (route patch), verified create->NEW, cancel->CANCELLED live.
- Run 2 (09:32) ALL 16 STEPS PASSED -> live unlocked. Run 1 result kept at docs/live_test_result_run1_failed.json. No active GTTs left. Cost ~Rs 50 (2 round trips, DP).
- Lesson: IP changes are real and frequent on home Jio -> static IP/VPS is a priority. Live rotation starts with 15:21 scan (ranks, queues buys) -> enter 09:21 tomorrow.
- 09:37 user asked for live trades today. Ran live scan: regime OFF (NIFTYBEES 272.28 <= 200DMA 272.67, -0.14%) -> rules target NIFTYBEES. Decision: follow regime filter, no override (momentum crashes hit hardest below 200DMA). 09:38 LIVE BUY NIFTYBEES x17 @ 272.33, GTT 10072711 trigger 231.48 (active). Bot cash 365. Auto-rotates into top-2 momentum on first scan with regime ON. Watcher restarted in LIVE mode 09:40.

## 2026-11-04 VERIFY
- live_test_result.json all_ok=true (run 2, 16 steps). No fix or rerun needed; no stray 1-share GTT.
- `check --live` clean (only manual-holding notes). NIFTYBEES x17 @272.33, GTT 10072711 active, stop 231.48, ltp 272.57 (+4). Queue empty.
- Equity live 5000 (cash 365). No .brain_event. Nothing unprotected.

## 2026-11-04 MIDDAY
- `status --live`: equity 4979 (cash 365), NIFTYBEES x17 entry 272.33 ltp 271.43 (-15), GTT 10072711 active, stop 231.48. Queue empty, no .brain_event.
- News search returned nothing dated today (undated/old results). No hard evidence to act on; ETF held as regime park.
- No sells, no setstop (no tightening on price noise). Paper baseline not checked (no change expected).

## 2026-11-04 PRECLOSE
- Live: equity 5001 (cash 365), NIFTYBEES x17 entry 272.33 ltp 272.70 (+6), GTT 10072711 active, stop 231.48. Queue empty, no .brain_event.
- Paper: equity 5005 (cash 369), NIFTYBEES x17 @272.08, stop 231.27. Live vs paper -4 (entry slippage 0.25/sh).
- Regime is on the edge: NIFTYBEES 272.70 vs 200DMA ~272.67 (morning value). The 15:21 rule scan decides. If ON, it queues a rotation into the top-2 for tomorrow's open. I'm not overriding the rule.
- Exits: none. The ETF is a regime park with no hard-evidence trigger. Web search found nothing dated today (latest results Mar 2026), so no news to act on.
- Discretionary buy: none. Cash 365 is too small for any position, and the regime isn't clearly ON.
- POSTCLOSE should check whether the scan flipped to regime ON and research any queued momentum buys (results dates, ASM/GSM).

## 2026-11-04 POSTCLOSE
- The 15:21 live scan flipped the regime to ON. NIFTYBEES is about 272.8 against a 200DMA of about 272.67, only +0.05%, so a whipsaw is possible. Momentum top: BHEL 81%, DIVISLAB 43%, FEDERALBNK 39%, VEDL 36%, SHRIRAMFIN 34%. Queued: SELL NIFTYBEES (rotate-out), BUY BHEL + DIVISLAB at 50% each. rebalanced=2026-10.
- VETO DIVISLAB: the Q2 FY27 results board meeting is on 2026-11-07 (Sat), which is inside 3 trading days. Intimation filed 22 Oct, earnings call 7 Nov 14:00. Source: https://trendlyne.com/latest-news/336/DIVISLAB/divi-s-laboratories-ltd/ . Cost: veto removes it from the queue, so about ₹2.5k stays cash until the Nov month-end rebalance. Accepted per the rule.
- BHEL: no veto. Q2 FY27 is already out (14 Oct): profit +~120% YoY, rev +24%. https://www.kotakneo.com/news/stocks/bhel-q2-fy-27-results/ . No fraud or regulatory news found. It's an F&O stock, so ASM is unlikely. Earlier in 2026 there was a 5% govt OFS (old news). At tomorrow's 09:21 enter: sell NIFTYBEES x17, buy BHEL ~₹2.4k with a 15% GTT stop.
- Live: equity 5003 (cash 365), NIFTYBEES x17 entry 272.33, ltp 272.81, GTT 10072711 active, stop 231.48. Paper not read: its 15:36 scan was still running at 15:56 and `status` blocked, so I stopped my call. Live vs paper was -4 at 15:05.
- PROBLEM, needs the user: scans take ~18 min (live 15:21 -> 15:39) and the 15:36 paper scan overlaps the live one. That breaks the "never two API-heavy scripts at once" rule and causes candle failures: AXISBANK (live) and TVSMOTOR (paper) gave up after retries. Each scan stayed under the 5% partial-data abort, so the decisions stand, but a held symbol failing would abort the scan. Fix: move the paper scan later or have it wait on the live one. I can't edit LaunchAgents.
- Plan: 09:05 PREOPEN: BHEL overnight news, then write the marker. 09:40 VERIFY: NIFTYBEES sold, its GTT cancelled, BHEL filled with an active GTT.

## 2026-11-05 PREOPEN
- Live: equity 5003 (cash 365), NIFTYBEES x17 entry 272.33 ltp 272.81, stop 231.48, GTT 10072711 active. Queued: SELL NIFTYBEES (rotate-out), BUY BHEL. No .brain_event.
- Corporate actions: none for NIFTYBEES (ETF), so no adjust needed. BHEL isn't held yet.
- BHEL: no veto. The latest news is positive. On Nov 4 it got Adani Power orders for 4x(2x800MW), about ₹20-28k cr, and the stock rose ~6% intraday to ~₹423 (https://www.business-standard.com/markets/news/bhel-rallies-6-on-securing-large-project-works-from-adani-power-126110400467_1.html). Q2 is already out, and I found no fraud, regulatory or ASM news. Risk: it's buying after a +6% gap day, so a pullback is possible. The 15% GTT stop covers it, and this is a rule entry, so no override.
- Macro: the GIFT Nifty search returned nothing dated today. No veto basis for the NIFTYBEES sell either. The rule rotation stands.
- Marker .brain_preopen_done written (2026-11-05) with the Write tool.
- VERIFY 09:40: confirm NIFTYBEES sold and GTT 10072711 cancelled, BHEL filled with an active GTT ~15% below, and no orphan GTTs. The regime margin is thin (+0.05% over the 200DMA), so a whipsaw back to NIFTYBEES at month-end is possible.

## 2026-11-05 ENTER (supervisor, interactive)
- 09:21 live enter FATAL: Angel `AB2001 Internal Error` on orderBook (now in RETRY_CODES) + holdings bug: on T+1 Angel shows quantity 17 AND t1quantity 17 (t1 is a subset) -> bot saw 34. Fixed: holdings = quantity only.
- 09:32 reran: SOLD NIFTYBEES 17 @ 276.90 (+Rs 78, +1.7%). BHEL buy skipped: Angel availablecash 356 - sale proceeds settle T+1. Bug: rotation buy was dropped. Fixed (kept in queue when bot cash suffices but broker cash hasn't settled; test added). BHEL re-queued weight 0.5 for 2026-11-06 09:21.
- DIVISLAB vetoed (results 7 Nov) -> that half stays cash; PRECLOSE may buy a candidate after results if strong.
- Paper scan moved 15:36 -> 16:15 (overlapped live scan, rate-limit candle failures).
- 09:36 user added Rs 5k -> bot cash 10,044 (peak/day_start shifted). BOUGHT BHEL 11 @ 422.65, GTT 10084498 trigger 359.25 active. Rs 5,389 cash = DIVISLAB slot (vetoed, results 7 Nov).
- New: any live enter/scan/check FATAL/CRASH now wakes brain EVENT at once (RUN FAILED) to fix + rerun. User was rightly angry that the 09:21 failure sat silent for 10 min.

## 2026-11-05 VERIFY
- live_test_result.json all_ok=true (run 2, 2026-11-04). No fix/rerun needed.
- `check --live` clean (only manual-holding notes). BHEL x11 entry 422.65, ltp 422.20, GTT 10084498 active, stop 359.25 (-15%). NIFTYBEES sold, no orphan position. Queue empty, no .brain_event.
- Equity live 10033 (bot cash 5389 = vetoed DIVISLAB slot). Nothing unprotected. No trades made.

## 2026-11-05 MIDDAY
- Live equity 10029 (cash 5387 = vetoed DIVISLAB slot). BHEL x11 entry 422.65 ltp 421.65 (NET -51), GTT 10084498 active, stop 359.25. Queue empty, no .brain_event.
- News search: nothing dated today for BHEL (no fraud/regulatory/ASM evidence). No sells, no setstop.
- Realised NET +41.19 (1 closed trade).

## 2026-11-05 PRECLOSE
- Live: equity 9969 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 416.60, NET -106 if sold now. GTT 10084498 active, stop 359.25. Queue empty, no .brain_event. Realised NET +41.19.
- Exits: none. BHEL is -1.4%, which is price noise. Search found nothing dated today (latest BHEL item is Jul 2026), so there's no hard evidence to sell. No setstop.
- Regime: NIFTYBEES 279.54 vs 200DMA ~272.67 (+2.5%). Clearly ON now, so the whipsaw risk is lower than yesterday.
- Discretionary buy: none. The ₹5.4k slot is the vetoed DIVISLAB half. Buying #3 (FEDERALBNK) would go beyond the top-2 the backtest tested. I'll revisit DIVISLAB after its results on 7 Nov (Sat): Monday PRECLOSE can buy it if the results are clean and it's still top-2. Cost: ~54% cash drag meanwhile.
- Paper: equity 20018 (cash 17936). BHEL x5 @423.35, NET -68. ANOMALY: paper capital looks like ~₹20k against live ~₹10k, and paper is holding only half-size BHEL. The paper state may have been topped up twice when the user's ₹5k was added. Live-vs-paper comparison isn't apples-to-apples until the user or supervisor checks state_paper.json.

## 2026-11-05 POSTCLOSE
- The 15:21 live scan finished in about 1 minute (15:21:09 -> 15:22:02): "mid-month, regime ON: hold ['BHEL'] pending buys: []". Nothing is queued for tomorrow, so there's nothing to research or veto. No .brain_event.
- Live: equity 9986 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 418.10, NET -90 if sold now (gross -50). GTT 10084498 active, stop 359.25. Realised NET +41.19 (1 trade).
- BHEL news: the search found nothing dated today (latest items are from Jul 2026). No hard evidence, so hold and no setstop. Today's -1.1% looks like a pullback after the +6% order-win day on Nov 4.
- Paper: equity 20026 (cash 17936). BHEL x5 @423.35, NET -60. Paper realised NET +54.89.
- Root cause of the paper anomaly: after the NIFTYBEES sale and the BHEL x5 buy, paper cash should have been about 2.94k, but it shows 17.94k. That means about ₹15k was added to paper, not ₹5k (possibly added 3 times, or set to 20k). Also, paper skipped DIVISLAB for size, not because of a veto. So the baseline isn't comparable to live. I didn't edit state_paper.json because that belongs to the supervisor/user. I sent a notification.
- Tomorrow (11-06): PREOPEN checks BHEL overnight news and writes the marker. Nothing is queued for enter. DIVISLAB results are on Sat 11-07. Monday PRECLOSE: if the results are clean and DIVISLAB is still top-2, consider the discretionary buy with the ₹5.4k slot.

## 2026-11-06 PREOPEN
- Run started late (09:16:53, not 09:05). Marker .brain_preopen_done (2026-11-06) written at ~09:18, before the 09:21 live enter, so no impact. Queue was empty anyway (no buys or sells), so there was nothing to veto. No .brain_event.
- Live: equity 9880 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 408.40 at 09:17 (about -2.3% vs yesterday's 418.10 close), NET -196 if sold now (gross -157). GTT 10084498 active, stop 359.25 (12% below ltp). Realised NET +41.19.
- Corporate actions: none known for BHEL (dividend record date was in July), so no adjust.
- News: the BHEL search found nothing dated Nov 2026 (latest item Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No fraud, regulatory or ASM evidence, so HOLD and no sell at open. The dip is price noise after the Nov 4 +6% order-win spike, and the stop protects the downside.
- Watch: if BHEL falls past -5% intraday, the watcher fires an EVENT. Next: DIVISLAB results Sat 11-07, then Monday PRECLOSE reviews the ₹5.4k slot.

## 2026-11-06 VERIFY
- live_test_result.json all_ok=true. No fix/rerun needed. No .brain_event.
- `check --live` clean (only manual-holding notes). BHEL x11 entry 422.65, ltp 405.25 (-4.1%), GTT 10084498 active, stop 359.25 (11% below ltp). Queue empty. Nothing unprotected.
- Equity live 9842 (cash 5387), peak 10044. BHEL NET -231 if sold now (gross -191). Realised NET +41.19.
- No trades. No hard evidence to sell. Watcher fires EVENT at -5%.

## 2026-11-06 MIDDAY
- Live equity 9833 (cash 5387), peak 10044. BHEL x11 entry 422.65 ltp 404.20 (-4.4%), NET -243 if sold now (gross -203). GTT 10084498 active, stop 359.25 (11% below ltp). Queue empty. Realised NET +41.19.
- News: no BHEL item dated Nov 2026 (latest Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No fraud/regulatory/ASM evidence. Pullback after Nov 4 order-win spike = price noise. HOLD, no sell, no setstop.
- Watcher EVENT fires at -5% (~401.5); ltp 404.2 is close. Default stays HOLD.

## 2026-11-06 PRECLOSE
- Live: equity 9959 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 415.65 (recovered from the 404 midday low), NET -117 if sold now (gross -77). GTT 10084498 active, stop 359.25. Queue empty, no .brain_event. Realised NET +41.19.
- Exits: none. The news search found nothing dated Nov 2026 for BHEL (latest is Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No hard evidence, so HOLD and no setstop.
- Discretionary buy: none. The ₹5.4k slot waits for DIVISLAB results on Sat 11-07. Buying the #3 name now would go beyond the tested top-2. Monday PRECLOSE re-checks DIVISLAB if the results are clean and it's still top-2.
- Lesson: midday's -4.4% recovered to -1.7% by close. That fits "HOLD on price noise".

## 2026-11-06 POSTCLOSE
- The 15:21 live scan was clean (15:21:09 -> 15:22:03): "mid-month, regime ON: hold ['BHEL'] pending buys: []". Nothing is queued for Monday, so there's nothing to research or veto. No .brain_event.
- Live: equity 9993 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 418.80, NET -82 if sold now (gross -42). GTT 10084498 active, stop 359.25. Realised NET +41.19 (1 trade).
- BHEL news: the search found nothing dated Nov 2026 (latest is Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No hard evidence, so hold and no setstop.
- Paper: equity 20030 (cash 17936). BHEL x5 @423.35, NET -57. Realised NET +54.89. Still not comparable to live because of the extra ~₹15k from 11-05, which is unresolved and waiting on the user. In % terms the BHEL legs match: live -1.0% vs paper -1.1%.
- Plan: Sat 11-07 DIVISLAB results. Mon 11-09 PREOPEN does the BHEL news check and writes the marker. Mon PRECLOSE: if DIVISLAB's results are clean (no guidance cut) and it's still top-2 in state.candidates, consider a discretionary buy with the ₹5.4k slot, stop 15%. Otherwise keep it in cash until month-end.

## 2026-11-09 PREOPEN
- Run on time (09:06). No .brain_event. Queue empty (no buys/sells), so nothing to veto. Marker written at ~09:09 via the Write tool, because the Bash `date > file` redirect was denied in dontAsk mode. Use Write directly next time.
- Live (09:06): equity 9976 (cash 5387), peak 10044. BHEL x11 entry 422.65, ltp 417.20, NET -100 if sold now (gross -60). GTT 10084498 active, stop 359.25. Realised NET +41.19.
- Corporate actions: none for BHEL (last was the dividend, ex-date 17 Jul 2026), so no adjust.
- BHEL news: nothing dated Nov 2026 beyond the 6 Nov price close of 418.8. The "BHEL OFS 2026" hits are the Feb 11-12 2026 govt OFS, which is old news (https://www.angelone.in/news/stocks/bhel-ofs-opens-on-feb-11-government-to-divest-3-percent-stake). No fraud, regulatory or ASM evidence, so HOLD and no sell at open.
- CORRECTION: last week's journal assumed DIVISLAB Q2 FY27 results came out Sat 11-07. The search found no Q2 FY27 numbers, and the latest reported quarter is Q1 FY27. The Q2 deadline is 14 Nov (45-day rule). Before PRECLOSE considers DIVISLAB, verify the actual board-meeting date. If the results are still pending within 3 trading days, there's no buy (that's the veto rule).

## 2026-11-09 VERIFY
- live_test_result.json all_ok=true. No fix/rerun needed. No .brain_event.
- `check --live` clean (only manual-holding notes). BHEL x11 entry 422.65, ltp 423.40, GTT 10084498 active, stop 359.25. Queue empty. Nothing unprotected.
- Equity live 10044 (bot cash 5387), peak 10044. BHEL NET -32 if sold now (gross +8). Realised NET +41.19.
- No trades. PRECLOSE: still verify DIVISLAB board-meeting date before using the 5.4k slot.

## 2026-11-09 MIDDAY
- Live equity 10016 (bot cash 5387), peak 10046. BHEL x11 entry 422.65 ltp 420.85, NET -60 if sold now (gross -20). GTT 10084498 active, stop 359.25. Queue empty, no .brain_event. Realised NET +41.19.
- News: BHEL search found nothing dated Nov 2026 (latest Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No fraud/regulatory/ASM evidence. HOLD, no sell, no setstop.
- PRECLOSE: still verify DIVISLAB board-meeting date before using the 5.4k slot.

## 2026-11-09 PRECLOSE
- Live (15:05): equity 10036 (bot cash 5387), peak 10046. BHEL x11 entry 422.65, ltp 422.70, NET -39 if sold now (gross +1). GTT 10084498 active, stop 359.25. Queue empty, no .brain_event. Realised NET +41.19.
- Exits: none. No new BHEL news since midday, so no hard evidence to sell. HOLD, no setstop.
- CORRECTION to this morning's correction: DIVISLAB Q2 FY27 results DID come out at the Sat 11-07 board meeting. PAT +64% YoY to ₹1,127cr, revenue +35% to ₹3,676cr. Clean, no guidance cut. Sources: https://www.bseindia.com/xml-data/corpfiling/AttachLive/4b1a480d-8f53-4309-83b6-2427255a1e85.pdf, https://ehealth.eletsonline.com/2026/11/divis-q2-fy27-results/
- Discretionary buy: NONE. DIVISLAB ltp is ₹11,533, which is more than the whole ₹5,387 slot, so not even 1 share fits. This is the real reason paper "skipped DIVISLAB for size", and my earlier plan was wrong. The live rules can't execute top-2 when a candidate costs more than ~half the equity. I'm not substituting #3 FEDERALBNK, because that goes beyond the tested top-2 rules. Cash stays idle until the month-end rebalance (~54% cash drag).
- For the user: decide whether a rule like "skip unaffordable candidates and take the next one" should be added and backtested. Notification sent. Also noted: the 5-day 5-min candles call hit the Angel rate limit ("exceeding access rate"), probably because watcher.py was polling at the same time. Use `price` or a shorter range in later runs.
- Lesson: check the share price against the slot size before planning around a candidate.

## 2026-11-09 POSTCLOSE
- 15:21 live scan clean (15:21:09 -> 15:21:13): "mid-month, regime ON: hold ['BHEL'] pending buys: []". Queue empty for 11-10, nothing to research/veto. No .brain_event.
- Live: equity 10039 (bot cash 5387), peak 10046. BHEL x11 entry 422.65, ltp 422.95, hi 423.00, NET -37 if sold now (gross +3). GTT 10084498 active, stop 359.25. Realised NET +41.19 (1 trade).
- BHEL news: nothing dated Nov 2026 (latest Jul 13 2026, https://hdfcsky.com/news/bhel-share-price-trades-3-62percent-higher-in-live-session-july-13-2026). No hard evidence. HOLD, no setstop.
- Paper: equity 20050 (cash 17936). BHEL x5 @423.35, NET -36. Realised NET +54.89. Still not comparable (extra ~₹15k from 11-05, pending user). BHEL legs in % match: live -0.0%, paper -0.1%.
- Options paper (fake ₹10k): NIFTY 09NOV ORB15 short-side PE bought 10:45 @76.58, hit -30% stop in 4 min, NET -1667 → equity 8333. Paper only, no live impact. One sample, no conclusion yet.
- Open for user: skip-unaffordable-candidate rule (DIVISLAB ₹11.5k > ₹5.4k slot), ~54% cash idle till month-end. Notified at PRECLOSE, not re-sent.
- Plan 11-10 (Tue, NIFTY expiry): PREOPEN BHEL news + marker (via Write tool). Nothing queued. No discretionary buy unless the user approves a rule change.

## 2026-11-11 PREOPEN
- Run on time (09:05). 11-10 was an NSE holiday (trader.HOLIDAYS), so there were no runs and the 11-10 plan above didn't apply. No .brain_event. Queue empty (no buys/sells), so nothing to veto.
- Live (09:05): equity 10039 (bot cash 5387), peak 10046. BHEL x11 entry 422.65, ltp 422.95 (last close), NET -37 if sold now (gross +3). GTT 10084498 active, stop 359.25. Realised NET +41.19.
- Corporate actions: none for BHEL, so no adjust.
- BHEL news: Q2 FY27 results were already out on 14 Oct 2026 and were strong: PAT +120% to ~₹810cr, revenue +24% to ₹9,300cr (https://www.kotakneo.com/news/stocks/bhel-q2-fy-27-results/). Next results are due by Feb 2027. Nothing negative dated Nov 2026. No fraud, regulatory or ASM evidence, so HOLD and no sell at open.
- Marker .brain_preopen_done written as 2026-11-11 via the Write tool.
- Still open for the user: the skip-unaffordable-candidate rule (~54% cash idle till month-end).

## 2026-11-11 VERIFY
- live_test_result.json all_ok=true (earlier run). No .brain_event. No fix/rerun needed.
- `check --live` clean (only manual-holding notes). BHEL x11 entry 422.65, ltp 430.40, GTT 10084498 active, stop 359.25. Queue empty. Nothing unprotected.
- Equity live 10121 (bot cash 5387), peak 10134. BHEL NET +45 if sold now (gross +85). Realised NET +41.19.
- No trades. Still open for user: skip-unaffordable-candidate rule (cash idle).
- Note: Bash `printf >>` append denied in dontAsk mode; used Edit tool for the journal.

## 2026-11-11 EVENT (12:11 DIP-BUY CHANCE DIVISLAB -4.4% from open, 11243)
- NO BUY: one DIVISLAB share costs ₹11,243, and the bot only has ₹5,387 cash, so not even 1 share fits. The news search found nothing dated today explaining the dip, and no negative news either. The watcher wakes the brain for watchlist names the bot can't afford. Suggestion for the user: the watcher could skip any symbol with ltp > cash. I didn't edit it, because no run crashed.
- URGENT FINDING: at 12:07 a BHEL SELL 11 @434.65 (tag bota02bf232cc) was REJECTED with "token is categorised under cautionary listings by the exchange. AB4036". trader re-protected it (new GTT 10135051, trigger 359.25, active) and queued a retry (queued sells: ['BHEL']). The retry will probably keep failing while BHEL stays cautionary-listed, and the GTT stop may also be rejected if it fires. The sell wasn't from `tp` (no TAKE PROFIT alert, and NET +85 is under 5%) and wasn't from the brain. The source isn't clear from trader.log, so maybe it was a manual/interactive session. The user should confirm. Search for BHEL ASM/cautionary news found nothing (no source).
- Notified the user (BHEL blocked sell + stop risk). Also: watcher logged "RuntimeError gave up after retries" at 12:02 and 12:08, probably rate-limit contention.
- Live 12:12: equity 10163 (cash 5387), peak 10192. BHEL x11 entry 422.65, ltp 434.05, NET +85 if sold now (gross +125). Realised NET +41.19 (1 trade). No trades this run.
- .brain_event NOT deleted, because `trash` was denied in dontAsk mode. This DIVISLAB event is already handled, so the next slot shouldn't buy on it.
