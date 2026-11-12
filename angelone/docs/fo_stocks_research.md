# Indian stock F&O options: practical rulebook (as of 2026-11-11)

Confidence tags: [V] verified from a fetched/search-returned source, [S] secondary/news source only, [U] unverified or practitioner knowledge, check before relying on it. Primary SEBI/NSE documents were NOT read directly in this pass (search snippets and broker pages only); verify anything that drives money.

## 1. Mechanics

**Expiry.** NSE monthly stock and index F&O expire on the **last Tuesday** of the month (previous trading day if holiday) since Sept 2025; BSE (Sensex/Bankex) on Thursday. [V] Angel One piece on 27 Oct 2026 expiry: https://www.angelone.in/news/market-updates/nifty-monthly-expiry-today-ambuja-cements-kaynes-and-sail-under-f-o-ban-on-october-27-2026. Next: Tue 24 Nov 2026 (one site listing 23 Nov looks wrong). Stock options are MONTHLY only (no weekly), so "near month" = the only liquid series; after expiry the next series becomes near month.
Note: Angel's settlement page still says "last Thursday" in the margin section; stale text.

**Universe.** 213 stocks have F&O as of 21 Oct 2026 [S] (https://www.angelone.in/news/market-updates/nifty-monthly-expiry-today-ambuja-cements-kaynes-and-sail-under-f-o-ban-on-october-27-2026 search summary). Entry criteria (NSE selection-criteria page https://www.nseindia.com/static/products-services/equity-derivatives-selection-criteria): average daily market cap, traded value, quarter-sigma order size, **MWPL >= Rs 1,500 cr** (raised from 500) and average daily delivery value >= Rs 35 cr (raised from 10) after SEBI's Aug 2024 circular [S]. Exit: fails criteria 3 continuous months; excluded stocks cannot re-enter for 1 year [S]. Recent changes: Swiggy, Waaree Energies, Premier Energies, Bajaj Holdings added 31 Dec 2025 [S]; Exide, Nuvama removed (effective ~29 Jul 2026, date uncertain) [S]; Piramal Ent, Hindustan Copper, MGL etc. removed Aug 2025 [S]. Practical consequence: the universe churns; rebuild it from NSE files daily, never hardcode.

**Lot size.** SEBI minimum contract value: Rs 15 lakh (band 15-20 lakh) for NEW INDEX contracts since Nov 2024 [V]; Nifty lot 75 -> 65 from Jan 2026 series [S]. For stocks, one unverified source claims lots were re-set to ~Rs 7.5 lakh contract value [U] and another cites a SEBI 2026 circular effective 1 May 2026 that I could not confirm [U]. Observed stock lot range: PAGEIND 20 to IDEA 71,475 [S]. Lots are revised by NSE semi-annually; always read the lot from the live scrip master / NSE `fo_mktlots`, never cache for months.

**Physical settlement.** Mandatory for all stock F&O since April 2018 [V]. ITM options held to expiry become delivery: long call must pay strike x qty, long put must deliver shares (short sale risk if you have none -> auction penalty) [V] (https://www.angelone.in/knowledge-center/derivatives/settlement-procedure). Angel's expiry-week margin ramp for LONG ITM options (percent of delivery margin): E-4 10%, E-3 25%, E-2 45%, E-1 70%, expiry day 100% [V, same page]; futures/short ITM 40% of contract value on expiry day. Consequence for a Rs 30k paper/real account: **a small account cannot hold a stock option ITM into expiry week**; the margin ramp alone forces exit. Broker practice elsewhere: Upstox squares off after 12:00 on expiry day without consent and may also square off 3 OTM strikes; Fyers squares off near-month positions on any shortfall [S]. Angel's exact auto-square-off clock time is NOT published on the page I read [U]: assume ~E-1 afternoon to expiry-day 12-14:00 and exit by E-2 on our own.

**STT.** From 1 Apr 2026 STT on option premium (sell side) is **0.15%** (was 0.1%); futures 0.05% [V] (https://www.angelone.in/news/market-updates/stt-hike-on-f-o-trade-effective-today-april-1-check-revised-stt-on-nifty-50-lot). STT on exercise/ITM-at-expiry: one source says 0.125% of settlement value [U]; it is charged on the whole contract value, so it can wipe a small premium gain. Rule: **always sell before expiry, never get exercised.** Buying (opening) an option pays no STT; STT hits the sale.

**Ban list.** Stock enters ban when OI > 95% of MWPL; fresh positions only after OI falls below ~80% [S]. In ban: only reducing/offsetting trades; new buys that increase position are rejected and penalties apply [V/S]. Selling-to-close a long option is allowed. So the brain must not BUY a banned stock's option, but can exit. Banned stocks often have distorted prices (OI crowding, momentum names) and run a short-covering risk. Source: https://www.nseindia.com/static/products-services/equity-derivatives-risk-management-sec-ban . 2026 examples: Ambuja, Kaynes, SAIL on 27 Oct.

**Price bands.** Stock options have a dummy circuit "operating range" of 10% of base price, adjusted for delta, flexible on member request [V] (https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications). Stock futures have no fixed band. Sliding temporary price limits apply to options when the underlying is in cooling-off (since 18 Nov 2024) [V]. An option can hit its operating range and be frozen: stop orders may not fill (exit risk on a gap).

**Programmatic sources.**
- Ban list: NSE `fo_secban_DDMMYYYY.csv` (name per NSE REG_IND file structure doc: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/REG_INDDDMMYY_File%20Structure%201.pdf) [V name, URL path UNVERIFIED]. Download from `nsearchives.nseindia.com` (no Cloudflare; weekend/holiday = 404) [S]. Libraries with working URL patterns: `nse-archives`, `nselib`, `jugaad-data`, `NseIndiaApi` on PyPI/GitHub: read their source for exact paths.
- Lot sizes: NSE `fo_mktlots.csv` (path unverified) or `nselib` F&O list, or the Angel scrip master (`lotsize` field on OPTSTK rows). Angel scrip master is the safest since it is what orders use. [U for NSE path]
- Bhavcopy: new UDiFF format since July 2024 (old URLs dead) [S] (https://tradingqna.com/t/has-nse-changed-bhavcopy-location/169551).
- Smoke-test every URL on a known trading day before wiring it in.

## 2. Costs and liquidity

- Angel One options brokerage: flat Rs 20 per executed order (Rs 0 for first 30 days of a new account) [V] (https://www.angelone.in/pricing). Round trip = Rs 40 + GST, plus exchange txn charge (~0.03-0.05% of premium), SEBI fee, stamp duty (buy side, 0.003%), STT 0.15% of sell premium. On a Rs 3,000 premium position round trip costs roughly 1.5-2.5% of premium in all-in costs; much worse for tiny premiums.
- SEBI FY26 study: costs = 35% of gross losses for losers, 21% of gross profits for winners; STT share of costs rose 13% -> 26.7% [V] (https://www.outlookmoney.com/amp/story/invest/sebi-futures-options-study-transaction-costs-traders-losses-fy26).
- Spreads: I found no sourced NSE spread statistics [U]. Practitioner expectation: index options ATM 0.05-0.3 rupees wide; large-cap stock options (RELIANCE, HDFCBANK, INFY, SBIN) ATM near-month about 0.3-1% of premium; mid/small F&O stocks 1-5%+ and far strikes 5-20%+. General rule: tight spread correlates with high OI at that strike [S, US-based guides]. Our own `options_recorder.py` data/flow gives measured spreads for NIFTY/BANKNIFTY; do the same for stocks before trusting any number here (TODO: log bid/ask for 20 stocks for a week).
- Illiquidity hurts buyers twice: you pay ask on entry and receive bid on exit, so a 3% spread = 3% hurdle before theta; wide-spread strikes also gap through stops. Use ATM or 1 strike OTM, near-month, OI >= ~500 lots (heuristic) and bid-ask spread <= 2% of premium; skip otherwise.

## 3. Evidence

SEBI studies (individual equity derivatives traders):
- FY22-24: 93% lost money, aggregate loss > Rs 1.8 lakh cr [S].
- FY25 (July 2025): 91% net loss, aggregate Rs 1.06 lakh cr (revised later to 1.12), 13 brokers, ~96 lakh traders [V] (https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html).
- FY26 (Aug 2026): 87.7% net losers after costs (82.1% before costs); ~4.4 lakh traders profitable gross turned net losers by costs; aggregate loss Rs 91,685 cr (-18%); average loss ~Rs 1.17 lakh; active traders 98.1 -> 78.6 lakh; options = ~92% of aggregate losses; traders earning < Rs 5 lakh/yr = 53% of losses on 43% of turnover [V] (Outlook link above; Finnovate, Open mag corroborate).
- Persistence: only ~0.5% (1 in 200) profitable every year across 5 years; 65.6% of consistent participants lost in all five years; prior-2-year losers likely to lose again [S] (https://www.outlookmoney.com/invest/sebi-futures-options-study-retail-traders-trading-losses-experience).
- What the profitable minority look like: **not found** in my sources (buyer-vs-seller split, win rate, experience). Earlier SEBI studies (Jan 2023, FY22 data) said profitable traders were larger/more experienced and that losses were concentrated in intraday options buyers [U, recall; verify in SEBI report].
- Research on buying stock options (OTM lottery premium, IV crush, option momentum): nothing Indian found. From general academic literature (US): OTM options are overpriced (lottery preference), earnings-straddle buyers lose on average because pre-earnings IV overstates the move, IV rises into events and collapses after [U, general knowledge, not verified this pass]. Treat as priors to TEST on our own data.

Bottom line: base rate for an option buyer is strongly negative; any edge must clear ~2-4% round-trip friction plus theta. The paper player must prove positive expectancy net of costs over >=100 trades before live.

## 4. Strategy playbook (small account, buying options). Practitioner heuristics [U]: test, do not trust.

1. **Event-driven (news, order wins, block deals, PSU/theme rallies).** Enter only after the first confirmation candle (15-30 min after release), not on the headline gap. Edge is momentum continuation days 1-3; stale news is already in IV.
2. **Breakout + OI confirmation.** Price breaks the prior-day/20-day high on volume >1.5x average AND futures OI rises >=5-10% intraday (long buildup). Price up + OI down = short covering: weaker, take quick profit, smaller size. Price down + OI up = short buildup (put candidate). Use stock FUTURES OI (fatter, cleaner than option OI). Mirror for puts.
3. **IV.** Prefer buying when IV percentile < 50 and not already spiked. Avoid buying within 1-3 sessions before quarterly results unless expecting a move bigger than the implied move; IV drops 20-50% after results even on correct direction (IV crush) [U]. Cleaner: buy after the results gap in the direction of continuation, or skip results week.
4. **Strike/expiry.** Near-month, ATM or one strike ITM (delta 0.5-0.65), >= 10 trading days to expiry; never buy with < 7 days left (theta + physical settlement margin). Avoid OTM lottery strikes (poor expectancy, wide spreads).
5. **Sizing.** Risk <= 1-2% of account per trade (premium paid x stop %); with Rs 30k that is Rs 300-600 risk; stock lots often cost Rs 5-30k premium, so many stocks are simply unaffordable: filter lot x premium <= ~Rs 8-10k. Max 2-3 concurrent.
6. **Stops/targets.** Stop = -30 to -35% of premium or underlying closes below breakout level; target +40-60% then trail; time stop 3-5 sessions if no progress (theta). Use option-price stops on LIMIT orders (algo MARKET banned); expect slippage on wide spreads.
7. **Rolling/exit.** Exit (do not roll) by E-3 at the latest; if thesis still live, re-enter next month series only after a fresh signal. Never hold ITM through E-2 (margin ramp, STT on exercise).
8. **Gap/overnight risk.** Holding overnight adds gap risk both ways; fine if stop-out is premium-capped (buyer's max loss = premium) but price band freezes and results-after-close gaps need a calendar check.

## 5. Data sources

| Need | Source | Script-usable |
|---|---|---|
| F&O bhavcopy (UDiFF), OI, settle | https://nsearchives.nseindia.com (see `nse-archives`, `nselib`, `jugaad-data`) | Yes, trading days only |
| Ban list | `fo_secban_DDMMYYYY.csv` (above) + NSE page https://www.nseindia.com/static/products-services/equity-derivatives-risk-management-sec-ban | Yes (verify path) |
| Lot sizes | Angel scrip master (already in repo `data/scripmaster.json`), NSE contract specs page | Yes |
| Live option chain, OI, bid/ask | Angel SmartAPI (market data/quote FULL) | Yes (rate limited) |
| OI spurts, % OI change, long/short buildup | NSE website live tables (JSON endpoints need cookies, blocked on cloud IPs [S]); or compute from bhavcopy + intraday FUT quotes | Compute ourselves |
| Participant-wise OI | NSE archives `fao_participant_oi_DDMMYYYY.csv` [U path] | Yes (index-heavy, low value for stocks) |
| Results calendar | NSE corporate "Board meetings" page / BSE announcements; Trendlyne, Screener (scrape) | NSE page needs cookie session; check `nselib` |
| Corporate announcements, block deals | NSE/BSE announcements feeds; brain already uses WebSearch | Partial |
| IV / IV percentile | Not published free by NSE; compute from chain via Black-Scholes using Angel LTP, store daily to build own percentile history | Self-built (start recording now) |

## Brain rules

1. Never buy an option in a stock on the ban list (check today's `fo_secban` first); exiting is allowed.
2. Only near-month, ATM or 1 strike ITM; never OTM lottery strikes.
3. Skip if bid-ask spread > 2% of premium or strike OI < ~500 lots; use LIMIT at mid-to-ask, never chase.
4. Skip if lot x premium > ~Rs 8-10k (30% of the Rs 30k account) or max loss at stop > 2% of equity.
5. No new buys with < 10 trading days to expiry; hard-exit every position by E-3 (before physical settlement margin ramp and exercise STT); never hold ITM to expiry.
6. Directional signal must be price break + volume + futures OI rising (long buildup for calls, short buildup for puts); short covering = half size, fast exit.
7. Check results calendar: no new positions 1-3 sessions before results unless explicitly trading the event; post-results trade only continuation.
8. Enter on confirmation (15-30 min after news/open), not on the headline spike; skip first 10 minutes.
9. Premium stop -30% (or underlying invalidation), take half at +40-50%, trail the rest; time stop 3-5 sessions without progress.
10. Max 3 open option positions, max 1 per sector/theme; no re-entry same stock within 2 sessions after a stop.
11. Prefer liquid large caps (top ~50 by option OI) over mid-caps; mid-cap option spreads eat the edge.
12. Prefer index option if no clear stock edge: spreads tighter, no ban/physical settlement risk (but weekly theta).
13. Be aware of costs: round trip ~Rs 40 + STT 0.15% on sell + exchange charges; do not take trades whose target < 3x total costs.
14. Skip when NIFTY gaps > 1.5% against the trade direction, or on RBI/Budget/election days.
15. Log every trade with reason, IV at entry (computed), spread at entry/exit, OI change: this is the dataset that decides whether the player has any edge.

**Brain packet data, ranked by value:**
1. Today's ban list + stocks near ban (MWPL%) (hard filter).
2. Per candidate: live option bid/ask, OI, volume for ATM/ATM+-1 near-month (liquidity filter).
3. Stock futures price change + OI change (intraday and 1-day) = buildup classification.
4. Days to expiry and lot size x premium (affordability, expiry gate).
5. Results/board-meeting calendar (next 5 days) and recent corporate announcements/block deals.
6. Underlying trend context: prior-day high/low, 20-day high, relative volume, sector move, NIFTY trend.
7. Computed IV and IV percentile (needs own history; start storing now) and implied vs recent realised move.
8. Open positions with days held, current premium, stop, DTE.
9. Participant-wise OI and PCR (index-level context, lowest value for stock picks).

## Key uncertainties
Stock lot/contract-value rule, Angel exact square-off time, STT on exercise rate, spread statistics, exact NSE file URLs, and profitable-minority traits were not confirmed from primary documents; section 4 numbers are unbacktested heuristics.
