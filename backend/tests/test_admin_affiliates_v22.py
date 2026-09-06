"""Iteration 22 — Admin promoter leaderboard and tier reassignment.

Tests GET /api/admin/affiliates and PUT /api/admin/affiliates/{id}/tier?tier_id=...
Rules:
- Do NOT create/delete tiers. Only 622 exists — reassign 622 to itself for safe test.
- Do NOT suspend affiliates or mark payouts paid.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"
DEFAULT_TIER_ID = 622


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def customer_session():
    email = f"testcust{uuid.uuid4().hex[:10]}@mailinator.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "Testpass123!", "name": "Cust"}, timeout=30)
    assert r.status_code == 200, r.text
    return s


# ---------------- GET /api/admin/affiliates ----------------
class TestAdminAffiliatesGet:
    def test_requires_auth(self):
        r = requests.get(f"{API}/admin/affiliates", timeout=15)
        assert r.status_code == 401

    def test_forbids_normal_customer(self, customer_session):
        r = customer_session.get(f"{API}/admin/affiliates", timeout=30)
        assert r.status_code == 403

    def test_admin_ok_and_shape(self, admin_session):
        r = admin_session.get(f"{API}/admin/affiliates", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "affiliates" in d and "tiers" in d and "stats" in d

        stats = d["stats"]
        for k in ("total_affiliates", "commissions_all_time",
                  "attributed_revenue_all_time", "attributed_orders",
                  "pending_payout_requests", "window_days"):
            assert k in stats, f"stats missing {k}"
        assert stats["window_days"] == 30

        # tiers array
        assert isinstance(d["tiers"], list) and len(d["tiers"]) >= 1
        assert any(t["id"] == DEFAULT_TIER_ID for t in d["tiers"])

        # affiliates — each row shape
        assert isinstance(d["affiliates"], list)
        for a in d["affiliates"]:
            for k in ("customer_id", "email", "code", "earnings", "balance",
                      "referrals", "tier_id", "tier_name", "tier_percent",
                      "joined_at"):
                assert k in a, f"row missing {k}"

    def test_sorted_by_earnings_then_referrals_desc(self, admin_session):
        r = admin_session.get(f"{API}/admin/affiliates", timeout=60)
        d = r.json()
        rows = d["affiliates"]
        keys = [(a["earnings"], a["referrals"]) for a in rows]
        assert keys == sorted(keys, reverse=True), keys


# ---------------- PUT /api/admin/affiliates/{id}/tier ----------------
class TestAdminAffiliateTier:
    def _pick_affiliate(self, admin_session):
        d = admin_session.get(f"{API}/admin/affiliates", timeout=60).json()
        assert d["affiliates"], "no affiliates found on live shop"
        return d["affiliates"][0]

    def test_requires_auth(self, admin_session):
        row = self._pick_affiliate(admin_session)
        r = requests.put(f"{API}/admin/affiliates/{row['customer_id']}/tier",
                         params={"tier_id": DEFAULT_TIER_ID}, timeout=15)
        assert r.status_code == 401

    def test_forbids_normal_customer(self, admin_session, customer_session):
        row = self._pick_affiliate(admin_session)
        r = customer_session.put(f"{API}/admin/affiliates/{row['customer_id']}/tier",
                                 params={"tier_id": DEFAULT_TIER_ID}, timeout=30)
        assert r.status_code == 403

    def test_admin_reassign_same_tier_ok(self, admin_session):
        row = self._pick_affiliate(admin_session)
        before = row
        r = admin_session.put(f"{API}/admin/affiliates/{row['customer_id']}/tier",
                              params={"tier_id": DEFAULT_TIER_ID}, timeout=60)
        assert r.status_code == 200, r.text

        # Reload, confirm unchanged (code/earnings/balance) and tier still 622
        d2 = admin_session.get(f"{API}/admin/affiliates", timeout=60).json()
        after = next((a for a in d2["affiliates"] if a["customer_id"] == before["customer_id"]), None)
        assert after, "affiliate vanished after tier reassign"
        assert after["tier_id"] == DEFAULT_TIER_ID
        assert after["code"] == before["code"]
        assert after["earnings"] == before["earnings"]
        assert after["balance"] == before["balance"]

    def test_bogus_tier_id_returns_readable_error_not_500(self, admin_session):
        row = self._pick_affiliate(admin_session)
        r = admin_session.put(f"{API}/admin/affiliates/{row['customer_id']}/tier",
                              params={"tier_id": 999999999}, timeout=60)
        assert r.status_code in (400, 422, 502), r.status_code
        # Backend must NOT 500 with a stack trace. Note: Cloudflare/edge replaces 5xx
        # bodies with a generic HTML page, so we only assert here that if the body IS
        # JSON, it carries a readable detail — the actual backend log shows the SellAuth
        # error text ("AffiliateTier not found") is passed through as the detail.
        try:
            body = r.json()
            assert "detail" in body and body["detail"], body
        except ValueError:
            # 502 body was rewritten by the edge — acceptable per spec (4xx/502 allowed)
            # as long as it's not a 500 with stack trace, which we already asserted.
            pass
