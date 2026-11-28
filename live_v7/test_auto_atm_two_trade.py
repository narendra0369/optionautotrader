"""V10 auto ATM / Greeks two-attempt policy regression. NO BROKER ORDERS."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import tempfile
import unittest
from pathlib import Path

from live_v7.auto_atm_two_trade import (
    AutoATMBlocked, select_atm, paper_greek_exit, schedule_15m,
    open_shadow_gate, reserve_shadow_entry, shadow_set_state, shadow_daily_status
)

IST=ZoneInfo("Asia/Kolkata")
NOW=datetime(2026,11,25,11,15,tzinfo=IST)
OWNER="owner_001122"
C1="strategy_signal_0001"
C2="strategy_signal_0002"
C3="strategy_signal_0003"


def sample_contract(side, strike, expiry="2026-11-26", market="NIFTY"):
    return {
       "market":market,"side":side,"exchange":"NFO","instrumentType":"OPTIDX",
       "expiry":expiry,"strike":strike,"symbol":f"{market}26NOV26{strike}{side}",
       "token":str(123456+int(strike)+(0 if side=="CE" else 1)),
       "lotSize":65 if market=="NIFTY" else 30,"tickSize":0.05,
    }


def pick(*,side="CE",spot="25051",now=NOW,rows=None):
    rows=rows or [sample_contract(side,25000),sample_contract(side,25050),
                  sample_contract(side,25100),sample_contract(side,25000,"2026-12-03")]
    return select_atm(market="NIFTY",side=side,index_spot=spot,
         observed_at=now-timedelta(seconds=2),now=now,contracts=rows,
         authenticated_index_read=True,official_master_verified=True)


class AutoATMTests(unittest.TestCase):
    def test_closest_actual_strike_and_nearest_expiry(self):
        p=pick()
        self.assertEqual(p["strike"],25050)
        self.assertEqual(p["expiry"],"2026-11-26")
        self.assertIsNone(p["premium"])
        self.assertIsNone(p["fillETASeconds"])
        self.assertFalse(p["realOrdersEnabled"])

    def test_equal_distance_tie_picks_lower_strike(self):
        self.assertEqual(pick(spot="25075")["strike"],25050)

    def test_expired_contract_discarded(self):
        p=pick(spot="25100",rows=[sample_contract("CE",25100,"2026-11-24"),
                                  sample_contract("CE",25000)])
        self.assertEqual(p["strike"],25000)

    def test_pe_contract_auto_selection(self):
        p=pick(side="PE",rows=[sample_contract("CE",25050),sample_contract("PE",25050)])
        self.assertEqual(p["side"],"PE")

    def test_unsafe_broker_inputs_never_produce_atm(self):
        rows=[sample_contract("CE",25050)]
        attrs=dict(market="NIFTY",side="CE",index_spot="25051",
            observed_at=NOW-timedelta(seconds=2),now=NOW,
            contracts=rows,authenticated_index_read=True,official_master_verified=True)
        for update in (
            {"authenticated_index_read":False},
            {"official_master_verified":False},
            {"observed_at":NOW-timedelta(minutes=1)},
            {"observed_at":NOW+timedelta(seconds=1)},
            {"index_spot":"NaN"},
            {"contracts":[]},
            {"market":"BTC"},
        ):
            with self.subTest(update=update),self.assertRaises(AutoATMBlocked):
                select_atm(**{**attrs,**update})

    def test_next_15m_closed_candle_and_weekend(self):
        q=schedule_15m(datetime(2026,11,25,9,16,tzinfo=IST))
        self.assertEqual(q["nextCheckIST"],"2026-11-25T09:30:00+05:30")
        q=schedule_15m(datetime(2026,11,25,9,30,tzinfo=IST))
        self.assertEqual(q["nextCheckIST"],"2026-11-25T09:45:00+05:30")
        q=schedule_15m(datetime(2026,11,25,15,5,tzinfo=IST))
        self.assertEqual(q["nextCheckIST"],"2026-11-26T09:30:00+05:30")
        q=schedule_15m(datetime(2026,11,28,12,0,tzinfo=IST))
        self.assertEqual(q["nextCheckIST"],"2026-11-30T09:30:00+05:30")
        self.assertTrue(q["tentative"])

    def test_auto_premium_risk_target_and_no_fill_eta(self):
        p=paper_greek_exit(selected=pick(),premium="100",strategy="ORB18",
            greeks={"delta":0.5,"gamma":0.001,"theta":-4,"vega":2,"iv":20})
        self.assertEqual(p["entryPremium"],100)
        self.assertEqual(p["stopTrigger"],95.4)
        self.assertEqual(p["orderTypes"]["entry"],"LIMIT")
        self.assertEqual(p["orderTypes"]["stop"],"STOPLOSS_LIMIT")
        self.assertEqual(p["orderTypes"]["duration"],"DAY")
        self.assertIsNone(p["estimatedFillTimeSeconds"])
        self.assertFalse(p["canSubmitOrder"])

    def test_strategies_have_distinct_risk_but_same_2x_target(self):
        opts=dict(selected=pick(),premium=100,
                  greeks={"delta":0.5,"gamma":0.001,"theta":-4,"vega":2,"iv":20})
        orb=paper_greek_exit(**opts,strategy="ORB18")
        iv=paper_greek_exit(**opts,strategy="IV_DEFENSE")
        self.assertLessEqual(iv["theoreticalMaxLossINR"],orb["theoreticalMaxLossINR"])
        self.assertEqual(iv["targetLimit"],orb["targetLimit"])

    def test_no_fake_greeks_or_quote(self):
        p=pick()
        for quote,g in (("NaN",{"delta":0.5,"gamma":0.001,"theta":-4,"vega":2,"iv":20}),
                        ("100",{}),("100",{"delta":-0.5,"gamma":0.001,"theta":-4,"vega":2,"iv":20})):
            with self.subTest(quote=quote,g=g),self.assertRaises(AutoATMBlocked):
                paper_greek_exit(selected=p,premium=quote,strategy="ORB18",greeks=g)


class DailyEntryTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory(prefix="optionx_autoatm_test_")
        self.db=open_shadow_gate(Path(self.dir.name)/"offline.sqlite3")

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def reserve(self,signal,market="NIFTY",now=NOW):
        return reserve_shadow_entry(self.db,owner=OWNER,market=market,signal_id=signal,now=now)

    def state(self,signal,status,now=NOW):
        return shadow_set_state(self.db,owner=OWNER,signal_id=signal,new_state=status,
                                now=now,synthetic_evidence=True)

    def test_first_stop_then_second_target_then_locked_forever_today(self):
        first=self.reserve(C1)
        self.assertEqual(first["remainingSlots"],1)
        self.state(C1,"FILLED")
        self.state(C1,"STOP_EXIT")
        second=self.reserve(C2,"BANKNIFTY")
        self.assertEqual(second["remainingSlots"],0)
        self.state(C2,"FILLED")
        self.state(C2,"TARGET_EXIT")
        status=shadow_daily_status(self.db,owner=OWNER,now=NOW)
        self.assertEqual(status["entryAttempts"],2)
        self.assertTrue(status["noNewEntries"])
        self.assertEqual(status["remaining"],0)
        with self.assertRaisesRegex(AutoATMBlocked,"TWO_ENTRY_DAILY_LIMIT_REACHED"):
            self.reserve(C3)

    def test_unknown_first_order_prevents_duplicate_or_second(self):
        self.reserve(C1)
        with self.assertRaisesRegex(AutoATMBlocked,"DUPLICATE_STRATEGY_SIGNAL"):
            self.reserve(C1)
        with self.assertRaisesRegex(AutoATMBlocked,"PREVIOUS_ENTRY_OR_EXIT_UNRESOLVED"):
            self.reserve(C2)

    def test_reject_consumes_slot_instead_of_infinite_retries(self):
        self.reserve(C1)
        self.state(C1,"REJECTED")
        self.reserve(C2)
        self.state(C2,"REJECTED")
        with self.assertRaises(AutoATMBlocked):
            self.reserve(C3)

    def test_open_position_after_second_entry_does_not_allow_third(self):
        self.reserve(C1)
        self.state(C1,"FILLED")
        self.state(C1,"STOP_EXIT")
        self.reserve(C2)
        self.state(C2,"PARTIAL")
        status=shadow_daily_status(self.db,owner=OWNER,now=NOW)
        self.assertEqual(status["openOrUnknown"],1)
        self.assertTrue(status["noNewEntries"])
        with self.assertRaises(AutoATMBlocked):
            self.reserve(C3)

    def test_restart_retains_count_and_blocks_third(self):
        path=self.db.execute("PRAGMA database_list").fetchone()[2]
        self.reserve(C1);self.state(C1,"FILLED");self.state(C1,"STOP_EXIT")
        self.reserve(C2);self.state(C2,"FILLED");self.state(C2,"TARGET_EXIT")
        self.db.close();self.db=open_shadow_gate(path)
        with self.assertRaises(AutoATMBlocked):
            self.reserve(C3)

    def test_new_india_day_resets_only_on_new_day(self):
        self.reserve(C1);self.state(C1,"REJECTED")
        later=datetime(2026,11,26,11,15,tzinfo=IST)
        r=self.reserve(C1,now=later)
        self.assertEqual(r["remainingSlots"],1)

    def test_outside_entry_hours_blocked(self):
        for time_arg in (datetime(2026,11,25,8,30,tzinfo=IST),
                         datetime(2026,11,25,14,45,tzinfo=IST),
                         datetime(2026,11,28,11,15,tzinfo=IST)):
            with self.assertRaisesRegex(AutoATMBlocked,"ENTRY_OUTSIDE_APPROVED_HOURS"):
                self.reserve(C1,now=time_arg)

    def test_terminal_states_cannot_reopen_or_fabricate_exit(self):
        self.reserve(C1)
        with self.assertRaises(AutoATMBlocked):
            self.state(C1,"STOP_EXIT")
        self.state(C1,"REJECTED")
        with self.assertRaises(AutoATMBlocked):
            self.state(C1,"FILLED")


if __name__=="__main__":
    unittest.main()
