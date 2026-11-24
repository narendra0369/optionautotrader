"""OptionX Angel One AWS SSH-only read-only pilot.

IMPORTANT: Requires an interactive SSH terminal on the existing AWS Mumbai host.
No passwords, API keys, PINs, TOTPs or tokens are logged, written or printed.
No broker order, cancel, or modify API can be reached from this CLI.
This pilot provides broker profile verification, official NFO contract metadata,
indicative LTP, completed 15-minute candles and a non-persistent paper preview.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_CEILING
import getpass
import ipaddress
import os
import sys

from ops.verify_angel_aws_readiness import verify as verify_aws_readiness

OWNER = "optionx-ssh-local-operator"


class PilotError(RuntimeError):
    pass


def _positive_decimal(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (ValueError, ArithmeticError):
        raise PilotError(label + "_INVALID") from None
    if not amount.is_finite() or amount <= 0:
        raise PilotError(label + "_INVALID")
    return amount


def paper_preview(contract: dict, ltp: float, risk=300, reward=600) -> dict:
    """Quote-derived, ONE-LOT illustrative paper BUY preview; NEVER places orders.

    These hypothetical levels do not represent executable prices, account
    balances, realized returns, enforced broker stops or guaranteed maximum loss.
    """
    if contract.get("side") not in ("CE", "PE"):
        raise PilotError("PAPER_PREVIEW_OPTIONS_ONLY")
    lot = contract.get("lotSize")
    if not isinstance(lot, int) or isinstance(lot, bool) or not 1 <= lot <= 10000:
        raise PilotError("PAPER_LOT_INVALID")
    price = _positive_decimal(ltp, "PRICE")
    tick = _positive_decimal(contract.get("tickSize"), "TICK")
    if tick > Decimal("100"):
        raise PilotError("TICK_INVALID")
    risk_d = _positive_decimal(risk, "RISK")
    reward_d = _positive_decimal(reward, "REWARD")
    qty = Decimal(lot)
    raw_stop = price - risk_d / qty
    if raw_stop <= 0:
        raise PilotError("PAPER_RISK_EXCEEDS_PREMIUM")
    stop = (raw_stop / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    target = ((price + reward_d / qty) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    if stop >= price or target <= price:
        raise PilotError("PAPER_LEVELS_NOT_POSSIBLE")
    return {
        "mode": "PAPER_PREVIEW_ONLY",
        "brokerOrdersSent": 0,
        "symbol": contract["symbol"],
        "side": "SIMULATED_BUY",
        "oneLotQuantity": lot,
        "indicativeEntryLtp": float(price),
        "illustrativeStopLevel": float(stop),
        "illustrativeTargetLevel": float(target),
        "theoreticalPremiumAtEntry": float(price * qty),
        "theoreticalLossAtStopBeforeCharges": float((price - stop) * qty),
        "theoreticalGainAtTargetBeforeCharges": float((target - price) * qty),
        "limitations": "No paper position persisted, trade/fill placed, slippage, fees, margin, spread, live quote freshness or automatic stop/target enforcement.",
    }


def _prompt_credentials() -> dict:
    """Read inputs only from the user's private SSH TTY, with no shell history."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PilotError("INTERACTIVE_SSH_TTY_REQUIRED")
    code = input("Angel client code (not printed again): ").strip()
    key = getpass.getpass("SmartAPI Trading API key (hidden): ").strip()
    pin = getpass.getpass("Angel login PIN (hidden): ").strip()
    totp = getpass.getpass("Current 6-digit TOTP (hidden): ").strip()
    return {"apiKey": key, "clientCode": code, "pin": pin, "totp": totp}


def _select_strike(args) -> str | None:
    if args.side == "FUT":
        return None
    if args.strike is not None:
        return args.strike
    if not sys.stdin.isatty():
        raise PilotError("STRIKE_REQUIRED")
    return input("Desired NIFTY/BANKNIFTY option strike (e.g. 26000): ").strip()


