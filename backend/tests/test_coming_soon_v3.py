"""Iteration 11 backend tests — Coming Soon / Active visibility rules.

Covers:
  * GET /api/products  -> active filter, include_inactive param, coming_soon exposed
  * PUT /api/products/{id} -> active / coming_soon / is_featured persistence
  * POST /api/orders/checkout -> 400 guard for coming_soon products
  * No _id leakage in product payloads
Every product mutated by these tests is restored to its original state in teardown.
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

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

CHECKOUT_CREDS = {
    "ptc_username": "qa_ptc_user",
    "ptc_password": "qa_ptc_pass",
    "origin_url": BASE_URL,
}

PRODUCT_FIELDS = ["name", "description", "category", "price", "msrp", "image_url",
                  "coins", "badge", "active", "coming_soon", "is_featured"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def payload_of(p):
    return {k: p.get(k) for k in PRODUCT_FIELDS}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def all_products(admin_token):
    r = requests.get(f"{API}/products", params={"include_inactive": "true"}, headers=auth(admin_token))
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def restorer(admin_token):
    """Yields a helper that PUTs updates and restores originals afterwards."""
    originals = {}

    def update(product, **changes):
        originals.setdefault(product["id"], payload_of(product))
        body = dict(payload_of(product))
        body.update(changes)
        r = requests.put(f"{API}/products/{product['id']}", json=body, headers=auth(admin_token))
        assert r.status_code == 200, f"update failed {r.status_code} {r.text}"
        return r.json()

    yield update

    for pid, body in originals.items():
        r = requests.put(f"{API}/products/{pid}", json=body, headers=auth(admin_token))
        assert r.status_code == 200, f"restore failed for {pid}: {r.status_code} {r.text}"


# ---------------- GET /api/products ----------------
class TestProductListing:
    def test_public_list_returns_active_only_and_includes_coming_soon(self, all_products):
        r = requests.get(f"{API}/products")
        assert r.status_code == 200
        pub = r.json()
        assert len(pub) > 0
        assert all(p["active"] is True for p in pub), "inactive product leaked into public list"
        assert all("_id" not in p and "id" in p for p in pub), "_id leaked"
        assert all("coming_soon" in p for p in pub)
        # seeded shundo services are coming_soon and must still be listed publicly
        cs = [p for p in pub if p.get("coming_soon")]
        assert len(cs) >= 1, "no coming_soon product visible on the public list"

    def test_include_inactive_requires_nothing_but_returns_superset(self, all_products):
        pub = requests.get(f"{API}/products").json()
        assert len(all_products) >= len(pub)
        pub_ids = {p["id"] for p in pub}
        assert pub_ids.issubset({p["id"] for p in all_products})

    def test_sorted_by_price_ascending(self):
        prices = [p["price"] for p in requests.get(f"{API}/products").json()]
        assert prices == sorted(prices)


# ---------------- Admin toggles ----------------
class TestVisibilityToggles:
    def test_coming_soon_product_stays_in_public_list(self, all_products, restorer):
        target = next(p for p in all_products
                      if p["category"] == "stardust" and not p.get("coming_soon") and p["active"])
        updated = restorer(target, coming_soon=True)
        assert updated["coming_soon"] is True
        assert updated["active"] is True

        pub = requests.get(f"{API}/products").json()
        found = next((p for p in pub if p["id"] == target["id"]), None)
        assert found is not None, "coming_soon product disappeared from the storefront list"
        assert found["coming_soon"] is True

    def test_inactive_product_hidden_publicly_but_visible_with_include_inactive(
        self, all_products, restorer, admin_token
    ):
        target = next(p for p in all_products
                      if p["category"] == "medals" and p["active"])
        restorer(target, active=False)

        pub = requests.get(f"{API}/products").json()
        assert target["id"] not in {p["id"] for p in pub}, "inactive product still on storefront"

        admin_list = requests.get(f"{API}/products", params={"include_inactive": "true"},
                                  headers=auth(admin_token)).json()
        found = next((p for p in admin_list if p["id"] == target["id"]), None)
        assert found is not None, "inactive product missing from admin list"
        assert found["active"] is False

    def test_featured_coming_soon_persists(self, all_products, restorer):
        target = next(p for p in all_products if p["category"] == "shundo_service")
        updated = restorer(target, coming_soon=True, is_featured=True, active=True)
        assert updated["coming_soon"] is True and updated["is_featured"] is True
        pub = requests.get(f"{API}/products").json()
        found = next(p for p in pub if p["id"] == target["id"])
        assert found["is_featured"] is True and found["coming_soon"] is True

    def test_toggle_featured_endpoint(self, all_products, admin_token):
        target = next(p for p in all_products if p["category"] == "shundo_service")
        original = bool(target.get("is_featured"))
        try:
            r = requests.patch(f"{API}/products/{target['id']}/featured",
                               json={"is_featured": not original}, headers=auth(admin_token))
            assert r.status_code == 200
            assert r.json()["is_featured"] is (not original)
            # coming_soon untouched
            assert r.json()["coming_soon"] == bool(target.get("coming_soon"))
        finally:
            requests.patch(f"{API}/products/{target['id']}/featured",
                           json={"is_featured": original}, headers=auth(admin_token))

    def test_update_requires_admin(self, all_products):
        target = all_products[0]
        r = requests.put(f"{API}/products/{target['id']}", json=payload_of(target))
        assert r.status_code in (401, 403), r.status_code


# ---------------- Regression: featured flag must survive an edit ----------------
class TestFeaturedPreservedOnUpdate:
    """DEFECT (iteration 11): the admin product form (Admin.jsx editProduct/saveProduct) does not
    carry is_featured, and ProductIn defaults it to False, so every PUT silently un-stars the
    product -> a starred Coming Soon product disappears from the Home page after any edit."""

    def test_put_without_is_featured_keeps_star(self, all_products, admin_token):
        target = next(p for p in all_products if p.get("is_featured") and p["active"])
        body = {k: target.get(k) for k in PRODUCT_FIELDS if k != "is_featured"}  # mimics the admin form
        try:
            r = requests.put(f"{API}/products/{target['id']}", json=body, headers=auth(admin_token))
            assert r.status_code == 200, r.text
            assert r.json()["is_featured"] is True, (
                "PUT /api/products/{id} without is_featured wiped the featured flag"
            )
        finally:
            requests.patch(f"{API}/products/{target['id']}/featured",
                           json={"is_featured": True}, headers=auth(admin_token))


# ---------------- Checkout guard ----------------
class TestCheckoutComingSoonGuard:
    def test_coming_soon_product_rejected(self, all_products):
        cs = next(p for p in all_products if p.get("coming_soon") and p["active"])
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": cs["id"], "quantity": 1}],
            "email": "qa_comingsoon@example.com",
            **CHECKOUT_CREDS,
        })
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        assert "not available yet" in r.json().get("detail", "").lower()

    def test_coming_soon_mixed_with_valid_product_rejected(self, all_products):
        cs = next(p for p in all_products if p.get("coming_soon") and p["active"])
        ok = next(p for p in all_products
                  if p["category"] == "pokecoin_bundle" and p["active"] and not p.get("coming_soon"))
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": ok["id"], "quantity": 1},
                      {"product_id": cs["id"], "quantity": 1}],
            "email": "qa_comingsoon@example.com",
            **CHECKOUT_CREDS,
        })
        assert r.status_code == 400
        assert "not available yet" in r.json().get("detail", "").lower()

    def test_newly_flagged_coming_soon_product_rejected(self, all_products, restorer):
        target = next(p for p in all_products
                      if p["category"] == "stardust" and not p.get("coming_soon") and p["active"])
        restorer(target, coming_soon=True)
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": target["id"], "quantity": 1}],
            "email": "qa_comingsoon@example.com",
            **CHECKOUT_CREDS,
        })
        assert r.status_code == 400
        assert "not available yet" in r.json().get("detail", "").lower()

    def test_inactive_product_rejected(self, all_products, restorer):
        target = next(p for p in all_products
                      if p["category"] == "stardust" and p["active"] and not p.get("coming_soon"))
        restorer(target, active=False)
        r = requests.post(f"{API}/orders/checkout", json={
            "items": [{"product_id": target["id"], "quantity": 1}],
            "email": "qa_comingsoon@example.com",
            **CHECKOUT_CREDS,
        })
        assert r.status_code == 400
        assert "unavailable" in r.json().get("detail", "").lower()


# ---------------- Waitlist ----------------
class TestWaitlist:
    def test_join_waitlist_for_coming_soon_product(self, all_products, admin_token):
        cs = next(p for p in all_products if p.get("coming_soon"))
        email = "qa_waitlist_v3@example.com"
        r = requests.post(f"{API}/waitlist", json={"email": email, "product_id": cs["id"]})
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        rows = requests.get(f"{API}/admin/waitlist", headers=auth(admin_token))
        assert rows.status_code == 200
        entries = rows.json()
        mine = [e for e in entries if e.get("email") == email]
        assert mine, "waitlist entry not persisted"
        assert mine[0].get("product_id") == cs["id"]
        assert all("_id" not in e for e in entries)
