# OptionX Mumbai Lightsail — secure research backend rollout

Target: **Fresh Deploy** AWS account; **Mumbai (ap-south-1)**; existing Ubuntu instance `optionx-trading-server`.

This is a **local-only read-only/paper research** service, **not a production trading broker integration**. It cannot place BUY/SELL orders.

## Deploy to the existing server
Open **Connect using SSH** in AWS Lightsail as `ubuntu`, then paste:

```bash
curl -fsSL https://raw.githubusercontent.com/narendra0369/optionautotrader/optionx-aws-mumbai-bootstrap-20261124/ops/bootstrap_aws_mumbai.sh -o /tmp/optionx-bootstrap.sh && bash -n /tmp/optionx-bootstrap.sh && sudo bash /tmp/optionx-bootstrap.sh && curl -fsS --max-time 8 http://127.0.0.1:10000/health
```

The script **refuses to overwrite** an existing `/opt/optionx-v7` or `optionx-market-api.service`. It runs tests before enabling a systemd service, creates non-login user `optionx`, and binds Python HTTP only to `127.0.0.1:10000`. It does not change firewall rules, broker credentials, domain, DNS or public HTTPS.

Success requires ALL markers:
- `OPTIONX_PRECHECK_PASSED`
- `OPTIONX_LOCAL_HEALTH_PASSED; real orders remain OFF`
- `OPTIONX_BOOTSTRAP_COMPLETE`
- `/health` JSON includes `"paperOnly":true`, `"liveOrdersEnabled":false`.

If markers are missing, do not rerun blindly. Check service status and installer output.

## Verify or stop

```bash
sudo systemctl status optionx-market-api --no-pager
curl --fail --silent --show-error http://127.0.0.1:10000/health
```

To stop without deleting data:

```bash
sudo systemctl disable --now optionx-market-api
```

## Safeguards
- Organization $20 monthly AWS cost Budget has alerts at 85% actual, 100% actual and 100% forecast, but is **not a hard spending limit**.
- Tested V7 frontend and backend remain on Render, untouched.
- No broker login secret, external API service port, live trading permission, or real order route enabled.
- 1GB Mumbai server is intended for light API checks, not 200k-strategy server-side backtests.
- GitHub Actions CI verifies source syntax, offline unit tests, localhost health and 423 hard-lock. It does **not** verify AWS deployment unless the SSH script runs and returns the markers.
