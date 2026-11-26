# OptionX V45 — production-oriented PostgreSQL integration, ISOLATED STAGING ONLY

V44 read-only reconciliation tests 18/18 PASS on AWS according to the owner's returned output. Production order transport is source-locked, Supabase engine_guard is STOPPED; do not alter either.

## Code delivered
1. `migrations/staging/optionx_v45_execution_stage.sql`: independent schema `optionx_exec_stage` (NOT `optionx_private`), table guard with default STOPPED and explicit MOCK_ONLY only, plus durable order_intents and append-only event table. Migration is NOT applied anywhere.
2. `live_v7/postgres_mock_execution_v45.py`: transactional Python adapter with SERIALIZABLE, owner guard row FOR UPDATE, deterministic payload hash, unique key, database commit before returning, no resends, irreversible unknown seal, rollback on error. Mock-only state is rejected by actual production guard since it's outside the production schema; returns canSubmitOrder False.
3. `live_v7/test_postgres_mock_execution_v45.py`: 17 isolated fake-connection unit tests. These tests verify query ordering and negative gates, NOT database isolation/locking under actual PostgreSQL concurrency.

## AWS isolated offline validation (NO DB OR BROKER CONNECTION)
```bash
bash <<'BASH'
set -e
echo '=== OPTIONX V45 POSTGRES STAGING ADAPTER TEST ==='
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-pg-v45
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v45-postgres-reservation-staging-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo 'BLOCKED_LOCAL_CHANGES'; exit 2; }
 sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_postgres_mock_execution_v45 -q
echo '=== V45_AWS_17_TESTS_COMPLETE ==='
BASH
```

## IMPORTANT production gap
- Actual staging PostgreSQL DB must be created with separate credentials and explicit non-production provisioning authorization; no migration applied to production. Validate database transactions and concurrency with real Postgres before considering deployment.
- No code in V45 is connected to live transport or read-only broker RAM session. No trades, cancels, broker request tests, existing service restarts or user manual position modifications.
- The mock schema and method cannot enable running real orders. Real permissions and precise order consent still need a separate audited release.
- Existing broker execution transport currently supports BUY LIMIT and SELL STOPLOSS_LIMIT only, **NOT SELL LIMIT** (manual 65-unit exit), so it is not safe to claim that historical LIMIT preview can be sent. A separately validated order-type contract and broker lifecycle is required.
