"""Iteration 19 — review-system upgrade tests.

Covers: anonymous/display_name on POST /api/reviews, public payload leakage,
pin/unpin admin endpoint, pinned-first sort on both public + admin listings,
DELETE with default lock=true (locks order) and lock=false (order still eligible),
and a light regression on the approval-coupon flow.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")
ADMIN_EMAIL = backend_env.get("ADMIN_EMAIL")
ADMIN_PASSWORD = backend_env.get("ADMIN_PASSWORD")


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _mk_order(mongo, email, marker):
    doc = {
        "user_id": "",
        "user_email": email,
        "origin_url": "https://preview.example",
        "items": [{"product_id": "TEST_PROD", "name": f"TEST {marker}", "category": "medals",
                   "price": 10.0, "quantity": 1, "variant_label": ""}],
        "total": 10.0, "subtotal": 10.0, "discount": 0.0, "coupon_code": None,
        "status": "completed", "payment_status": "paid",
        "session_id": f"TEST_SESSION_{marker}",
        "ptc_username_enc": "x", "ptc_password_enc": "x",
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    }
    return str(mongo.orders.insert_one(doc).inserted_id)


@pytest.fixture()
def order_factory(mongo):
    created = []

    def make(prefix="A"):
        marker = f"REVUP_{prefix}_{secrets.token_hex(3)}"
        email = f"reviewup+{marker.lower()}@delivered.resend.dev"
        oid = _mk_order(mongo, email, marker)
        created.append(oid)
        return {"id": oid, "email": email}

    yield make
    for oid in created:
        mongo.orders.delete_one({"_id": ObjectId(oid)})
        mongo.reviews.delete_many({"order_id": oid})


def _submit(oid, display_name="", anonymous=False, rating=5, title="Great"):
    body = "This is a QA seeded review body which is easily over 150 chars long. " * 3
    return requests.post(f"{API}/reviews", json={
        "order_id": oid, "rating": rating, "title": title, "body": body,
        "display_name": display_name, "anonymous": anonymous,
        "turnstile_token": "preview-bypass",
    })


def _approve(admin, rid):
    r = admin.post(f"{API}/admin/reviews/{rid}/approve")
    assert r.status_code == 200, r.text
    code = (r.json().get("coupon") or {}).get("code")
    return code


def _cleanup_coupons(mongo, codes):
    for c in codes:
        if c:
            mongo.coupons.delete_many({"code": c})
            mongo.coupon_redemptions.delete_many({"code": c})


def _find_rid(admin, order_id):
    docs = admin.get(f"{API}/admin/reviews", params={"status": "pending"}).json()
    return next(x["id"] for x in docs if x["order_id"] == order_id)


# ---------------- POST /reviews stores display_name + anonymous ----------------
class TestSubmissionDisplayName:
    def test_display_name_is_used_in_public_payload(self, admin, order_factory, mongo):
        o = order_factory("A")
        r = _submit(o["id"], display_name="Ash", anonymous=False)
        assert r.status_code == 200, r.text
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            pub = requests.get(f"{API}/reviews").json()
            entry = next(x for x in pub["reviews"] if x["id"] == rid)
            assert entry["first_name"] == "Ash"
        finally:
            _cleanup_coupons(mongo, [code])

    def test_anonymous_true_masks_to_valued_customer(self, admin, order_factory, mongo):
        o = order_factory("B")
        r = _submit(o["id"], display_name="Ash", anonymous=True)
        assert r.status_code == 200
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            entry = next(x for x in requests.get(f"{API}/reviews").json()["reviews"]
                         if x["id"] == rid)
            assert entry["first_name"] == "Valued Customer"
        finally:
            _cleanup_coupons(mongo, [code])

    def test_blank_display_name_falls_back_to_valued_customer(self, admin, order_factory, mongo):
        o = order_factory("C")
        r = _submit(o["id"], display_name="   ", anonymous=False)
        assert r.status_code == 200
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            entry = next(x for x in requests.get(f"{API}/reviews").json()["reviews"]
                         if x["id"] == rid)
            assert entry["first_name"] == "Valued Customer"
            # Also verify DB stored anonymous=True (fallback)
            doc = mongo.reviews.find_one({"_id": ObjectId(rid)})
            assert doc["anonymous"] is True
        finally:
            _cleanup_coupons(mongo, [code])


# ---------------- Public payload never leaks PII ----------------
class TestPublicPayloadLeak:
    def test_public_reviews_do_not_leak_email_realname_or_order_id(self, admin, order_factory, mongo):
        o = order_factory("D")
        _submit(o["id"], display_name="Ash", anonymous=False)
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            resp = requests.get(f"{API}/reviews")
            assert resp.status_code == 200
            data = resp.json()
            for entry in data["reviews"]:
                assert "user_email" not in entry
                assert "email" not in entry
                assert "order_id" not in entry
                assert "user_id" not in entry
                # first_name must be the display_name, not any real name
            # And ensure the raw email string never appears anywhere
            assert o["email"] not in resp.text
            assert o["id"] not in resp.text
        finally:
            _cleanup_coupons(mongo, [code])


# ---------------- Pin endpoint ----------------
class TestPinEndpoint:
    def test_pin_and_unpin_and_404(self, admin, order_factory, mongo):
        o = order_factory("E")
        _submit(o["id"], display_name="Ash")
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            r = admin.post(f"{API}/admin/reviews/{rid}/pin", params={"pinned": "true"})
            assert r.status_code == 200
            assert r.json()["pinned"] is True
            assert mongo.reviews.find_one({"_id": ObjectId(rid)})["pinned"] is True

            r2 = admin.post(f"{API}/admin/reviews/{rid}/pin", params={"pinned": "false"})
            assert r2.status_code == 200
            assert r2.json()["pinned"] is False
            assert mongo.reviews.find_one({"_id": ObjectId(rid)})["pinned"] is False

            r3 = admin.post(f"{API}/admin/reviews/{ObjectId()}/pin", params={"pinned": "true"})
            assert r3.status_code == 404
        finally:
            _cleanup_coupons(mongo, [code])

    def test_pin_requires_admin(self, order_factory, mongo, admin):
        o = order_factory("F")
        _submit(o["id"], display_name="Ash")
        rid = _find_rid(admin, o["id"])
        code = _approve(admin, rid)
        try:
            r = requests.post(f"{API}/admin/reviews/{rid}/pin", params={"pinned": "true"})
            assert r.status_code in (401, 403), r.text
        finally:
            _cleanup_coupons(mongo, [code])


# ---------------- Sort order: pinned first ----------------
class TestPinnedFirst:
    def test_public_and_admin_sort_pinned_first(self, admin, order_factory, mongo):
        old = order_factory("OLD")
        new = order_factory("NEW")
        _submit(old["id"], display_name="Older")
        rid_old = _find_rid(admin, old["id"])
        code_old = _approve(admin, rid_old)
        # Force older created_at
        mongo.reviews.update_one({"_id": ObjectId(rid_old)},
                                 {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(days=10)}})
        _submit(new["id"], display_name="Newer")
        rid_new = _find_rid(admin, new["id"])
        code_new = _approve(admin, rid_new)
        try:
            # Baseline: newer first when neither pinned
            pub = requests.get(f"{API}/reviews").json()["reviews"]
            ids = [r["id"] for r in pub]
            assert ids.index(rid_new) < ids.index(rid_old)

            # Now pin the older one — must jump to first
            admin.post(f"{API}/admin/reviews/{rid_old}/pin", params={"pinned": "true"})
            pub2 = requests.get(f"{API}/reviews").json()["reviews"]
            ids2 = [r["id"] for r in pub2]
            assert ids2[0] == rid_old
            # And the flag comes through
            assert pub2[0]["pinned"] is True

            # Admin listing: pinned first as well
            all_admin = admin.get(f"{API}/admin/reviews", params={"status": "approved"}).json()
            admin_ids = [r["id"] for r in all_admin]
            assert admin_ids[0] == rid_old
        finally:
            _cleanup_coupons(mongo, [code_old, code_new])


# ---------------- DELETE with lock semantics ----------------
class TestDeleteLockSemantics:
    def test_default_lock_true_locks_order_and_blocks_second_review(self, admin, order_factory, mongo):
        o = order_factory("LOCK")
        r = _submit(o["id"], display_name="Ash")
        assert r.status_code == 200
        rid = _find_rid(admin, o["id"])
        d = admin.delete(f"{API}/admin/reviews/{rid}")
        assert d.status_code == 200
        assert mongo.reviews.find_one({"_id": ObjectId(rid)}) is None
        order = mongo.orders.find_one({"_id": ObjectId(o["id"])})
        assert order.get("review_declined") is True
        # A second attempt is refused
        r2 = _submit(o["id"], display_name="Retry")
        assert r2.status_code == 400
        assert "no longer eligible" in r2.text.lower() or "declined" in r2.text.lower()

    def test_lock_false_keeps_order_eligible(self, admin, order_factory, mongo):
        o = order_factory("UNLOCK")
        r = _submit(o["id"], display_name="Ash")
        assert r.status_code == 200
        rid = _find_rid(admin, o["id"])
        d = admin.delete(f"{API}/admin/reviews/{rid}", params={"lock": "false"})
        assert d.status_code == 200
        assert mongo.reviews.find_one({"_id": ObjectId(rid)}) is None
        order = mongo.orders.find_one({"_id": ObjectId(o["id"])})
        assert not order.get("review_declined"), "lock=false must NOT set review_declined"
        # A new review must be accepted
        r2 = _submit(o["id"], display_name="Second")
        assert r2.status_code == 200, r2.text


# ---------------- Regression: approve issues a single-use coupon ----------------
class TestApprovalCouponRegression:
    def test_approve_issues_single_coupon(self, admin, order_factory, mongo):
        o = order_factory("REG")
        _submit(o["id"], display_name="Ash")
        rid = _find_rid(admin, o["id"])
        r = admin.post(f"{API}/admin/reviews/{rid}/approve")
        assert r.status_code == 200
        coupon = r.json()["coupon"]
        assert coupon and coupon["code"].startswith("THANKS")
        try:
            doc = mongo.coupons.find_one({"code": coupon["code"]})
            assert doc["max_uses"] == 1
            assert doc["one_per_customer"] is True
            assert doc["issued_to"].lower() == o["email"].lower()
        finally:
            _cleanup_coupons(mongo, [coupon["code"]])
