"""Check Angel One AWS static-IP prerequisites without broker login or orders.

Run only on the intended Lightsail instance, after localhost research API installation.
This script does not contact Angel One or send any trading order.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import urllib.error
import urllib.request

HEALTH = "http://127.0.0.1:10000/health"
ORDERS = "http://127.0.0.1:10000/api/live/orders"
ANGEL_STATUS = "http://127.0.0.1:10000/api/brokers/angel/status"
IPV4_SERVICE = "https://api.ipify.org"

class ReadinessError(RuntimeError):
    pass

def _read(url: str, opener=None):
    get = opener or urllib.request.urlopen
    try:
        with get(urllib.request.Request(url, headers={"User-Agent": "OptionX-AWS-Readiness/1.0"}), timeout=10) as response:
            return response.getcode(), response.read(1025)
    except urllib.error.HTTPError as err:
        return err.code, err.read(1025)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ReadinessError("UNREACHABLE: " + url.split("/")[2]) from exc

def _json(data):
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReadinessError("INVALID_RESPONSE") from exc

def verify(expected_ip: str, opener=None):
    try:
        expected = ipaddress.ip_address(expected_ip)
    except ValueError as exc:
        raise ReadinessError("EXPECTED_IPV4_INVALID") from exc
    if expected.version != 4 or not expected.is_global:
        raise ReadinessError("EXPECTED_IPV4_NOT_GLOBAL")
    code, body = _read(IPV4_SERVICE, opener)
    if code != 200:
        raise ReadinessError("IPV4_LOOKUP_FAILED")
    try:
        observed = ipaddress.ip_address(body.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReadinessError("IPV4_LOOKUP_INVALID") from exc
    if observed != expected:
        raise ReadinessError(f"EGRESS_IPV4_MISMATCH: expected={expected} actual={observed}")
    print("PASS: server egress IPv4 matches attached AWS static IP")

    code, body = _read(HEALTH, opener)
    status = _json(body)
    if code != 200 or status.get("status") != "ok" or status.get("paperOnly") is not True or status.get("liveOrdersEnabled") is not False:
        raise ReadinessError("LOCAL_RESEARCH_BACKEND_NOT_SAFE")
    print("PASS: localhost research backend healthy and paper-only")

    code, body = _read(ORDERS, opener)
    payload = _json(body)
    if code != 423 or payload.get("error") != "REAL_ORDERS_HARD_LOCKED" or payload.get("orderSent") is not False:
        raise ReadinessError("REAL_ORDER_GATE_NOT_LOCKED")
    print("PASS: real-order endpoint remains hard-locked")

    code, _ = _read(ANGEL_STATUS, opener)
    if code != 401:
        raise ReadinessError("ANGEL_ACCOUNT_STATUS_PUBLICLY_EXPOSED")
    print("PASS: Angel account status requires authentication")

    print("AWS_PRECHECK_PASSED: safe to propose this IPv4 for SmartAPI app registration")
    print("NOTE: This is NOT trading approval; broker-whitelisting and independent lifecycle tests remain pending.")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Check public egress IPv4 and local Angel safety gates, with no orders")
    parser.add_argument("--expected-ip", required=True, help="AWS Lightsail static public IPv4; not a secret")
    args = parser.parse_args(argv)
    try:
        verify(args.expected_ip)
    except ReadinessError as exc:
        print(f"AWS_PRECHECK_BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
