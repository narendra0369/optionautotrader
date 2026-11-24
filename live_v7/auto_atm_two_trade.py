"""OptionX V10 ATM + 15m + TWO entry/day PAPER safety policy.

Pure deterministic policy. No network, no live broker, no order submission.
Do not treat this as approved trading software. Current website has no
verified unattended execution signal or native stop/target order route.
"""
from __future__ import annotations
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from zoneinfo import ZoneInfo
import sqlite3
import re

IST = ZoneInfo("Asia/Kolkata")
MAX_DAILY_ENTRY_ATTEMPTS = 2
ENTRY_CUTOFF = time(14, 45)
SESSION_START = time(9, 15)
SESSION_END = time(15, 30)
SUPPORTED_MARKETS = {"NIFTY", "BANKNIFTY"}
ACTIVE_STATES = {"INTENT_UNKNOWN", "BROKER_OPEN", "PARTIAL", "FILLED", "STOP_WORKING", "EXIT_UNKNOWN"}
TERMINAL_STATES = {"STOP_EXIT", "TARGET_EXIT", "MANUAL_EXIT", "REJECTED", "CANCELLED_CONFIRMED"}


class AutoATMBlocked(ValueError):
    pass


def _dec(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, str, Decimal, float)):
        raise AutoATMBlocked(name + "_INVALID")
    try: value=Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        raise AutoATMBlocked(name + "_INVALID") from None
    if not value.is_finite() or value<=0:
        raise AutoATMBlocked(name + "_MUST_BE_POSITIVE")
    return value


def ist_datetime(moment):
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise AutoATMBlocked("CLOCK_NEEDS_TIMEZONE")
    return moment.astimezone(IST)


def schedule_15m(now):
    """Next 15-min completed candle check, provisional until NSE holiday verification."""
    now=ist_datetime(now)
    d=now.date()
    while True:
        if d.weekday()<5:
            first=datetime.combine(d,time(9,30),IST)
            cutoff=datetime.combine(d,ENTRY_CUTOFF,IST)
            if now < first:
                check=first
            else:
                passed=(now-first).total_seconds()
                bars=int(passed//900)+1
                check=first+timedelta(minutes=15*bars)
            if check<=cutoff:
                return {
                  "nextCheckIST":check.isoformat(),"strategyTimeframe":"15m",
                  "intervalSeconds":900,"tentative":True,
                  "reason":"NSE holidays/exchange disruptions NOT verified; 15m is only the next evaluation slot, NOT a guaranteed fill or trade."
                }
        d=d+timedelta(days=1)
        now=datetime.combine(d,time(0,0),IST)


def select_atm(*, market, side, index_spot, observed_at, now, contracts,
               authenticated_index_read, official_master_verified):
    """Select nearest *actual* option strike, expiry and lot from broker master.

    Caller obtains index spot from owner-bound Angel read-only NSE quote. Strike
    grid is never guessed. Same distance -> lower strike deterministic.
    """
    if market not in SUPPORTED_MARKETS or side not in ("CE","PE"):
        raise AutoATMBlocked("UNSUPPORTED_MARKET_OR_SIDE")
    if authenticated_index_read is not True or official_master_verified is not True:
        raise AutoATMBlocked("TRUSTED_BROKER_DATA_REQUIRED")
    spot=_dec(index_spot,"INDEX_SPOT")
    if spot<Decimal(1000) or spot>Decimal(1000000):
        raise AutoATMBlocked("INDEX_SPOT_OUT_OF_RANGE")
    now_ist=ist_datetime(now)
    observed_ist=ist_datetime(observed_at)
    seconds=(now_ist-observed_ist).total_seconds()
    if seconds<0 or seconds>10:
        raise AutoATMBlocked("INDEX_QUOTE_NOT_FRESH")
    if not isinstance(contracts,(tuple,list)) or not contracts or len(contracts)>200000:
        raise AutoATMBlocked("BROKER_MASTER_UNAVAILABLE")
    options=[]
    for c in contracts:
        if (not isinstance(c,dict) or c.get("market")!=market or
            c.get("side")!=side or c.get("exchange")!="NFO" or
            c.get("instrumentType")!="OPTIDX"):
            continue
        try:
            from datetime import date
            expiry=date.fromisoformat(c["expiry"])
            strike=_dec(c["strike"],"STRIKE")
            token=c["token"]
            symbol=c["symbol"]
            lot=c["lotSize"]
            tick=_dec(c["tickSize"],"TICK")
            if expiry<now_ist.date() or tick>Decimal("100") or
                type(lot) is not int or not 1<=lot<=10000 or
                not isinstance(token,str) or not re.fullmatch(r"\d{2,16}",token) or
                not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9.-]{6,72}",symbol)):
                continue
            options.append((expiry,abs(strike-spot),strike,c))
        except (KeyError,ValueError,TypeError,AutoATMBlocked):
            continue
    if not options:
        raise AutoATMBlocked("NO_CURRENT_ATM_OPTION_IN_BROKER_MASTER")
    options.sort(key=lambda row:(row[0],row[1],row[2],row[3]["token"]))
    c=options[0][3]
    return {"market":market,"side":side,"spot":float(spot),"strike":float(options[0][2]),
            "expiry":c["expiry"],"symbol":c["symbol"],"token":c["token"],
            "lotSize":c["lotSize"],"tickSize":float(_dec(c["tickSize"],"TICK")),
            "spotObservedAt":observed_ist.isoformat(),
            "selection":"nearest_actual_strike_nearest_expiry",
            "premium":None,"fillETASeconds":None,
            "fillETAStatus":"UNKNOWABLE_WITHOUT_VALIDATED_ORDERBOOK_LIQUIDITY",
            "realOrdersEnabled":False}


