"""Iteration 18 — reworked review-reward coupon flow.

Coupons are only issued on admin APPROVAL (never on submit). Declining is a hard delete and
permanently marks the order review_declined. Auto coupons survive redemption (row kept 30 days).
Single-use, one-per-customer, issued_to-locked. /api/reviews/status must return the correct
per-order shape for the My Orders page.
"""
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")
ADMIN_EMAIL = backend_env.get("ADMIN_EMAIL")
ADMIN_PASSWORD = backend_env.get("ADMIN_PASSWORD")


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def real_product_id():
    r = requests.get(f"{API}/products")
    r.raise_for_status()
    # pick a non-event_pass product
    for p in r.json():
        if p.get("category") != "event_pass" and p.get("active", True):
            return p["id"]
    pytest.skip("no eligible product for validate test")


@pytest.fixture(scope="session")
def review_settings(admin):
    # Ensure feature enabled with predictable percent/expiry
    admin.put(f"{API}/admin/settings/reviews",
              json={"enabled": True, "percent_off": 5, "expiry_days": 30})
    yield


def _mk_order(mongo, email, marker):
    doc = {
        "user_id": "",
        "user_email": email,
        "origin_url": "https://preview.example",
        "items": [{
            "product_id": "TEST_PROD",
            "name": f"TEST review-flow item {marker}",
            "category": "medals",
            "price": 10.0,
            "quantity": 1,
            "variant_label": "",
        }],
        "total": 10.0,
        "subtotal": 10.0,
        "discount": 0.0,
        "coupon_code": None,
        "status": "completed",
        "payment_status": "paid",
        "session_id": f"TEST_SESSION_{marker}",
        "ptc_username_enc": "x",
        "ptc_password_enc": "x",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    return str(mongo.orders.insert_one(doc).inserted_id)


@pytest.fixture()
def order_a(mongo):
    marker = f"REVQA_A_{secrets.token_hex(3)}"
    email = f"reviewqa+{marker.lower()}@delivered.resend.dev"
    oid = _mk_order(mongo, email, marker)
    yield {"id": oid, "email": email}
    mongo.orders.delete_one({"_id": ObjectId(oid)})
    mongo.reviews.delete_many({"order_id": oid})


@pytest.fixture()
def order_b(mongo):
    marker = f"REVQA_B_{secrets.token_hex(3)}"
    email = f"reviewqa+{marker.lower()}@delivered.resend.dev"
    oid = _mk_order(mongo, email, marker)
    yield {"id": oid, "email": email}
    mongo.orders.delete_one({"_id": ObjectId(oid)})
    mongo.reviews.delete_many({"order_id": oid})


@pytest.fixture()
def order_c(mongo):
    marker = f"REVQA_C_{secrets.token_hex(3)}"
    email = f"reviewqa+{marker.lower()}@delivered.resend.dev"
    oid = _mk_order(mongo, email, marker)
    yield {"id": oid, "email": email}
    mongo.orders.delete_one({"_id": ObjectId(oid)})
    mongo.reviews.delete_many({"order_id": oid})


def _submit_review(oid, rating=5, title="Great", body=None):
    if body is None:
        body = "This is a QA seeded review body which is easily over 150 chars long. " * 3
    return requests.post(f"{API}/reviews", json={
        "order_id": oid, "rating": rating, "title": title, "body": body,
        "turnstile_token": "preview-bypass",
    }, headers={"Content-Type": "application/json"})


def _cleanup_coupon(mongo, code):
    if code:
        mongo.coupons.delete_many({"code": code})
        mongo.coupon_redemptions.delete_many({"code": code})


# ---------------- Submit does NOT create a coupon ----------------
class TestSubmitNoCoupon:
    def test_submit_returns_null_coupon_and_pending_status(self, order_a, mongo, review_settings):
        before = mongo.coupons.count_documents({"source": "auto"})
        r = _submit_review(order_a["id"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["coupon"] is None
        assert "review_id" in body
        after = mongo.coupons.count_documents({"source": "auto"})
        assert after == before, "submit must not create an auto coupon"

        # /reviews/status shows pending
        st = requests.get(f"{API}/reviews/status", params={"order_ids": order_a["id"]}).json()
        assert st[order_a["id"]]["status"] == "pending"
        assert "coupon" not in st[order_a["id"]] or st[order_a["id"]].get("coupon") is None


# ---------------- Approve issues exactly ONE coupon ----------------
class TestApproveIssuesCoupon:
    def test_approve_creates_single_coupon_and_links_it(self, admin, order_a, mongo, review_settings):
        _submit_review(order_a["id"])
        rid = admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
        rid = next(x["id"] for x in rid if x["order_id"] == order_a["id"])

        before = mongo.coupons.count_documents({"source": "auto", "issued_to": order_a["email"]})
        r = admin.post(f"{API}/admin/reviews/{rid}/approve")
        assert r.status_code == 200, r.text
        coupon = r.json()["coupon"]
        assert coupon and coupon["code"].startswith("THANKS")
        assert coupon["percent_off"] == 5

        after = mongo.coupons.count_documents({"source": "auto", "issued_to": order_a["email"]})
        assert after - before == 1

        doc = mongo.coupons.find_one({"code": coupon["code"]})
        assert doc["source"] == "auto"
        assert doc["max_uses"] == 1
        assert doc["one_per_customer"] is True
        assert doc["issued_to"].lower() == order_a["email"].lower()
        assert doc["review_id"] == rid

        review = mongo.reviews.find_one({"_id": ObjectId(rid)})
        assert review["status"] == "approved"
        assert review["coupon_code"] == coupon["code"]
        assert review.get("approved_at")

        # /reviews/status now shows approved + unredeemed coupon
        st = requests.get(f"{API}/reviews/status", params={"order_ids": order_a["id"]}).json()
        entry = st[order_a["id"]]
        assert entry["status"] == "approved"
        assert entry["coupon"]["state"] == "unredeemed"
        assert entry["coupon"]["code"] == coupon["code"]
        assert entry["coupon"]["percent_off"] == 5
        _cleanup_coupon(mongo, coupon["code"])

    def test_one_star_review_still_gets_coupon(self, admin, order_b, mongo, review_settings):
        _submit_review(order_b["id"], rating=1, title="Meh")
        rid = next(x["id"] for x in admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
                   if x["order_id"] == order_b["id"])
        r = admin.post(f"{API}/admin/reviews/{rid}/approve")
        assert r.status_code == 200
        assert r.json()["coupon"] is not None
        _cleanup_coupon(mongo, r.json()["coupon"]["code"])

    def test_reapproving_does_not_issue_second_coupon(self, admin, order_c, mongo, review_settings):
        _submit_review(order_c["id"])
        rid = next(x["id"] for x in admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
                   if x["order_id"] == order_c["id"])
        first = admin.post(f"{API}/admin/reviews/{rid}/approve").json()["coupon"]
        assert first
        count_before = mongo.coupons.count_documents({"issued_to": order_c["email"]})
        second = admin.post(f"{API}/admin/reviews/{rid}/approve")
        assert second.status_code == 200
        assert second.json()["coupon"] is None
        count_after = mongo.coupons.count_documents({"issued_to": order_c["email"]})
        assert count_after == count_before
        _cleanup_coupon(mongo, first["code"])


# ---------------- Decline path ----------------
class TestDecline:
    def test_decline_deletes_review_no_coupon_and_locks_order(self, admin, order_a, mongo, review_settings):
        r = _submit_review(order_a["id"])
        assert r.status_code == 200
        rid = next(x["id"] for x in admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
                   if x["order_id"] == order_a["id"])
        before = mongo.coupons.count_documents({"source": "auto"})
        d = admin.delete(f"{API}/admin/reviews/{rid}")
        assert d.status_code == 200
        assert mongo.reviews.find_one({"_id": ObjectId(rid)}) is None
        assert mongo.coupons.count_documents({"source": "auto"}) == before, "decline must not issue a coupon"

        order = mongo.orders.find_one({"_id": ObjectId(order_a["id"])})
        assert order.get("review_declined") is True

        # Second attempt is refused
        r2 = _submit_review(order_a["id"])
        assert r2.status_code == 400
        assert "no longer eligible" in r2.text or "declined" in r2.text.lower()

        # /reviews/status reports declined
        st = requests.get(f"{API}/reviews/status", params={"order_ids": order_a["id"]}).json()
        assert st[order_a["id"]]["status"] == "declined"


# ---------------- Single use + wrong-email + row survival ----------------
class TestCouponSingleUse:
    def _approve(self, admin, order):
        _submit_review(order["id"])
        rid = next(x["id"] for x in admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
                   if x["order_id"] == order["id"])
        return admin.post(f"{API}/admin/reviews/{rid}/approve").json()["coupon"]

    def test_validate_ok_then_rejects_after_redemption(self, admin, order_a, mongo, review_settings, real_product_id):
        coupon = self._approve(admin, order_a)
        code = coupon["code"]
        try:
            payload = {"code": code, "email": order_a["email"],
                       "items": [{"product_id": real_product_id, "quantity": 1}]}
            # First validate should succeed (single use, not yet redeemed)
            r = requests.post(f"{API}/coupons/validate", json=payload)
            assert r.status_code == 200, r.text

            # Simulate redemption at webhook time
            mongo.coupons.update_one({"code": code},
                                     {"$inc": {"used_count": 1},
                                      "$set": {"redeemed_at": datetime.now(timezone.utc),
                                               "redeemed_order_id": "FAKE"}})
            mongo.coupon_redemptions.insert_one({
                "code": code, "email": order_a["email"].lower(),
                "order_id": "FAKE", "redeemed_at": datetime.now(timezone.utc),
            })

            # Second validate must be rejected (single use, max_uses reached)
            r2 = requests.post(f"{API}/coupons/validate", json=payload)
            assert r2.status_code == 400
            msg = r2.json().get("detail", "").lower()
            assert "fully redeemed" in msg or "already used" in msg

            # Coupon row survives — GET admin list still shows it
            listing = admin.get(f"{API}/admin/coupons", params={"source": "auto"}).json()
            row = next((c for c in listing if c["code"] == code), None)
            assert row is not None, "auto coupon must survive redemption"
            assert row["used_count"] >= 1
            assert row.get("redeemed_at")

            # /reviews/status now shows redeemed
            st = requests.get(f"{API}/reviews/status", params={"order_ids": order_a["id"]}).json()
            assert st[order_a["id"]]["coupon"]["state"] == "redeemed"
            assert st[order_a["id"]]["coupon"]["redeemed_at"]
        finally:
            _cleanup_coupon(mongo, code)

    def test_wrong_email_cannot_use_coupon(self, admin, order_b, mongo, review_settings, real_product_id):
        coupon = self._approve(admin, order_b)
        code = coupon["code"]
        try:
            r = requests.post(f"{API}/coupons/validate", json={
                "code": code, "email": "someone-else@example.com",
                "items": [{"product_id": real_product_id, "quantity": 1}],
            })
            assert r.status_code == 400
            assert "not valid" in r.json().get("detail", "").lower()
        finally:
            _cleanup_coupon(mongo, code)


# ---------------- Admin deletion -> status unavailable ----------------
class TestAdminDelete:
    def test_delete_coupon_makes_status_unavailable(self, admin, order_c, mongo, review_settings):
        _submit_review(order_c["id"])
        rid = next(x["id"] for x in admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
                   if x["order_id"] == order_c["id"])
        coupon = admin.post(f"{API}/admin/reviews/{rid}/approve").json()["coupon"]
        code = coupon["code"]
        # find coupon id
        doc = mongo.coupons.find_one({"code": code})
        cid = str(doc["_id"])
        d = admin.delete(f"{API}/admin/coupons/{cid}")
        assert d.status_code == 200
        st = requests.get(f"{API}/reviews/status", params={"order_ids": order_c["id"]}).json()
        entry = st[order_c["id"]]
        assert entry["status"] == "approved"
        assert entry["coupon"]["state"] == "unavailable"


# ---------------- Sweep window ----------------
class TestSweep:
    def test_sweep_only_removes_redeemed_or_expired_older_than_30d(self, admin, mongo, review_settings):
        code_recent = f"THANKSQA{secrets.token_hex(2).upper()}"
        code_old_redeemed = f"THANKSQA{secrets.token_hex(2).upper()}"
        code_old_unredeemed = f"THANKSQA{secrets.token_hex(2).upper()}"
        now = datetime.now(timezone.utc)
        # recent, redeemed — must survive
        mongo.coupons.insert_one({
            "code": code_recent, "source": "auto", "issued_to": "qa@x.com",
            "discount_type": "percent", "percent_off": 5, "one_per_customer": True,
            "max_uses": 1, "used_count": 1, "active": True,
            "expires_at": now + timedelta(days=30),
            "redeemed_at": now, "created_at": now,
        })
        # 40d old, redeemed — must be swept
        mongo.coupons.insert_one({
            "code": code_old_redeemed, "source": "auto", "issued_to": "qa@x.com",
            "discount_type": "percent", "percent_off": 5, "one_per_customer": True,
            "max_uses": 1, "used_count": 1, "active": True,
            "expires_at": now + timedelta(days=30),
            "redeemed_at": now - timedelta(days=40),
            "created_at": now - timedelta(days=40),
        })
        # 40d old, unredeemed and still valid — must survive (only redeemed OR expired go)
        mongo.coupons.insert_one({
            "code": code_old_unredeemed, "source": "auto", "issued_to": "qa@x.com",
            "discount_type": "percent", "percent_off": 5, "one_per_customer": True,
            "max_uses": 1, "used_count": 0, "active": True,
            "expires_at": now + timedelta(days=30),
            "created_at": now - timedelta(days=40),
        })
        try:
            # trigger sweep via admin listing
            admin.get(f"{API}/admin/coupons", params={"source": "auto"})
            assert mongo.coupons.find_one({"code": code_recent}) is not None
            assert mongo.coupons.find_one({"code": code_old_redeemed}) is None
            assert mongo.coupons.find_one({"code": code_old_unredeemed}) is not None
        finally:
            mongo.coupons.delete_many({"code": {"$in": [code_recent, code_old_redeemed, code_old_unredeemed]}})