def _safe_login_and_marketdata(args):
    """Sensitive broker values live only in this short-lived Python process."""
    import angel_gateway
    from live_v7.angel_marketdata import (
        MarketDataError, historical_15m, list_contracts, quote_ltp,
    )

    os.environ["OPTIONX_OWNER_USER_ID"] = OWNER
    os.environ["ANGEL_EGRESS_PUBLIC_IPV4"] = args.expected_ip
    credentials = _prompt_credentials()
    try:
        result = angel_gateway.connect(OWNER, credentials)
    finally:
        # Do not keep a second copy of the inputs in the CLI stack.
        credentials.clear()
    print("ANGEL_PROFILE_VERIFIED: connected=" + str(result["connected"])
          + " client=" + str(result["maskedClientCode"])
          + " real_orders_enabled=false")
    try:
        strike = _select_strike(args)
        contracts = list_contracts(OWNER, args.market, args.side, strike=strike)
        options = contracts["contracts"]
        if not options:
            raise PilotError("NO_MATCHING_VERIFIED_CONTRACTS")
        contract = options[0]
        print("OFFICIAL_CONTRACT: " + contract["symbol"]
              + " | token=" + contract["token"]
              + " | lot=" + str(contract["lotSize"])
              + " | expiry=" + contract["expiry"]
              + " | quote_verified=false")
        quote = quote_ltp(OWNER, contract["token"])
        print("ANGEL_INDICATIVE_LTP: " + str(quote["ltp"])
              + " | observedAt=" + quote["observedAt"]
              + " | exchange_timestamp_verified=false")
        candles = historical_15m(OWNER, contract["token"], days=args.days)
        print("ANGEL_COMPLETED_15M_CANDLES: " + str(candles["barCount"])
              + " | timeframe=15m"
              + " | historical_only=true")
        if args.paper_open or args.paper_observe:
            from ops.paper_ledger_v1 import PaperError, open_paper, monitor_paper
            try:
                if args.paper_open:
                    saved = open_paper(
                        args.paper_db, contract, quote, capital=args.paper_capital,
                        lots=args.paper_lots)
                    print("PAPER_ENTRY_SAVED: id=" + str(saved["paperTradeId"])
                          + " symbol=" + saved["contract"]
                          + " lots=" + str(saved["lots"])
                          + " qty=" + str(saved["qty"])
                          + " indicative_entry=" + saved["quoteEntry"]
                          + " illustrative_SL=" + saved["illustrativeStop"]
                          + " illustrative_target=" + saved["illustrativeTarget"])
                    print("PAPER_SAFETY: virtual-only; no real fills; NO unattended monitoring; costs excluded")
                else:
                    tick = monitor_paper(args.paper_db, contract, quote)
                    print("PAPER_OBSERVED: id=" + str(tick["paperTradeId"])
                          + " ltp=" + tick["quoteLtp"]
                          + " paper_closed=" + str(tick["paperClosed"])
                          + " trigger=" + str(tick["trigger"]))
                    print("PAPER_SAFETY: illustrative quote triggers, not real execution")
            except PaperError as exc:
                print("PAPER_RECORD_BLOCKED: " + str(exc))
        if args.paper_preview:
            try:
                p = paper_preview(contract, quote["ltp"], args.risk, args.reward)
            except PilotError as exc:
                print("PAPER_PREVIEW_BLOCKED: " + str(exc))
            else:
                print("PAPER_PREVIEW_ONLY: qty=" + str(p["oneLotQuantity"])
                      + " entry=" + str(p["indicativeEntryLtp"])
                      + " illustrative_SL=" + str(p["illustrativeStopLevel"])
                      + " illustrative_target=" + str(p["illustrativeTargetLevel"])
                      + " theoretical_loss=" + str(p["theoreticalLossAtStopBeforeCharges"])
                      + " theoretical_gain=" + str(p["theoreticalGainAtTargetBeforeCharges"]))
                print("PAPER_PREVIEW_WARNING: no position persisted, fills or SL/target orders; no fees or slippage.")
        print("ANGEL_AWS_READONLY_PILOT_PASSED: no real orders; profile session discarded on exit")
    except MarketDataError as exc:
        raise PilotError("ANGEL_MARKETDATA_BLOCKED_" + exc.code) from None
    finally:
        angel_gateway.disconnect(OWNER)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Angel One read-only AWS SSH test; NEVER submits broker orders")
    parser.add_argument("--expected-ip", required=True, help="Verified AWS public egress IPv4")
    parser.add_argument("--connect", action="store_true", help="Prompt locally via SSH TTY for ephemeral Angel profile login")
    parser.add_argument("--market", choices=("NIFTY", "BANKNIFTY"), default="NIFTY")
    parser.add_argument("--side", choices=("CE", "PE", "FUT"), default="CE")
    parser.add_argument("--strike", help="Desired option strike; nearby verified contract will be selected")
    parser.add_argument("--days", type=int, choices=(1, 2, 3, 5, 7), default=3)
    parser.add_argument("--paper-preview", action="store_true", help="Calculate one-lot hypothetical paper preview; no position ledger")
    parser.add_argument("--paper-status", action="store_true", help="Show existing private paper journal without broker credentials")
    parser.add_argument("--paper-open", action="store_true", help="Explicit virtual-only entry at broker's indicative LTP; no real order")
    parser.add_argument("--paper-observe", action="store_true", help="Observe one matching position with a fresh indicative LTP; no background monitoring")
    parser.add_argument("--paper-capital", default="500000", help="Initial virtual capital; fixed at initial journal creation")
    parser.add_argument("--paper-lots", type=int, default=None, help="Virtual lots, capped by stepped paper risk policy")
    parser.add_argument("--paper-db", default="/var/lib/optionx-paper/paper-v1.sqlite3", help="Private virtual-only SQLite journal path")
    parser.add_argument("--risk", type=float, default=300, help="Illustrative rupee risk per one-lot preview only")
    parser.add_argument("--reward", type=float, default=600, help="Illustrative rupee reward per one-lot preview only")
    args = parser.parse_args(argv)

    try:
        address = ipaddress.ip_address(args.expected_ip)
        if address.version != 4 or not address.is_global:
            raise PilotError("EXPECTED_IP_NOT_PUBLIC_IPV4")
        # The precheck compares the observed outbound public IPv4 with this
        # verified target and independently re-verifies all no-orders gates.
        verify_aws_readiness(args.expected_ip)
        print("AWS_ANGEL_PRECHECK_PASSED")
        if sum(bool(x) for x in (args.paper_status, args.paper_open, args.paper_observe)) > 1:
            raise PilotError("CHOOSE_ONE_PAPER_OPERATION")
        if args.paper_status:
            from ops.paper_ledger_v1 import PaperError, status as paper_status
            try:
                state = paper_status(args.paper_db)
                print("PAPER_LEDGER_STATUS: cash=" + state["realizedEquityBeforeChargesINR"]
                      + " trades_today=" + str(state["tradesToday"])
                      + " max_trades=" + str(state["maxTradesPerDay"])
                      + " open_position=" + str(bool(state["openPosition"])))
                if state["openPosition"]:
                    pos = state["openPosition"]
                    print("PAPER_OPEN_POSITION: id=" + str(pos["id"])
                          + " symbol=" + pos["symbol"]
                          + " indicative_entry=" + pos["indicative_entry"]
                          + " last_observed_ltp=" + str(pos["last_quote"])
                          + " last_observed_utc=" + str(pos["last_observed_utc"]))
                print("PAPER_LEDGER_NOTE: no auto monitoring, exchange executions or real orders")
            except PaperError as exc:
                raise PilotError("PAPER_STATUS_" + str(exc)) from None
            return 0
        if (args.paper_open or args.paper_observe) and not args.connect:
            raise PilotError("PAPER_POSITION_REQUIRES_INTERACTIVE_BROKER_CONFIRMATION")
        if not args.connect:
            print("NO_BROKER_LOGIN_ATTEMPTED: run with --connect over an interactive SSH TTY")
            return 0
        _safe_login_and_marketdata(args)
        return 0
    except PilotError as exc:
        print("ANGEL_AWS_PILOT_BLOCKED: " + str(exc), file=sys.stderr)
    except Exception as exc:
        # Deliberately do not expose broker or transport exception payloads.
        if exc.__class__.__name__ == "AuthError":
            print("ANGEL_AWS_PILOT_BLOCKED: ANGEL_PROFILE_LOGIN_REJECTED", file=sys.stderr)
        elif exc.__class__.__name__ == "ReadinessError":
            print("ANGEL_AWS_PILOT_BLOCKED: AWS_SAFETY_PRECHECK_FAILED", file=sys.stderr)
        else:
            print("ANGEL_AWS_PILOT_BLOCKED: UNEXPECTED_LOCAL_ERROR", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
