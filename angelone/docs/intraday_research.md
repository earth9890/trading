# Intraday cash (MIS) with Rs 10k via Angel One SmartAPI: research (2026-11-04)

Confidence: SEBI, Gao and Angel brokerage are sourced. Stamp, exchange, SEBI-fee rates and leverage rules are from general knowledge and marked UNVERIFIED. Searches did not return them.

## 1. SEBI evidence
- SEBI study (July 2024), FY23, equity cash intraday, top-10 brokers: over 70% of individual intraday traders lost money. Average loss was Rs 5,371 per trader. About 6.9M traders in FY23, up from 1.5M in FY19. [Business Standard](https://www.business-standard.com/amp/markets/news/over-70-intra-day-traders-incur-losses-during-fy23-reveals-sebi-study-124072401110_1.html), [ThePrint](https://theprint.in/economy/71-of-intraday-traders-incur-losses-finds-sebi-report-impact-higher-among-young-small-traders/2192598)
- The loss-maker share rose from 65% (FY19) to over 70% (FY23). It was 80% for traders with more than 500 trades a year and 81% for those under 20.
- Costs: loss-makers spent an extra 57% of their losses on trading costs. Profit-makers spent 19% of their profits on costs. [News Arena](https://newsarenaindia.com/economy/70-of-intraday-traders-suffered-losses-in-fy23-sebi/17650)
- Newer cash-segment intraday data (FY24 or later): not found, UNVERIFIED. SEBI's newer studies cover F&O.

## 2. Angel One charges
- Brokerage: the lower of Rs 20 or 0.1%, minimum Rs 5. This has applied since 17 Nov 2025. It was previously the lower of Rs 20 or 0.03%. [Angel pricing update](https://www.angelone.in/news/product-updates/pricing-update-nov-2025-b2c)
- STT: 0.025% on the sell side only. This is consistent across sources.
- Stamp duty: 0.003% on the buy side (UNVERIFIED for Angel; this is the statutory rate). One third-party source said 0.015%, which looks like the delivery rate.
- NSE transaction charge: about 0.00297% per side (UNVERIFIED). SEBI fee: Rs 10 per crore (UNVERIFIED). GST: 18% on brokerage + transaction charge + SEBI fee. No DP charge for intraday.
- Check [Angel's charges page](https://www.angelone.in/exchange-transaction-charges) before relying on any rate.

Round-trip cost estimate (buy and sell the same notional):

| Position | Brokerage | STT | Stamp | Txn + SEBI | GST | Total | % of position |
|---|---|---|---|---|---|---|---|
| Rs 10,000 (no leverage) | 10+10 = 20 | 2.5 | 0.3 | 0.6 | 3.7 | about Rs 27 | about 0.27% |
| Rs 50,000 (5x) | 20+20 = 40 | 12.5 | 1.5 | 3.1 | 7.8 | about Rs 65 | about 0.13% |

- The 0.1% brokerage cap means a Rs 10k trade pays 0.2% in brokerage alone. Position size above Rs 20k hits the Rs 20 cap.
- Slippage is not included. It is likely 0.05 to 0.2% per side on mid and small caps.
- Rs 65 per day is roughly Rs 1,400 per month (21 days) on a Rs 10k account. That is about 14% of capital if you trade every day at full 5x size.

## 3. MIS leverage and square-off
- Auto square-off: equity at 3:15 pm per [Angel support](https://www.angelone.in/support/your-orders/square-off). A source says MIS timings change from 3 Aug 2026 to match new exchange hours. New times are UNVERIFIED.
- Auto square-off fee: sources conflict. One says about Rs 50 + GST, another says normal brokerage only. UNVERIFIED. Avoid relying on auto square-off by exiting yourself before 3:15.
- Margin: leverage is stock-specific, typically up to about 5x for liquid large caps and much less (or none) for others. Under peak-margin rules the required margin is checked at the snapshot peak, so leverage cannot be increased intraday by position juggling. Specific Angel multiples: UNVERIFIED. Read them from the SmartAPI margin or RMS endpoint.
- Angel may square off positions if the loss reaches 80% of available margin (per an Angel help snippet).
- With LIMIT-only orders, an exit limit can fail to fill. A stuck position then gets squared off by Angel at 3:15 and may incur fees.

## 4. Strategy evidence
- ORB with "Stocks in Play": Zarattini, Barbon and Aziz, [SFI RP 24-98](https://ideas.repec.org/p/chf/rpseri/rp2498.html). The backtest is on US stocks from 2016 to 2023. It reports about 1,600% net return and Sharpe 2.81 for the top-20 Stocks in Play. That is a US result with US cost assumptions, and it does not transfer automatically to India.
- Replication: an [independent replication](https://www.mql5.com/en/blogs/post/776235) on five indices was titled "gross reproduced, net zero". I read only the title and snippet, so the method and conclusion are UNVERIFIED. Expect the edge to be thin after costs.
- Market intraday momentum: Gao, Han, Li and Zhou, [JFE 2018](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414). The first half-hour return predicts the last half-hour return on SPY. In-sample R2 is 1.6%, out-of-sample R2 is 1.2%. Gross annualized return is 6.3% for the long-only version, per [Alpha Architect](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/). A follow-up found it significant in 12 of 16 markets. This is index-level evidence. It is not proven for individual Indian stocks, and no India-specific test was found, UNVERIFIED.
- VWAP reversion/trend and gap-and-go or gap-fade: no peer-reviewed India-specific evidence found. UNVERIFIED. Most published claims are vendor blogs.
- Cost applicability: the paper edges are a few bps to tens of bps per trade. A 0.13 to 0.27% round-trip cost plus slippage can erase them. Only large-cap, high-liquidity names and few trades per day are viable.

## 5. Risks and tax
- Overtrading. The SEBI data shows the more trades, the more losers.
- Slippage and LIMIT-only fill risk (missed entries, stuck exits).
- Leverage amplifies losses. A 2% adverse move on a 5x position is a 10% loss of capital.
- Circuit limits (a stock can lock and trap an exit), ASM/GSM stocks (higher margin, restricted MIS), news gaps, and illiquid small caps.
- API risks: static IP, session expiry, bugs, and duplicate orders. Keep a hard kill switch and a daily loss cap.
- Tax (verify with a CA, UNVERIFIED here): intraday equity is speculative business income, taxed at slab rates. It is reported in ITR-3. Speculative losses carry forward 4 years and offset only speculative income. Audit thresholds may apply. Loss-making years still need filing to carry the loss forward.

## 6. Bottom line
- Base rate: over 70% of intraday traders lose, and costs consume most of any edge.
- On Rs 10k the Rs 10k trade pays about 0.27% round trip. Even at 5x it is about 0.13% plus slippage. Break-even needs roughly 0.2 to 0.4% gross edge per round trip, which is hard.
- Realistic expectation: the most likely outcome is a slow loss. Expect negative returns after costs, in the order of -Rs 1k to -Rs 5k a year with disciplined low-frequency trading, and worse when overtrading. This is an estimate, not sourced. A small positive edge exists only in the best case: few trades, liquid large caps, strict stops.
- Treat it as a paid-tuition experiment. Cap daily loss (for example 1 to 2% of capital), trade at most 1 to 2 setups a day, and paper-test with realistic costs and LIMIT fills first.
