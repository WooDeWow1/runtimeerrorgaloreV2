"""Iteration 14: SellAuth catalog checkout, cart rules, coupon passthrough, banner, admin cleanup.

Covers:
- GET /api/products  (sellauth_product_id/variant_id mapping, PokeCoins pricing)
- POST /api/orders/checkout (real SellAuth catalog checkout, cart rules, coupon passthrough)
- removed coupon engine endpoints (404/405)
- GET /api/settings/banner + PUT /api/admin/settings/banner (auth + validation)
- regression: waitlist, analytics, admin orders, checkout-session polling
"""
import os
import subprocess
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base.rstrip("/") + "/api"
ORIGIN = base.rstrip("/")

from admin_creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

CREATED_SESSIONS = []


class Anon:
    """Cookie-less client so every request is truly anonymous."""

    def request(self, method, url, **kw):
        headers = {"Content-Type": "application/json", **kw.pop("headers", {})}
        return requests.request(method, url, headers=headers, timeout=60, **kw)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture(scope="module")
def client():
    return Anon()


@pytest.fixture(scope="module")
def admin_headers(client):
    r = client.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no token in login response: {r.text[:300]}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def products(client):
    r = client.get(f"{BASE}/products")
    assert r.status_code == 200, r.text[:300]
    return r.json()


def pick(products, category, coming_soon=False):
    return [p for p in products if p["category"] == category
            and bool(p.get("coming_soon")) == coming_soon]


def checkout_payload(items, coupon=None, email=None):
    body = {
        "items": items,
        "ptc_username": "qa_it14_trainer",
        "ptc_password": "qa_it14_pass",
        "origin_url": ORIGIN,
        "email": email or f"qa-it14+{uuid.uuid4().hex[:6]}@gmail.com",
    }
    if coupon:
        body["coupon_code"] = coupon
    return body


def do_checkout(client, items, coupon=None):
    r = client.post(f"{BASE}/orders/checkout", json=checkout_payload(items, coupon))
    if r.status_code == 200:
        sid = r.json().get("session_id")
        if sid:
            CREATED_SESSIONS.append(sid)
    return r


# ---------------- SellAuth catalog mapping ----------------
class TestCatalogMapping:
    def test_every_available_product_has_sellauth_ids(self, products):
        assert len(products) >= 10
        missing = [p["name"] for p in products
                   if not p.get("coming_soon")
                   and not (p.get("sellauth_product_id") and p.get("sellauth_variant_id"))]
        assert missing == [], f"products missing SellAuth ids: {missing}"

    def test_only_the_two_shundo_items_are_coming_soon(self, products):
        cs = [p for p in products if p.get("coming_soon")]
        assert len(cs) == 2, [p["name"] for p in cs]
        assert all(p["category"] == "shundo_service" for p in cs)
        assert all(p.get("sellauth_product_id") is None for p in cs)

    def test_no_mongo_object_id_leak(self, products):
        for p in products:
            assert "_id" not in p
            assert isinstance(p["id"], str) and len(p["id"]) == 24

    def test_sellauth_synced_prices(self, products):
        by_name = {p["name"]: p["price"] for p in products}
        assert by_name.get("5,600 Pokécoins") == 25.00
        assert by_name.get('"Size Matters" - 3x Platinum Medal Bundle') == 129.99
        assert by_name.get("“Showcase Star” - Platinum Medal") == 149.99


