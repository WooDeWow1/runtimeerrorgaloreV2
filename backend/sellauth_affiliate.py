"""SellAuth affiliate program access.

Reads use the seller API. Anything the customer triggers (payout requests) goes through a
short-lived customer-dashboard token minted server-to-server for that one customer, so a request
can never reach another account.
"""
import logging
import os
import secrets
import string
from typing import Optional

import httpx

from sellauth import SELLAUTH_BASE, SellAuthError, _headers, _shop_id

logger = logging.getLogger(__name__)

CUSTOMER_BASE = f"{SELLAUTH_BASE}/customer-dashboard"
TIMEOUT = 25
CODE_ALPHABET = string.ascii_uppercase + string.digits


def _err(resp: httpx.Response, action: str) -> SellAuthError:
    try:
        message = resp.json().get("message") or ""
    except ValueError:
        message = ""
    logger.error("SellAuth %s failed: %s %s", action, resp.status_code, resp.text[:300])
    return SellAuthError(message or f"SellAuth rejected the request ({resp.status_code})")


async def settings() -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{SELLAUTH_BASE}/shops/{_shop_id()}/settings", headers=_headers())
    if resp.is_error:
        raise _err(resp, "settings fetch")
    return resp.json().get("affiliate") or {}


async def default_tier() -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/affiliate-tiers", headers=_headers()
        )
    if resp.is_error:
        raise _err(resp, "tier fetch")
    tiers = resp.json() or []
    return next((t for t in tiers if t.get("is_default")), tiers[0] if tiers else {})


def commission_range(tier: dict) -> dict:
    """A flat headline rate would be a lie: per-product overrides run from 0% (Event Passes)
    up to 10%, so the panel shows the range and names what earns nothing."""
    base = float(tier.get("percentage") or 0)
    overrides = [float(p["pivot"]["percentage"]) for p in tier.get("products") or []
                 if p.get("pivot") is not None]
    rates = overrides or [base]
    excluded = [p["name"] for p in tier.get("products") or []
                if float(p["pivot"]["percentage"]) == 0]
    return {
        "base_percent": base,
        "min_percent": min(rates),
        "max_percent": max(rates),
        "excluded_products": excluded,
        "buyer_discount_percent": float(tier.get("discount_percentage") or 0),
        "tier_id": tier.get("id"),
        "tier_name": tier.get("name") or "",
    }


async def find_customer(email: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{SELLAUTH_BASE}/shops/{_shop_id()}/customers",
                                headers=_headers(), params={"email": email})
    if resp.is_error:
        raise _err(resp, "customer lookup")
    rows = resp.json().get("data") or []
    return next((r for r in rows if (r.get("email") or "").lower() == email.lower()), None)


async def create_customer(email: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{SELLAUTH_BASE}/shops/{_shop_id()}/customers",
                                 headers=_headers(), json={"email": email})
    if resp.is_error:
        raise _err(resp, "customer create")
    body = resp.json()
    return body.get("customer") or body


async def get_affiliate(customer_id: int) -> Optional[dict]:
    """Detail view. Returns None when the customer exists but is not an affiliate."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/affiliates/{int(customer_id)}", headers=_headers()
        )
    if resp.status_code == 404:
        return None
    if resp.is_error:
        raise _err(resp, "affiliate fetch")
    return resp.json()


def new_code(seed: str) -> str:
    """Readable, unguessable, and inside SellAuth's 16 character limit."""
    stem = "".join(ch for ch in seed.upper() if ch in string.ascii_uppercase)[:8] or "POKE"
    return f"{stem}{''.join(secrets.choice(CODE_ALPHABET) for _ in range(6))}"[:16]


async def invite_affiliate(email: str, code: str, tier_id: int) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/affiliates/invite", headers=_headers(),
            json={"email": email, "affiliate_code": code, "tier_id": int(tier_id),
                  "send_email": True},
        )
    if resp.is_error:
        raise _err(resp, "affiliate invite")
    return resp.json()


async def customer_token(customer_id: int) -> str:
    """Minted server side only, and scoped to this single customer."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/customers/{int(customer_id)}/token",
            headers=_headers(), json={"expires_in": 300},
        )
    if resp.is_error:
        raise _err(resp, "customer token")
    return resp.json()["token"]


async def request_payout(customer_id: int, amount: float, payout_details: str) -> dict:
    token = await customer_token(customer_id)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{CUSTOMER_BASE}/affiliate/payout-request",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json={"amount": round(float(amount), 2), "payout_details": payout_details},
        )
    if resp.is_error:
        raise _err(resp, "payout request")
    return resp.json()


async def cancel_payout(customer_id: int, payout_request_id: int) -> dict:
    token = await customer_token(customer_id)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{CUSTOMER_BASE}/affiliate/payout-request/{int(payout_request_id)}/cancel",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if resp.is_error:
        raise _err(resp, "payout cancel")
    return resp.json()


def referral_link(code: str) -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    return f"{base}/?ref={code}"
