"""Seed a paid guest order for automated tests. Prints JSON: {session_id, order_id, email}.

Usage: python3 /app/scripts/seed_test_order.py [email]
"""
import asyncio
import json
import sys
import uuid

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


async def main():
    email = sys.argv[1] if len(sys.argv) > 1 else f"test-it13+{uuid.uuid4().hex[:8]}@gmail.com"
    prod = await server.db.products.find_one({"category": "pokecoin_bundle"})
    session = {
        "_id": server.ObjectId(),
        "email": email,
        "items": [{"product_id": str(prod["_id"]), "name": prod["name"],
                   "category": prod["category"], "price": prod["price"], "quantity": 1}],
        "total": prod["price"], "subtotal": prod["price"], "discount": 0.0,
        "ptc_username_enc": server.encrypt_secret("testtrainer"),
        "ptc_password_enc": server.encrypt_secret("testpass1234"),
        "origin_url": "https://digital-gaming-store-7.preview.emergentagent.com",
        "user_id": "",
    }
    await server.db.checkout_sessions.insert_one(session)
    order_id = await server.create_order_from_session(session)
    print(json.dumps({"session_id": str(session["_id"]), "order_id": order_id, "email": email}))


asyncio.run(main())
