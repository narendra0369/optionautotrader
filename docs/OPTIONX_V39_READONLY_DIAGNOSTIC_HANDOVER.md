# OPTIONX V39 staged read-only diagnostics — 26 Nov 2026

## Trigger
Owner ran V32 read-only FULL market quote and reported `V32_FULL_QUOTE_READ_ONLY: BLOCKED`, `V39_LIVE_READONLY_EXIT_CODE: 2` and `BROKER_ORDER_SUBMITTED: NO | REAL_ORDERS: OFF`. The V32 runner intentionally suppresses exceptions, so this output does **not** identify whether authentication, market books, manual position or quote parsing was responsible.

## V39 change
`live_v7/manual_full_quote_diagnostic_v39.py` reuses existing V32 approved owner-only read paths to identify only a coarse stage:
- CONFIG, AUTHENTICATION, POSITIONS_READ, ORDERS_READ, POSITION_CHECK, FULL_QUOTE, FEED_FRESHNESS
- Only sanitised position-check reasons: count, contract, token, quantity changed, active SELL conflict or unknown status. Does not print raw book rows, broker payloads, customer identifiers or secrets.
- V32 requires exact historical NIFTY29DEC2629000CE, token 38158 and quantity 65. A new account state legitimately fails the V32 guard.
- During or after market close, a quote timestamp may be stale. Freshness failure **never** triggers a live test order.
- No order send, cancellation, modification, production DB or service change. No actual technical/compliance entitlement certification.

## AWS command
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-diagnostic-v39
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v39-readonly-block-diagnostic-20261126
if [ ! -e "$DIR" ]; then sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD; fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_manual_full_quote_diagnostic_v39 -q
echo V39_AWS_OFFLINE_TEST_COMPLETE
'
```
Only after tests pass, the owner may separately run the owner-bound diagnostic in an interactive private terminal; credentials are entered only at the prompts and must never be posted in chat:
```bash
cd /opt/optionx-v7-diagnostic-v39 || exit 1
read -r -p "OptionX Owner UUID: " OWNER
read -r -p "Angel Client Code: " CLIENT
sudo -u optionx env OPTIONX_OWNER_USER_ID="$OWNER" \
 ANGEL_ALLOWED_CLIENT_CODE="$CLIENT" \
 ANGEL_EGRESS_PUBLIC_IPV4="43.204.246.235" PYTHONDONTWRITEBYTECODE=1 \
 /tmp/optionx-v19-pg-venv/bin/python -B \
 -m live_v7.manual_full_quote_diagnostic_v39
RC=$?
unset OWNER CLIENT
echo "V39_READONLY_DIAGNOSTIC_EXIT_CODE: $RC"
```

STOPPED production guard and immutable execution lock remain; no real order is authorized by this diagnosis. Manual position remains untouched. Any later live send requires a separately certified release and fresh exact-order user authorization.
