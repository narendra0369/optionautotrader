# OptionX — AWS Mumbai bootstrap (safe research mode only)

## State and boundaries
- AWS Lightsail Linux/Ubuntu host exists in Mumbai in the **Fresh Deploy** workload account.
- Separate AWS Budget notifications exist in the management account.
- Static IPv4 is attached to the Lightsail host.
- **2026-11-24 verified on host**: Backend installed at `/opt/optionx-v7`; `optionx-market-api.service` active, `http://127.0.0.1:10000/health` returned `status=ok`, `paperOnly=true`, `liveOrdersEnabled=false`, and port `10000` bound to `127.0.0.1` only. User reported the four independent `ops.verify_angel_aws_readiness` prechecks passing (including matching observed outbound IPv4 to attached Lightsail static IPv4). Broker SmartAPI App creation was reported complete; registration/status cannot be independently verified by this runbook. This is NOT production HTTPS/public deployment or approval for real orders.
- Do **NOT** deploy live order code, copy broker credentials to SSH, open API ports, or alter the existing Render production services.
- Public IP / account details are intentionally not committed to this public repository.

## Bootstrap from the instance's authenticated Ubuntu SSH shell

Check the host is the intended Lightsail instance before doing anything. The command below downloads a reviewed, isolated-branch script pinned to the known GitHub commit. Inspect it in the browser before execution if desired.

```bash
curl --fail --silent --show-error --location --max-time 20 \
  'https://raw.githubusercontent.com/narendra0369/optionautotrader/e8572807e35197f927d95a0026f0cf29ac0e7cae/ops/bootstrap_aws_mumbai.sh' \
  -o /tmp/optionx-aws-bootstrap.sh
sudo bash /tmp/optionx-aws-bootstrap.sh
```

The bootstrap preserves any previous `/opt/optionx-v7` or `optionx-market-api.service` installation. It fails closed rather than overwriting existing code.

## Check results

```bash
sudo systemctl is-enabled optionx-market-api
sudo systemctl is-active optionx-market-api
curl --fail --silent --show-error http://127.0.0.1:10000/health
sudo ss -ltnp | grep ':10000'
```

Expected `/health`: `"status":"ok"`, `"paperOnly":true`, `"liveOrdersEnabled":false`. The HTTP service should listen only on `127.0.0.1:10000`. Do not add an inbound Lightsail firewall rule for port 10000.

## Angel One registered IPv4 verification (run after backend installation)

Run the following check only on this instance, using the static IPv4 currently attached in Lightsail Networking. This compares actual outbound IPv4 with the intended registered primary IPv4, ensures the local backend remains paper-only and denies unauthenticated Angel data and live orders. It **does not** connect to Angel One or place orders.

```bash
cd /opt/optionx-v7
sudo -u optionx /usr/bin/python3 -B -m ops.verify_angel_aws_readiness --expected-ip YOUR_STATIC_IPV4
```

Do not register a possibly incorrect IPv4 with the broker; Angel One limits how often a registered primary IP may be changed. The output `AWS_PRECHECK_PASSED` is only a prerequisite to *app/IP registration*, **not** broker API trading approval. Confirm registration in your own official SmartAPI portal, without putting API keys, OTP, PIN or private SSH keys in chats, code or GitHub.

## Network and later integration

Lightsail public TCP 80 and 22 were observed open during audit; the GUI firewall edit did not save. Restrict unnecessary inbound rules with AWS Lightsail networking controls before exposing a public HTTP service. Keep SSH access until there is a verified alternative.

Do not connect the hosted V7 frontend directly to an HTTP IPv4 endpoint: browsers will block mixed content and the public host would lack HTTPS, authentication/rate-limit hardening and consented service publication. Set up a domain + TLS reverse proxy, CORS allowlist, service isolation, health monitoring and recovery tests first.

Real-money broker placement remains hard-locked. Read-only tests do not authorize opening live trading.

## Verified remediation and safe next steps (2026-11-24)

- The initial host install passed all 137 backend tests but the unprivileged systemd service crashed because the staged source files were not group-readable. The repair granted the existing `optionx` service group read access and restarted the service; health then passed. The isolated bootstrap script now installs the directory as `root:optionx` with group-readable files (fix commit `05922579120a76cfca53c8fdb0494753202c84d0`). **Do not re-run the one-time installer on an existing host**.
- The read-only static-IP verification command must run as `optionx`, not `ubuntu`, since the source directory is intentionally restricted. All four safety checks were observed passing, including outbound IPv4 match and unauthenticated 401.
- The existing public V7 frontend/backend currently runs on **Render**, not from this Lightsail instance. Render's backend egress is not established to be the broker-whitelisted AWS Mumbai static IPv4. Do not send broker credentials through a Render frontend-to-Render backend login as proof of AWS egress; do not enable order routes.
- Next: independently inspect the SmartAPI My Apps registered primary IP and app status; create an explicitly authenticated, rate-limited HTTPS path to the AWS-hosted API using a user-owned domain with verified DNS/TLS or a temporary developer-only SSH tunnel. Maintain localhost-only binding until the HTTPS gateway is proven safe. Require configured owner-binding, request origin checks, short sessions, and no broker secret logging/storage. Never paste API keys/PIN/TOTP into chat, GitHub, or publicly readable URLs.
- After read-only quote checks from the AWS egress (not Render), perform paper-only end-to-end validation with no order execution. Broker API and exchange permissions, full trading risk controls and recovery/lifecycle testing remain distinct, blocking items before any future real-order deployment.
