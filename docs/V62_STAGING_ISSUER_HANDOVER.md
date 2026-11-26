# OptionX V62 isolated issuer gate

This is an **incremental, fail-closed staging readiness evaluator**, not a production signing/dispatch issuer. No API endpoints, signing keys, or broker order methods are provided.

## Completed before V62

V57 owner-bound Angel read-only three-book verification, V58 PostgreSQL read-only recovery and manual exclusion, V59 (27) and V60 (24) offline targeted regressions, V61 isolated signing key compatibility and single-use nonce replay tests (per AWS terminal outputs). Do not rerun them without relevant changes.

## V62 new verification

`live_v7/staging_issuer_gate_v62.py` reports blockers for owner STOP, engine guard, activation evidence, manual exposure, two-trade limit, risk reservation, journal durability, leader fencing, fresh books, and required external attestations. All its inputs are *untrusted caller-provided values*. Even if all supplied flags are true, `canIssue`, `canSubmitOrder`, `canCancelOrder`, and `liveOrdersEnabled` remain **false**.

For 19 targeted offline regression tests, the separate downloadable V62 staging ZIP contains a standalone equivalent and a read-only AWS runner. The ZIP was tested locally; installation and AWS execution are separate.

## Not certified

Actual issuer deployment, durable production transaction across intent and risk, independent attestations, broker fills, native protective SL and unknown outcome recovery, static-IP whitelisting, Angel write entitlement and applicable algo compliance. Never activate real-order API while these remain unverified. Never touch manually held positions.
