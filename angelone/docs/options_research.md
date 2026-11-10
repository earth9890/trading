# Index options buying in India (Rs 10k, Angel One SmartAPI): research, as of 2026-11-05

Confidence key: V = seen in search results/secondary sources; UNVERIFIED = not confirmed against a primary NSE/BSE/SEBI document. No primary circular was opened, so verify key numbers before go-live.

## 1. Contract specs and rules
- NIFTY lot 65 (NSE circular FAOP70616, 3 Oct 2025; effective from the 6 Jan 2026 expiry). V: [Angel One](https://www.angelone.in/news/market-updates/nse-revises-lot-sizes-for-index-derivatives-from-december-2025-nifty-lot-size-to-reduce-to-65), [Sahi](https://www.sahi.com/blogs/nifty-lot-size-2026-bank-nifty-sensex)
- SENSEX lot 20. V (third-party tables, one conflicting). Read lot size from the instrument master, never hardcode.
- Expiry: NIFTY weekly on Tuesday (NSE, since Sep 2025); SENSEX weekly on Thursday (BSE). A holiday moves expiry to the previous trading day. V
- Capital fit: 1 NIFTY lot = 65 units, so a Rs 100 premium costs Rs 6,500. The Rs 10k cap allows roughly one lot at a premium of Rs 150 or less. SENSEX 20 units is cheaper per lot (about Rs 3,000 at Rs 150).
- SEBI Oct/Nov 2024 framework (upfront premium, one weekly expiry per exchange, calendar-spread benefit removed on expiry day, +2% ELM on expiry day, intraday position-limit monitoring): my search found no source. UNVERIFIED for 2026 status. Upfront premium is irrelevant for buyers. One-weekly-expiry-per-exchange is consistent with the NIFTY and SENSEX expiry days above.

## 2. Costs: buying round trip
| Item | Rate |
|---|---|
| Angel brokerage | Rs 20/order flat (user-stated) |
| STT, option sell side | **0.15% of premium since 1 Apr 2026** (was 0.10%). Budget 2026 confirmed. [Deccan Herald](https://www.deccanherald.com/business/markets/union-budget-2026-stt-on-futures-hiked-by-150-options-by-50-markets-tank-3882160), [Angel One](https://www.angelone.in/news/market-updates/budget-2026-stt-hike-here-is-how-trading-will-cost-more-for-retail-investors-now) |
| STT, exercised ITM option | Also 0.15% of settlement value (was 0.125%). V, same sources |
| NSE exchange charge, options | 0.03503% of premium (Oct 2024). One Zerodha page shows 0.03553%, so verify. No 2026 revision found. [Zerodha bulletin](https://zerodha.com/marketintel/bulletin/391488/revision-in-transactions-charges-from-1st-october-2024) |
| BSE SENSEX options | 0.0325% of premium (Rs 3,250/crore). [Outlook Business](https://www.outlookbusiness.com/markets/nse-bse-revise-transaction-charges-effective-from-october-1) |
| SEBI fee | Rs 10/crore (my recollection, UNVERIFIED) |
| Stamp duty | 0.003% of buy value |
| GST | 18% on brokerage + exchange charge + SEBI fee |

**Worked example:** NIFTY, 1 lot (65), buy at Rs 100, sell at Rs 110. Buy value Rs 6,500, sell value Rs 7,150.
- Brokerage 2 x 20 = 40.00
- STT 0.15% x 7,150 = 10.73
- Exchange 0.03503% x 13,650 = 4.78
- SEBI fee about 0.01
- Stamp 0.003% x 6,500 = 0.20
- GST 18% x (40 + 4.78 + 0.01) = 8.06
- **Total about Rs 63.8.** Gross profit is Rs 650, so net is about Rs 586.
- Breakeven is about 1 index point of option move. The flat Rs 40 brokerage is about 63% of total cost, so costs are about 0.5% of turnover per round trip. This drops if premium per trade is larger. The spread matters far more than fees (section 3).

## 3. Spreads and slippage
No credible published figure found for ATM weekly expiry-day spreads. UNVERIFIED. Rule-of-thumb only: liquid ATM NIFTY and SENSEX tick spreads are Rs 0.05 to 0.5 in normal conditions. They widen to several rupees in fast moves or in the last hour. SENSEX is less liquid than NIFTY. One backtest-tool vendor claims live multi-leg fills run 0.5 to 1.5% worse than mid. Treat this as a vendor claim. For the bot: record bid, ask and fill in a paper run and measure it yourself. Place LIMIT orders at or near the ask on entry, with a bounded chase.

## 4. Strategies and evidence
No rigorous, cost-inclusive, peer-reviewed or audited evidence found for any of these on NIFTY or SENSEX options. Everything below is vendor blogs or forums, so treat it as UNVERIFIED.
- Expiry-day 15-min ORB buying ATM: only a vendor claim of a 52-week Bank Nifty backtest, with no net-of-cost P&L. [source](https://bankniftyoptions-com.pages.dev/artigos/banknifty-weekly-expiry-strategy). A related academic-style ORB replication on index CFDs found gross edge reproduced but net about zero after costs. [MQL5](https://www.mql5.com/en/blogs/post/776235)
- 9:20 short straddle (selling): backtests exist (e.g. 869 points in 60 days, 40-point drawdown, excluding costs). The strategy shows drawdown periods since 2021 and is reported "gamed" by 9:20 crowding. [MarketCalls](https://www.marketcalls.in/futures-and-options/how-the-9-20-intraday-straddlers-are-being-gamed.html), [TradingQnA](https://tradingqna.com/t/reports-of-the-death-of-920-short-straddle-is-greatly-exaggerated/179061). Margin is about Rs 2.4 lakh per NIFTY straddle lot (a Dec 2024 forum post, so not feasible at Rs 10k and out of scope for a buying-only bot).
- Momentum or trend-day buying, VWAP, gamma blast, OI/PCR: no published net-profitable evidence found. Buying edge must come from (a) a trend large enough to beat theta plus spread, and (b) a hard stop. Without an edge test of your own, assume negative expectancy.

## 5. SEBI studies
- FY25 (Jul 2025): 91% of individual F&O traders lost; aggregate loss Rs 1.06 lakh crore (+41% vs FY24); about 70% of index-options turnover on expiry day. [Business Standard](https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html)
- FY26 (Aug 2026): 87.7% lost; aggregate net loss Rs 91,685 crore (-18%); options about 92% of losses; 82.1% lost even gross, and costs pushed about 4.4 lakh more traders into net loss; expiry-day share of index-options turnover about 59%. [Business Today](https://www.businesstoday.in/markets/story/rs91685-cr-lost-88-of-individual-traders-lost-money-in-fy26-options-drove-92-of-losses-550474-2026-08-21), [Moneylife](https://www.moneylife.in/article/retail-fo-traders-lose-rs91685-crore-in-fy26-despite-sebi-curbs-average-loss-hits-rs117-lakh-govt/81318.html). One summary says 90% of option buyers lost in FY26. UNVERIFIED. Seller versus buyer split and expiry-day-specific loss rates: not confirmed.
- "1 in 200": a separate SEBI study found only about 0.5% of traders were profitable every year over five years, and 65.6% of those active all five years lost in every year. V (secondary summary)

## 6. Dangers (mechanics, not sourced)
- Theta: an ATM weekly option bleeds fastest on expiry day, so time value is about zero by 15:30. A flat market loses roughly the whole premium.
- IV crush after events or after the open: premium can fall even if the index moves in your favour.
- Expiry-day gamma: both the big wins and the sudden total loss come from here. Use a hard premium stop (for example -30% to -40%) and a time stop.
- Freak or erroneous prints in far-OTM strikes, and wide spreads: trade ATM or near-ATM only, and use LIMIT orders.
- Auto square-off: brokers close intraday positions around 15:15 to 15:20 and charge a fee. Exit yourself before then.
- Exercise trap: an ITM option held to expiry is cash-settled with STT of 0.15% on the full intrinsic value, which can exceed the profit on a small position. Never hold to expiry.
- Margin for selling: out of scope. The bot is buying-only, so max loss is the premium paid.

## Takeaways for the bot
Costs are about Rs 64 per round trip on a Rs 6,500 position, so spread and slippage dominate. Evidence of a net edge is weak or absent everywhere, so paper-trade first and treat the Rs 10k as risk capital.
