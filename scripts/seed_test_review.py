"""One-time: publish the single test review the owner asked for."""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    existing = await db.reviews.find_one({"title": "Test"})
    if existing:
        print("test review already present")
        return
    from datetime import datetime, timezone
    await db.reviews.insert_one({
        "order_id": "seed-test-review",
        "user_id": "",
        "user_email": os.environ["ADMIN_EMAIL"],
        "first_name": "Test",
        "rating": 5,
        "title": "Test",
        "body": "Just A Test",
        "status": "approved",
        "coupon_code": None,
        "created_at": datetime.now(timezone.utc),
    })
    print("seeded test review")
    client.close()


asyncio.run(main())
