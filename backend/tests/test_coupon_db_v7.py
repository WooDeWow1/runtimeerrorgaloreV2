"""DB-level checks that HTTP alone cannot cover: session pricing rows, max_uses exhaustion,
one_per_customer redemption block."""
import asyncio
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

backend_env = dotenv_values("/app/backend/.env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = frontend_env["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
QA_EMAIL = "pokecoinsqa@gmail.com"


def db():
    client = AsyncIOMotorClient(backend_env["MONGO_URL"])
    return client, client[backend_env["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'Email:\s*`([^`]+)`', content).group(1)
    pwd = re.search(r'Password:\s*`([^`]+)`', content).group(1)
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="module")
def cart(admin):
    prods = requests.get(f"{API}/products").json()
    coin = next(p for p in prods if p["name"] == "2,700 Pokécoins")
    ticket = next(p for p in prods if p["name"] == "Weekly Event Ticket")
    return coin, ticket


def test_checkout_session_records_discounted_total(cart):
    coin, ticket = cart
    r = requests.post(f"{API}/orders/checkout", json={
        "items": [{"product_id": coin["id"], "quantity": 1},
                  {"product_id": ticket["id"], "quantity": 1}],
        "ptc_username": "qa_user", "ptc_password": "qa_pass",
        "origin_url": BASE_URL, "email": QA_EMAIL, "coupon_code": "TEST20"})
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    async def check():
        client, d = db()
        from bson import ObjectId
        doc = await d.checkout_sessions.find_one({"_id": ObjectId(session_id)})
        client.close()
        return doc

    doc = asyncio.run(check())
    assert doc is not None
    assert doc["subtotal"] == 17.98
    assert doc["discount"] == 3.00
    assert doc["total"] == 14.98, f"session total should be the discounted total, got {doc['total']}"
    assert doc["coupon_code"] == "TEST20"
    assert doc["invoice_id"]


def test_checkout_without_coupon_records_zero_discount(cart):
    coin, _ = cart
    r = requests.post(f"{API}/orders/checkout", json={
        "items": [{"product_id": coin["id"], "quantity": 1}],
        "ptc_username": "qa_user", "ptc_password": "qa_pass",
        "origin_url": BASE_URL, "email": QA_EMAIL})
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    async def check():
        client, d = db()
        from bson import ObjectId
        doc = await d.checkout_sessions.find_one({"_id": ObjectId(session_id)})
        client.close()
        return doc

    doc = asyncio.run(check())
    assert doc["discount"] == 0.0
    assert doc["coupon_code"] is None
    assert doc["total"] == doc["subtotal"] == coin["price"]


def test_max_uses_exhausted_and_one_per_customer(admin, cart):
    coin, _ = cart
    items = [{"product_id": coin["id"], "quantity": 1}]
    r = admin.post(f"{API}/admin/coupons", json={"code": "TEST_QA_DBGUARD", "discount_type": "percent",
                                                 "percent_off": 10, "max_uses": 1,
                                                 "one_per_customer": True})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    try:
        # works before exhaustion
        ok = requests.post(f"{API}/coupons/validate",
                           json={"code": "TEST_QA_DBGUARD", "items": items, "email": QA_EMAIL})
        assert ok.status_code == 200, ok.text

        async def redeem():
            client, d = db()
            await d.coupons.update_one({"code": "TEST_QA_DBGUARD"}, {"$set": {"used_count": 1}})
            await d.coupon_redemptions.update_one(
                {"code": "TEST_QA_DBGUARD", "email": QA_EMAIL},
                {"$set": {"order_id": "qa"}}, upsert=True)
            client.close()

        asyncio.run(redeem())
        r2 = requests.post(f"{API}/coupons/validate",
                           json={"code": "TEST_QA_DBGUARD", "items": items, "email": QA_EMAIL})
        assert r2.status_code == 400
        assert "fully redeemed" in r2.json()["detail"], r2.text

        # lift max_uses -> now the per-customer guard should be the blocker
        async def lift():
            client, d = db()
            await d.coupons.update_one({"code": "TEST_QA_DBGUARD"}, {"$set": {"max_uses": 99}})
            client.close()

        asyncio.run(lift())
        r3 = requests.post(f"{API}/coupons/validate",
                           json={"code": "TEST_QA_DBGUARD", "items": items, "email": QA_EMAIL})
        assert r3.status_code == 400 and "already used" in r3.json()["detail"], r3.text
        # a different email still works
        r4 = requests.post(f"{API}/coupons/validate",
                           json={"code": "TEST_QA_DBGUARD", "items": items,
                                 "email": "someoneelse@gmail.com"})
        assert r4.status_code == 200, r4.text
    finally:
        admin.delete(f"{API}/admin/coupons/{cid}")

        async def clean():
            client, d = db()
            await d.coupon_redemptions.delete_many({"code": "TEST_QA_DBGUARD"})
            client.close()

        asyncio.run(clean())
