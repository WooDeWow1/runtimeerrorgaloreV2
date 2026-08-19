"""Create a paid guest order + session for UI testing. Prints the session id."""
import asyncio
import sys
import uuid

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


async def main():
    email = f"uitest+{uuid.uuid4().hex[:6]}@gmail.com"
    prod = await server.db.products.find_one({"category": "pokecoin_bundle"})
    session = {
        "_id": server.ObjectId(),
        "email": email,
        "items": [{"product_id": str(prod["_id"]), "name": prod["name"],
                   "category": prod["category"], "price": prod["price"], "quantity": 1}],
        "total": prod["price"], "subtotal": prod["price"], "discount": 0.0,
        "ptc_username_enc": server.encrypt_secret("uitrainer"),
        "ptc_password_enc": server.encrypt_secret("uipass1234"),
        "origin_url": "https://digital-gaming-store-7.preview.emergentagent.com",
        "user_id": "",
    }
    await server.db.checkout_sessions.insert_one(session)
    order_id = await server.create_order_from_session(session)
    await server.db.messages.insert_one({
        "order_id": order_id, "sender_id": "admin", "sender_name": "Operator",
        "sender_role": "admin", "body": "Hey! We are starting your order shortly.",
        "created_at": server.utc_now(),
    })
    print("SESSION_ID", str(session["_id"]))
    print("ORDER_ID", order_id)
    print("EMAIL", email)


asyncio.run(main())
