import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import hashlib  # noqa: E402
import hmac  # noqa: E402
import httpx  # noqa: E402
import jwt  # noqa: E402
from bson import ObjectId  # noqa: E402
from bson.errors import InvalidId  # noqa: E402
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from models import (  # noqa: E402
    CATEGORIES,
    ORDER_STATUSES,
    CheckoutRequest,
    Coupon,
    CouponIn,
    CouponValidateRequest,
    FeaturedUpdate,
    LoginRequest,
    Message,
    MessageIn,
    Notification,
    Order,
    OrderItem,
    PasswordChangeRequest,
    Product,
    ProductIn,
    ProductUpdate,
    RegisterRequest,
    StatusUpdate,
    UserPublic,
    WaitlistIn,
    utc_now,
)
from security import (  # noqa: E402
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
import sellauth  # noqa: E402
from emailer import order_tracking_html, send_email  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

SELLAUTH_WEBHOOK_SECRET = os.environ["SELLAUTH_WEBHOOK_SECRET"]
SESSION_TTL_MINUTES = int(os.environ.get("CHECKOUT_SESSION_TTL_MINUTES", "30"))
MIN_CHARGE = 0.50

app = FastAPI(title="PokeCoins API")
api = APIRouter(prefix="/api")


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id")


def set_auth_cookies(response: Response, user_id: str, email: str, role: str):
    response.set_cookie("access_token", create_access_token(user_id, email, role), httponly=True,
                        secure=True, samesite="none", max_age=3600, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user_id), httponly=True,
                        secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException as exc:
        if exc.status_code == 429:
            raise
        return None


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def public_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "customer"),
    }


# ---------------- Auth ----------------
@api.post("/auth/register")
async def register(payload: RegisterRequest, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": "customer",
        "created_at": utc_now(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    set_auth_cookies(response, str(result.inserted_id), email, "customer")
    return {
        "user": public_user(doc),
        "access_token": create_access_token(str(result.inserted_id), email, "customer"),
    }


@api.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and locked_until.replace(tzinfo=timezone.utc) > utc_now():
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
        await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": utc_now() + timedelta(minutes=15)}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    role = user.get("role", "customer")
    set_auth_cookies(response, str(user["_id"]), email, role)
    return {
        "user": public_user(user),
        "access_token": create_access_token(str(user["_id"]), email, role),
    }


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.post("/auth/change-password")
async def change_password(payload: PasswordChangeRequest, user: dict = Depends(get_current_user)):
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_self_managed": True,
                  "password_changed_at": utc_now()}},
    )
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    role = user.get("role", "customer")
    set_auth_cookies(response, str(user["_id"]), user["email"], role)
    return {
        "user": public_user(user),
        "access_token": create_access_token(str(user["_id"]), user["email"], role),
    }


