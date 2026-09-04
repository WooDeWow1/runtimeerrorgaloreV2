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


def _site_url() -> str:
    """Public site URL used in email chrome. Must be https for the G3 link gate."""
    url = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
    return url if url.startswith("https://") else "https://pokecoins.cc"


def support_email() -> str:
    return os.environ.get("EMAIL_REPLY_TO", "")


def support_line() -> str:
    """Footer line so buyers can reply or write in directly."""
    address = support_email()
    if not address:
        return ""
    safe = escape(address)
    return f'Questions? Reply to this email or write to <a href="mailto:{safe}" style="color:#71717a">{safe}</a>.<br>'


def order_url(order: dict) -> str:
    """Absolute link to an order page. Always the public site so emailed links work anywhere."""
    return f"{_site_url()}/order/{order['id'] if 'id' in order else order['_id']}"


def admin_order_url(order_id: str) -> str:
    """Deep link that opens this order's chat in the admin console."""
    return f"{_site_url()}/admin?order={order_id}"


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


def _wrap(inner: str) -> str:
    """Shared pokecoins.cc branded shell: dark header wordmark + neon accent."""
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    site = escape(_site_url())
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f4f5;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #e4e4e7">'
        '<tr><td style="background:#050505;padding:20px 24px">'
        f'<a href="{site}" style="font-family:Arial,sans-serif;font-size:20px;font-weight:bold;'
        f'letter-spacing:-0.5px;color:#ffffff;text-decoration:none">POKE'
        '<span style="color:#00e6b8">COINS</span></a>'
        '</td></tr>'
        f'<tr><td style="padding:28px 24px;font-family:Arial,sans-serif;color:#18181b">{inner}</td></tr>'
        '<tr><td style="border-top:1px solid #e4e4e7;padding:16px 24px;'
        'font-family:Arial,sans-serif;font-size:11px;color:#71717a">'
        f'Sent by {brand} · <a href="{site}" style="color:#71717a">{site}</a><br>'
        f'{support_line()}'
        'We never ask for your password or payment details by email.'
        '</td></tr></table></td></tr></table>'
    )


def _button(url: str, label: str) -> str:
    return (
        f'<p style="margin:24px 0"><a href="{escape(url)}" style="background:#00e6b8;color:#050505;'
        'padding:13px 22px;text-decoration:none;font-weight:bold;font-size:14px;'
        f'display:inline-block;border-radius:2px">{escape(label)}</a></p>'
        f'<p style="font-size:11px;color:#71717a;margin:0">Or paste this link into your browser:<br>'
        f'{escape(url)}</p>'
    )


def support_reply_html(*, order_id: str, body: str, order_url: str) -> str:
    return _wrap(
        f'<h2 style="margin:0 0 14px;font-size:19px">New reply about order {escape(order_id[-8:])}</h2>'
        f'<blockquote style="margin:0;padding:14px 16px;border-left:3px solid #00e6b8;'
        f'background:#fafafa;font-size:14px;line-height:1.6;white-space:pre-wrap">{escape(body)}</blockquote>'
        + _button(order_url, "Open order chat")
    )


def customer_message_html(*, order_id: str, body: str, customer_email: str, admin_url: str) -> str:
    return _wrap(
        f'<h2 style="margin:0 0 14px;font-size:19px">New customer message — order {escape(order_id[-8:])}</h2>'
        f'<p style="margin:0 0 14px;font-size:13px;color:#3f3f46">From {escape(customer_email)}</p>'
        f'<blockquote style="margin:0;padding:14px 16px;border-left:3px solid #00e6b8;'
        f'background:#fafafa;font-size:14px;line-height:1.6;white-space:pre-wrap">{escape(body)}</blockquote>'
        + _button(admin_url, "Open in admin panel")
    )


def order_tracking_html(*, order_id: str, tracking_url: str, total: float, item_lines: list[str]) -> str:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    items = "".join(
        f'<li style="margin-bottom:4px">{escape(line)}</li>' for line in item_lines
    )
    return _wrap(
        f'<h2 style="margin:0 0 14px;font-size:19px">Payment received — order {escape(order_id[-8:])}</h2>'
        f'<p style="margin:0 0 16px;font-size:14px;line-height:1.6">Thanks for your order with {brand}. '
        'Payment is confirmed and your order is queued for fulfilment.</p>'
        f'<ul style="padding-left:18px;font-size:14px;margin:0 0 12px">{items}</ul>'
        f'<p style="font-size:14px;margin:0"><strong>Total paid: ${total:.2f}</strong></p>'
        + _button(tracking_url, "Track order & chat with us")
        + '<p style="font-size:13px;line-height:1.6;color:#3f3f46;margin:20px 0 0">'
        'That page has a live chat built in — message us there any time and we reply straight to you.</p>'
        '<p style="font-size:13px;line-height:1.6;color:#3f3f46;margin:12px 0 0">'
        'When an operator logs in, the status changes to <strong>Processing</strong> — please stay logged '
        'out of your game account until it says Completed.</p>'
    )

