"""QA it14 cleanup: remove QA-created checkout sessions / orders / waitlist rows."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa

EMAIL_PATTERNS = ["qa-it14", "uitest+"]


async def main():
    for pat in EMAIL_PATTERNS:
        rx = {"$regex": pat, "$options": "i"}
        s = await server.db.checkout_sessions.delete_many({"email": rx})
        o = await server.db.orders.delete_many({"user_email": rx})
        w = await server.db.waitlist.delete_many({"email": rx})
        u = await server.db.users.delete_many({"email": rx})
        print(pat, "sessions", s.deleted_count, "orders", o.deleted_count,
              "waitlist", w.deleted_count, "users", u.deleted_count)
    left = await server.db.checkout_sessions.count_documents(
        {"email": {"$regex": "qa-it14|uitest\\+", "$options": "i"}})
    print("remaining qa sessions:", left)
    print("products:", await server.db.products.count_documents({}))


asyncio.run(main())