# ---------------- Cart rules (assert_cart_rules) ----------------
class TestCartRules:
    def test_pass_alone_rejected(self, client, products):
        p = pick(products, "event_pass")[0]
        r = do_checkout(client, [{"product_id": p["id"], "quantity": 1}])
        assert r.status_code == 400, r.text[:300]
        assert "cannot be bought on its own" in r.json()["detail"]

    def test_two_distinct_passes_with_coins_rejected(self, client, products):
        passes = pick(products, "event_pass")
        coins = pick(products, "pokecoin_bundle")[0]
        r = do_checkout(client, [
            {"product_id": passes[0]["id"], "quantity": 1},
            {"product_id": passes[1]["id"], "quantity": 1},
            {"product_id": coins["id"], "quantity": 1},
        ])
        assert r.status_code == 400, r.text[:300]
        assert "Only one Event Pass per order" in r.json()["detail"]

    def test_pass_quantity_two_rejected(self, client, products):
        p = pick(products, "event_pass")[0]
        coins = pick(products, "pokecoin_bundle")[0]
        r = do_checkout(client, [
            {"product_id": p["id"], "quantity": 2},
            {"product_id": coins["id"], "quantity": 1},
        ])
        assert r.status_code == 400, r.text[:300]
        assert "Only one Event Pass per order" in r.json()["detail"]

    def test_pass_plus_stardust_allowed(self, client, products):
        p = pick(products, "event_pass")[0]
        star = pick(products, "stardust")[0]
        r = do_checkout(client, [
            {"product_id": p["id"], "quantity": 1},
            {"product_id": star["id"], "quantity": 1},
        ])
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data["checkout_url"].startswith("http"), data
        assert data["invoice_id"]

    def test_pass_plus_medal_allowed(self, client, products):
        p = pick(products, "event_pass")[0]
        medal = pick(products, "medals")[0]
        r = do_checkout(client, [
            {"product_id": p["id"], "quantity": 1},
            {"product_id": medal["id"], "quantity": 1},
        ])
        assert r.status_code == 200, r.text[:400]
        assert r.json()["checkout_url"].startswith("http")

    def test_coming_soon_product_blocked(self, client, products):
        cs = [p for p in products if p.get("coming_soon")][0]
        r = do_checkout(client, [{"product_id": cs["id"], "quantity": 1}])
        assert r.status_code == 400
        assert "not available yet" in r.json()["detail"]

    def test_empty_cart_rejected(self, client):
        r = client.post(f"{BASE}/orders/checkout", json=checkout_payload([]))
        assert r.status_code == 400
        assert "Cart is empty" in r.json()["detail"]


# ---------------- Coupon passthrough / removed engine ----------------
@pytest.mark.skip(reason="Obsolete: the local coupon engine was restored in iteration 15 "
                         "(this site owns discounts). Live coverage lives in "
                         "test_hybrid_coupons_v7.py / test_refactor_regression_v9.py")
class TestCouponPassthrough:
    def test_coupon_code_accepted_and_session_created(self, client, products):
        coins = pick(products, "pokecoin_bundle")[0]
        r = do_checkout(client, [{"product_id": coins["id"], "quantity": 1}], coupon="qa-it14-bogus")
        # An unknown code must not break checkout locally: SellAuth owns validation.
        assert r.status_code in (200, 400), r.text[:400]
        if r.status_code == 200:
            sid = r.json()["session_id"]
            s = client.get(f"{BASE}/checkout-sessions/{sid}")
            assert s.status_code == 200
            assert s.json().get("coupon_code") in ("QA-IT14-BOGUS", None)
        else:
            # SellAuth rejected the coupon -> error surfaces from SellAuth, not local engine
            assert "coupon" in r.text.lower() or "invalid" in r.text.lower(), r.text[:300]

    @pytest.mark.parametrize("path,method", [
        ("/coupons/validate", "POST"),
        ("/coupons/validate", "GET"),
        ("/admin/coupons", "GET"),
        ("/admin/coupons", "POST"),
        ("/admin/coupons/anything", "DELETE"),
    ])
    def test_coupon_endpoints_removed(self, client, path, method):
        r = client.request(method, f"{BASE}{path}", json={})
        assert r.status_code in (404, 405), f"{method} {path} -> {r.status_code}"


