# Edge cases & market rules: Angel One NSE delivery swing bot (Rs 5k)

Written 2026-11-03. Legend: [V] = verified in a source fetched today; [K] = from background knowledge, re-verify before go-live. Rule first, then BOT action.

## 1. Settlement
- [K] NSE cash is T+1 (since Jan 2023); optional T+0 exists only for a small stock list, so ignore it. BOT: never use T+0.
- [K] Bought shares reach demat after T+1 pay-out; selling them before that (BTST) is a short-delivery risk. The exchange auctions the shortfall and the penalty can be 20%+ on top of the close-out price. BOT: no sell of a holding until broker shows it in holdings (not positions) with `t1quantity` settled or `authorisedquantity` > 0. Treat T1 holdings as non-sellable until the broker confirms.
- [K] Sale proceeds are usable for new buys the same day (as margin) but are withdrawable only after T+1. BOT: size buys from `getRMS` available cash, never from expected sale proceeds.
- Cost on Rs 5k: see section 10. DP charge makes round-trips on tiny lots costly. BOT: minimum hold of several days, no churn.

## 2. Price bands and circuits
- [K] Stock bands are 2/5/10/20%, with some stocks having no band. F&O stocks have no fixed band but use dynamic operating ranges (about 10% flex). BOT: read `upperCircuit`/`lowerCircuit` from quote data and refuse to buy within ~1% of upper circuit (cannot exit if it flips) or a stock at lower circuit.
- [K] Index-level halts (Nifty/Sensex 10/15/20% moves) pause the whole market for 45 min to the rest of the day. BOT: on any order error or stale quotes during a halt, do nothing and retry after resume; never spam orders.
- [K] If a stock is locked at lower circuit, a stop-loss gets no fills and you may be stuck for days. BOT: log it, keep the stop on, no market-order panic attempts, alert user. Position sizing (section 9) caps the damage.
- BOT: reject any limit price outside band (pre-validate).

## 3. Surveillance (ASM / GSM / ESM / T2T)
- [K] ASM, GSM and ESM stocks carry margin of up to 100% and sometimes trade-for-trade. BE and BZ series are trade-for-trade (no intraday netting, delivery only). BOT: universe filter excludes any ASM/GSM/ESM name and any series other than EQ.
- Fetch: NSE publishes ASM/GSM lists under Market Data / Surveillance on nseindia.com (needs browser-like headers plus cookies from a warm-up GET of the homepage) and as archive files on nsearchives.nseindia.com. BOT: refresh the lists daily before 9:00, cache them, and fail closed (no new buys) if the fetch fails or the list is older than 1 trading day.
- BOT: if a held stock enters a list, do not add; consider an exit by a plan rule (not panic).
- Also check the F&O ban list: not applicable to cash buys, but ban stocks are volatile, so skip them.

## 4. Gaps and stop-loss mechanics
- [K] Regular SL orders are day orders, so they expire at 15:30. For multi-day holds use GTT (Angel GTT API, valid up to 1 year) or re-place the SL daily. BOT: after each fill, create the GTT stop; on startup verify a live stop exists for every holding.
- [K] A gap down through the stop makes an SL-limit sit unfilled below the market. NSE cash SL-M is largely unavailable on retail platforms (verify what SmartAPI accepts). BOT: use SL-limit with the limit set 1-2% below the trigger (clipped to band), and if still open 5 min after the open, cancel and send an aggressive limit at the best bid minus a small buffer ("market protection" emulation).
- [K] Pre-open is 9:00-9:15: order entry 9:00-9:08, matching 9:08-9:12, buffer 9:12-9:15, continuous trading from 9:15. The first print is a single auction price and can differ a lot from the previous close. BOT: do not place buys before 9:15; wait for the first quotes, skip a stock if it gaps beyond a threshold (for example above +3% or below -3% from the signal price), and use limit orders with a cap, not market.
- BOT: stops are checked on the live LTP as well; never rely on a single mechanism.

## 5. Corporate actions
- [K] Splits, bonus, and demergers change the price, not the value. An ex-date price drop can falsely trip the stop or poison indicators. Dividends drop the price by about the dividend.
- BOT: pull the NSE corporate actions list daily; for any held or candidate stock with an ex-date today or tomorrow, skip new buys and recompute the stop (split ratio) before the open. Use adjusted OHLC for indicators (rebuild history after any split/bonus). Detect unadjusted breaks: if one-day change < -40% while volume is normal, flag as suspected split, pause the stock.
- Broker auto-adjusts holdings and may cancel open orders/GTTs on the ex-date. BOT: re-verify stops after ex-date.

