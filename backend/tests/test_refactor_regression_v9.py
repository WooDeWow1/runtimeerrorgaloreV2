"""Iteration 17 regression sweep over the code-quality refactor (behaviour must be identical).

Covers the extracted helpers: price_cart / sellauth_cart (checkout), record_redemption /
send_order_confirmation / create_order_from_session, webhook_signature_ok / read_invoice /
find_session / invoice_is_paid (webhook), assert_coupon_fits / discount_amount (coupon engine),
unread_for_order / admin_unread / mark_order_read, and catalog_sync.plan's diff.

Nothing here pays a SellAuth invoice: paid promotion is simulated with a signed webhook.
"""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

from admin_creds import ADMIN_EMAIL, ADMIN_PASSWORD

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_fe = {}
with open("/app/frontend/.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.split("=", 1)
            _fe[k.strip()] = v.strip()
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
LOCAL_API = "http://localhost:8001/api"  # ingress strips the signature header

WEBHOOK_SECRET = os.environ["SELLAUTH_WEBHOOK_SECRET"]
TTL_MIN = int(os.environ.get("CHECKOUT_SESSION_TTL_MINUTES", "30"))
mongo = MongoClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]

TEST_EMAIL = "delivered@resend.dev"
CREDS = {"ptc_username": "qa_it17_user", "ptc_password": "qa_it17_pass"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sign(raw: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def post_webhook(body: dict, signature=True, secret_query=False):
    raw = json.dumps(body).encode()
    headers = {"content-type": "application/json"}
    if isinstance(signature, str):
        headers["signature"] = signature
    elif signature:
        headers["signature"] = sign(raw)
    url = f"{LOCAL_API}/webhooks/sellauth"
    if secret_query:
        url = f"{url}?secret={WEBHOOK_SECRET}"
    return requests.post(url, data=raw, headers=headers, timeout=90), raw


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def products():
    r = requests.get(f"{API}/products")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def bundle(products):
    """The $14.99 Pokécoin bundle used by the coupon spec."""
    for p in products:
        if p["category"] == "pokecoin_bundle" and abs(p["price"] - 14.99) < 0.01 and p["active"] \
                and not p.get("coming_soon") and not p["name"].startswith("TEST_"):
            return p
    pytest.fail("No active $14.99 pokecoin_bundle product found")


@pytest.fixture(scope="module")
def weekly(products):
    for p in products:
        if p["name"].startswith("Weekly Event Ticket") and p.get("variants"):
            return p
    pytest.fail("Weekly Event Ticket with variants not found")


@pytest.fixture(scope="module")
def cleanup():
    trash = {"sessions": [], "orders": [], "coupons": [], "messages": []}
    yield trash
    for sid in trash["sessions"]:
        db.checkout_sessions.delete_one({"_id": ObjectId(sid)})
    for oid_ in trash["orders"]:
        db.orders.delete_one({"_id": ObjectId(oid_)})
        db.messages.delete_many({"order_id": oid_})
        db.notifications.delete_many({"order_id": oid_})
    for code in trash["coupons"]:
        db.coupons.delete_many({"code": code})
        db.coupon_redemptions.delete_many({"code": code})


def make_session(items, cleanup, coupon_code=None, subtotal=None, discount=0.0, total=None,
                 email=TEST_EMAIL, user_id=""):
    now = datetime.now(timezone.utc)
    subtotal = subtotal if subtotal is not None else round(sum(i["price"] * i["quantity"] for i in items), 2)
    doc = {
        "items": items, "subtotal": subtotal, "discount": discount,
        "total": total if total is not None else subtotal,
        "coupon_code": coupon_code, "user_id": user_id, "email": email, "origin_url": BASE_URL,
        "ptc_username_enc": "gAAAAABqa_it17_user", "ptc_password_enc": "gAAAAABqa_it17_pass",
        "status": "awaiting_payment", "created_at": now,
        "expires_at": now + timedelta(minutes=TTL_MIN),
    }
    sid = str(db.checkout_sessions.insert_one(doc).inserted_id)
    cleanup["sessions"].append(sid)
    return sid


def line(product, qty=1, variant=None):
    return {
        "product_id": product["id"], "name": product["name"], "category": product["category"],
        "price": variant["price"] if variant else product["price"], "quantity": qty,
        "variant_label": variant["label"] if variant else "",
        "sellauth_product_id": product.get("sellauth_product_id"),
        "sellauth_variant_id": (variant or {}).get("sellauth_variant_id") or product.get("sellauth_variant_id"),
    }


# ---------------- coupon engine: assert_coupon_fits / discount_amount / compute_discount ----------------
class TestCouponEngine:
    def test_test20_mixed_cart_exact_maths(self, bundle, weekly):
        ultra = next(v for v in weekly["variants"] if v["label"] == "Ultra Box")
        r = requests.post(f"{API}/coupons/validate", json={
            "code": "TEST20", "email": TEST_EMAIL,
            "items": [{"product_id": bundle["id"], "quantity": 1},
                      {"product_id": weekly["id"], "quantity": 1,
                       "variant_id": ultra["sellauth_variant_id"]}],
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["subtotal"] == 20.98
        assert d["eligible_subtotal"] == 14.99
        assert d["discount"] == 3.00
        assert d["total"] == 17.98
        assert d["percent_label"] == "20%"
        assert d["excluded_names"] == ["Weekly Event Ticket"]
        assert d["code"] == "TEST20"
        assert "unit_prices" not in d

    def test_event_pass_only_cart_rejected(self, weekly):
        r = requests.post(f"{API}/coupons/validate", json={
            "code": "TEST20", "email": TEST_EMAIL,
            "items": [{"product_id": weekly["id"], "quantity": 1}],
        })
        assert r.status_code == 400
        assert "Event Pass" in r.json()["detail"]

    def test_empty_cart_and_unknown_code(self, bundle):
        r = requests.post(f"{API}/coupons/validate", json={"code": "TEST20", "items": [], "email": TEST_EMAIL})
        assert r.status_code == 400 and "empty" in r.json()["detail"].lower()
        r = requests.post(f"{API}/coupons/validate", json={
            "code": f"NOPE{uuid.uuid4().hex[:5]}", "email": TEST_EMAIL,
            "items": [{"product_id": bundle["id"], "quantity": 1}]})
        assert r.status_code == 400

    @pytest.mark.parametrize("patch,fragment", [
        ({"active": False}, "not valid"),
        ({"expires_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}, "expired"),
        ({"max_uses": 1}, "fully redeemed"),
        ({"min_subtotal": 999.0}, "at least"),
    ])
    def test_rejections(self, admin, bundle, cleanup, patch, fragment):
        code = f"QAIT17{uuid.uuid4().hex[:5].upper()}"
        cleanup["coupons"].append(code)
        payload = {"code": code, "discount_type": "percent", "percent_off": 10, **patch}
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin), json=payload)
        assert r.status_code == 200, r.text[:300]
        cid = r.json()["id"]
        if "max_uses" in patch:
            db.coupons.update_one({"_id": ObjectId(cid)}, {"$set": {"used_count": 1}})
        r = requests.post(f"{API}/coupons/validate", json={
            "code": code, "email": TEST_EMAIL,
            "items": [{"product_id": bundle["id"], "quantity": 1}]})
        assert r.status_code == 400, r.text[:300]
        assert fragment.lower() in r.json()["detail"].lower(), r.json()["detail"]
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin))

    def test_one_per_customer_rejected_after_redemption(self, admin, bundle, cleanup):
        code = f"QAOPC{uuid.uuid4().hex[:5].upper()}"
        cleanup["coupons"].append(code)
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin), json={
            "code": code, "discount_type": "percent", "percent_off": 10, "one_per_customer": True})
        assert r.status_code == 200
        cid = r.json()["id"]
        items = [{"product_id": bundle["id"], "quantity": 1}]
        ok = requests.post(f"{API}/coupons/validate", json={"code": code, "email": TEST_EMAIL, "items": items})
        assert ok.status_code == 200, ok.text[:200]
        db.coupon_redemptions.insert_one({"code": code, "email": TEST_EMAIL,
                                          "order_id": "qa", "redeemed_at": datetime.now(timezone.utc)})
        again = requests.post(f"{API}/coupons/validate", json={"code": code, "email": TEST_EMAIL, "items": items})
        assert again.status_code == 400
        assert "already used" in again.json()["detail"].lower()
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin))

    def test_fixed_amount_coupon_effective_percent_label(self, admin, bundle, cleanup):
        code = f"QAFIX{uuid.uuid4().hex[:5].upper()}"
        cleanup["coupons"].append(code)
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin), json={
            "code": code, "discount_type": "fixed", "amount_off": 5})
        assert r.status_code == 200, r.text[:300]
        cid = r.json()["id"]
        r = requests.post(f"{API}/coupons/validate", json={
            "code": code, "email": TEST_EMAIL,
            "items": [{"product_id": bundle["id"], "quantity": 1}]})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["discount_type"] == "fixed"
        assert d["discount"] == 5.00
        assert d["total"] == round(d["subtotal"] - 5.00, 2)
        assert d["percent_label"].endswith("%") and d["percent_label"] != "0%"
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin))