# ---------------- Announcement banner ----------------
class TestBanner:
    def test_public_get(self, client):
        r = client.get(f"{BASE}/settings/banner")
        assert r.status_code == 200
        data = r.json()
        for key in ("enabled", "text", "link_url", "link_label"):
            assert key in data
        assert isinstance(data["enabled"], bool)

    def test_anonymous_put_rejected(self, client):
        r = client.put(f"{BASE}/admin/settings/banner",
                       json={"enabled": True, "text": "hax", "link_url": "", "link_label": ""})
        assert r.status_code in (401, 403), r.status_code

    def test_javascript_link_rejected(self, client, admin_headers):
        r = client.put(f"{BASE}/admin/settings/banner", headers=admin_headers, json={
            "enabled": True, "text": "bad", "link_url": "javascript:alert(1)", "link_label": "x"})
        assert r.status_code == 400, r.text[:300]
        assert "https://" in r.json()["detail"]

    def test_admin_update_and_persist(self, client, admin_headers):
        original = client.get(f"{BASE}/settings/banner").json()
        try:
            new = {"enabled": True, "text": "QA IT14 banner", "link_url": "/products",
                   "link_label": "QA link"}
            r = client.put(f"{BASE}/admin/settings/banner", headers=admin_headers, json=new)
            assert r.status_code == 200, r.text[:300]
            got = client.get(f"{BASE}/settings/banner").json()
            assert got["text"] == "QA IT14 banner"
            assert got["link_url"] == "/products"
            assert got["link_label"] == "QA link"
            assert got["enabled"]

            off = {**new, "enabled": False}
            assert client.put(f"{BASE}/admin/settings/banner", headers=admin_headers,
                              json=off).status_code == 200
            assert not (client.get(f"{BASE}/settings/banner").json()["enabled"])
        finally:
            client.put(f"{BASE}/admin/settings/banner", headers=admin_headers, json=original)
            assert client.get(f"{BASE}/settings/banner").json() == original

    def test_absolute_https_link_allowed(self, client, admin_headers):
        original = client.get(f"{BASE}/settings/banner").json()
        try:
            r = client.put(f"{BASE}/admin/settings/banner", headers=admin_headers, json={
                "enabled": True, "text": "QA abs", "link_url": "https://pokecoins.cc/products",
                "link_label": "Go"})
            assert r.status_code == 200, r.text[:300]
        finally:
            client.put(f"{BASE}/admin/settings/banner", headers=admin_headers, json=original)


# ---------------- Regression ----------------
class TestRegression:
    def test_admin_orders_requires_admin(self, client):
        r = client.get(f"{BASE}/admin/orders")
        assert r.status_code in (401, 403)

    def test_admin_orders_and_analytics(self, client, admin_headers):
        r = client.get(f"{BASE}/admin/orders", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        a = client.get(f"{BASE}/admin/analytics", headers=admin_headers)
        assert a.status_code == 200, a.text[:300]
        totals = a.json().get("totals", {})
        assert "orders" in totals and "unique_visitors" in totals, a.json()

    def test_waitlist(self, client, admin_headers, products):
        cs = [p for p in products if p.get("coming_soon")][0]
        email = f"qa-it14-wl+{uuid.uuid4().hex[:6]}@gmail.com"
        r = client.post(f"{BASE}/waitlist", json={"email": email, "product_id": cs["id"],
                                                  "note": "qa"})
        assert r.status_code in (200, 201), r.text[:300]
        wl = client.get(f"{BASE}/admin/waitlist", headers=admin_headers)
        assert wl.status_code == 200
        assert any(e.get("email") == email for e in wl.json())

    def test_paid_session_poll_and_order(self, client):
        out = subprocess.run(["python3", "/app/scripts/seed_ui_test_order.py"],
                             capture_output=True, text=True, cwd="/app/backend", timeout=120)
        assert out.returncode == 0, out.stderr[-600:]
        info = dict(line.split(" ", 1) for line in out.stdout.strip().splitlines()
                    if line.startswith(("SESSION_ID", "ORDER_ID", "EMAIL")))
        sid, order_id = info["SESSION_ID"], info["ORDER_ID"]
        try:
            s = client.get(f"{BASE}/checkout-sessions/{sid}")
            assert s.status_code == 200, s.text[:300]
            body = s.json()
            assert body.get("status") == "paid", body
            assert body.get("order_id") == order_id
            o = client.get(f"{BASE}/orders/{order_id}")
            assert o.status_code == 200
            assert o.json()["payment_status"] == "paid"
            assert "ptc_password_enc" not in o.json()
        finally:
            subprocess.run(["python3", "/app/scripts/delete_orders_by_id.py", order_id],
                           capture_output=True, text=True, cwd="/app/backend", timeout=120)


def teardown_module(module):
    """Remove the unpaid SellAuth checkout sessions this suite created."""
    import asyncio
    import sys
    if not CREATED_SESSIONS:
        return
    sys.path.insert(0, "/app/backend")
    import server  # noqa

    async def _clean():
        for sid in CREATED_SESSIONS:
            try:
                await server.db.checkout_sessions.delete_one({"_id": server.ObjectId(sid)})
            except Exception:
                pass
    asyncio.run(_clean())
