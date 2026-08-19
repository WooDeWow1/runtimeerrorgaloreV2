"""Iteration 12 backend tests.

Covers:
  * PUT /api/products/{id} partial update (ProductUpdate + exclude_unset) preserves is_featured
  * PUT invalid category -> 400, unknown id -> 404, non-admin -> 401/403
  * GET /api/products?include_inactive=true admin gating (anon/customer 403, admin 200 superset)
All mutated products are restored in teardown.
"""
import os
import uuid

import pytest
import requests

BASE_URL = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "officialwifi@icloud.com")
ADMIN_PASSWORD = "admin"

PRODUCT_FIELDS = ["name", "description", "category", "price", "msrp", "image_url",
                  "coins", "badge", "active", "coming_soon", "is_featured"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def customer_token():
    email = f"TEST_it12_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Password123", "name": "TEST Customer"})
    assert r.status_code in (200, 201), r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def all_products(admin_token):
    r = requests.get(f"{API}/products", params={"include_inactive": "true"}, headers=auth(admin_token))
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def restore(admin_token):
    saved = []

    def remember(product):
        saved.append((product["id"], {k: product.get(k) for k in PRODUCT_FIELDS}))

    yield remember

    for pid, body in saved:
        r = requests.put(f"{API}/products/{pid}", json=body, headers=auth(admin_token))
        assert r.status_code == 200, f"restore failed {pid}: {r.status_code} {r.text}"


# ---------- PUT partial update ----------
class TestPartialUpdate:
    def test_partial_coming_soon_only_preserves_all_other_fields(self, all_products, admin_token, restore):
        target = next(p for p in all_products
                      if p.get("is_featured") and p["active"] and not p.get("coming_soon"))
        restore(target)

        r = requests.put(f"{API}/products/{target['id']}", json={"coming_soon": True},
                         headers=auth(admin_token))
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["coming_soon"] is True
        assert updated["is_featured"] is True, "partial PUT wiped is_featured"
        assert updated["active"] is True
        assert updated["name"] == target["name"]
        assert updated["price"] == target["price"]
        assert updated["category"] == target["category"]
        assert updated["description"] == target["description"]

        # verify persistence via GET
        pub = requests.get(f"{API}/products").json()
        found = next(p for p in pub if p["id"] == target["id"])
        assert found["coming_soon"] is True and found["is_featured"] is True

    def test_full_form_save_roundtrips_star(self, all_products, admin_token, restore):
        """Mimics the admin edit form which now sends is_featured with the full body."""
        target = next(p for p in all_products if p.get("is_featured") and p["active"])
        restore(target)
        body = {k: target.get(k) for k in PRODUCT_FIELDS}
        body["coming_soon"] = True
        r = requests.put(f"{API}/products/{target['id']}", json=body, headers=auth(admin_token))
        assert r.status_code == 200, r.text
        assert r.json()["is_featured"] is True
        assert r.json()["coming_soon"] is True

    def test_empty_body_is_noop(self, all_products, admin_token):
        target = all_products[0]
        r = requests.put(f"{API}/products/{target['id']}", json={}, headers=auth(admin_token))
        assert r.status_code == 200, r.text
        for field in PRODUCT_FIELDS:
            assert r.json()[field] == target.get(field), f"{field} changed on empty PUT"

    def test_invalid_category_400(self, all_products, admin_token):
        target = all_products[0]
        r = requests.put(f"{API}/products/{target['id']}", json={"category": "not_a_category"},
                         headers=auth(admin_token))
        assert r.status_code == 400, f"{r.status_code} {r.text}"
        after = requests.get(f"{API}/products", params={"include_inactive": "true"},
                             headers=auth(admin_token)).json()
        found = next(p for p in after if p["id"] == target["id"])
        assert found["category"] == target["category"], "category mutated despite 400"

    def test_unknown_id_404(self, admin_token):
        r = requests.put(f"{API}/products/{'a' * 24}", json={"coming_soon": True},
                         headers=auth(admin_token))
        assert r.status_code == 404, f"{r.status_code} {r.text}"

    def test_non_admin_cannot_update(self, all_products, customer_token):
        target = all_products[0]
        r = requests.put(f"{API}/products/{target['id']}", json={"coming_soon": True},
                         headers=auth(customer_token))
        assert r.status_code in (401, 403), r.status_code


# ---------- include_inactive gating ----------
class TestIncludeInactiveGating:
    def test_anonymous_403(self):
        r = requests.get(f"{API}/products", params={"include_inactive": "true"})
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_customer_403(self, customer_token):
        r = requests.get(f"{API}/products", params={"include_inactive": "true"},
                         headers=auth(customer_token))
        assert r.status_code == 403, f"{r.status_code} {r.text}"

    def test_admin_gets_superset(self, admin_token, all_products, restore):
        # pick a target no other test class touches (avoids xdist cross-worker races)
        target = next(p for p in all_products
                      if p["active"] and not p.get("is_featured") and not p.get("coming_soon"))
        restore(target)
        r = requests.put(f"{API}/products/{target['id']}", json={"active": False},
                         headers=auth(admin_token))
        assert r.status_code == 200

        pub_ids = {p["id"] for p in requests.get(f"{API}/products").json()}
        assert target["id"] not in pub_ids

        admin_list = requests.get(f"{API}/products", params={"include_inactive": "true"},
                                  headers=auth(admin_token))
        assert admin_list.status_code == 200
        admin_ids = {p["id"] for p in admin_list.json()}
        assert target["id"] in admin_ids
        assert pub_ids.issubset(admin_ids)
        assert all("_id" not in p for p in admin_list.json())

    def test_public_list_unaffected_without_param(self):
        r = requests.get(f"{API}/products")
        assert r.status_code == 200
        assert all(p["active"] is True for p in r.json())
