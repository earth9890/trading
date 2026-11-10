# Angel One SmartAPI reference (as of 2026-11-03)
Legend: [SDK] read from installed SmartApi source; [WEB] Angel notice/forum; [UNV] unverified/from memory - test before relying.
Base `https://apiconnect.angelone.in`. All calls via `requests`; HTTP 200 even on logical errors, so check `status` (bool), `message`, `errorcode`.
Headers needed: Bearer JWT, `X-PrivateKey`(api key), `X-UserType: USER`, `X-SourceID: WEB`, client IP/MAC headers (SDK fills them).

## 1. Session
| Item | Detail |
|---|---|
| Login | `generateSession(clientCode, password(PIN), totp)` -> POST loginByPassword; returns profile dict with `data.jwtToken` ("Bearer " prefixed), `refreshToken`, `feedToken`. SDK also calls getProfile (2 requests). [SDK] |
| TOTP | 6-digit, from the QR secret (`pyotp.TOTP(secret).now()`), 30s window; wrong/expired -> AB1050-type invalid totp [UNV code]. Don't login within last 2s of a window. |
| JWT lifetime | ~24h but all sessions die at ~midnight IST daily [UNV exact]; refresh token similar. Treat any token as invalid after 00:00 IST. |
| Refresh | `generateToken(refresh_token)` -> sets new jwt+feedToken (limit 1/s, 1000/h). `renewAccessToken()` posts jwt+refresh. Refresh only works while refresh token valid; after midnight do full `generateSession`. [SDK] |
| Re-login when | AG8001/AG8002 (invalid/expired token), HTTP 401/403 TokenException, or after midnight. Login once per day, share session; do not login per run (1/s limit, and other processes share it). |
| Logout | `terminateSession(clientCode)`; kills the JWT for all processes sharing it. Avoid in a shared setup. |
| SDK hook | `setSessionExpiryHook(fn)` fires only for `error_type=="TokenException"` with 403. [SDK] |

## 2. Rate limits [WEB: forum post 16438; per-IP/user not documented]
| Endpoint | /sec | /min | /hour |
|---|---|---|---|
| loginByPassword | 1 | - | - |
| generateTokens | 1 | - | 1000 |
| getProfile | 3 | - | 1000 |
| logout | 1 | - | - |
| getRMS (rmsLimit) | 2 | - | - |
| placeOrder / modifyOrder / cancelOrder | 20 | 500 | 1000 |
| getOrderBook, getTradeBook, getPosition, getHolding, getAllHolding, searchScrip | 1 | - | - |
| getLtpData, quote (getMarketData), convertPosition, order details/{id}, margin batch | 10 | 500 | 5000 |
| GTT create/modify/cancel/ruleDetails/ruleList | 10 | 500 | 5000 |
| getCandleData | 3 | 180 (table said 500, mod corrected) | 5000 |
- Exceeded: HTTP body is plain text/HTML `Access denied because of exceeding access rate`, not JSON, so the SDK raises `DataException("Couldn't parse the JSON response ... Access denied because of exceeding access rate")`. [WEB] Catch DataException and treat as rate limit.
- Backoff: client-side limiter per endpoint (use 80% of /sec, e.g. 1 call/1.2s for the "1/s" group); on hit sleep 1.5s, then 3, 6 (cap ~30s, 4 tries); if per-minute blocked, wait to next minute boundary. Never retry order placement blindly (see Gotchas). Prefer `getMarketData` (batch up to 50 tokens/mode [UNV]) over many ltpData calls; hourly orders cap 1000.
- Order rate by SEBI: 10 orders/sec/exchange without registration. [WEB]

