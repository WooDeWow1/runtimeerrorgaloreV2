"""QA it14: verify the confirmation email body links to https://pokecoins.cc and actually sends."""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa
from emailer import order_tracking_html, order_url, send_email  # noqa


async def main():
    order_id = "6a8a89eb5dc466ed1a73a49f"
    order = await server.db.orders.find_one({"_id": server.oid(order_id)})
    url = order_url({"origin_url": order.get("origin_url", ""), "id": order_id})
    print("TRACKING_URL", url)
    assert url.startswith("https://pokecoins.cc/order/"), url
    html = order_tracking_html(
        order_id=order_id, tracking_url=url, total=order["total"],
        item_lines=[f"{i['name']} x{i['quantity']}" for i in order["items"]],
    )
    assert "pokecoins.cc" in html and "preview.emergentagent" not in html, "email body has wrong host"
    print("HTML_OK link count:", html.count("https://pokecoins.cc"))
    res = await send_email(to="delivered@resend.dev", subject="QA IT14 confirmation link check",
                           html=html)
    print("SEND_RESULT", res)


asyncio.run(main())
