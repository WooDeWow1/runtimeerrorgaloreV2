"""Delete test-created orders/users/messages/sessions/notifications (emails containing TEST-it13)."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

PAT = {"$regex": "TEST-it13", "$options": "i"}


async def main():
    orders = await server.db.orders.find({"user_email": PAT}).to_list(1000)
    order_ids = [str(o["_id"]) for o in orders]
    users = await server.db.users.find({"email": PAT}).to_list(1000)
    user_ids = [str(u["_id"]) for u in users]
    m = await server.db.messages.delete_many({"order_id": {"$in": order_ids}})
    n = await server.db.notifications.delete_many({"$or": [{"order_id": {"$in": order_ids}},
                                                          {"user_id": {"$in": user_ids}}]})
    o = await server.db.orders.delete_many({"user_email": PAT})
    s = await server.db.checkout_sessions.delete_many({"email": PAT})
    u = await server.db.users.delete_many({"email": PAT})
    print(f"deleted orders={o.deleted_count} sessions={s.deleted_count} users={u.deleted_count} "
          f"messages={m.deleted_count} notifications={n.deleted_count}")


asyncio.run(main())
