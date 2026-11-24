"""OptionX private, read-only PAPER dashboard over an SSH tunnel.

No broker connections, account credentials, live-order endpoints, POST handlers,
web auth, public listen socket, JavaScript, or CDNs. Access only through the
operator's own local SSH port-forward. Not a public HTTPS production dashboard.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pwd
from zoneinfo import ZoneInfo

from ops.paper_ledger_v1 import DB_PATH, PaperError, status as paper_status

IST = ZoneInfo("Asia/Kolkata")
BIND_HOST = "127.0.0.1"
BIND_PORT = 10001
PUBLIC_TUNNEL_PORT = 18751
_ALLOWED_HOSTS = {
    "127.0.0.1:18751", "localhost:18751",
    "127.0.0.1:10001", "localhost:10001",
}
_CSS = """
:root{color-scheme:dark;--bg:#0b111b;--panel:#151e2b;--card:#1b2636;
--text:#f3f5f8;--muted:#96a3b5;--line:#2a3749;--gold:#d8bd86;
--gain:#58c49b;--loss:#f08384}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}
main{max-width:1130px;margin:auto;padding:28px 18px 60px}
header{display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;align-items:center}
.brand{font-size:24px;letter-spacing:.01em;font-weight:650}
.brand span{color:var(--gold)}.pill{padding:7px 11px;background:#273245;border:1px solid #54606d;color:var(--gold);border-radius:999px;font-size:12px;letter-spacing:.04em}
h1{font-size:27px;font-weight:600;margin:34px 0 6px}
.subtitle{color:var(--muted);font-size:13px;margin:0 0 22px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.label{font-size:12px;color:var(--muted);margin-bottom:8px}
.value{font-size:25px;font-weight:650;letter-spacing:-.02em}
.gold{color:var(--gold)}.gain{color:var(--gain)}.loss{color:var(--loss)}
.section{margin-top:18px}.section h2{font-size:17px;font-weight:600;margin:0 0 15px}
table{width:100%;border-collapse:collapse;font-size:13px;text-align:left}
th{color:var(--muted);font-weight:450}th,td{padding:12px 8px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0} .scroll{overflow-x:auto}
.caution{margin:22px 0;padding:14px 16px;border-left:3px solid var(--gold);background:#1d2632;border-radius:8px;color:#c5cbd5;font-size:13px}
footer{color:var(--muted);font-size:12px;margin-top:28px}
@media(max-width:740px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}
main{padding:18px 12px 35px}.value{font-size:21px}h1{font-size:22px}table{min-width:650px}}
"""


def _escape(value):
    return html.escape(str(value if value is not None else "—"), quote=True)


def _money(value):
    try:
        d = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return "N/A"
    if not d.is_finite():
        return "N/A"
    return "₹" + f"{d:,.2f}"


def _short(value, maximum=80):
    value = str(value if value is not None else "—")
    return value[:maximum]


def paper_observation_health(snapshot: dict | None, *, now=None) -> dict:
    """Audit ONLY the age of a *local* indicative price observation.

    An observed LTP is never proof of execution-grade freshness or an
    exchange native SL. Any open position with unknown/stale input is
    explicitly marked UNMONITORED, not implicitly healthy.
    """
    now = now or datetime.now(timezone.utc)
    position = (snapshot or {}).get("openPosition")
    if not isinstance(position, dict):
        return {"state": "NO_POSITION", "ageSeconds": None, "protectedByBroker": False,
                "continuousMonitoringVerified": False}
    observed = position.get("last_observed_utc")
    try:
        stamp = datetime.fromisoformat(observed)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("missing timezone")
        seconds = (now - stamp.astimezone(timezone.utc)).total_seconds()
        if seconds < 0 or seconds > 120:
            raise ValueError("stale or future observation")
    except (TypeError, ValueError):
        return {"state": "STALE_OR_UNKNOWN_LOCAL_LTP", "ageSeconds": None,
                "protectedByBroker": False, "continuousMonitoringVerified": False}
    return {"state": "RECENT_LOCAL_LTP_ONLY", "ageSeconds": int(seconds),
            "protectedByBroker": False, "continuousMonitoringVerified": False}


def make_view(snapshot: dict | None = None, *, error: str | None = None, now=None) -> str:
    """Server-rendered HTML; escapes broker symbols and ledger fields."""
    now = now or datetime.now(timezone.utc)
    current = now.astimezone(IST).strftime("%d %b %Y • %I:%M:%S %p IST")
    snapshot = snapshot or {}
    plan = snapshot.get("paperPlan") or {}
    capital = _money(snapshot.get("initialCapitalINR")) if not error else "Not available"
    equity = _money(snapshot.get("realizedEquityBeforeChargesINR")) if not error else "Not available"
    pnl_value = snapshot.get("todayGrossPnlBeforeChargesINR", "0")
    pnl = _money(pnl_value) if not error else "Not available"
    try:
        pnl_class = "gain" if Decimal(str(pnl_value)) >= 0 else "loss"
    except (ValueError, InvalidOperation, TypeError):
        pnl_class = ""
    count = str(snapshot.get("tradesToday", "0")) if not error else "—"
    max_trades = str(snapshot.get("maxTradesPerDay", "2"))
    observation = paper_observation_health(snapshot, now=now)
    observer_warning = ""
    if observation["state"] == "STALE_OR_UNKNOWN_LOCAL_LTP":
        observer_warning = (
            '<div class="caution">PAPER POSITION NOT MONITORED: The last local LTP '
            'observation is over 120 seconds old or unverified. No real stop '
            'or automatic protective exit is active. Check the operator SSH session.</div>'
        )
    elif observation["state"] == "RECENT_LOCAL_LTP_ONLY":
        observer_warning = (
            '<div class="caution">Recent local LTP observation only. '
            'Continuous monitoring and broker protective stops remain unverified.</div>'
        )
    position = snapshot.get("openPosition")
    position_html = ('<p class="subtitle">No open virtual position. There are no real broker holdings here.</p>')
    if isinstance(position, dict):
        symbol = _escape(_short(position.get("symbol")))
        lot = _escape(position.get("lots"))
        quantity = _escape(position.get("quantity"))
        entry = _escape(position.get("indicative_entry"))
        stop = _escape(position.get("illustrative_stop"))
        target = _escape(position.get("illustrative_target"))
        quote = _escape(position.get("last_quote"))
        seen = _escape(_short(position.get("last_observed_utc")))
        position_html = (
            '<div class="scroll"><table><thead><tr>'
            '<th>Option contract</th><th>Lots / Qty</th><th>Entry LTP</th>'
            '<th>Virtual SL</th><th>Virtual Target</th><th>Last LTP</th><th>Observed UTC</th>'
            '</tr></thead><tbody><tr>'
            f'<td>{symbol}</td><td>{lot} / {quantity}</td><td>₹{entry}</td>'
            f'<td>₹{stop}</td><td>₹{target}</td><td>₹{quote}</td><td>{seen}</td>'
            '</tr></tbody></table></div>'
        )
    rows = []
    for record in snapshot.get("recentTrades", [])[:10]:
        if not isinstance(record, dict):
            continue
        rows.append(
            "<tr>"
            f'<td>{_escape(_short(record.get("symbol"), 75))}</td>'
            f'<td>{_escape(record.get("status"))}</td>'
            f'<td>{_escape(record.get("quantity"))}</td>'
            f'<td>{_escape(record.get("opened_utc"))}</td>'
            f'<td>{_escape(record.get("close_reason"))}</td>'
            f'<td>{_escape(_money(record.get("gross_pnl")))}</td>'
            "</tr>"
        )
    history = "".join(rows) if rows else '<tr><td colspan="6">No virtual trades recorded yet.</td></tr>'
    error_notice = ('<div class="caution">Paper journal unavailable. Dashboard is read-only and will not '
                    'automatically initialize or repair any account.</div>') if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15"><title>OptionX | Private Paper Dashboard</title>
<style>{_CSS}</style></head><body><main>
<header><div class="brand">OPTION<span>X</span> <small style="font-size:12px;color:var(--muted)">AI TRADER</small></div>
<div class="pill">PRIVATE SSH · PAPER ONLY · REAL ORDERS OFF</div></header>
<h1>Paper Trading Dashboard</h1>
<p class="subtitle">AWS Mumbai · Angel One research · {_escape(current)} · refreshes every 15 seconds</p>
{error_notice}
{observer_warning}
<div class="grid">
<div class="card"><div class="label">Initial Virtual Capital</div><div class="value">{capital}</div></div>
<div class="card"><div class="label">Realized Virtual Equity*</div><div class="value gold">{equity}</div></div>
<div class="card"><div class="label">Today’s Gross Paper P&amp;L*</div><div class="value {pnl_class}">{pnl}</div></div>
<div class="card"><div class="label">Trades Today</div><div class="value">{_escape(count)} / {_escape(max_trades)}</div></div>
</div>
<section class="section card"><h2>Open Virtual Position</h2>{position_html}</section>
<section class="section card"><h2>Recent Virtual Trades</h2>
<div class="scroll"><table><thead><tr><th>Contract</th><th>State</th><th>Qty</th>
<th>Opened (UTC)</th><th>Exit reason</th><th>Gross P&amp;L*</th></tr></thead>
<tbody>{history}</tbody></table></div></section>
<div class="caution">* Simulated, indicative prices—not exchange fills. Charges, fees, spreads, slippage,
margin and unrealized P&amp;L are NOT included. The website does not automatically manage
or protect a position. Paper risk tiers: {_escape(plan.get("illustrativeLots","—"))}
virtual lots maximum; never a broker order authorization.</div>
<footer>Private localhost read-only view through your SSH tunnel. No public HTTPS, account login,
broker order, or remote mobile access is enabled by this page.</footer></main></body></html>"""


def make_handler(database_path):
    db_file = Path(database_path)

    class PrivateHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            return  # no sensitive referrers, queries or request data in logs

        def _send(self, status, payload, mime):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; "
                             "style-src 'unsafe-inline'; base-uri 'none'; "
                             "frame-ancestors 'none'; form-action 'none'; img-src 'none'; script-src 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.headers.get("Host", "") not in _ALLOWED_HOSTS:
                return self._send(403, b"Access only through private localhost SSH tunnel", "text/plain; charset=utf-8")
            if self.path == "/health":
                return self._send(200, b'{"service":"optionx-private-paper","paperOnly":true,"realOrdersEnabled":false}',
                                  "application/json; charset=utf-8")
            if self.path not in ("/", "/status.json"):
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            try:
                s = paper_status(db_file)
            except (PaperError, OSError, ValueError):
                if self.path == "/status.json":
                    return self._send(503, b'{"paperStatus":"unavailable","realOrdersEnabled":false}',
                                      "application/json; charset=utf-8")
                return self._send(503, make_view(error="UNAVAILABLE").encode("utf-8"),
                                  "text/html; charset=utf-8")
            if self.path == "/status.json":
                safe = {
                    "mode": "PAPER_ONLY",
                    "initialVirtualCapitalINR": s["initialCapitalINR"],
                    "realizedEquityBeforeChargesINR": s["realizedEquityBeforeChargesINR"],
                    "todayGrossPnlBeforeChargesINR": s["todayGrossPnlBeforeChargesINR"],
                    "tradesToday": s["tradesToday"],
                    "maxTradesPerDay": s["maxTradesPerDay"],
                    "openVirtualPosition": s["openPosition"],
                    "paperObservationHealth": paper_observation_health(s),
                    "recentVirtualTrades": s["recentTrades"],
                    "realOrdersEnabled": False,
                }
                return self._send(200, json.dumps(safe, separators=(",", ":")).encode("utf-8"),
                                  "application/json; charset=utf-8")
            return self._send(200, make_view(s).encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            return self._send(405, b"Read only", "text/plain; charset=utf-8")

    return PrivateHandler


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only private virtual paper dashboard, SSH only")
    p.add_argument("--port", type=int, default=BIND_PORT)
    p.add_argument("--db", default=str(DB_PATH))
    args = p.parse_args(argv)
    if args.port != BIND_PORT:
        p.error("Fixed 127.0.0.1:10001 private bind only")
    if os.name != "posix" or pwd.getpwuid(os.geteuid()).pw_name != "optionx":
        p.error("Must run as restricted Linux user optionx")
    server = ThreadingHTTPServer((BIND_HOST, args.port), make_handler(args.db))
    print("OPTIONX_PAPER_DASHBOARD: http://127.0.0.1:18751/ after private SSH -L tunnel")
    print("PAPER_ONLY: no orders, no public API, no broker credentials")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("PRIVATE_DASHBOARD_STOPPED")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
