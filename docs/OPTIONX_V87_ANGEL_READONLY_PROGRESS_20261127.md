# OPTIONX V87 — Angel One read-only reconciliation upgrade (2026-11-27)
Branch: optionx-v87-angel-reconcile-readonly-20261127. Not merged, not deployed to AWS/Render. No credentials required or requested.
- New: scripts/optionx_v87_angel_reconcile.py
- New: tests/test_optionx_v87_angel_reconcile.py
- Reuses the already-existing live_v7/angel_books_readonly.py read_three_books result shape, without importing or calling a broker. The existing broker snapshot uses the owner-verified short-lived RAM session and GET-only resources.
- The checker identifies missing/stale books, missing authenticated owner/transport, unknown order status, unmatched/manual active orders, manual position exposure, bad quantities and unavailable fill ID proof.
- Never places, sells, cancels or modifies orders. All permissions returned False; recoveryCertified False.
- Existing tradebook adapter provides only row count, not order-linked trade IDs, so even a valid three-book response cannot certify fill recovery. That mapping needs a separate authorized read-only implementation and tests.
- Current live V81 worker remains PENDING, owner STOP remains enforced and no live risk policy exists. Do not bypass any of these for deployment.
- Operator offline test: git fetch branch, run `python3 -m unittest -v tests/test_optionx_v87_angel_reconcile.py` from repo root; tests are pure offline and have no broker imports or network calls.
- Development environment's independently built equivalent model passed 14/14 offline unit tests; GitHub deployment/CI tests still must run against the committed code to attest that exact source.
- Integrating checker into owner-only broker route should be separately reviewed so browser-provided flags, timestamps or snapshots cannot be treated as trusted.
Next certification steps: authenticated broker fresh Order/Trade/Position Book (without sharing secrets), order-linked fill normalization and manual position isolation, non-prod lifecycle recovery tests, independently approved workload/risk authorization, explicit STOP-state transition design.
