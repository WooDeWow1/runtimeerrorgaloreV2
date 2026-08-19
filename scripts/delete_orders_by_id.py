"""Delete specific test orders (and their messages/notifications) by order id."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


async def main():
    ids = sys.argv[1:]
    m = await server.db.messages.delete_many({"order_id": {"$in": ids}})
    n = await server.db.notifications.delete_many({"order_id": {"$in": ids}})
    o = await server.db.orders.delete_many({"_id": {"$in": [server.oid(i) for i in ids]}})
    print(f"deleted orders={o.deleted_count} messages={m.deleted_count} notifications={n.deleted_count}")


asyncio.run(main())
