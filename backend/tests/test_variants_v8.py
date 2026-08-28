"""Iteration 16: product variants, description formatting, variant-aware coupon maths
and variant pass-through to SellAuth checkout."""
import asyncio
import re
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
_cred = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
ADMIN_EMAIL = re.search(r'Email:\s*`([^`]+)`', _cred).group(1)
ADMIN_PASS = re.search(r'Password:\s*`([^`]+)`', _cred).group(1)

WEEKLY = 851924
MONTHLY = 851928
EXPECTED = {
    WEEKLY: [("Basic", 1508676, 2.99), ("+ 6 Ranks", 1553265, 4.49), ("Ultra Box", 1553266, 5.99)],
    MONTHLY: [("Basic", 1508694, 4.99), ("+10 Ranks", 1553263, 6.99), ("Ultra Box", 1553264, 9.99)],
}


def _mongo(coro):
    async def run():
        client = AsyncIOMotorClient(env["MONGO_URL"])
        try:
            return await coro(client[env["DB_NAME"]])
        finally:
            client.close()

    return asyncio.run(run())


@pytest.fixture(scope="module")
def products():
    r = requests.get(f"{API}/products", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


def by_sellauth(products, sid):
    match = [p for p in products if p.get("sellauth_product_id") == sid]
    assert match, f"no product with sellauth id {sid}"
    return match[0]


def a_bundle(products):
    return next(p for p in products if p["category"] == "pokecoin_bundle"
                and abs(p["price"] - 14.99) < 0.001 and p["active"] and not p["coming_soon"])


# ---------- variant seeding ----------
@pytest.mark.parametrize("sid", [WEEKLY, MONTHLY])
def test_variants_seeded(products, sid):
    p = by_sellauth(products, sid)
    got = [(v["label"], v["sellauth_variant_id"], v["price"]) for v in p["variants"]]
    assert got == EXPECTED[sid], got
    # card price + default variant equal the first (Basic) option
    assert p["price"] == EXPECTED[sid][0][2]
    assert p["sellauth_variant_id"] == EXPECTED[sid][0][1]
    assert "_id" not in p


def test_products_have_no_mongo_id(products):
    assert all("_id" not in p for p in products)


# ---------- variant resolution / validation ----------
def test_invalid_variant_rejected(products):
    p = by_sellauth(products, WEEKLY)
    r = requests.post(f"{API}/coupons/validate",
                      json={"code": "TEST20", "items": [{"product_id": p["id"], "quantity": 1,
                                                         "variant_id": 999}]}, timeout=30)
    assert r.status_code == 400, r.text
    assert "no longer available" in r.json()["detail"], r.text


def test_missing_variant_falls_back_to_first(products):
    """No variant_id -> Basic price (2.99). Coupon maths proves the resolved price."""
    p = by_sellauth(products, WEEKLY)
    bundle = a_bundle(products)
    r = requests.post(f"{API}/coupons/validate",
                      json={"code": "TEST20",
                            "items": [{"product_id": bundle["id"], "quantity": 1},
                                      {"product_id": p["id"], "quantity": 1}]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["subtotal"] == round(bundle["price"] + 2.99, 2), r.json()


# ---------- coupon maths with variants ----------
def test_coupon_excludes_event_pass_variant(products):
    p = by_sellauth(products, WEEKLY)
    bundle = a_bundle(products)
    r = requests.post(f"{API}/coupons/validate",
                      json={"code": "TEST20",
                            "items": [{"product_id": bundle["id"], "quantity": 1},
                                      {"product_id": p["id"], "quantity": 1,
                                       "variant_id": 1553266}]}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["subtotal"] == 20.98, d
    assert d["eligible_subtotal"] == 14.99, d
    assert d["discount"] == 3.00, d
    assert d["total"] == 17.98, d
    assert d["excluded_names"] == ["Weekly Event Ticket"], d


def test_two_variants_of_same_product_are_separate_lines(products):
    """Monthly Go Pass has variants; two different variants must price independently."""
    p = by_sellauth(products, MONTHLY)
    bundle = a_bundle(products)
    r = requests.post(f"{API}/coupons/validate",
                      json={"code": "TEST20",
                            "items": [{"product_id": bundle["id"], "quantity": 1},
                                      {"product_id": p["id"], "quantity": 1, "variant_id": 1508694},
                                      {"product_id": p["id"], "quantity": 1,
                                       "variant_id": 1553264}]}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["subtotal"] == round(14.99 + 4.99 + 9.99, 2), d
    assert d["eligible_subtotal"] == 14.99, d


# ---------- cart rules regression ----------
def test_event_pass_alone_rejected(products):
    p = by_sellauth(products, WEEKLY)
    r = requests.post(f"{API}/orders/checkout", json={
        "items": [{"product_id": p["id"], "quantity": 1, "variant_id": 1553266}],
        "ptc_username": "TEST_qa", "ptc_password": "TEST_qa",
        "origin_url": BASE, "email": "delivered@resend.dev"}, timeout=60)
    assert r.status_code == 400, r.text
    assert "cannot be bought on its own" in r.json()["detail"], r.text


def test_two_event_passes_rejected(products):
    weekly = by_sellauth(products, WEEKLY)
    monthly = by_sellauth(products, MONTHLY)
    bundle = a_bundle(products)
    r = requests.post(f"{API}/orders/checkout", json={
        "items": [{"product_id": bundle["id"], "quantity": 1},
                  {"product_id": weekly["id"], "quantity": 1, "variant_id": 1553266},
                  {"product_id": monthly["id"], "quantity": 1, "variant_id": 1553264}],
        "ptc_username": "TEST_qa", "ptc_password": "TEST_qa",
        "origin_url": BASE, "email": "delivered@resend.dev"}, timeout=60)
    assert r.status_code == 400, r.text
    assert "Only one Event Pass" in r.json()["detail"], r.text


# ---------- checkout carries the variant ----------
def test_checkout_persists_variant(products):
    weekly = by_sellauth(products, WEEKLY)
    bundle = a_bundle(products)
    r = requests.post(f"{API}/orders/checkout", json={
        "items": [{"product_id": bundle["id"], "quantity": 1},
                  {"product_id": weekly["id"], "quantity": 1, "variant_id": 1553266}],
        "ptc_username": "TEST_qa", "ptc_password": "TEST_qa",
        "origin_url": BASE, "email": "delivered@resend.dev"}, timeout=90)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"].startswith("http"), body
    session_id = body["session_id"]

    async def fetch(d):
        return await d.checkout_sessions.find_one({"_id": ObjectId(session_id)})

    doc = _mongo(fetch)
    assert doc is not None
    line = next(i for i in doc["items"] if i["sellauth_product_id"] == WEEKLY)
    assert line["sellauth_variant_id"] == 1553266, line
    assert line["price"] == 5.99, line
    assert line["variant_label"] == "Ultra Box", line
    assert doc["total"] == round(bundle["price"] + 5.99, 2), doc["total"]

    async def cleanup(d):
        await d.checkout_sessions.delete_one({"_id": ObjectId(session_id)})

    _mongo(cleanup)


# ---------- description formatting ----------
MULTILINE = "Line one\nLine two\n\nSecond paragraph after a blank line.\n- bullet a\n- bullet b"


def test_description_newlines_survive_save_and_update(admin):
    payload = {"name": "TEST_Formatting Probe", "description": MULTILINE,
               "category": "pokecoin_bundle", "price": 1.99, "image_url": "",
               "active": True, "coming_soon": False}
    r = admin.post(f"{API}/products", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    try:
        assert r.json()["description"] == MULTILINE
        listed = next(p for p in requests.get(f"{API}/products", timeout=30).json()
                      if p["id"] == pid)
        assert listed["description"] == MULTILINE, repr(listed["description"])

        # variants editor via API: add two options then remove them
        upd = admin.put(f"{API}/products/{pid}", json={"variants": [
            {"label": "TEST_Small", "sellauth_variant_id": 111111, "price": 1.99},
            {"label": "TEST_Large", "sellauth_variant_id": 222222, "price": 3.99}]}, timeout=30)
        assert upd.status_code == 200, upd.text
        assert [v["label"] for v in upd.json()["variants"]] == ["TEST_Small", "TEST_Large"]

        # a chosen custom variant prices the line
        val = requests.post(f"{API}/coupons/validate", json={"code": "TEST20", "items": [
            {"product_id": pid, "quantity": 2, "variant_id": 222222}]}, timeout=30)
        assert val.status_code == 200, val.text
        assert val.json()["subtotal"] == 7.98, val.json()

        cleared = admin.put(f"{API}/products/{pid}", json={"variants": []}, timeout=30)
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["variants"] == []
    finally:
        assert admin.delete(f"{API}/products/{pid}", timeout=30).status_code == 200


def test_existing_product_descriptions_keep_newlines(products):
    multi = [p for p in products if "\n" in (p.get("description") or "")]
    assert multi, "no product description contains a newline"
