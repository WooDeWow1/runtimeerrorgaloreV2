"""Push the local (preview) catalog to the live production site over its admin API."""
import os
from urllib.parse import urlparse

import httpx

SYNC_FIELDS = [
    "name", "description", "category", "price", "msrp", "image_url", "coins", "badge",
    "active", "coming_soon", "is_featured", "sellauth_product_id", "sellauth_variant_id",
    "variants",
]
TIMEOUT = 30


class SyncError(Exception):
    pass


def target_base(own_host: str = "") -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    if not base.startswith("https://"):
        raise SyncError("PUBLIC_APP_URL is not set to an https:// production URL")
    # Pushing a site to itself would rewrite live rows with their own values, so refuse it.
    host = (urlparse(base).hostname or "").lower()
    if own_host and host == own_host.split(":")[0].lower():
        raise SyncError(
            f"Sync target {host} is this same site — run the sync from preview, not production"
        )
    return base


def _key(p: dict) -> tuple:
    """SellAuth product id is the identity; names are editable and used only as a fallback."""
    sa_id = p.get("sellauth_product_id")
    return ("sa", int(sa_id)) if sa_id else ("name", (p.get("name") or "").strip().lower())


def _payload(p: dict) -> dict:
    return {k: p.get(k) for k in SYNC_FIELDS if p.get(k) is not None}


def _differences(src: dict, dst: dict) -> dict:
    out = {}
    for k in SYNC_FIELDS:
        a, b = src.get(k), dst.get(k)
        if isinstance(a, float) or isinstance(b, float):
            same = a is not None and b is not None and abs(float(a) - float(b)) < 0.005
        else:
            same = a == b
        if not same and not (a is None and b in (None, "", 0, [])):
            out[k] = {"from": b, "to": a}
    return out


async def _login(client: httpx.AsyncClient, base: str) -> str:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not (email and password):
        raise SyncError("ADMIN_EMAIL / ADMIN_PASSWORD are not configured")
    resp = await client.post(f"{base}/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise SyncError(f"Production login failed ({resp.status_code}). Admin password may differ there.")
    return resp.json()["access_token"]


async def _target_products(client, base, token) -> list:
    resp = await client.get(
        f"{base}/api/products",
        params={"include_inactive": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        raise SyncError(f"Could not read the production catalog ({resp.status_code})")
    return resp.json()


def _diff_plan(source: list[dict], target: list[dict]) -> tuple[list, list]:
    by_key = {_key(p): p for p in target}
    creates, updates = [], []
    for p in source:
        dst = by_key.get(_key(p))
        if not dst:
            creates.append({"name": p["name"], "category": p.get("category"), "price": p.get("price")})
            continue
        diff = _differences(p, dst)
        if diff:
            updates.append({"name": p["name"], "id": dst["id"], "changes": diff})
    return creates, updates


async def _set_featured(client, base, headers, product_id, is_featured: bool) -> None:
    await client.patch(f"{base}/api/products/{product_id}/featured",
                       json={"is_featured": bool(is_featured)}, headers=headers)


async def _apply_creates(client, base, headers, creates, src_by_name, errors) -> None:
    for c in creates:
        p = src_by_name[c["name"]]
        resp = await client.post(f"{base}/api/products", json=_payload(p), headers=headers)
        if resp.status_code >= 400:
            errors.append(f"create {p['name']}: {resp.status_code} {resp.text[:160]}")
            continue
        if p.get("is_featured"):
            await _set_featured(client, base, headers, resp.json()["id"], True)


async def _apply_updates(client, base, headers, updates, src_by_name, errors) -> None:
    for u in updates:
        p = src_by_name[u["name"]]
        body = {k: p.get(k) for k in u["changes"]}
        resp = await client.put(f"{base}/api/products/{u['id']}", json=body, headers=headers)
        if resp.status_code >= 400:
            errors.append(f"update {p['name']}: {resp.status_code} {resp.text[:160]}")
            continue
        if "is_featured" in body:
            await _set_featured(client, base, headers, u["id"], p.get("is_featured"))


async def plan(source: list[dict], apply: bool = False, own_host: str = "") -> dict:
    base = target_base(own_host)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        token = await _login(client, base)
        target = await _target_products(client, base, token)
        headers = {"Authorization": f"Bearer {token}"}
        creates, updates = _diff_plan(source, target)

        result = {
            "target": base,
            "source_count": len(source),
            "target_count": len(target),
            "creates": creates,
            "updates": updates,
            "applied": False,
            "errors": [],
        }
        if not apply or not (creates or updates):
            return result

        src_by_name = {p["name"]: p for p in source}
        await _apply_creates(client, base, headers, creates, src_by_name, result["errors"])
        await _apply_updates(client, base, headers, updates, src_by_name, result["errors"])

        result["applied"] = True
        result["target_count"] = len(await _target_products(client, base, token))
        return result
