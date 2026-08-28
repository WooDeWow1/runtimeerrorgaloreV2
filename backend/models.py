from datetime import datetime, timezone
from typing import Annotated, Any, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]

CATEGORIES = ["pokecoin_bundle", "event_pass", "pokelid", "medals", "stardust", "shundo_service"]
# Event Passes may never be discounted, by category and by SellAuth product id.
NO_DISCOUNT_CATEGORIES = ["event_pass"]
NO_DISCOUNT_SELLAUTH_IDS = [851924, 851927, 851928]
ORDER_STATUSES = ["awaiting_payment", "pending", "processing", "completed", "cancelled"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if not doc:
            return None
        return cls.model_validate(doc)


# ---------- Users ----------
class UserPublic(BaseDocument):
    email: str
    name: str
    role: str = "customer"
    created_at: datetime = Field(default_factory=utc_now)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ClaimOrderRequest(BaseModel):
    """Post-purchase signup: the email comes from the order, never from the caller."""
    order_id: str
    password: str = Field(min_length=6)
    name: str = ""


# ---------- Products ----------
class ProductVariant(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    sellauth_variant_id: int
    price: float = Field(gt=0)


class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    category: str
    price: float = Field(gt=0)
    msrp: Optional[float] = Field(default=None, gt=0)
    image_url: str = ""
    coins: Optional[int] = None
    badge: str = ""
    active: bool = True
    coming_soon: bool = False
    is_featured: bool = False
    sellauth_product_id: Optional[int] = None
    sellauth_variant_id: Optional[int] = None
    variants: List[ProductVariant] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    msrp: Optional[float] = Field(default=None, gt=0)
    image_url: Optional[str] = None
    coins: Optional[int] = Field(default=None, gt=0)
    badge: Optional[str] = None
    active: Optional[bool] = None
    coming_soon: Optional[bool] = None
    is_featured: Optional[bool] = None
    sellauth_product_id: Optional[int] = None
    sellauth_variant_id: Optional[int] = None
    variants: Optional[List[ProductVariant]] = None


class Product(BaseDocument):
    name: str
    description: str = ""
    category: str
    price: float
    msrp: Optional[float] = None
    image_url: str = ""
    coins: Optional[int] = None
    badge: str = ""
    active: bool = True
    coming_soon: bool = False
    is_featured: bool = False
    sellauth_product_id: Optional[int] = None
    sellauth_variant_id: Optional[int] = None
    variants: List[ProductVariant] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


# ---------- Categories ----------
class CategoryIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    note: str = ""
    coming_soon: bool = False


class CategoryUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    note: Optional[str] = None
    coming_soon: Optional[bool] = None


class CategoryMove(BaseModel):
    direction: Literal["up", "down"]


class Category(BaseDocument):
    key: str
    label: str
    note: str = ""
    coming_soon: bool = False
    order: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class BannerSettings(BaseModel):
    enabled: bool = False
    text: str = ""
    link_url: str = ""
    link_label: str = ""


# ---------- Orders ----------
class CartItemIn(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=50)
    variant_id: Optional[int] = None


class OrderItem(BaseModel):
    product_id: str
    name: str
    category: str
    price: float
    quantity: int
    variant_label: str = ""
    sellauth_product_id: Optional[int] = None
    sellauth_variant_id: Optional[int] = None


class CheckoutRequest(BaseModel):
    items: List[CartItemIn]
    ptc_username: str = Field(min_length=1)
    ptc_password: str = Field(min_length=1)
    origin_url: str
    email: Optional[EmailStr] = None
    coupon_code: Optional[str] = None


class Order(BaseDocument):
    user_id: str = ""
    user_email: str
    origin_url: str = ""
    items: List[OrderItem]
    total: float
    subtotal: Optional[float] = None
    discount: float = 0.0
    coupon_code: Optional[str] = None
    status: str = "awaiting_payment"
    payment_status: str = "pending"
    session_id: Optional[str] = None
    ptc_username_enc: str
    ptc_password_enc: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StatusUpdate(BaseModel):
    status: str


class FeaturedUpdate(BaseModel):
    is_featured: bool


class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    discount_type: Literal["percent", "fixed"] = "percent"
    percent_off: Optional[float] = Field(default=None, gt=0, le=100)
    amount_off: Optional[float] = Field(default=None, gt=0)
    one_per_customer: bool = False
    active: bool = True
    excluded_product_ids: List[str] = Field(default_factory=list)
    excluded_categories: List[str] = Field(default_factory=list)
    min_subtotal: Optional[float] = Field(default=None, ge=0)
    max_uses: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None
    note: str = ""


class Coupon(BaseDocument):
    code: str
    discount_type: str = "percent"
    percent_off: Optional[float] = None
    amount_off: Optional[float] = None
    one_per_customer: bool = False
    active: bool = True
    excluded_product_ids: List[str] = Field(default_factory=list)
    excluded_categories: List[str] = Field(default_factory=list)
    min_subtotal: Optional[float] = None
    max_uses: Optional[int] = None
    used_count: int = 0
    expires_at: Optional[datetime] = None
    note: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class CouponValidateRequest(BaseModel):
    code: str
    items: List["CartItemIn"]
    email: Optional[str] = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1)


class Message(BaseDocument):
    order_id: str
    sender_id: str
    sender_name: str
    sender_role: str
    body: str
    created_at: datetime = Field(default_factory=utc_now)


class Notification(BaseDocument):
    user_id: str
    order_id: Optional[str] = None
    title: str
    body: str
    read: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class WaitlistIn(BaseModel):
    email: EmailStr
    product_id: Optional[str] = None
    note: str = ""


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
