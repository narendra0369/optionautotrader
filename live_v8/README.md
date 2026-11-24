# OptionX V8 — Angel One order lifecycle rehearsal (OFFLINE ONLY)

**User goal:** Build the missing buy/sell order adapter, protective SL/target
coordinator, broker partial-fill/reject and crash/restart recovery, with
repeatable tests. Preserve existing AWS Mumbai read-only paper services and
24-hour health watchdog. Never enable real-money orders in this stage.

## What is implemented
- `angel_order_plans.py`: exact SmartAPI-style JSON **plans** for NFO
  **NORMAL LIMIT BUY**, **STOPLOSS STOPLOSS_LIMIT SELL** and **NORMAL LIMIT
  target SELL**. Only accepts broker-verified NFO token, lot size and tick
  size asserted in the local rehearsal harness; validates exact price ticks,
  quantities, direction and ownership requirements. No MARKET/IOC/ROBO,
  options selling/short selling, extra reverse exits or OCO claim.
  `send_real_order()` ALWAYS raises `REAL_ORDERS_HARD_LOCKED`.
- `shadow_journal.py`: local SQLite DEV rehearsal journal using WAL and
  `synchronous=FULL`, atomic reserve and event uniqueness. It records
  `ACK_UNKNOWN` **before** any simulated submission and will not retry
  blindly after reconnect/restart. Stores synthetic broker order IDs,
  cumulative verified fill/exit quantities, and broker-confirmed stop coverage.
  Warns when partial fills remain unprotected or an exit leaves an orphan stop.
- `restart_recovery.py`: independent *read-only* simulated full-account
  Orderbook + Tradebook + Positions comparison with ten-second fresh evidence
  requirement, account/owner proof flags, order-ID linkage, duplicate and
  untracked order detection, fill/quantity/stop coverage confirmation.
  **Always sets** `canSubmitOrder=false` and `newEntriesBlocked=true`,
  including when synthetic books match.
- `test_order_rehearsal.py`: offline-only unit tests covering valid order
  payloads, tick/lot/NaN/bool rejection, unverified contract, SELL stop
  trigger/limit direction, target cancel interlock, hard order lock,
  duplicate/unknown ACK, broker rejection, partial fill, gap to stop cover,
  missing or rejected stop, stale or unowned snapshots, mismatched tradebook,
  unexpected manual orders/positions, oversize exits, duplicate events,
  durable unknown state after reopening journal.
- `offline_demo.py`: deterministic end-to-end synthetic BUY 65 → FILL 65 →
  STOP ACK 65 → restart 3-book reconciliation using a throwaway local SQLite
  database. **No network, no API key/TOTP, no broker actual symbol.**

Run from repository root (Python 3.10+):

```powershell
python -m unittest -v live_v8.test_order_rehearsal
python -m live_v8.offline_demo
```

The demo's `NIFTY27NOV2626000CE` and token `123456` are **invented test
fixtures**, and must never be treated as actual Angel One instruments.

Official broker specifications checked during this development:
- https://smartapi.angelone.in/docs/Orders
- https://smartapi.angelbroking.com/exchange-regulations
- https://github.com/angel-one/smartapi-python

## NOT completed / cannot claim until independently demonstrated
- No real broker private order API transport, order ID receipt, orderbook
  replay from AWS, real SL/target placement, real fill/reject/cancel, real
  exchange OCO (not established), actual broker/native exit protection, or
  restart against true Angel Orderbook+Tradebook+Positions with open trades.
- No production signed owner HTTPS AWS gateway, encrypted vault, durable live
  order store, authenticated broker session renewal, broker quote WebSocket,
  exchange holiday/cutoff/lot/fee/stop confirmation, operational alerting.
- No broker order permissions/regulatory order subtype confirmation beyond
  Active API app + registered AWS static IP `43.204.246.235`.
- No real-money risk amount approved independent of the existing ₹500,000
  *virtual* paper account; no user approval to send real orders.
- This folder is **not imported by `market_api.py`** and is not deployed on
  the AWS market API, Render production or the mobile public site.

## Safe next milestones

1. Review the new V8 offline tests in GitHub CI and user machine; fix failures.
2. Build a separate, owner-authenticated **read-only AWS staging bridge** to
   collect complete orderbook/tradebook/positions and exact quote timestamps;
   test account mapping, origin, TLS, retries and fail-closed behavior.
3. Introduce durable live intent ledger and trusted broker/order update
   normalizers, manual kill switch and audit alerts. Run approved broker
   test/sandbox lifecycle if available; isolate secrets server-side.
4. Independently confirm per-order API permissions, broker-supported
   stop-limit and target/stop-cancel rules, margin, instrument master and
   static registered egress. Test live native protective exit and recovery
   with separate explicit owner permission before enabling any real trades.
5. Only after all gates pass, obtain owner-approved live sizing and a separate
   explicit final enable action. **Never infer live approval from a green CI
   or a verified static IP**.

## Note on SL/target OCO

A SELL STOPLOSS_LIMIT can remain unfilled during a sharp move. Sending both
a live stop SELL and a live target SELL for the same long options quantity may
create two competing exit orders. Until an explicitly supported broker-side
OCO/reduce-only mechanism is independently verified, the V8 planner requires
the stop CANCEL to be broker-confirmed and the open position freshly checked
before planning a target SELL. This is **not atomic** and is not ready for live
execution. No loss amount or execution price is guaranteed.

Existing 21/21 offline V7 scenarios and paper market service stay unchanged.
