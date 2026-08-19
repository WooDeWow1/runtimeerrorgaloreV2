import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

EMAIL_BASE_URL = "https://integrations.emergentagent.com"

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> str | None:
    _assert_safe_email(subject, html)
    payload = {
        "to": [to],
        "subject": subject,
        "html": html,
        "from_name": os.environ["EMAIL_FROM_NAME"],
    }
    reply_to = os.environ.get("EMAIL_REPLY_TO")
    if reply_to:
        payload["contact_email"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": os.environ["EMERGENT_EMAIL_KEY"]},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as exc:
        logger.error("Email send failed: %s %s", exc.response.status_code, exc.response.text[:300])
        return None
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return None


def support_reply_html(*, order_id: str, body: str, order_url: str) -> str:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#111">'
        f"<h2 style=\"margin:0 0 12px\">New reply about order {escape(order_id[-8:])}</h2>"
        f'<blockquote style="margin:0 0 16px;padding:12px 16px;border-left:3px solid #00ffcc;'
        f'background:#f6f6f6;white-space:pre-wrap">{escape(body)}</blockquote>'
        f'<p><a href="{escape(order_url)}" style="background:#00ffcc;color:#000;padding:12px 20px;'
        'text-decoration:none;font-weight:bold;display:inline-block">Open order chat</a></p>'
        f'<p style="font-size:12px;color:#555">Or open this link: {escape(order_url)}</p>'
        f'<p style="font-size:12px;color:#888">Sent by {brand}. We never ask for your password or payment '
        "details by email.</p>"
        "</td></tr></table>"
    )


def order_tracking_html(*, order_id: str, tracking_url: str, total: float, item_lines: list[str]) -> str:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    items = "".join(f"<li>{escape(line)}</li>" for line in item_lines)
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#111">'
        f"<h2 style=\"margin:0 0 12px\">Payment received — order {escape(order_id[-8:])}</h2>"
        f"<p>Thanks for your order with {brand}. Your order is queued for fulfilment.</p>"
        f'<ul style="padding-left:18px">{items}</ul>'
        f"<p><strong>Total paid: ${total:.2f}</strong></p>"
        f'<p><a href="{escape(tracking_url)}" style="background:#00ffcc;color:#000;padding:12px 20px;'
        'text-decoration:none;font-weight:bold;display:inline-block">Track your order</a></p>'
        f'<p style="font-size:12px;color:#555">Or open this link: {escape(tracking_url)}</p>'
        '<p style="font-size:12px;color:#555">When an operator logs in you will see the status change to '
        "Processing — stay logged out of your game account until it says Completed.</p>"
        f'<p style="font-size:12px;color:#888">Sent by {brand}. We never ask for your password or payment '
        "details by email.</p>"
        "</td></tr></table>"
    )
