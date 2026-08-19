"""End-to-end check of guest order -> chat -> claim account -> my orders."""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")
import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")
BASE = "http://localhost:8001/api"


async def main():
    email = f"claimtest+{uuid.uuid4().hex[:8]}@gmail.com"
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        # seed a paid guest order directly through the internal helper
        import server
        prods = (await c.get("/products")).json()
        bundle = next(p for p in prods if p["category"] == "pokecoin_bundle")
        session = {
            "_id": server.ObjectId(),
            "email": email,
            "items": [{"product_id": bundle["id"], "name": bundle["name"],
                       "category": bundle["category"],
                       "price": bundle["price"], "quantity": 1}],
            "total": bundle["price"], "subtotal": bundle["price"], "discount": 0.0,
            "ptc_username_enc": server.encrypt_secret("trainer1"),
            "ptc_password_enc": server.encrypt_secret("pw123456"),
            "origin_url": "https://digital-gaming-store-7.preview.emergentagent.com",
            "user_id": "",
        }
        await server.db.checkout_sessions.insert_one(session)
        order_id = await server.create_order_from_session(session)
        print("1. guest order created:", order_id)

        # guest can read + post in the chat without an account
        r = await c.post(f"/orders/{order_id}/messages", json={"body": "Hi, when will this start?"})
        print("2. guest chat post:", r.status_code, r.json().get("sender_role"))

        # admin replies -> notification + email to the buyer
        tok = (await c.post("/auth/login", json={"email": os.environ["ADMIN_EMAIL"],
                                                 "password": os.environ["ADMIN_PASSWORD"]})).json()["access_token"]
        ah = {"Authorization": f"Bearer {tok}"}
        r = await c.post(f"/orders/{order_id}/messages", json={"body": "On it now, thanks!"}, headers=ah)
        print("3. admin reply:", r.status_code, r.json().get("sender_role"))
        msgs = (await c.get(f"/orders/{order_id}/messages")).json()
        print("   thread:", [(m["sender_role"], m["body"][:22]) for m in msgs])

        # claim the order -> account created, order attached
        r = await c.post("/auth/claim-order", json={"order_id": order_id, "password": "hunter2pass"})
        print("4. claim:", r.status_code, r.json() if r.status_code != 200 else
              {k: r.json()[k] for k in ("orders_claimed",)}, r.json().get("user", {}).get("email"))
        token = r.json()["access_token"]
        uh = {"Authorization": f"Bearer {token}"}

        # the new account sees the order
        mine = (await c.get("/orders", headers=uh)).json()
        print("5. /orders for new account:", [o["id"] for o in mine])

        # re-claiming is refused, and a stranger cannot read the order any more
        print("6. re-claim blocked:", (await c.post("/auth/claim-order",
              json={"order_id": order_id, "password": "x123456"})).json().get("detail"))
        print("7. anonymous access now:", (await c.get(f"/orders/{order_id}")).status_code,
              (await c.get(f"/orders/{order_id}/messages")).status_code)
        print("8. owner access still:", (await c.get(f"/orders/{order_id}", headers=uh)).status_code)

        # login with the new password works
        print("9. login as claimed user:",
              (await c.post("/auth/login", json={"email": email, "password": "hunter2pass"})).status_code)

        # cleanup
        await server.db.orders.delete_one({"_id": server.oid(order_id)})
        await server.db.messages.delete_many({"order_id": order_id})
        await server.db.users.delete_one({"email": email})
        await server.db.checkout_sessions.delete_one({"_id": session["_id"]})
        print("10. cleaned up")


asyncio.run(main())
