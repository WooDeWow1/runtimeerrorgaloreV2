import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import hashlib  # noqa: E402
import hmac  # noqa: E402
import secrets  # noqa: E402
import httpx  # noqa: E402
import jwt  # noqa: E402
from bson import ObjectId  # noqa: E402
from bson.errors import InvalidId  # noqa: E402
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from models import (  # noqa: E402
    BannerSettings,
    CATEGORIES,
    NO_DISCOUNT_CATEGORIES,
    NO_DISCOUNT_SELLAUTH_IDS,
    ORDER_STATUSES,
    Category,
    CategoryIn,
    CategoryMove,
    CategoryUpdate,
    CheckoutRequest,
    Coupon,
    CouponIn,
    CouponValidateRequest,
    ReviewSettings,
    Review,
    ReviewIn,
    ClaimOrderRequest,
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
import catalog_sync  # noqa: E402
import sellauth  # noqa: E402
import turnstile  # noqa: E402
from emailer import (  # noqa: E402
    admin_order_url,
    customer_message_html,
    order_tracking_html,
    order_url,
    my_orders_url,
    review_approved_html,
    send_email,
    support_email,
    support_reply_html,
)

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


@api.post("/auth/claim-order")
async def claim_order(payload: ClaimOrderRequest, response: Response):
    """Create an account from a completed guest order and attach that buyer's orders to it."""
    order = await db.orders.find_one({"_id": oid(payload.order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("user_id"):
        raise HTTPException(status_code=400, detail="This order already belongs to an account")
    email = order["user_email"].lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(
            status_code=400,
            detail="You already have an account with this email — sign in to see this order.",
        )
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name.strip() or email.split("@")[0],
        "role": "customer",
        "created_at": utc_now(),
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    user_id = str(result.inserted_id)
    # Adopt every unclaimed order this buyer placed with the same email (case-insensitive,
    # since older orders were not normalised on write).
    claimed = await db.orders.update_many(
        {
            "user_email": {"$regex": f"^{re.escape(email)}$", "$options": "i"},
            "$or": [{"user_id": ""}, {"user_id": {"$exists": False}}],
        },
        {"$set": {"user_id": user_id, "updated_at": utc_now()}},
    )
    set_auth_cookies(response, user_id, email, "customer")
    return {
        "user": public_user(doc),
        "access_token": create_access_token(user_id, email, "customer"),
        "orders_claimed": claimed.modified_count,
    }


@api.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    email = payload.email.lower()
    # Behind the ingress request.client.host is the pod IP and rotates, which let an
    # attacker sidestep the lockout: key on the forwarded client IP instead.
    identifier = f"{client_ip(request)}:{email}"
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


# ---------------- Categories ----------------
SEED_CATEGORIES = [
    {"key": "pokecoin_bundle", "label": "Pokécoins", "note": "Required for passes"},
    {"key": "event_pass", "label": "Event Passes", "note": "Bundle required"},
    {"key": "pokelid", "label": "PokéLid Stamp Rally", "note": "Account login service"},
    {"key": "medals", "label": "Platinum Medals", "note": "Standalone or bundled"},
    {"key": "stardust", "label": "Stardust", "note": "Farmed by operators"},
    {"key": "shundo_service", "label": "Shundo Hunting (Waitlist)", "note": "Operator fleet",
     "coming_soon": True},
]


def slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "category"


async def category_keys() -> list[str]:
    keys = [d["key"] async for d in db.categories.find({}, {"key": 1})]
    return keys or CATEGORIES


async def assert_category(key: str) -> None:
    if key not in await category_keys():
        raise HTTPException(status_code=400, detail="Invalid category")


@api.get("/categories")
async def list_categories():
    docs = await db.categories.find().sort("order", 1).to_list(100)
    return [Category.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/admin/categories")
async def create_category(payload: CategoryIn, admin: dict = Depends(get_admin_user)):
    key = slugify(payload.label)
    if await db.categories.find_one({"key": key}):
        raise HTTPException(status_code=400, detail="A category with that name already exists")
    last = await db.categories.find().sort("order", -1).to_list(1)
    category = Category(key=key, label=payload.label.strip(), note=payload.note,
                        coming_soon=payload.coming_soon,
                        order=(last[0]["order"] + 1) if last else 0)
    result = await db.categories.insert_one(category.to_mongo())
    doc = await db.categories.find_one({"_id": result.inserted_id})
    return Category.from_mongo(doc).model_dump(by_alias=False)


@api.put("/admin/categories/{category_id}")
async def update_category(category_id: str, payload: CategoryUpdate,
                          admin: dict = Depends(get_admin_user)):
    updates = payload.model_dump(exclude_unset=True)
    if "label" in updates:
        updates["label"] = updates["label"].strip()
    if updates:
        result = await db.categories.update_one({"_id": oid(category_id)}, {"$set": updates})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Category not found")
    doc = await db.categories.find_one({"_id": oid(category_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return Category.from_mongo(doc).model_dump(by_alias=False)


@api.post("/admin/categories/{category_id}/move")
async def move_category(category_id: str, payload: CategoryMove,
                        admin: dict = Depends(get_admin_user)):
    docs = await db.categories.find().sort("order", 1).to_list(100)
    index = next((n for n, d in enumerate(docs) if str(d["_id"]) == category_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Category not found")
    swap = index - 1 if payload.direction == "up" else index + 1
    if 0 <= swap < len(docs):
        docs[index], docs[swap] = docs[swap], docs[index]
    for n, d in enumerate(docs):
        await db.categories.update_one({"_id": d["_id"]}, {"$set": {"order": n}})
    return await list_categories()


@api.delete("/admin/categories/{category_id}")
async def delete_category(category_id: str, admin: dict = Depends(get_admin_user)):
    doc = await db.categories.find_one({"_id": oid(category_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    in_use = await db.products.count_documents({"category": doc["key"]})
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"{in_use} product(s) still use this category — move or delete them first.",
        )
    await db.categories.delete_one({"_id": doc["_id"]})
    return {"ok": True}


@api.get("/admin/sellauth/products/{sellauth_product_id}")
async def lookup_sellauth_product(sellauth_product_id: int, admin: dict = Depends(get_admin_user)):
    """Resolve a SellAuth product id into its variant id, live price and name."""
    try:
        return await sellauth.fetch_product(sellauth_product_id)
    except sellauth.SellAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def sellauth_fields(sellauth_product_id: Optional[int]) -> dict:
    """Pull the variant id and live price for a SellAuth product, ignoring lookup failures."""
    if not sellauth_product_id:
        return {}
    try:
        remote = await sellauth.fetch_product(sellauth_product_id)
    except (sellauth.SellAuthError, httpx.HTTPError) as exc:
        logger.warning("SellAuth lookup failed for %s: %s", sellauth_product_id, exc)
        return {}
    return {"sellauth_variant_id": remote["sellauth_variant_id"], "price": remote["price"]}


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
    await assert_category(payload.category)
    data = payload.model_dump()
    data.update(await sellauth_fields(payload.sellauth_product_id))
    product = Product(**data)
    result = await db.products.insert_one(product.to_mongo())
    doc = await db.products.find_one({"_id": result.inserted_id})
    return Product.from_mongo(doc).model_dump(by_alias=False)


@api.put("/products/{product_id}")
async def update_product(product_id: str, payload: ProductUpdate, admin: dict = Depends(get_admin_user)):
    if payload.category is not None:
        await assert_category(payload.category)
    existing = await db.products.find_one({"_id": oid(product_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    # Only touch the fields the caller actually sent, so flags like is_featured survive an edit.
    updates = payload.model_dump(exclude_unset=True)
    if "sellauth_product_id" in updates and updates["sellauth_product_id"] != existing.get("sellauth_product_id"):
        updates.update(await sellauth_fields(updates["sellauth_product_id"]))
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


async def resolve_items(entries) -> List[OrderItem]:
    items: List[OrderItem] = []
    for entry in entries:
        doc = await db.products.find_one({"_id": oid(entry.product_id), "active": True})
        if not doc:
            raise HTTPException(status_code=400, detail="A product in your cart is unavailable")
        if doc.get("coming_soon"):
            raise HTTPException(status_code=400, detail=f"{doc['name']} is not available yet")
        price = float(doc["price"])
        variant_label = ""
        variant_id = doc.get("sellauth_variant_id")
        variants = doc.get("variants") or []
        if variants:
            chosen = next(
                (v for v in variants if int(v["sellauth_variant_id"]) == (entry.variant_id or 0)),
                variants[0],
            )
            if entry.variant_id and int(chosen["sellauth_variant_id"]) != int(entry.variant_id):
                raise HTTPException(
                    status_code=400, detail=f"That option is no longer available for {doc['name']}"
                )
            price = float(chosen["price"])
            variant_label = chosen["label"]
            variant_id = int(chosen["sellauth_variant_id"])
        items.append(OrderItem(
            product_id=str(doc["_id"]), name=doc["name"], category=doc["category"],
            price=price, quantity=entry.quantity, variant_label=variant_label,
            sellauth_product_id=doc.get("sellauth_product_id"),
            sellauth_variant_id=variant_id,
        ))
    return items


def assert_cart_rules(items: List[OrderItem]) -> None:
    """Event Passes ride along with another product: never alone, never more than one."""
    passes = sum(i.quantity for i in items if i.category == "event_pass")
    others = [i for i in items if i.category != "event_pass"]
    if passes and not others:
        raise HTTPException(
            status_code=400,
            detail="An Event Pass cannot be bought on its own — add Pokécoins, Stardust or a "
                   "Medal bundle to your cart.",
        )
    if passes > 1:
        raise HTTPException(
            status_code=400, detail="Only one Event Pass per order. Please check out separately."
        )


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


# ---------------- Coupons (this site owns discounts; SellAuth only takes the money) ----------------
def discount_eligible(item: OrderItem, coupon: dict) -> bool:
    """Event Passes can never be discounted — blocked by category AND by SellAuth product id."""
    if item.category in NO_DISCOUNT_CATEGORIES:
        return False
    if item.sellauth_product_id and int(item.sellauth_product_id) in NO_DISCOUNT_SELLAUTH_IDS:
        return False
    if item.category in (coupon.get("excluded_categories") or []):
        return False
    if item.product_id in (coupon.get("excluded_product_ids") or []):
        return False
    return True


async def load_coupon(code: str, email: str) -> dict:
    coupon = await db.coupons.find_one({"code": code.strip().upper()})
    if not coupon or not coupon.get("active", True):
        raise HTTPException(status_code=400, detail="That discount code is not valid")
    expires_at = coupon.get("expires_at")
    if expires_at and expires_at.replace(tzinfo=timezone.utc) < utc_now():
        raise HTTPException(status_code=400, detail="That discount code has expired")
    max_uses = coupon.get("max_uses")
    if max_uses and coupon.get("used_count", 0) >= max_uses:
        raise HTTPException(status_code=400, detail="That discount code has been fully redeemed")
    if coupon.get("one_per_customer") and email:
        used = await db.coupon_redemptions.find_one({"code": coupon["code"], "email": email.lower()})
        if used:
            raise HTTPException(status_code=400, detail="You have already used this discount code")
    # A review reward belongs to the customer who earned it and to nobody else.
    if coupon.get("source") == "auto" and coupon.get("issued_to"):
        if email.lower() != coupon["issued_to"].lower():
            raise HTTPException(status_code=400, detail="That discount code is not valid")
    return coupon


def line_key(item: OrderItem) -> str:
    """A cart line is a product + chosen variant."""
    return f"{item.product_id}:{item.sellauth_variant_id or ''}"


def assert_coupon_fits(coupon: dict, subtotal: float, eligible_subtotal: float) -> None:
    min_subtotal = coupon.get("min_subtotal")
    if min_subtotal and subtotal < float(min_subtotal):
        raise HTTPException(
            status_code=400,
            detail=f"This code needs a cart of at least ${float(min_subtotal):.2f}",
        )
    if eligible_subtotal <= 0:
        raise HTTPException(
            status_code=400,
            detail="This code does not apply to any item in your cart — it cannot be used on "
                   "Event Passes. Add an eligible item to save.",
        )


def discount_amount(coupon: dict, eligible_subtotal: float) -> float:
    if coupon.get("discount_type", "percent") == "fixed":
        raw = float(coupon.get("amount_off") or 0)
    else:
        raw = eligible_subtotal * float(coupon.get("percent_off") or 0) / 100
    # Never discount below a chargeable amount.
    discount = round(min(raw, max(eligible_subtotal - MIN_CHARGE, 0)), 2)
    if discount <= 0:
        raise HTTPException(status_code=400, detail="That code gives no discount on this cart")
    return discount


def compute_discount(coupon: dict, items: List[OrderItem]) -> dict:
    subtotal = round(sum(i.price * i.quantity for i in items), 2)
    eligible = [i for i in items if discount_eligible(i, coupon)]
    eligible_subtotal = round(sum(i.price * i.quantity for i in eligible), 2)
    assert_coupon_fits(coupon, subtotal, eligible_subtotal)
    discount = discount_amount(coupon, eligible_subtotal)

    # Spread the discount across eligible lines so SellAuth receives the exact final total.
    factor = (eligible_subtotal - discount) / eligible_subtotal
    prices: dict[str, float] = {
        line_key(item): max(round(item.price * factor, 2), 0.01) for item in eligible
    }
    total = round(sum((prices.get(line_key(i), i.price)) * i.quantity for i in items), 2)
    percent_value = (
        float(coupon["percent_off"])
        if coupon.get("discount_type", "percent") == "percent" and coupon.get("percent_off")
        else round((subtotal - total) / subtotal * 100, 1) if subtotal else 0
    )
    return {
        "code": coupon["code"],
        "subtotal": subtotal,
        "eligible_subtotal": eligible_subtotal,
        "discount": round(subtotal - total, 2),
        "total": total,
        "discount_type": coupon.get("discount_type", "percent"),
        "percent_off": coupon.get("percent_off"),
        "amount_off": coupon.get("amount_off"),
        "percent_label": f"{percent_value:g}%",
        "unit_prices": prices,
        "excluded_names": [i.name for i in items if line_key(i) not in prices],
    }


@api.post("/coupons/validate")
async def validate_coupon(payload: CouponValidateRequest, user: Optional[dict] = Depends(get_optional_user)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    email = (user["email"] if user else (payload.email or "")).lower()
    coupon = await load_coupon(payload.code, email)
    items = await resolve_items(payload.items)
    result = compute_discount(coupon, items)
    result.pop("unit_prices", None)
    return result


async def assert_coupon_payload(payload: CouponIn) -> None:
    if payload.discount_type == "percent" and not payload.percent_off:
        raise HTTPException(status_code=400, detail="Enter a percentage to take off")
    if payload.discount_type == "fixed" and not payload.amount_off:
        raise HTTPException(status_code=400, detail="Enter a dollar amount to take off")
    known = await category_keys()
    for key in payload.excluded_categories or []:
        if key not in known:
            raise HTTPException(status_code=400, detail=f"Unknown category: {key}")


@api.get("/admin/coupons")
async def list_coupons(source: Optional[str] = None, admin: dict = Depends(get_admin_user)):
    await sweep_auto_coupons()
    query = {} if not source else (
        {"source": "auto"} if source == "auto" else {"source": {"$ne": "auto"}}
    )
    docs = await db.coupons.find(query).sort("created_at", -1).to_list(200)
    return [Coupon.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/admin/coupons")
async def create_coupon(payload: CouponIn, admin: dict = Depends(get_admin_user)):
    code = payload.code.strip().upper()
    if await db.coupons.find_one({"code": code}):
        raise HTTPException(status_code=400, detail="That code already exists")
    await assert_coupon_payload(payload)
    coupon = Coupon(**{**payload.model_dump(), "code": code})
    result = await db.coupons.insert_one(coupon.to_mongo())
    doc = await db.coupons.find_one({"_id": result.inserted_id})
    return Coupon.from_mongo(doc).model_dump(by_alias=False)


@api.put("/admin/coupons/{coupon_id}")
async def update_coupon(coupon_id: str, payload: CouponIn, admin: dict = Depends(get_admin_user)):
    code = payload.code.strip().upper()
    await assert_coupon_payload(payload)
    clash = await db.coupons.find_one({"code": code, "_id": {"$ne": oid(coupon_id)}})
    if clash:
        raise HTTPException(status_code=400, detail="That code already exists")
    updates = {**payload.model_dump(), "code": code}
    result = await db.coupons.update_one({"_id": oid(coupon_id)}, {"$set": updates})
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


async def price_cart(items: List[OrderItem], coupon_code: Optional[str], email: str) -> dict:
    """This site owns discounts: price the cart here, then hand SellAuth the final total."""
    subtotal = round(sum(i.price * i.quantity for i in items), 2)
    if not coupon_code:
        return {"subtotal": subtotal, "total": subtotal, "discount": 0.0, "unit_prices": {}}
    coupon = await load_coupon(coupon_code, email)
    priced = compute_discount(coupon, items)
    return {
        "subtotal": subtotal,
        "total": priced["total"],
        "discount": priced["discount"],
        "unit_prices": priced["unit_prices"],
    }


def sellauth_cart(items: List[OrderItem], unit_prices: dict) -> list[dict]:
    """Discounted lines carry a custom price; everything else stays a catalog item."""
    cart = []
    for i in items:
        entry = i.model_dump()
        if line_key(i) in unit_prices:
            entry["custom_price"] = unit_prices[line_key(i)]
        cart.append(entry)
    return cart


@api.post("/orders/checkout")
async def checkout(payload: CheckoutRequest, user: Optional[dict] = Depends(get_optional_user)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    items = await resolve_items(payload.items)
    assert_cart_rules(items)

    user_id = str(user["_id"]) if user else ""
    email = (user["email"] if user else (payload.email or "")).lower()
    if not email:
        raise HTTPException(status_code=400, detail="An email address is required for guest checkout")

    coupon_code = (payload.coupon_code or "").strip().upper() or None
    priced = await price_cart(items, coupon_code, email)

    # Nothing is written to `orders` yet: a spam-resistant temporary session with a 30 min TTL.
    session_doc = {
        "items": [i.model_dump() for i in items],
        "total": priced["total"],
        "subtotal": priced["subtotal"],
        "discount": priced["discount"],
        "coupon_code": coupon_code,
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

    try:
        checkout_data = await sellauth.create_checkout(
            items=sellauth_cart(items, priced["unit_prices"]), email=email, session_id=session_id,
        )
    except sellauth.SellAuthError as exc:
        # 4xx so the real reason reaches the buyer: proxies replace 5xx bodies with their own page.
        await db.checkout_sessions.delete_one({"_id": result.inserted_id})
        raise HTTPException(status_code=400, detail=str(exc))

    await db.checkout_sessions.update_one(
        {"_id": result.inserted_id},
        {"$set": {"invoice_id": checkout_data["invoice_id"], "checkout_url": checkout_data["url"]}},
    )
    return {
        "checkout_url": checkout_data["url"],
        "session_id": session_id,
        "invoice_id": checkout_data["invoice_id"],
    }


async def record_redemption(session: dict, order_id: str) -> None:
    """Count the coupon use only once the money actually landed. Auto (review) coupons keep
    their row after redemption so support can still look the code up."""
    if not session.get("coupon_code"):
        return
    try:
        await db.coupons.update_one(
            {"code": session["coupon_code"]},
            {"$inc": {"used_count": 1},
             "$set": {"redeemed_at": utc_now(), "redeemed_order_id": order_id}},
        )
        await db.coupon_redemptions.update_one(
            {"code": session["coupon_code"], "email": session["email"].lower()},
            {"$set": {"order_id": order_id, "redeemed_at": utc_now()}},
            upsert=True,
        )
    except Exception as exc:
        logger.error("Could not record coupon redemption: %s", exc)


async def send_order_confirmation(session: dict, order_id: str) -> None:
    """A provider hiccup must never undo a paid order, so this swallows its errors."""
    try:
        await send_email(
            to=session["email"],
            subject=f"Payment received — track your {os.environ['EMAIL_FROM_NAME']} order",
            html=order_tracking_html(
                order_id=order_id,
                tracking_url=order_url({"origin_url": session.get("origin_url", ""), "id": order_id}),
                total=session["total"],
                item_lines=[
                    f"{i['name']}{' — ' + i['variant_label'] if i.get('variant_label') else ''} x{i['quantity']}"
                    for i in session["items"]
                ],
            ),
        )
    except Exception as exc:
        logger.error("Order confirmation email failed for %s: %s", order_id, exc)


async def create_order_from_session(session: dict) -> Optional[str]:
    """Promote a paid checkout session into a permanent order. Idempotent."""
    if session.get("order_id"):
        return session["order_id"]
    order = Order(
        user_id=session.get("user_id", ""),
        user_email=session["email"],
        origin_url=session.get("origin_url", ""),
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
    await record_redemption(session, order_id)
    await db.checkout_sessions.update_one(
        {"_id": session["_id"]}, {"$set": {"status": "paid", "order_id": order_id}}
    )
    await notify(session.get("user_id", ""), order_id, "Order received",
                 "Payment confirmed. Your order is queued — an operator will pick it up shortly.")
    await send_order_confirmation(session, order_id)
    return order_id


def verify_webhook_signature(raw: bytes, signature: Optional[str]) -> bool:
    if not signature:
        return False
    expected = hmac.new(SELLAUTH_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def webhook_signature_ok(raw: bytes, request: Request) -> bool:
    signature = (
        request.headers.get("signature")
        or request.headers.get("x-signature")
        or request.headers.get("x-sellauth-signature")
    )
    if verify_webhook_signature(raw, signature):
        return True
    return request.query_params.get("secret") == SELLAUTH_WEBHOOK_SECRET


def _unwrap_invoice(payload: dict) -> dict:
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else payload
    if isinstance(payload.get("data"), dict) and not invoice.get("id"):
        return payload["data"]
    return invoice


def _session_id_from(invoice: dict, payload: dict) -> Optional[str]:
    custom = invoice.get("custom_fields") or payload.get("custom_fields") or {}
    if isinstance(custom, dict) and custom.get("checkout_session_id"):
        return custom["checkout_session_id"]
    meta = invoice.get("metadata") or payload.get("metadata")
    if isinstance(meta, dict):
        return meta.get("checkout_session_id")
    if isinstance(meta, list) and meta:
        return str(meta[0])
    return None


def read_invoice(payload: dict) -> tuple[dict, str, Optional[str]]:
    """SellAuth nests the invoice differently per event, so normalise it here."""
    invoice = _unwrap_invoice(payload)
    invoice_id = str(invoice.get("id") or invoice.get("invoice_id") or "")
    return invoice, invoice_id, _session_id_from(invoice, payload)


async def find_session(session_id: Optional[str], invoice_id: str) -> Optional[dict]:
    if session_id:
        try:
            session = await db.checkout_sessions.find_one({"_id": oid(session_id)})
        except HTTPException:
            session = None
        if session:
            return session
    if invoice_id:
        return await db.checkout_sessions.find_one({"invoice_id": invoice_id})
    return None


async def invoice_is_paid(invoice: dict, invoice_id: str) -> bool:
    """Trust the payload, but re-read from SellAuth before rejecting a payment."""
    if sellauth.is_paid(invoice):
        return True
    if not invoice_id:
        return False
    fresh = await sellauth.get_invoice(invoice_id)
    return bool(fresh and sellauth.is_paid(fresh))


@app.post("/api/webhooks/sellauth")
async def sellauth_webhook(request: Request):
    raw = await request.body()
    if not webhook_signature_ok(raw, request):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    invoice, invoice_id, session_id = read_invoice(payload)

    event_key = f"{invoice_id}:{hashlib.sha256(raw).hexdigest()}"
    if await db.webhook_events.find_one({"event_key": event_key}):
        return {"ok": True, "duplicate": True}

    session = await find_session(session_id, invoice_id)
    if session is None:
        logger.warning("SellAuth webhook for unknown session/invoice %s", invoice_id)
        return {"ok": True, "matched": False}

    if not await invoice_is_paid(invoice, invoice_id):
        return {"ok": True, "paid": False}

    order_id = await create_order_from_session(session)
    try:
        await db.webhook_events.insert_one({"event_key": event_key, "received_at": utc_now()})
    except Exception as exc:
        logger.info("Webhook replay guard not stored for %s: %s", invoice_id, exc)
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
    orders = []
    for doc in docs:
        data = order_response(doc)
        data["unread_count"] = await unread_for_order(doc)
        orders.append(data)
    return orders


async def unread_for_order(order: dict) -> int:
    """Customer messages that arrived after the admin last opened or answered this order."""
    seen = order.get("admin_read_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)
    return await db.messages.count_documents({
        "order_id": str(order["_id"]),
        "sender_role": {"$ne": "admin"},
        "created_at": {"$gt": seen},
    })


@api.get("/admin/unread")
async def admin_unread(admin: dict = Depends(get_admin_user)):
    """Totals for the sidebar dot: how many orders are waiting on a reply."""
    docs = await db.orders.find({}, {"admin_read_at": 1}).to_list(500)
    orders, messages = 0, 0
    for doc in docs:
        count = await unread_for_order(doc)
        if count:
            orders += 1
            messages += count
    return {"orders": orders, "messages": messages}


@api.post("/admin/orders/{order_id}/read")
async def mark_order_read(order_id: str, admin: dict = Depends(get_admin_user)):
    result = await db.orders.update_one({"_id": oid(order_id)}, {"$set": {"admin_read_at": utc_now()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"ok": True}


@api.delete("/admin/orders/{order_id}")
async def delete_order(order_id: str, admin: dict = Depends(get_admin_user)):
    """Hard delete, used to clear out test orders. Takes the order's chat, notifications and
    review with it so nothing is left orphaned."""
    result = await db.orders.delete_one({"_id": oid(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.messages.delete_many({"order_id": order_id})
    await db.notifications.delete_many({"order_id": order_id})
    await db.reviews.delete_many({"order_id": order_id})
    return {"ok": True}


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

    def safe_decrypt(token: Optional[str]) -> str:
        """Legacy/seeded rows can hold unreadable ciphertext: say so instead of 500ing."""
        if not token:
            return "(not provided)"
        try:
            return decrypt_secret(token)
        except Exception as exc:
            logger.warning("Could not decrypt credentials for order %s: %s", order_id, exc)
            return "(unreadable — ask the customer in chat)"

    return {
        "ptc_username": safe_decrypt(doc.get("ptc_username_enc")),
        "ptc_password": safe_decrypt(doc.get("ptc_password_enc")),
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
        await db.orders.update_one({"_id": order["_id"]}, {"$set": {"admin_read_at": utc_now()}})
        await notify(order.get("user_id", ""), order_id, "New message from support", payload.body[:140])
        # Guests have no bell, so email is the only way they hear back.
        try:
            await send_email(
                to=order["user_email"],
                subject=f"Reply from {os.environ['EMAIL_FROM_NAME']} support",
                html=support_reply_html(
                    order_id=order_id,
                    body=payload.body,
                    order_url=order_url({"origin_url": order.get("origin_url", ""), "id": order_id}),
                ),
            )
        except Exception as exc:
            logger.error("Support reply email failed for %s: %s", order_id, exc)
    else:
        # Ping the support inbox so an operator can jump straight into the order.
        try:
            await send_email(
                to=support_email() or order["user_email"],
                subject=f"New Customer Message - Order #{order_id[-8:]}",
                html=customer_message_html(
                    order_id=order_id,
                    body=payload.body,
                    customer_email=order.get("user_email", ""),
                    admin_url=admin_order_url(order_id),
                ),
            )
        except Exception as exc:
            logger.error("Customer message alert failed for %s: %s", order_id, exc)
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


@api.get("/settings/banner")
async def get_banner():
    doc = await db.settings.find_one({"_id": "banner"})
    if not doc:
        return BannerSettings().model_dump()
    return BannerSettings(**{k: v for k, v in doc.items() if k != "_id"}).model_dump()


@api.put("/admin/settings/banner")
async def update_banner(payload: BannerSettings, admin: dict = Depends(get_admin_user)):
    if payload.link_url and not payload.link_url.startswith(("https://", "/")):
        raise HTTPException(status_code=400, detail="Banner link must be an https:// or / path URL")
    await db.settings.update_one(
        {"_id": "banner"}, {"$set": {**payload.model_dump(), "updated_at": utc_now()}}, upsert=True
    )
    return payload.model_dump()


# ---------------- Catalog sync (preview -> production) ----------------
async def _sync_catalog(apply: bool) -> dict:
    docs = await db.products.find().sort("name", 1).to_list(500)
    source = [Product.from_mongo(d).model_dump(by_alias=False) for d in docs]
    try:
        return await catalog_sync.plan(source, apply=apply)
    except catalog_sync.SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach production: {exc}")


@api.get("/admin/sync/catalog")
async def sync_catalog_preview(admin: dict = Depends(get_admin_user)):
    return await _sync_catalog(apply=False)


@api.post("/admin/sync/catalog")
async def sync_catalog_apply(admin: dict = Depends(get_admin_user)):
    return await _sync_catalog(apply=True)


# ---------------- Review reward coupons (extends the existing coupon engine) ----------------
REVIEW_SETTINGS_DEFAULTS = {"enabled": True, "percent_off": 5.0, "expiry_days": 7}


async def review_settings() -> dict:
    doc = await db.settings.find_one({"_id": "review_coupon"}) or {}
    return {**REVIEW_SETTINGS_DEFAULTS, **{k: doc[k] for k in REVIEW_SETTINGS_DEFAULTS if k in doc}}


@api.get("/admin/settings/reviews")
async def get_review_settings(admin: dict = Depends(get_admin_user)):
    return await review_settings()


@api.put("/admin/settings/reviews")
async def put_review_settings(payload: ReviewSettings, admin: dict = Depends(get_admin_user)):
    await db.settings.update_one({"_id": "review_coupon"}, {"$set": payload.model_dump()}, upsert=True)
    return await review_settings()


AUTO_COUPON_RETENTION_DAYS = 30


async def sweep_auto_coupons() -> int:
    """Spent and expired auto coupons stay on file for 30 days so support can look a code up.
    Manual coupons — banner code, affiliate codes — are never touched."""
    cutoff = utc_now() - timedelta(days=AUTO_COUPON_RETENTION_DAYS)
    result = await db.coupons.delete_many({
        "source": "auto",
        "created_at": {"$lt": cutoff},
        "$or": [
            {"used_count": {"$gte": 1}},
            {"expires_at": {"$lt": utc_now()}},
        ],
    })
    return result.deleted_count


async def issue_review_coupon(review_id: str, user_id: str, email: str) -> Optional[dict]:
    """One unique single-use code per approved review. Event Pass exclusion is inherited
    from the shared coupon engine, so nothing extra is configured here."""
    settings = await review_settings()
    if not settings["enabled"]:
        return None
    await sweep_auto_coupons()
    expires_at = utc_now() + timedelta(days=int(settings["expiry_days"]))
    for _ in range(5):
        code = f"THANKS{secrets.token_hex(3).upper()}"
        coupon = Coupon(
            code=code, source="auto", review_id=review_id, order_id=None, issued_to=email,
            discount_type="percent", percent_off=float(settings["percent_off"]),
            one_per_customer=True, max_uses=1, expires_at=expires_at,
            note="Thanks for your review",
        )
        try:
            await db.coupons.insert_one(coupon.to_mongo())
        except DuplicateKeyError:
            continue
        return {"code": code, "percent_off": float(settings["percent_off"]),
                "expires_at": expires_at.isoformat()}
    logger.error("Could not generate a unique review coupon for %s", review_id)
    return None


# ---------------- Reviews ----------------
async def review_author(order: dict, user: Optional[dict]) -> tuple[str, str, str]:
    """Only the buyer may review an order. Guests keep access to their own order id."""
    if user:
        if order.get("user_id") and order["user_id"] != str(user["_id"]):
            raise HTTPException(status_code=403, detail="That order belongs to another account")
        name = (user.get("name") or user["email"].split("@")[0]).strip()
        return str(user["_id"]), user["email"], name.split(" ")[0].title()
    if order.get("user_id"):
        raise HTTPException(status_code=401, detail="Sign in to review this order")
    return "", order["user_email"], order["user_email"].split("@")[0].title()


@api.post("/reviews")
async def create_review(payload: ReviewIn, request: Request,
                        user: Optional[dict] = Depends(get_optional_user)):
    order = await db.orders.find_one({"_id": oid(payload.order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") != "completed":
        raise HTTPException(status_code=400, detail="You can review an order once it is completed")
    if await db.reviews.find_one({"order_id": payload.order_id}):
        raise HTTPException(status_code=400, detail="You have already reviewed this order")
    if order.get("review_declined"):
        raise HTTPException(status_code=400, detail="This order is no longer eligible for a review")

    if not turnstile.bypassed_request(request):
        ok, reason = await turnstile.verify(
            payload.turnstile_token, request.client.host if request.client else None
        )
        if not ok:
            raise HTTPException(status_code=400, detail=f"CAPTCHA check failed ({reason}) — please retry")

    user_id, email, first_name = await review_author(order, user)
    review = Review(order_id=payload.order_id, user_id=user_id, user_email=email,
                    first_name=first_name, rating=payload.rating,
                    title=payload.title.strip(), body=payload.body.strip())
    result = await db.reviews.insert_one(review.to_mongo())
    # The reward coupon is only created once an admin approves the review.
    return {"ok": True, "review_id": str(result.inserted_id), "coupon": None}


def coupon_state(coupon: Optional[dict]) -> dict:
    """What My Orders should show for an approved review's reward."""
    if not coupon:
        return {"state": "unavailable"}
    expires_at = coupon.get("expires_at")
    expired = bool(expires_at and expires_at.replace(tzinfo=timezone.utc) < utc_now())
    if coupon.get("used_count", 0) >= 1:
        state = "redeemed"
    elif expired or not coupon.get("active", True):
        state = "expired"
    else:
        state = "unredeemed"
    return {
        "state": state,
        "code": coupon["code"],
        "percent_off": coupon.get("percent_off"),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "redeemed_at": coupon["redeemed_at"].isoformat() if coupon.get("redeemed_at") else None,
    }


@api.get("/reviews/status")
async def review_status(order_ids: str = ""):
    """Per order: whether a review exists, and the state of any reward coupon, so My Orders
    can show the right button and keep the code visible permanently."""
    ids = [i for i in order_ids.split(",") if i]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    declined = await db.orders.find(
        {"_id": {"$in": [oid(i) for i in ids]}, "review_declined": True}, {"_id": 1}
    ).to_list(100)
    for d in declined:
        out[str(d["_id"])] = {"status": "declined"}
    docs = await db.reviews.find({"order_id": {"$in": ids}}).to_list(100)
    for d in docs:
        entry = {"status": d["status"]}
        if d["status"] == "approved":
            coupon = (
                await db.coupons.find_one({"code": d["coupon_code"]}) if d.get("coupon_code") else None
            )
            entry["coupon"] = coupon_state(coupon)
        out[d["order_id"]] = entry
    return out


@api.get("/reviews")
async def public_reviews(limit: int = 100):
    """Approved reviews only. Never leaks the email, order or full name."""
    docs = await db.reviews.find({"status": "approved"}).sort("created_at", -1).to_list(limit)
    reviews = [
        {"id": str(d["_id"]), "rating": d["rating"], "title": d.get("title", ""),
         "body": d["body"], "first_name": d["first_name"],
         "created_at": d["created_at"]}
        for d in docs
    ]
    average = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else None
    return {"reviews": reviews, "count": len(reviews), "average": average}


@api.get("/admin/reviews")
async def list_reviews(status: Optional[str] = None, admin: dict = Depends(get_admin_user)):
    query = {"status": status} if status else {}
    docs = await db.reviews.find(query).sort("created_at", -1).to_list(500)
    return [Review.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.post("/admin/reviews/{review_id}/approve")
async def approve_review(review_id: str, admin: dict = Depends(get_admin_user)):
    review = await db.reviews.find_one({"_id": oid(review_id)})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    already_approved = review.get("status") == "approved"
    await db.reviews.update_one(
        {"_id": oid(review_id)}, {"$set": {"status": "approved", "approved_at": utc_now()}}
    )
    if already_approved and review.get("coupon_code"):
        return {"ok": True, "coupon": None}

    coupon = await issue_review_coupon(review_id, review.get("user_id", ""), review["user_email"])
    if coupon:
        await db.reviews.update_one({"_id": oid(review_id)},
                                    {"$set": {"coupon_code": coupon["code"]}})
        await notify_review_approved(review["user_email"], coupon)
    return {"ok": True, "coupon": coupon}


async def notify_review_approved(email: str, coupon: dict) -> None:
    """Never let an email hiccup roll back an approval."""
    try:
        await send_email(
            to=email,
            subject=f"Your review is live — {coupon['percent_off']:g}% off your next order",
            html=review_approved_html(
                code=coupon["code"],
                percent_off=float(coupon["percent_off"]),
                expires_on=coupon["expires_at"][:10],
                orders_url=my_orders_url(),
            ),
        )
    except Exception as exc:
        logger.error("Review approval email failed for %s: %s", email, exc)


@api.delete("/admin/reviews/{review_id}")
async def delete_review(review_id: str, admin: dict = Depends(get_admin_user)):
    """Declining is a hard delete, no coupon is issued, and the order cannot be reviewed again."""
    review = await db.reviews.find_one({"_id": oid(review_id)})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    await db.reviews.delete_one({"_id": oid(review_id)})
    await db.orders.update_one({"_id": oid(review["order_id"])},
                               {"$set": {"review_declined": True}})
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@api.get("/health")
async def api_health():
    return {"status": "ok"}


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
    # Index creation and seeding are writes: keep them non-fatal so the site stays live for
    # browsing even when the database is read-only (e.g. Atlas DiskUseThresholdExceeded).
    await ensure_indexes()
    try:
        await seed_data()
    except Exception as exc:
        logger.error("Startup seeding skipped (database not writable?): %s", exc)


INDEXES = [
    ("users", "email", {"unique": True}),
    ("login_attempts", "identifier", {}),
    ("orders", "user_id", {}),
    ("messages", "order_id", {}),
    ("notifications", "user_id", {}),
    ("checkout_sessions", "expires_at", {"expireAfterSeconds": 0}),
    ("checkout_sessions", "invoice_id", {}),
    ("visits", "expires_at", {"expireAfterSeconds": 0}),
    ("visits", [("ip", 1), ("day", 1)], {"unique": True}),
    ("webhook_events", "event_key", {"unique": True}),
    ("categories", "key", {"unique": True}),
    ("coupons", "code", {"unique": True}),
    ("coupon_redemptions", [("code", 1), ("email", 1)], {"unique": True}),
    ("reviews", "order_id", {"unique": True}),
]


async def ensure_indexes():
    for collection, keys, options in INDEXES:
        try:
            await db[collection].create_index(keys, **options)
        except Exception as exc:
            logger.error("Could not create index on %s (%s): %s", collection, keys, exc)


POKELID_DESCRIPTION = (
    "We login to your account and go through the stamp rally’s. You receive an estimate of 50-100 "
    "exclusive background Pokemon (usually a Pikachu) and you may even get shiny ones! (We cannot "
    "guarantee how many shinies anyone will get, it’s all RNG)"
)

EXTRA_PRODUCTS = [
    {"name": "Japan PokéLid Stamp Rally Collection", "category": "pokelid", "price": 24.99,
     "description": POKELID_DESCRIPTION, "image_url": "/images/japanlid.jpg",
     "sellauth_product_id": 857694, "badge": "Stamp Rally"},
    {"name": "LEGO PokéLid Stamp Rally", "category": "pokelid", "price": 24.99,
     "description": POKELID_DESCRIPTION, "image_url": "/images/legolid.jpg",
     "sellauth_product_id": 857690, "badge": "Stamp Rally"},
    {"name": "GO Pass Deluxe: Mega Finale", "category": "event_pass", "price": 10.99,
     "description": "Value Varies / 1x GO Pass Mega Finale\n\n"
                    "Requires a Pokécoin bundle in cart to purchase!",
     "image_url": "/images/go-pass.png", "sellauth_product_id": 864451, "badge": "Mega Finale"},
]


SEED_VARIANTS = {
    851924: [(1508676, "Basic"), (1553265, "+ 6 Ranks"), (1553266, "Ultra Box")],
    851928: [(1508694, "Basic"), (1553263, "+10 Ranks"), (1553264, "Ultra Box")],
    864451: [(1570359, "Basic"), (1570360, "+ 10 Ranks"), (1570361, "Ultra Box")],
}


async def seed_variants():
    """Attach the Event Pass upgrade options, pricing each one from its SellAuth variant."""
    for sellauth_product_id, options in SEED_VARIANTS.items():
        doc = await db.products.find_one({"sellauth_product_id": sellauth_product_id})
        if not doc or doc.get("variants"):
            continue
        try:
            remote = await sellauth.fetch_product(sellauth_product_id)
        except (sellauth.SellAuthError, httpx.HTTPError) as exc:
            logger.warning("Could not seed variants for %s: %s", sellauth_product_id, exc)
            continue
        prices = {v["sellauth_variant_id"]: v["price"] for v in remote["variants"]}
        variants = [
            {"label": label, "sellauth_variant_id": variant_id, "price": prices[variant_id]}
            for variant_id, label in options
            if variant_id in prices
        ]
        if not variants:
            continue
        await db.products.update_one(
            {"_id": doc["_id"]},
            {"$set": {"variants": variants, "price": variants[0]["price"],
                      "sellauth_variant_id": variants[0]["sellauth_variant_id"]}},
        )


async def seed_data():
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

    for n, entry in enumerate(SEED_CATEGORIES):
        await db.categories.update_one(
            {"key": entry["key"]},
            {"$setOnInsert": {**entry, "order": n, "coming_soon": entry.get("coming_soon", False),
                              "created_at": utc_now()}},
            upsert=True,
        )

    for entry in EXTRA_PRODUCTS:
        if await db.products.find_one({"name": entry["name"]}):
            continue
        data = {**entry, **await sellauth_fields(entry.get("sellauth_product_id"))}
        await db.products.insert_one(Product(**data).to_mongo())

    await seed_variants()


@app.on_event("shutdown")
async def shutdown():
    client.close()
