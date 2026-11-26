# OptionX V47 — durable control-plane foundation, not real execution

Owner explicitly requests one-click live trading from website after V46 AWS 10/10 PASS. This branch builds the durable local owner STOP/review state for a future AWS execution service. It DOES NOT unlock or send real broker orders.

## Files
- `live_v7/owner_control_store_v47.py`: private (0700 dir, 0600 SQLite) transactional durable owner control state, audit trail; any new owner defaults STOPPED. Owner review requests remain STOPPED, emergency STOP persists across process restart, owner digest partitioning, fail-closed.
- `live_v7/test_owner_control_store_v47.py`: 16 isolated tests including restart, audit, access denial, permissions and no broker transport.
- No modification to production `optionx_private.engine_guard`, no Render/AWS deployment, no switch to live orders.

## Why one-click real activation is not yet complete
1. Existing Angel real-order transport `live_v7/angel_execution_transport.py` ends in unconditional source-level blocking, even when caller flags are true.
2. Website is served via Render and accesses Render's public market API; brokerage and whitelisted static egress have been observed on a separate AWS machine. A status button on Render is not an authenticated order-authorization channel to AWS.
3. V45 mock PostgreSQL tests passed but no real PostgreSQL staging concurrency or production durable journal has been certified. STOPPED guard remains.
4. No executed broker-side ACK/TradeBook lifecycle has been verified. Manual NIFTY position is not OptionX-owned and must not be silently adopted.
5. Broker approval email was supplied by owner; live write entitlement not independently observed.

The correct deployment needs an authenticated owner command channel to the AWS worker (mTLS or comparable), an independently audited durable production database journal, live broker lifecycle certification, risk limits and an effective persistent STOP. The user then initiates specific owner-authorized trade intent via website; an emergency STOP must actually fence worker orders. Source lock should not be removed by browser-only state.

## AWS offline tests only
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-control-v47
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v47-owner-control-persistence-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo BLOCKED_LOCAL_CHANGES; exit 2; }
 sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_owner_control_store_v47 -q
echo V47_AWS_16_TESTS_COMPLETE
BASH
```

Passing does not certify live execution. No attempt should be made to turn on real broker orders from this module.
