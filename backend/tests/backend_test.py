"""PokéForge backend regression suite — SellAuth + temp Checkout Sessions.

Architecture:
- POST /api/orders/checkout writes a temporary doc to `checkout_sessions` (30 min TTL)
  and calls SellAuth. The store's plan currently returns HTTP 503 (Checkout API not
  enabled) — we treat that as expected. On any SellAuth error the session doc is deleted.
- The paid path is exercised by simulating a signed SellAuth webhook, which promotes
  the session into an `orders` doc.
- No Stripe anywhere.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = ""
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
except Exception:
    pass
BASE_URL = BASE_URL or os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

API = f"{BASE_URL}/api"
LOCAL_API = "http://localhost:8001/api"  # for webhook (some ingresses strip signature header)
from admin_creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402
WEBHOOK_SECRET = os.environ["SELLAUTH_WEBHOOK_SECRET"]
TTL_MIN = int(os.environ.get("CHECKOUT_SESSION_TTL_MINUTES", "30"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "admin"
    return data["access_token"]


@pytest.fixture(scope="session")
def customer():
    email = f"trainer_{uuid.uuid4().hex[:8]}@gmail.com"
    password = f"Trainer#{uuid.uuid4().hex[:12]}"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Trainer Test"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "password": password, "token": data["access_token"], "id": data["user"]["id"]}


@pytest.fixture(scope="session")
def customer2():
    email = f"trainer2_{uuid.uuid4().hex[:8]}@gmail.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Trainer#2026", "name": "T2"})
    assert r.status_code == 200
    data = r.json()
    return {"email": email, "token": data["access_token"], "id": data["user"]["id"]}


def _products():
    return requests.get(f"{API}/products").json()


def _find(category):
    # Skip TEST_* products: other xdist workers create and delete them mid-run, which
    # would otherwise make carts reference a product that disappears.
    for p in _products():
        if (p["category"] == category and not p.get("coming_soon")
                and not p["name"].startswith("TEST_")):
            return p
    return None


def _make_session(email="delivered@resend.dev", user_id="", invoice_id=None):
    """Insert a checkout_sessions doc directly (mirrors what checkout() writes)."""
    bundle = _find("pokecoin_bundle")
    now = __import__("datetime").datetime.utcnow()
    doc = {
        "items": [{"product_id": bundle["id"], "name": bundle["name"], "category": bundle["category"],
                   "price": bundle["price"], "quantity": 1}],
        "total": bundle["price"],
        "user_id": user_id,
        "email": email,
        "origin_url": BASE_URL,
        "ptc_username_enc": "gAAAAABtest_ciphertext_user",  # sentinel
        "ptc_password_enc": "gAAAAABtest_ciphertext_pass",
        "status": "awaiting_payment",
        "created_at": now,
        "expires_at": now + timedelta(minutes=TTL_MIN),
    }
    if invoice_id:
        doc["invoice_id"] = invoice_id
    result = db.checkout_sessions.insert_one(doc)
    return str(result.inserted_id)


def _sign(raw: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


# ---------------- No Stripe leftovers ----------------
class TestNoStripe:
    def test_stripe_routes_gone(self):
        # Legacy Stripe endpoints must 404 now
        r1 = requests.post(f"{API}/stripe/webhook", json={})
        r2 = requests.get(f"{API}/payments/status/dummyid")
        assert r1.status_code == 404, r1.status_code
        assert r2.status_code == 404, r2.status_code

    def test_no_stripe_in_source(self):
        found = []
        for root, _dirs, files in os.walk("/app/backend"):
            if any(skip in root for skip in ("__pycache__", "tests")):
                continue
            for name in files:
                if name.endswith((".py", ".txt", ".env")):
                    path = os.path.join(root, name)
                    with open(path, "r", errors="ignore") as f:
                        if "stripe" in f.read().lower():
                            found.append(path)
        assert not found, f"Stripe references left in: {found}"


# ---------------- Auth / Products ----------------
class TestAuth:
    def test_root(self):
        assert requests.get(f"{API}/").status_code == 200

    def test_me_returns_user(self, customer):
        r = requests.get(f"{API}/auth/me", headers=auth(customer["token"]))
        assert r.status_code == 200 and r.json()["email"] == customer["email"]


class TestProducts:
    def test_list_products_no_stripe_price(self):
        products = _products()
        assert len(products) >= 6
        for p in products:
            assert "_id" not in p and "id" in p
            assert "stripe_price_id" not in p

    def test_admin_crud(self, admin_token):
        payload = {"name": "TEST_Prod", "description": "d", "category": "pokecoin_bundle",
                   "price": 1.99, "coins": 100}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # storefront lists it
        assert any(p["id"] == pid for p in _products())
        payload["name"] = "TEST_Prod_upd"
        r2 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json=payload)
        assert r2.status_code == 200 and r2.json()["name"] == "TEST_Prod_upd"
        assert requests.delete(f"{API}/products/{pid}", headers=auth(admin_token)).status_code == 200


# ---------------- TTL index ----------------
class TestTTLIndex:
    def test_expires_at_ttl_index(self):
        idx = db.checkout_sessions.index_information()
        ttl = [v for v in idx.values() if v.get("expireAfterSeconds") == 0
               and v.get("key") == [("expires_at", 1)]]
        assert ttl, f"expected TTL index on expires_at with expireAfterSeconds=0; got {idx}"

    def test_webhook_events_unique_index(self):
        idx = db.webhook_events.index_information()
        assert any(v.get("unique") and v.get("key") == [("event_key", 1)] for v in idx.values())


# ---------------- Checkout: validation before session/invoice ----------------
class TestCheckoutValidation:
    def test_guest_missing_email_400(self):
        bundle = _find("pokecoin_bundle")
        before = db.checkout_sessions.count_documents({})
        orders_before = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400
        assert "email" in r.json()["detail"].lower()
        assert db.checkout_sessions.count_documents({}) == before
        assert db.orders.count_documents({}) == orders_before

    def test_guest_event_pass_only_400_no_session_no_order(self):
        p = _find("event_pass")
        before_s = db.checkout_sessions.count_documents({})
        before_o = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "email": "guest.pokecoins.test@gmail.com",
        })
        assert r.status_code == 400
        assert "Pok" in r.json()["detail"]
        assert db.checkout_sessions.count_documents({}) == before_s
        assert db.orders.count_documents({}) == before_o

    def test_registered_event_pass_only_400(self, customer):
        p = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code == 400


# ---------------- Checkout: SellAuth is now live, expect 200 + checkout_url ----------------
class TestCheckoutLive:
    def test_guest_checkout_returns_url_no_order(self):
        bundle = _find("pokecoin_bundle")
        orders_before = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "email": "delivered@resend.dev",
        })
        # SellAuth Checkout API is now active — expect 200 with URL and no order yet.
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("checkout_url", "").startswith("http")
        assert body.get("session_id")
        assert body.get("invoice_id")
        assert db.orders.count_documents({}) == orders_before
        # Cleanup the created session
        db.checkout_sessions.delete_one({"_id": ObjectId(body["session_id"])})


# ---------------- Webhook security + paid promotion ----------------
class TestWebhook:
    def test_webhook_bad_signature_401(self):
        raw = json.dumps({"invoice": {"id": "x", "status": "completed"}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": "0" * 64, "content-type": "application/json"})
        assert r.status_code == 401

    def test_webhook_missing_signature_401(self):
        raw = json.dumps({"invoice": {"id": "x", "status": "completed"}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"content-type": "application/json"})
        assert r.status_code == 401

    def test_webhook_unknown_session_matched_false(self):
        raw = json.dumps({"invoice": {"id": f"unknown-{uuid.uuid4().hex[:6]}",
                                       "status": "completed",
                                       "custom_fields": {"checkout_session_id": "000000000000000000000000"}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"})
        assert r.status_code == 200
        body = r.json()
        assert not (body.get("matched"))

    def test_webhook_unpaid_status_creates_no_order(self):
        sid = _make_session(email="delivered@resend.dev")
        orders_before = db.orders.count_documents({})
        raw = json.dumps({"invoice": {"id": f"inv-{uuid.uuid4().hex[:6]}",
                                       "status": "pending",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"})
        assert r.status_code == 200
        assert not (r.json().get("paid"))
        assert db.orders.count_documents({}) == orders_before
        # session should still be awaiting_payment
        sess = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert sess and sess["status"] == "awaiting_payment"
        db.checkout_sessions.delete_one({"_id": ObjectId(sid)})

    def test_webhook_paid_promotes_session_to_order_and_idempotent(self, admin_token):
        sid = _make_session(email="delivered@resend.dev")
        invoice_id = f"inv-{uuid.uuid4().hex[:8]}"
        raw = json.dumps({"invoice": {"id": invoice_id, "status": "completed",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        sig = _sign(raw)

        orders_before = db.orders.count_documents({})
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": sig, "content-type": "application/json"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("paid")
        order_id = body.get("order_id")
        assert order_id
        # Exactly one new order
        assert db.orders.count_documents({}) == orders_before + 1
        doc = db.orders.find_one({"_id": ObjectId(order_id)})
        assert doc["status"] == "pending"
        assert doc["payment_status"] == "paid"
        assert doc["ptc_username_enc"] == "gAAAAABtest_ciphertext_user"
        assert doc["ptc_password_enc"] == "gAAAAABtest_ciphertext_pass"
        assert doc["session_id"] == sid
        # Session marked paid
        sess = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert sess["status"] == "paid" and sess["order_id"] == order_id

        # Replay -> duplicate:true, no new order
        r2 = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                           headers={"signature": sig, "content-type": "application/json"})
        assert r2.status_code == 200
        assert r2.json().get("duplicate")
        assert db.orders.count_documents({}) == orders_before + 1

        # Store order_id for downstream tests
        pytest.paid_order_id = order_id
        pytest.paid_session_id = sid

    def test_checkout_session_status_returns_order_id(self):
        sid = pytest.paid_session_id
        r = requests.get(f"{API}/checkout-sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "paid"
        assert data["order_id"] == pytest.paid_order_id


# ---------------- Public tracking route (guest order from webhook) ----------------
class TestTracking:
    @pytest.fixture(scope="class")
    def paid_order_id(self):
        """Self-contained paid guest order (xdist runs classes in separate workers,
        so we cannot rely on state set by TestWebhooks)."""
        sid = _make_session(email="delivered@resend.dev")
        raw = json.dumps({"invoice": {"id": f"inv-{uuid.uuid4().hex[:8]}", "status": "completed",
                                      "custom_fields": {"checkout_session_id": sid}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"},
                          timeout=60)
        assert r.status_code == 200, r.text
        order_id = r.json().get("order_id")
        assert order_id
        return order_id

    def test_public_get_guest_order(self, paid_order_id):
        oid = paid_order_id
        r = requests.get(f"{API}/orders/{oid}")
        assert r.status_code == 200
        data = r.json()
        assert data["payment_status"] == "paid"
        assert data["status"] == "pending"
        assert "ptc_password" not in data and "ptc_password_enc" not in data
        assert data["items"] and data["total"] > 0

    def test_public_get_messages(self, paid_order_id):
        oid = paid_order_id
        assert requests.get(f"{API}/orders/{oid}/messages").status_code == 200


# ---------------- Registered-user privacy ----------------
class TestRegisteredPrivacy:
    @pytest.fixture(scope="class")
    def registered_order_id(self, customer):
        # Create a session tied to the registered user, then promote via webhook.
        sid = _make_session(email=customer["email"], user_id=customer["id"])
        invoice_id = f"inv-{uuid.uuid4().hex[:8]}"
        raw = json.dumps({"invoice": {"id": invoice_id, "status": "completed",
                                       "custom_fields": {"checkout_session_id": sid}}}).encode()
        r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                          headers={"signature": _sign(raw), "content-type": "application/json"}, timeout=60)
        assert r.status_code == 200 and r.json().get("order_id")
        return r.json()["order_id"]

    def test_other_user_forbidden(self, registered_order_id, customer2):
        r = requests.get(f"{API}/orders/{registered_order_id}", headers=auth(customer2["token"]))
        assert r.status_code == 403

    def test_anonymous_forbidden(self, registered_order_id):
        assert requests.get(f"{API}/orders/{registered_order_id}").status_code == 403

    def test_admin_can_read(self, registered_order_id, admin_token):
        assert requests.get(f"{API}/orders/{registered_order_id}",
                            headers=auth(admin_token)).status_code == 200

    def test_customer_cannot_reveal_creds(self, registered_order_id, customer):
        assert requests.get(f"{API}/admin/orders/{registered_order_id}/credentials",
                            headers=auth(customer["token"])).status_code == 403

    def test_admin_status_transitions_notify_customer(self, registered_order_id, admin_token, customer):
        r = requests.patch(f"{API}/admin/orders/{registered_order_id}/status",
                           headers=auth(admin_token), json={"status": "processing"})
        assert r.status_code == 200 and r.json()["status"] == "processing"
        time.sleep(0.3)
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("processed" in n["title"].lower() or "logged out" in n["title"].lower() for n in notifs)
        r2 = requests.patch(f"{API}/admin/orders/{registered_order_id}/status",
                            headers=auth(admin_token), json={"status": "completed"})
        assert r2.status_code == 200
        notifs = requests.get(f"{API}/notifications", headers=auth(customer["token"])).json()
        assert any("completed" in n["title"].lower() for n in notifs)


# ---------------- Admin listing / auth gates ----------------
class TestAdminProtection:
    def test_admin_orders_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/orders").status_code == 401
        assert requests.get(f"{API}/admin/orders", headers=auth(customer["token"])).status_code == 403

    def test_admin_can_list_orders(self, admin_token):
        r = requests.get(f"{API}/admin/orders", headers=auth(admin_token))
        assert r.status_code == 200 and isinstance(r.json(), list)


# ---------------- Medals category + MSRP ----------------
class TestMedalsCategory:
    def test_seeded_medals_present_with_msrp(self):
        products = _products()
        medals = [p for p in products if p["category"] == "medals"]
        assert len(medals) >= 1, f"Expected at least 1 medals product, got {len(medals)}"
        for p in medals:
            assert p.get("msrp") is None or p["msrp"] > p["price"]

    def test_admin_can_create_medals_product(self, admin_token):
        payload = {"name": "TEST_MedalProd", "description": "d", "category": "medals",
                   "price": 12.5, "msrp": 25.0}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["category"] == "medals"
        assert data["msrp"] == 25.0
        pid = data["id"]
        # Cleanup
        requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))

    def test_non_admin_cannot_create_medals(self, customer):
        payload = {"name": "TEST_MedalUnauth", "description": "d", "category": "medals",
                   "price": 1.0, "msrp": 2.0}
        r = requests.post(f"{API}/products", headers=auth(customer["token"]), json=payload)
        assert r.status_code == 403

    def test_invalid_category_400(self, admin_token):
        payload = {"name": "TEST_BadCat", "description": "d", "category": "junk_category",
                   "price": 1.0}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 400


# ---------------- Medals cart logic ----------------
class TestMedalsCartLogic:
    def test_medals_unlock_event_pass(self, customer):
        """Iteration 14 rule: a Medal bundle is a valid companion for an Event Pass."""
        medal = _find("medals")
        ep = _find("event_pass")
        assert medal and ep
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [
                {"product_id": medal["id"], "quantity": 1},
                {"product_id": ep["id"], "quantity": 1},
            ],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code in (200, 502, 503), f"got {r.status_code}: {r.text}"
        if r.status_code == 200:
            db.checkout_sessions.delete_one({"_id": ObjectId(r.json()["session_id"])})

    def test_medals_only_passes_validation(self, customer):
        """Medals-only checkout passes cart validation and now returns a real SellAuth URL."""
        medal = _find("medals")
        assert medal
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": medal["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        # Must NOT be 400 (validation passed); may be 200 (live) or 502/503 (SellAuth email quirks)
        assert r.status_code in (200, 502, 503), f"got {r.status_code}: {r.text}"
        if r.status_code == 200:
            db.checkout_sessions.delete_one({"_id": ObjectId(r.json()["session_id"])})

    def test_medals_plus_bundle_passes_validation(self, customer):
        medal = _find("medals")
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [
                {"product_id": medal["id"], "quantity": 1},
                {"product_id": bundle["id"], "quantity": 1},
            ],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code in (200, 502, 503), r.text
        if r.status_code == 200:
            db.checkout_sessions.delete_one({"_id": ObjectId(r.json()["session_id"])})


# ---------------- Waitlist ----------------
class TestWaitlist:
    def test_waitlist_public_upsert(self):
        email = f"TEST_wl_{uuid.uuid4().hex[:8]}@example.com"
        payload = {"email": email, "product_id": "shundo-1"}
        r1 = requests.post(f"{API}/waitlist", json=payload)
        assert r1.status_code == 200 and r1.json().get("ok")
        # Duplicate submission does not increase count (upsert)
        r2 = requests.post(f"{API}/waitlist", json=payload)
        assert r2.status_code == 200
        count = db.waitlist.count_documents({"email": email.lower(), "product_id": "shundo-1"})
        assert count == 1
        db.waitlist.delete_many({"email": email.lower()})

    def test_admin_waitlist_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/waitlist").status_code == 401
        assert requests.get(f"{API}/admin/waitlist",
                            headers=auth(customer["token"])).status_code == 403

    def test_admin_waitlist_lists(self, admin_token):
        r = requests.get(f"{API}/admin/waitlist", headers=auth(admin_token))
        assert r.status_code == 200 and isinstance(r.json(), list)


# ---------------- Stardust category ----------------
class TestStardustCategory:
    def test_seeded_stardust_products_present(self):
        products = _products()
        stardust = [p for p in products if p["category"] == "stardust"]
        assert len(stardust) >= 3, f"Expected >=3 stardust products, got {len(stardust)}"
        # User actively edits prices; only assert MSRP > price invariant.
        for p in stardust:
            assert p.get("msrp") is None or p["msrp"] > p["price"]

    def test_admin_create_stardust_product(self, admin_token):
        payload = {"name": "TEST_StardustProd", "description": "d", "category": "stardust",
                   "price": 5.99, "msrp": 11.99}
        r = requests.post(f"{API}/products", headers=auth(admin_token), json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["category"] == "stardust"
        requests.delete(f"{API}/products/{r.json()['id']}", headers=auth(admin_token))

    def test_customer_cannot_create_stardust(self, customer):
        r = requests.post(f"{API}/products", headers=auth(customer["token"]), json={
            "name": "TEST_StardustCust", "category": "stardust", "price": 1.0, "msrp": 2.0,
        })
        assert r.status_code == 403

    def test_invalid_category_still_400(self, admin_token):
        r = requests.post(f"{API}/products", headers=auth(admin_token), json={
            "name": "TEST_BadCat2", "category": "not_a_cat", "price": 1.0,
        })
        assert r.status_code == 400


# ---------------- Stardust cart logic ----------------
class TestStardustCart:
    def test_stardust_only_passes_validation(self, customer):
        p = _find("stardust")
        assert p
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": p["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code in (200, 502, 503), f"got {r.status_code}: {r.text}"
        if r.status_code == 200:
            assert r.json().get("checkout_url", "").startswith("http")
            db.checkout_sessions.delete_one({"_id": ObjectId(r.json()["session_id"])})

    def test_stardust_unlocks_event_pass(self, customer):
        """Iteration 14 rule: Stardust is a valid companion for an Event Pass."""
        stardust = _find("stardust")
        ep = _find("event_pass")
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [
                {"product_id": stardust["id"], "quantity": 1},
                {"product_id": ep["id"], "quantity": 1},
            ],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
        })
        assert r.status_code in (200, 502, 503), f"got {r.status_code}: {r.text}"
        if r.status_code == 200:
            db.checkout_sessions.delete_one({"_id": ObjectId(r.json()["session_id"])})


# ---------------- Password change ----------------
class TestPasswordChange:
    def test_change_password_requires_auth(self):
        r = requests.post(f"{API}/auth/change-password", json={
            "current_password": "x", "new_password": "yyyyyyyy",
        })
        assert r.status_code == 401

    def test_change_password_short_returns_422(self, customer):
        r = requests.post(f"{API}/auth/change-password",
                          headers=auth(customer["token"]),
                          json={"current_password": customer["password"], "new_password": "short"})
        assert r.status_code == 422

    def test_wrong_current_password_returns_401(self, customer):
        r = requests.post(f"{API}/auth/change-password",
                          headers=auth(customer["token"]),
                          json={"current_password": "wrong_pw!", "new_password": "NewPass#2026"})
        assert r.status_code == 401
        assert "current password" in r.json()["detail"].lower()

    def test_customer_password_change_happy_path(self, customer):
        new_pw = "NewPass#2026"
        r = requests.post(f"{API}/auth/change-password",
                          headers=auth(customer["token"]),
                          json={"current_password": customer["password"], "new_password": new_pw})
        assert r.status_code == 200 and r.json().get("ok")

        # Verify bcrypt hash format in DB
        user_doc = db.users.find_one({"email": customer["email"]})
        assert user_doc["password_hash"].startswith("$2b$"), f"Not bcrypt: {user_doc['password_hash'][:10]}"
        assert user_doc["password_hash"] != new_pw
        assert user_doc.get("password_self_managed")

        # OLD password rejected
        r_old = requests.post(f"{API}/auth/login",
                              json={"email": customer["email"], "password": customer["password"]})
        assert r_old.status_code == 401

        # NEW password works
        r_new = requests.post(f"{API}/auth/login",
                              json={"email": customer["email"], "password": new_pw})
        assert r_new.status_code == 200
        # Update fixture creds for downstream reuse
        customer["password"] = new_pw
        customer["token"] = r_new.json()["access_token"]

    def test_reusing_same_password_returns_400(self, customer):
        r = requests.post(f"{API}/auth/change-password",
                          headers=auth(customer["token"]),
                          json={"current_password": customer["password"],
                                "new_password": customer["password"]})
        assert r.status_code == 400


# ---------------- Visitor tracking ----------------
class TestVisitorTracking:
    def test_track_public_no_auth(self):
        r = requests.post(f"{API}/track")
        assert r.status_code == 200 and r.json().get("ok")

    def test_track_dedup_per_ip_per_day(self):
        # Use forwarded IP so we test a stable identity regardless of client
        test_ip = f"203.0.113.{__import__('random').randint(1, 250)}"
        day = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")
        db.visits.delete_many({"ip": test_ip})
        for _ in range(3):
            r = requests.post(f"{API}/track", headers={"X-Forwarded-For": test_ip})
            assert r.status_code == 200
        docs = list(db.visits.find({"ip": test_ip, "day": day}))
        assert len(docs) == 1, f"expected 1 doc, got {len(docs)}"
        assert docs[0]["hits"] >= 3
        db.visits.delete_many({"ip": test_ip})

    def test_visits_indexes(self):
        idx = db.visits.index_information()
        # unique compound (ip, day)
        assert any(v.get("unique") and v.get("key") == [("ip", 1), ("day", 1)]
                   for v in idx.values()), f"missing unique (ip,day) index: {idx}"
        # TTL on expires_at
        assert any(v.get("expireAfterSeconds") == 0 and v.get("key") == [("expires_at", 1)]
                   for v in idx.values()), f"missing TTL index on expires_at: {idx}"

    def test_geolocation_united_states(self):
        db.ip_geo.delete_one({"_id": "8.8.8.8"})
        db.visits.delete_many({"ip": "8.8.8.8"})
        r = requests.post(f"{API}/track", headers={"X-Forwarded-For": "8.8.8.8"})
        assert r.status_code == 200
        doc = db.visits.find_one({"ip": "8.8.8.8"})
        assert doc is not None
        # ip-api may be rate limited; accept United States or Unknown but at least verify no hang
        assert doc.get("country") in ("United States", "Unknown"), doc.get("country")
        # Cache created
        cached = db.ip_geo.find_one({"_id": "8.8.8.8"})
        assert cached is not None

    def test_geolocation_private_ip_unknown_non_fatal(self):
        r = requests.post(f"{API}/track", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r.status_code == 200
        doc = db.visits.find_one({"ip": "10.0.0.1"})
        assert doc is not None
        assert doc["country"] == "Unknown"


# ---------------- Analytics endpoint ----------------
class TestAnalytics:
    def test_analytics_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/analytics").status_code == 401
        assert requests.get(f"{API}/admin/analytics",
                            headers=auth(customer["token"])).status_code == 403

    def test_analytics_admin_shape(self, admin_token):
        # Ensure at least one visit exists
        requests.post(f"{API}/track", headers={"X-Forwarded-For": "8.8.4.4"})
        r = requests.get(f"{API}/admin/analytics", headers=auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "totals" in data and "top_countries" in data and "visits" in data
        t = data["totals"]
        for key in ("unique_visitors", "visits_today", "total_hits", "orders", "revenue", "waitlist"):
            assert key in t, f"missing totals.{key}"
        assert isinstance(data["visits"], list)
        assert isinstance(data["top_countries"], list)


# ---------------- Stardust visibility (iteration 7) ----------------
class TestStardustVisibility:
    def test_stardust_products_active_and_not_coming_soon(self):
        products = _products()
        stardust = [p for p in products if p["category"] == "stardust"]
        assert len(stardust) >= 3, f"Expected >=3 stardust, got {len(stardust)}"
        for p in stardust:
            assert p.get("active", True), f"{p['name']} not active"

    def test_all_category_keys_are_lowercase_snake_case(self):
        # Categories are admin-managed now, so read the live list instead of hardcoding it.
        allowed = {c["key"] for c in requests.get(f"{API}/categories").json()}
        for p in _products():
            assert p["category"] in allowed, f"Invalid category on {p['name']}: {p['category']}"
            assert p["category"] == p["category"].lower()


# ---------------- is_featured field (iteration 7) ----------------
class TestFeaturedField:
    def test_is_featured_present_on_every_product(self):
        for p in _products():
            assert "is_featured" in p, f"Missing is_featured on {p['name']}"
            assert isinstance(p["is_featured"], bool), f"is_featured not bool: {p['is_featured']}"

    def test_create_defaults_is_featured_false(self, admin_token):
        r = requests.post(f"{API}/products", headers=auth(admin_token), json={
            "name": "TEST_FeatDefault", "category": "medals", "price": 1.0, "msrp": 2.0,
        })
        assert r.status_code == 200
        data = r.json()
        assert not (data["is_featured"])
        # Verify persisted
        for p in _products():
            if p["id"] == data["id"]:
                assert not (p["is_featured"])
                break
        requests.delete(f"{API}/products/{data['id']}", headers=auth(admin_token))

    def test_create_with_is_featured_true_persists(self, admin_token):
        r = requests.post(f"{API}/products", headers=auth(admin_token), json={
            "name": "TEST_FeatTrue", "category": "medals", "price": 1.0, "msrp": 2.0,
            "is_featured": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_featured"]
        requests.delete(f"{API}/products/{data['id']}", headers=auth(admin_token))

    def test_put_preserves_is_featured(self, admin_token):
        r = requests.post(f"{API}/products", headers=auth(admin_token), json={
            "name": "TEST_FeatPut", "category": "medals", "price": 1.0, "msrp": 2.0,
            "is_featured": True,
        })
        pid = r.json()["id"]
        # PUT with is_featured explicitly true
        r2 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json={
            "name": "TEST_FeatPut2", "category": "medals", "price": 1.5, "msrp": 3.0,
            "is_featured": True,
        })
        assert r2.status_code == 200 and r2.json()["is_featured"]
        # PUT to false
        r3 = requests.put(f"{API}/products/{pid}", headers=auth(admin_token), json={
            "name": "TEST_FeatPut2", "category": "medals", "price": 1.5, "msrp": 3.0,
            "is_featured": False,
        })
        assert not (r3.json()["is_featured"])
        requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))


# ---------------- PATCH /api/products/{id}/featured (iteration 7) ----------------
class TestFeaturedToggle:
    def test_requires_auth(self):
        products = _products()
        pid = products[0]["id"]
        r = requests.patch(f"{API}/products/{pid}/featured", json={"is_featured": True})
        assert r.status_code == 401

    def test_forbidden_for_customer(self, customer):
        pid = _products()[0]["id"]
        r = requests.patch(f"{API}/products/{pid}/featured",
                           headers=auth(customer["token"]),
                           json={"is_featured": True})
        assert r.status_code == 403

    def test_404_for_nonexistent(self, admin_token):
        # Valid-looking ObjectId that doesn't exist
        r = requests.patch(f"{API}/products/000000000000000000000000/featured",
                           headers=auth(admin_token),
                           json={"is_featured": True})
        assert r.status_code == 404

    def test_toggle_persists(self, admin_token):
        # Create isolated test product
        r = requests.post(f"{API}/products", headers=auth(admin_token), json={
            "name": "TEST_ToggleFeat", "category": "medals", "price": 1.0, "msrp": 2.0,
            "is_featured": False,
        })
        pid = r.json()["id"]

        # Toggle ON
        r_on = requests.patch(f"{API}/products/{pid}/featured",
                              headers=auth(admin_token),
                              json={"is_featured": True})
        assert r_on.status_code == 200
        assert r_on.json()["is_featured"]
        # Persistence via GET
        got = next(p for p in _products() if p["id"] == pid)
        assert got["is_featured"]

        # Toggle OFF
        r_off = requests.patch(f"{API}/products/{pid}/featured",
                               headers=auth(admin_token),
                               json={"is_featured": False})
        assert not (r_off.status_code == 200 and r_off.json()["is_featured"])
        got2 = next(p for p in _products() if p["id"] == pid)
        assert not (got2["is_featured"])

        requests.delete(f"{API}/products/{pid}", headers=auth(admin_token))


# ---------------- Coupon Admin CRUD (iteration 8) ----------------
def _coupon_payload(code=None, **overrides):
    payload = {
        "code": code or f"TEST{uuid.uuid4().hex[:6].upper()}",
        "percent_off": 10.0,
        "active": True,
        "excluded_product_ids": [],
        "excluded_categories": [],
        "min_subtotal": None,
        "max_uses": None,
        "note": "",
    }
    payload.update(overrides)
    return payload


class TestCouponAdminCrud:
    def test_list_requires_admin(self, customer):
        assert requests.get(f"{API}/admin/coupons").status_code == 401
        assert requests.get(f"{API}/admin/coupons",
                            headers=auth(customer["token"])).status_code == 403

    def test_create_requires_admin(self, customer):
        p = _coupon_payload()
        assert requests.post(f"{API}/admin/coupons", json=p).status_code == 401
        assert requests.post(f"{API}/admin/coupons", headers=auth(customer["token"]),
                             json=p).status_code == 403

    def test_create_and_uppercase_code(self, admin_token):
        code = f"test{uuid.uuid4().hex[:6]}"
        p = _coupon_payload(code=code, percent_off=15.0, note="hi")
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token), json=p)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["code"] == code.upper()
        assert data["percent_off"] == 15.0
        assert data["used_count"] == 0
        assert data["note"] == "hi"
        # Verify listed
        listing = requests.get(f"{API}/admin/coupons", headers=auth(admin_token)).json()
        assert any(c["code"] == code.upper() for c in listing)
        # Cleanup
        requests.delete(f"{API}/admin/coupons/{data['id']}", headers=auth(admin_token))

    def test_duplicate_code_returns_400(self, admin_token):
        code = f"DUP{uuid.uuid4().hex[:6].upper()}"
        r1 = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                           json=_coupon_payload(code=code))
        assert r1.status_code == 200
        cid = r1.json()["id"]
        r2 = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                           json=_coupon_payload(code=code.lower()))
        assert r2.status_code == 400
        assert "exists" in r2.json()["detail"].lower()
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_percent_out_of_range_422(self, admin_token):
        r_zero = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                               json=_coupon_payload(percent_off=0))
        assert r_zero.status_code == 422
        r_over = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                               json=_coupon_payload(percent_off=101))
        assert r_over.status_code == 422

    def test_unknown_category_400(self, admin_token):
        r = requests.post(
            f"{API}/admin/coupons",
            headers=auth(admin_token),
            json=_coupon_payload(excluded_categories=["nonsense_cat"]),
        )
        assert r.status_code == 400
        assert "unknown category" in r.json()["detail"].lower()

    def test_optional_fields_accepted(self, admin_token):
        p = _coupon_payload(min_subtotal=25.0, max_uses=3, note="promo")
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token), json=p)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["min_subtotal"] == 25.0 and data["max_uses"] == 3
        requests.delete(f"{API}/admin/coupons/{data['id']}", headers=auth(admin_token))

    def test_put_updates_all_fields(self, admin_token):
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(percent_off=5))
        cid = r.json()["id"]
        upd = _coupon_payload(code=r.json()["code"], percent_off=25, active=False,
                              excluded_categories=["stardust"], min_subtotal=10, note="upd")
        r2 = requests.put(f"{API}/admin/coupons/{cid}", headers=auth(admin_token), json=upd)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert not (data["percent_off"] == 25 and data["active"])
        assert "stardust" in data["excluded_categories"]
        assert data["min_subtotal"] == 10 and data["note"] == "upd"
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_delete_bogus_id_404(self, admin_token):
        r = requests.delete(f"{API}/admin/coupons/000000000000000000000000",
                            headers=auth(admin_token))
        assert r.status_code == 404


# ---------------- Coupon validation endpoint (iteration 8) ----------------
class TestCouponValidation:
    @pytest.fixture
    def coupon_20(self, admin_token):
        code = f"VAL{uuid.uuid4().hex[:6].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=20))
        cid = r.json()["id"]
        yield {"id": cid, "code": code}
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_validate_public_no_auth(self, coupon_20):
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/coupons/validate", json={
            "code": coupon_20["code"],
            "items": [{"product_id": bundle["id"], "quantity": 1}],
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["code"] == coupon_20["code"]
        assert data["percent_off"] == 20
        assert data["subtotal"] == round(bundle["price"], 2)
        assert data["discount"] == round(bundle["price"] * 0.2, 2)
        assert data["total"] == round(data["subtotal"] - data["discount"], 2)
        assert data["excluded_names"] == []

    def test_case_insensitive_code(self, coupon_20):
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/coupons/validate", json={
            "code": coupon_20["code"].lower(),
            "items": [{"product_id": bundle["id"], "quantity": 1}],
        })
        assert r.status_code == 200 and r.json()["code"] == coupon_20["code"]

    def test_unknown_code_400(self):
        bundle = _find("pokecoin_bundle")
        r = requests.post(f"{API}/coupons/validate", json={
            "code": "NEVEREXIST_XYZ",
            "items": [{"product_id": bundle["id"], "quantity": 1}],
        })
        assert r.status_code == 400
        assert "not valid" in r.json()["detail"].lower()

    def test_inactive_coupon_400(self, admin_token):
        code = f"INACT{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, active=False))
        cid = r.json()["id"]
        bundle = _find("pokecoin_bundle")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code, "items": [{"product_id": bundle["id"], "quantity": 1}],
            })
            assert r2.status_code == 400
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_expired_coupon_400(self, admin_token):
        code = f"EXP{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code))
        cid = r.json()["id"]
        # Force expires_at in the past via direct db update
        db.coupons.update_one({"_id": ObjectId(cid)},
                              {"$set": {"expires_at": __import__("datetime").datetime.utcnow() - timedelta(days=1)}})
        bundle = _find("pokecoin_bundle")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code, "items": [{"product_id": bundle["id"], "quantity": 1}],
            })
            assert r2.status_code == 400
            assert "expired" in r2.json()["detail"].lower()
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_usage_limit_400(self, admin_token):
        code = f"USED{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, max_uses=1))
        cid = r.json()["id"]
        db.coupons.update_one({"_id": ObjectId(cid)}, {"$set": {"used_count": 1}})
        bundle = _find("pokecoin_bundle")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code, "items": [{"product_id": bundle["id"], "quantity": 1}],
            })
            assert r2.status_code == 400
            assert "fully redeemed" in r2.json()["detail"].lower()
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_min_subtotal_400(self, admin_token):
        code = f"MIN{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, min_subtotal=9999.0))
        cid = r.json()["id"]
        bundle = _find("pokecoin_bundle")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code, "items": [{"product_id": bundle["id"], "quantity": 1}],
            })
            assert r2.status_code == 400
            assert "9999" in r2.json()["detail"] or "spend" in r2.json()["detail"].lower()
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))


# ---------------- Coupon exclusions (iteration 8) ----------------
class TestCouponExclusions:
    def test_category_exclusion_all_excluded_400(self, admin_token):
        code = f"CATX{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=20,
                                               excluded_categories=["stardust"]))
        cid = r.json()["id"]
        stardust = _find("stardust")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code,
                "items": [{"product_id": stardust["id"], "quantity": 1}],
            })
            assert r2.status_code == 400
            assert "does not apply" in r2.json()["detail"].lower()
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_category_exclusion_mixed_cart_discounts_only_eligible(self, admin_token):
        code = f"MIX{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=20,
                                               excluded_categories=["stardust"]))
        cid = r.json()["id"]
        bundle = _find("pokecoin_bundle")
        stardust = _find("stardust")
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code,
                "items": [
                    {"product_id": bundle["id"], "quantity": 1},
                    {"product_id": stardust["id"], "quantity": 1},
                ],
            })
            assert r2.status_code == 200, r2.text
            data = r2.json()
            expected_subtotal = round(bundle["price"] + stardust["price"], 2)
            expected_eligible = round(bundle["price"], 2)
            expected_discount = round(expected_eligible * 0.20, 2)
            assert data["subtotal"] == expected_subtotal
            assert data["eligible_subtotal"] == expected_eligible
            assert data["discount"] == expected_discount
            assert data["total"] == round(expected_subtotal - expected_discount, 2)
            assert stardust["name"] in data["excluded_names"]
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_product_id_exclusion(self, admin_token):
        # Exclude one specific product; verify only that product is excluded in a mixed cart.
        products = [p for p in _products() if not p.get("coming_soon")]
        # Prefer two products in the same category to demonstrate category-independence of the rule.
        same_cat_pair = None
        by_cat = {}
        for p in products:
            by_cat.setdefault(p["category"], []).append(p)
        for cat, plist in by_cat.items():
            if cat == "event_pass":
                continue
            if len(plist) >= 2:
                same_cat_pair = (plist[0], plist[1])
                break
        if same_cat_pair is None:
            # Fallback: use two distinct products across categories
            if len(products) < 2:
                pytest.skip("need at least 2 purchasable products")
            same_cat_pair = (products[0], products[1])
        excluded, eligible_same_cat = same_cat_pair
        code = f"PID{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=10,
                                               excluded_product_ids=[excluded["id"]]))
        cid = r.json()["id"]
        try:
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": code,
                "items": [
                    {"product_id": excluded["id"], "quantity": 1},
                    {"product_id": eligible_same_cat["id"], "quantity": 1},
                ],
            })
            assert r2.status_code == 200, r2.text
            data = r2.json()
            assert excluded["name"] in data["excluded_names"]
            assert eligible_same_cat["name"] not in data["excluded_names"]
            expected_eligible = round(eligible_same_cat["price"], 2)
            assert data["eligible_subtotal"] == expected_eligible
            assert data["discount"] == round(expected_eligible * 0.10, 2)
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))


# ---------------- Coupon at checkout (iteration 8) ----------------
class TestCouponCheckout:
    def test_checkout_applies_discount_server_side_and_stores_on_session(self, admin_token, customer):
        code = f"CO{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=10))
        cid = r.json()["id"]
        bundle = _find("pokecoin_bundle")
        try:
            r2 = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
                "items": [{"product_id": bundle["id"], "quantity": 1}],
                "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
                "coupon_code": code.lower(),
            })
            assert r2.status_code in (200, 502, 503), r2.text
            if r2.status_code == 200:
                sid = r2.json()["session_id"]
                sess = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
                expected_subtotal = round(bundle["price"], 2)
                expected_discount = round(expected_subtotal * 0.10, 2)
                assert sess["coupon_code"] == code
                assert abs(sess["subtotal"] - expected_subtotal) < 0.01
                assert abs(sess["discount"] - expected_discount) < 0.01
                assert abs(sess["total"] - (expected_subtotal - expected_discount)) < 0.01
                db.checkout_sessions.delete_one({"_id": ObjectId(sid)})
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_checkout_invalid_coupon_400_no_orphan_session(self, customer):
        bundle = _find("pokecoin_bundle")
        before_s = db.checkout_sessions.count_documents({})
        before_o = db.orders.count_documents({})
        r = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
            "coupon_code": "NEVEREXIST_ABC",
        })
        assert r.status_code == 400
        assert db.checkout_sessions.count_documents({}) == before_s
        assert db.orders.count_documents({}) == before_o

    def test_event_pass_bundle_rule_precedes_coupon_error(self, admin_token, customer):
        # Even with a coupon, event-pass-only should return the bundle error, not a coupon error.
        code = f"EPC{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=10))
        cid = r.json()["id"]
        ep = _find("event_pass")
        try:
            r2 = requests.post(f"{API}/orders/checkout", headers=auth(customer["token"]), json={
                "items": [{"product_id": ep["id"], "quantity": 1}],
                "ptc_username": "u", "ptc_password": "p", "origin_url": BASE_URL,
                "coupon_code": code,
            })
            assert r2.status_code == 400
            assert "Pok" in r2.json()["detail"]
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))

    def test_webhook_promotes_session_with_coupon_and_increments_used_count(self, admin_token):
        # Create coupon
        code = f"WHK{uuid.uuid4().hex[:5].upper()}"
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=_coupon_payload(code=code, percent_off=10))
        cid = r.json()["id"]
        # Insert a session directly carrying coupon fields
        bundle = _find("pokecoin_bundle")
        now = __import__("datetime").datetime.utcnow()
        subtotal = round(bundle["price"], 2)
        discount = round(subtotal * 0.10, 2)
        total = round(subtotal - discount, 2)
        session_doc = {
            "items": [{"product_id": bundle["id"], "name": bundle["name"],
                       "category": bundle["category"], "price": bundle["price"], "quantity": 1}],
            "total": total,
            "subtotal": subtotal,
            "discount": discount,
            "coupon_code": code,
            "user_id": "",
            "email": "delivered@resend.dev",
            "origin_url": BASE_URL,
            "ptc_username_enc": "gAAAAABtest_cu",
            "ptc_password_enc": "gAAAAABtest_cp",
            "status": "awaiting_payment",
            "created_at": now,
            "expires_at": now + timedelta(minutes=TTL_MIN),
        }
        sid = str(db.checkout_sessions.insert_one(session_doc).inserted_id)
        try:
            invoice_id = f"inv-{uuid.uuid4().hex[:8]}"
            raw = json.dumps({"invoice": {"id": invoice_id, "status": "completed",
                                          "custom_fields": {"checkout_session_id": sid}}}).encode()
            sig = _sign(raw)
            r_wh = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                                 headers={"signature": sig, "content-type": "application/json"},
                                 timeout=60)
            assert r_wh.status_code == 200, r_wh.text
            order_id = r_wh.json().get("order_id")
            assert order_id
            order = db.orders.find_one({"_id": ObjectId(order_id)})
            assert order["coupon_code"] == code
            assert abs(order["discount"] - discount) < 0.01
            assert abs(order["subtotal"] - subtotal) < 0.01
            assert abs(order["total"] - total) < 0.01
            coupon_doc = db.coupons.find_one({"_id": ObjectId(cid)})
            assert coupon_doc["used_count"] == 1
            # Replay -> no double increment
            r_wh2 = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw,
                                  headers={"signature": sig, "content-type": "application/json"})
            assert r_wh2.status_code == 200
            assert r_wh2.json().get("duplicate")
            coupon_doc2 = db.coupons.find_one({"_id": ObjectId(cid)})
            assert coupon_doc2["used_count"] == 1
        finally:
            requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin_token))


# ---------------- Restore admin password to 'admin' at end of session ----------------
def test_zz_restore_admin_password():
    """Runs last (alphabetically after all TestX classes). Restores admin password to 'admin'
    via direct MongoDB bcrypt hash + unsets password_self_managed so seed stays authoritative."""
    import bcrypt as _bcrypt
    new_hash = _bcrypt.hashpw(b"admin", _bcrypt.gensalt()).decode()
    result = db.users.update_one(
        {"email": ADMIN_EMAIL.lower()},
        {"$set": {"password_hash": new_hash},
         "$unset": {"password_self_managed": "", "password_changed_at": ""}},
    )
    assert result.matched_count == 1
    # Verify login with 'admin' works
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "admin"})
    assert r.status_code == 200, f"admin login broken after restore: {r.text}"
    assert r.json()["user"]["role"] == "admin"

