# OptionX — AWS Mumbai bootstrap (safe research mode only)

## State and boundaries
- AWS Lightsail Linux/Ubuntu host exists in Mumbai in the **Fresh Deploy** workload account.
- Separate AWS Budget notifications exist in the management account.
- Static IPv4 is attached to the Lightsail host.
- **Backend has NOT yet been installed on the host**. GitHub CI passing is not proof of a running AWS backend.
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
python3 -m ops.verify_angel_aws_readiness --expected-ip YOUR_STATIC_IPV4
```

Do not register a possibly incorrect IPv4 with the broker; Angel One limits how often a registered primary IP may be changed. The output `AWS_PRECHECK_PASSED` is only a prerequisite to *app/IP registration*, **not** broker API trading approval. Confirm registration in your own official SmartAPI portal, without putting API keys, OTP, PIN or private SSH keys in chats, code or GitHub.

## Network and later integration

Lightsail public TCP 80 and 22 were observed open during audit; the GUI firewall edit did not save. Restrict unnecessary inbound rules with AWS Lightsail networking controls before exposing a public HTTP service. Keep SSH access until there is a verified alternative.

Do not connect the hosted V7 frontend directly to an HTTP IPv4 endpoint: browsers will block mixed content and the public host would lack HTTPS, authentication/rate-limit hardening and consented service publication. Set up a domain + TLS reverse proxy, CORS allowlist, service isolation, health monitoring and recovery tests first.

Real-money broker placement remains hard-locked. Read-only tests do not authorize opening live trading.
