"""Regression + security tests for the P0/P1 hardening pass (iteration 28).

Covers:
- Admin login rotates from 'admin' -> 'acientraft2020'.
- CSRF guard: cookie-only unsafe writes blocked without allowed Origin.
- Non-admin / anon cannot reach /api/admin/*.
- get_order 403 across customers.
- Guest order access_key: refused without k=, accepted with correct k=.
- Guest order messages GET/POST honour the same key.
- popup coupon endpoint is rate limited to 3/day per IP.
- Legal endpoint still serves markdown for terms + privacy.
"""
import os
import secrets
import time
import uuid

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ORIGIN = BASE_URL  # same as CORS_ORIGINS entry

ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "acientraft2020"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _bearer_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {token}",
                      "Origin": ORIGIN})
    return s


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      headers={"Origin": ORIGIN}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_client(admin_token):
    return _bearer_session(admin_token)


def _register_customer():
    email = f"test_sec_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "P@ssword123!", "name": "Sec Test"},
                      headers={"Origin": ORIGIN}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    return email, body["access_token"], body["user"]["id"]


@pytest.fixture(scope="session")
def customer_a():
    email, token, uid = _register_customer()
    return {"email": email, "token": token, "id": uid,
            "client": _bearer_session(token)}


@pytest.fixture(scope="session")
def customer_b():
    email, token, uid = _register_customer()
    return {"email": email, "token": token, "id": uid,
            "client": _bearer_session(token)}