# ---------------- checkout: price_cart + sellauth_cart ----------------
class TestCheckout:
    def test_full_price_cart_returns_checkout_url(self, bundle, cleanup):
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "email": TEST_EMAIL, "origin_url": BASE_URL, **CREDS}, timeout=90)
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["checkout_url"].startswith("http")
        sid = body["session_id"]
        cleanup["sessions"].append(sid)
        doc = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert doc["subtotal"] == round(bundle["price"], 2)
        assert doc["discount"] == 0.0
        assert doc["total"] == round(bundle["price"], 2)
        assert doc["coupon_code"] is None
        assert doc["invoice_id"] and doc["status"] == "awaiting_payment"
        assert doc["items"][0]["sellauth_product_id"] == bundle.get("sellauth_product_id")

    def test_coupon_cart_records_discounted_total(self, bundle, weekly, cleanup):
        ultra = next(v for v in weekly["variants"] if v["label"] == "Ultra Box")
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1},
                      {"product_id": weekly["id"], "quantity": 1,
                       "variant_id": ultra["sellauth_variant_id"]}],
            "coupon_code": "test20", "email": TEST_EMAIL, "origin_url": BASE_URL, **CREDS}, timeout=90)
        assert r.status_code == 200, r.text[:400]
        sid = r.json()["session_id"]
        cleanup["sessions"].append(sid)
        doc = db.checkout_sessions.find_one({"_id": ObjectId(sid)})
        assert doc["subtotal"] == 20.98
        assert doc["discount"] == 3.00
        assert doc["total"] == 17.98
        assert doc["coupon_code"] == "TEST20"
        pass_line = next(i for i in doc["items"] if i["category"] == "event_pass")
        assert pass_line["variant_label"] == "Ultra Box"
        assert pass_line["sellauth_variant_id"] == ultra["sellauth_variant_id"]
        assert pass_line["price"] == 5.99

    def test_invalid_variant_400(self, weekly):
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": weekly["id"], "quantity": 1, "variant_id": 999}],
            "email": TEST_EMAIL, "origin_url": BASE_URL, **CREDS})
        assert r.status_code == 400
        assert "no longer available" in r.json()["detail"]

    def test_guest_without_email_400(self, bundle):
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "origin_url": BASE_URL, **CREDS})
        assert r.status_code == 400 and "email" in r.json()["detail"].lower()

    def test_bad_coupon_rejected_no_session(self, bundle):
        before = db.checkout_sessions.count_documents({})
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": bundle["id"], "quantity": 1}],
            "coupon_code": f"NOPE{uuid.uuid4().hex[:5]}",
            "email": TEST_EMAIL, "origin_url": BASE_URL, **CREDS})
        assert r.status_code == 400
        assert db.checkout_sessions.count_documents({}) == before


