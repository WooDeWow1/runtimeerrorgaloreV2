"""Vault (Backup Vault) security & functionality tests — iteration 25.

Covers:
- Auth gating: 401 guest, 403 customer, 403 admin+wrong phrase, 200 admin+phrase.
- Phrase never echoed in responses/headers; frontend bundle has no phrase.
- Rate limiter: successful unlock clears failures; 5 fails → 429; unrelated endpoints still work.
- /unlock returns per-collection counts.
- /code-map returns markdown + attachment header, skips node_modules/__pycache__/build/.git.
- /export returns JSON with all collections except 'visits', parses cleanly, ObjectIds as strings.
"""
import io
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
VAULT_PHRASE = os.environ["VAULT_PHRASE"]  # never printed/logged
ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    assert r.json()["user"]["role"] == "admin"
    return s


@pytest.fixture(scope="module")
def customer_session():
    s = requests.Session()
    email = f"TEST_vault_cust_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "password123", "name": "Vault Cust"},
               timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def guest_session():
    return requests.Session()


# ---------- Security / auth gating ----------
class TestVaultAuthGating:
    def test_unlock_guest_401(self, guest_session):
        r = guest_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                               json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 401, r.text

    def test_code_map_guest_401(self, guest_session):
        r = guest_session.post(f"{BASE_URL}/api/admin/vault/code-map",
                               json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 401

    def test_export_guest_401(self, guest_session):
        r = guest_session.post(f"{BASE_URL}/api/admin/vault/export",
                               json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 401

    def test_unlock_customer_403_even_with_correct_phrase(self, customer_session):
        r = customer_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                  json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 403, r.text

    def test_code_map_customer_forbidden(self, customer_session):
        r = customer_session.post(f"{BASE_URL}/api/admin/vault/code-map",
                                  json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 403

    def test_export_customer_forbidden(self, customer_session):
        r = customer_session.post(f"{BASE_URL}/api/admin/vault/export",
                                  json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 403

    def test_admin_wrong_phrase_403_generic_message(self, admin_session):
        r1 = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                json={"phrase": "totally-wrong-guess-abc"}, timeout=15)
        assert r1.status_code == 403
        near = VAULT_PHRASE[:-1] + ("Z" if VAULT_PHRASE[-1] != "Z" else "A")
        r2 = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                json={"phrase": near}, timeout=15)
        assert r2.status_code == 403
        # Same generic body — must not leak "close" info.
        assert r1.json() == r2.json(), "response varies by guess (info leak)"
        body = r1.text.lower()
        assert "close" not in body and "almost" not in body

    def test_admin_empty_phrase_rejected(self, admin_session):
        # Pydantic min_length=1 → 422
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                               json={"phrase": ""}, timeout=15)
        assert r.status_code in (403, 422)


# ---------- Unlock success path ----------
class TestVaultUnlock:
    def test_unlock_admin_correct(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                               json={"phrase": VAULT_PHRASE}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("collections"), dict)
        assert len(data["collections"]) > 0
        for name, count in data["collections"].items():
            assert isinstance(name, str)
            assert isinstance(count, int) and count >= 0

    def test_unlock_response_does_not_leak_phrase(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                               json={"phrase": VAULT_PHRASE}, timeout=15)
        assert VAULT_PHRASE not in r.text
        for _, v in r.headers.items():
            assert VAULT_PHRASE not in v


# ---------- Code map ----------
class TestCodeMap:
    def test_code_map_content_and_headers(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/code-map",
                               json={"phrase": VAULT_PHRASE}, timeout=30)
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        m = re.search(r'filename="([^"]+)"', cd)
        assert m, cd
        fname = m.group(1)
        assert fname.startswith("pokecoins-code-map-") and fname.endswith(".md")
        body = r.text
        assert "# PokeCoins" in body
        assert "backend/server.py" in body
        assert "frontend/src" in body
        # Excluded dirs must NOT appear in listing.
        for banned in ("node_modules", "__pycache__", "/build/", "/.git/"):
            assert banned not in body, f"code map contains {banned}"
        assert VAULT_PHRASE not in body

    def test_code_map_file_count_reasonable(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/code-map",
                               json={"phrase": VAULT_PHRASE}, timeout=30)
        assert r.status_code == 200
        headers = re.findall(r"^### `", r.text, flags=re.M)
        # requirement says ~60 files
        assert 30 <= len(headers) <= 200, f"unexpected file count: {len(headers)}"


# ---------- Export ----------
class TestExport:
    def test_export_content_and_shape(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/export",
                               json={"phrase": VAULT_PHRASE}, timeout=60)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        m = re.search(r'filename="(pokecoins-backup-[^"]+\.json)"', cd)
        assert m, cd
        # Cleanly parses:
        data = json.loads(r.text)
        assert "exported_at" in data
        assert "database" in data
        assert isinstance(data.get("collections"), dict)
        cols = data["collections"]
        assert "visits" not in cols, "visits should be excluded"
        # Ensure critical business collections are present.
        for required in ("orders", "users", "products", "reviews", "coupons"):
            assert required in cols, f"missing collection {required}"
            assert isinstance(cols[required], list)
        # ObjectIds serialised as strings; datetimes as strings — dumps must have succeeded.
        assert VAULT_PHRASE not in r.text

    def test_export_counts_match_unlock(self, admin_session):
        unl = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                 json={"phrase": VAULT_PHRASE}, timeout=15).json()["collections"]
        exp = admin_session.post(f"{BASE_URL}/api/admin/vault/export",
                                 json={"phrase": VAULT_PHRASE}, timeout=60).json()["collections"]
        for name in ("orders", "users", "products", "reviews", "coupons"):
            if name in unl:
                assert len(exp[name]) == unl[name], (
                    f"{name}: export {len(exp[name])} != unlock {unl[name]}")


