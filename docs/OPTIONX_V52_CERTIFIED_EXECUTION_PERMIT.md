# OPTIONX V52 — Source-level unconditional deny replaced with exact-order permit

Owner requested replacing Angel's unconditional source lock and connecting it to their own website activation.

## Implemented
- `live_v7/angel_execution_transport.py`: removed unconditional `LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION` raise. Execution transport now REQUIRES an exact payload, owner, operation bound one-time signed AWS dispatch permit for `place` and `cancel`, in addition to broker approval and production safety gates. V52 capability reports `sourceLockEnabled=False`, `permitRequired=True`, **`realOrdersEnabled=False`**.
- `live_v7/certified_execution_permit_v52.py`: verifies short-lived HMAC-SHA256 signed permit with an AWS-private key file, exact order hash/owner, <=10 second expiry, strict single-use durable private SQLite nonce ledger. Consumes signed nonce atomically *before* initiating HTTP request. A crash or ambiguous response cannot reuse the permit.
- `live_v7/test_certified_execution_permit_v52.py`: 16 isolated tests, including fake HTTP ACK positive path. No Angel network calls.
- Updated old V49-V51 source-lock-specific assertions and CI workflow for 83 offline tests.

## Important limitations
- This is SOURCE code in a draft GitHub PR; nothing is merged/deployed. The existing AWS production worker and website remain unchanged.
- There is no deployed production permit issuer. An issuer must perform an independently certified PostgreSQL pre-send reservation, owner bound/approved strategy check, fees and margin check, daily max two entry attempts, existing position/orderbook reconciliation, current broker approved API entitlement, nonce fencing and protective exit recovery BEFORE signing. The browser MUST NOT be able to mint permits or submit arbitrary signed order payload.
- The V52 permit nonce ledger is an independent SQLite store, not the final PostgreSQL order/leader transaction. Do not assert it closes distributed reservation races or certifies protective stops.
- V51 website sends an owner ARM REQUEST that still fails closed due missing trusted production evidence. It does not send an order.
- No production broker order validation, write lifecycle certification, real order, protected deployment, service restart or Render→AWS TLS provisioning has occurred.

## Result
The unconditional **source-level** broker lock is replaced by a more granular cryptographically enforced permit gate, but real money orders are **still OFF by default**. The owner retains control over what they authorize, while broker/exchange permissions and safety preconditions remain separate facts.
