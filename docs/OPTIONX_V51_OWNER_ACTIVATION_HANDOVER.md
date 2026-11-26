# V51: Owner-click activation request → signed AWS gate

User requests source-lock removal coding linked to a website button for their own operation. V51 implements the user-controlled **signed activation request** path, but **DOES NOT remove Angel's order-sending source lock or claim REAL ON**.

## Changes
- Owner button on Live Broker Setup is labeled `Owner Unlock / Activate Request`.
- `live_ui.mjs` now sends a POST to `/api/v51/owner/activate`. Browser sends only `{}` and a verified owner Supabase bearer session; no security predicate or broker secret is accepted.
- Render `market_api.py` authenticates owner, pins staging origin, rejects nonempty bodies, requires feature `OPTIONX_V48_CONTROL_RELAY_ENABLED` and HMAC-signs server-to-server request to fixed TLS AWS endpoint.
- V48 signature grammar now recognizes `REQUEST_ACTIVATE_LIVE` but its old STOP/review handler explicitly rejects the new action, preventing accidentally treating activation as STOP.
- AWS loopback receiver detects the dedicated activation action, opens a separate locked-down V50 activation DB and calls V51 `attempt_activation`.
- V51 checks owner UUID, signature, fixed fields, 30-second freshness and stores nonce durably. The eligibility evidence is AWS-owned, not browser supplied. Currently there is *no independently verified broker-write certification provider*: `_trusted_aws_evidence()` returns all False and Angel transport `sourceLockEnabled=True`. Therefore activation must return `BLOCKED`, even with an authenticated user and accepted signed command. The actual source-level write blocker remains.
- 16 offline V51 regression tests; GitHub Actions includes V49–V51 combined 67 unit tests.

## Exactly what remains to truly self-activate live trading
1. Independently provision the Render/AWS HMAC signing secret through encrypted service settings, TLS-reverse proxy/endpoint with host pinning, no publicly open AWS loopback listener. The actual Render and AWS services currently run different code and are NOT connected by this PR.
2. Produce independently verified broker WRITE-entitlement evidence and exact accepted order schema, approved static-IP control, authenticated tradebook/orderbook field mapping, real STOP enforcement, charges/margin checks, protective exits and crash-recovery.
3. Certified production PostgreSQL intent+quota transaction (V45 remains mock-only); verify actual simultaneous click races and leader fencing.
4. Only after audited certification should a controlled replacement for `angel_execution_transport.py` hard lock be released in a reviewed deployment with rollback. Changing one UI value or environment toggle is not sufficient.
5. Merge and deploy on approved staging services. No deployment performed; no secrets requested, no AWS worker restarted, no real orders sent.

## Safe local AWS regression
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-arm-v51
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v51-owner-click-activation-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo BLOCKED_LOCAL_CHANGES; exit 2; }
 sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_owner_arm_command_v51 -q
echo V51_OWNER_ACTIVATION_16_TESTS_COMPLETE
BASH
```
