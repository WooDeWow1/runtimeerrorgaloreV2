"""Iteration 23 — Custom Affiliate Codes (/api/affiliate/code).

Rules:
- Do NOT rename admin's code 4LFSA649.
- Use freshly registered customers with mailinator.com domain.
- Do NOT create checkouts, do NOT mark payouts paid.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _register():
    email = f"codechg{uuid.uuid4().hex[:10]}@mailinator.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "Testpass123!", "name": "Code Chg"}, timeout=30)
    assert r.status_code == 200, r.text
    return s, email


@pytest.fixture(scope="module")
def non_promoter():
    s, email = _register()
    return s, email


@pytest.fixture(scope="module")
def enrolled_promoter():
    s, email = _register()
    r = s.post(f"{API}/affiliate/enroll", timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_affiliate"] is True
    return s, email, d["code"]


# --------- Auth ---------
class TestAuth:
    def test_requires_auth(self):
        r = requests.post(f"{API}/affiliate/code", json={"code": "MYNEW1"}, timeout=15)
        assert r.status_code == 401


# --------- Validation ---------
class TestValidation:
    def test_too_short(self, enrolled_promoter):
        s, _, _ = enrolled_promoter
        r = s.post(f"{API}/affiliate/code", json={"code": "AB"}, timeout=15)
        assert r.status_code == 422

    def test_too_long(self, enrolled_promoter):
        s, _, _ = enrolled_promoter
        r = s.post(f"{API}/affiliate/code", json={"code": "A" * 17}, timeout=15)
        assert r.status_code == 422

    def test_special_chars(self, enrolled_promoter):
        s, _, _ = enrolled_promoter
        r = s.post(f"{API}/affiliate/code", json={"code": "BAD!CODE"}, timeout=15)
        assert r.status_code == 422

    def test_space_rejected(self, enrolled_promoter):
        s, _, _ = enrolled_promoter
        r = s.post(f"{API}/affiliate/code", json={"code": "BAD CODE"}, timeout=15)
        assert r.status_code == 422

    def test_accepts_underscore_hyphen(self):
        # Just testing model validation via a fresh unauth call — expect 401 (means model passed).
        # If model rejected, we'd see 422 before auth.
        r = requests.post(f"{API}/affiliate/code", json={"code": "MY_CODE-1"}, timeout=15)
        assert r.status_code == 401  # passed validation, then hit auth


# --------- Not a promoter ---------
class TestNotPromoter:
    def test_returns_400(self, non_promoter):
        s, _ = non_promoter
        r = s.post(f"{API}/affiliate/code",
                   json={"code": f"NEW{uuid.uuid4().hex[:6].upper()}"}, timeout=60)
        assert r.status_code == 400, r.text
        assert "promoter" in r.json()["detail"].lower()


# --------- /affiliate/me exposes code_editable and code_change_used ---------
class TestMeExposesFields:
    def test_before_change(self, enrolled_promoter):
        s, _, _ = enrolled_promoter
        r = s.get(f"{API}/affiliate/me", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "code_editable" in d
        assert "code_change_used" in d
        assert d["code_editable"] is True
        assert d["code_change_used"] is False


# --------- Happy path + one-change-only ---------
class TestChangeCode:
    def test_change_and_one_change_only_and_ignores_injection(self, enrolled_promoter):
        s, email, original_code = enrolled_promoter
        new_code = f"TR{uuid.uuid4().hex[:10].upper()}"[:16]

        # Try to inject other-user identity in body — must be ignored (server uses caller's own).
        r = s.post(f"{API}/affiliate/code",
                   json={"code": new_code,
                         "customer_id": 1,
                         "sellauth_customer_id": 1,
                         "email": "attacker@example.com"},
                   timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        # SellAuth should now reflect the new code
        assert d["code"] == new_code, d
        assert d["link"] == f"https://pokecoins.cc/?ref={new_code}"
        assert d["is_affiliate"] is True

        # /me shows code_change_used=True
        me = s.get(f"{API}/affiliate/me", timeout=30).json()
        assert me["code_change_used"] is True
        assert me["code"] == new_code

        # A second change is rejected — SellAuth is NOT hit again
        r2 = s.post(f"{API}/affiliate/code",
                    json={"code": f"AGAIN{uuid.uuid4().hex[:6].upper()}"},
                    timeout=30)
        assert r2.status_code == 400, r2.text
        assert "already" in r2.json()["detail"].lower()

        # Code still equals the FIRST custom one (SellAuth was not reached)
        me2 = s.get(f"{API}/affiliate/me", timeout=30).json()
        assert me2["code"] == new_code


# --------- Duplicate collision ---------
class TestDuplicate:
    def test_duplicate_readable_400(self):
        # Two fresh users. First claims a unique code. Second tries the same code —
        # SellAuth must reject with a readable 400 (not 500, not Cloudflare page).
        code = f"DUP{uuid.uuid4().hex[:8].upper()}"[:16]

        s1, _ = _register()
        r = s1.post(f"{API}/affiliate/enroll", timeout=90)
        assert r.status_code == 200
        r = s1.post(f"{API}/affiliate/code", json={"code": code}, timeout=90)
        assert r.status_code == 200, r.text

        s2, _ = _register()
        r = s2.post(f"{API}/affiliate/enroll", timeout=90)
        assert r.status_code == 200
        r = s2.post(f"{API}/affiliate/code", json={"code": code}, timeout=90)
        assert r.status_code == 400, r.text
        body = r.json()
        assert "detail" in body and body["detail"]
        # Body should NOT be a Cloudflare HTML page — we already parsed as JSON above.


# --------- CodeChangeRequest model unit ---------
class TestCodeModel:
    def test_pattern_and_upper(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from models import CodeChangeRequest
        # Valid
        assert CodeChangeRequest(code="ABC").code == "ABC"
        assert CodeChangeRequest(code="my_code-1").code == "my_code-1"
        # Invalid (raises)
        from pydantic import ValidationError
        for bad in ["AB", "A" * 17, "BAD!", "BAD CODE", "hi.there"]:
            with pytest.raises(ValidationError):
                CodeChangeRequest(code=bad)
