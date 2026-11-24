"""Angel One one-login-per-trading-day policy regression, no broker connections."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from unittest import TestCase
from unittest.mock import patch

import angel_gateway as ag
from live_v7.angel_day_session_policy import (
    BASE_SECONDS, bounded_readonly_expiry, is_day_scope_allowed,
)


def bearer_with_exp(exp: int) -> str:
    def e(x):
        return base64.urlsafe_b64encode(json.dumps(x,separators=(',',':')).encode()).decode().rstrip("=")
    return e({"alg": "HS256", "typ": "JWT"}) + "." + e({"exp": exp}) + ".fake_signature"


# Tue 24 November 2026 at 10:00 IST
LOGIN = datetime(2026,11,24,4,30,tzinfo=timezone.utc).timestamp()
# Same trading day 15:30 IST
MARKET_END = datetime(2026,11,24,10,0,tzinfo=timezone.utc).timestamp()


class AngelDayPolicyTests(TestCase):
    def test_normal_default_is_fifteen_minutes(self):
        expiry, scope = bounded_readonly_expiry(LOGIN,bearer_with_exp(int(MARKET_END+5000)))
        self.assertEqual(expiry, LOGIN+BASE_SECONDS)
        self.assertEqual(scope,"SHORT_READONLY")

    def test_opted_in_session_caps_at_market_close(self):
        expiry, scope = bounded_readonly_expiry(
            LOGIN,bearer_with_exp(int(MARKET_END+5000)),day_policy_requested=True)
        self.assertEqual(expiry,MARKET_END)
        self.assertEqual(scope,"TRADING_DAY_READONLY")

    def test_broker_jwt_exp_shortens_session_without_faking_validity(self):
        jwt=bearer_with_exp(int(LOGIN+3300))
        expiry,scope=bounded_readonly_expiry(LOGIN,jwt,day_policy_requested=True)
        self.assertLessEqual(expiry,LOGIN+3180)
        self.assertEqual(scope,"TRADING_DAY_READONLY")

    def test_missing_or_malformed_jwt_never_extends_to_day(self):
        for token in ("fake","aaa.broken.zzz","bad.body.here",bearer_with_exp(-1)):
            expiry,scope=bounded_readonly_expiry(LOGIN,token,day_policy_requested=True)
            self.assertLessEqual(expiry,LOGIN+BASE_SECONDS)
            self.assertEqual(scope,"SHORT_READONLY")

    def test_weekend_and_after_regular_session_not_extended(self):
        saturday=datetime(2026,11,28,4,30,tzinfo=timezone.utc).timestamp()
        evening=datetime(2026,11,24,12,0,tzinfo=timezone.utc).timestamp()
        for t in (saturday, evening):
            expiry,scope=bounded_readonly_expiry(t,bearer_with_exp(int(t+100000)),day_policy_requested=True)
            self.assertEqual(expiry,t+BASE_SECONDS)
            self.assertEqual(scope,"SHORT_READONLY")

    def test_browser_or_render_mode_never_enables_day_scope_by_default(self):
        self.assertFalse(is_day_scope_allowed({}))
        self.assertFalse(is_day_scope_allowed({
            "OPTIONX_ANGEL_READONLY_DAY_SESSION":"1",
            "OPTIONX_OWNER_USER_ID":"private-owner"
        }))
        self.assertFalse(is_day_scope_allowed({
            "OPTIONX_ANGEL_READONLY_DAY_SESSION":"1",
            "OPTIONX_OWNER_USER_ID":"private-owner",
            "OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED":"1",
            "OPTIONX_LIVE_ORDERS_ENABLED":"1",
        }))
        self.assertTrue(is_day_scope_allowed({
            "OPTIONX_ANGEL_READONLY_DAY_SESSION":"1",
            "OPTIONX_OWNER_USER_ID":"private-owner",
            "OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED":"1",
        }))

    def test_existing_angel_gateway_default_15min_and_no_secret_in_status(self):
        user="123e4567-e89b-12d3-a456-426614174000"
        creds={"apiKey":"KEY_0123456789","clientCode":"AB1234","pin":"1234","totp":"123456"}
        resp={"jwtToken":bearer_with_exp(int(MARKET_END+5000))}
        def fake_call(method, endpoint, key, token="", payload=None, fetch=None):
            return resp if method=="POST" else {"clientcode":"AB1234"}
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":user,
                                      "OPTIONX_ANGEL_READONLY_DAY_SESSION":"0",
                                      "OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED":"0"}), \
             patch.object(ag,"_post_or_get",side_effect=fake_call):
            ag._SESSIONS.clear();ag._ATTEMPTS.clear()
            try:
                info=ag.connect(user,creds,now=LOGIN)
                self.assertEqual(info["readOnlySessionScope"],"SHORT_READONLY")
                self.assertFalse(info["connectedToAwsAutoTrading"])
                self.assertTrue(info["temporaryOneLoginReuse"])
                self.assertTrue(info["connected"])
                self.assertEqual(ag._SESSIONS[user]["expires"],LOGIN+BASE_SECONDS)
                self.assertEqual(ag._SESSIONS[user]["sessionScope"],"SHORT_READONLY")
                self.assertNotIn("pin",ag._SESSIONS[user])
                self.assertNotIn("totp",ag._SESSIONS[user])
                self.assertNotIn("123456",json.dumps(info))
                self.assertFalse(ag.status(user,now=LOGIN+901)["connected"])
                self.assertTrue(ag.status(user,now=LOGIN+901)["needsFreshTotp"])
            finally:
                ag._SESSIONS.clear();ag._ATTEMPTS.clear()

    def test_opted_in_private_day_policy_does_not_enable_orders(self):
        user="123e4567-e89b-12d3-a456-426614174000"
        creds={"apiKey":"KEY_0123456789","clientCode":"AB1234","pin":"1234","totp":"123456"}
        def broker(method,endpoint,key,token="",payload=None,fetch=None):
            return {"jwtToken":bearer_with_exp(int(MARKET_END+1000))} if method=="POST" else {"clientcode":"AB1234"}
        env={"OPTIONX_OWNER_USER_ID":user,
             "OPTIONX_ANGEL_READONLY_DAY_SESSION":"1",
             "OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED":"1",
             "OPTIONX_REAL_ORDERS_ENABLED":"0",
             "OPTIONX_LIVE_ORDERS_ENABLED":"0"}
        with patch.dict(os.environ,env),patch.object(ag,"_post_or_get",side_effect=broker):
            ag._SESSIONS.clear();ag._ATTEMPTS.clear()
            try:
                state=ag.connect(user,creds,now=LOGIN)
                self.assertEqual(state["readOnlySessionScope"],"TRADING_DAY_READONLY")
                self.assertEqual(ag._SESSIONS[user]["expires"], MARKET_END)
                self.assertFalse(state["orderExecutionEnabled"])
                self.assertFalse(state["connectedToAwsAutoTrading"])
                self.assertFalse(ag.status(user,now=MARKET_END+1)["connected"])
            finally:
                ag._SESSIONS.clear();ag._ATTEMPTS.clear()