# ---------------- webhook: signature / read_invoice / find_session / invoice_is_paid ----------------
class TestWebhook:
    def test_bad_signature_401(self):
        r, _ = post_webhook({"invoice": {"id": "x", "status": "completed"}}, signature="0" * 64)
        assert r.status_code == 401

    def test_secret_query_fallback_accepted(self):
        r, _ = post_webhook({"invoice": {"id": f"qa-unknown-{uuid.uuid4().hex[:6]}", "status": "completed"}},
                            signature=False, secret_query=True)
        assert r.status_code == 200, r.text[:200]
        assert not (r.json().get("matched"))

    def test_unknown_invoice_matched_false(self):
        r, _ = post_webhook({"invoice": {"id": f"qa-unknown-{uuid.uuid4().hex[:6]}", "status": "completed",
                                         "custom_fields": {"checkout_session_id": "000000000000000000000000"}}})
        assert r.status_code == 200
        assert not (r.json().get("matched"))

    def test_unpaid_invoice_paid_false(self, bundle, cleanup):
        sid = make_session([line(bundle)], cleanup)
        r, _ = post_webhook({"invoice": {"id": f"qa-unpaid-{uuid.uuid4().hex[:6]}", "status": "pending",
                                         "custom_fields": {"checkout_session_id": sid}}})
        assert r.status_code == 200
        assert not (r.json().get("paid"))
        assert db.checkout_sessions.find_one({"_id": ObjectId(sid)})["status"] == "awaiting_payment"

    def test_paid_promotes_with_coupon_redemption_and_replay_guard(self, admin, bundle, weekly, cleanup):
        code = f"QAWHK{uuid.uuid4().hex[:5].upper()}"
        cleanup["coupons"].append(code)
        cr = requests.post(f"{API}/admin/coupons", headers=auth(admin), json={
            "code": code, "discount_type": "percent", "percent_off": 20})
        assert cr.status_code == 200, cr.text[:300]
        cid = cr.json()["id"]
        ultra = next(v for v in weekly["variants"] if v["label"] == "Ultra Box")
        items = [line(bundle), line(weekly, variant=ultra)]
        sid = make_session(items, cleanup, coupon_code=code, subtotal=20.98, discount=3.00, total=17.98)

        invoice_id = f"qa-paid-{uuid.uuid4().hex[:8]}"
        body = {"invoice": {"id": invoice_id, "status": "completed",
                            "custom_fields": {"checkout_session_id": sid}}}
        r, _ = post_webhook(body)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("paid")
        order_id = data["order_id"]
        cleanup["orders"].append(order_id)

        order = db.orders.find_one({"_id": ObjectId(order_id)})
        assert order["payment_status"] == "paid" and order["status"] == "pending"
        assert order["coupon_code"] == code
        assert order["subtotal"] == 20.98 and order["discount"] == 3.00 and order["total"] == 17.98
        assert order["session_id"] == sid
        pass_line = next(i for i in order["items"] if i["category"] == "event_pass")
        assert pass_line["variant_label"] == "Ultra Box"

        assert db.coupons.find_one({"_id": ObjectId(cid)})["used_count"] == 1
        red = db.coupon_redemptions.find_one({"code": code, "email": TEST_EMAIL})
        assert red and red["order_id"] == order_id

        # replay -> duplicate, no second order and no double increment
        r2, _ = post_webhook(body)
        assert r2.status_code == 200 and r2.json().get("duplicate")
        assert db.orders.count_documents({"session_id": sid}) == 1
        assert db.coupons.find_one({"_id": ObjectId(cid)})["used_count"] == 1
        requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(admin))

        # order is visible to the buyer's tracking route and to admin
        pub = requests.get(f"{API}/orders/{order_id}")
        assert pub.status_code == 200
        assert pub.json()["items"][1]["variant_label"] == "Ultra Box"
        assert "_id" not in pub.json()


