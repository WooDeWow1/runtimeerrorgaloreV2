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


def _image_url(product: dict) -> str:
    """First gallery image in SellAuth order, so the storefront never needs a local file."""
    images = sorted(
        product.get("images") or [],
        key=lambda i: (i.get("pivot") or {}).get("order", 0),
    )
    return next((i["url"] for i in images if i.get("url")), "")


async def fetch_product(product_id: int) -> dict:
    """Look up a SellAuth product so the admin only ever types its id."""
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.get(
            f"{SELLAUTH_BASE}/shops/{_shop_id()}/products/{int(product_id)}", headers=_headers()
        )
    if resp.is_error:
        raise SellAuthError(f"SellAuth product {product_id} not found ({resp.status_code})")
    data = resp.json()
    product = data.get("product") if isinstance(data.get("product"), dict) else data
    variants = product.get("variants") or []
    if not variants:
        raise SellAuthError(f"SellAuth product {product_id} has no variants")
    variant = variants[0]
    name = product.get("name") or ""

    def short_label(raw: str) -> str:
        """SellAuth names variants '<Product> (Ultra Box)': keep just the option part."""
        label = (raw or "").strip()
        if name and label.startswith(name):
            label = label[len(name):].strip()
        return label.strip("()-– ").strip() or "Standard"

    return {
        "sellauth_product_id": int(product.get("id", product_id)),
        "sellauth_variant_id": int(variant["id"]),
        "price": float(variant["price"]),
        "name": name,
        "description": product.get("description") or "",
        "image_url": _image_url(product),
        "variants": [
            {"label": short_label(v.get("name")), "sellauth_variant_id": int(v["id"]),
             "price": float(v["price"])}
            for v in variants
        ],
    }


def _cart_line(item: dict) -> dict:
    """Catalog line when SellAuth owns the price; custom line when we discounted it."""
    custom_price = item.get("custom_price")
    if custom_price is None and item.get("sellauth_product_id") and item.get("sellauth_variant_id"):
        return {
            "productId": int(item["sellauth_product_id"]),
            "variantId": int(item["sellauth_variant_id"]),
            "quantity": item["quantity"],
        }
    price = float(custom_price if custom_price is not None else item["price"])
    return {"name": item["name"], "price": f"{price:.2f}", "quantity": item["quantity"]}


async def _post_checkout(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """Post the checkout, retrying with older metadata shapes some shops still validate."""
    url = f"{SELLAUTH_BASE}/shops/{_shop_id()}/checkout"
    session_id = payload["metadata"]["checkout_session_id"]
    resp = await client.post(url, headers=_headers(), json=payload)
    for fallback in ([session_id], None):
        if not (resp.status_code in (400, 422) and "metadata" in resp.text):
            return resp
        if fallback is None:
            payload.pop("metadata", None)
        else:
            payload["metadata"] = fallback
        resp = await client.post(url, headers=_headers(), json=payload)
    return resp


def _checkout_error(resp: httpx.Response) -> SellAuthError:
    logger.error("SellAuth checkout failed: %s %s", resp.status_code, resp.text[:400])
    message = ""
    try:
        body = resp.json()
        message = body.get("message") or body.get("error") or ""
    except ValueError:
        pass
    if "subscription plan" in message.lower() or "unlock checkout api" in message.lower():
        return SellAuthPlanError(
            "SellAuth's Checkout API is not enabled on this store's subscription plan. "
            "Enable the Checkout API feature in SellAuth to accept payments."
        )
    return SellAuthError(message or f"SellAuth rejected the checkout ({resp.status_code})")


async def create_checkout(*, items: list[dict], email: str, session_id: str,
                          affiliate_code: Optional[str] = None) -> dict:
    """Create a SellAuth hosted checkout. Catalog items use the shop's product/variant ids so
    SellAuth owns pricing and stock. Discounted lines carry a `custom_price` and are sent as
    custom items instead, because a catalog price cannot be overridden."""
    payload: dict[str, Any] = {
        "cart": [_cart_line(i) for i in items],
        "email": email,
        "currency": "USD",
        "metadata": {"checkout_session_id": session_id},
    }
    if affiliate_code:
        payload["affiliate"] = affiliate_code[:16]
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await _post_checkout(client, payload)
    if resp.is_error:
        raise _checkout_error(resp)
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
