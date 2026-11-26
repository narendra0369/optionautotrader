# OPTIONX V37 — Conditional Angel One SmartAPI Response Review
Date: 2026-11-26 IST

## Provenance
Owner supplied an email-style message attributed to Angel One SmartAPI Technical Support, received at approximately 12:41 PM IST. This is a transcription supplied in chat: sender authentication, full email headers and account-specific app permission activation were not independently verified. Avoid committing account client IDs or private account identifiers.

## What the response actually says
- The application details were **reviewed**, including a self-coded application hosted on AWS and the registered static public IP already recorded in prior handovers.
- Live order execution facilities **may** be permitted, **subject to** successful validation and applicable regulatory requirements.
- Authorized SmartAPI endpoints **may** be used for BUY/SELL, including NFO, subject to broker/exchange RMS and order validation.
- Only approved static-IP-origin requests may be considered.
- Stop-loss limit orders are subject to supported order types/parameters; LPP applies.
- Applicable fees/taxes follow prevailing tariffs; applicable algo registration/tagging must be completed.
- **Final live trading authorization will be effective only after confirmation by both technical and compliance teams.**

Therefore this is **NOT final account-specific live order permission**. It is also NOT the owner's final consent for a particular manual-position SELL.

## Verified work completed
- V30 owner-authenticated AWS position/LTP preview PASS; no broker orders.
- V31 offline 18/18 AWS PASS.
- V32 offline 19/19 AWS and owner FULL quote PASS; transient bid 10.85 and ask 10.90 at snapshot.
- V34 + V35 combined offline 36/36 AWS PASS.
- V36 offline 20/20 AWS PASS.
- Existing manual position historically NIFTY29DEC2629000CE token 38158, long 65; snapshots expire.

## Do not authorize live execution from this email
Required remaining evidence:
1. Explicit technical **AND** compliance team final authorization, with the exact self-coded app and trading API entitlement confirmed (no credentials shared).
2. F&O segment, API key Trading permissions, undertaking and exchange algo-tagging compliance confirmation.
3. Fresh broker positions/orders/tradebook, exact manual position/product type/lot and any open SELL/STOP verification.
4. Current relevant tick/master; no standalone LPP bounds endpoint claimed; reconcile LPP errors 17070 without automatic repricing or resubmission.
5. Actual transaction costs and verified cost basis; limit SELL 10.50 is distinct from STOPLOSS_LIMIT 10.00/9.95 and neither is guaranteed to fill.
6. Independently reviewed production durable pre-send intent journal, unknown ACK handling, crash/restart recovery, kill switch and broker-owned order-ID reconciliation.
7. Fresh owner's **separate explicit exact-order authorization** after all safety checks, naming contract, side, order type, quantity, limit or trigger/limit, risk and order lifetime.

Source lock `live_v7/angel_execution_transport.py` and Supabase STOPPED engine guard stay unchanged. No real BUY, SELL, STOP, cancel, replace or automatic retry. No production deployment.

## Suggested response to Angel One
Please confirm whether the SmartAPI Trading API entitlement and NFO access for my specific reviewed self-coded AWS app are now **activated** or still pending; whether the required one-time undertaking and algo tagging are complete; and whether **both** technical and compliance teams have issued their final live order execution approval. Please reply with a clear final approved/pending status and any outstanding action without requesting any PIN, TOTP or API secret.
