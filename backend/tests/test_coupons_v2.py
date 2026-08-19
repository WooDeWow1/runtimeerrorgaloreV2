"""Iteration 10 backend tests — fixed-amount coupons, one-per-customer limit,
admin waitlist view, favicon. Self-contained (no conftest in repo)."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "officialwifi@icloud.com")
ADMIN_PASSWORD = "admin"

mongo = MongoClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def products():
    r = requests.get(f"{API}/products")
    assert r.status_code == 200
    return r.json()


def pick(products, category):
    for p in products:
        if p["category"] == category and not p.get("coming_soon"):
            return p
    return None


def cheapest(products, category=None):
    pool = [p for p in products if not p.get("coming_soon")
            and (category is None or p["category"] == category)]
    return sorted(pool, key=lambda p: p["price"])[0]


def payload(code=None, **over):
    body = {
        "code": code or f"TESTQA{uuid.uuid4().hex[:6].upper()}",
        "discount_type": "percent",
        "percent_off": 10.0,
        "amount_off": None,
        "one_per_customer": False,
        "active": True,
        "excluded_product_ids": [],
        "excluded_categories": [],
        "note": "iteration10",
    }
    body.update(over)
    return body


def create_coupon(token, **over):
    r = requests.post(f"{API}/admin/coupons", headers=auth(token), json=payload(**over))
    assert r.status_code == 200, f"create coupon failed: {r.status_code} {r.text}"
    return r.json()


def delete_coupon(token, cid):
    requests.delete(f"{API}/admin/coupons/{cid}", headers=auth(token))


# ---------------- Fixed amount coupon: admin CRUD + validation ----------------
class TestFixedCouponAdmin:
    def test_create_fixed_coupon(self, admin_token):
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=10.0)
        try:
            assert c["discount_type"] == "fixed"
            assert c["amount_off"] == 10.0
            assert c["percent_off"] is None
            assert c["used_count"] == 0
            listing = requests.get(f"{API}/admin/coupons", headers=auth(admin_token)).json()
            row = next(x for x in listing if x["code"] == c["code"])
            assert row["discount_type"] == "fixed" and row["amount_off"] == 10.0
        finally:
            delete_coupon(admin_token, c["id"])

    def test_percent_coupon_still_works(self, admin_token):
        c = create_coupon(admin_token, percent_off=15.0)
        try:
            assert c["discount_type"] == "percent"
            assert c["percent_off"] == 15.0
            assert c["amount_off"] is None
        finally:
            delete_coupon(admin_token, c["id"])

    def test_fixed_without_amount_400(self, admin_token):
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=payload(discount_type="fixed", percent_off=None, amount_off=None))
        assert r.status_code == 400, r.text
        assert "dollar" in r.json()["detail"].lower()

    def test_percent_without_percent_400(self, admin_token):
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=payload(discount_type="percent", percent_off=None))
        assert r.status_code == 400, r.text
        assert "percent" in r.json()["detail"].lower()

    def test_negative_amount_422(self, admin_token):
        r = requests.post(f"{API}/admin/coupons", headers=auth(admin_token),
                          json=payload(discount_type="fixed", percent_off=None, amount_off=-5))
        assert r.status_code == 422, r.text

    def test_update_percent_to_fixed(self, admin_token):
        c = create_coupon(admin_token, percent_off=10.0)
        try:
            upd = payload(code=c["code"], discount_type="fixed", percent_off=None, amount_off=7.5)
            r = requests.put(f"{API}/admin/coupons/{c['id']}", headers=auth(admin_token), json=upd)
            assert r.status_code == 200, r.text
            assert r.json()["discount_type"] == "fixed" and r.json()["amount_off"] == 7.5
            # persistence check
            listing = requests.get(f"{API}/admin/coupons", headers=auth(admin_token)).json()
            row = next(x for x in listing if x["code"] == c["code"])
            assert row["discount_type"] == "fixed" and row["amount_off"] == 7.5
        finally:
            delete_coupon(admin_token, c["id"])


class TestFixedCouponValidate:
    def test_fixed_discount_equals_amount(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        # amount small enough to be below the bundle price
        amount = 2.0
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=amount)
        try:
            r = requests.post(f"{API}/coupons/validate", json={
                "code": c["code"], "items": [{"product_id": bundle["id"], "quantity": 1}]})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["discount_type"] == "fixed"
            assert d["amount_off"] == amount
            assert d["discount"] == amount
            assert d["discount_label"] == f"${amount:.2f} off"
            assert d["total"] == round(d["subtotal"] - amount, 2)
        finally:
            delete_coupon(admin_token, c["id"])

    def test_fixed_capped_at_subtotal_never_negative(self, admin_token, products):
        cheap = cheapest(products)
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=50.0)
        try:
            r = requests.post(f"{API}/coupons/validate", json={
                "code": c["code"], "items": [{"product_id": cheap["id"], "quantity": 1}]})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["subtotal"] == round(cheap["price"], 2)
            assert d["discount"] == d["subtotal"], f"discount {d['discount']} should cap at subtotal"
            assert d["total"] == 0.0
            assert d["total"] >= 0
            # label still shows the face value of the coupon
            assert d["discount_label"] == "$50.00 off"
        finally:
            delete_coupon(admin_token, c["id"])

    def test_fixed_respects_excluded_category(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        dust = pick(products, "stardust")
        if not dust:
            pytest.skip("no stardust product available")
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=500.0,
                          excluded_categories=["stardust"])
        try:
            r = requests.post(f"{API}/coupons/validate", json={"code": c["code"], "items": [
                {"product_id": bundle["id"], "quantity": 1},
                {"product_id": dust["id"], "quantity": 1}]})
            assert r.status_code == 200, r.text
            d = r.json()
            expected_subtotal = round(bundle["price"] + dust["price"], 2)
            assert d["subtotal"] == expected_subtotal
            assert d["eligible_subtotal"] == round(bundle["price"], 2)
            # huge fixed amount must cap at eligible subtotal only
            assert d["discount"] == round(bundle["price"], 2)
            assert d["total"] == round(dust["price"], 2)
            assert dust["name"] in d["excluded_items"]
        finally:
            delete_coupon(admin_token, c["id"])

    def test_fixed_respects_excluded_product(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        other = next(p for p in products
                     if p["id"] != bundle["id"] and not p.get("coming_soon"))
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=1.0,
                          excluded_product_ids=[other["id"]])
        try:
            r = requests.post(f"{API}/coupons/validate", json={"code": c["code"], "items": [
                {"product_id": bundle["id"], "quantity": 1},
                {"product_id": other["id"], "quantity": 1}]})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["eligible_subtotal"] == round(bundle["price"], 2)
            assert other["name"] in d["excluded_items"]
            assert d["discount"] == 1.0
        finally:
            delete_coupon(admin_token, c["id"])

    def test_all_items_excluded_400(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=5.0,
                          excluded_product_ids=[bundle["id"]])
        try:
            r = requests.post(f"{API}/coupons/validate", json={
                "code": c["code"], "items": [{"product_id": bundle["id"], "quantity": 1}]})
            assert r.status_code == 400, r.text
            assert "does not apply" in r.json()["detail"].lower()
        finally:
            delete_coupon(admin_token, c["id"])


class TestFullDiscountCheckout:
    def test_fixed_coupon_covering_whole_cart_checkout(self, admin_token, products):
        """DEFECT: when a fixed coupon >= subtotal the cart is charged $0.00; SellAuth
        rejects it with 422 ('cart total must be greater than 0') and the API surfaces a
        raw 502 while the UI still shows 'PAY $0.00'."""
        bundle = pick(products, "pokecoin_bundle")
        email = "delivered@resend.dev"
        c = create_coupon(admin_token, discount_type="fixed", percent_off=None, amount_off=500.0)
        try:
            r = requests.post(f"{API}/orders/checkout", json={
                "items": [{"product_id": bundle["id"], "quantity": 1}],
                "ptc_username": "TESTQAu", "ptc_password": "TESTQAp",
                "origin_url": BASE_URL, "email": email, "coupon_code": c["code"]})
            print(f"100%-off checkout -> {r.status_code}: {r.text[:200]}")
            if r.status_code == 200:
                db.checkout_sessions.delete_one(
                    {"_id": __import__("bson").ObjectId(r.json()["session_id"])})
            assert r.status_code < 500, (
                "checkout with a full-cart fixed discount should be handled with a friendly "
                f"4xx (minimum charge), got {r.status_code}: {r.text[:200]}")
        finally:
            db.checkout_sessions.delete_many({"email": email, "coupon_code": c["code"]})
            delete_coupon(admin_token, c["id"])


# ---------------- One per customer ----------------
class TestOnePerCustomer:
    def test_blocks_redeemed_email_allows_other(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        used_email = f"testqa_used_{uuid.uuid4().hex[:6]}@example.com"
        fresh_email = f"testqa_fresh_{uuid.uuid4().hex[:6]}@example.com"
        c = create_coupon(admin_token, one_per_customer=True, percent_off=10.0)
        try:
            assert c["one_per_customer"] is True
            items = [{"product_id": bundle["id"], "quantity": 1}]

            # Before any redemption both emails validate fine
            r0 = requests.post(f"{API}/coupons/validate",
                               json={"code": c["code"], "items": items, "email": used_email})
            assert r0.status_code == 200, r0.text
            assert r0.json()["one_per_customer"] is True

            db.coupon_redemptions.update_one(
                {"code": c["code"], "email": used_email},
                {"$set": {"order_id": "TESTQA", "redeemed_at": datetime.now(timezone.utc)}},
                upsert=True)

            r1 = requests.post(f"{API}/coupons/validate",
                               json={"code": c["code"], "items": items, "email": used_email})
            assert r1.status_code == 400, r1.text
            assert "already used" in r1.json()["detail"].lower()

            # Case-insensitive check
            r1b = requests.post(f"{API}/coupons/validate",
                                json={"code": c["code"], "items": items,
                                      "email": used_email.upper()})
            assert r1b.status_code == 400, f"uppercase email should also be blocked: {r1b.text}"

            r2 = requests.post(f"{API}/coupons/validate",
                               json={"code": c["code"], "items": items, "email": fresh_email})
            assert r2.status_code == 200, r2.text
            assert r2.json()["discount"] > 0
        finally:
            db.coupon_redemptions.delete_many({"code": c["code"]})
            delete_coupon(admin_token, c["id"])

    def test_no_email_still_validates(self, admin_token, products):
        """Checkout page may validate before an email is typed — must not hard-fail."""
        bundle = pick(products, "pokecoin_bundle")
        c = create_coupon(admin_token, one_per_customer=True, percent_off=10.0)
        try:
            r = requests.post(f"{API}/coupons/validate", json={
                "code": c["code"], "items": [{"product_id": bundle["id"], "quantity": 1}]})
            assert r.status_code == 200, r.text
        finally:
            delete_coupon(admin_token, c["id"])

    def test_checkout_blocks_redeemed_email(self, admin_token, products):
        bundle = pick(products, "pokecoin_bundle")
        used_email = f"testqa_co_{uuid.uuid4().hex[:6]}@example.com"
        c = create_coupon(admin_token, one_per_customer=True, percent_off=10.0)
        try:
            db.coupon_redemptions.update_one(
                {"code": c["code"], "email": used_email},
                {"$set": {"order_id": "TESTQA", "redeemed_at": datetime.now(timezone.utc)}},
                upsert=True)
            r = requests.post(f"{API}/orders/checkout", json={
                "items": [{"product_id": bundle["id"], "quantity": 1}],
                "ptc_username": "TESTQAuser", "ptc_password": "TESTQApass",
                "origin_url": BASE_URL, "email": used_email, "coupon_code": c["code"]})
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
            assert "already used" in r.json()["detail"].lower()
            # no session should have been created
            assert db.checkout_sessions.count_documents({"email": used_email}) == 0
        finally:
            db.coupon_redemptions.delete_many({"code": c["code"]})
            db.checkout_sessions.delete_many({"email": used_email})
            delete_coupon(admin_token, c["id"])

    def test_redemption_recorded_via_paid_webhook(self, admin_token, products):
        """Simulate a paid SellAuth webhook and verify coupon_redemptions + used_count."""
        import hashlib
        import hmac
        import json as _json

        from bson import ObjectId

        secret = os.environ["SELLAUTH_WEBHOOK_SECRET"].encode()
        bundle = pick(products, "pokecoin_bundle")
        email = "delivered@resend.dev"
        c = create_coupon(admin_token, one_per_customer=True, percent_off=10.0)
        session_id = None
        order_id = None
        try:
            now = datetime.utcnow()
            res = db.checkout_sessions.insert_one({
                "items": [{"product_id": bundle["id"], "name": bundle["name"],
                           "category": bundle["category"], "price": bundle["price"],
                           "quantity": 1}],
                "total": round(bundle["price"] * 0.9, 2),
                "subtotal": bundle["price"],
                "discount": round(bundle["price"] * 0.1, 2),
                "coupon_code": c["code"],
                "user_id": "", "email": email, "origin_url": BASE_URL,
                "ptc_username_enc": "gAAAAABtest", "ptc_password_enc": "gAAAAABtest",
                "status": "awaiting_payment", "created_at": now,
                "expires_at": now + timedelta(minutes=30),
            })
            session_id = res.inserted_id
            raw = _json.dumps({"invoice": {"id": f"inv-{uuid.uuid4().hex[:8]}",
                                           "status": "completed",
                                           "custom_fields": {
                                               "checkout_session_id": str(session_id)}}}).encode()
            sig = hmac.new(secret, raw, hashlib.sha256).hexdigest()
            r = requests.post("http://localhost:8001/api/webhooks/sellauth", data=raw,
                              headers={"signature": sig, "content-type": "application/json"},
                              timeout=90)
            assert r.status_code == 200, r.text
            sess = db.checkout_sessions.find_one({"_id": session_id})
            order_id = sess.get("order_id")
            assert order_id, f"order not created from paid session: {sess.get('status')}"

            red = db.coupon_redemptions.find_one({"code": c["code"], "email": email})
            assert red is not None, "coupon_redemptions row not written on order creation"
            assert red["order_id"] == order_id
            assert db.coupons.find_one({"code": c["code"]})["used_count"] == 1

            # And the same email is now blocked from reusing the code
            r2 = requests.post(f"{API}/coupons/validate", json={
                "code": c["code"], "email": email,
                "items": [{"product_id": bundle["id"], "quantity": 1}]})
            assert r2.status_code == 400, r2.text
        finally:
            db.coupon_redemptions.delete_many({"code": c["code"]})
            if order_id:
                db.orders.delete_one({"_id": ObjectId(order_id)})
            if session_id:
                db.checkout_sessions.delete_one({"_id": session_id})
            delete_coupon(admin_token, c["id"])


# ---------------- Admin waitlist ----------------
class TestAdminWaitlist:
    def test_requires_admin(self):
        assert requests.get(f"{API}/admin/waitlist").status_code == 401

    def test_lists_signups(self, admin_token, products):
        shundo = pick(products, "shundo_service") or products[0]
        email = f"testqa_wl_{uuid.uuid4().hex[:6]}@example.com"
        try:
            r = requests.post(f"{API}/waitlist", json={"email": email,
                                                       "product_id": shundo["id"],
                                                       "note": "TESTQA"})
            assert r.status_code == 200, r.text
            rows = requests.get(f"{API}/admin/waitlist", headers=auth(admin_token))
            assert rows.status_code == 200, rows.text
            data = rows.json()
            assert isinstance(data, list)
            row = next((x for x in data if x["email"] == email), None)
            assert row is not None, "new signup missing from admin waitlist"
            assert row["product_id"] == shundo["id"]
            assert row["created_at"]
            assert "_id" not in row
        finally:
            db.waitlist.delete_many({"email": email})

    def test_duplicate_signup_is_upsert(self, admin_token, products):
        shundo = pick(products, "shundo_service") or products[0]
        email = f"testqa_wl2_{uuid.uuid4().hex[:6]}@example.com"
        try:
            for _ in range(2):
                requests.post(f"{API}/waitlist",
                              json={"email": email, "product_id": shundo["id"]})
            assert db.waitlist.count_documents({"email": email}) == 1
        finally:
            db.waitlist.delete_many({"email": email})


# ---------------- Favicon ----------------
class TestFavicon:
    def test_favicon_png_200(self):
        r = requests.get(f"{BASE_URL}/favicon.png")
        assert r.status_code == 200, r.status_code
        assert r.headers.get("content-type", "").startswith("image/"), r.headers.get("content-type")
        assert len(r.content) > 100

    def test_index_references_favicon(self):
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        assert "favicon.png" in r.text, "index.html does not reference favicon.png"
