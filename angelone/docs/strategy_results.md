# Strategy search vs NIFTYBEES buy & hold (Rs 5,000, NSE, daily bars, local data only)

Code: `research_bt.py` (imports backtest.py load/indicators/costs; own engine). Period 2019-01 to 2026-11. IS = 2019-22, OOS = 2023-26.
Costs: backtest.costs (0.1% STT each side, stamp, exchange, Rs 16 DP per sell). Signal at close, fill next open, stops checked from entry day, gaps fill at open. Taxes (20% STCG) NOT modelled.
Universe = today's ~79 liquid NIFTY-100 names (survivorship bias, large; see robustness). Rotation uses equal weight in top-N, regime = NIFTYBEES close > 200DMA (daily), rebalance on last trading day of month, stocks need 20d avg turnover > Rs 20cr and mom>0. In regime-off: hold NIFTYBEES ("bees-fb") or cash.

## Main table
| strategy | CAGR | maxDD | trades | PF | win% | IS CAGR | IS DD | OOS CAGR | OOS DD | CAGR/|DD| |
|---|---|---|---|---|---|---|---|---|---|---|
| NIFTYBEES B&H | 11.6% | -36% | 0 | nan | nan% | 14.8% | -36% | 8.2% | -15% | 0.32 |
| rot n=1 6m bees-fb stop15% | 26.0% | -63% | 77 | 1.43 | 48% | 32.9% | -63% | 19.0% | -49% | 0.41 |
| rot n=2 6m bees-fb stop15% | 32.8% | -44% | 124 | 1.90 | 54% | 37.3% | -44% | 27.4% | -32% | 0.75 |
| rot n=1 12-1 bees-fb stop15% | 18.3% | -45% | 76 | 1.40 | 62% | 42.1% | -29% | -2.1% | -45% | 0.40 |
| rot n=2 12-1 bees-fb stop15% | 31.9% | -27% | 117 | 2.02 | 56% | 41.1% | -26% | 23.0% | -27% | 1.17 |
| rot n=2 6m cash-fb stop15% | 28.5% | -39% | 71 | 2.26 | 49% | 28.3% | -39% | 28.0% | -28% | 0.73 |
| rot n=2 6m bees-fb stop2.5ATR | 20.5% | -54% | 137 | 1.42 | 45% | 21.6% | -54% | 18.5% | -45% | 0.38 |
| rot n=3 6m bees-fb stop15% | 31.3% | -38% | 167 | 2.20 | 53% | 30.0% | -38% | 32.2% | -22% | 0.82 |
| don55/20 no filter 2%/2pos | 6.0% | -23% | 76 | 1.52 | 43% | 4.4% | -23% | 7.7% | -20% | 0.26 |
| don55/20 +regime 2%/2pos | 6.8% | -17% | 61 | 1.85 | 43% | 4.8% | -15% | 9.0% | -15% | 0.40 |
| don55/20 +regime novol 2%/2pos | 14.1% | -25% | 64 | 2.32 | 39% | 13.9% | -25% | 14.0% | -15% | 0.56 |
| don+regime 1%/2pos | 1.8% | -14% | 63 | 1.29 | 32% | 2.9% | -11% | 0.7% | -14% | 0.13 |
| don+regime 1%/1pos | 0.9% | -8% | 30 | 1.36 | 40% | 1.9% | -8% | -0.3% | -5% | 0.11 |
| don+regime 2%/1pos | -0.2% | -18% | 35 | 0.96 | 40% | -1.3% | -16% | 0.9% | -11% | -0.01 |
| dip rsi2<10 hold5 | -17.3% | -79% | 107 | 0.38 | 36% | -20.2% | -67% | -14.2% | -47% | -0.22 |
| dip rsi2<10 hold10 | -14.6% | -73% | 87 | 0.43 | 41% | -19.8% | -65% | -9.0% | -34% | -0.20 |
| dip 20d-low hold10 | -1.4% | -28% | 26 | 0.77 | 50% | -2.2% | -28% | -0.6% | -13% | -0.05 |
| dip 20d-low hold20 | 0.5% | -24% | 22 | 1.07 | 50% | 0.6% | -24% | 0.4% | -12% | 0.02 |
| 70%BH + 30% rot n=2 6m bees-fb stop15% | 16.6% | -34% | 108 | 1.87 | 48% | 17.4% | -34% | 15.5% | -24% | 0.48 |
| 70%BH + 30% don55/20 +regime 2%/2pos | 8.4% | -30% | 57 | 0.72 | 25% | 10.1% | -30% | 6.5% | -15% | 0.28 |
| 70%BH + 30% rot n=1 6m bees-fb stop15% | 14.4% | -37% | 76 | 1.36 | 46% | 17.6% | -37% | 11.0% | -34% | 0.39 |

