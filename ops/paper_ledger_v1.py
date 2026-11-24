"""OptionX isolated, durable *virtual-only* NFO option paper journal.

No broker network, login, order placement, refresh tokens, or SDK imports.
ONLY accept broker-verified contract metadata and quote inputs from the
separate Angel read-only pilot. This is NOT an exchange execution simulator:
quote timestamps are local observations, not exchange-verified.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import os
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from live_v7.risk_policy import stepped_paper_plan, MAX_TRADES_PER_DAY

IST = ZoneInfo("Asia/Kolkata")
DB_PATH = Path("/var/lib/optionx-paper/paper-v1.sqlite3")
_SYMBOL = re.compile(r"^(NIFTY|BANKNIFTY)[A-Z0-9._-]{4,65}(CE|PE)$")
_TOKEN = re.compile(r"^\d{2,14}$")


class PaperError(ValueError):
    pass


def _dec(value, label, *, positive=True):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise PaperError(label + "_INVALID")
    try:
        d = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise PaperError(label + "_INVALID") from None
    if not d.is_finite() or (positive and d <= 0):
        raise PaperError(label + "_INVALID")
    return d


def _now(ts):
    if ts is None:
        return datetime.now(timezone.utc)
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise PaperError("AWARE_TIMESTAMP_REQUIRED")
    return ts.astimezone(timezone.utc)


def _db(path):
    p = Path(path)
    if not p.parent.is_dir():
        raise PaperError("PAPER_PRIVATE_DIRECTORY_NOT_CONFIGURED")
    db = sqlite3.connect(str(p), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _init(db, capital):
    db.execute("""CREATE TABLE IF NOT EXISTS account (
        k INTEGER PRIMARY KEY CHECK(k = 1),
        initial_capital TEXT NOT NULL,
        created_utc TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opened_utc TEXT NOT NULL,
        trade_day_ist TEXT NOT NULL,
        market TEXT NOT NULL,
        symbol TEXT NOT NULL,
        token TEXT NOT NULL,
        side TEXT NOT NULL CHECK(side IN ('CE','PE')),
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        lots INTEGER NOT NULL CHECK(lots > 0),
        lot_size INTEGER NOT NULL CHECK(lot_size > 0),
        indicative_entry TEXT NOT NULL,
        illustrative_stop TEXT NOT NULL,
        illustrative_target TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
        last_quote TEXT,
        last_observed_utc TEXT,
        closed_utc TEXT,
        closing_quote TEXT,
        close_reason TEXT,
        gross_pnl TEXT
    )""")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_open_paper_trade ON trades(status) WHERE status = 'OPEN'")
    if capital is not None:
        amount = _dec(capital, "CAPITAL")
        if amount < 30000 or amount > 100000000:
            raise PaperError("PAPER_CAPITAL_OUT_OF_RANGE")
        db.execute("INSERT OR IGNORE INTO account (k, initial_capital, created_utc) VALUES (1, ?, ?)",
                   (str(amount), datetime.now(timezone.utc).isoformat()))
        saved = db.execute("SELECT initial_capital FROM account WHERE k = 1").fetchone()[0]
        if _dec(saved, "CAPITAL") != amount:
            raise PaperError("PAPER_CAPITAL_ALREADY_SET_DIFFERENTLY")


def _capital(db):
    row = db.execute("SELECT initial_capital FROM account WHERE k = 1").fetchone()
    if not row:
        raise PaperError("PAPER_ACCOUNT_NOT_INITIALIZED")
    return _dec(row[0], "CAPITAL")


def _equity(db):
    capital = _capital(db)
    closed = db.execute("SELECT gross_pnl FROM trades WHERE status='CLOSED'").fetchall()
    return capital + sum((_dec(r[0], "PNL", positive=False) for r in closed), Decimal(0))


def _snapshot(db, now):
    equity = _equity(db)
    plan = stepped_paper_plan(str(max(equity, Decimal(0))))
    today = now.astimezone(IST).date().isoformat()
    rows = db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 10").fetchall()
    today_count = db.execute("SELECT count(*) FROM trades WHERE trade_day_ist=?", (today,)).fetchone()[0]
    today_closed = db.execute("SELECT gross_pnl FROM trades WHERE trade_day_ist=? AND status='CLOSED'", (today,)).fetchall()
    today_pnl = sum((_dec(r[0], "PNL", positive=False) for r in today_closed), Decimal(0))
    open_pos = next((dict(r) for r in rows if r["status"] == "OPEN"), None)
    if open_pos is None:
        row = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchone()
        open_pos = dict(row) if row else None
    return {
        "mode": "PERSISTENT_PAPER_ONLY",
        "initialCapitalINR": str(_capital(db)),
        "realizedEquityBeforeChargesINR": str(equity),
        "todayGrossPnlBeforeChargesINR": str(today_pnl),
        "tradesToday": today_count,
        "maxTradesPerDay": MAX_TRADES_PER_DAY,
        "paperPlan": plan,
        "openPosition": open_pos,
        "recentTrades": [dict(r) for r in rows],
        "unattendedMonitoring": False,
        "liveExecutionEnabled": False,
        "orderExecutionEnabled": False,
        "canSubmitOrder": False,
        "brokerOrdersSent": 0,
        "warning": "Indicative broker LTP, not exchange-verified. No auto monitoring, real fills, charges or broker stops.",
    }


def status(path=DB_PATH, *, now=None):
    now = _now(now)
    with _db(path) as db:
        try:
            return _snapshot(db, now)
        except sqlite3.OperationalError as exc:
            raise PaperError("PAPER_ACCOUNT_NOT_INITIALIZED") from None


def _verify_contract(c):
    if not isinstance(c, dict) or c.get("exchange") != "NFO":
        raise PaperError("VERIFIED_NFO_CONTRACT_REQUIRED")
    sym, token, side = c.get("symbol"), c.get("token"), c.get("side")
    if (not isinstance(sym, str) or not _SYMBOL.fullmatch(sym) or
            not isinstance(token, str) or not _TOKEN.fullmatch(token) or side not in ("CE", "PE")):
        raise PaperError("NFO_OPTION_SYMBOL_INVALID")
    if c.get("market") not in ("NIFTY", "BANKNIFTY"):
        raise PaperError("MARKET_INVALID")
    lot = c.get("lotSize")
    if not isinstance(lot, int) or isinstance(lot, bool) or not 1 <= lot <= 10000:
        raise PaperError("LOT_SIZE_INVALID")
    _dec(c.get("tickSize"), "TICK")
    return lot


def _levels(entry, lot_size, risk_per_lot, reward_per_lot, tick):
    raw_stop = entry - risk_per_lot / Decimal(lot_size)
    if raw_stop <= 0:
        raise PaperError("PAPER_RISK_EXCEEDS_PREMIUM")
    stop = (raw_stop / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    target = ((entry + reward_per_lot / Decimal(lot_size)) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    if not 0 < stop < entry < target:
        raise PaperError("PAPER_TICK_LEVELS_INVALID")
    return stop, target


def open_paper(path, contract, quote, *, capital="500000", now=None, lots=None):
    """Explicit one-time simulation after a fresh broker LTP; no real orders."""
    stamp = _now(now)
    day_ist = stamp.astimezone(IST)
    if not (day_ist.weekday() < 5 and
            (9, 15) <= (day_ist.hour, day_ist.minute) < (15, 30)):
        raise PaperError("PAPER_NEW_ENTRY_OUTSIDE_NSE_SESSION")
    lot_size = _verify_contract(contract)
    price = _dec(quote.get("ltp") if isinstance(quote, dict) else None, "QUOTE")
    if quote.get("contract") != contract:
        raise PaperError("QUOTE_CONTRACT_MISMATCH")
    observed = quote.get("observedAt")
    try:
        parsed = datetime.fromisoformat(observed)
    except (TypeError, ValueError):
        raise PaperError("QUOTE_OBSERVATION_MISSING") from None
    if parsed.tzinfo is None or not (0 <= (stamp - parsed.astimezone(timezone.utc)).total_seconds() <= 60):
        raise PaperError("QUOTE_OBSERVATION_STALE")
    with _db(path) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _init(db, capital)
            snapshot = _snapshot(db, stamp)
            plan = snapshot["paperPlan"]
            maximum = plan["illustrativeLots"]
            if maximum < 1:
                raise PaperError("INSUFFICIENT_PAPER_EQUITY")
            wanted = maximum if lots is None else lots
            if not isinstance(wanted, int) or isinstance(wanted, bool) or not 1 <= wanted <= maximum:
                raise PaperError("PAPER_LOT_COUNT_EXCEEDS_RISK_TIER")
            if snapshot["openPosition"] is not None:
                raise PaperError("EXISTING_PAPER_POSITION_OPEN")
            if snapshot["tradesToday"] >= MAX_TRADES_PER_DAY:
                raise PaperError("DAILY_TRADE_COUNT_LIMIT")
            if (_dec(snapshot["todayGrossPnlBeforeChargesINR"], "TODAY", positive=False)
                    <= -_dec(plan["dailyStopINR"], "DAILY")):
                raise PaperError("DAILY_PAPER_LOSS_CAP")
            size = wanted * lot_size
            required = price * size
            if required > _dec(snapshot["realizedEquityBeforeChargesINR"], "EQUITY"):
                raise PaperError("PAPER_PREMIUM_EXCEEDS_EQUITY")
            stop, target = _levels(price, lot_size, Decimal("300"), Decimal("600"),
                                   _dec(contract["tickSize"], "TICK"))
            db.execute("""INSERT INTO trades (
                opened_utc,trade_day_ist,market,symbol,token,side,quantity,lots,
                lot_size,indicative_entry,illustrative_stop,illustrative_target,
                status,last_quote,last_observed_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                stamp.isoformat(), day_ist.date().isoformat(), contract["market"],
                contract["symbol"],contract["token"],contract["side"],size,wanted,
                lot_size,str(price),str(stop),str(target),"OPEN",str(price),stamp.isoformat()
            ))
            ident = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("COMMIT")
            return {"mode": "PAPER_OPEN_SIMULATED", "paperTradeId": ident,
                    "contract": contract["symbol"], "lots": wanted, "qty": size,
                    "quoteEntry": str(price), "illustrativeStop": str(stop),
                    "illustrativeTarget": str(target),
                    "premiumBeforeCharges": str(required), "canSubmitOrder": False,
                    "brokerOrdersSent": 0,
                    "warning": "No broker fill, auto monitoring, guaranteed loss limit or charges."}
        except Exception:
            db.execute("ROLLBACK")
            raise


