"""Guardrail regression for the persistent research-only watchdog systemd unit."""
from pathlib import Path
from unittest import TestCase


class SystemdPaperWatchdogSafetyTests(TestCase):
    def test_restricted_daemon_uses_no_network_and_no_orders(self):
        file=Path(__file__).resolve().parent/"systemd"/"optionx-paper-health-watchdog.service"
        text=file.read_text(encoding="utf-8")
        required=[
            "User=optionx", "Group=optionx",
            "NoNewPrivileges=true", "ProtectSystem=strict",
            "ProtectHome=true", "PrivateTmp=true", "PrivateDevices=true",
            "RestrictAddressFamilies=AF_UNIX",
            "ReadWritePaths=/var/lib/optionx-paper",
            "ReadOnlyPaths=/opt/optionx-v7",
            "ExecStart=/usr/bin/python3 -B -m ops.paper_health_watchdog --interval 30",
            "CapabilityBoundingSet=", "AmbientCapabilities="
        ]
        for assertion in required:
            self.assertIn(assertion, text)
        forbidden=["ANGEL_API_KEY","ANGEL_TOTP","placeOrder","market_api.py",
                   "live_gateway.py", "0.0.0.0", "AF_INET", "AF_INET6",
                   "ExecStartPre=/bin/bash -c", "User=root"]
        for unsafe in forbidden:
            self.assertNotIn(unsafe,text)