## 3. placeOrder (`placeOrder(dict)` returns orderid string or None; `placeOrderFullResponse` returns whole response dict) [SDK]
Params: `variety`, `tradingsymbol`, `symboltoken`, `transactiontype` (BUY/SELL), `exchange` (NSE/BSE/NFO/BFO/MCX/CDS/NCDEX), `ordertype`, `producttype`, `duration` (DAY/IOC), `price` (string), `squareoff`, `stoploss`, `triggerprice`, `quantity` (string), `ordertag` (<=20 chars [UNV]), `disclosedquantity`. `uniqueorderid` returned in response `data` alongside `orderid` (full response only) [UNV]. None values are stripped.
| Field | Allowed |
|---|---|
| variety | NORMAL, STOPLOSS, AMO, ROBO (ROBO legacy/BO; likely disabled [UNV]) |
| ordertype | MARKET, LIMIT, STOPLOSS_LIMIT, STOPLOSS_MARKET |
| producttype | DELIVERY (CNC), INTRADAY (MIS), CARRYFORWARD (NRML F&O), MARGIN, BO |
- STOPLOSS variety needs `triggerprice` (+`price` for SL-L). For SL-L SELL: trigger >= price; BUY: trigger <= price.
- 2026 rules [WEB]: from 1 Apr 2026 "Market orders and IOC orders are strictly prohibited for algorithmic trading". Expect rejects for MARKET and `duration=IOC` from API; SL-M likewise [UNV exact error text]. Use LIMIT (priced marketable, within tick and circuit range) + DAY. Whether Angel converts market->limit-with-protection is NOT confirmed.
- Success: `{"status":true,"message":"SUCCESS","errorcode":"","data":{"script":..,"orderid":"2611...","uniqueorderid":"<uuid>"}}`. Order id returned = accepted by OMS, not by exchange; confirm via order status.
- Modify: `modifyOrder({variety,orderid,ordertype,producttype,duration,price,quantity,tradingsymbol,symboltoken,exchange})`. Cancel: `cancelOrder(order_id, variety)`.

## 4. Order status
- `orderBook()` (1/s) -> `data` list (None when no orders). Fields: `orderid, uniqueorderid, orderstatus, status, text` (rejection reason), `filledshares, unfilledshares, averageprice, price, triggerprice, ordertype, producttype, transactiontype, tradingsymbol, symboltoken, exchorderid, updatetime, exchtime`.
- Status strings (lowercase): `open`, `complete`, `rejected`, `cancelled`, `trigger pending`, `validation pending`, `put order req received`, `modified`, `open pending`, `after market order req received`, `modify pending`, `cancel pending`, `modify validation pending`, `not cancelled`. Terminal: complete/rejected/cancelled. [partly UNV]
- `individual_order_details(uniqueorderid)` -> GET `/order/v1/details/{uniqueorderid}` (10/s; takes the uniqueorderid GUID, not orderid; SDK has no auth/error handling, returns None on non-200). [SDK/WEB]
- `tradeBook()` fills: `orderid, fillprice, fillsize, filltime, fillid`.
- Poll orderBook at <=1/s; once per ~2s per pending order batch.

## 5. GTT (never called in this repo; docs only)
- `gttCreateRule({tradingsymbol, symboltoken, exchange, producttype, transactiontype, price, qty, triggerprice, disclosedqty, timeperiod})` returns rule id (int). `gttModifyRule({id, symboltoken, exchange, qty, price, triggerprice, disclosedqty, timeperiod})`. `gttCancelRule({id, symboltoken, exchange})`. `gttDetails(id)`. `gttLists(status=[...], page, count)` status must be a list e.g. `['NEW','CANCELLED','ACTIVE','SENTTOEXCHANGE','FORALL']`. [SDK for names; status list UNV]
- Single-leg only (no OCO; for stop+target place two rules and cancel manually) [UNV]. producttype DELIVERY or MARGIN only. Applies to equity cash; SELL of delivered holdings works if shares are in demat (not T1 pending) [UNV].
- On trigger a LIMIT order at `price` is sent (validity DAY); if price not hit it stays open/expires. Rule `timeperiod` in days, max 365 [UNV].

## 6. Holdings, positions, RMS
- `holding()` = delivered+T1 stock: `tradingsymbol, symboltoken, exchange, isin, quantity, t1quantity, realisedquantity, authorisedquantity, product, averageprice, ltp, close, profitandloss, pnlpercentage`. `allholding()` adds `totalholding` summary. T1 shares are in `t1quantity` (bought, not yet delivered); selling T1 needs EDIS/TPIN authorisation like other delivery sells (`authorisedquantity`) [UNV T1-sell rules].
- `position()` = day's trades: `buyqty, sellqty, netqty, avgnetprice, ltp, pnl, realised, unrealised, producttype`. `convertPosition({exchange,symboltoken,oldproducttype,newproducttype,tradingsymbol,transactiontype,quantity,type})`.
- `rmsLimit()` fields: `net` (total balance after margin used), `availablecash` (free cash for new trades), `availableintradaypayin` (intraday pay-in not yet settled, usable for intraday), `availablelimitmargin`, `collateral`, `m2munrealized`, `m2mrealized`, `utiliseddebits`, `utilisedspan`, `utilisedexposure`, `utilisedpayout`, `grossAvailable`. Use `availablecash` for sizing. [meaning from docs memory UNV]

