# OPTIONX V48 — Render-to-AWS owner command channel, default STOPPED

Owner confirmed V47 AWS 16/16 PASS and requested the missing web-to-AWS control channel and production worker. V48 is a substantial control-plane integration, but **NOT an enabled production trading system** and must never be described as such.

## Code components
- `live_v7/signed_owner_commands_v48.py`: HMAC-SHA256 canonical request, strict owner UUID/action, 30-second timestamp window, one-time nonce persisted under same private SQLite atomic transaction as control state, rejects duplicate/altered/replayed commands.
- `live_v7/aws_control_receiver_v48.py`: local-only AWS receiver on 127.0.0.1:8766; dedicated owner and restricted private DB store; no CORS, credential printing, broker SDK or order POST. NOT reachable by Render until a trusted HTTPS reverse proxy and pinned host are established.
- `live_v7/render_aws_relay_v48.py`: HTTPS-only server-to-server command signature and 7s bounded response handling, no bearer sent to AWS, only explicitly verified owner can sign.
- `market_api.py`: V48 owner request route, strict V7 staging Origin, Supabase Auth owner matching, feature OFF by default. Accepts ONLY exact empty JSON and fixed REQUEST_UNLOCK_REVIEW; no browser command choice, order payload or key.
- `live_ui.mjs`, `index.html`: Request Owner Unlock Review button. Explicitly says REALL ORDERS OFF even after AWS ACK.
- `live_v7/test_signed_owner_commands_v48.py`: 17 isolated tests.
- `live_v7/test_render_aws_relay_v48.py`: 16 isolated tests.

## Critical deployment constraints
- NONE of these services are deployed automatically. No AWS reverse proxy configured, no secret signing key provisioned, no production journal integration, no broker order transport enabled, no Supabase guard change. This is a draft GitHub branch.
- Never set `OPTIONX_V48_CONTROL_RELAY_ENABLED=1` without staging-only endpoint TLS cert, private trusted backend-to-AWS connectivity, same unique shared 256-bit secret on both server vaults (never Git/browser), owner-ID verification, replay/clock testing, and careful isolation from real order operations. Do not use simple public port forwarding to port 8766.
- Review request changes the private control journal to REVIEW_REQUESTED with `stopped=1`. It is NOT ARM/START. Emergency STOP method exists internally but has no connection to live broker service, so website button stays disabled.
- Existing Angel transport source lock remains; production PostgreSQL has STOPPED guard; no real orders sent, manual 65-unit NIFTY untouched. Render shared egress is distinct from broker approved AWS egress.
- Actual production worker requires a separately reviewed broker write adapter, owner-only exact contract, limits, broker-approved route/type, durable PostgreSQL intent and recovery, broker ACK/TradeBook matching and protective exit handling. A checkbox cannot substitute for this.

## AWS safe offline tests
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-channel-v48
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v48-owner-signed-commands-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo BLOCKED_LOCAL_CHANGES; exit 2; }
 sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_signed_owner_commands_v48 live_v7.test_render_aws_relay_v48 -q
echo V48_AWS_33_TESTS_COMPLETE
BASH
```

These tests use fake HTTP and SQLite in temp dirs only; they do not contact real broker/Render/production DB.
