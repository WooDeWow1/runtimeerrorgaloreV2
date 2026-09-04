"""Auth playbook checks: bcrypt hash format, httpOnly cookies, CORS+credentials,
brute-force lockout, seed_admin idempotency."""
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
from admin_creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

mongo = MongoClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]


class TestPasswordHashing:
    def test_admin_hash_is_bcrypt_2b(self):
        admin = db.users.find_one({"email": ADMIN_EMAIL})
        assert admin, "seeded admin missing"
        assert admin["role"] == "admin"
        h = admin["password_hash"]
        assert h.startswith("$2b$"), f"unexpected hash prefix: {h[:4]}"
        assert len(h) == 60

    def test_new_user_hash_is_bcrypt_and_not_plaintext(self):
        email = f"testqa_hash_{uuid.uuid4().hex[:6]}@example.com"
        pwd = "Trainer#2026"
        try:
            r = requests.post(f"{API}/auth/register",
                              json={"email": email, "password": pwd, "name": "QA Hash"})
            assert r.status_code == 200, r.text
            doc = db.users.find_one({"email": email})
            assert doc["password_hash"].startswith("$2b$")
            assert pwd not in doc["password_hash"]
            assert "password" not in r.json()["user"]
        finally:
            db.users.delete_many({"email": email})


class TestCookies:
    def test_login_sets_httponly_cookies(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        raw = r.headers.get("set-cookie", "") + " ".join(
            v for k, v in r.raw.headers.items() if k.lower() == "set-cookie")
        assert "access_token" in raw and "refresh_token" in raw, raw
        assert raw.lower().count("httponly") >= 2, raw
        assert "Secure" in raw, raw
        assert "access_token" in r.cookies and "refresh_token" in r.cookies

    def test_cookie_auth_works_without_bearer(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["email"] == ADMIN_EMAIL

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        r = s.post(f"{API}/auth/logout")
        assert r.status_code == 200
        assert s.get(f"{API}/auth/me").status_code == 401


LOCAL_API = "http://localhost:8001/api"


class TestCors:
    def test_app_preflight_allows_credentials_with_reflected_origin(self):
        """Edge/ingress answers OPTIONS with ACAO '*' and no credentials header, so the
        app-level policy is asserted directly against uvicorn."""
        r = requests.options(f"{LOCAL_API}/auth/login", headers={
            "Origin": BASE_URL, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        assert r.status_code in (200, 204), r.status_code
        assert r.headers.get("access-control-allow-credentials") == "true"
        assert r.headers.get("access-control-allow-origin") == BASE_URL

    def test_arbitrary_origin_is_reflected_security_note(self):
        """SECURITY NOTE: allow_origin_regex='.*' + allow_credentials=True reflects ANY
        origin, so any site can make credentialed cross-origin calls."""
        evil = "https://evil.example.com"
        r = requests.options(f"{LOCAL_API}/auth/login", headers={
            "Origin": evil, "Access-Control-Request-Method": "POST"})
        reflected = r.headers.get("access-control-allow-origin")
        print(f"CORS allow-origin for {evil}: {reflected} "
              f"(credentials={r.headers.get('access-control-allow-credentials')})")
        assert reflected == evil, "expected current permissive behaviour to be documented"


class TestBruteForceLockout:
    def test_lockout_after_five_failures(self):
        """DEFECT: lockout key is f"{request.client.host}:{email}" and request.client.host is
        the ingress pod IP (multiple replicas), so failures are split across identifiers and
        the real 5-strike threshold needs ~5 * replicas attempts."""
        email = f"testqa_lock_{uuid.uuid4().hex[:6]}@example.com"
        try:
            requests.post(f"{API}/auth/register",
                          json={"email": email, "password": "Trainer#2026", "name": "QA Lock"})
            codes = []
            locked_at = None
            for n in range(1, 21):
                sc = requests.post(f"{API}/auth/login",
                                   json={"email": email, "password": "wrong"}).status_code
                codes.append(sc)
                if sc == 429:
                    locked_at = n
                    break
            assert locked_at, f"never locked out in 20 attempts: {codes}"
            print(f"locked out on attempt {locked_at} (expected 6)")
            # Correct password is also locked out while the window is active
            good = requests.post(f"{API}/auth/login",
                                 json={"email": email, "password": "Trainer#2026"})
            assert good.status_code == 429, good.status_code
            assert locked_at == 6, (
                f"lockout triggered on attempt {locked_at}; per-IP key is diluted by the "
                f"ingress proxy IPs (use X-Forwarded-For or key on email only)")
        finally:
            db.users.delete_many({"email": email})
            db.login_attempts.delete_many({"identifier": {"$regex": email}})

    def test_successful_login_resets_counter(self):
        email = f"testqa_reset_{uuid.uuid4().hex[:6]}@example.com"
        pwd = "Trainer#2026"
        try:
            requests.post(f"{API}/auth/register",
                          json={"email": email, "password": pwd, "name": "QA Reset"})
            for _ in range(3):
                requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong"})
            ok = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})
            assert ok.status_code == 200, ok.text
            assert db.login_attempts.count_documents({"identifier": {"$regex": email}}) == 0
        finally:
            db.users.delete_many({"email": email})
            db.login_attempts.delete_many({"identifier": {"$regex": email}})


class TestSeedAdminIdempotent:
    def test_only_one_admin_doc(self):
        assert db.users.count_documents({"email": ADMIN_EMAIL}) == 1

    def test_admin_login_works(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "admin"