# ---------- Rate limit (runs LAST — will lock this IP out) ----------
class TestVaultRateLimitZ:
    """Named with Z prefix so pytest collects/runs after everything else alphabetically-ish.
    Note: uses admin session because auth check runs first. Will consume the IP throttle.
    """

    def test_success_clears_prior_failures_then_lock_after_five(self, admin_session):
        wrong = {"phrase": "definitely-not-the-right-phrase-xx"}
        good = {"phrase": VAULT_PHRASE}

        # The throttle is in-memory and lasts 15 minutes, so a previous run of this class can
        # still have this IP locked. A correct phrase clears it, which is the first thing tested.
        assert admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                  json=good, timeout=15).status_code == 200

        # 4 wrong → still 403, not 429.
        for i in range(4):
            r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                   json=wrong, timeout=15)
            assert r.status_code == 403, f"attempt {i}: {r.status_code}"

        # Successful unlock clears counter.
        r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                               json=good, timeout=15)
        assert r.status_code == 200

        # Now 5 more wrong → the 6th should be 429 (5 recorded).
        codes = []
        for _ in range(6):
            r = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                   json=wrong, timeout=15)
            codes.append(r.status_code)
        assert 429 in codes, f"never got throttled: {codes}"
        # 429 body carries the 15-minute lockout message.
        last = admin_session.post(f"{BASE_URL}/api/admin/vault/unlock",
                                  json=wrong, timeout=15)
        assert last.status_code == 429
        assert "15 min" in last.text or "minutes" in last.text.lower()

    def test_throttle_does_not_block_unrelated_endpoints(self, admin_session):
        # After lockout, other admin endpoints must still work.
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        r = admin_session.get(f"{BASE_URL}/api/products", timeout=15)
        assert r.status_code == 200


# ---------- Frontend bundle scan ----------
class TestFrontendBundleNoPhrase:
    def test_phrase_not_in_frontend_src(self):
        root = Path("/app/frontend/src")
        assert root.exists()
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".jsx", ".ts", ".tsx", ".json", ".css"):
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                assert VAULT_PHRASE not in text, f"phrase leaked in {p}"
                assert "VAULT_PHRASE" not in text, f"VAULT_PHRASE identifier in {p}"
