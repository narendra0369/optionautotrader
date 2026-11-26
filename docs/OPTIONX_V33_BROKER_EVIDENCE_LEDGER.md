# OptionX V33 — evidence ledger and remaining real-order blockers (2026-11-26)

## Read-only evidence completed (historical, not current order authorization)
- V28 authenticated AWS instrument master preflight PASS: NFO token 38158, symbol NIFTY29DEC2629000CE, lot 65, expiry 29DEC2026, tick 0.05. Implementation: `live_v7/manual_sl_combined_preflight_v28.py`, fetches the Angel scrip master over TLS. Not dependent on a stored local instrument-master file. This does NOT prove *current* dynamic LPP.
- V29 AWS 16 offline tests PASS.
- V30 AWS 15 offline tests PASS and owner-authenticated read-only broker recheck PASS: manual long 65, proposed SELL LIMIT 10.50, snapshot LTP 10.80, no order submitted.
- V31 AWS 18 offline tests PASS. All mock evidence checks remain source-locked; not production broker certification.
- V32 AWS 19 offline tests PASS and authenticated read-only FULL quote PASS: LTP 10.80, best bid 10.85 (displayed bid quantity 65), best ask 10.90, reported exchange feed timestamp 2026-11-26T06:11:31Z, broker-reported feed age 9.621 sec at reception. These are time-limited observations, NOT executable present liquidity, and exchange source timestamp was not independently certified.
- V33 inventory search found no **locally cached** instrument-master; the V28 network master route is already implemented and was previously run successfully. Do not misreport this inventory result as missing all contract/tick checks.

## V33 outstanding blocking evidence
1. **Current** position + conflicting orders + session state, whenever contemplating an actual order; historical snapshots expire.
2. Broker official entitlement/approval in writing for this exact self-coded SmartAPI key and registered AWS IP, `NFO SELL LIMIT DAY` for an existing manual bought option position, exact `NORMAL` variety/producttype, 65-unit lot and order field requirements; plus independent confirmation if `SELL STOPLOSS_LIMIT` is requested instead. Read-only account access is not proof of write permission. Do not send a "small test" order to infer entitlement.
3. Dynamic exchange/broker Limit Price Protection bounds at intended submission/trigger time. Static tick `0.05` and displayed bid do not certify LPP.
4. Actual broker cost basis and all charges/taxes. Owner-declared average 12.92 is not verified fill cost. At 10.50 draft limit, gross premium loss on 65 units would be (12.92 - 10.50)*65 = 157.30 INR *if all 65 fill exactly there*, excluding costs; risk is not capped if the order remains unfilled.
5. Production durable journal, unknown ACK reconciliation, duplicate-send prevention, owner-specific authorization, restart/partial-fill handling, real-time reconciliation, broker order IDs, and independent compliance approval. Existing source lock and DB STOPPED guard prohibit live execution.

## Critical type distinction
V30–V32 current exit draft is **SELL LIMIT 10.50**. V28/V29 proposed an entirely distinct **SELL STOPLOSS_LIMIT trigger 10.00 / limit 9.95**. Never substitute one for the other or treat LIMIT SELL as a protective SL. A stop-limit can trigger but remain unfilled and cannot guarantee maximum loss.

## Next action (no broker orders)
Use official Angel One support/portal to request written permission + exact supported NFO order fields, account/app registration and algorithm tagging, dynamic LPP source, and fee schedule. Do not include API keys, PINs, TOTP, JWT, UUIDs or account secrets in any ticket. Independently verify existing read-only feeds for market quote and broker instrument metadata as required. Only after current evidence, production certification and a **separate, exact-order owner consent** may an independently reviewed execution release even be considered.

## Non-negotiable invariants
No new real BUY, SELL, modify, or cancellation. No source-lock removal, no database stop-guard change, no automatic handling of manual positions, no deployment to the running AWS service. V33 ledger is documentation only.
