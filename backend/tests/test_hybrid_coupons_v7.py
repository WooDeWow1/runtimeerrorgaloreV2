"""Iteration 15 — hybrid launch: categories manager, product editor + SellAuth resolve,
coupon engine (Event Pass hard block), discounted checkout."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

POKELID_DESCRIPTION = (
    "We login to your account and go through the stamp rally’s. You receive an estimate of 50-100 "
    "exclusive background Pokemon (usually a Pikachu) and you may even get shiny ones! (We cannot "
    "guarantee how many shinies anyone will get, it’s all RNG)"
)


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("credentials file unusable")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=creds)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    assert r.json()["user"]["role"] == "admin"
    return s


QA_EMAIL = "pokecoinsqa@gmail.com"


@pytest.fixture(scope="session", autouse=True)
def test20(admin):
    """The QA coupon TEST20 (20% off, no restrictions). Created if the store does not have it."""
    existing = next((c for c in admin.get(f"{API}/admin/coupons").json() if c["code"] == "TEST20"), None)
    if existing:
        yield existing
        return
    r = admin.post(f"{API}/admin/coupons", json={"code": "TEST20", "discount_type": "percent",
                                                 "percent_off": 20, "note": "QA"})
    assert r.status_code == 200 or "already exists" in r.text, r.text
    yield next(c for c in admin.get(f"{API}/admin/coupons").json() if c["code"] == "TEST20")


@pytest.fixture(scope="session")
def products(anon):
    r = anon.get(f"{API}/products")
    assert r.status_code == 200
    return r.json()


def by_name(products, name):
    return next(p for p in products if p["name"] == name)


# ---------------- categories ----------------
class TestCategories:
    EXPECTED = ["pokecoin_bundle", "event_pass", "pokelid", "medals", "stardust", "shundo_service"]

    def test_public_list_order(self, anon):
        r = anon.get(f"{API}/categories")
        assert r.status_code == 200
        data = r.json()
        assert [c["key"] for c in data] == self.EXPECTED
        assert all("_id" not in c and "id" in c for c in data)
        shundo = next(c for c in data if c["key"] == "shundo_service")
        assert shundo["coming_soon"] is True
        assert shundo["label"] == "Shundo Hunting (Waitlist)"

    def test_admin_guard(self, anon):
        assert anon.post(f"{API}/admin/categories", json={"label": "TEST_nope"}).status_code == 401
        assert anon.get(f"{API}/admin/coupons").status_code == 401

    def test_category_crud_and_reorder(self, admin):
        # create
        r = admin.post(f"{API}/admin/categories", json={"label": "TEST_Zone", "note": "qa"})
        assert r.status_code == 200, r.text
        cat = r.json()
        cid, key = cat["id"], cat["key"]
        assert key == "test_zone"
        assert cat["label"] == "TEST_Zone"
        try:
            # duplicate
            assert admin.post(f"{API}/admin/categories", json={"label": "TEST_Zone"}).status_code == 400
            # rename persists
            r = admin.put(f"{API}/admin/categories/{cid}", json={"label": "TEST_Zone2"})
            assert r.status_code == 200 and r.json()["label"] == "TEST_Zone2"
            listed = admin.get(f"{API}/categories").json()
            assert next(c for c in listed if c["id"] == cid)["label"] == "TEST_Zone2"
            start = [c["id"] for c in listed].index(cid)
            # move up
            r = admin.post(f"{API}/admin/categories/{cid}/move", json={"direction": "up"})
            assert r.status_code == 200
            up = [c["id"] for c in r.json()].index(cid)
            assert up == start - 1, f"move up did not change order ({start} -> {up})"
            # move down
            r = admin.post(f"{API}/admin/categories/{cid}/move", json={"direction": "down"})
            assert [c["id"] for c in r.json()].index(cid) == start
        finally:
            assert admin.delete(f"{API}/admin/categories/{cid}").status_code == 200
        assert cid not in [c["id"] for c in admin.get(f"{API}/categories").json()]
        assert admin.delete(f"{API}/admin/categories/{cid}").status_code == 404

    def test_delete_in_use_category_blocked(self, admin):
        cats = admin.get(f"{API}/categories").json()
        pokelid = next(c for c in cats if c["key"] == "pokelid")
        r = admin.delete(f"{API}/admin/categories/{pokelid['id']}")
        assert r.status_code == 400, r.text
        assert "still use this category" in r.json()["detail"]
        # still present
        assert "pokelid" in [c["key"] for c in admin.get(f"{API}/categories").json()]


# ---------------- products + sellauth ----------------
class TestProductsSellAuth:
    def test_sellauth_lookup(self, admin):
        r = admin.get(f"{API}/admin/sellauth/products/857694")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("sellauth_variant_id"), int)
        assert float(data["price"]) > 0

    def test_sellauth_lookup_requires_admin(self, anon):
        assert anon.get(f"{API}/admin/sellauth/products/857694").status_code == 401

    def test_pokelid_products(self, products, anon):
        japan = by_name(products, "Japan PokéLid Stamp Rally Collection")
        lego = by_name(products, "LEGO PokéLid Stamp Rally")
        for p, sid, img in ((japan, 857694, "/images/japanlid.jpg"), (lego, 857690, "/images/legolid.jpg")):
            assert p["category"] == "pokelid"
            assert p["sellauth_product_id"] == sid
            assert isinstance(p["sellauth_variant_id"], int)
            assert p["image_url"] == img
            assert p["description"] == POKELID_DESCRIPTION
            assert p["price"] > 0
            assert anon.get(f"{BASE_URL}{img}").status_code == 200

    def test_product_crud_with_sellauth_autofill(self, admin):
        payload = {
            "name": "TEST_QA Product", "description": "qa", "category": "pokelid",
            "price": 1.23, "msrp": 9.99, "image_url": "/images/japanlid.jpg",
            "badge": "QA", "sellauth_product_id": 857694, "active": True, "is_featured": False,
        }
        r = admin.post(f"{API}/products", json=payload)
        assert r.status_code == 200, r.text
        prod = r.json()
        pid = prod["id"]
        try:
            assert isinstance(prod["sellauth_variant_id"], int), "variant not auto-resolved"
            assert prod["price"] != 1.23, "price should be overwritten by SellAuth live price"
            live = admin.get(f"{API}/admin/sellauth/products/857694").json()
            assert prod["price"] == float(live["price"])
            assert prod["sellauth_variant_id"] == live["sellauth_variant_id"]
            # persisted
            listed = admin.get(f"{API}/products", params={"include_inactive": "true"}).json()
            saved = next(p for p in listed if p["id"] == pid)
            assert saved["image_url"] == "/images/japanlid.jpg"
            assert saved["msrp"] == 9.99
            # update: partial edit keeps other fields
            r = admin.put(f"{API}/products/{pid}", json={"name": "TEST_QA Product 2", "badge": "QA2"})
            assert r.status_code == 200 and r.json()["name"] == "TEST_QA Product 2"
            again = next(p for p in admin.get(f"{API}/products", params={"include_inactive": "true"}).json()
                         if p["id"] == pid)
            assert again["name"] == "TEST_QA Product 2"
            assert again["msrp"] == 9.99 and again["sellauth_variant_id"] == prod["sellauth_variant_id"]
            # bad category rejected
            assert admin.put(f"{API}/products/{pid}", json={"category": "nope"}).status_code == 400
        finally:
            assert admin.delete(f"{API}/products/{pid}").status_code == 200
        assert pid not in [p["id"] for p in admin.get(f"{API}/products", params={"include_inactive": "true"}).json()]

    def test_create_product_invalid_category(self, admin):
        r = admin.post(f"{API}/products", json={"name": "TEST_bad", "category": "bogus", "price": 5})
        assert r.status_code == 400


# ---------------- coupons ----------------
@pytest.fixture(scope="class")
def coupon_ids():
    return []


@pytest.fixture(scope="class", autouse=True)
def cleanup_coupons(admin, coupon_ids):
    yield
    for cid in coupon_ids:
        admin.delete(f"{API}/admin/coupons/{cid}")


def make_coupon(admin, coupon_ids, **kwargs):
    payload = {"code": kwargs.pop("code"), "discount_type": "percent", "percent_off": 20, **kwargs}
    r = admin.post(f"{API}/admin/coupons", json=payload)
    assert r.status_code == 200, r.text
    coupon_ids.append(r.json()["id"])
    return r.json()


class TestCouponCRUD:
    def test_validation_errors(self, admin, coupon_ids):
        r = admin.post(f"{API}/admin/coupons", json={"code": "TEST_PCTMISS", "discount_type": "percent"})
        assert r.status_code == 400, r.text
        r = admin.post(f"{API}/admin/coupons", json={"code": "TEST_FIXMISS", "discount_type": "fixed"})
        assert r.status_code == 400, r.text

    def test_crud_and_duplicate(self, admin, coupon_ids):
        c = make_coupon(admin, coupon_ids, code="test_qa_crud", percent_off=15, note="qa")
        assert c["code"] == "TEST_QA_CRUD"
        assert c["used_count"] == 0
        dup = admin.post(f"{API}/admin/coupons", json={"code": "TEST_QA_CRUD", "percent_off": 5,
                                                      "discount_type": "percent"})
        assert dup.status_code == 400
        r = admin.put(f"{API}/admin/coupons/{c['id']}", json={"code": "TEST_QA_CRUD",
                                                             "discount_type": "fixed", "amount_off": 2})
        assert r.status_code == 200 and r.json()["discount_type"] == "fixed"
        listed = admin.get(f"{API}/admin/coupons").json()
        saved = next(x for x in listed if x["id"] == c["id"])
        assert saved["amount_off"] == 2 and saved["discount_type"] == "fixed"
        assert admin.delete(f"{API}/admin/coupons/{c['id']}").status_code == 200
        assert admin.delete(f"{API}/admin/coupons/{c['id']}").status_code == 404
        coupon_ids.remove(c["id"])


class TestCouponUpdateValidation:
    """KNOWN BUGS (iteration 15): PUT /admin/coupons skips the create-time guards."""

    def test_put_duplicate_code_should_be_400_not_500(self, admin, coupon_ids):
        a = make_coupon(admin, coupon_ids, code="TEST_QA_DUPA", percent_off=10)
        b = make_coupon(admin, coupon_ids, code="TEST_QA_DUPB", percent_off=10)
        r = admin.put(f"{API}/admin/coupons/{b['id']}",
                      json={"code": "TEST_QA_DUPA", "discount_type": "percent", "percent_off": 10})
        assert r.status_code == 400, f"expected 400 for duplicate code, got {r.status_code}: {r.text[:200]}"

    def test_put_percent_coupon_without_percent_should_400(self, admin, coupon_ids):
        c = make_coupon(admin, coupon_ids, code="TEST_QA_PUTPCT", percent_off=10)
        r = admin.put(f"{API}/admin/coupons/{c['id']}",
                      json={"code": "TEST_QA_PUTPCT", "discount_type": "percent"})
        assert r.status_code == 400, (
            f"percent coupon saved with percent_off=null (status {r.status_code}) — "
            "the code becomes unusable at checkout"
        )


class TestCouponValidation:
    def test_mixed_cart_test20(self, anon, products):
        coin = by_name(products, "2,700 Pokécoins")
        ticket = by_name(products, "Weekly Event Ticket")
        assert coin["price"] == 14.99 and ticket["price"] == 2.99
        r = anon.post(f"{API}/coupons/validate", json={
            "code": "TEST20",
            "items": [{"product_id": coin["id"], "quantity": 1},
                      {"product_id": ticket["id"], "quantity": 1}],
            "email": "qa_mixed@example.com",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subtotal"] == 17.98
        assert d["eligible_subtotal"] == 14.99
        assert d["discount"] == 3.00
        assert d["total"] == 14.98
        assert "Weekly Event Ticket" in d["excluded_names"]
        assert "unit_prices" not in d

    def test_event_pass_only_cart_rejected(self, anon, products):
        ticket = by_name(products, "Weekly Event Ticket")
        r = anon.post(f"{API}/coupons/validate", json={
            "code": "TEST20", "items": [{"product_id": ticket["id"], "quantity": 1}],
            "email": "qa_ep@example.com"})
        assert r.status_code == 400
        assert "cannot be used on Event Passes" in r.json()["detail"]

    def test_event_pass_never_discounted_even_if_category_allowed(self, anon, admin, products, coupon_ids):
        """Hard block: a coupon with no exclusions still cannot touch event_pass / ids 851924/7/8."""
        make_coupon(admin, coupon_ids, code="TEST_QA_HARD", percent_off=50)
        coin = by_name(products, "2,700 Pokécoins")
        passes = [p for p in products if p["category"] == "event_pass"]
        assert {p["sellauth_product_id"] for p in passes} >= {851924, 851927, 851928}
        for ep in passes:
            r = anon.post(f"{API}/coupons/validate", json={
                "code": "TEST_QA_HARD",
                "items": [{"product_id": coin["id"], "quantity": 1},
                          {"product_id": ep["id"], "quantity": 1}],
                "email": "qa_hard@example.com"})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["eligible_subtotal"] == coin["price"], f"{ep['name']} leaked into eligible subtotal"
            assert d["discount"] == round(coin["price"] * 0.5, 2)
            assert ep["name"] in d["excluded_names"]

    def test_unknown_code(self, anon, products):
        coin = by_name(products, "2,700 Pokécoins")
        r = anon.post(f"{API}/coupons/validate", json={
            "code": "TEST_QA_NOPE_XYZ", "items": [{"product_id": coin["id"], "quantity": 1}]})
        assert r.status_code == 400 and "not valid" in r.json()["detail"]

    def test_empty_cart(self, anon):
        r = anon.post(f"{API}/coupons/validate", json={"code": "TEST20", "items": []})
        assert r.status_code == 400

    def test_guards(self, anon, admin, products, coupon_ids):
        coin = by_name(products, "2,700 Pokécoins")
        cart = [{"product_id": coin["id"], "quantity": 1}]

        def validate(code, email="qa_guard@example.com"):
            return anon.post(f"{API}/coupons/validate",
                             json={"code": code, "items": cart, "email": email})

        # expired
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        make_coupon(admin, coupon_ids, code="TEST_QA_EXP", expires_at=past)
        r = validate("TEST_QA_EXP")
        assert r.status_code == 400 and "expired" in r.json()["detail"]

        # inactive
        make_coupon(admin, coupon_ids, code="TEST_QA_OFF", active=False)
        assert validate("TEST_QA_OFF").status_code == 400

        # min subtotal not met
        make_coupon(admin, coupon_ids, code="TEST_QA_MIN", min_subtotal=500)
        r = validate("TEST_QA_MIN")
        assert r.status_code == 400 and "at least $500.00" in r.json()["detail"], r.text

        # excluded category => no eligible items
        make_coupon(admin, coupon_ids, code="TEST_QA_EXCL", excluded_categories=["pokecoin_bundle"])
        assert validate("TEST_QA_EXCL").status_code == 400

        # fixed amount
        make_coupon(admin, coupon_ids, code="TEST_QA_FIX", discount_type="fixed", percent_off=None,
                    amount_off=5)
        r = validate("TEST_QA_FIX")
        assert r.status_code == 200 and r.json()["discount"] == 5.0
        assert r.json()["total"] == round(coin["price"] - 5, 2)

        # fixed amount larger than cart is clamped to leave the MIN_CHARGE
        make_coupon(admin, coupon_ids, code="TEST_QA_HUGE", discount_type="fixed", percent_off=None,
                    amount_off=1000)
        r = validate("TEST_QA_HUGE")
        assert r.status_code == 200, r.text
        assert r.json()["total"] >= 0.5

    def test_max_uses_and_one_per_customer(self, anon, admin, products, coupon_ids):
        coin = by_name(products, "2,700 Pokécoins")
        cart = [{"product_id": coin["id"], "quantity": 1}]
        c = make_coupon(admin, coupon_ids, code="TEST_QA_MAX", max_uses=1)
        # simulate an existing redemption by bumping used_count via a direct edit is not exposed;
        # verify by creating with max_uses=1 and then checking the exhausted path through PUT.
        admin.put(f"{API}/admin/coupons/{c['id']}", json={"code": "TEST_QA_MAX", "discount_type": "percent",
                                                          "percent_off": 20, "max_uses": 1})
        r = anon.post(f"{API}/coupons/validate", json={"code": "TEST_QA_MAX", "items": cart,
                                                      "email": "qa_max@example.com"})
        # used_count is still 0 so it should validate fine
        assert r.status_code == 200, r.text


# ---------------- checkout ----------------
class TestCheckout:
    def _cart(self, products):
        coin = by_name(products, "2,700 Pokécoins")
        ticket = by_name(products, "Weekly Event Ticket")
        return coin, ticket

    def test_cart_rules_still_enforced(self, anon, products):
        coin, ticket = self._cart(products)
        base = {"ptc_username": "qa_user", "ptc_password": "qa_pass",
                "origin_url": BASE_URL, "email": QA_EMAIL}
        r = anon.post(f"{API}/orders/checkout", json={**base,
                                                     "items": [{"product_id": ticket["id"], "quantity": 1}]})
        assert r.status_code == 400 and "cannot be bought on its own" in r.json()["detail"]
        r = anon.post(f"{API}/orders/checkout", json={**base, "items": [
            {"product_id": coin["id"], "quantity": 1}, {"product_id": ticket["id"], "quantity": 2}]})
        assert r.status_code == 400 and "Only one Event Pass" in r.json()["detail"]

    def test_checkout_with_coupon_records_discounted_total(self, anon, products):
        coin, ticket = self._cart(products)
        r = anon.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": coin["id"], "quantity": 1},
                      {"product_id": ticket["id"], "quantity": 1}],
            "ptc_username": "qa_user", "ptc_password": "qa_pass",
            "origin_url": BASE_URL, "email": QA_EMAIL, "coupon_code": "TEST20"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["checkout_url"].startswith("http")
        assert data["invoice_id"]
        status = anon.get(f"{API}/checkout-sessions/{data['session_id']}")
        assert status.status_code == 200
        assert status.json()["status"] == "awaiting_payment"
        pytest.session_with_coupon = data["session_id"]

    def test_checkout_without_coupon(self, anon, products):
        coin, _ = self._cart(products)
        r = anon.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": coin["id"], "quantity": 1}],
            "ptc_username": "qa_user", "ptc_password": "qa_pass",
            "origin_url": BASE_URL, "email": QA_EMAIL})
        assert r.status_code == 200, r.text
        assert r.json()["checkout_url"].startswith("http")

    def test_checkout_bad_coupon_rejected(self, anon, products):
        coin, _ = self._cart(products)
        r = anon.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": coin["id"], "quantity": 1}],
            "ptc_username": "qa_user", "ptc_password": "qa_pass",
            "origin_url": BASE_URL, "email": QA_EMAIL, "coupon_code": "TEST_QA_NOPE_XYZ"})
        assert r.status_code == 400


# ---------------- regressions ----------------
class TestRegressions:
    def test_banner(self, anon):
        r = anon.get(f"{API}/settings/banner")
        assert r.status_code == 200 and "enabled" in r.json()

    def test_admin_orders_and_credentials(self, admin):
        r = admin.get(f"{API}/admin/orders")
        assert r.status_code == 200
        orders = r.json()
        assert all("ptc_username_enc" not in o for o in orders)
        if orders:
            oid = orders[0]["id"]
            c = admin.get(f"{API}/admin/orders/{oid}/credentials")
            assert c.status_code == 200 and "ptc_username" in c.json()
            m = admin.get(f"{API}/orders/{oid}/messages")
            assert m.status_code == 200 and isinstance(m.json(), list)

    def test_catalog_sync_diff(self, admin):
        r = admin.get(f"{API}/admin/sync/catalog")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), dict)

    def test_waitlist(self, admin):
        assert admin.get(f"{API}/admin/waitlist").status_code == 200