def paper_greek_exit(*, selected, premium, greeks, strategy, lots=1,
                     per_lot_risk=300, reward_ratio=2, scenario_points=10, minutes=15):
    """Auto premium SL/TP preview, never a broker order or OCO guarantee.

    Theta assumed per 375-min day and Vega per one IV point; this is not
    calibrated to actual Angel data conventions. Risk ceiling is theoretical.
    """
    if strategy not in ("ORB18", "EMA", "IV_DEFENSE"):
        raise AutoATMBlocked("UNSUPPORTED_STRATEGY")
    if selected.get("realOrdersEnabled") is not False or
        selected.get("selection")!="nearest_actual_strike_nearest_expiry":
        raise AutoATMBlocked("UNVERIFIED_ATM_CONTRACT")
    if type(lots) is not int or not 1<=lots<=12:
        raise AutoATMBlocked("INVALID_LOTS")
    if type(selected.get("lotSize")) is not int:
        raise AutoATMBlocked("UNKNOWN_LOT")
    p=_dec(premium,"PREMIUM")
    tick=_dec(selected.get("tickSize"),"TICK")
    if p%tick!=0 or tick>=p:
        raise AutoATMBlocked("PREMIUM_TICK_OR_QUOTE_MISMATCH")
    if not isinstance(greeks,dict):
        raise AutoATMBlocked("GREEKS_MISSING")
    try:
        delta=Decimal(str(greeks["delta"]))
        gamma=Decimal(str(greeks["gamma"]))
        theta=Decimal(str(greeks["theta"]))
        vega=Decimal(str(greeks["vega"]))
        iv=Decimal(str(greeks["iv"]))
    except (TypeError,KeyError,ValueError,InvalidOperation):
        raise AutoATMBlocked("GREEKS_NOT_VERIFIED") from None
    if any(not x.is_finite() for x in (delta,gamma,theta,vega,iv)):
        raise AutoATMBlocked("GREEKS_NOT_FINITE")
    if (abs(delta)>1 or gamma<0 or gamma>5 or abs(theta)>10000
        or vega<0 or vega>10000 or not 0<iv<=200 or
        (selected["side"]=="CE" and delta<=0) or
        (selected["side"]=="PE" and delta>=0)):
        raise AutoATMBlocked("GREEKS_INCONSISTENT_WITH_OPTION")
    qty=lots*selected["lotSize"]
    max_loss=_dec(per_lot_risk,"RISK")*lots
    reward=_dec(reward_ratio,"REWARD_RATIO")
    if reward>10:
        raise AutoATMBlocked("REWARD_RATIO_TOO_HIGH")
    move=_dec(scenario_points,"SCENARIO")
    horizon=_dec(minutes,"HORIZON")
    if horizon>375:
        raise AutoATMBlocked("HORIZON_TOO_LONG")
    sign=Decimal("1") if delta>0 else Decimal("-1")
    adverse_spot=-sign*move
    adverse=delta*adverse_spot+Decimal(".5")*gamma*adverse_spot*adverse_spot+theta*horizon/Decimal(375)-vega
    sensitivity=max(Decimal("0"),-adverse)
    conservative={"ORB18":Decimal("1"),"EMA":Decimal(".85"),
                  "IV_DEFENSE":Decimal(".65")}[strategy]
    width=min(max_loss/Decimal(qty)*conservative,max(tick,sensitivity*conservative))
    sl_ticks=((p-width)/tick).to_integral_value(rounding=ROUND_CEILING)
    target_ticks=((p+max_loss*reward/Decimal(qty))/tick).to_integral_value(rounding=ROUND_CEILING)
    sl=sl_ticks*tick
    target=target_ticks*tick
    stop_limit=sl-tick
    hypothetical_loss=(p-sl)*qty
    hypothetical_gain=(target-p)*qty
    if (sl<=tick or stop_limit<=0 or sl>=p or hypothetical_loss<=0
         or hypothetical_loss>max_loss or target<=p or hypothetical_gain<max_loss*reward):
        raise AutoATMBlocked("PROTECTIVE_LEVEL_NOT_POSSIBLE")
    return {
       "mode":"AUTO_PAPER_RESEARCH_NO_ORDERS","strategy":strategy,
       "contract":selected["symbol"],"side":selected["side"],
       "quantity":qty,"entryPremium":float(p),"stopTrigger":float(sl),
       "stopLimit":float(stop_limit),"targetLimit":float(target),
       "theoreticalMaxLossINR":float(hypothetical_loss),
       "theoreticalProfitINR":float(hypothetical_gain),
       "orderTypes":{"entry":"LIMIT","stop":"STOPLOSS_LIMIT","target":"LIMIT","duration":"DAY"},
       "estimatedFillTimeSeconds":None,
       "fillTimeStatus":"UNKNOWN_NOT_PREDICTABLE_WITHOUT_LIVE_DEPTH_AND_EXECUTIONS",
       "canSubmitOrder":False,"liveOrdersEnabled":False,
       "note":"No execution guarantee: SL-LIMIT can remain unfilled; costs/spread/gaps may exceed risk. Stop and target require verified cancellation/position gating, not simultaneous independent sells."
    }


