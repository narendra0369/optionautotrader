# OptionX V46 — Owner Live Unlock website control (review-only)

Owner request: add a website control they can click themselves to unlock real trading after successful V45 offline tests 17/17. This branch implements the UI and authenticated server-side gate inspection without creating a bypass. It does NOT enable real orders.

## Included
- `index.html`: Owner Live Unlock panel at top of existing Live Broker Setup page; prominent REAL ORDERS OFF, check button and disabled/unwired emergency STOP placeholder. No "LIVE ON" is asserted.
- `live_ui.mjs`: button calls authenticated `GET /api/v46/owner/live-unlock-status`. Reports fixed server reasons, uses safe textContent, no secrets or browser flags, no order call.
- `market_api.py`: reads Supabase authenticated user identity, requires owner match on server. No POST unlock route.
- `live_v7/owner_live_unlock_v46.py`: independently reads broker execution transport source-lock capability. Always blocks while source lock and production readiness are not independently certified.
- `live_v7/test_owner_live_unlock_v46.py`: 10 offline regression tests of owner binding, backend route, explicit no-send states.

## Important distinctions
- V41 read-only Angel verification was on AWS Lightsail, not Render's public market service. The Render backend has a different session and egress and cannot infer a live AWS order entitlement from old tests.
- The current `angel_execution_transport.py` unconditionally raises `LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION`.
- No production / Supabase schema migration, broker POST, manual position operation, live worker, source lock change, service restart, public deployment or production gating changes in this PR.
- An emergency STOP button should NEVER be fake: it stays disabled until an audited persistent stop endpoint exists. A browser toggle MUST NOT be treated as sufficient to enable real orders.
- Even if an owner accepts all risks, enabled live trading requires independent verified owner entitlement, production journal and risk controls, contract data freshness, ambiguous response reconciliation, and a final explicit exact-order consent.

## AWS isolated source checks
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-owner-unlock-v46
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v46-owner-live-unlock-ui-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
  test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo BLOCKED_LOCAL_CHANGES; exit 2; }
  sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_owner_live_unlock_v46 -q
echo V46_OWNER_UNLOCK_TEST_COMPLETE
BASH
```

Status: GitHub draft PR only. Nothing has been deployed to the live website; existing website will remain unchanged until a separately verified staging deploy. The button checks readiness only, not actual unlock.
