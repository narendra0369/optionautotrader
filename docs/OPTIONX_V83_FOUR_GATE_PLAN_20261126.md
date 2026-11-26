# OPTIONX V83 Four-Gate Sequential Work Plan
2026-11-26 | OFFLINE DEVELOPMENT ONLY | NO DEPLOY

Basis: V82 master handover and operator's 19-PASS AWS local custody audit. New live read-only Supabase check: two pending proofs, one PENDING worker, zero VERIFIED workers, zero independent attestations. The database project is `yghijfzwsvmzaffllszl`.

## Gate 1 — Independent attestation
STATUS: BLOCKED BY REAL EXTERNAL VERIFIER.
Required: independent reviewer with verified separation from owner and host root, documented evidence custody, fresh challenge from independent verifier, trusted hardware/workload provenance or explicit limitation, binding to worker UUID and public key fingerprint, signed report, expiry <= 15 min, revocation and escalation.
Do not manufacture reviewer, attest from self-reported host checks, or promote the PENDING key. AWS root can impersonate a process.

## Gate 2 — Secure gateway
STATUS: OFFLINE REFERENCE POLICY IMPLEMENTED; NO DEPLOY.
`scripts/optionx_v83_offline_safety.py` exposes pure deny-by-default diagnostic scope evaluation. It has no network, database, secrets or broker imports. It denies order.place/order.cancel/order.modify and all unknown scopes, and never returns an order authorization.
Production design requires server-verified owner authentication, separate independent reviewer evidence, short-lived nonce+request signature, atomic nonce consumption, explicit per-call authorization, audit trail, revocation and STOP dominance. The existing V82 diagnostic SQL always returns canTrade=false/canReserve=false and must not be interpreted as an execution permit.

## Gate 3 — Risk and owner STOP
STATUS: OFFLINE STOP-INVARIANT MODEL IMPLEMENTED; NO DEPLOY.
Owner STOP is default. The paper tier stays unchanged: initial ₹30,000, +one lot per additional ₹40,000, paper risk ₹300/lot, target ₹600/lot, daily loss ₹600/lot. Global maximum 2 entries/day. Neither STOP clearing nor paper risk values can independently authorize live orders. V65 structural guard conflict remains untouched until reviewed in a separate nonproduction environment.

## Gate 4 — Broker lifecycle
STATUS: OFFLINE MODEL IMPLEMENTED; NO LIVE/API TEST.
Simulate partial fill, full fill, SL/target exit, cancel and reconciliation-required cases with a pure state machine. A broker-side order cannot be inferred from a simulator result. Manual positions are out of scope; no automatic reconciliation of manually held positions or real orders.

## Go/no-go
Gate 1 BLOCKED; Gate 2 OFFLINE ONLY; Gate 3 OFFLINE ONLY; Gate 4 OFFLINE ONLY.
All live BUY/SELL/CANCEL/MODIFY OFF. No AWS service changes, no Supabase changes, no migration, no permissions changes, no real broker API calls, no worker promotion. Completion requires actual offline test execution and an independent external review before any deploy.
