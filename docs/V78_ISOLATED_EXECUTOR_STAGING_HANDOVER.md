# OPTIONX V78 — Execution identity staging

## Scope
- Existing five OPTIONX systemd units are checked active before and after installation. None is edited, stopped, restarted or re-enabled.
- A separate non-login `optionx-executor` Linux user/group is created with no supplementary groups, no home directory.
- A new `optionx-v78-executor-staging.service` runs a **deny-only heartbeat process** as that user.
- Network is disabled by PrivateNetwork=yes, IPAddressDeny=any and RestrictAddressFamilies=AF_UNIX.
- Service filesystem is read-only; no broker credentials, PostgreSQL credentials, auth secrets or environmental files.
- Service is started but not enabled at boot. Repeat installs refuse an unrelated preexisting unit.
- The staged worker cannot place, modify or cancel an order and cannot reserve risk.

## To execute
Run `sudo bash scripts/install_optionx_v78_isolated_executor.sh` only from a trusted checkout containing the verified V78 branch. The repository is private; downloading via unauthenticated raw.githubusercontent URLs is not supported.

## Expected
V78_ISOLATED_SETUP_COMPLETE
PASS: FIVE_EXISTING_SERVICES_STILL_ACTIVE
PASS: V78_ISOLATED_STAGING_STARTED

## Still blocked
- Supabase optionx_execution_worker remains NOLOGIN; no AWS worker-to-DB attestation or scoped grant exists.
- Live execution remains OFF with Owner STOP. Previous manual broker position is untouched.
- Production restart, recovery, broker regulatory approval and exact protective stop implementation are not certified.

This is **real host preparation** when executed on AWS, not proof that an execution engine or broker write route is live.