## 7. Instruments
- Scrip master: `https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json` (no auth; download once/day). Fields: `token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size`.
- `tick_size` is in PAISE (5 = Rs0.05; strike/price fields x100 for derivatives). Price must be an exact multiple of tick (round with Decimal); lot size = `lotsize`. NSE equity symbol suffix `-EQ`. Freeze quantity is NOT in the master; get from NSE freeze list (orders above freeze qty rejected) [UNV].
- Equity price band: reject when outside circuit; text in `text` field.

## 8. Error codes (`errorcode`)
| Code | Meaning | Action |
|---|---|---|
| AG8001 | Invalid token | re-login (fatal until relogin) |
| AG8002 | Token expired | refresh/relogin |
| AG8003 | Token missing | fix headers, fatal |
| AB8050 / AB8051 | Invalid / expired refresh token | full relogin |
| AB1004 | Something went wrong, try later | retryable (reads); orders: check book first |
| AB1050 / AB1051 / AB1052 | invalid TOTP / PIN / client | fatal; regenerate TOTP once |
| AB1007 / AB1008 | Invalid/empty request params | fatal bug |
| AB2000-series, AB1010 | Invalid order/ data | fatal |
| AB1019 | Max rate | retryable w/ backoff |
| LOGIN-ish "Invalid IP" / "static IP" | IP not registered | fatal; fix registration |
| Rate text | `Access denied because of exceeding access rate` | retryable |
Only AG8001/8002/8003 are well attested [WEB]; the rest are [UNV], match on `message` as well.

## 9. Compliance (from 1 Apr 2026) [WEB, Angel notice]
- Orders accepted only from registered primary static IP (secondary optional; IP change max 1 per calendar week; one IP per client unless family). Register in SmartAPI dashboard app. Data/read APIs may not be IP-restricted [UNV].
- 10 orders/sec/exchange threshold; below it, generic exchange algo id (assigned by Angel, no tag needed from you). Market and IOC banned for algos.
- Self-hosted logic permitted for "tech-savvy" clients with static IP; mock sessions exempt.

## 10. WebSocket V2 (`SmartWebSocketV2(auth_token, api_key, client_code, feed_token)`) [SDK]
`subscribe(correlation_id, mode, [{"exchangeType":1,"tokens":["2885"]}])`. Modes: 1 LTP, 2 QUOTE, 3 SNAP_QUOTE, 4 DEPTH (NSE cash only, quota ~50 tokens). exchangeType: 1 NSE_CM, 2 NSE_FO, 3 BSE_CM, 4 BSE_FO, 5 MCX_FO, 7 NCDEX, 13 CDE_FO. Prices in paise (divide by 100). Callbacks `on_open/on_data/on_error/on_close`; ping every 10s; auto-retry via `max_retry_attempt`. Max ~1000 tokens per connection [UNV]. Not subject to REST limits.

## 11. Hours (IST) [UNV, standard NSE]
Pre-open 09:00-09:15 (order entry 09:00-09:08); normal 09:15-15:30; closing session 15:40-16:00. AMO windows: after market ~16:00 to 09:00 next day (use variety AMO; Angel also 18:00-ish dependence UNV). MIS auto square-off ~15:15-15:20. Server API is up round the clock except maintenance near midnight.

## Gotchas
1. Rate-limit reply is not JSON: wrap calls for `DataException`; the SDK's error path also `raise exp(...)` when `error_type` is set.
2. `placeOrder` returns None on ANY failure (error only logged); use `placeOrderFullResponse` to see `message/errorcode`.
3. `gttCreateRule` etc. index `['data']['id']` directly, so failures raise TypeError/KeyError.
4. Never retry placeOrder after timeout without checking orderBook (duplicate risk); use `ordertag` as your idempotency marker.
5. quantity/price must be strings; prices multiple of tick; tick_size in paise.
6. Many "1/s" endpoints (orderBook, position, holding, rmsLimit 2/s) are shared by all processes on same account: budget across processes.
7. `individual_order_details` needs uniqueorderid, and SDK ignores `_request` error handling.
8. orderBook `data` can be None with empty book.
9. Candle data: ONE_MINUTE max 30 days/call, THREE/FIVE 100d, TEN 100d, FIFTEEN 200d, THIRTY 200d, ONE_HOUR 400d, ONE_DAY 2000d; params `exchange, symboltoken, interval, fromdate, todate` as "YYYY-MM-DD HH:MM" [UNV limits].
10. Token expiry at midnight kills long-running bots; schedule a relogin ~08:30.
