"""Admin credentials for the test suite — read from backend/.env, never hardcoded."""
import os

from dotenv import dotenv_values

_env = dotenv_values("/app/backend/.env")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL") or _env.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or _env.get("ADMIN_PASSWORD")

if not (ADMIN_EMAIL and ADMIN_PASSWORD):
    raise RuntimeError("ADMIN_EMAIL / ADMIN_PASSWORD missing from environment and backend/.env")