# ---------- admin login regression ----------
class TestAdminLogin:
    def test_new_password_works(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          headers={"Origin": ORIGIN}, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"

    def test_old_password_rejected(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": "admin"},
                          headers={"Origin": ORIGIN}, timeout=15)
        assert r.status_code in (401, 429), r.text


# ---------- CSRF guard ----------
class TestCSRFGuard:
    def test_cookie_only_write_without_origin_blocked(self):
        # login to get cookies (no bearer)
        s = requests.Session()
        r = s.post(f"{API}/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                   headers={"Origin": ORIGIN}, timeout=15)
        assert r.status_code == 200
        # Now do a write with cookie but a foreign Origin -> blocked
        r2 = s.post(f"{API}/auth/logout",
                    headers={"Origin": "https://evil.example.com"}, timeout=15)
        assert r2.status_code == 403, r2.text
        assert "Cross-site" in r2.text or "blocked" in r2.text.lower()

    def test_bearer_auth_bypasses_csrf(self, admin_client):
        # A safe write endpoint we can reach: /auth/logout
        r = admin_client.post(f"{API}/auth/logout", timeout=15)
        assert r.status_code == 200


# ---------- admin endpoint AuthZ ----------
class TestAdminAuthZ:
    def test_anonymous_admin_endpoints_401(self):
        r = requests.get(f"{API}/admin/orders",
                         headers={"Origin": ORIGIN}, timeout=15)
        assert r.status_code == 401

    def test_customer_admin_endpoints_403(self, customer_a):
        r = customer_a["client"].get(f"{API}/admin/orders", timeout=15)
        assert r.status_code == 403

    def test_customer_admin_write_403(self, customer_a):
        r = customer_a["client"].post(f"{API}/admin/coupons",
                                       json={"code": "TESTX", "percent_off": 5}, timeout=15)
        assert r.status_code in (403, 422)


# ---------- Order cross-customer isolation ----------
class TestOrderIsolation:
    def _seed_order(self, mongo, user_id: str, email: str, access_key=None):
        doc = {
            "user_id": user_id,
            "user_email": email,
            "origin_url": BASE_URL,
            "items": [],
            "total": 0.0,
            "subtotal": 0.0,
            "discount": 0.0,
            "coupon_code": None,
            "status": "pending",
            "payment_status": "paid",
            "session_id": "",
            "ptc_username_enc": "",
            "ptc_password_enc": "",
            "created_at": __import__("datetime").datetime.utcnow(),
            "updated_at": __import__("datetime").datetime.utcnow(),
        }
        if access_key:
            doc["access_key"] = access_key
        return str(mongo.orders.insert_one(doc).inserted_id)

    def test_customer_cannot_read_others_order(self, mongo, customer_a, customer_b):
        order_id = self._seed_order(mongo, customer_a["id"], customer_a["email"])
        try:
            # A reads own order -> 200
            r_ok = customer_a["client"].get(f"{API}/orders/{order_id}", timeout=15)
            assert r_ok.status_code == 200, r_ok.text
            # B tries to read A's -> 403
            r = customer_b["client"].get(f"{API}/orders/{order_id}", timeout=15)
            assert r.status_code == 403
            # B tries to read A's messages -> 403
            r2 = customer_b["client"].get(f"{API}/orders/{order_id}/messages", timeout=15)
            assert r2.status_code == 403
        finally:
            mongo.orders.delete_one({"_id": ObjectId(order_id)})


# ---------- Guest order access_key ----------
class TestGuestOrderAccessKey:
    def test_guest_order_requires_key(self, mongo):
        # Seed a guest order (no user_id) with an access_key
        key = secrets.token_urlsafe(16)
        guest_email = f"guest_sec_{uuid.uuid4().hex[:8]}@example.com"
        doc = {
            "user_id": "",
            "user_email": guest_email,
            "origin_url": BASE_URL,
            "items": [],
            "total": 0.0, "subtotal": 0.0, "discount": 0.0,
            "coupon_code": None,
            "status": "pending", "payment_status": "paid",
            "session_id": "",
            "ptc_username_enc": "", "ptc_password_enc": "",
            "access_key": key,
            "created_at": __import__("datetime").datetime.utcnow(),
            "updated_at": __import__("datetime").datetime.utcnow(),
        }
        order_id = str(mongo.orders.insert_one(doc).inserted_id)
        try:
            # No key -> 403
            r1 = requests.get(f"{API}/orders/{order_id}",
                              headers={"Origin": ORIGIN}, timeout=15)
            assert r1.status_code == 403
            assert "confirmation email" in r1.text.lower() or "blocked" in r1.text.lower()

            # Wrong key -> 403
            r2 = requests.get(f"{API}/orders/{order_id}?k=nope",
                              headers={"Origin": ORIGIN}, timeout=15)
            assert r2.status_code == 403

            # Correct key -> 200
            r3 = requests.get(f"{API}/orders/{order_id}?k={key}",
                              headers={"Origin": ORIGIN}, timeout=15)
            assert r3.status_code == 200, r3.text

            # messages endpoint honors key
            r4 = requests.get(f"{API}/orders/{order_id}/messages",
                              headers={"Origin": ORIGIN}, timeout=15)
            assert r4.status_code == 403
            r5 = requests.get(f"{API}/orders/{order_id}/messages?k={key}",
                              headers={"Origin": ORIGIN}, timeout=15)
            assert r5.status_code == 200
        finally:
            mongo.orders.delete_one({"_id": ObjectId(order_id)})

    def test_legacy_order_without_key_still_works(self, mongo):
        """Orders emailed before keys existed must still open without ?k=."""
        guest_email = f"legacy_sec_{uuid.uuid4().hex[:8]}@example.com"
        doc = {
            "user_id": "",
            "user_email": guest_email,
            "origin_url": BASE_URL,
            "items": [], "total": 0.0, "subtotal": 0.0, "discount": 0.0,
            "coupon_code": None,
            "status": "pending", "payment_status": "paid",
            "session_id": "",
            "ptc_username_enc": "", "ptc_password_enc": "",
            # no access_key
            "created_at": __import__("datetime").datetime.utcnow(),
            "updated_at": __import__("datetime").datetime.utcnow(),
        }
        order_id = str(mongo.orders.insert_one(doc).inserted_id)
        try:
            r = requests.get(f"{API}/orders/{order_id}",
                             headers={"Origin": ORIGIN}, timeout=15)
            assert r.status_code == 200, r.text
        finally:
            mongo.orders.delete_one({"_id": ObjectId(order_id)})


# ---------- Popup offer rate limit ----------
class TestPopupOfferRateLimit:
    def test_popup_offer_rate_limited(self, mongo, admin_client):
        # find or create a discount_offer popup
        popup = mongo.popups.find_one({"type": "discount_offer"})
        if not popup:
            pytest.skip("No discount_offer popup seeded in DB")
        popup_id = str(popup["_id"])

        # Clear rate limits for this IP action to make the test deterministic
        mongo.rate_limits.delete_many({"key": {"$regex": "^popup-offer:"}})

        results = []
        for _ in range(5):
            r = requests.post(f"{API}/popups/{popup_id}/offer",
                              headers={"Origin": ORIGIN}, timeout=15)
            results.append(r.status_code)
            time.sleep(0.2)
        # Should be 3 successes then 429
        successes = sum(1 for s in results if s == 200)
        rate_limited = sum(1 for s in results if s == 429)
        assert successes <= 3, f"more than 3 popup offers succeeded: {results}"
        assert rate_limited >= 1, f"no 429 responses observed: {results}"
        # Cleanup
        mongo.rate_limits.delete_many({"key": {"$regex": "^popup-offer:"}})
        mongo.coupons.delete_many({"description": {"$regex": "^Popup offer:"}})


# ---------- Legal page ----------
class TestLegalPage:
    def test_legal_get_returns_terms_and_privacy(self):
        r = requests.get(f"{API}/legal", headers={"Origin": ORIGIN}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "terms" in body and "privacy" in body
        assert isinstance(body["terms"], str) and len(body["terms"]) > 50
        assert isinstance(body["privacy"], str) and len(body["privacy"]) > 50


# ---------- Read-only regression sweep ----------
class TestPublicReadEndpoints:
    @pytest.mark.parametrize("path", [
        "/health", "/products", "/categories", "/popups", "/settings/banner",
        "/reviews", "/admin/settings/reviews",  # last one requires admin? check
    ])
    def test_public_read(self, path):
        r = requests.get(f"{API}{path}", headers={"Origin": ORIGIN}, timeout=15)
        # admin-only endpoints will 401; that is fine, we just don't want 500s
        assert r.status_code in (200, 401, 403), f"{path} -> {r.status_code} {r.text[:200]}"


class TestAdminReadSweep:
    @pytest.mark.parametrize("path", [
        "/admin/orders", "/admin/coupons", "/admin/reviews", "/admin/waitlist",
        "/admin/popups", "/admin/affiliates", "/admin/payouts", "/admin/unread",
        "/admin/settings/payout-methods", "/admin/analytics",
    ])
    def test_admin_get(self, admin_client, path):
        r = admin_client.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"
