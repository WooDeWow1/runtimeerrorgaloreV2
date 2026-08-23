"""One-time: attach SellAuth product/variant ids to our catalog, matched by SellAuth product id.

Variant ids are fetched live from the shop so they never have to be typed by hand.
Usage: python3 map_sellauth_ids.py [--apply]
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
import httpx  # noqa: E402
import server  # noqa: E402

# SellAuth product id -> our product name
MAPPING = {
    851924: "Weekly Event Ticket",
    851927: "Mega Raid Day Ticket",
    851928: "Monthly Go Pass",
    851929: "2,700 Pokécoins",
    851931: "5,600 Pokécoins",
    851933: "15,500 Pokécoins",
    851937: '"Size Matters" - 3x Platinum Medal Bundle',
    851941: "“Showcase Star” - Platinum Medal",
    851935: "1M Stardust Farming",
    851942: "5M Stardust Farming",
    851943: "10M Stardust Farming",
}


async def main(apply: bool):
    headers = {"Authorization": f"Bearer {os.environ['SELLAUTH_API_KEY']}",
               "Accept": "application/json"}
    url = f"https://api.sellauth.com/v1/shops/{os.environ['SELLAUTH_SHOP_ID']}/products"
    async with httpx.AsyncClient(timeout=30) as c:
        data = (await c.get(url, headers=headers)).json()
    remote = {p["id"]: p for p in (data.get("data") if isinstance(data, dict) else data)}

    for sa_id, name in MAPPING.items():
        rp = remote.get(sa_id)
        if not rp or not rp.get("variants"):
            print(f"  !! SellAuth product {sa_id} ({name}) not found or has no variant")
            continue
        variant = rp["variants"][0]
        ours = await server.db.products.find_one({"name": name})
        if not ours:
            print(f"  !! local product not found: {name}")
            continue
        price = float(variant["price"])
        note = "" if abs(price - float(ours["price"])) < 0.005 else \
            f"  (PRICE DIFFERS: site ${ours['price']} vs SellAuth ${price:.2f})"
        print(f"  {name} -> product {sa_id} / variant {variant['id']} @ ${price:.2f}{note}")
        if apply:
            await server.db.products.update_one(
                {"_id": ours["_id"]},
                {"$set": {"sellauth_product_id": sa_id,
                          "sellauth_variant_id": int(variant["id"]),
                          "price": price,
                          "updated_at": server.utc_now()}},
            )
    unmapped = [d["name"] async for d in server.db.products.find(
        {"sellauth_product_id": {"$in": [None]}})]
    print("unmapped (expected: Shundo coming-soon items):", unmapped)
    if not apply:
        print("\nDry run. Re-run with --apply to write.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
