"""QA it14: create one SellAuth catalog checkout (leave unpaid) and print the invoice price."""
import asyncio
import json
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa
import sellauth  # noqa


async def main():
    prod = await server.db.products.find_one({"name": "5,600 Pokécoins"})
    items = [{"product_id": str(prod["_id"]), "name": prod["name"], "category": prod["category"],
              "price": prod["price"], "quantity": 1,
              "sellauth_product_id": prod.get("sellauth_product_id"),
              "sellauth_variant_id": prod.get("sellauth_variant_id")}]
    data = await sellauth.create_checkout(items=items, email="qa-it14@gmail.com",
                                          session_id="qa-it14-probe", coupon=None)
    print("URL", data["url"])
    print("INVOICE_ID", data["invoice_id"])
    raw = data["raw"]
    print("RAW_KEYS", list(raw.keys()))
    inv = await sellauth.get_invoice(str(data["invoice_id"]))
    if inv:
        inner = inv.get("invoice") if isinstance(inv.get("invoice"), dict) else inv
        print("STATUS", inner.get("status"))
        for k in ("price", "total", "subtotal", "coupon", "coupon_id", "currency"):
            if k in inner:
                print(k.upper(), inner[k])
        print("ITEMS", json.dumps(inner.get("items", []))[:600])


asyncio.run(main())
