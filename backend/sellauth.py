import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SELLAUTH_BASE = "https://api.sellauth.com/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['SELLAUTH_API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _shop_id() -> str:
    return os.environ["SELLAUTH_SHOP_ID"]


class SellAuthError(Exception):
    pass


class SellAuthPlanError(SellAuthError):
    pass


async def create_checkout(*, items: list[dict], email: str, session_id: str,
                          coupon: Optional[str] = None) -> dict:
    """Create a SellAuth hosted checkout. Catalog items use the shop's product/variant ids so
    SellAuth owns pricing, stock and coupons; anything unmapped falls back to a custom line."""
    cart = []
    for i in items:
        if i.get("sellauth_product_id") and i.get("sellauth_variant_id"):
            cart.append({
                "productId": int(i["sellauth_product_id"]),
                "variantId": int(i["sellauth_variant_id"]),
                "quantity": i["quantity"],
            })
        else:
            cart.append({"name": i["name"], "price": f"{i['price']:.2f}", "quantity": i["quantity"]})
    payload: dict[str, Any] = {
        "cart": cart,
        "email": email,
        "currency": "USD",
        "metadata": {"checkout_session_id": session_id},
    }
    if coupon:
        payload["coupon"] = coupon.strip()
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.post(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/checkout", headers=_headers(), json=payload
        )
        # Older shops validate metadata as a plain list of strings.
        if resp.status_code in (400, 422) and "metadata" in resp.text:
            payload["metadata"] = [session_id]
            resp = await client.post(
                f"{SELLAUTH_BASE}/shops/{_shop_id()}/checkout", headers=_headers(), json=payload
            )
        if resp.status_code in (400, 422) and "metadata" in resp.text:
            payload.pop("metadata", None)
            resp = await client.post(
                f"{SELLAUTH_BASE}/shops/{_shop_id()}/checkout", headers=_headers(), json=payload
            )
    if resp.is_error:
        logger.error("SellAuth checkout failed: %s %s", resp.status_code, resp.text[:400])
        message = ""
        try:
            message = resp.json().get("message") or resp.json().get("error") or ""
        except ValueError:
            pass
        if "subscription plan" in message.lower() or "unlock checkout api" in message.lower():
            raise SellAuthPlanError(
                "SellAuth's Checkout API is not enabled on this store's subscription plan. "
                "Enable the Checkout API feature in SellAuth to accept payments."
            )
        raise SellAuthError(message or f"SellAuth rejected the checkout ({resp.status_code})")
    data = resp.json()
    invoice = data.get("invoice") or {}
    url = data.get("url") or data.get("checkout_url") or data.get("invoice_url") or invoice.get("url")
    invoice_id = data.get("invoice_id") or invoice.get("id") or data.get("id")
    if not url:
        logger.error("SellAuth returned no checkout URL: %s", str(data)[:400])
        raise SellAuthError("SellAuth returned no checkout URL")
    return {"url": url, "invoice_id": str(invoice_id) if invoice_id else None, "raw": data}


async def get_invoice(invoice_id: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{SELLAUTH_BASE}/shops/{_shop_id()}/invoices/{invoice_id}", headers=_headers()
            )
        if resp.is_error:
            logger.warning("SellAuth invoice fetch failed: %s %s", resp.status_code, resp.text[:200])
            return None
        return resp.json()
    except Exception as exc:
        logger.warning("SellAuth invoice fetch error: %s", exc)
        return None


PAID_STATUSES = {"completed", "paid", "success", "successful", "complete"}


def is_paid(invoice: dict) -> bool:
    inner = invoice.get("invoice") if isinstance(invoice.get("invoice"), dict) else invoice
    status = str(inner.get("status") or inner.get("payment_status") or "").lower()
    return status in PAID_STATUSES
