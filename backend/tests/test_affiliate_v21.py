"""Iteration 21 — Refer & Earn (SellAuth affiliate program) backend tests.

Rules:
- Read freely from SellAuth. Enrolling a test customer is fine (creates a code, harmless).
- Never create real checkouts/invoices. Never mark payouts paid.
- Balances are $0 — payout requests will fail naturally, assert the error is validation not 500.
"""
import os
import asyncio
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load env
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


# ---------------- fixtures ----------------
def _register_user():
    # SellAuth invite rejects reserved test TLDs (.dev, .test) and example.com. Mailinator
    # is a public trash-mailbox domain that SellAuth accepts, and mail sent there is safe
    # to ignore.
    email = f"testaff{uuid.uuid4().hex[:10]}@mailinator.com"
    password = "Testpass123!"
    session = requests.Session()
    r = session.post(f"{API}/auth/register",
                     json={"email": email, "password": password, "name": "Aff Tester"},
                     timeout=30)
    assert r.status_code == 200, r.text
    return session, email


@pytest.fixture(scope="module")
def user_session():
    session, email = _register_user()
    return session, email


@pytest.fixture(scope="module")
def second_user_session():
    session, email = _register_user()
    return session, email


# ---------------- /api/affiliate/me ----------------
class TestAffiliateMe:
    def test_requires_auth(self):
        r = requests.get(f"{API}/affiliate/me", timeout=15)
        assert r.status_code == 401

    def test_shape_for_authed_user(self, user_session):
        session, _ = user_session
        r = session.get(f"{API}/affiliate/me", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("program_enabled") is True
        for key in ("is_affiliate", "code", "link", "balance", "lifetime_earnings",
                    "referrals_count", "commission", "payout", "attribution_window_days"):
            assert key in d, f"missing {key}"
        assert d["attribution_window_days"] == 30
        c = d["commission"]
        for k in ("min_percent", "max_percent", "excluded_products",
                  "buyer_discount_percent", "tier_id"):
            assert k in c, f"commission missing {k}"
        # range 0-10 per spec
        assert c["min_percent"] == 0
        assert c["max_percent"] <= 10
        # Event Passes named as 0%
        assert any("event" in p.lower() or "pass" in p.lower() for p in c["excluded_products"]), c["excluded_products"]
        assert c["tier_id"] == 622
        p = d["payout"]
        assert p["enabled"] is True
        assert p["min_amount"] == 10
        assert set(p["methods"].keys()) == {"cashapp", "btc", "sol", "ltc", "usdc"}

    def test_ignores_client_supplied_identity(self, user_session):
        session, _ = user_session
        # Try to spoof via query params AND body — /affiliate/me is a GET, extra params
        # must not swap identity. Also test that a body doesn't help.
        r = session.get(f"{API}/affiliate/me",
                        params={"customer_id": 99999, "email": "attacker@x.com",
                                "sellauth_customer_id": 1},
                        timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Response should still reflect the caller's own state — attacker code (like 4LFSA649
        # which belongs to admin) must not appear.
        assert d.get("code", "") != "4LFSA649"


# ---------------- /api/affiliate/enroll ----------------
class TestEnroll:
    def test_requires_auth(self):
        r = requests.post(f"{API}/affiliate/enroll", timeout=15)
        assert r.status_code == 401

    def test_enroll_new_customer_and_idempotent(self, user_session):
        session, email = user_session
        # Enrol
        r1 = session.post(f"{API}/affiliate/enroll", timeout=60)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["is_affiliate"] is True
        assert d1["code"] and len(d1["code"]) <= 16
        assert d1["link"].startswith("https://pokecoins.cc/?ref=")
        assert d1["link"].endswith(d1["code"])
        assert d1["commission"]["tier_id"] == 622

        # Idempotent — second enroll returns SAME code
        r2 = session.post(f"{API}/affiliate/enroll", timeout=60)
        assert r2.status_code == 200
        assert r2.json()["code"] == d1["code"]

    def test_ignores_client_supplied_identity_in_body(self, second_user_session, user_session):
        # Second user tries to pass first user's id/email/code — must be ignored.
        session_a, email_a = user_session
        first = session_a.get(f"{API}/affiliate/me", timeout=30).json()

        session_b, email_b = second_user_session
        r = session_b.post(f"{API}/affiliate/enroll",
                           json={"customer_id": 1, "email": email_a,
                                 "sellauth_customer_id": 1, "affiliate_code": first["code"]},
                           timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # Must be a distinct code — server ignored the body attempt
        assert d["code"] != first["code"], "server accepted client-supplied affiliate_code!"
        assert d["is_affiliate"] is True


# ---------------- /api/affiliate/payout ----------------
class TestPayout:
    def test_requires_auth(self):
        r = requests.post(f"{API}/affiliate/payout",
                          json={"amount": 10, "method": "btc", "destination": "abc"},
                          timeout=15)
        assert r.status_code == 401

    def test_below_minimum(self, user_session):
        session, _ = user_session
        r = session.post(f"{API}/affiliate/payout",
                         json={"amount": 5, "method": "btc",
                               "destination": "bc1qexampleaddresshere"},
                         timeout=30)
        assert r.status_code == 400
        assert "minimum" in r.json()["detail"].lower()

    def test_unknown_method_rejected(self, user_session):
        session, _ = user_session
        r = session.post(f"{API}/affiliate/payout",
                         json={"amount": 15, "method": "paypal",
                               "destination": "somebody@x.com"},
                         timeout=30)
        assert r.status_code == 422  # pydantic Literal reject

    def test_usdc_requires_chain(self, user_session):
        session, _ = user_session
        r = session.post(f"{API}/affiliate/payout",
                         json={"amount": 15, "method": "usdc",
                               "destination": "0xabc123", "chain": ""},
                         timeout=30)
        assert r.status_code == 400
        assert "chain" in r.json()["detail"].lower()

    def test_above_balance(self, user_session):
        # Balance is $0, so any valid amount ≥ 10 must fail on balance check
        session, _ = user_session
        r = session.post(f"{API}/affiliate/payout",
                         json={"amount": 15, "method": "btc",
                               "destination": "bc1qexampleaddresshere"},
                         timeout=30)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"].lower()
        # Either "balance" (our guard) or SellAuth's validation msg — must not be 500
        assert "balance" in detail or "affiliate" in detail or "insufficient" in detail, detail

    def test_cannot_target_other_user(self, user_session, second_user_session):
        session_b, _ = second_user_session
        # attempt to pass another user's id — should still be routed to caller's own
        r = session_b.post(f"{API}/affiliate/payout",
                           json={"amount": 15, "method": "btc", "destination": "bc1qexample",
                                 "customer_id": 1, "sellauth_customer_id": 1,
                                 "user_id": "000000000000000000000000"},
                           timeout=30)
        # Will fail on balance (caller has $0), but importantly not 500 and not moving
        # somebody else's money.
        assert r.status_code == 400, r.text


# ---------------- attribution_code / payout_details_line unit tests ----------------
class TestAttributionAndPayoutFmt:
    def test_payout_details_line_cashapp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import payout_details_line
        from models import PayoutRequest
        line = payout_details_line(PayoutRequest(
            amount=10, method="cashapp", destination="$tester"))
        assert line == "Cash App: $tester"

    def test_payout_details_line_usdc_with_chain(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import payout_details_line
        from models import PayoutRequest
        line = payout_details_line(PayoutRequest(
            amount=10, method="usdc", destination="0xabc", chain="Solana"))
        assert line == "USDC (Solana): 0xabc"

    def test_attribution_code_no_coupon_passes_ref(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import attribution_code
        result = asyncio.get_event_loop().run_until_complete(
            attribution_code("MYCODE123", has_coupon=False))
        assert result == "MYCODE123"

    def test_attribution_code_empty_ref_returns_none(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import attribution_code
        result = asyncio.get_event_loop().run_until_complete(
            attribution_code("", has_coupon=False))
        assert result is None

    def test_attribution_code_with_coupon_and_zero_buyer_discount_passes(self):
        """Default tier has discount_percentage=0, so with a coupon the ref IS still passed."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import attribution_code
        result = asyncio.get_event_loop().run_until_complete(
            attribution_code("MYCODE123", has_coupon=True))
        # Live shop currently has buyer_discount 0, so the code should pass through
        assert result == "MYCODE123"

    def test_attribution_code_with_coupon_and_buyer_discount_dropped(self, monkeypatch):
        """When a tier carries a buyer discount > 0 AND coupon is applied, the ref MUST be dropped."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from server import attribution_code
        import sellauth_affiliate as sa

        async def fake_tier():
            return {"id": 622, "percentage": 7, "discount_percentage": 5, "products": []}

        monkeypatch.setattr(sa, "default_tier", fake_tier)
        result = asyncio.get_event_loop().run_until_complete(
            attribution_code("MYCODE123", has_coupon=True))
        assert result is None, "ref must be dropped when buyer discount would stack"


# ---------------- referral_link builds correctly ----------------
class TestReferralLink:
    def test_link_format(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import sellauth_affiliate as sa
        link = sa.referral_link("ABC123")
        assert link == "https://pokecoins.cc/?ref=ABC123"

    def test_new_code_within_16_chars(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import sellauth_affiliate as sa
        for seed in ["Ada Lovelace", "poke@example.com", "x", "A" * 30]:
            code = sa.new_code(seed)
            assert 1 <= len(code) <= 16, (seed, code)
