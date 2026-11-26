# OptionX V50 — Owner activation control, fail-closed

Owner confirms V49 corrected AWS 22/22 PASS. User requests all required work at once and self-service click-to-unlock real trading.

## Delivered code
- `live_v7/owner_activation_v50.py`: durable SQLite owner ARM/STOP control-plane with explicit owner verification, private filesystem permissions, 15-minute lease, expiry on restart, durable audit and independent production evidence predicates. Arming requires that `transport_is_source_locked is False` and 12 independently audited checks PASS. ARM alone NEVER submits a broker order or adopts manual holdings.
- `live_v7/owner_activation_coordinator_v50.py`: reads actual Angel transport source-lock capabilities. Existing AWS V41 was READ-ONLY, not WRITE certification. No trusted production evidence collector yet, so reports blockers and cannot activate.
- `index.html`, `live_ui.mjs`: Owner Live Setup UI with `Check Live Activation (Owner)` button, authenticated status retrieval and visible blockers; existing owner review and STOP placeholder controls remain.
- `market_api.py`: read-only `GET /api/v50/owner/activation-eligibility`, authenticated via Supabase and owner binding. It is currently a Render backend status, NOT the AWS engine. It cannot take browser readiness flags, and no POST /arm is exposed.
- `live_v7/test_owner_activation_v50.py`: 20 isolated control-plane tests.
- `live_v7/test_activation_wiring_v50.py`: 9 UI/auth/source lock tests.
- `.github/workflows/optionx-v50-validation.yml`: automatically runs 51 V49+V50 tests on matching pull requests and verifies source lock remains. This workflow is not guaranteed to execute until GitHub's own CI reports a run.

## Real order activation is NOT complete
**The source lock in `angel_execution_transport.py` remains active.** Backend and AWS worker are not deployed from this branch. Production PostgreSQL journal/transaction isolation, AWS TLS authenticated command channel, signed independent owner and broker write entitlement evidence, protect-stop/partial-fill/unknown broker lifecycle, and actual isolated write-path certification are unfinished. Render and AWS are separate hosts: a Render GET cannot silently ARM AWS.

Activation backend supports an ARMED *control state* only if a trusted caller supplies independently established production evidence and independently reviewed transport state; this branch provides neither broker POST nor a publicly callable ARM endpoint. Never expose these parameters to browser clients or override them by environment toggle.

The user should not be told clicking the new control will execute any real order. The historical 65-unit position is not adopted and the previous ₹10.50 LIMIT is not submitted.

## Non-destructive AWS test if needed
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-activation-v50
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v50-owner-activation-control-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || exit 2
 sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_lifecycle_worker_v49 live_v7.test_owner_activation_v50 live_v7.test_activation_wiring_v50 -q
echo 'V50_AWS_51_TESTS_COMPLETE'
BASH
```

No deployment, new credentials, secrets, risk order, broker interaction, production database change or service restart in this commit.
