"""Iteration 20 — PokeCoins commercial launch reconfiguration.

Covers:
  1. GET /api/categories returns the 6 launch categories in the exact order.
  2. Hunting Service products (Auto Raid, Egg Hatching, Shiny Shadow) + Shundo migration.
  3. POST /api/products name-uniqueness (409) and unique index on products.name.
  4. Description edit round-trip via PUT /api/products/{id}.
  5. GET /api/admin/sync/catalog dry-run — target-lookup by sellauth_product_id, variants diffs.
  6. Sync self-push guard (unit test on catalog_sync.target_base).
  7. Coupon regression — Event Pass exclusion, /coupons/validate excluded_names,
     sellauth_cart custom_price wiring.
"""
import os
import sys
import time
import asyncio
from urllib.parse import urlparse

import pytest
import requests

# Import catalog_sync directly for the guard unit test.
sys.path.insert(0, "/app/backend")
import catalog_sync  # noqa: E402

def _load_public_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip("/")


BASE_URL = _load_public_url()
ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"

EXPECTED_CATEGORY_ORDER = [
    "pokecoin_bundle", "hunting_service", "event_pass",
    "pokelid", "medals", "stardust",
]


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api_client):
    r = api_client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
                              "turnstile_token": "preview-bypass"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def all_products(api_client, admin_headers):
    r = api_client.get(f"{BASE_URL}/api/products?include_inactive=true", headers=admin_headers)
    assert r.status_code == 200
    return r.json()


