# OPTIONX V32 — Owner-bound FULL quote depth (26 Nov 2026)

## Starting point
V30 AWS owner-authenticated manual position check PASS: 65 long NIFTY29DEC2629000CE, token 38158, LTP snapshot 10.80, SELL LIMIT 10.50 draft; no orders sent. V31 AWS mock risk tests 18/18 PASS. Neither certifies live SELL.

## V32
Adds `live_v7/manual_full_quote_readonly_v32.py`, using only Angel's documented POST `/rest/secure/angelbroking/market/v1/quote` with `mode: FULL` and exact NFO token. Angel FULL mode documents top-five depth, `exchFeedTime` and last trade price. Parser checks instrument/token/market depth, quote age and bid vs limit. No order endpoints, cancel endpoints, execution transport imports or production deployments.

Broker-reported `exchFeedTime` is **NOT independently authenticated exchange feed time**. The server can see time-of-receipt, not prove quote execution, entitlement, tick size, LPP or accurate all-in fees. Do not conflate `bestBid >= limit` with fill guarantee; displayed quantity can change.

The isolated V32 reader requires owner authentication and a renewed position/orderbook read; an active sell or changed quantity blocks preview. It never automatically adopts owner manual positions.

## Run AWS safely
AWS existing /opt/optionx-v7 checkout is root-owned; avoid git without sudo. Execute from existing Ubuntu SSH terminal:

```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-depth-v32
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v32-full-market-quote-readonly-20261126
if [ ! -e "$DIR" ]; then sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD; fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_manual_full_quote_readonly_v32 -v
echo V32_AWS_OFFLINE_TEST_COMPLETE
'
```

Only after offline PASS, run read-only owner-authenticated quote (do not paste secrets in chat):

```bash
cd /opt/optionx-v7-depth-v32
read -r -p "OptionX Owner UUID: " OWNER
read -rs -p "Angel Client Code: " CLIENT
echo
sudo -u optionx env OPTIONX_OWNER_USER_ID="$OWNER" \
 ANGEL_ALLOWED_CLIENT_CODE="$CLIENT" \
 ANGEL_EGRESS_PUBLIC_IPV4="43.204.246.235" \
 PYTHONDONTWRITEBYTECODE=1 \
 /tmp/optionx-v19-pg-venv/bin/python -B \
 -m live_v7.manual_full_quote_readonly_v32
RC=$?
unset OWNER CLIENT
echo V32_READ_ONLY_EXIT_CODE:$RC
```

Full quote API failures are safe blockers, not permission to alter order or use stale/fallback prices. Never enable Real Orders from V32 PASS. A separate complete certification and fresh exact-order owner authorization remain prerequisites.
