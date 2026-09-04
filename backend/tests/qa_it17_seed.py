"""Seed / teardown for the iteration-17 admin UI run.

python qa_it17_seed.py create  -> prints the order id (paid order + 1 unread customer message)
python qa_it17_seed.py clean   -> removes everything it created
"""
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

with open("/app/frontend/.env") as f:
    BASE_URL = next(l.split("=", 1)[1].strip() for l in f if l.startswith("REACT_APP_BACKEND_URL=")).rstrip("/")
API = f"{BASE_URL}/api"
LOCAL_API = "http://localhost:8001/api"
SECRET = os.environ["SELLAUTH_WEBHOOK_SECRET"]
mongo = MongoClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]
MARK = "QA_IT17_UI"


def create():
    product = next(p for p in requests.get(f"{API}/products").json()
                   if p["category"] == "pokecoin_bundle" and p["active"] and not p.get("coming_soon"))
    now = datetime.now(timezone.utc)
    sid = str(db.checkout_sessions.insert_one({
        "items": [{"product_id": product["id"], "name": product["name"], "category": product["category"],
                   "price": product["price"], "quantity": 1, "variant_label": ""}],
        "subtotal": product["price"], "discount": 0.0, "total": product["price"],
        "coupon_code": None, "user_id": "", "email": "delivered@resend.dev", "origin_url": BASE_URL,
        "ptc_username_enc": f"gAAAAA{MARK}_u", "ptc_password_enc": f"gAAAAA{MARK}_p",
        "status": "awaiting_payment", "created_at": now, "expires_at": now + timedelta(minutes=30),
    }).inserted_id)
    raw = json.dumps({"invoice": {"id": f"qa-it17-ui-{uuid.uuid4().hex[:8]}", "status": "completed",
                                  "custom_fields": {"checkout_session_id": sid}}}).encode()
    r = requests.post(f"{LOCAL_API}/webhooks/sellauth", data=raw, timeout=90, headers={
        "content-type": "application/json",
        "signature": hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()})
    r.raise_for_status()
    order_id = r.json()["order_id"]
    m = requests.post(f"{API}/orders/{order_id}/messages",
                      json={"body": f"{MARK} customer needs help"}, timeout=60)
    m.raise_for_status()
    print(order_id)


def clean():
    ids = [str(d["_id"]) for d in db.orders.find({"ptc_username_enc": f"gAAAAA{MARK}_u"}, {"_id": 1})]
    for oid_ in ids:
        db.messages.delete_many({"order_id": oid_})
        db.notifications.delete_many({"order_id": oid_})
        db.orders.delete_one({"_id": ObjectId(oid_)})
    db.checkout_sessions.delete_many({"ptc_username_enc": f"gAAAAA{MARK}_u"})
    db.coupons.delete_many({"code": {"$regex": "^QA(IT17|OPC|FIX|WHK)"}})
    db.coupon_redemptions.delete_many({"code": {"$regex": "^QA(IT17|OPC|FIX|WHK)"}})
    print(f"cleaned {len(ids)} order(s)")


if __name__ == "__main__":
    {"create": create, "clean": clean}[sys.argv[1]]()