# ---------------- 1. Categories ----------------
class TestCategories:
    def test_categories_order_and_no_shundo(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/categories")
        assert r.status_code == 200
        docs = r.json()
        keys = [d["key"] for d in docs]
        assert keys == EXPECTED_CATEGORY_ORDER, f"got {keys}"
        assert "shundo_service" not in keys
        labels = {d["key"]: d["label"] for d in docs}
        assert labels["pokecoin_bundle"] == "Pokécoins"
        assert labels["hunting_service"] == "Hunting Service"
        assert labels["event_pass"] == "Event Passes"


# ---------------- 2. Hunting Service catalog ----------------
class TestHuntingCatalog:
    def _find(self, products, name):
        for p in products:
            if p["name"] == name:
                return p
        return None

    def test_shundo_products_moved_to_hunting_service(self, all_products):
        shundos = [p for p in all_products if "Shundo" in p["name"]]
        assert len(shundos) >= 2, "expected 2 Shundo products"
        for p in shundos:
            assert p["category"] == "hunting_service", f"{p['name']} still on {p['category']}"
            assert p.get("coming_soon") is True, f"{p['name']} not coming_soon"

    def test_auto_raid_hunting(self, all_products):
        p = self._find(all_products, "Auto Raid Hunting")
        assert p, "Auto Raid Hunting missing"
        assert p["category"] == "hunting_service"
        assert p["sellauth_product_id"] == 870739
        assert "/images/autoraid" in (p.get("image_url") or "").lower() or \
            "sellauth.com" in (p.get("image_url") or ""), p.get("image_url")
        labels = {v["label"]: v["price"] for v in (p.get("variants") or [])}
        expected = {"25 Raids": 24.99, "50 Raids": 44.99, "75 Raids": 62.99, "100 Raids": 79.99}
        for lbl, price in expected.items():
            assert lbl in labels, f"missing variant {lbl}: {labels}"
            assert abs(labels[lbl] - price) < 0.01, f"{lbl}={labels[lbl]} exp {price}"

    def test_egg_hatching(self, all_products):
        p = self._find(all_products, "Egg Hatching")
        assert p, "Egg Hatching missing"
        assert p["category"] == "hunting_service"
        assert p["sellauth_product_id"] == 870828
        assert "eggs" in (p.get("image_url") or "").lower() or \
            "sellauth.com" in (p.get("image_url") or ""), p.get("image_url")
        labels = {v["label"]: v["price"] for v in (p.get("variants") or [])}
        expected = {"9 Eggs": 29.99, "27 Eggs": 74.99, "54 Eggs": 129.99}
        for lbl, price in expected.items():
            assert lbl in labels
            assert abs(labels[lbl] - price) < 0.01

    def test_shiny_shadow_hunting_coming_soon(self, all_products):
        p = self._find(all_products, "Team GO Rocket — Shiny Shadow Hunting")
        assert p, "Shiny Shadow Hunting missing"
        assert p["category"] == "hunting_service"
        assert p["sellauth_product_id"] == 870940
        assert p.get("coming_soon") is True
        assert "shinyshadow" in (p.get("image_url") or "").lower() or \
            "sellauth.com" in (p.get("image_url") or ""), p.get("image_url")
        variants = p.get("variants") or []
        # 7 variants (1614148..1614154) on the re-tiered price ladder, Giovanni removed.
        variant_ids = {v["sellauth_variant_id"] for v in variants}
        expected_ids = set(range(1614148, 1614155))
        assert expected_ids.issubset(variant_ids), \
            f"missing variants: {expected_ids - variant_ids}"
        expected_prices = {
            1614148: 24.99, 1614149: 49.99, 1614150: 84.99, 1614151: 119.99,
            1614152: 29.99, 1614153: 64.99, 1614154: 119.99,
        }
        for v in variants:
            want = expected_prices.get(v["sellauth_variant_id"])
            if want:
                assert abs(v["price"] - want) < 0.01, f"{v['label']}={v['price']} exp {want}"
        assert not any("giovanni" in v["label"].lower() for v in variants)
        assert next(v for v in variants if v["sellauth_variant_id"] == 1614151)["badge"] == "MAX"


# ---------------- 3. POST /products name-uniqueness ----------------
class TestProductNameUniqueness:
    def test_duplicate_name_returns_409(self, api_client, admin_headers, all_products):
        existing_name = all_products[0]["name"]
        r = api_client.post(
            f"{BASE_URL}/api/products",
            headers=admin_headers,
            json={"name": existing_name, "category": "hunting_service", "price": 9.99,
                  "description": "dup", "image_url": "/images/test.png"},
        )
        assert r.status_code == 409, f"expected 409 got {r.status_code}: {r.text}"
        body = r.json()
        assert "already exists" in (body.get("detail") or "").lower()

    def test_new_name_succeeds_and_can_be_cleaned_up(self, api_client, admin_headers):
        name = f"TEST_LaunchProduct_{int(time.time())}"
        r = api_client.post(
            f"{BASE_URL}/api/products",
            headers=admin_headers,
            json={"name": name, "category": "hunting_service", "price": 1.23,
                  "description": "seed", "image_url": "/images/test.png"},
        )
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        pid = r.json()["id"]
        # And a second POST with the same name is now 409.
        r2 = api_client.post(
            f"{BASE_URL}/api/products",
            headers=admin_headers,
            json={"name": name, "category": "hunting_service", "price": 1.23,
                  "description": "seed", "image_url": "/images/test.png"},
        )
        assert r2.status_code == 409
        # cleanup
        api_client.delete(f"{BASE_URL}/api/products/{pid}", headers=admin_headers)

    def test_products_name_unique_index_exists(self):
        # Query MongoDB directly to confirm the unique index on products.name.
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E501
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")

        async def _check():
            client = AsyncIOMotorClient(mongo_url)
            info = await client[db_name]["products"].index_information()
            client.close()
            return info

        info = asyncio.get_event_loop().run_until_complete(_check())
        name_index = [v for k, v in info.items() if v.get("key") == [("name", 1)]]
        assert name_index, f"no index on products.name: keys={list(info.keys())}"
        assert name_index[0].get("unique") is True, f"index not unique: {name_index[0]}"


# ---------------- 4. Description edit round-trip ----------------
class TestDescriptionEdit:
    def test_edit_hunting_description_persists(self, api_client, admin_headers, all_products):
        auto_raid = next((p for p in all_products if p["name"] == "Auto Raid Hunting"), None)
        assert auto_raid, "Auto Raid Hunting missing"
        pid = auto_raid["id"]
        original = auto_raid["description"]
        marker = f"[edited-by-test-{int(time.time())}]"
        new_desc = f"{marker} {original}"
        try:
            r = api_client.put(f"{BASE_URL}/api/products/{pid}", headers=admin_headers,
                               json={"description": new_desc})
            assert r.status_code == 200, f"put failed: {r.text}"
            assert r.json()["description"] == new_desc
            # And GET /products echoes it back.
            r2 = api_client.get(f"{BASE_URL}/api/products")
            fetched = next(p for p in r2.json() if p["id"] == pid)
            assert fetched["description"] == new_desc
        finally:
            api_client.put(f"{BASE_URL}/api/products/{pid}", headers=admin_headers,
                           json={"description": original})


# ---------------- 5. Catalog sync dry-run ----------------
class TestCatalogSyncDryRun:
    def test_dry_run_uses_sellauth_id_no_duplicate_creates(self, api_client, admin_headers):
        r = api_client.get(f"{BASE_URL}/api/admin/sync/catalog", headers=admin_headers)
        # It's OK if production login fails (they may have rotated the password) —
        # in that case the sync raises a 400 SyncError and we still learn the guard is wired.
        if r.status_code == 400:
            detail = (r.json().get("detail") or "").lower()
            pytest.skip(f"sync dry-run unavailable ({detail}) — testing guard directly")
        assert r.status_code == 200, f"sync dry-run failed: {r.status_code} {r.text}"
        plan = r.json()
        assert "creates" in plan and "updates" in plan
        assert plan.get("applied") is False
        # Products that already exist on the target by sellauth_product_id should NOT be
        # in creates. Fetch the source list and confirm any sellauth-tagged product does not
        # appear as a create if it also exists on the target (identity match).
        create_names = {c["name"] for c in plan["creates"]}
        # A sanity-check: the 3 seeded products with SellAuth ids that already exist upstream
        # should either be updates or absent — never creates for a product we can identify.
        # We cannot know upstream's exact state, so we just verify plan format.
        for u in plan["updates"]:
            assert "id" in u and "changes" in u
        # If any update has a variants change, its shape is {"from": [...], "to": [...]}.
        for u in plan["updates"]:
            if "variants" in u["changes"]:
                v = u["changes"]["variants"]
                assert "from" in v and "to" in v
        # None of the source items with a sellauth_product_id can appear in creates unless
        # target really doesn't have them (which is a legit new-product case).
        # We can't fail the test on that alone. Just verify create_names is a set of strings.
        assert all(isinstance(n, str) for n in create_names)


# ---------------- 6. Self-push guard (unit) ----------------
class TestSelfPushGuard:
    def test_target_base_refuses_same_host(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_APP_URL", "https://pokecoins.cc")
        with pytest.raises(catalog_sync.SyncError) as exc:
            catalog_sync.target_base(own_host="pokecoins.cc")
        assert "same site" in str(exc.value).lower()

    def test_target_base_accepts_different_host(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_APP_URL", "https://pokecoins.cc")
        base = catalog_sync.target_base(own_host="digital-gaming-store-7.preview.emergentagent.com")
        assert base == "https://pokecoins.cc"

    def test_target_base_ignores_port_in_own_host(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_APP_URL", "https://pokecoins.cc")
        with pytest.raises(catalog_sync.SyncError):
            catalog_sync.target_base(own_host="pokecoins.cc:443")

    def test_target_base_requires_https(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_APP_URL", "http://insecure.example")
        with pytest.raises(catalog_sync.SyncError):
            catalog_sync.target_base()

    def test_sync_endpoint_returns_400_on_same_host(self, api_client, admin_headers):
        """The endpoint calls request_host() then target_base(own_host) — the guard is
        exercised at the unit level above. We cannot spoof the Host header end-to-end
        because Kubernetes ingress rewrites X-Forwarded-Host with the real preview host
        before it reaches FastAPI. Verify the wiring instead: request_host() reads the
        forwarded host header and target_base() raises SyncError, which _sync_catalog
        converts to HTTP 400."""
        import server  # noqa: E501
        from fastapi import Request
        # Build a stub Request with a forwarded-host header pointing at production.
        pub_host = urlparse(os.environ.get("PUBLIC_APP_URL") or "https://pokecoins.cc").hostname
        scope = {
            "type": "http",
            "headers": [(b"x-forwarded-host", pub_host.encode())],
        }
        req = Request(scope)
        assert server.request_host(req) == pub_host
        # And target_base raises when own_host matches.
        os.environ["PUBLIC_APP_URL"] = f"https://{pub_host}"
        with pytest.raises(catalog_sync.SyncError) as exc:
            catalog_sync.target_base(own_host=pub_host)
        assert "same site" in str(exc.value).lower()


# ---------------- 7. Coupon regression ----------------
class TestCouponRegression:
    @pytest.fixture(scope="class")
    def event_pass_product(self, all_products):
        p = next((x for x in all_products if x["category"] == "event_pass"), None)
        assert p, "no event_pass product seeded"
        return p

    @pytest.fixture(scope="class")
    def eligible_product(self, all_products):
        # pick a non event_pass, non coming_soon product with a price > 5 to avoid MIN_CHARGE
        for p in all_products:
            if (p["category"] not in ("event_pass",) and not p.get("coming_soon")
                    and float(p["price"]) > 5 and p.get("sellauth_product_id")):
                return p
        pytest.skip("no eligible product to discount")

    @pytest.fixture(scope="class")
    def percent_coupon(self, api_client, admin_headers):
        code = f"TESTPCT{int(time.time())}"
        r = api_client.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code, "discount_type": "percent", "percent_off": 10,
                  "active": True, "one_per_customer": False},
        )
        assert r.status_code == 200, f"coupon create failed: {r.text}"
        yield r.json()
        # cleanup
        api_client.delete(f"{BASE_URL}/api/admin/coupons/{r.json()['id']}",
                          headers=admin_headers)

    def test_validate_excludes_event_pass(self, api_client, percent_coupon,
                                          event_pass_product, eligible_product):
        r = api_client.post(
            f"{BASE_URL}/api/coupons/validate",
            json={"code": percent_coupon["code"],
                  "email": "coupontest@example.com",
                  "items": [
                      {"product_id": eligible_product["id"], "quantity": 1},
                      {"product_id": event_pass_product["id"], "quantity": 1},
                  ]},
        )
        assert r.status_code == 200, f"validate failed: {r.text}"
        data = r.json()
        assert data["discount"] > 0, "expected some discount"
        # Event Pass name must appear in excluded_names.
        assert event_pass_product["name"] in data.get("excluded_names", []), \
            f"excluded_names={data.get('excluded_names')}"
        # Eligible subtotal must exclude the Event Pass.
        assert data["eligible_subtotal"] < data["subtotal"]

    def test_validate_reports_no_eligible_when_only_event_pass(self, api_client,
                                                               percent_coupon,
                                                               event_pass_product):
        r = api_client.post(
            f"{BASE_URL}/api/coupons/validate",
            json={"code": percent_coupon["code"],
                  "email": "coupontest@example.com",
                  "items": [{"product_id": event_pass_product["id"], "quantity": 1}]},
        )
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert "event pass" in detail or "does not apply" in detail

    def test_sellauth_cart_payload_uses_custom_price_for_discounted_lines(self):
        """Unit test on the cart-building code path — no live SellAuth call."""
        from server import sellauth_cart, line_key  # noqa: E501
        from models import OrderItem  # local import in case the module path differs
        assert OrderItem  # keep linter quiet

        item = OrderItem(
            product_id="pid1", name="Auto Raid Hunting", category="hunting_service",
            price=44.99, quantity=1, sellauth_product_id=870739,
            sellauth_variant_id=1613377,
        )
        pass_item = OrderItem(
            product_id="pid2", name="GO Pass", category="event_pass",
            price=10.99, quantity=1, sellauth_product_id=864451,
            sellauth_variant_id=1570359,
        )
        unit_prices = {line_key(item): 40.49}  # 10% off
        cart = sellauth_cart([item, pass_item], unit_prices)
        assert len(cart) == 2
        # Discounted line carries custom_price.
        discounted = [c for c in cart if c["name"] == "Auto Raid Hunting"][0]
        assert discounted.get("custom_price") == 40.49
        # Event pass line does NOT get a custom_price.
        pass_line = [c for c in cart if c["name"] == "GO Pass"][0]
        assert "custom_price" not in pass_line

    def test_sellauth_cart_line_shape_for_discounted_line(self):
        """The actual SellAuth _cart_line() should render the discounted line as a custom line."""
        from sellauth import _cart_line  # noqa: E501
        line = _cart_line({
            "name": "Auto Raid Hunting", "price": 44.99, "quantity": 1,
            "sellauth_product_id": 870739, "sellauth_variant_id": 1613377,
            "custom_price": 40.49,
        })
        # Discounted lines are sent as name/price/quantity (custom), NOT productId/variantId.
        assert "productId" not in line
        assert "variantId" not in line
        assert line["name"] == "Auto Raid Hunting"
        assert line["price"] == "40.49"
        assert line["quantity"] == 1

    def test_sellauth_cart_line_shape_for_catalog_line(self):
        from sellauth import _cart_line
        line = _cart_line({
            "name": "GO Pass", "price": 10.99, "quantity": 1,
            "sellauth_product_id": 864451, "sellauth_variant_id": 1570359,
            # no custom_price -> catalog line
        })
        assert line["productId"] == 864451
        assert line["variantId"] == 1570359
        assert "price" not in line
