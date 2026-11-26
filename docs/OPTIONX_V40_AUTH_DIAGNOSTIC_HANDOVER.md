# OptionX V40 Auth Stage Diagnostic — 26 Nov 2026

## Ground truth from AWS
- V39 offline tests: user AWS output `Ran 13 tests ... OK`.
- V39 actual owner login attempt: `V39_DIAGNOSTIC: BLOCKED`, `V39_BLOCK_STAGE: AUTHENTICATION`; no orders submitted.
- AWS checks: expected public IPv4 `43.204.246.235`, Angel base HTTPS HTTP 200, Ubuntu IST clock coherent, existing market API service active.
- V40 local owner UUID/client syntax and account code match: `LOCAL_AUTH_CONFIG: PASS`.
- These checks rule out several local configuration errors, **not** PIN/TOTP validity, Trading API activation, profile match or broker login acceptance.

## Code
`live_v7/angel_auth_stage_diagnostic_v40.py` calls the existing read-only `verify_login` ONCE and intercepts only method/path labels for the existing allowlisted login/profile calls, never handles raw broker payload or secrets. Reports one of CONFIG, PRIVATE_INPUT, LOGIN_API or PROFILE_API; no PIN/TOTP/JWT/API key/response/exception echoed. A client-side stage label does NOT prove broker permission.
`live_v7/test_angel_auth_stage_diagnostic_v40.py`: 10 offline regression tests. Source-level execution lock and STOPPED guard preserved.

## AWS TEST first
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-auth-v40
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v40-auth-stage-diagnostic-20261126
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_angel_auth_stage_diagnostic_v40 -q
echo V40_AWS_OFFLINE_TEST_COMPLETE
'
```

## Single real owner read-only login (OPTIONAL, AFTER offline PASS)
No retries if blocked. Owner should use a fresh TOTP from the authorized authenticator, and ensure account security; enter private inputs ONLY into AWS SSH terminal. Do NOT enter credentials or print them in ChatGPT.
```bash
cd /opt/optionx-v7-auth-v40 || { echo "V40_DIRECTORY_MISSING"; false; }
read -rs -p "OptionX Owner UUID: " OWNER; echo
read -rs -p "Angel Client Code: " CLIENT; echo
sudo -u optionx env OPTIONX_OWNER_USER_ID="$OWNER" \
 ANGEL_ALLOWED_CLIENT_CODE="${CLIENT^^}" \
 ANGEL_EGRESS_PUBLIC_IPV4="43.204.246.235" PYTHONDONTWRITEBYTECODE=1 \
 /tmp/optionx-v19-pg-venv/bin/python -B \
 -m live_v7.angel_auth_stage_diagnostic_v40
RC=$?
unset OWNER CLIENT
echo "V40_AUTH_DIAGNOSTIC_EXIT_CODE: $RC"
```
No account credentials should be posted. Do not force repeated login or defeat broker rate limits. If LOGIN_API blocked, verify broker service, API key/PIN/fresh TOTP and contact support. If PROFILE_API blocked, check broker profile endpoint / app permissions with Angel support. Neither case permits real order testing. No live order send, modify, cancel or LPP auto retry.
