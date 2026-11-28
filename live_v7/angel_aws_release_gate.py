"""AWS V7 execution release inspection, strictly diagnostic and read-only.

This program cannot switch on trading, access credentials, or place orders.
It verifies deployed code layout, outbound IPv4 observations, worker presence,
the persistent ledger implementation gate, and *evidence* of broker approval.
An IP match alone must NEVER clear broker approval.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import subprocess
import urllib.request

REGISTERED_IP = "43.204.246.235"
REQUIRED_MODULES = (
    "angel_execution_transport.py", "angel_order_contracts.py",
    "angel_greeks_order_bridge.py", "angel_auto_atm.py",
    "angel_execution_rehearsal.py", "order_journal.py",
    "ledger_store.py", "kill_switch.py", "reconciliation.py",
    "protective_exit.py",
)
IP_ENDPOINTS = ("https://api.ipify.org", "https://ipv4.icanhazip.com")


def inspect_source(root: Path) -> dict:
    base = root / "live_v7"
    present = {module: (base / module).is_file() for module in REQUIRED_MODULES}
    return {"modules": present, "requiredModulesPresent": all(present.values()),
            "sourceLockPresent": (base / "angel_execution_transport.py").is_file()
            and "LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION"
            in (base / "angel_execution_transport.py").read_text(encoding="utf-8")}


def observed_egress(fetch=None) -> dict:
    def default_fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent":"OptionX-AWS-Audit/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read(48).decode("ascii").strip()
    fetch = fetch or default_fetch
    ips = []
    for url in IP_ENDPOINTS:
        try:
            raw = fetch(url)
            ip = ipaddress.ip_address(raw.strip())
            ips.append(str(ip) if ip.version == 4 and ip.is_global else None)
        except (OSError, ValueError, UnicodeError, TimeoutError):
            ips.append(None)
    agreed = bool(ips[0] and ips[0] == ips[1])
    return {"observedIps": ips, "observationsAgree": agreed,
            "registeredIp": REGISTERED_IP, "matchesRegisteredIp": agreed and ips[0] == REGISTERED_IP,
            "dedicatedEgressProven": False, "brokerRegistrationIndependentlyVerified": False}


def evaluate(*, source: dict, egress: dict) -> dict:
    # No data from an external diagnostic can grant orders.
    reasons = []
    if not source["requiredModulesPresent"]: reasons.append("REQUIRED_SOURCE_MISSING")
    if not egress["matchesRegisteredIp"]: reasons.append("OUTBOUND_IPV4_MISMATCH_OR_UNKNOWN")
    reasons.extend((
        "BROKER_ALGO_ORDER_PERMISSION_EVIDENCE_NOT_INSPECTED",
        "VAULT_AND_DURABLE_PRODUCTION_LEDGER_NOT_VERIFIED",
        "REAL_ORDER_ACK_AND_NATIVE_STOP_NOT_VERIFIED",
        "PARTIAL_FILL_NETWORK_RESTART_RECOVERY_NOT_VERIFIED",
        "LIVE_EXECUTION_WORKER_NOT_DEPLOYED_OR_CERTIFIED",
        "OWNER_LIVE_RISK_AUTHORIZATION_NOT_VERIFIED",
    ))
    return {"mode": "READ_ONLY_AWS_RELEASE_GATE",
            "source": source, "egress": egress,
            "blockedReasons": reasons, "canSubmitOrder": False,
            "canCancelOrder": False, "liveOrdersEnabled": False,
            "nextAction": "Verify broker permission and implement audited durable lifecycle before a separate live release."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only AWS OptionX execution release gate")
    parser.add_argument("--root", default="/opt/optionx-v7", help="Project candidate root")
    parser.add_argument("--skip-network", action="store_true")
    args = parser.parse_args()
    source = inspect_source(Path(args.root))
    egress = ({"observedIps": [], "observationsAgree": False,
               "registeredIp": REGISTERED_IP, "matchesRegisteredIp": False,
               "dedicatedEgressProven": False,
               "brokerRegistrationIndependentlyVerified": False}
              if args.skip_network else observed_egress())
    print(json.dumps(evaluate(source=source, egress=egress), indent=2))


if __name__ == "__main__":
    main()