def open_shadow_gate(filename):
    """Disposable/local TEST ledger ONLY; not production real-order persistence."""
    db=sqlite3.connect(str(filename),isolation_level=None,timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS auto_atm_intents(
       owner TEXT NOT NULL,trade_day TEXT NOT NULL,signal_id TEXT NOT NULL,
       market TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
       PRIMARY KEY (owner,trade_day,signal_id))""")
    return db


def reserve_shadow_entry(db,*,owner,market,signal_id,now):
    """Reserve a slot BEFORE any mock send: rejects/unknown ACK consume slot."""
    if not isinstance(owner,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",owner):
        raise AutoATMBlocked("OWNER_INVALID")
    if market not in SUPPORTED_MARKETS:
        raise AutoATMBlocked("MARKET_INVALID")
    if not isinstance(signal_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",signal_id):
        raise AutoATMBlocked("SIGNAL_ID_INVALID")
    today=ist_datetime(now)
    if today.weekday()>=5 or not SESSION_START<=today.time().replace(tzinfo=None)<ENTRY_CUTOFF:
        raise AutoATMBlocked("ENTRY_OUTSIDE_APPROVED_HOURS")
    day=today.date().isoformat()
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT COUNT(*),SUM(CASE WHEN state IN ("
            "'INTENT_UNKNOWN','BROKER_OPEN','PARTIAL','FILLED','STOP_WORKING','EXIT_UNKNOWN')"
            " THEN 1 ELSE 0 END) FROM auto_atm_intents WHERE owner=? AND trade_day=?",
            (owner,day)).fetchone()
        count,active=row[0],row[1] or 0
        if db.execute("SELECT 1 FROM auto_atm_intents WHERE owner=? AND trade_day=? AND signal_id=?",
                      (owner,day,signal_id)).fetchone():
            raise AutoATMBlocked("DUPLICATE_STRATEGY_SIGNAL")
        if count>=MAX_DAILY_ENTRY_ATTEMPTS:
            raise AutoATMBlocked("TWO_ENTRY_DAILY_LIMIT_REACHED")
        if active:
            raise AutoATMBlocked("PREVIOUS_ENTRY_OR_EXIT_UNRESOLVED")
        db.execute("INSERT INTO auto_atm_intents VALUES(?,?,?,?,?,?)",
                   (owner,day,signal_id,market,"INTENT_UNKNOWN",
                    today.astimezone(timezone.utc).isoformat()))
        db.commit()
        return {"status":"SHADOW_RESERVED_NO_ORDER","day":day,"remainingSlots":MAX_DAILY_ENTRY_ATTEMPTS-count-1,
                "maxEntriesDay":MAX_DAILY_ENTRY_ATTEMPTS,"canSubmitRealOrder":False}
    except:
        db.rollback()
        raise


def shadow_set_state(db,*,owner,signal_id,new_state,now,synthetic_evidence):
    """Only fake lifecycle evidence admitted; no real adapter binding."""
    if synthetic_evidence is not True or new_state not in ACTIVE_STATES|TERMINAL_STATES:
        raise AutoATMBlocked("SYNTHETIC_LIFECYCLE_PROOF_REQUIRED")
    date_key=ist_datetime(now).date().isoformat()
    row=db.execute("SELECT state FROM auto_atm_intents WHERE owner=? AND trade_day=? AND signal_id=?",
                   (owner,date_key,signal_id)).fetchone()
    if not row:
        raise AutoATMBlocked("SHADOW_TRADE_NOT_FOUND")
    if row[0] in TERMINAL_STATES:
        raise AutoATMBlocked("CANNOT_REOPEN_CLOSED_TRADE")
    if row[0]=="INTENT_UNKNOWN" and new_state in {"STOP_EXIT","TARGET_EXIT","MANUAL_EXIT"}:
        raise AutoATMBlocked("NO_VERIFIED_POSITION_TO_EXIT")
    db.execute("UPDATE auto_atm_intents SET state=? WHERE owner=? AND trade_day=? AND signal_id=?",
               (new_state,owner,date_key,signal_id))
    return True


def shadow_daily_status(db,*,owner,now):
    day=ist_datetime(now).date().isoformat()
    rows=db.execute("SELECT state FROM auto_atm_intents WHERE owner=? AND trade_day=?",
                    (owner,day)).fetchall()
    count=len(rows)
    active=sum(1 for (state,) in rows if state in ACTIVE_STATES)
    return {"day":day,"entryAttempts":count,"limit":2,"remaining":max(0,2-count),
            "noNewEntries":count>=2 or active>0,
            "openOrUnknown":active,"liveOrdersEnabled":False}
