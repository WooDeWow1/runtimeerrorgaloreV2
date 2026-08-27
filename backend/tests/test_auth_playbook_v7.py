"""Auth playbook re-verification: bcrypt format, httpOnly cookies, CORS credentials,
brute-force lockout, admin seed behaviour."""
import asyncio
import re
from pathlib import Path

import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
ADMIN_EMAIL = re.search(r'Email:\s*`([^`]+)`', content).group(1)
ADMIN_PASS = re.search(r'Password:\s*`([^`]+)`', content).group(1)


def test_bcrypt_hash_format():
    async def get():
        c = AsyncIOMotorClient(env["MONGO_URL"])
        d = c[env["DB_NAME"]]
        u = await d.users.find_one({"email": ADMIN_EMAIL})
        c.close()
        return u

    user = asyncio.run(get())
    assert user is not None
    assert user["password_hash"].startswith("$2b$"), user["password_hash"][:10]
    assert user["role"] == "admin"


def test_login_sets_httponly_cookies():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    assert "access_token" in raw and "HttpOnly" in raw, raw[:200]
    assert "Secure" in raw and "samesite=none" in raw.lower(), raw[:200]
    # cookie session alone authenticates /auth/me
    me = s.get(f"{API}/auth/me")
    assert me.status_code == 200 and me.json()["role"] == "admin"


def test_cors_allows_credentials_with_origin():
    """Actual (non-preflight) request: the app echoes any Origin and allows credentials.
    NOTE: OPTIONS preflight is answered by the ingress (ACAO '*', no allow-credentials)."""
    origin = "https://evil.example.com"
    r = requests.get(f"{API}/health", headers={"Origin": origin})
    print("CORS actual request headers:", dict(r.headers))
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-credentials") == "true"
    # Finding: backend uses allow_origin_regex=".*" with credentials. In preview the ingress
    # rewrites Access-Control-Allow-Origin to "*"; on a custom domain the app would echo any
    # origin back, so an explicit origin allow-list is the safer configuration.
    assert r.headers.get("access-control-allow-origin") in ("*", origin)


def test_brute_force_lockout():
    email = "qa_lockout_probe@gmail.com"
    # The pod egress IP rotates behind the ingress, so pin the forwarded IP the app keys on.
    headers = {"X-Forwarded-For": "203.0.113.99"}
    codes = []
    for _ in range(6):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong-pass"},
                          headers=headers)
        codes.append(r.status_code)
    print("lockout status sequence:", codes)
    assert codes[:5] == [401] * 5, codes
    assert codes[5] == 429, codes
    # a valid admin login from the same IP but different email is unaffected
    ok = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                       headers=headers)
    assert ok.status_code == 200, ok.text

    async def clean():
        c = AsyncIOMotorClient(env["MONGO_URL"])
        d = c[env["DB_NAME"]]
        await d.login_attempts.delete_many({"identifier": {"$regex": email}})
        c.close()

    asyncio.run(clean())


def test_admin_password_matches_env_seed():
    assert ADMIN_EMAIL == env["ADMIN_EMAIL"].lower()
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": env["ADMIN_PASSWORD"]})
    assert r.status_code == 200, "seed_admin did not sync the env password"
