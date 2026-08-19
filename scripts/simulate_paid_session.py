"""Simulate a paid SellAuth invoice for a checkout session (preview testing only)."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


async def main(session_id):
    session = await server.db.checkout_sessions.find_one({"_id": server.oid(session_id)})
    if not session:
        print("session not found")
        return
    order_id = await server.create_order_from_session(session)
    print("order created:", order_id)


asyncio.run(main(sys.argv[1]))