def monitor_paper(path, contract, quote, *, now=None):
    """One explicit quote observation: simulated exit at observed quote on trigger."""
    stamp = _now(now)
    _verify_contract(contract)
    if not isinstance(quote, dict) or quote.get("contract") != contract:
        raise PaperError("QUOTE_CONTRACT_MISMATCH")
    price = _dec(quote.get("ltp"), "QUOTE")
    try:
        obs = datetime.fromisoformat(quote.get("observedAt"))
    except (ValueError, TypeError):
        raise PaperError("QUOTE_OBSERVATION_MISSING") from None
    if obs.tzinfo is None or not 0 <= (stamp-obs.astimezone(timezone.utc)).total_seconds() <= 60:
        raise PaperError("QUOTE_OBSERVATION_STALE")
    with _db(path) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchone()
            if not row:
                raise PaperError("NO_OPEN_PAPER_POSITION")
            if row["token"] != contract["token"] or row["symbol"] != contract["symbol"]:
                raise PaperError("PAPER_POSITION_CONTRACT_MISMATCH")
            last = datetime.fromisoformat(row["last_observed_utc"])
            if stamp <= last:
                raise PaperError("PAPER_OBSERVATION_NOT_NEW")
            stop = _dec(row["illustrative_stop"], "STOP")
            target = _dec(row["illustrative_target"], "TARGET")
            reason = "STOP_OBSERVED" if price <= stop else "TARGET_OBSERVED" if price >= target else None
            if reason:
                gross = (price - _dec(row["indicative_entry"], "ENTRY")) * Decimal(row["quantity"])
                db.execute("""UPDATE trades SET status='CLOSED',last_quote=?,last_observed_utc=?,
                    closed_utc=?,closing_quote=?,close_reason=?,gross_pnl=? WHERE id=? AND status='OPEN'""",
                    (str(price),stamp.isoformat(),stamp.isoformat(),str(price),reason,str(gross),row["id"]))
            else:
                db.execute("UPDATE trades SET last_quote=?,last_observed_utc=? WHERE id=?",
                           (str(price),stamp.isoformat(),row["id"]))
            db.execute("COMMIT")
            return {"mode": "PAPER_QUOTE_OBSERVATION", "paperTradeId": row["id"],
                    "quoteLtp": str(price), "paperClosed": bool(reason),
                    "trigger": reason or "NONE", "canSubmitOrder": False,
                    "brokerOrdersSent": 0,
                    "warning": "No automatic monitoring between manual observations; SL/TP are not real broker orders."}
        except Exception:
            db.execute("ROLLBACK")
            raise