# ---------------- unread alerts: unread_for_order / admin_unread / mark_order_read ----------------
class TestUnreadAlerts:
    @pytest.fixture(scope="class")
    def paid_order(self, bundle, cleanup):
        sid = make_session([line(bundle)], cleanup)
        r, _ = post_webhook({"invoice": {"id": f"qa-unread-{uuid.uuid4().hex[:8]}", "status": "completed",
                                         "custom_fields": {"checkout_session_id": sid}}})
        assert r.status_code == 200 and r.json().get("paid"), r.text[:300]
        order_id = r.json()["order_id"]
        cleanup["orders"].append(order_id)
        return order_id

    def test_admin_unread_requires_admin(self):
        assert requests.get(f"{API}/admin/unread").status_code in (401, 403)

    def test_customer_message_raises_unread_count(self, admin, paid_order):
        requests.post(f"{API}/admin/orders/{paid_order}/read", headers=auth(admin))
        before = requests.get(f"{API}/admin/unread", headers=auth(admin)).json()
        r = requests.post(f"{API}/orders/{paid_order}/messages",
                          json={"body": "QA_IT17 customer ping"}, timeout=60)
        assert r.status_code == 200, r.text[:300]

        orders = requests.get(f"{API}/admin/orders", headers=auth(admin)).json()
        mine = next(o for o in orders if o["id"] == paid_order)
        assert mine["unread_count"] == 1, mine

        after = requests.get(f"{API}/admin/unread", headers=auth(admin)).json()
        assert set(after) == {"orders", "messages"}
        assert after["orders"] == before["orders"] + 1
        assert after["messages"] == before["messages"] + 1

    def test_mark_read_zeroes_that_order(self, admin, paid_order):
        r = requests.post(f"{API}/admin/orders/{paid_order}/read", headers=auth(admin))
        assert r.status_code == 200 and r.json()["ok"]
        orders = requests.get(f"{API}/admin/orders", headers=auth(admin)).json()
        mine = next(o for o in orders if o["id"] == paid_order)
        assert mine["unread_count"] == 0

    def test_admin_reply_marks_read(self, admin, paid_order):
        requests.post(f"{API}/orders/{paid_order}/messages", json={"body": "QA_IT17 second ping"}, timeout=60)
        orders = requests.get(f"{API}/admin/orders", headers=auth(admin)).json()
        assert next(o for o in orders if o["id"] == paid_order)["unread_count"] == 1
        r = requests.post(f"{API}/orders/{paid_order}/messages", headers=auth(admin),
                          json={"body": "QA_IT17 admin reply"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        orders = requests.get(f"{API}/admin/orders", headers=auth(admin)).json()
        assert next(o for o in orders if o["id"] == paid_order)["unread_count"] == 0


# ---------------- catalog_sync.plan diff ----------------
class TestCatalogSyncDiff:
    def test_diff_shape(self, admin):
        r = requests.get(f"{API}/admin/sync/catalog", headers=auth(admin), timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for key in ("target", "source_count", "target_count", "creates", "updates"):
            assert key in d, d
        assert isinstance(d["creates"], list) and isinstance(d["updates"], list)
        assert isinstance(d["source_count"], int) and d["source_count"] > 0

    def test_diff_requires_admin(self):
        assert requests.get(f"{API}/admin/sync/catalog").status_code in (401, 403)
