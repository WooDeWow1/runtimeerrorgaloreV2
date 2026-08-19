"""Backfill is_featured and re-activate the Stardust catalog.

Existing products predate the is_featured flag, so every live (active, non-coming-soon)
product is starred by default; unstar what you don't want from Admin -> Products.
"""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    reactivated = await db.products.update_many(
        {"category": "stardust"}, {"$set": {"active": True, "coming_soon": False}}
    )
    print(f"Stardust products re-activated: {reactivated.modified_count}")

    starred = await db.products.update_many(
        {"is_featured": {"$exists": False}, "active": True, "coming_soon": {"$ne": True}},
        {"$set": {"is_featured": True}},
    )
    print(f"Backfilled is_featured=True: {starred.modified_count}")

    rest = await db.products.update_many(
        {"is_featured": {"$exists": False}}, {"$set": {"is_featured": False}}
    )
    print(f"Backfilled is_featured=False: {rest.modified_count}")

    async for p in db.products.find({}, {"name": 1, "category": 1, "active": 1, "is_featured": 1}):
        print(f"  {p['name'][:44]:46} {p['category']:16} active={p.get('active')} featured={p.get('is_featured')}")


asyncio.run(main())
