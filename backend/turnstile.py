"""Cloudflare Turnstile server-side verification.

The site key is public and lives in the frontend; only the secret key belongs here.
A token is single-use and expires after ~5 minutes, so it is verified exactly once.
"""
import logging
import os
from typing import Optional

import httpx

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
logger = logging.getLogger(__name__)


def dev_bypass_hosts() -> list[str]:
    """Hostnames where the challenge is skipped because they cannot be added in Cloudflare
    (the preview sandbox). Production hostnames must never be listed here."""
    raw = os.environ.get("TURNSTILE_DEV_BYPASS_HOSTS", "")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def bypassed(host: str) -> bool:
    return host.lower() in dev_bypass_hosts()


def bypassed_request(request) -> bool:
    """The sandbox host cannot be registered in Cloudflare, so the challenge is skipped there.
    Behind the ingress the real hostname arrives in x-forwarded-host / origin, not host."""
    hosts = dev_bypass_hosts()
    if not hosts:
        return False
    candidates = [
        (request.headers.get("host") or "").split(":")[0],
        (request.headers.get("x-forwarded-host") or "").split(":")[0],
        (request.headers.get("origin") or ""),
        (request.headers.get("referer") or ""),
    ]
    return any(h and h in candidate.lower() for h in hosts for candidate in candidates)


async def verify(token: str, remote_ip: Optional[str] = None) -> tuple[bool, str]:
    """Returns (ok, reason). A network failure is a failure — we never accept on error."""
    secret = os.environ.get("TURNSTILE_SECRET_KEY")
    if not secret:
        return False, "turnstile-not-configured"
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(SITEVERIFY, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Turnstile verification unreachable: %s", exc)
        return False, "internal-error"
    if data.get("success"):
        return True, "ok"
    codes = ",".join(data.get("error-codes") or []) or "unknown"
    logger.warning("Turnstile rejected a token: %s", codes)
    return False, codes