(Trades/PF/win% for B&H are n/a. Last column = full-period CAGR/|maxDD|. Core-satellite = static 3,500 B&H + 1,500 sleeve, no rebalance; the sleeve's Rs 16 DP is heavy at Rs 1.5k.)

## Survivorship / robustness check on rotation (n=2, stop 15%)
Test: remove the 10/20 best ex-post performers from the universe (overly harsh: also removes real selection skill), or the bottom half.
| variant | CAGR | maxDD | IS CAGR | OOS CAGR |
|---|---|---|---|---|
| 6m, full | 32.8% | -44% | 37.3% | 27.4% |
| 12-1, full | 31.9% | -27% | 41.1% | 23.0% |
| 6m, drop top-10 winners | 15.6% | -46% | -0.3% | 34.2% |
| 12-1, drop top-10 winners | 16.1% | -38% | 11.6% | 20.9% |
| 6m, drop top-20 | 20.6% | -35% | 12.9% | 28.4% |
| 12-1, drop top-20 | 14.4% | -35% | 11.5% | 17.5% |
| lookback 3m / 12m (n=2) | 26.0% / 41.1% | -32% / -29% | 37.5 / 58.3 | 14.8 / 25.4 |
| 12-1 stop 10% / 20% / 25% / none | 22.7 / 27.5 / 28.9 / 29.5% | -43 / -43 / -44 / -35% | | 18.5 / 23.8 / 26.5 / 21.9 |

## Findings (honest)
1. Donchian 55/20 + regime filter with vol>=1.5x: 6.8%/yr, DD -17% (Calmar 0.40 vs B&H 0.32): the filter helps but it still loses to B&H on return. Dropping the volume condition gives 14.1%/-25% (OOS 14.0%), but that is one parameter flip I tried after seeing results, so treat as unproven. Sizing 1%/1 position kills it (0.9%).
2. NIFTYBEES dip-buy (RSI2<10, or 20d-low): negative to flat (-17%..+0.5%). Costs per round trip (STT 0.2% + Rs 16) plus ETF trending down on dips. Dead.
3. Core-satellite 70/30 gives 8-17%/yr; it just dilutes. Does not beat B&H unless the satellite is the rotation (16.6%/-34%, Calmar 0.48), and then it is simply a diluted rotation.
4. Monthly momentum rotation is the only thing that beats B&H, in return AND Calmar (0.75-1.17 vs 0.32), in both IS and OOS, across lookbacks, N=2-3 and stop widths. Weak spots: n=1 is fragile (6m DD -63%, 12-1 OOS -2%); ATR stop (2.5 ATR) hurts (20%/-54%, whipsawed).
5. But the headline 30%+/yr is NOT believable: survivorship bias (today's index members are past winners). Removing the 10 best ex-post names cuts it to ~15-16%/yr with DD -38 to -46%, roughly B&H return with worse drawdown; OOS (2023-26) stays 17-34%, IS drops to 0-12%. Realistic expectation: B&H +/- a few points, with 2-stock concentration risk and -30..-45% drawdowns. No strategy here is proven to beat B&H out of sample on a bias-free universe.
6. Rs 5k reality: 1-2 positions of Rs 2.5k each, Rs 16 DP per sell is 0.6% per exit; roughly 15 round trips/yr at 2 stocks drag ~1.5-2%/yr (included). Taxes (20% STCG on trades < 1 yr) not included and would cut the rotation's edge further vs B&H (which defers/LTCG 12.5%).

## ONE recommended plan (Rs 5k)
Monthly momentum rotation, top-2, 12-1 momentum, regime filter, NIFTYBEES fallback.
- Universe: the liquid list (20d avg turnover > Rs 20cr). Rank by close[t-21]/close[t-252]-1; need > 0.
- Regime: NIFTYBEES close > its 200DMA, checked daily. OFF -> sell all stocks at next open and hold NIFTYBEES (not cash).
- Rebalance: last trading day of month, orders at next open. Hold the top-2 ranked names, 50% of equity each (about Rs 2.5k). Keep a name if still in top 2; sell names that drop out. If regime ON and holding NIFTYBEES, move into the top-2.
- Stop: hard stop 15% below fill, placed same day as a GTT/SL order; after a stop-out stay in cash until next month-end rebalance.
- Sizing: equal weight 50/50, no leverage, no pyramiding. Risk per position at the stop is 7.5% of equity.
- Why: only candidate with positive IS and OOS and better CAGR/|DD| across variants (12-1 n=2: 31.9%/-27%, OOS 23.0%/-27%); fallback to NIFTYBEES means you never do worse than B&H in bear regimes beyond whipsaw. 12-1/n=2 was the most stable variant, but it was picked from the grid after seeing it, so expect a large haircut (bias-free ~15%).
- Honest alternative: simply buy and hold NIFTYBEES (11.6%, DD -36%, ~zero costs, zero effort, no STCG). If you cannot tolerate 2-stock DD of ~-30..-45% or do not want the tax/DP drag, do that. Paper-trade the rotation 3 months before real money.

## Intraday (MIS) test, 2026-11-04 — `intraday_bt.py`
1y of 5-min bars (2025-11 → 2026-11), 6 largest NIFTY stocks (RELIANCE HDFCBANK BHARTIARTL ITC LT HINDUNILVR), Rs 10k, max 2 trades/day,
Angel intraday costs (0.1%/Rs20 brokerage, STT 0.025% sell, stamp, exch, GST) + 0.05% slippage/side, conservative intrabar fills.
| strategy | trades | gross edge/trade (after slippage) | cost/trade | 1x result | 5x result |
|---|---|---|---|---|---|
| ORB 15-min (EOD / 1R / 2R) | 492 | -4 to -5 bps | 27 bps (1x) / 22 (5x) | -76..-78% | account blown |
| ORB 30-min | 492 | -5.5 bps | | -80% | blown |
| Gap fade >1% | 128 | -7.6 bps | | -22% | -96% |
| First-hour relative strength | 496 | -8.1 bps | | -87% | blown |
| Last-half-hour momentum (Gao) | 494 | -7.6 bps | | -86% | blown |
Verdict: no edge even before brokerage (+-5 bps pre-slippage); costs are 5x any edge. Matches SEBI FY23: >70% of intraday traders lose. REJECTED.

## Index options BUYING, 2026-11-05 — `options_bt.py` (research only)
2y 5-min NIFTY/SENSEX + India VIX (2024-10 → 2026-11). Expired option candles aren't available from Angel, so premiums are
Black-Scholes with IV = VIX x calibrated multiplier (0.8 expiry morning → 1.05 at 15:00, 1.2 non-expiry; calibrated on real
NIFTY 03NOV/09NOV and SENSEX 05NOV candles; model ~Rs 10-15 rich on expiry-morning calls). Rs 10k, 1 lot, Rs 20/order,
STT 0.15% sell, exch, GST, stamp, slippage Rs 0.5+0.3%/side. Bug fixed: index data has a synthetic 15:25 close print.
| strategy | trades | win | avg net/trade | result |
|---|---|---|---|---|
| NIFTY expiry ORB15 (thread style, +reentry) | 181 | 9% | -764 | account blown |
| NIFTY expiry ORB15 / tgt +60% | 103 | 13-25% | -532..-672 | blown |
| SENSEX expiry ORB15 | 101 | 11% | -310 | blown |
| NIFTY trend 10:30 | 46 | 22% | -86 | -20%/yr |
| NIFTY last-30min (Gao) | 143 | 30% | -170 | blown |
| Expiry 14:00 straddle buy | 210 | 16% | -557 | blown |
Model-free check (ORB traded on the index itself, points): NIFTY expiry +2.2 pts/trade (t=+0.19), other days -1.2 (t=-0.21),
SENSEX expiry -18 (t=-0.47). The signal has NO edge; options add theta + ~Rs 56 costs + ~Rs 65 slippage per lot. REJECTED.
Live dry run: options_paper.py (launchd 09:17, expiry days) logs real-price paper trades to journal_options_paper.csv.
30-day manual replay (2026-09-23 → 11-05, thread-style ORB both indices, Rs 10k): 18 trades, 8 wins, NET +20,998 (3 big
SENSEX expiry wins). Context over 2y: of 471 rolling 30-day windows only 6% were profitable, 4% > +10k, 82% lost > Rs 10k
(account gone); median window -19.6k. Months positive 5/26 (incl. Sep-Oct 2026). Recent month = top-4% luck, not edge.
Caveat: model prices expiry-morning calls ~Rs 10-15 rich (bias vs buyers); index-points test shows zero edge regardless.
Bot vs blind brain (2026-11-05): 12 expiry days 09-24..11-03; a fresh sonnet agent per day saw only data to 09:30 that
day (15 sessions OHLC+VIX, first 15 min) and chose TRADE/CALLS_ONLY/PUTS_ONLY/SKIP. Same model prices + rules.
BOT +20,998 (18 trades) vs BRAIN +14,398 (15 trades). Brain saved Oct 1 (+1.3k), cost Oct 6 (-0.7k) and SKIPPED Oct 29
(-7.2k missed). Direction calls mostly echoed the trend = same info as the breakout itself. No evidence brain adds edge.
- 2026-11-05 LIVE paper duel SENSEX expiry (real option candles): BOT and BRAIN (CALLS_ONLY) both took 79000CE twice: -1,434 (stop 10:00) then 13:00 re-entry 168.75 -> exit 15:15, day NET +5,009 each. Running 31-day total: BOT +26,007, BRAIN +19,407.

## 2026-11-09 NIFTY expiry - paper ORB15 (replayed after close on real option candles)
Live paper run blocked all day: Mac asleep until 09:27, all launchd jobs fired at once, Angel candle API
returned "exceeding access rate" until after close. Replay (same rules) on real NFO candles:
NIFTY 24850PE in 10:45 @ 84.10, -30% stop same bar @ 58.19 -> gross -1,684, NET -1,741. No re-entry signal before 13:00.
Fixes: options_paper.py retries candle fetch + alerts on crash; user set `pmset repeat wakeorpoweron MTWRF 09:10`.

## 2026-11-10 Bot vs Brain, last 25 expiry days (Aug 20 - Nov 9 2026), modelled prices, Rs 10k, 1 lot, NET
`options_duel_bt.py` -> docs/options_duel.csv (brain = blind opus, no tools, 09:30 packet).
- BOT  +21,487, 10/25 days won, equity hit -502 (would have been wiped out before the Sep 15 +14k day).
- BRAIN +31,808, 9/19 traded days won, min equity 1,911. Edge came from PUTS_ONLY on 15/25 days (skipped 4 call-loss days, missed 2 small call wins).
- 5 big trend days (+14k, +11k, +9k, +7k, +3k) made all the profit; 60% of days lose 1-3k.
## 2026-11-10 Improvement ideas, ALL 205 expiry days (2 years), `options_ideas_bt.py` -> docs/options_ideas.csv
Every variant loses in BOTH halves. Baseline -2.75L; no re-entry -97k (best); against-trend -111k; skip VIX>16 -162k;
with-trend -185k; option stop -50% -381k (worst). VIX/OR-width/gap filters don't fix it. Last 25 days are a lucky window.
Applied (paper only): options_paper.py no longer re-enters after a loss.

## 2026-11-10 Loop 2 (Rs 30k per player)
- At Rs 30k the 25-day duel survives: BOT min equity ~19.5k, final +21.5k; BRAIN min ~21.9k, final +31.8k. 2-year baseline -2.75L still = 9x the account.
- ORDER FLOW (`options_flow_bt.py`, real Angel OI 5-min, 28 days, live contracts only): 09:30 flow sign (new put writing - new call writing, ATM+-5) predicted rest-of-day direction 54%, corr +0.08; PCR corr +0.09. Coin flip so far -> forward test only.
- SELLING (`options_sell_bt.py`, modelled, 205 expiry days, 1 lot, NET):
  iron fly (09:30 sell ATM straddle, wings +-4 strikes, stop loss=credit): +36k / +94k / +143k at IV x0.9/1.0/1.1, positive in both halves at every IV.
  condor +-1%/2%: -61k / -25k / +25k.  ORB credit spread: -8k / +21k / +46k.
  CAVEAT: model over-prices expiry-morning options ~Rs 10-15/leg -> inflates seller credit by up to ~Rs 1.3-2k/day (NIFTY). Real prices decide.
  Friction check on live SENSEX quotes: instant open+close of the fly = -Rs 611 (8 orders + spreads).
- New paper players from Nov 12: FLOW (OI direction, journal_options_flow.csv), FLY (hedged seller on real prices, journal_options_fly.csv).
- New recorder `options_recorder.py` (launchd 09:12): 5-min chain snapshots (ATM+-10, OI, volume, buy/sell qty) -> data/flow/. Real expiry-day prices for future backtests.

## 2026-11-10 HYBRID: brain picks the day's strategy (`options_hybrid_bt.py`, 208 expiry days, blind opus, Rs 30k, NET)
Brain plans: SELL 110 / BUY 62 / SKIP 36. Real skill at day TYPE: avg day range on its BUY days 1.36%, SELL days 0.77%.
| strategy | total | 1st half | 2nd half | maxDD | min equity |
|---|---|---|---|---|---|
| always BUY (bot) | -1,01,962 | -63k | -38k | broke | -1.04L |
| always SELL fly IVx0.9 | +30,360 | +21k | +10k | -71% | 9,735 |
| HYBRID buy/sell/skip IVx0.9 | +67,517 | +52k | +15k | -66% | 9,815 |
| **SELL-or-SKIP (brain) IVx0.9** | **+77,572** | +50k | +28k | -41% | 17,577 |
| SELL-or-SKIP IVx1.0 | +1,09,832 | +66k | +44k | -38% | 18,745 |
Brain BUY days: buy -10k (fly would have lost -42k). Both indices positive (NIFTY +44k, SENSEX +33k); 6/9 quarters positive.
Applied (paper): HYBRID player trades only the brain's SELL days (iron fly); BUY/SKIP = no trade.
CAVEAT: modelled option prices; real-price paper test from 2026-11-12 decides.

## 2026-11-11: stock picking variants + quick small-profit rules (₹10k, 2 slots, 2019-01..2026-11, NET after Angel charges)
Ranking for monthly rotation (15% stop): strongest 12-1 momentum 31.4%/yr DD -29% | most volatile 6.1% DD -43% |
momentum x volatility 27.5% DD -38% | 1-month return 14.0% DD -53% | momentum/volatility 23.5% DD -28% |
Adani only (ENT/PORTS) 42.7% DD -47% (2019-22 +115.5%/yr, 2023+ -7.1%/yr).
Quick-profit (buy top-10 leader or dip in leader, take profit / stop / max days): every combo lost.
+2%/-3%/5d: 24% win, avg NET -₹45/trade, account wiped | +4%/-5%/10d: 44% win, -₹33 | +8%/-8%/20d: 46-48% win, -22..-30%/yr.
Round-trip cost on ₹5k ≈ ₹47 (~1%), DP ₹23.6 + min brokerage dominate.
User's decision anyway (2026-11-11): LIVE = brain dip-buys + +5% NET take-profit, -5% stop; monthly rotation removed. Track real NET.

## 2026-11-11: BANKNIFTY / BANKEX monthly expiry backtest (`options_bank_bt.py`, docs/options_bank.csv)
Modelled prices (Black-Scholes on India VIX x IV mult; bank indices trade above VIX so 1.0/1.2/1.4), Rs 30k, 1 lot, NET after costs+slippage, data 2024-10-29..2026-11-11. MONTHLY expiries (BANKNIFTY Thu -> Tue from Sep-2025; BANKEX Mon (Nov-Dec 2024) -> Tue -> Thu from Sep-2025). Historical lots per expiry (BANKNIFTY 15/30/35/30, BANKEX 15/30); NIFTY/SENSEX rows use current lots. orb15 = ORB15 breakout buy, no re-entry; iron_fly = 09:30 ATM fly, wings 4 strikes, stop 1x credit.

| index | freq | IV x | strategy | days | total NET | win days | worst day | maxDD Rs |
|---|---|---|---|---|---|---|---|---|
| BANKNIFTY | monthly | 1.0 | orb15_noreentry | 25 | -36,546 | 0 | -3,391 | -35,688 |
| BANKNIFTY | monthly | 1.0 | iron_fly_w4_stop1x | 25 | 8,003 | 14 | -5,835 | -16,179 |
| BANKNIFTY | monthly | 1.2 | orb15_noreentry | 25 | -43,133 | 0 | -3,585 | -42,133 |
| BANKNIFTY | monthly | 1.2 | iron_fly_w4_stop1x | 25 | 21,444 | 14 | -4,758 | -12,330 |
| BANKNIFTY | monthly | 1.4 | orb15_noreentry | 25 | -49,705 | 0 | -3,731 | -48,563 |
| BANKNIFTY | monthly | 1.4 | iron_fly_w4_stop1x | 25 | 30,756 | 16 | -3,863 | -9,593 |
| BANKEX | monthly | 1.0 | orb15_noreentry | 24 | -15,637 | 2 | -2,876 | -29,341 |
| BANKEX | monthly | 1.0 | iron_fly_w4_stop1x | 24 | 7,184 | 12 | -4,053 | -8,068 |
| BANKEX | monthly | 1.2 | orb15_noreentry | 24 | -23,481 | 2 | -3,407 | -34,893 |
| BANKEX | monthly | 1.2 | iron_fly_w4_stop1x | 24 | 19,439 | 14 | -3,367 | -4,641 |
| BANKEX | monthly | 1.4 | orb15_noreentry | 24 | -31,313 | 2 | -3,938 | -40,450 |
| BANKEX | monthly | 1.4 | iron_fly_w4_stop1x | 24 | 27,992 | 15 | -2,790 | -3,212 |
| NIFTY | weekly | 1.0 | orb15_noreentry | 106 | -70,738 | 13 | -2,650 | -96,665 |
| NIFTY | weekly | 1.0 | iron_fly_w4_stop1x | 106 | 79,825 | 66 | -6,684 | -17,260 |
| NIFTY | weekly | 1.2 | orb15_noreentry | 106 | -87,142 | 12 | -2,991 | -111,246 |
| NIFTY | weekly | 1.2 | iron_fly_w4_stop1x | 106 | 144,738 | 73 | -5,802 | -10,104 |
| NIFTY | weekly | 1.4 | orb15_noreentry | 106 | -120,576 | 10 | -3,443 | -137,090 |
| NIFTY | weekly | 1.4 | iron_fly_w4_stop1x | 106 | 190,025 | 79 | -5,056 | -8,740 |
| SENSEX | weekly | 1.0 | orb15_noreentry | 108 | -34,232 | 11 | -3,596 | -55,541 |
| SENSEX | weekly | 1.0 | iron_fly_w4_stop1x | 108 | 20,278 | 59 | -3,118 | -12,603 |
| SENSEX | weekly | 1.2 | orb15_noreentry | 108 | -68,601 | 10 | -3,751 | -86,215 |
| SENSEX | weekly | 1.2 | iron_fly_w4_stop1x | 108 | 47,742 | 62 | -2,644 | -8,579 |
| SENSEX | weekly | 1.4 | orb15_noreentry | 108 | -91,989 | 11 | -4,070 | -105,913 |
| SENSEX | weekly | 1.4 | iron_fly_w4_stop1x | 108 | 65,073 | 67 | -2,292 | -6,649 |

Verdict: with only ~24-25 expiry days per bank index this is a screen, not evidence. Buying (ORB15) lost on both indices at every IV (BANKNIFTY 0 wins in 24 trades, nearly every one stopped at -30%; BANKEX 2 wins), consistent with the NIFTY/SENSEX weekly result, so no case for buying on monthlies. The iron fly was positive on both (BANKNIFTY +8k/+21k/+31k, BANKEX +7k/+19k/+28k at IV x1.0/1.2/1.4) with ~55-65% win days and worst day ~-4k..-6k on a 30k account, but its profit rises mechanically with the assumed IV (seller credit is inflated if the model over-prices expiry-morning options, as found for NIFTY), so only the x1.0 row is conservative and a few big days dominate. At about 1 trade/month, Rs 7-8k over 2 years is small versus the Rs 4-6k worst day. Treat as 'not disproven, not proven'; the real-price recorder data should decide before any capital.