## 6. Holidays and special sessions
- [V] 2026 weekday closures (NSE, per [Angel One](https://www.angelone.in/nse-holidays)): Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3, Apr 14, May 1, May 28, Jun 26, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25. Weekend ones: Feb 15, Mar 21, Aug 15, Nov 8.
- Upcoming relevant: Tue 10 Nov (Diwali Balipratipada), Tue 24 Nov (Guru Nanak; one source lists it as a settlement holiday, so confirm), Fri 25 Dec.
- Muhurat: the Angel page says Wed 21 Oct 2026, but the same page lists Diwali Laxmi Pujan on Sun 8 Nov, so the date is conflicting. Muhurat is a special evening hour; BOT: no trading in Muhurat and treat any non-standard session as closed unless explicitly enabled.
- [V] 2027: no official NSE circular was found; NSE usually publishes in December (2026 circulars were dated Dec 2025). BOT: refuse to assume 2027 dates; the calendar file must be refreshed from the NSE circular in Dec 2026; if the date is beyond the loaded calendar, stop trading (fail closed).
- Detection: (1) weekend; (2) local calendar file; (3) at 9:15 confirm with a live quote (LTP timestamp updated); (4) NSE `holiday-master?type=trading` endpoint as a cross-check. If sources disagree, do not trade.
- Special Saturday sessions (DR drills) occasionally occur: BOT ignores weekends.

## 7. Order rejections and idempotency
- Common rejects: insufficient funds/margin, price outside band, price not a multiple of tick (Rs 0.05 or 0.01 per instrument; round to `tick_size`), quantity above freeze qty, RMS block (stock in surveillance, blocked scrip), exchange maintenance. BOT: pre-validate all of these locally and on reject classify as RETRYABLE (network, rate limit) or TERMINAL (funds, band, RMS); terminal means mark the signal failed, alert, no retry.
- Partial fills: BOT tracks filled qty, sets the stop for the filled qty only, and cancels the remainder at the cutoff (for example 10:00) rather than chasing.
- Duplicate orders on retry: BOT writes an intent record (UUID) before sending; send with `ordertag` = that UUID; on timeout or unknown outcome, query the order book by `ordertag` before any resend.
- Modification limits: exchange limits modifications per order; BOT prefers cancel and re-place only after confirming the cancel; never modify rapidly.
- Rate limits: SmartAPI has per-second limits; BOT throttles and backs off.

## 8. Operational
- Internet/power failure on the laptop: the stop must live at the broker (GTT/SL), not in the bot loop. BOT: heartbeat plus alert on a missed beat (phone/Telegram).
- Token expiry: JWT expires daily (about midnight); BOT re-logs in before 9:00 (TOTP automated), and on a 401 refreshes and retries once.
- Clock drift: sync NTP; BOT compares local time against the broker/server time header and refuses to trade if the skew is over 2 s. TOTP also fails on drift.
- Crash mid-order: on startup, reconcile before anything else: fetch holdings, positions, order book, and GTT list and rebuild state from the broker (broker is the source of truth). Open intents with no order are marked unknown and resolved by `ordertag` lookup.
- State file corruption: write atomically (temp file plus rename), keep a rolling backup, checksum it; on failure, rebuild from the broker and refuse to buy until reconciliation is clean.
- Single instance: lock file to prevent two bots running.

## 9. Risk controls
- Max daily loss (for example 2% of capital): breach means stop new buys for the day.
- Drawdown kill switch (for example 10% from peak equity): flatten or freeze per policy, require manual re-arm.
- Max positions: with Rs 5k, 2-3 (a lot size of 1 stock may be Rs 1k+ anyway); min order value to keep DP cost under about 0.5% of the position.
- Max per-position: <= 40% of capital; per-trade risk <= 1-2% of capital (position = risk / stop distance).
- No averaging down: never add to a loser; BOT rejects buy when the symbol is already held at a loss.
- Sector concentration: max 1 position per sector at this size.
- Cooldown: 3 consecutive losses means 2-3 trading days off; also same-stock re-entry cooldown after a stop-out.
- Liquidity filter: min average daily turnover to avoid slippage and circuits.
- Dry-run/paper mode default; live requires explicit flag.

## 10. Tax and costs
- [K] STCG on listed equity (STT paid) is 20% (from 23 Jul 2024); LTCG 12.5% above Rs 1.25L/yr; holding > 12 months is long term. Short-term losses can offset gains and carry forward 8 years if filed. Delivery STT is 0.1% on both buy and sell.
- [K] Intraday equity is speculative business income (ITR-3), not capital gains. BOT: delivery only; never squareoff same day except by an emergency exit rule (flag it, since it changes tax treatment).
- [V] [Angel One](https://www.angelone.in/angel-one-brokerage-charges) shows Rs 0 delivery brokerage, but third-party sites list Rs 20 or 0.1%; verify on the rate card before go-live.
- [V] DP charge per [Angel One](https://www.angelone.in/knowledge-center/demat-account/dp-charges): Rs 20 per debit transaction (Rs 50 for BSDA clients, per that page) plus taxes; comparison sites say Rs 20 + GST per scrip per sell day. On a Rs 1,500 position this is about 1.6% of the sale; hence the minimum position size rule above.
- Add up: STT 0.1% x2, exchange charges, stamp duty on buy, GST. BOT: compute the net expected edge after costs and skip trades where target gain < ~3x round-trip cost.
- BOT: keep a trade ledger (CSV) with all charges for ITR / AIS reconciliation.

## Sources
- NSE holidays: https://www.angelone.in/nse-holidays
- Charges: https://www.angelone.in/angel-one-brokerage-charges , https://www.angelone.in/list-of-charges , https://www.angelone.in/knowledge-center/demat-account/dp-charges
- NSE circulars (holidays, surveillance): https://nsearchives.nseindia.com/content/circulars/
- NSE ASM/GSM, pre-open, price bands: nseindia.com Market Data / Surveillance and Trading pages (re-verify [K] items there)