# ---------------- Products ----------------
@api.get("/products")
async def list_products(
    include_inactive: bool = False, user: Optional[dict] = Depends(get_optional_user)
):
    if include_inactive and (not user or user.get("role") != "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    query = {} if include_inactive else {"active": True}
    docs = await db.products.find(query).sort("price", 1).to_list(500)
    return [Product.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/products")
async def create_product(payload: ProductIn, admin: dict = Depends(get_admin_user)):
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    product = Product(**payload.model_dump())
    result = await db.products.insert_one(product.to_mongo())
    doc = await db.products.find_one({"_id": result.inserted_id})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.put("/products/{product_id}")
async def update_product(product_id: str, payload: ProductUpdate, admin: dict = Depends(get_admin_user)):
    if payload.category is not None and payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    existing = await db.products.find_one({"_id": oid(product_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    # Only touch the fields the caller actually sent, so flags like is_featured survive an edit.
    updates = payload.model_dump(exclude_unset=True)
    if updates:
        await db.products.update_one({"_id": oid(product_id)}, {"$set": updates})
    doc = await db.products.find_one({"_id": oid(product_id)})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.patch("/products/{product_id}/featured")
async def toggle_featured(product_id: str, payload: FeaturedUpdate, admin: dict = Depends(get_admin_user)):
    result = await db.products.update_one(
        {"_id": oid(product_id)}, {"$set": {"is_featured": payload.is_featured}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    doc = await db.products.find_one({"_id": oid(product_id)})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.delete("/products/{product_id}")
async def delete_product(product_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.products.delete_one({"_id": oid(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"ok": True}


# ---------------- Coupons ----------------
async def resolve_items(entries) -> List[OrderItem]:
    items: List[OrderItem] = []
    for entry in entries:
        doc = await db.products.find_one({"_id": oid(entry.product_id), "active": True})
        if not doc:
            raise HTTPException(status_code=400, detail="A product in your cart is unavailable")
        if doc.get("coming_soon"):
            raise HTTPException(status_code=400, detail=f"{doc['name']} is not available yet")
        items.append(OrderItem(
            product_id=str(doc["_id"]), name=doc["name"], category=doc["category"],
            price=float(doc["price"]), quantity=entry.quantity,
        ))
    return items


async def apply_coupon(
    code: Optional[str], items: List[OrderItem], email: Optional[str] = None
) -> dict:
    """Returns pricing breakdown. Raises 400 with a human message if the code cannot be used."""
    subtotal = round(sum(i.price * i.quantity for i in items), 2)
    result = {
        "subtotal": subtotal, "discount": 0.0, "total": subtotal,
        "coupon_code": None, "percent_off": None, "amount_off": None,
        "discount_type": None, "discount_label": None,
        "eligible_subtotal": subtotal, "excluded_items": [],
    }
    if not code:
        return result

    coupon = await db.coupons.find_one({"code": code.strip().upper()})
    if not coupon or not coupon.get("active", True):
        raise HTTPException(status_code=400, detail="That coupon code is not valid.")
    expires = coupon.get("expires_at")
    if expires and expires.replace(tzinfo=timezone.utc) < utc_now():
        raise HTTPException(status_code=400, detail="That coupon has expired.")
    if coupon.get("max_uses") and coupon.get("used_count", 0) >= coupon["max_uses"]:
        raise HTTPException(status_code=400, detail="That coupon has reached its usage limit.")
    if coupon.get("min_subtotal") and subtotal < coupon["min_subtotal"]:
        raise HTTPException(
            status_code=400,
            detail=f"Spend at least ${coupon['min_subtotal']:.2f} to use this coupon.",
        )
    if coupon.get("one_per_customer") and email:
        used = await db.coupon_redemptions.find_one(
            {"code": coupon["code"], "email": email.strip().lower()}
        )
        if used:
            raise HTTPException(
                status_code=400,
                detail="You've already used this code — it is limited to one per customer.",
            )

    excluded_ids = set(coupon.get("excluded_product_ids") or [])
    excluded_cats = set(coupon.get("excluded_categories") or [])
    eligible, excluded_names = [], []
    for i in items:
        if i.product_id in excluded_ids or i.category in excluded_cats:
            excluded_names.append(i.name)
        else:
            eligible.append(i)
    if not eligible:
        raise HTTPException(
            status_code=400, detail="This coupon does not apply to any item in your cart."
        )

    eligible_subtotal = round(sum(i.price * i.quantity for i in eligible), 2)
    if coupon.get("discount_type", "percent") == "fixed":
        amount = float(coupon.get("amount_off") or 0)
        # Cap the discount so the cart still has a chargeable total for the payment provider.
        max_discount = max(round(subtotal - MIN_CHARGE, 2), 0)
        discount = round(min(amount, eligible_subtotal, max_discount), 2)
        if discount <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"This cart is too small for that code — spend at least ${MIN_CHARGE + 0.01:.2f}.",
            )
        label = f"${discount:.2f} off"
    else:
        discount = round(eligible_subtotal * coupon["percent_off"] / 100, 2)
        label = f"{coupon['percent_off']:g}% off"
    result.update({
        "discount": discount,
        "total": round(subtotal - discount, 2),
        "coupon_code": coupon["code"],
        "percent_off": coupon.get("percent_off"),
        "amount_off": coupon.get("amount_off"),
        "discount_type": coupon.get("discount_type", "percent"),
        "discount_label": label,
        "one_per_customer": bool(coupon.get("one_per_customer")),
        "eligible_subtotal": eligible_subtotal,
        "excluded_items": excluded_names,
    })
    return result


@api.post("/coupons/validate")
async def validate_coupon(payload: CouponValidateRequest):
    items = await resolve_items(payload.items)
    return await apply_coupon(payload.code, items, payload.email)


def validate_coupon_payload(payload: CouponIn):
    if payload.discount_type == "fixed":
        if not payload.amount_off:
            raise HTTPException(status_code=400, detail="Fixed coupons need a dollar amount off.")
    elif not payload.percent_off:
        raise HTTPException(status_code=400, detail="Percentage coupons need a percent off.")


@api.get("/admin/coupons")
async def list_coupons(admin: dict = Depends(get_admin_user)):
    docs = await db.coupons.find().sort("created_at", -1).to_list(200)
    return [Coupon.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/admin/coupons")
async def create_coupon(payload: CouponIn, admin: dict = Depends(get_admin_user)):
    validate_coupon_payload(payload)
    for cat in payload.excluded_categories:
        if cat not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Unknown category: {cat}")
    coupon = Coupon(**{**payload.model_dump(), "code": payload.code.strip().upper()})
    try:
        result = await db.coupons.insert_one(coupon.to_mongo())
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="That coupon code already exists")
    doc = await db.coupons.find_one({"_id": result.inserted_id})
    return Coupon.from_mongo(doc).model_dump(by_alias=False)


@api.put("/admin/coupons/{coupon_id}")
async def update_coupon(coupon_id: str, payload: CouponIn, admin: dict = Depends(get_admin_user)):
    validate_coupon_payload(payload)
    for cat in payload.excluded_categories:
        if cat not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Unknown category: {cat}")
    updates = {**payload.model_dump(), "code": payload.code.strip().upper()}
    try:
        result = await db.coupons.update_one({"_id": oid(coupon_id)}, {"$set": updates})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="That coupon code already exists")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Coupon not found")
    doc = await db.coupons.find_one({"_id": oid(coupon_id)})
    return Coupon.from_mongo(doc).model_dump(by_alias=False)


@api.delete("/admin/coupons/{coupon_id}")
async def delete_coupon(coupon_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.coupons.delete_one({"_id": oid(coupon_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return {"ok": True}


# ---------------- Orders ----------------
def order_response(doc: dict, include_credentials: bool = False) -> dict:
    order = Order.from_mongo(doc)
    data = order.model_dump(by_alias=False)
    data.pop("ptc_username_enc", None)
    data.pop("ptc_password_enc", None)
    data["ptc_username_masked"] = "•" * 8
    if include_credentials:
        data["ptc_username"] = decrypt_secret(doc["ptc_username_enc"])
        data["ptc_password"] = decrypt_secret(doc["ptc_password_enc"])
    return data


async def notify(user_id: str, order_id: str, title: str, body: str):
    if not user_id:
        return
    n = Notification(user_id=user_id, order_id=order_id, title=title, body=body)
    await db.notifications.insert_one(n.to_mongo())


@api.post("/orders/checkout")
async def checkout(payload: CheckoutRequest, user: Optional[dict] = Depends(get_optional_user)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    items = await resolve_items(payload.items)

    has_pass = any(i.category == "event_pass" for i in items)
    has_coins = any(i.category == "pokecoin_bundle" for i in items)
    if has_pass and not has_coins:
        raise HTTPException(
            status_code=400,
            detail="An Event Pass requires at least one Pokécoin Bundle in your cart.",
        )

    user_id = str(user["_id"]) if user else ""
    email = (user["email"] if user else (payload.email or "")).lower()
    if not email:
        raise HTTPException(status_code=400, detail="An email address is required for guest checkout")

    pricing = await apply_coupon(payload.coupon_code, items, email)
    total = pricing["total"]

    # Nothing is written to `orders` yet: a spam-resistant temporary session with a 30 min TTL.
    session_doc = {
        "items": [i.model_dump() for i in items],
        "total": total,
        "subtotal": pricing["subtotal"],
        "discount": pricing["discount"],
        "coupon_code": pricing["coupon_code"],
        "user_id": user_id,
        "email": email,
        "origin_url": payload.origin_url.rstrip("/"),
        "ptc_username_enc": encrypt_secret(payload.ptc_username),
        "ptc_password_enc": encrypt_secret(payload.ptc_password),
        "status": "awaiting_payment",
        "created_at": utc_now(),
        "expires_at": utc_now() + timedelta(minutes=SESSION_TTL_MINUTES),
    }
    result = await db.checkout_sessions.insert_one(session_doc)
    session_id = str(result.inserted_id)

    # SellAuth is charged the discounted amounts; the order keeps original prices + discount metadata.
    charge_items = [i.model_dump() for i in items]
    if pricing["discount"] > 0:
        factor = max(
            (pricing["eligible_subtotal"] - pricing["discount"]) / pricing["eligible_subtotal"], 0
        )
        excluded = set(pricing["excluded_items"])
        eligible_idx = [n for n, e in enumerate(charge_items) if e["name"] not in excluded]
        for n in eligible_idx:
            charge_items[n]["price"] = round(charge_items[n]["price"] * factor, 2)
        # Absorb per-line rounding drift into the last eligible line so the charge matches `total`.
        charged = round(sum(e["price"] * e["quantity"] for e in charge_items), 2)
        drift = round(total - charged, 2)
        if drift and eligible_idx:
            last = charge_items[eligible_idx[-1]]
            adjusted = round(last["price"] + drift / last["quantity"], 2)
            last["price"] = max(adjusted, 0.01)

    try:
        checkout_data = await sellauth.create_checkout(
            items=charge_items, email=email, session_id=session_id
        )
    except sellauth.SellAuthPlanError as exc:
        await db.checkout_sessions.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=503, detail=str(exc))
    except sellauth.SellAuthError as exc:
        await db.checkout_sessions.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=502, detail=str(exc))

    await db.checkout_sessions.update_one(
        {"_id": result.inserted_id},
        {"$set": {"invoice_id": checkout_data["invoice_id"], "checkout_url": checkout_data["url"]}},
    )
    return {
        "checkout_url": checkout_data["url"],
        "session_id": session_id,
        "invoice_id": checkout_data["invoice_id"],
    }


async def create_order_from_session(session: dict) -> Optional[str]:
    """Promote a paid checkout session into a permanent order. Idempotent."""
    if session.get("order_id"):
        return session["order_id"]
    order = Order(
        user_id=session.get("user_id", ""),
        user_email=session["email"],
        items=[OrderItem(**i) for i in session["items"]],
        total=session["total"],
        subtotal=session.get("subtotal", session["total"]),
        discount=session.get("discount", 0.0),
        coupon_code=session.get("coupon_code"),
        status="pending",
        payment_status="paid",
        session_id=str(session["_id"]),
        ptc_username_enc=session["ptc_username_enc"],
        ptc_password_enc=session["ptc_password_enc"],
    )
    result = await db.orders.insert_one(order.to_mongo())
    order_id = str(result.inserted_id)
    if session.get("coupon_code"):
        await db.coupons.update_one({"code": session["coupon_code"]}, {"$inc": {"used_count": 1}})
        await db.coupon_redemptions.update_one(
            {"code": session["coupon_code"], "email": session["email"].lower()},
            {"$set": {"order_id": order_id, "redeemed_at": utc_now()}},
            upsert=True,
        )
    await db.checkout_sessions.update_one(
        {"_id": session["_id"]}, {"$set": {"status": "paid", "order_id": order_id}}
    )
    await notify(session.get("user_id", ""), order_id, "Order received",
                 "Payment confirmed. Your order is queued — an operator will pick it up shortly.")

    tracking_url = f"{session['origin_url']}/order/{order_id}"
    await send_email(
        to=session["email"],
        subject=f"Payment received — track your {os.environ['EMAIL_FROM_NAME']} order",
        html=order_tracking_html(
            order_id=order_id,
            tracking_url=tracking_url,
            total=session["total"],
            item_lines=[f"{i['name']} x{i['quantity']}" for i in session["items"]],
        ),
    )
    return order_id


def verify_webhook_signature(raw: bytes, signature: Optional[str]) -> bool:
    if not signature:
        return False
    expected = hmac.new(SELLAUTH_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


@app.post("/api/webhooks/sellauth")
async def sellauth_webhook(request: Request):
    raw = await request.body()
    signature = (
        request.headers.get("signature")
        or request.headers.get("x-signature")
        or request.headers.get("x-sellauth-signature")
    )
    secret_ok = verify_webhook_signature(raw, signature)
    if not secret_ok and request.query_params.get("secret") != SELLAUTH_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else payload
    if isinstance(payload.get("data"), dict) and not invoice.get("id"):
        invoice = payload["data"]
    invoice_id = str(invoice.get("id") or invoice.get("invoice_id") or "")
    custom = invoice.get("custom_fields") or payload.get("custom_fields") or {}
    session_id = custom.get("checkout_session_id") if isinstance(custom, dict) else None

    event_key = f"{invoice_id}:{hashlib.sha256(raw).hexdigest()}"
    if await db.webhook_events.find_one({"event_key": event_key}):
        return {"ok": True, "duplicate": True}

    session = None
    if session_id:
        try:
            session = await db.checkout_sessions.find_one({"_id": oid(session_id)})
        except HTTPException:
            session = None
    if session is None and invoice_id:
        session = await db.checkout_sessions.find_one({"invoice_id": invoice_id})
    if session is None:
        logger.warning("SellAuth webhook for unknown session/invoice %s", invoice_id)
        return {"ok": True, "matched": False}

    paid = sellauth.is_paid(invoice)
    if not paid and invoice_id:
        fresh = await sellauth.get_invoice(invoice_id)
        paid = bool(fresh and sellauth.is_paid(fresh))
    if not paid:
        return {"ok": True, "paid": False}

    order_id = await create_order_from_session(session)
    try:
        await db.webhook_events.insert_one({"event_key": event_key, "received_at": utc_now()})
    except Exception:
        pass
    return {"ok": True, "paid": True, "order_id": order_id}


@api.get("/checkout-sessions/{session_id}")
async def checkout_session_status(session_id: str):
    session = await db.checkout_sessions.find_one({"_id": oid(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Checkout session expired or not found")
    if not session.get("order_id") and session.get("invoice_id"):
        invoice = await sellauth.get_invoice(session["invoice_id"])
        if invoice and sellauth.is_paid(invoice):
            await create_order_from_session(session)
            session = await db.checkout_sessions.find_one({"_id": oid(session_id)})
    return {
        "session_id": session_id,
        "status": session.get("status", "awaiting_payment"),
        "order_id": session.get("order_id"),
        "expires_at": session.get("expires_at"),
    }


@api.get("/orders")
async def my_orders(user: dict = Depends(get_current_user)):
    docs = await db.orders.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(200)
    return [order_response(d) for d in docs]


@api.get("/admin/orders")
async def all_orders(status: Optional[str] = None, admin: dict = Depends(get_admin_user)):
    query = {"status": status} if status else {}
    docs = await db.orders.find(query).sort("created_at", -1).to_list(500)
    return [order_response(d) for d in docs]


@api.get("/orders/{order_id}")
async def get_order(order_id: str, user: Optional[dict] = Depends(get_optional_user)):
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    owner = doc.get("user_id") or ""
    if owner and (not user or (user.get("role") != "admin" and owner != str(user["_id"]))):
        raise HTTPException(status_code=403, detail="Not your order")
    return order_response(doc)


@api.get("/admin/orders/{order_id}/credentials")
async def reveal_credentials(order_id: str, admin: dict = Depends(get_admin_user)):
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "ptc_username": decrypt_secret(doc["ptc_username_enc"]),
        "ptc_password": decrypt_secret(doc["ptc_password_enc"]),
    }


@api.patch("/admin/orders/{order_id}/status")
async def update_status(order_id: str, payload: StatusUpdate, admin: dict = Depends(get_admin_user)):
    if payload.status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.orders.update_one({"_id": oid(order_id)},
                               {"$set": {"status": payload.status, "updated_at": utc_now()}})
    if payload.status != doc.get("status"):
        if payload.status == "processing":
            await notify(doc["user_id"], order_id, "Order is being processed — STAY LOGGED OUT",
                         "An operator is now logged into your PTC account. Please do NOT log into your "
                         "Pokémon GO account until this order is marked Completed.")
        elif payload.status == "completed":
            await notify(doc["user_id"], order_id, "Order completed",
                         "Your order is complete. You may safely log back into your Pokémon GO account. "
                         "We recommend changing your PTC password.")
        elif payload.status == "cancelled":
            await notify(doc["user_id"], order_id, "Order cancelled",
                         "Your order was cancelled. Reply in the order chat if you need help.")
    updated = await db.orders.find_one({"_id": oid(order_id)})
    return order_response(updated)


# ---------------- Messaging ----------------
async def assert_order_access(order_id: str, user: Optional[dict]) -> dict:
    doc = await db.orders.find_one({"_id": oid(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    owner = doc.get("user_id") or ""
    if owner and (not user or (user.get("role") != "admin" and owner != str(user["_id"]))):
        raise HTTPException(status_code=403, detail="Not your order")
    return doc


@api.get("/orders/{order_id}/messages")
async def list_messages(order_id: str, user: Optional[dict] = Depends(get_optional_user)):
    await assert_order_access(order_id, user)
    docs = await db.messages.find({"order_id": order_id}).sort("created_at", 1).to_list(500)
    return [Message.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/orders/{order_id}/messages")
async def post_message(order_id: str, payload: MessageIn, user: Optional[dict] = Depends(get_optional_user)):
    order = await assert_order_access(order_id, user)
    role = user.get("role", "customer") if user else "customer"
    msg = Message(
        order_id=order_id,
        sender_id=str(user["_id"]) if user else "guest",
        sender_name=user.get("name", "User") if user else "Guest",
        sender_role=role,
        body=payload.body,
    )
    result = await db.messages.insert_one(msg.to_mongo())
    if role == "admin":
        await notify(order.get("user_id", ""), order_id, "New message from support", payload.body[:140])
    msg.id = str(result.inserted_id)
    return msg.model_dump(by_alias=False)


# ---------------- Notifications ----------------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    docs = await db.notifications.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(100)
    return [Notification.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/notifications/read")
async def mark_notifications_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": str(user["_id"]), "read": False}, {"$set": {"read": True}})
    return {"ok": True}


# ---------------- Visitor analytics (lightweight) ----------------
def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def lookup_country(ip: str) -> str:
    cached = await db.ip_geo.find_one({"_id": ip})
    if cached:
        return cached.get("country", "Unknown")
    country = "Unknown"
    if not (ip == "unknown" or ip.startswith(("10.", "127.", "192.168.", "172."))):
        try:
            async with httpx.AsyncClient(timeout=4) as http:
                resp = await http.get(f"http://ip-api.com/json/{ip}", params={"fields": "status,country"})
            data = resp.json()
            if data.get("status") == "success":
                country = data.get("country") or "Unknown"
        except Exception as exc:
            logger.info("Geo lookup failed for %s: %s", ip, exc)
    await db.ip_geo.update_one({"_id": ip}, {"$set": {"country": country}}, upsert=True)
    return country


@api.post("/track")
async def track_visit(request: Request):
    """One lightweight row per IP per day: keeps the collection tiny."""
    ip = client_ip(request)
    day = utc_now().strftime("%Y-%m-%d")
    country = await lookup_country(ip)
    await db.visits.update_one(
        {"ip": ip, "day": day},
        {"$set": {"ip": ip, "day": day, "country": country, "last_seen": utc_now()},
         "$setOnInsert": {"first_seen": utc_now(), "expires_at": utc_now() + timedelta(days=90)},
         "$inc": {"hits": 1}},
        upsert=True,
    )
    return {"ok": True}


@api.get("/admin/analytics")
async def analytics(admin: dict = Depends(get_admin_user)):
    visits = await db.visits.find().sort("last_seen", -1).to_list(200)
    countries: dict[str, int] = {}
    for v in visits:
        countries[v.get("country", "Unknown")] = countries.get(v.get("country", "Unknown"), 0) + 1
    today = utc_now().strftime("%Y-%m-%d")
    return {
        "totals": {
            "unique_visitors": len({v["ip"] for v in visits}),
            "visits_today": sum(1 for v in visits if v.get("day") == today),
            "total_hits": sum(v.get("hits", 0) for v in visits),
            "orders": await db.orders.count_documents({}),
            "revenue": round(
                sum(o.get("total", 0) for o in await db.orders.find({}, {"total": 1}).to_list(1000)), 2
            ),
            "waitlist": await db.waitlist.count_documents({}),
        },
        "top_countries": sorted(
            [{"country": c, "visitors": n} for c, n in countries.items()],
            key=lambda x: -x["visitors"],
        )[:8],
        "visits": [
            {
                "ip": v["ip"],
                "country": v.get("country", "Unknown"),
                "hits": v.get("hits", 1),
                "last_seen": v.get("last_seen"),
            }
            for v in visits[:100]
        ],
    }


# ---------------- Waitlist ----------------
@api.post("/waitlist")
async def join_waitlist(payload: WaitlistIn):
    await db.waitlist.update_one(
        {"email": payload.email.lower(), "product_id": payload.product_id},
        {"$set": {"email": payload.email.lower(), "product_id": payload.product_id,
                  "note": payload.note, "created_at": utc_now()}},
        upsert=True,
    )
    return {"ok": True}


@api.get("/admin/waitlist")
async def list_waitlist(admin: dict = Depends(get_admin_user)):
    docs = await db.waitlist.find().sort("created_at", -1).to_list(500)
    return [
        {"email": d["email"], "product_id": d.get("product_id"),
         "note": d.get("note", ""), "created_at": d.get("created_at")}
        for d in docs
    ]


@api.get("/")
async def root():
    return {"message": "PokeCoins API online"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEED_PRODUCTS = [
    {"name": "550 Pokécoins", "description": "Instant Pokécoin top-up delivered to your account within the hour.",
     "category": "pokecoin_bundle", "price": 4.99, "coins": 550, "badge": "STARTER",
     "is_featured": True, "image_url": "/images/coins-stack.jpg"},
    {"name": "1,200 Pokécoins", "description": "Mid-tier stack. Best value per coin for regular raiders.",
     "category": "pokecoin_bundle", "price": 8.99, "coins": 1200, "badge": "POPULAR",
     "is_featured": True, "image_url": "/images/coins-stack.jpg"},
    {"name": "5,200 Pokécoins", "description": "Whale stack. Storage, incubators, remote passes — all covered.",
     "category": "pokecoin_bundle", "price": 29.99, "coins": 5200, "badge": "MAX",
     "is_featured": True, "image_url": "/images/snorlax.jpg"},
    {"name": "GO Fest Global Ticket", "description": "Full weekend access pass. Requires a Pokécoin bundle in cart.",
     "category": "event_pass", "price": 14.99, "badge": "EVENT",
     "is_featured": True, "image_url": "/images/event-pass.jpg"},
    {"name": "Ghost Hour Raid Pass", "description": "Gengar Mega raid weekend timed research pass.",
     "category": "event_pass", "price": 6.99, "badge": "LIMITED",
     "is_featured": True, "image_url": "/images/gengar.jpg"},
    {"name": "Shundo Hunt — Single Target", "description": "Location-simulated shundo hunting via iTools, PGTools, RegiBot & Shungo. Launching soon.",
     "category": "shundo_service", "price": 49.99, "badge": "COMING SOON", "coming_soon": True,
     "image_url": "/images/psyduck.jpg"},
    {"name": "Platinum Medal — Single Badge",
     "description": "Operator grind service to push any single medal to Platinum. Standalone or bundled with coins.",
     "category": "medals", "price": 24.99, "msrp": 49.99, "badge": "SERVICE",
     "is_featured": True, "image_url": "/images/platinum-medal.jpg"},
    {"name": "Platinum Medal — Full Set Grind",
     "description": "Full sweep of the medal board to Platinum, handled by our operator fleet across multiple sessions.",
     "category": "medals", "price": 99.99, "msrp": 199.99, "badge": "BEST VALUE",
     "is_featured": True, "image_url": "/images/platinum-medal-set.jpg"},
    {"name": "1M Stardust Farming",
     "description": "Operator-farmed 1,000,000 Stardust delivered to your account. Ideal for a few second moves and trades.",
     "category": "stardust", "price": 19.99, "msrp": 39.99, "badge": "STARTER",
     "is_featured": True, "image_url": "/images/stardust.jpg"},
    {"name": "5M Stardust Farming",
     "description": "5,000,000 Stardust farmed across dedicated sessions. Enough to power up a full raid squad.",
     "category": "stardust", "price": 79.99, "msrp": 159.99, "badge": "POPULAR",
     "is_featured": True, "image_url": "/images/stardust.jpg"},
    {"name": "10M Stardust Farming",
     "description": "10,000,000 Stardust bulk farm. Our biggest dust drop — second moves, trades and max PvP builds covered.",
     "category": "stardust", "price": 139.99, "msrp": 299.99, "badge": "MAX",
     "is_featured": True, "image_url": "/images/stardust.jpg"},
    {"name": "Shundo Hunt — Community Day Background Target",
     "description": "Operators run your account in the background all Community Day, chasing the featured shiny-hundo while you go about your day. Launching soon.",
     "category": "shundo_service", "price": 79.99, "badge": "COMING SOON", "coming_soon": True,
     "image_url": "/images/gengar.jpg"},
]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.orders.create_index("user_id")
    await db.messages.create_index("order_id")
    await db.notifications.create_index("user_id")
    await db.checkout_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.visits.create_index("expires_at", expireAfterSeconds=0)
    await db.visits.create_index([("ip", 1), ("day", 1)], unique=True)
    await db.checkout_sessions.create_index("invoice_id")
    await db.webhook_events.create_index("event_key", unique=True)
    await db.coupons.create_index("code", unique=True)
    await db.coupon_redemptions.create_index([("code", 1), ("email", 1)], unique=True)

    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Forge Admin", "role": "admin", "created_at": utc_now(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        if existing.get("password_self_managed"):
            logger.info("Admin password was changed in-app; skipping env reseed.")
        else:
            await db.users.update_one({"email": admin_email},
                                      {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})

    if await db.products.count_documents({}) == 0:
        for entry in SEED_PRODUCTS:
            product = Product(**entry)
            await db.products.insert_one(product.to_mongo())


@app.on_event("shutdown")
async def shutdown():
    client.close()
